"""👤 The user's Google account, for their YouTube Music library (playlists, liked songs).

No password ever reaches DISO and no browser extension is needed: Edge (or Chrome) opens with a profile of
DISO's own and the user signs in on Google's own page, in a plain browser window. When that window is
closed, the same profile is opened once more without a window ("headless") and asked, over the browser's
DevTools connection, for its cookies; YouTube Music is then used with them (ytmusicapi, the way the
website itself is). The cookies are kept encrypted for this Windows user (DPAPI); signing out deletes them
and the profile. Google renews its cookies now and then: when a request is refused they are read again
from the profile (the browser renews them when it opens music.youtube.com)."""
import ctypes
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from ctypes import wintypes

from .logs import log
from .utils import app_data_dir, subprocess_flags

ORIGIN = "https://music.youtube.com"
LOGIN_URL = ("https://accounts.google.com/ServiceLogin?service=youtube&hl=tr"
             "&continue=https%3A%2F%2Fmusic.youtube.com%2F")
NEEDED = "__Secure-3PAPISID"         # without it the cookies are not a signed-in session
READ_TIMEOUT = 30                    # s: the headless browser answers in a few
LIKED = "LM"                         # YouTube Music's "liked songs" list
LIKED_TITLE = "Beğendiğim şarkılar"


def profile_dir(browser_id=None) -> str:
    """DISO's own profile of that browser (each browser keeps its own: their files do not mix)."""
    name = "google_profile" if browser_id in (None, "", "edge") else f"google_profile_{browser_id}"
    return os.path.join(app_data_dir(), name)


def store_path() -> str:
    return os.path.join(app_data_dir(), "google_account.bin")


# ------------------------------------------------------------------------------ DPAPI
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Encrypt / decrypt for this Windows user only (CryptProtectData / CryptUnprotectData)."""
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):   # UI_FORBIDDEN
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def save(data: dict, path=None):
    path = path or store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(_dpapi(json.dumps(data).encode("utf-8"), True))
    os.replace(tmp, path)


def load(path=None):
    """What was saved at sign-in ({cookie, agent, name, photo, handle}), or None."""
    try:
        with open(path or store_path(), "rb") as f:
            data = json.loads(_dpapi(f.read(), False).decode("utf-8"))
        return data if isinstance(data, dict) and data.get("cookie") else None
    except (OSError, ValueError):
        return None


def signed_in() -> bool:
    return load() is not None


def sign_out():
    """Forget the account: the saved cookies and the browser profile (its session) both go."""
    for path in (store_path(), store_path() + ".tmp"):
        try:
            os.remove(path)
        except OSError:
            pass
    for bid in CHROMIUM:
        shutil.rmtree(profile_dir(bid), ignore_errors=True)


# ------------------------------------------------------------------------------ the browser
CHROMIUM = ("chrome", "edge", "brave", "vivaldi", "opera")      # the ones that can be asked for their cookies
_DEFAULT_PROGIDS = {"chromehtml": "chrome", "msedgehtm": "edge", "bravehtml": "brave", "vivaldihtm": "vivaldi",
                    "operastable": "opera", "operagxstable": "opera"}


def default_browser_id():
    """The browser Windows opens links with ("chrome", "edge", "firefox" …), or ""."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations"
                                                       r"\https\UserChoice") as k:
            progid = str(winreg.QueryValueEx(k, "ProgId")[0]).lower()
    except OSError:
        return ""
    if progid.startswith("firefox"):
        return "firefox"
    return next((bid for key, bid in _DEFAULT_PROGIDS.items() if progid.startswith(key)), "")


def usable_browsers(found=None) -> dict:
    """{id: program} of the browsers on this PC that the Google sign-in can use, the default one first."""
    from . import extension_setup
    found = extension_setup.find_browsers() if found is None else found
    default = default_browser_id()
    order = ([default] if default in CHROMIUM else []) + [b for b in CHROMIUM if b != default]
    return {bid: found[bid] for bid in order if found.get(bid)}


def find_browser(prefer=""):
    """(id, program): the chosen one, else the default browser (when it can be used), else Chrome, Edge …"""
    usable = usable_browsers()
    if prefer in usable:
        return prefer, usable[prefer]
    return next(iter(usable.items()), (None, None))


