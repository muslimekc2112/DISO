"""DISO updating itself (the "DISO" card of the update window).

A new version is looked for on GitHub (the newest release of brand.HOME_URL) once at the start and then
once a day. It is only announced: nothing is downloaded until the user presses "Güncelle". Then the
release's setup (DISO-Setup-<version>.exe) is downloaded, checked against the SHA-256 GitHub publishes
for it (a file without one is never run), and started with --update: Windows asks for permission (UAC),
the setup puts the new version in place without a window and starts DISO again. Said no to Windows:
DISO just goes on. Where DISO cannot install itself (Linux, the portable DISO.exe, running from the
source) the button opens the release page instead.

GitHub's API allows 60 questions an hour per address (shared addresses run out); when it says no, the
release page itself is read: /releases/latest points at the newest tag, and its file list carries the
SHA-256 of every file."""
import os
import re
import subprocess
import sys
import threading
import time

from . import brand
from .logs import log
from .segmented_downloader import get_proxies
from .updater import Component, version_key
from .utils import WINDOWS, app_data_dir, human_size

REPO = brand.HOME_URL.split("github.com/", 1)[1].strip("/")          # muslimekc2112/DISO
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
LATEST_URL = f"https://github.com/{REPO}/releases/latest"
ASSETS_URL = f"https://github.com/{REPO}/releases/expanded_assets/{{tag}}"
TIMEOUT = 20
FIRST_LOOK = 15             # s after the start
EVERY = 24 * 3600           # then once a day
_SHA = re.compile(r"sha256:([0-9a-f]{64})")


def tag_version(tag: str) -> str:
    """'v1.0.2' -> '1.0.2'; 'v0.11.5-beta' -> '0.11.5'; '' when it is no version."""
    m = re.match(r"^v?(\d+(?:\.\d+)*)", (tag or "").strip())
    return m.group(1) if m else ""


def is_newer(version: str, current: str = brand.VERSION) -> bool:
    return bool(version) and version_key(version) > version_key(current)


def setup_asset(assets):
    """The Windows setup among a release's files ({name, url, size, sha256}), or None."""
    for a in assets:
        if re.fullmatch(r"DISO-Setup-[\w.\-]+\.exe", a.get("name") or ""):
            return a
    return None


def _get(url, **kw):
    import requests
    headers = {"User-Agent": f"DISO/{brand.VERSION}", **kw.pop("headers", {})}
    return requests.get(url, headers=headers, timeout=TIMEOUT, proxies=get_proxies(), **kw)


