"""
Keeps the tools the app depends on up to date.

  yt-dlp, yt-dlp-ejs  PyPI wheels. A newer copy is unpacked into
                      %LOCALAPPDATA%\\DISO/packages and imported in front of the bundled
                      one. That works for the source run and for the .exe (which has
                      yt-dlp inside it), without needing pip.
  FFmpeg              the build this app installed itself, when its mirror offers a
                      newer one. A copy the user installed on their own is never touched.

Every download is checked against a SHA-256 digest before anything is unpacked. PyPI
publishes the digest of each wheel; the FFmpeg checksum comes from the same mirror.

Startup (see main.py and ui.App):
  activate()  before anything imports yt_dlp: installs the import hook
  start()     background thread: check everything, install what is outdated
  ready       set when yt_dlp may be imported; video_engine waits for it
"""
import importlib.abc
import importlib.machinery
import importlib.metadata
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import zipfile

import requests

from . import ffmpeg_setup
from .segmented_downloader import (TIMEOUT, DownloadError, FastDownloader, build_headers,
                                   get_proxies)
from .utils import app_data_dir, find_ffmpeg, human_size

PYPI_URL = "https://pypi.org/pypi/{}/json"
PACKAGES = {"yt-dlp": "yt_dlp", "yt-dlp-ejs": "yt_dlp_ejs"}  # PyPI name -> import name
PARALLEL = 4                  # connections per download (the wheels are small)

ready = threading.Event()     # set when yt_dlp may be imported
notices = queue.Queue()       # short texts for the window ("yt-dlp updated", "rolled back" ...)
_started = False
_overrides = {}               # import name -> folder that holds the newer copy
_active = {}                  # PyPI name -> version of the copy in use
_finder = None
_instance = None              # the Updater, so a rollback can update its cards
_ytdlp_lock = threading.Lock()
_ytdlp_checked = False        # the downloaded yt-dlp passed the smoke test


def _short(e) -> str:
    return str(e).strip()[:160] or type(e).__name__


# ---------------------------------------------------------------------- versions
def version_key(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def bundled_version(pkg: str) -> str:
    """Version of the copy that came with the app (pip install or inside the .exe)."""
    try:
        return importlib.metadata.version(pkg)
    except Exception:
        return ""


def effective_version(pkg: str) -> str:
    return _active.get(pkg) or bundled_version(pkg)


# ------------------------------------------------------------------ packages folder
def packages_dir() -> str:
    d = os.path.join(app_data_dir(), "packages")
    os.makedirs(d, exist_ok=True)
    return d


def _manifest_path() -> str:
    return os.path.join(packages_dir(), "manifest.json")


def _read_manifest() -> dict:
    try:
        with open(_manifest_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_manifest(data: dict) -> None:
    tmp = _manifest_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _manifest_path())


class _OverrideFinder(importlib.abc.MetaPathFinder):
    """Finds yt_dlp / yt_dlp_ejs in packages/ before the bundled copies (also inside the .exe)."""

    def __init__(self, roots: dict):
        self.roots = roots  # import name -> folder that contains it

    def find_spec(self, fullname, path=None, target=None):
        top = fullname.partition(".")[0]
        root = self.roots.get(top)
        if root is None:
            return None
        search = [root] if fullname == top else path
        return importlib.machinery.PathFinder.find_spec(fullname, search) if search else None


def _register(pkg: str, version: str) -> None:
    global _finder
    _overrides[PACKAGES[pkg]] = packages_dir()
    _active[pkg] = version
    if _finder is None:
        _finder = _OverrideFinder(_overrides)
        sys.meta_path.insert(0, _finder)


def activate() -> None:
    """Use the copies in packages/ that are not older than the bundled ones.
    Call before anything imports yt_dlp."""
    manifest = _read_manifest()
    for pkg, module in PACKAGES.items():
        ver = manifest.get(pkg, "")
        if ver and os.path.isdir(os.path.join(packages_dir(), module)) \
                and version_key(ver) >= version_key(bundled_version(pkg)):
            _register(pkg, ver)


def wait_ready(timeout: float = 90) -> None:
    """Called before yt_dlp is imported: waits for the startup update to finish."""
    if _started:
        ready.wait(timeout)


# ---------------------------------------------------------------------- rollback
def rollback(pkg: str, bad_version: str, reason="") -> str:
    """Undo a downloaded copy that does not work: bring back the previous downloaded copy,
    or fall back to the bundled one. The bad version is remembered, so the updater does not
    install it again on the next start. Returns the version now in use ("" = bundled)."""
    module = PACKAGES[pkg]
    final = os.path.join(packages_dir(), module)
    backup = os.path.join(packages_dir(), f".previous-{module}")
    manifest = _read_manifest()
    previous = dict(manifest.get("_previous", {}))
    bad = dict(manifest.get("_bad", {}))
    bad[pkg] = bad_version

    shutil.rmtree(final, ignore_errors=True)
    restored = previous.pop(pkg, "")
    if restored and os.path.isdir(backup):
        os.replace(backup, final)
        manifest[pkg] = restored
        _active[pkg] = restored
    else:
        restored = ""
        shutil.rmtree(backup, ignore_errors=True)
        manifest.pop(pkg, None)
        _active.pop(pkg, None)
        _overrides.pop(module, None)
    manifest["_previous"], manifest["_bad"] = previous, bad
    _write_manifest(manifest)

    for name in [n for n in sys.modules if n == module or n.startswith(module + ".")]:
        del sys.modules[name]  # forget the half-imported broken copy
    importlib.invalidate_caches()

    now = f"{restored} sürümüne" if restored else "yerleşik sürüme"
    notices.put(f"{pkg} {bad_version} çalışmadı, {now} dönüldü")
    if _instance is not None:
        _instance.rolled_back(pkg, bad_version, restored, reason)
    return restored


class _Culprit(Exception):
    """The smoke test failed and knows which package is to blame."""

    def __init__(self, pkg, cause):
        super().__init__(str(cause))
        self.pkg, self.cause = pkg, cause


def _smoke_test(yt_dlp) -> None:
    try:
        yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}).close()
    except Exception as e:
        raise _Culprit("yt-dlp", e)
    if "yt-dlp-ejs" in _active:
        try:
            importlib.import_module("yt_dlp_ejs")
        except Exception as e:
            raise _Culprit("yt-dlp-ejs", e)


