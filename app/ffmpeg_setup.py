"""
Automatic FFmpeg installer.

MP3 conversion and MP4 merging (video stream + audio stream) need ffmpeg.
If ffmpeg cannot be found, on Windows we download the official "essentials" build
once, with our own fast multi-connection engine, check its SHA-256 against the checksum
the same mirror publishes, and unpack ffmpeg.exe / ffprobe.exe into
~/.hizli_indirici/tools (that folder is on PATH, see utils.setup_environment).
A mismatch means the archive is corrupt or was tampered with: it is never unpacked.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from urllib.parse import urlparse

import requests

from .segmented_downloader import (TIMEOUT, DownloadError, FastDownloader, build_headers,
                                   get_proxies)
from .utils import find_ffmpeg, subprocess_flags, user_tools_dir

# (archive, checksum file). The checksum file is either a bare hash (gyan.dev) or
# "<hash>  <file name>" lines (BtbN). Both are fetched from the same mirror as the archive.
FFMPEG_SOURCES = [
    ("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
     "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256"),
    ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
     "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/checksums.sha256"),
]
INFO_FILE = "ffmpeg.json"      # what was installed: sha256, source, version
_HASH = re.compile(r"\b([0-9a-fA-F]{64})\b")
_lock = threading.Lock()
last_error = ""


# ----------------------------------------------------------------------- checksums
def fetch_expected_sha256(archive_url: str, sha_url: str) -> str:
    """SHA-256 the mirror publishes for archive_url."""
    r = requests.get(sha_url, headers=build_headers(), timeout=TIMEOUT, proxies=get_proxies())
    r.raise_for_status()
    name = os.path.basename(urlparse(archive_url).path)
    for line in r.text.splitlines():
        m = _HASH.search(line)
        if not m:
            continue
        rest = line[m.end():].strip().lstrip("*").strip()
        if not rest or rest == name:  # bare hash, or "<hash>  <name>" for this archive
            return m.group(1).lower()
    raise DownloadError(f"{name} için SHA-256 değeri bulunamadı")


def latest_release() -> tuple:
    """(sha256, archive url) of the newest build offered by the first mirror that answers."""
    err = None
    for archive, sha_url in FFMPEG_SOURCES:
        try:
            return fetch_expected_sha256(archive, sha_url), archive
        except Exception as e:
            err = e
    raise DownloadError(f"FFmpeg sürümü kontrol edilemedi: {err}")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -------------------------------------------------------------------- install info
def _info_path() -> str:
    return os.path.join(user_tools_dir(), INFO_FILE)


def read_info() -> dict:
    try:
        with open(_info_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_info(data: dict) -> None:
    tmp = _info_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, _info_path())


def is_managed(path) -> bool:
    """True if this ffmpeg is the one this app installed (not the user's own copy)."""
    return bool(path) and os.path.dirname(os.path.abspath(path)) == os.path.abspath(user_tools_dir())


def ffmpeg_version(path) -> str:
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=10,
                             **subprocess_flags()).stdout
        m = re.search(r"ffmpeg version (\S+)", out)
        return m.group(1) if m else "?"
    except Exception:
        return ""


# ------------------------------------------------------------------------ install
def _extract(zip_path: str, target_dir: str) -> None:
    """Unpack ffmpeg.exe / ffprobe.exe. They are written beside the targets and swapped in
    at the end, so an interrupted install never leaves a half-written executable."""
    staged = {}
    with zipfile.ZipFile(zip_path) as zf:
        for m in zf.infolist():
            name = os.path.basename(m.filename).lower()
            if name in ("ffmpeg.exe", "ffprobe.exe") and "/bin/" in m.filename.replace("\\", "/"):
                tmp = os.path.join(target_dir, name + ".new")
                with zf.open(m) as src, open(tmp, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                staged[name] = tmp
    if "ffmpeg.exe" not in staged:
        raise RuntimeError("ffmpeg.exe was not found inside the downloaded archive")
    for name, tmp in staged.items():
        os.replace(tmp, os.path.join(target_dir, name))


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def ensure_ffmpeg(progress=None, sources=None, force=False):
    """
    Returns the path of ffmpeg (installing it first if needed) or None.
    progress(done_bytes, total_bytes) is called while the archive downloads.
    force=True installs the newest build even if ffmpeg is already there (update).
    """
    global last_error
    if not force and find_ffmpeg():
        return find_ffmpeg()
    if not force and not sys.platform.startswith("win"):
        last_error = "Please install ffmpeg with your package manager (apt/brew) and restart."
        return None
    with _lock:  # only one download even if several items need ffmpeg at once
        if not force and find_ffmpeg():
            return find_ffmpeg()
        tools = user_tools_dir()
        zip_path = os.path.join(tools, "ffmpeg-download.zip")
        for archive, sha_url in (sources or FFMPEG_SOURCES):
            try:
                expected = fetch_expected_sha256(archive, sha_url)
                _remove(zip_path)
                FastDownloader.cleanup(zip_path)
                cb = (lambda d, t, s, e, c: progress(d, t)) if progress else None
                FastDownloader(archive, zip_path, 8, on_progress=cb, limited=False).run()
                actual = sha256_file(zip_path)
                if actual != expected:
                    raise DownloadError(f"SHA-256 eşleşmedi (beklenen {expected[:12]}…, gelen {actual[:12]}…)")
                _extract(zip_path, tools)
                _write_info({"sha256": expected, "archive": archive,
                             "version": ffmpeg_version(os.path.join(tools, "ffmpeg.exe"))})
                last_error = ""
                break
            except Exception as e:  # try the next mirror
                last_error = f"{archive}: {e}"
            finally:
                _remove(zip_path)
        os.environ["PATH"] = tools + os.pathsep + os.environ.get("PATH", "")
        return find_ffmpeg()