def from_api(get=_get) -> dict:
    r = get(API_URL, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    d = r.json()
    assets = [{"name": a.get("name", ""), "url": a.get("browser_download_url", ""), "size": int(a.get("size") or 0),
               "sha256": (_SHA.match(a.get("digest") or "") or [None, ""])[1]} for a in d.get("assets") or []]
    return {"tag": d.get("tag_name", ""), "version": tag_version(d.get("tag_name", "")), "page": d.get("html_url", ""),
            "notes": (d.get("body") or "").strip(), "assets": assets}


def from_page(get=_get) -> dict:
    """The same from the release page (no API, no limit). No notes there."""
    r = get(LATEST_URL, allow_redirects=False)
    tag = (r.headers.get("Location") or "").rstrip("/").rsplit("/tag/", 1)[-1] if r.status_code in (301, 302, 303, 307) else ""
    if not tag_version(tag):
        raise ValueError("GitHub'da sürüm bulunamadı")
    r = get(ASSETS_URL.format(tag=tag))
    r.raise_for_status()
    html = r.text
    links = list(re.finditer(rf'href="(/{re.escape(REPO)}/releases/download/[^"]+?/([^"/]+))"', html))
    assets = []
    for i, m in enumerate(links):
        end = links[i + 1].start() if i + 1 < len(links) else len(html)
        digest = _SHA.search(html, m.end(), end)                # GitHub writes a file's SHA-256 right after its link
        assets.append({"name": m.group(2), "url": "https://github.com" + m.group(1), "size": 0,
                       "sha256": digest.group(1) if digest else ""})
    return {"tag": tag, "version": tag_version(tag), "page": f"https://github.com/{REPO}/releases/tag/{tag}",
            "notes": "", "assets": assets}


def latest_release(get=_get) -> dict:
    try:
        return from_api(get)
    except Exception as e:  # noqa: BLE001 - the limit of the API (403), or it changed: the page tells the same
        log.info("GitHub API: %s; reading the release page", e)
        return from_page(get)


def installed_here(executable=None, frozen=None) -> bool:
    """True when this is the installed DISO (Program Files, registered by the setup): only that one is
    updated by the setup. The portable DISO.exe and the source are not."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not (WINDOWS and frozen):
        return False
    import winreg
    here = os.path.normcase(os.path.dirname(os.path.abspath(executable or sys.executable)))
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{brand.APP_ID}") as key:
                place = winreg.QueryValueEx(key, "InstallLocation")[0]
        except OSError:
            continue
        if place and os.path.normcase(os.path.abspath(place)) == here:
            return True
    return False


def run_as_admin(exe, parameters) -> bool:
    """Start the setup with administrator rights (Windows asks). False when the user said no."""
    import ctypes
    from ctypes import wintypes

    class Info(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

    info = Info(cbSize=ctypes.sizeof(Info), fMask=0x400, lpVerb="runas", lpFile=exe, lpParameters=parameters,
                lpDirectory=os.path.dirname(exe), nShow=1)          # 0x400: no error box of Windows' own
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(Info)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    return bool(shell32.ShellExecuteExW(ctypes.byref(info)))


class AppUpdate:
    """The DISO card: check() looks (in the background, never downloads); update() downloads, checks and
    starts the setup. `ready_to_quit` turns True when the setup runs: the window closes DISO then."""

    def __init__(self, release=None, can_install=None, start_setup=None, download=None):
        self.comp = Component("diso", brand.NAME, "Programın kendisi. Yeni sürüm çıkınca haber veririm; "
                                                  "“Güncelle” dersen indirip kurarım, sonra DISO yeniden açılır.")
        self.comp.installed = brand.VERSION_LABEL
        self._release, self._start_setup, self._download = release, start_setup, download
        self.can_install = installed_here() if can_install is None else can_install
        self.release = None
        self.running = False
        self.ready_to_quit = False
        self.announce = None            # (version, page) once a new version is found: the window tells the user
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self.last_check = 0.0

    # ------------------------------------------------------------------ looking
    def start(self):
        """Look now and then (once soon after the start, then daily)."""
        if os.environ.get("HIZLI_NO_UPDATE") or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="app-update", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        if self._stop.wait(FIRST_LOOK):
            return
        while True:
            self.check()
            if self._stop.wait(EVERY):
                return

    def check(self) -> bool:
        """Look for a new version (blocks). False if a look or an update is already running."""
        if not self._lock.acquire(blocking=False):
            return False
        self.running = True
        c = self.comp
        try:
            c.status, c.message = "checking", ""
            try:
                rel = (self._release or latest_release)()
            except Exception as e:  # noqa: BLE001 - shown on the card; tried again tomorrow
                log.info("DISO update check: %s", e)
                c.status, c.message = "error", f"GitHub'a ulaşamadım: {_short(e)}"
                return True
            self.release = rel
            c.latest, c.checked_at = rel["version"], time.time()
            if not is_newer(rel["version"]):
                c.status, c.message = "current", ""
            else:
                c.status = "available"
                c.message = (f"Yeni sürüm: {rel['version']}. Kurmak için “Güncelle”ye bas." if self.can_install else
                             f"Yeni sürüm: {rel['version']}. “Güncelle” indirme sayfasını açar.")
                if self.announce is None or self.announce[0] != rel["version"]:
                    self.announce = (rel["version"], rel["page"])
            return True
        finally:
            self.running = False
            self.last_check = time.time()
            self._lock.release()

    # ------------------------------------------------------------------ updating
    def update(self) -> str:
        """The "Güncelle" button (blocks; run it on another thread). Returns "page" (open the release page),
        "started" (the setup runs: close DISO), "cancelled" (Windows' question was answered no) or "error"."""
        rel = self.release
        if rel is None or not is_newer(rel["version"]):
            return "error"
        if not self.can_install:
            return "page"
        asset = setup_asset(rel["assets"])
        c = self.comp
        if asset is None or not asset["sha256"]:
            c.status, c.message = "error", "Bu sürümün kurulum dosyası (ya da SHA-256'sı) bulunamadı; sayfadan indir."
            return "page"
        if not self._lock.acquire(blocking=False):
            return "error"
        self.running = True
        try:
            c.status, c.progress, c.message = "working", 0.0, "İndiriliyor…"

            def on_progress(done, total, *_):
                c.progress = (done / total) if total else 0.0
                c.message = f"İndiriliyor… {human_size(done)} / {human_size(total)}"

            folder = os.path.join(app_data_dir(), "update-tmp")
            os.makedirs(folder, exist_ok=True)
            setup = os.path.join(folder, asset["name"])
            try:
                (self._download or _download_verified)(asset["url"], asset["sha256"], setup, on_progress)
            except Exception as e:  # noqa: BLE001
                log.info("DISO update download: %s", e)
                c.status, c.message = "error", f"İndiremedim: {_short(e)}"
                return "error"
            c.progress, c.message = 1.0, "Windows izin istiyor…"
            if not (self._start_setup or run_as_admin)(setup, "--update --launch"):
                c.status, c.message = "available", "Kurulum için izin verilmedi. İstediğinde tekrar “Güncelle”ye bas."
                return "cancelled"
            c.message = "Kuruluyor… DISO kapanıp yeni sürümle yeniden açılacak."
            self.ready_to_quit = True
            return "started"
        finally:
            self.running = False
            self._lock.release()


def _download_verified(url, sha256, dest, on_progress):
    from .updater import _download_verified as download
    download(url, sha256, dest, on_progress)


def _short(e) -> str:
    return str(e).splitlines()[0][:140] if str(e) else type(e).__name__