def load_yt_dlp():
    """import yt_dlp. The first time, also prove that a downloaded copy works; if it does
    not, roll back the downloaded package that is to blame and try again."""
    global _ytdlp_checked
    with _ytdlp_lock:
        for attempt in range(3):
            try:
                import yt_dlp
                if not _ytdlp_checked:
                    _smoke_test(yt_dlp)
                    _ytdlp_checked = True
                return yt_dlp
            except Exception as e:
                cause = e.cause if isinstance(e, _Culprit) else e
                blame = e.pkg if isinstance(e, _Culprit) else "yt-dlp"
                if blame not in _active:  # the bundled copy is not ours to roll back
                    blame = "yt-dlp" if "yt-dlp" in _active else next(iter(_active), None)
                if blame is None or attempt == 2:  # nothing we installed to blame
                    raise cause
                rollback(blame, _active[blame], cause)
        raise RuntimeError("yt-dlp yüklenemedi")  # not reached


# ------------------------------------------------------------------ download/install
def fetch_release(pkg: str) -> dict:
    """Newest version of a PyPI package, with the URL and SHA-256 of its universal wheel."""
    # the JSON is ~1.2 MB uncompressed but ~270 KB with gzip, so ask for compression here
    headers = {**build_headers(), "Accept-Encoding": "gzip, deflate"}
    r = requests.get(PYPI_URL.format(pkg), headers=headers, timeout=TIMEOUT, proxies=get_proxies())
    r.raise_for_status()
    data = r.json()
    for f in data.get("urls", []):
        if f.get("packagetype") == "bdist_wheel" and f["filename"].endswith("-py3-none-any.whl"):
            return {"version": data["info"]["version"], "url": f["url"],
                    "sha256": f["digests"]["sha256"], "filename": f["filename"]}
    raise DownloadError(f"{pkg}: uygun paket bulunamadı")


def _download_verified(url, sha256, dest, on_progress) -> None:
    FastDownloader.cleanup(dest)
    if os.path.exists(dest):
        os.remove(dest)
    FastDownloader(url, dest, PARALLEL, on_progress=on_progress, limited=False).run()
    if ffmpeg_setup.sha256_file(dest) != sha256:
        os.remove(dest)
        raise DownloadError("SHA-256 eşleşmedi, dosya kullanılmadı")


def _in_use(module: str) -> bool:
    """yt_dlp (or yt_dlp_ejs) was imported in this run: its files must not change under it."""
    return module in sys.modules or any(m.startswith(module + ".") for m in list(sys.modules))


