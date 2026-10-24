"""Deno: the JavaScript runtime yt-dlp needs for YouTube (its protection is solved in JavaScript). DISO comes
with one; this keeps it new enough, the way ffmpeg_setup does for FFmpeg: the newest release of denoland/deno
on GitHub, its archive checked against the SHA-256 published beside it, deno.exe put into DISO's tools folder
(it comes first on PATH, see utils.tool_dirs) and tried before it is used. A Deno the user installed somewhere
else is never touched. Only a new minor version (2.9 -> 2.10) is downloaded: Deno makes a release almost every
week and a 40 MB download for each one would be too much."""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

import requests

from .logs import log
from .segmented_downloader import TIMEOUT, DownloadError, FastDownloader, build_headers, get_proxies
from .utils import EXE, subprocess_flags, user_tools_dir

ASSET = "deno-x86_64-pc-windows-msvc.zip"
API_URL = "https://api.github.com/repos/denoland/deno/releases/latest"
LATEST_URL = "https://github.com/denoland/deno/releases/latest"
DOWNLOAD_URL = "https://github.com/denoland/deno/releases/download/{tag}/" + ASSET
_VERSION = re.compile(r"deno\s+(\d+\.\d+\.\d+)", re.I)
_HASH = re.compile(r"\b([0-9a-fA-F]{64})\b")


def find():
    return shutil.which("deno")


def version_of(path) -> str:
    """'2.9.7' of a deno.exe, "" when it does not run."""
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30,
                             stdin=subprocess.DEVNULL, **subprocess_flags()).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    m = _VERSION.search(out or "")
    return m.group(1) if m else ""


def key(version: str) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d+", version or "")[:3]) or (0,)


def is_ours(path) -> bool:
    """DISO's own Deno: the one in its tools folder, or the one it came with (beside the installed DISO.exe)."""
    if not path:
        return False
    here = os.path.normcase(os.path.dirname(os.path.abspath(path)))
    ours = [user_tools_dir(), os.path.join(os.path.dirname(sys.executable), "deno")]
    return any(here == os.path.normcase(os.path.abspath(d)) for d in ours)


def wanted(installed: str, latest: str) -> bool:
    """Update when the newest one is a new minor (or major) version, not for every weekly patch."""
    return key(latest)[:2] > key(installed)[:2]


def latest_tag(get=requests.get) -> str:
    """'v2.10.1': GitHub's API, or (when it says "too many questions") where /releases/latest leads."""
    try:
        r = get(API_URL, headers=build_headers({"Accept": "application/vnd.github+json"}), timeout=TIMEOUT,
                proxies=get_proxies())
        r.raise_for_status()
        return r.json()["tag_name"]
    except Exception as e:  # noqa: BLE001 - try the page instead
        log.info("deno api: %s", e)
    r = get(LATEST_URL, headers=build_headers(), timeout=TIMEOUT, proxies=get_proxies(), allow_redirects=True)
    r.raise_for_status()
    m = re.search(r"/tag/(v[\w.\-]+)", r.url)
    if not m:
        raise DownloadError("Deno'nun son sürümü okunamadı")
    return m.group(1)


def install(tag: str, progress=None, tries=3) -> str:
    """Download Deno `tag` into the tools folder (checked, tried). Returns its path. Raises DownloadError."""
    url = DOWNLOAD_URL.format(tag=tag)
    r = requests.get(url + ".sha256sum", headers=build_headers(), timeout=TIMEOUT, proxies=get_proxies())
    r.raise_for_status()
    m = _HASH.search(r.text)
    if not m:
        raise DownloadError("Deno'nun SHA-256 değeri okunamadı")
    expected = m.group(1).lower()
    tools = user_tools_dir()
    archive = os.path.join(tools, "deno-download.zip")
    target = os.path.join(tools, "deno" + EXE)
    error = None
    try:
        for attempt in range(tries):                    # GitHub's file server now and then hangs up
            try:
                cb = (lambda d, t, s, e, c: progress(d, t)) if progress else None
                FastDownloader(url, archive, 4, on_progress=cb, limited=False).run()
                break
            except Exception as e:  # noqa: BLE001 - tried again, said at the end
                error = e
                time.sleep(1 + attempt)
        else:
            raise DownloadError(f"Deno indirilemedi: {error}", network=True)
        h = hashlib.sha256()
        with open(archive, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != expected:
            raise DownloadError("Deno: SHA-256 eşleşmedi, kullanılmadı")
        with zipfile.ZipFile(archive) as z:
            name = next((n for n in z.namelist() if os.path.basename(n).lower() == "deno" + EXE), None)
            if name is None:
                raise DownloadError("deno.exe arşivin içinde yok")
            with z.open(name) as src, open(target + ".new", "wb") as dst:
                shutil.copyfileobj(src, dst)
        if not version_of(target + ".new"):
            raise DownloadError("İndirilen Deno bu bilgisayarda çalışmadı")
        os.replace(target + ".new", target)
        log.info("deno %s installed: %s", tag, target)
        return target
    finally:
        for leftover in (archive, target + ".new"):
            try:
                os.remove(leftover)
            except OSError:
                pass
        FastDownloader.cleanup(archive)
