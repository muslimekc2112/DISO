"""
python main.py --selftest result.json

Checks the pieces the window needs, without opening it: which yt-dlp is really loaded (the
bundled one or a newer downloaded copy), whether the optional parts (drag & drop, tray, SOCKS
proxy) are there, whether ffmpeg is found. Used to verify a built .exe, where there is no
console to look at.
"""
import importlib
import json
import os
import sys

from . import __version__, updater
from .utils import find_ffmpeg


def collect() -> dict:
    info = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
            "python": sys.version.split()[0], "packages_dir": updater.packages_dir(),
            "overrides": dict(updater._active)}
    try:
        yt = updater.load_yt_dlp()
        info["yt_dlp_file"] = os.path.dirname(yt.__file__)
        info["yt_dlp_version"] = getattr(getattr(yt, "version", None), "__version__", "?")
        info["yt_dlp_mark"] = getattr(yt, "MARK", None)   # only a test copy has one
    except Exception as e:  # noqa: BLE001
        info["yt_dlp_error"] = f"{type(e).__name__}: {e}"
    for name in ("customtkinter", "tkinterdnd2", "pystray", "PIL", "socks", "requests"):
        try:
            importlib.import_module(name)
            info[name] = True
        except Exception as e:  # noqa: BLE001
            info[name] = f"{type(e).__name__}: {e}"
    info["ffmpeg"] = find_ffmpeg()
    return info


def run(path=None) -> int:
    text = json.dumps(collect(), indent=2, ensure_ascii=False)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    elif sys.stdout is not None:
        print(text)
    return 0