def _unpack(wheel: str, module: str) -> bool:
    """Replace packages/<module> with the one inside the wheel. The copy that was there is
    kept as .previous-<module> (for rollback). Returns True if there was one."""
    staging = os.path.join(packages_dir(), f".staging-{module}")
    shutil.rmtree(staging, ignore_errors=True)
    with zipfile.ZipFile(wheel) as zf:
        names = [n for n in zf.namelist() if n.startswith(module + "/")]
        if not names:
            raise DownloadError(f"{module} paketinde içerik yok")
        zf.extractall(staging, members=names)  # zipfile strips ".." and absolute paths
    final = os.path.join(packages_dir(), module)
    backup = os.path.join(packages_dir(), f".previous-{module}")
    shutil.rmtree(backup, ignore_errors=True)
    had_old = os.path.isdir(final)
    if had_old:
        os.replace(final, backup)
    os.replace(os.path.join(staging, module), final)
    shutil.rmtree(staging, ignore_errors=True)
    return had_old


# ------------------------------------------------------------------------- updater
class Component:
    """What the update panel shows for one tool."""

    def __init__(self, key: str, title: str, desc: str):
        self.key = key
        self.title = title
        self.desc = desc
        self.installed = ""     # version in use now
        self.latest = ""        # newest version the server has
        self.status = "idle"    # idle|checking|current|available|working|done|error|missing|manual
        self.progress = 0.0     # 0..1 while downloading
        self.message = ""
        self.checked_at = 0.0


