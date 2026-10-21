"""🧲 Torrents: magnet links, .torrent links and .torrent files, downloaded by aria2.

aria2 (https://aria2.github.io, GPL, one small aria2c.exe) is downloaded the first time a torrent is
added, once, from its GitHub release; its SHA-256 is written below (the same one other package managers
check), so a changed or broken archive is never used. Every torrent runs in an aria2c of its own that only
DISO talks to (JSON-RPC on 127.0.0.1 with a secret); DISO asks it how far it is twice a second and shows
it like any other download. Pause stops that aria2c (aria2's '.aria2' control file keeps what is done:
"resume" goes on from there), cancel also deletes the torrent's half files. When a torrent is complete it
is not shared on (seed time 0): DISO is a downloader, not a torrent client that keeps uploading."""
import base64
import json
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
import zipfile
from urllib.parse import unquote, urlsplit

import requests

from .logs import log
from .segmented_downloader import DownloadError, DownloadStopped, FastDownloader
from .utils import EXE, human_size, subprocess_flags, user_tools_dir

ARIA2_VERSION = "1.37.0"
ARIA2_URL = ("https://github.com/aria2/aria2/releases/download/release-1.37.0/"
             "aria2-1.37.0-win-64bit-build1.zip")
ARIA2_SHA256 = "67d015301eef0b612191212d564c5bb0a14b5b9c4796b76454276a4d28d9b288"
ARIA2_SIZE = "~2.5 MB"
POLL = 0.5
STARTUP_WAIT = 10
_lock = threading.Lock()


# ------------------------------------------------------------------------ what a torrent is
def is_magnet(url: str) -> bool:
    return (url or "").strip().lower().startswith("magnet:?")


def is_torrent_link(url: str) -> bool:
    """A magnet link, a link to a .torrent file, or a .torrent file on this computer (file:///…)."""
    url = (url or "").strip()
    if is_magnet(url):
        return True
    parts = urlsplit(url)
    return parts.scheme.lower() in ("http", "https", "file") and unquote(parts.path).lower().endswith(".torrent")


def local_torrent(url: str) -> str:
    """The path of a file:/// .torrent link ("" for other links)."""
    parts = urlsplit(url or "")
    if parts.scheme.lower() != "file":
        return ""
    path = unquote(parts.path)
    if len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return os.path.normpath(path)


def magnet_name(url: str) -> str:
    """The name a magnet link carries (dn=…), else ""."""
    from urllib.parse import parse_qs
    return (parse_qs(urlsplit(url).query).get("dn") or [""])[0].strip()


# ------------------------------------------------------------------------ aria2 itself
def find_aria2():
    found = shutil.which("aria2c")
    if found:
        return found
    candidate = os.path.join(user_tools_dir(), "aria2c" + EXE)
    return candidate if os.path.isfile(candidate) else None


