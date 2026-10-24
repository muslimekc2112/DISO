"""
Automatic FFmpeg installer.

MP3 conversion and MP4 merging (video stream + audio stream) need ffmpeg.
If ffmpeg cannot be found (or an update is asked for) we download a static build for this system
once, with our own fast multi-connection engine, check its SHA-256 against the checksum
the same mirror publishes, and unpack ffmpeg / ffprobe into the tools folder of DISO's data
(%LOCALAPPDATA%\\DISO/tools; that folder is on PATH, see utils.setup_environment).
A mismatch means the archive is corrupt or was tampered with: it is never unpacked.

Windows: gyan.dev, else BtbN. Linux: BtbN. macOS: martin-riedl.de (ffmpeg and ffprobe come as
two archives there).
"""
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import threading
import zipfile
from urllib.parse import urlparse

import requests

from .segmented_downloader import (TIMEOUT, DownloadError, FastDownloader, build_headers,
                                   get_proxies)
from .utils import EXE, MAC, WINDOWS, bundled_ffmpeg_dirs, find_ffmpeg, subprocess_flags, user_tools_dir

BESIDE = "<archive>.sha256"     # the checksum file is the archive's own address + ".sha256" (after its redirect)
TOOLS = ("ffmpeg" + EXE, "ffprobe" + EXE)


def platform_sources(system=None, machine=None) -> list:
    """The mirrors of this system, best first: (archive, checksum file[, more (archive, checksum) parts]).
    The checksum file is either a bare hash (gyan.dev), "<hash>  <file name>" lines (BtbN) or the
    archive's own .sha256 (martin-riedl.de). Both come from the same mirror as the archive."""
    system = (system or ("windows" if WINDOWS else "macos" if MAC else "linux")).lower()
    arm = (machine or platform.machine()).lower() in ("arm64", "aarch64")
    btbn = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    if system == "windows":
        return [("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
                 "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256"),
                (btbn + "ffmpeg-master-latest-win64-gpl.zip", btbn + "checksums.sha256")]
    if system == "macos":
        base = f"https://ffmpeg.martin-riedl.de/redirect/latest/macos/{'arm64' if arm else 'amd64'}/release/"
        return [(base + "ffmpeg.zip", BESIDE, [(base + "ffprobe.zip", BESIDE)])]
    linux = "linuxarm64" if arm else "linux64"
    return [(btbn + f"ffmpeg-master-latest-{linux}-gpl.tar.xz", btbn + "checksums.sha256")]


FFMPEG_SOURCES = platform_sources()
INFO_FILE = "ffmpeg.json"      # what was installed: sha256, source, version
BUNDLED_FILE = "ffmpeg-bundled.json"   # the FFmpeg DISO came with: its version, the mirror's build then
_HASH = re.compile(r"\b([0-9a-fA-F]{64})\b")
_lock = threading.Lock()
last_error = ""


# ----------------------------------------------------------------------- checksums
def resolve(archive_url: str, sha_url: str) -> tuple:
    """(archive, checksum file) to use. A "latest" address that redirects is followed first, so that the
    file and its checksum are of the same build."""
    if sha_url != BESIDE:
        return archive_url, sha_url
    # GET (only its headers are read): that server answers HEAD of the file itself with 404
    with requests.get(archive_url, allow_redirects=True, headers=build_headers(), timeout=TIMEOUT,
                      proxies=get_proxies(), stream=True) as r:
        r.raise_for_status()
        return r.url, r.url + ".sha256"


def fetch_expected_sha256(archive_url: str, sha_url: str) -> str:
    """SHA-256 the mirror publishes for archive_url."""
    archive_url, sha_url = resolve(archive_url, sha_url)
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
    for archive, sha_url, *_more in FFMPEG_SOURCES:
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


def is_bundled(path) -> bool:
    """True if this ffmpeg came with DISO (inside the program or beside the installed DISO.exe)."""
    if not path:
        return False
    here = os.path.normcase(os.path.dirname(os.path.abspath(path)))
    return any(here == os.path.normcase(os.path.abspath(d)) for d in bundled_ffmpeg_dirs())


def bundled_build(version: str) -> str:
    """The mirror's build (its SHA-256) that the bundled FFmpeg of this version was first compared
    with; "" before the first check, or after DISO came with another version."""
    try:
        with open(os.path.join(user_tools_dir(), BUNDLED_FILE), encoding="utf-8") as f:
            data = json.load(f)
        return data.get("sha256", "") if data.get("version") == version else ""
    except Exception:
        return ""