class Updater:
    def __init__(self):
        self.components = {
            "yt-dlp": Component("yt-dlp", "yt-dlp",
                                "Sitelerin videolarını çözer. YouTube vb. değişince güncellenir."),
            "yt-dlp-ejs": Component("yt-dlp-ejs", "yt-dlp-ejs",
                                    "YouTube'un JavaScript tabanlı korumasını çözer."),
            "ffmpeg": Component("ffmpeg", "FFmpeg",
                                "Video ve ses birleştirme, MP3 dönüştürme."),
        }
        global _instance
        _instance = self
        self.notices = notices              # short texts for the window
        self.ffmpeg_busy = lambda: False    # the window sets this: True while ffmpeg is needed
        self.running = False
        self.writing = False        # True while files are being replaced
        self.last_check = 0.0
        self._lock = threading.Lock()

    def start(self) -> None:
        """Check and update in the background, once per launch."""
        global _started
        _started = True
        ready.set()                             # downloads never wait for the check (see _swap)
        if os.environ.get("HIZLI_NO_UPDATE"):   # for tests and offline use: skip the network check
            return
        threading.Thread(target=self._startup, daemon=True).start()

    def _startup(self):
        try:
            self.run(install=True)
        finally:
            ready.set()
        try:
            load_yt_dlp()        # warm up now (after any update): the first download does not wait for it
        except Exception:  # noqa: BLE001 - the download will say what is wrong
            pass

    def install_ffmpeg(self) -> bool:
        """Install FFmpeg now (the 'Kur' button). Returns False if another check is running."""
        if not self._lock.acquire(blocking=False):
            return False
        self.running = True
        try:
            self._install_ffmpeg(self.components["ffmpeg"])
        finally:
            self.running = False
            self._lock.release()
        return True

    def run(self, install: bool = True) -> bool:
        """Check every component; with install=True also update what is outdated.
        Blocks. Returns False if another check is already running."""
        if not self._lock.acquire(blocking=False):
            return False
        self.running = True
        try:
            outdated = self._check_packages()
            if install and outdated:
                for pkg, info in outdated.items():
                    self._install_package(pkg, info)
            self._check_ffmpeg(install)
        finally:
            ready.set()                         # whatever happened, yt-dlp is never left blocked
            self.running = False
            self.last_check = time.time()
            self._lock.release()
        return True

    # -- yt-dlp and yt-dlp-ejs
    def rolled_back(self, pkg, bad_version, restored, reason) -> None:
        """A downloaded copy did not work and was rolled back (see rollback())."""
        comp = self.components.get(pkg)
        if comp is None:
            return
        comp.installed = restored or bundled_version(pkg)
        comp.status = "error"
        comp.message = (f"{bad_version} çalışmadı, geri alındı ({_short(reason)}). "
                        "Daha yeni bir sürüm çıkınca tekrar denenecek.")

    def _check_packages(self) -> dict:
        outdated = {}
        bad = _read_manifest().get("_bad", {})
        for pkg in PACKAGES:
            comp = self.components[pkg]
            comp.status, comp.message = "checking", ""
            comp.installed = effective_version(pkg)
            try:
                info = fetch_release(pkg)
            except Exception as e:
                comp.status, comp.message = "error", f"Sunucuya ulaşamadım: {_short(e)}"
                continue
            comp.latest = info["version"]
            comp.checked_at = time.time()
            if info["version"] == bad.get(pkg):
                comp.status = "current"
                comp.message = f"{info['version']} bu bilgisayarda çalışmadı; daha yeni sürüm beklenecek"
            elif version_key(info["version"]) > version_key(comp.installed):
                comp.status, comp.message = "available", f"Yeni sürüm: {info['version']}"
                outdated[pkg] = info
            else:
                comp.status, comp.message = "current", ""
        return outdated

    def _install_package(self, pkg: str, info: dict) -> None:
        comp = self.components[pkg]
        module = PACKAGES[pkg]
        comp.status, comp.progress, comp.message = "working", 0.0, "İndiriliyor…"

        def on_progress(done, total, *_):
            comp.progress = (done / total) if total else 0.0
            comp.message = f"İndiriliyor… {human_size(done)} / {human_size(total)}"

        tmp = os.path.join(app_data_dir(), "update-tmp")
        try:
            os.makedirs(tmp, exist_ok=True)
            wheel = os.path.join(tmp, info["filename"])
            _download_verified(info["url"], info["sha256"], wheel, on_progress)
            comp.progress, comp.message = 1.0, "Kuruluyor…"
            # The files are swapped only while nobody imports yt-dlp (the import holds the same lock).
            # If a download already uses it, the files of a running yt-dlp are not touched: the new
            # version is installed at the next start, before the first download.
            with _ytdlp_lock:
                if _in_use(module):
                    comp.status = "available"
                    comp.message = f"{info['version']} hazır: DISO'yu bir dahaki açışında kurulacak"
                    return
                ready.clear()
                self.writing = True  # the window waits for this short step if it is closed now
                try:
                    had_old = _unpack(wheel, module)
                    manifest = _read_manifest()
                    previous = dict(manifest.get("_previous", {}))
                    if had_old and manifest.get(pkg):
                        previous[pkg] = manifest[pkg]   # rollback target
                    else:
                        previous.pop(pkg, None)
                    manifest[pkg] = info["version"]
                    manifest["_previous"] = previous
                    _write_manifest(manifest)
                finally:
                    self.writing = False
                    ready.set()
            _register(pkg, info["version"])
        except Exception as e:
            comp.status, comp.message = "error", f"Güncelleyemedim: {_short(e)}"
            return
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        comp.installed = info["version"]
        comp.status = "done"
        comp.message = "Güncellendi" + (" — yeniden başlatınca tam etkin olur" if module in sys.modules else "")
        self.notices.put(f"{comp.title} {info['version']} sürümüne güncellendi")

    # -- FFmpeg
    def _check_ffmpeg(self, install: bool) -> None:
        comp = self.components["ffmpeg"]
        path = find_ffmpeg()
        if not path:
            comp.status, comp.installed = "missing", ""
            comp.message = "Kurulu değil; MP3 ya da video birleştirirken kendim kurarım"
            return
        if not ffmpeg_setup.is_managed(path):
            comp.status, comp.installed = "manual", ffmpeg_setup.ffmpeg_version(path)
            comp.message = "Senin kendi kurulumun; ona dokunmam"
            return
        info = ffmpeg_setup.read_info()
        comp.installed = info.get("version") or ffmpeg_setup.ffmpeg_version(path)
        comp.status, comp.message = "checking", ""
        try:
            sha, _ = ffmpeg_setup.latest_release()
        except Exception as e:
            comp.status, comp.message = "error", f"Sunucuya ulaşamadım: {_short(e)}"
            return
        comp.checked_at = time.time()
        if sha == info.get("sha256"):
            comp.status, comp.message = "current", ""
            return
        comp.status, comp.message = "available", "Yeni FFmpeg derlemesi var"
        if install:
            self._install_ffmpeg(comp)

    def _install_ffmpeg(self, comp: Component) -> None:
        if self.ffmpeg_busy():
            comp.message = "Bir işlem FFmpeg kullanıyor; bitince tekrar dene"
            return
        comp.status, comp.progress, comp.message = "working", 0.0, "İndiriliyor…"

        def on_progress(done, total):
            comp.progress = (done / total) if total else 0.0
            comp.message = f"İndiriliyor… {human_size(done)} / {human_size(total)}"

        ffmpeg_setup.ensure_ffmpeg(progress=on_progress, force=True)
        if ffmpeg_setup.last_error:
            comp.status, comp.message = "error", f"Güncelleyemedim: {_short(ffmpeg_setup.last_error)}"
            return
        comp.installed = ffmpeg_setup.read_info().get("version", "")
        comp.status, comp.progress, comp.message = "done", 1.0, "Güncellendi"
        self.notices.put("FFmpeg güncellendi")
