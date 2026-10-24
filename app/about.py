"""Facts about this copy of the program: for the about window, and for the 'copy the details' button that
is what to send when something does not work (so nobody has to be asked "which version? where? what Windows?")."""
import importlib
import os
import platform
import shutil
import subprocess
import sys

from . import brand
from .logs import log_path
from .utils import app_data_dir, find_ffmpeg, subprocess_flags


def _first_line(cmd, timeout=6):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **subprocess_flags())
        text = (out.stdout or out.stderr or "").strip()
        return text.splitlines()[0].strip() if text else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def install_folder() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ytdlp_version() -> str:
    try:
        return importlib.import_module("yt_dlp.version").__version__
    except Exception:  # noqa: BLE001 - not installed / broken: say so, never fail
        return ""


def facts():
    """[(label, value), ...] in the order they are shown. Slow lookups (starting deno) are in here, so call it
    from a worker thread when a window is waiting for it."""
    ffmpeg = find_ffmpeg()
    deno = shutil.which("deno")
    deno_version = _first_line([deno, "--version"]) if deno else ""
    ytdlp = ytdlp_version()
    return [
        ("Sürüm", brand.VERSION_LABEL),
        ("Çalışma şekli", "Kurulu uygulama" if getattr(sys, "frozen", False) else "Kaynak koddan"),
        ("Kurulum klasörü", install_folder()),
        ("Veri klasörü", app_data_dir()),
        ("Günlük dosyası", log_path()),
        ("Windows", platform.platform()),
        ("Python", platform.python_version()),
        ("yt-dlp", ytdlp or "yüklü değil"),
        ("FFmpeg", ffmpeg or "yok (lazım olunca kendim indiririm)"),
        ("Deno", f"{deno_version or 'sürüm okunamadı'} ({deno})" if deno
         else "yok (YouTube'un bazı biçimleri eksik gelebilir)"),
    ]


def as_text(rows=None) -> str:
    """The same facts as plain text, to paste into a message."""
    rows = facts() if rows is None else rows
    width = max(len(k) for k, _ in rows) + 1
    return f"{brand.NAME} {brand.VERSION_LABEL}\n" + "\n".join(f"{k + ':':<{width + 1}} {v}" for k, v in rows)
