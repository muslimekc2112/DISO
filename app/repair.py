"""🔧 Is a downloaded file whole? And when only its end is missing, the missing part is downloaded and put
after it (the part that is there is kept).

check() looks at a finished download: is it still there, is it as big as the server says, and can its
contents be read through (archives with Python, videos and songs with FFmpeg, pictures with Pillow, a
PDF's end mark). complete_tail() downloads the missing end of a file. Nothing here touches the window."""
import gzip
import os
import subprocess
import tarfile
import zipfile
from dataclasses import dataclass

import requests

from .logs import log
from .segmented_downloader import build_headers, get_proxies, probe
from .utils import subprocess_flags

OK, MISSING, EMPTY, SHORT, BROKEN, UNKNOWN = "ok", "missing", "empty", "short", "broken", "unknown"
MEDIA = (".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".ts", ".3gp", ".mpg", ".mpeg",
         ".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".oga", ".opus", ".wma")
PICTURES = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff")
TIMEOUT = 900                  # a long film read through on a slow disk
CHUNK = 1 << 16


@dataclass
class Verdict:
    status: str                # OK / MISSING / EMPTY / SHORT / BROKEN / UNKNOWN
    detail: str = ""           # why, in words for the user
    missing: int = 0           # SHORT: bytes missing at the end
    resumable: bool = False    # SHORT: the server can send just the missing end


def _tool(name):
    from .tags import _tool as find
    return find(name)


def read_through(path: str) -> str:
    """"" when the contents of the file can be read to the end, else what is wrong with them. Files whose
    insides cannot be checked here (an exe, a rar ...) give ""."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".zip", ".jar", ".apk", ".docx", ".xlsx", ".pptx", ".epub"):
            with zipfile.ZipFile(path) as z:
                bad = z.testzip()
            return f"bozuk parça: {bad}" if bad else ""
        if ext in (".gz", ".tgz") or path.lower().endswith(".tar.gz"):
            with gzip.open(path, "rb") as f:
                while f.read(1 << 20):
                    pass
            return ""
        if ext == ".tar":
            with tarfile.open(path) as t:
                for member in t:
                    if member.isfile():
                        f = t.extractfile(member)
                        while f is not None and f.read(1 << 20):
                            pass
            return ""
        if ext == ".pdf":
            with open(path, "rb") as f:
                head = f.read(5)
                f.seek(max(0, os.path.getsize(path) - 2048))
                tail = f.read()
            if head != b"%PDF-":
                return "PDF değil"
            return "" if b"%%EOF" in tail else "sonu eksik"
        if ext in PICTURES:
            from PIL import Image
            with Image.open(path) as im:
                im.load()
            return ""
        if ext in MEDIA:
            return _media_errors(path)
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError, ValueError) as e:
        return str(e) or type(e).__name__
    except Exception as e:  # noqa: BLE001 - Pillow's own errors: the picture is broken
        return str(e) or type(e).__name__
    return ""


def _media_errors(path: str) -> str:
    """FFmpeg reads every packet of the file (nothing is decoded: quick even for a film)."""
    ffmpeg = _tool("ffmpeg")
    if not ffmpeg:
        return ""
    try:
        proc = subprocess.run([ffmpeg, "-v", "error", "-hide_banner", "-nostats", "-i", path, "-map", "0",
                               "-c", "copy", "-f", "null", "-"], capture_output=True, timeout=TIMEOUT,
                              stdin=subprocess.DEVNULL, **subprocess_flags())
    except (OSError, subprocess.SubprocessError) as e:
        log.info("cannot read %s through: %s", path, e)
        return ""
    lines = [ln.strip() for ln in proc.stderr.decode("utf-8", "replace").splitlines() if ln.strip()]
    if proc.returncode != 0:
        return lines[-1] if lines else "FFmpeg açamadı"
    serious = [ln for ln in lines if any(w in ln.lower() for w in ("invalid", "truncat", "corrupt", "error",
                                                                    "moov atom", "partial file"))]
    return serious[0] if serious else ""


def check(path: str, url: str = "", headers=None, ask_server=True) -> Verdict:
    """How a finished download is. With a link (and ask_server) the server is asked how big it should be."""
    if not path or not os.path.isfile(path):
        return Verdict(MISSING, "dosya yerinde yok")
    size = os.path.getsize(path)
    if size == 0:
        return Verdict(EMPTY, "dosya boş")
    if url and ask_server:
        try:
            pr = probe(url, headers)
        except Exception as e:  # noqa: BLE001 - offline: the contents can still be checked
            log.info("repair: cannot ask %s: %s", url, e)
            pr = None
        ctype = (pr.content_type or "").lower() if pr else ""
        if pr and pr.total > 0 and not ctype.startswith(("text/html", "application/json")):
            if size < pr.total:
                return Verdict(SHORT, f"{pr.total - size:,} bayt eksik".replace(",", "."), pr.total - size,
                               pr.resumable)
    problem = read_through(path)
    if problem:
        return Verdict(BROKEN, problem)
    return Verdict(OK)


def complete_tail(path: str, url: str, headers=None, progress=None, stop=None) -> int:
    """Download what is missing at the end of `path` and add it. Returns the bytes added. Raises
    OSError when the server does not send just the missing part (then it must be downloaded again)."""
    have = os.path.getsize(path)
    h = build_headers(headers)
    h["Range"] = f"bytes={have}-"
    added = 0
    with requests.get(url, headers=h, stream=True, timeout=30, allow_redirects=True, proxies=get_proxies()) as r:
        if r.status_code != 206 or not (r.headers.get("Content-Range") or "").startswith(f"bytes {have}-"):
            raise OSError("sunucu yalnız eksik kısmı göndermedi")
        with open(path, "ab") as f:
            for chunk in r.iter_content(CHUNK):
                if stop is not None and stop():
                    raise OSError("durduruldu")
                f.write(chunk)
                added += len(chunk)
                if progress:
                    progress(added)
    return added