def remember_bundled(version: str, sha256: str) -> None:
    """The bundled FFmpeg is as new as the mirror's build of the day it is first checked (it is put
    into DISO when DISO is built); a later build on the mirror is an update."""
    path = os.path.join(user_tools_dir(), BUNDLED_FILE)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"version": version, "sha256": sha256}, f)
    os.replace(path + ".tmp", path)


def ffmpeg_version(path) -> str:
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=10,
                             **subprocess_flags()).stdout
        m = re.search(r"ffmpeg version (\S+)", out)
        return m.group(1) if m else "?"
    except Exception:
        return ""


# ------------------------------------------------------------------------ install
def _wanted(member: str):
    """'ffmpeg' / 'ffprobe' (with .exe on Windows) when this archive member is one of them: in the
    archive's bin/ folder, or at its top (macOS builds are a bare program in a zip)."""
    member = member.replace("\\", "/")
    name = os.path.basename(member).lower()
    if name in TOOLS and ("/bin/" in "/" + member or "/" not in member):
        return name
    return None


def _unpack(archive_path: str, target_dir: str) -> dict:
    """Write ffmpeg / ffprobe out of a .zip or .tar.xz beside their targets: {name: staged file}."""
    staged = {}

    def stage(name, src):
        tmp = os.path.join(target_dir, name + ".new")
        with open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)
        if not WINDOWS:
            os.chmod(tmp, 0o755)
        staged[name] = tmp

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            for m in zf.infolist():
                name = _wanted(m.filename)
                if name and not m.is_dir():
                    with zf.open(m) as src:
                        stage(name, src)
    else:
        with tarfile.open(archive_path) as tf:
            for m in tf:
                name = _wanted(m.name)
                if name and m.isfile():
                    with tf.extractfile(m) as src:
                        stage(name, src)
    return staged


def _commit(staged: dict, target_dir: str) -> None:
    """Swap the new programs in at the end, so an interrupted install never leaves a half-written one."""
    if TOOLS[0] not in staged:
        for tmp in staged.values():
            _remove(tmp)
        raise RuntimeError(f"{TOOLS[0]} was not found inside the downloaded archive")
    for name, tmp in staged.items():
        os.replace(tmp, os.path.join(target_dir, name))


def _extract(zip_path: str, target_dir: str) -> None:
    """Unpack ffmpeg / ffprobe (see _unpack and _commit)."""
    _commit(_unpack(zip_path, target_dir), target_dir)


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
    with _lock:  # only one download even if several items need ffmpeg at once
        if not force and find_ffmpeg():
            return find_ffmpeg()
        tools = user_tools_dir()
        for archive, sha_url, *more in (sources or FFMPEG_SOURCES):
            downloads, staged, first = [], {}, None
            try:
                for i, (part, part_sha) in enumerate([(archive, sha_url)] + list(more[0] if more else [])):
                    part, part_sha = resolve(part, part_sha)
                    expected = fetch_expected_sha256(part, part_sha)
                    first = first or expected
                    path = os.path.join(tools, f"ffmpeg-download-{i}" + (".tar.xz" if part.endswith(".tar.xz") else ".zip"))
                    downloads.append(path)
                    _remove(path)
                    FastDownloader.cleanup(path)
                    cb = (lambda d, t, s, e, c: progress(d, t)) if progress else None
                    FastDownloader(part, path, 8, on_progress=cb, limited=False).run()
                    actual = sha256_file(path)
                    if actual != expected:
                        raise DownloadError(f"SHA-256 eşleşmedi (beklenen {expected[:12]}…, gelen {actual[:12]}…)")
                    staged.update(_unpack(path, tools))
                _commit(staged, tools)
                staged = {}
                _write_info({"sha256": first, "archive": archive,
                             "version": ffmpeg_version(os.path.join(tools, TOOLS[0]))})
                last_error = ""
                break
            except Exception as e:  # try the next mirror
                last_error = f"{archive}: {e}"
            finally:
                for path in downloads + list(staged.values()):
                    _remove(path)
        os.environ["PATH"] = tools + os.pathsep + os.environ.get("PATH", "")
        return find_ffmpeg()