def _sha256(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_aria2(progress=None, url=ARIA2_URL, sha256=ARIA2_SHA256, tries=4):
    """The path of aria2c, downloading it first when it is not there. Raises DownloadError."""
    found = find_aria2()
    if found:
        return found
    with _lock:
        found = find_aria2()
        if found:
            return found
        tools = user_tools_dir()
        archive = os.path.join(tools, "aria2-download.zip")
        error = None
        for attempt in range(tries):                     # GitHub's file server now and then hangs up
            try:
                cb = (lambda d, t, s, e, c: progress(d, t)) if progress else None
                FastDownloader(url, archive, 4, on_progress=cb, limited=False).run()
                break
            except Exception as e:  # noqa: BLE001 - tried again, said at the end
                error = e
                time.sleep(1 + attempt)
        else:
            raise DownloadError(f"aria2 indirilemedi: {error}", network=True)
        try:
            actual = _sha256(archive)
            if actual != sha256:
                raise DownloadError(f"aria2: SHA-256 eşleşmedi (beklenen {sha256[:12]}…, gelen {actual[:12]}…)")
            target = os.path.join(tools, "aria2c" + EXE)
            with zipfile.ZipFile(archive) as z:
                member = next((m for m in z.namelist() if os.path.basename(m).lower() == "aria2c" + EXE), None)
                if member is None:
                    raise DownloadError("aria2c arşivin içinde yok")
                with z.open(member) as src, open(target + ".new", "wb") as dst:
                    shutil.copyfileobj(src, dst)
            os.replace(target + ".new", target)
            log.info("aria2 %s installed: %s", ARIA2_VERSION, target)
            return target
        finally:
            for leftover in (archive,):
                try:
                    os.remove(leftover)
                except OSError:
                    pass
            FastDownloader.cleanup(archive)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Aria2:
    """One aria2c that downloads one torrent into `folder`, driven over JSON-RPC."""

    def __init__(self, exe, folder):
        self.port, self.secret = _free_port(), secrets.token_hex(16)
        self.folder = folder
        args = [exe, "--enable-rpc", "--rpc-listen-all=false", f"--rpc-listen-port={self.port}",
                f"--rpc-secret={self.secret}", f"--dir={folder}", "--continue=true", "--seed-time=0",
                "--bt-save-metadata=true", "--bt-load-saved-metadata=true", "--follow-torrent=true",
                "--file-allocation=none", "--console-log-level=error", "--summary-interval=0",
                "--auto-file-renaming=false", "--allow-overwrite=false", "--bt-detach-seed-only=true",
                f"--stop-with-process={os.getpid()}"]
        self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE, **subprocess_flags())
        deadline = time.time() + STARTUP_WAIT
        while True:
            try:
                self.call("getVersion")
                return
            except (requests.RequestException, DownloadError):
                if self.proc.poll() is not None or time.time() > deadline:
                    err = (self.proc.stderr.read() or b"").decode("utf-8", "replace").strip() if self.proc.poll() is not None else ""
                    self.close()
                    raise DownloadError(f"aria2 başlamadı {err}".strip())
                time.sleep(0.15)

    def call(self, method, *params):
        body = {"jsonrpc": "2.0", "id": "diso", "method": "aria2." + method,
                "params": [f"token:{self.secret}", *params]}
        r = requests.post(f"http://127.0.0.1:{self.port}/jsonrpc", data=json.dumps(body), timeout=10,
                          proxies={"http": None, "https": None})
        data = r.json()
        if "error" in data:
            raise DownloadError(str(data["error"].get("message") or data["error"]))
        return data.get("result")

    def close(self, wait=5.0):
        """Stop aria2c. After a pause it is given time to write down what is done; a complete torrent
        needs nothing more (aria2 would still say goodbye to the tracker: seconds for nothing)."""
        try:
            self.call("forceShutdown")
        except Exception:  # noqa: BLE001 - it is killed below anyway
            pass
        try:
            self.proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            try:
                self.proc.wait(timeout=5)                    # its files are let go only when it is gone
            except (subprocess.TimeoutExpired, OSError):
                pass
        except OSError:
            pass


# ------------------------------------------------------------------------ one torrent in the list
KEYS = ["status", "totalLength", "completedLength", "downloadSpeed", "connections", "numSeeders", "followedBy",
        "bittorrent", "errorMessage", "errorCode", "files", "infoHash", "seeder"]


def _name(status) -> str:
    bt = status.get("bittorrent") or {}
    return ((bt.get("info") or {}).get("name") or "").strip()


def _paths(status) -> list:
    return [f.get("path") for f in status.get("files") or [] if f.get("path") and not f["path"].startswith("[METADATA]")]


class Stopper:
    """What item.attach() needs: stop(reason) ends the wait loop."""

    def __init__(self):
        self.reason = None

    def stop(self, reason="pause"):
        self.reason = reason