def open_login(exe, browser_id=None):
    """The sign-in window (a plain browser window: Google lets people sign in there)."""
    profile = profile_dir(browser_id)
    os.makedirs(profile, exist_ok=True)
    return subprocess.Popen([exe, f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                             "--new-window", LOGIN_URL], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def cookie_header(cookies) -> str:
    """'name=value; …' of the youtube.com cookies (as the browser sends them to music.youtube.com)."""
    seen, parts = set(), []
    for c in cookies or []:
        domain = (c.get("domain") or "").lstrip(".")
        if domain == "youtube.com" or domain.endswith(".youtube.com"):
            if c.get("name") and c["name"] not in seen:
                seen.add(c["name"])
                parts.append(f"{c['name']}={c.get('value', '')}")
    return "; ".join(parts)


def _devtools(profile, timeout):
    """(port, browser path) from the DevToolsActivePort file the browser writes when it is ready."""
    path = os.path.join(profile, "DevToolsActivePort")
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().split()
            if len(lines) >= 2:
                return int(lines[0]), lines[1]
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    return None, None


class _Cdp:
    """A minimal DevTools connection: call(method, **params) -> result."""

    def __init__(self, url):
        from websockets.sync.client import connect
        self.ws = connect(url, max_size=None, open_timeout=10)
        self.n = 0

    def call(self, method, timeout=15, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            msg = json.loads(self.ws.recv(timeout=max(0.1, end - time.monotonic())))
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise OSError(msg["error"].get("message", "devtools error"))
                return msg.get("result", {})
        raise TimeoutError(method)

    def close(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass


def read_session(exe, visit=True, timeout=READ_TIMEOUT, browser_id=None):
    """Open DISO's browser profile without a window and take its cookies: {cookie, agent} (cookie "" when
    nobody is signed in there). visit: open music.youtube.com first, so the browser renews old cookies."""
    profile = profile_dir(browser_id)
    try:
        os.remove(os.path.join(profile, "DevToolsActivePort"))
    except OSError:
        pass
    proc = subprocess.Popen([exe, "--headless=new", f"--user-data-dir={profile}", "--remote-debugging-port=0",
                             "--no-first-run", "--no-default-browser-check", "--disable-gpu", "about:blank"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            **subprocess_flags())
    cdp = None
    try:
        port, path = _devtools(profile, timeout)
        if port is None:
            raise OSError("the browser did not start")
        cdp = _Cdp(f"ws://127.0.0.1:{port}{path}")
        agent = cdp.call("Browser.getVersion").get("userAgent", "").replace("HeadlessChrome", "Chrome")
        if visit:
            cdp.call("Target.createTarget", url=ORIGIN + "/")
            time.sleep(4)                                   # the page loads and renews what has to be
        cookies = cdp.call("Storage.getCookies").get("cookies", [])
        header = cookie_header(cookies)
        try:
            cdp.call("Browser.close", timeout=5)
        except (OSError, TimeoutError):
            pass
        return {"cookie": header if f"{NEEDED}=" in header else "", "agent": agent}
    finally:
        if cdp is not None:
            cdp.close()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


# ------------------------------------------------------------------------------ YouTube Music
def headers(data) -> dict:
    """What ytmusicapi needs to act as the signed-in website (it adds a fresh SAPISIDHASH to each request)."""
    return {"cookie": data["cookie"], "authorization": "SAPISIDHASH 0_0", "origin": ORIGIN, "x-origin": ORIGIN,
            "x-goog-authuser": "0", "accept": "*/*", "content-type": "application/json",
            "user-agent": data.get("agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def client(data=None):
    from ytmusicapi import YTMusic
    data = data or load()
    if not data:
        raise PermissionError("not signed in")
    return YTMusic(auth=headers(data))


def account_info(api) -> dict:
    info = api.get_account_info() or {}
    return {"name": info.get("accountName") or "", "handle": info.get("channelHandle") or "",
            "photo": info.get("accountPhotoUrl") or ""}


def playlists(api) -> list:
    """[{id, title, count}] of the library: liked songs first, then the playlists as YouTube Music lists them."""
    out = [{"id": LIKED, "title": LIKED_TITLE, "count": None}]
    for p in api.get_library_playlists(limit=None) or []:
        pid = p.get("playlistId")
        if not pid or pid == LIKED:
            continue
        count = p.get("count")
        try:
            count = int(str(count).replace(".", "").replace(",", "").split()[0]) if count is not None else None
        except (ValueError, IndexError):
            count = None
        out.append({"id": pid, "title": (p.get("title") or pid).strip(), "count": count})
    return out


def tracks(api, playlist_id) -> list:
    """The songs of a list as the music search gives them ({url, title, channel, …}), in order."""
    from .music_search import ytmusic_result
    data = api.get_playlist(playlist_id, limit=None) or {}
    return [r for r in map(ytmusic_result, data.get("tracks") or []) if r]


def _refused(e) -> bool:
    text = str(e).lower()
    return any(w in text for w in ("401", "403", "sign in", "signed in", "login", "credentials", "unauthorized"))


class Account:
    """The account on worker threads: connect(), refresh(), library(), songs(id), each answers through
    drain() as (what, result, error). The window polls drain() (it must not wait for the network)."""

    def __init__(self, browser=None, browser_id=None, prefer=""):
        self.data = load()
        if browser is None:
            browser_id, browser = find_browser(prefer or (self.data or {}).get("browser", ""))
        self.browser, self.browser_id = browser, browser_id
        self._done = queue.Queue()
        self._login = None
        self._cancel = threading.Event()
        self.busy = False

    @property
    def connected(self) -> bool:
        return bool(self.data)

    def _run(self, what, work):
        def job():
            try:
                self._done.put((what, work(), None))
            except Exception as e:  # noqa: BLE001 - shown to the user
                log.info("google %s: %s", what, e)
                self._done.put((what, None, e))
            finally:
                self.busy = False
        self.busy = True
        threading.Thread(target=job, daemon=True, name=f"google-{what}").start()

    def drain(self):
        out = []
        while True:
            try:
                out.append(self._done.get_nowait())
            except queue.Empty:
                return out

    def _call(self, fn):
        """fn(api), once more with renewed cookies when YouTube refuses the old ones."""
        try:
            return fn(client(self.data))
        except Exception as e:  # noqa: BLE001
            if not _refused(e) or not self.browser:
                raise
            fresh = read_session(self.browser, browser_id=self.browser_id)
            if not fresh["cookie"]:
                raise PermissionError("signed out") from e
            self.data = dict(self.data, **fresh)
            save(self.data)
            return fn(client(self.data))

    # ---- what the window asks for
    def connect(self):
        """Open the sign-in window; when it is closed, take the session ("connected", info)."""
        if not self.browser:
            raise FileNotFoundError("no browser")
        self._cancel.clear()

        def work():
            self._login = open_login(self.browser, self.browser_id)
            while self._login.poll() is None:
                if self._cancel.is_set():
                    self._login.terminate()
                    raise InterruptedError("cancelled")
                time.sleep(0.3)
            time.sleep(1)                                   # the profile is let go of
            fresh = read_session(self.browser, visit=False, browser_id=self.browser_id)
            if not fresh["cookie"]:
                raise PermissionError("not signed in")
            info = account_info(client(fresh))
            self.data = dict(fresh, browser=self.browser_id or "", **info)
            save(self.data)
            return info
        self._run("connected", work)

    def cancel(self):
        self._cancel.set()

    def library(self):
        self._run("library", lambda: self._call(playlists))

    def songs(self, items):
        """items: [{id, title}] -> [(title, songs)] (one after another; a list that fails is left out)."""
        def work():
            out = []
            for p in items:
                try:
                    out.append((p["title"], self._call(lambda api, p=p: tracks(api, p["id"]))))
                except Exception as e:  # noqa: BLE001
                    log.info("google list %s: %s", p.get("id"), e)
            return out
        self._run("songs", work)

    def use_browser(self, browser_id):
        """Sign in with another browser (its program is looked up again)."""
        bid, exe = find_browser(browser_id)
        if exe:
            self.browser_id, self.browser = bid, exe

    def sign_out(self):
        sign_out()
        self.data = None