def run(item, aria2_factory=Aria2):
    """Download the torrent of `item` (blocking, on the manager's worker thread). Sets item.title,
    item.final_path and the progress; raises DownloadStopped on pause / cancel."""
    from .models import DOWNLOADING
    item.message = f"Torrent için aria2 indiriliyor (tek seferlik, {ARIA2_SIZE})…" if not find_aria2() else ""
    exe = ensure_aria2(lambda d, t: setattr(item, "message", f"aria2 indiriliyor… {human_size(d)}"))
    os.makedirs(item.folder, exist_ok=True)
    stopper = Stopper()
    item.attach(stopper)
    session = aria2_factory(exe, item.folder)
    known_paths, status, finished, cancelled, since = [], {}, False, False, time.time()
    try:
        local = local_torrent(item.url)
        if local:
            with open(local, "rb") as f:
                gid = session.call("addTorrent", base64.b64encode(f.read()).decode("ascii"))
        else:
            gid = session.call("addUri", [item.url])
        item.state = DOWNLOADING
        item.title = item.title or magnet_name(item.url) or item.title
        item.message = "Torrent bilgisi alınıyor (eşler aranıyor)…"
        while True:
            if stopper.reason or item.stop_reason:
                raise DownloadStopped(stopper.reason or item.stop_reason)
            status = session.call("tellStatus", gid, KEYS)
            state = status.get("status")
            known_paths = _paths(status) or known_paths
            if state == "complete" and status.get("followedBy"):
                gid = status["followedBy"][0]                # the metadata came: now the files themselves
                continue
            if state == "error":
                raise DownloadError(f"Torrent indirilemedi: {status.get('errorMessage') or status.get('errorCode')}")
            if state == "removed":
                raise DownloadStopped("cancel")
            _show(item, status)
            whole = status.get("seeder") == "true" and _name(status)      # every piece is here and checked
            if state == "complete" or whole:
                name = _name(status)
                item.final_path = os.path.join(item.folder, name) if name else (known_paths[0] if known_paths else "")
                item.message = ""
                finished = True
                return item.final_path
            time.sleep(POLL)
    except DownloadStopped as e:
        if e.reason == "cancel":
            item.temp_files = list(item.temp_files) + _leftovers(item.folder, status, known_paths)
            cancelled = True
        raise
    finally:
        session.close(wait=1.0 if finished else 5.0)
        if finished:
            _forget_metadata(item.folder, status, item.url, since)
        elif cancelled:
            own = os.path.normcase(local_torrent(item.url) or "?")
            item.temp_files += [p for p in _saved_metadata(item.folder, status, since) if os.path.normcase(p) != own]


def _show(item, status):
    total = int(status.get("totalLength") or 0)
    done = int(status.get("completedLength") or 0)
    speed = float(status.get("downloadSpeed") or 0)
    name = _name(status)
    if name:
        item.title = name
    conns = int(status.get("connections") or 0)
    eta = (total - done) / speed if speed > 0 and total else None
    item.on_progress(done, total, speed, eta, conns)
    if not name and not total:
        item.message = "Torrent bilgisi alınıyor (eşler aranıyor)…"
    elif conns == 0 and done < total:
        item.message = "Eş aranıyor…"
    else:
        seeders = status.get("numSeeders")
        item.message = f"🧲 {conns} eş" + (f", {seeders} tam" if seeders not in (None, "", "0") else "")


def _saved_metadata(folder, status, since) -> list:
    """The .torrent files aria2 wrote into `folder` for this torrent since `since` (to go on after a pause)."""
    name = _name(status).encode("utf-8")
    mark = b"4:name%d:%s" % (len(name), name)
    out = []
    try:
        entries = os.listdir(folder)
    except OSError:
        return out
    for entry in entries:
        path = os.path.join(folder, entry)
        try:
            if entry.lower().endswith(".torrent") and os.path.getmtime(path) >= since - 1                     and os.path.getsize(path) < 50_000_000 and mark in open(path, "rb").read():
                out.append(path)
        except OSError:
            continue
    return out


def _forget_metadata(folder, status, url, since):
    """The .torrent aria2 saved beside the files is not needed once they are complete (never the user's own)."""
    own = os.path.normcase(local_torrent(url) or "?")
    for path in _saved_metadata(folder, status, since):
        if os.path.normcase(path) != own:
            try:
                os.remove(path)
            except OSError:
                pass


def _leftovers(folder, status, paths) -> list:
    """The files a cancelled torrent leaves: its half files and aria2's control files (only these)."""
    out = []
    for p in paths:
        out += [p, p + ".aria2"]
    name = _name(status)
    if name:
        top = os.path.join(folder, name)
        out += [top + ".aria2"]
    return out


def remove_empty_dirs(paths, folder):
    """After a cancel: the torrent's own folders that are now empty go too (never `folder` itself)."""
    base = os.path.normcase(os.path.abspath(folder))
    dirs = sorted({os.path.dirname(os.path.abspath(p)) for p in paths}, key=len, reverse=True)
    for d in dirs:
        while os.path.normcase(d).startswith(base + os.sep) and os.path.isdir(d) and not os.listdir(d):
            try:
                os.rmdir(d)
            except OSError:
                break
            d = os.path.dirname(d)
