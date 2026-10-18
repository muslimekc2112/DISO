"""
python main.py --selftest result.json

Checks the pieces the window needs, without opening it: which yt-dlp is really loaded (the
bundled one or a newer downloaded copy), whether the optional parts (tray, SOCKS
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
            "python": sys.version.split()[0], "packages_dir": updater.packages_dir()}
    try:
        yt = updater.load_yt_dlp()
        info["yt_dlp_file"] = os.path.dirname(yt.__file__)
        info["yt_dlp_version"] = getattr(getattr(yt, "version", None), "__version__", "?")
        info["yt_dlp_mark"] = getattr(yt, "MARK", None)   # only a test copy has one
    except Exception as e:  # noqa: BLE001
        info["yt_dlp_error"] = f"{type(e).__name__}: {e}"
    info["overrides"] = dict(updater._active)   # after loading: a broken update has been rolled back
    for name in ("customtkinter", "pystray", "PIL", "socks", "requests"):
        try:
            importlib.import_module(name)
            info[name] = True
        except Exception as e:  # noqa: BLE001
            info[name] = f"{type(e).__name__}: {e}"
    info["ffmpeg"] = find_ffmpeg()
    try:   # the music player talks to Windows' own MCI
        from . import player
        player.MciBackend()
        info["music_player"] = True
    except Exception as e:  # noqa: BLE001
        info["music_player"] = f"error: {type(e).__name__}: {e}"
    try:   # the player window needs the table widget, picture tools and the tag reader inside the exe
        import tkinter.font  # noqa: F401
        from tkinter import ttk  # noqa: F401

        from PIL import Image, ImageDraw  # noqa: F401

        from . import music_ui, tags
        music_ui.rounded(Image.new("RGB", (16, 16), "#888888"), 4)
        info["music_ui"] = True
        info["tag_tools"] = bool(tags._tool("ffprobe")) and bool(tags._tool("ffmpeg"))
    except Exception as e:  # noqa: BLE001
        info["music_ui"] = f"error: {type(e).__name__}: {e}"
        info["tag_tools"] = False
    try:   # an MP3 with a big cover (MCI refuses it) gets a playable copy, and MCI opens that
        import shutil
        import subprocess
        import tempfile

        from . import playable, player as _player
        from .utils import subprocess_flags
        d = tempfile.mkdtemp(prefix="diso-selftest-")
        song, cover = os.path.join(d, "s.mp3"), os.path.join(d, "c.jpg")
        for args in (["-f", "lavfi", "-i", "color=c=gray:s=1000x1000", "-vf", "noise=alls=100:allf=t",
                      "-frames:v", "1", "-q:v", "2", cover],
                     ["-f", "lavfi", "-i", "sine=duration=3", "-i", cover, "-map", "0:a", "-map", "1:v",
                      "-c:a", "libmp3lame", "-c:v", "copy", "-disposition:v", "attached_pic",
                      "-id3v2_version", "3", song]):
            subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", *args],
                           check=True, capture_output=True, timeout=60, **subprocess_flags())
        made = playable.Preparer()._make(song)
        mci = _player.MciBackend(alias="diso_selftest")
        info["playable"] = bool(made and mci.load(playable.copy_path(song)))
        mci.close()
        os.remove(playable.copy_path(song))
        shutil.rmtree(d, ignore_errors=True)
    except Exception as e:  # noqa: BLE001
        info["playable"] = f"error: {type(e).__name__}: {e}"
    try:   # YouTube needs a JavaScript runtime: Deno, which the installer puts beside the program
        import shutil as _shutil
        deno = _shutil.which("deno")
        info["deno"] = deno or ""
        if deno:
            from .utils import subprocess_flags
            import subprocess as _subprocess
            out = _subprocess.run([deno, "--version"], capture_output=True, text=True, timeout=30, **subprocess_flags())
            info["deno_version"] = (out.stdout.splitlines() or [""])[0]
    except Exception as e:  # noqa: BLE001
        info["deno"] = f"error: {type(e).__name__}: {e}"
    try:   # the tray icon needs the Windows backend of pystray
        from . import tray
        tray.TrayIcon("selftest", lambda name: None)
        info["tray_icon"] = True
    except Exception as e:  # noqa: BLE001
        info["tray_icon"] = f"error: {type(e).__name__}: {e}"
    try:   # Windows' media panel needs the winrt packages inside the exe
        from . import smtc
        info["media_panel"] = smtc.AVAILABLE
        if smtc.AVAILABLE:
            import winrt.windows.storage  # noqa: F401
            import winrt.windows.storage.streams  # noqa: F401
    except Exception as e:  # noqa: BLE001
        info["media_panel"] = f"error: {type(e).__name__}: {e}"
    try:   # the taskbar preview buttons, the English texts, the lyrics, the history and backups
        from . import backup, history, i18n, lang_en, lyrics, taskbar  # noqa: F401
        info["extras"] = bool(lang_en.PLAIN) and callable(taskbar.draw_icons)
    except Exception as e:  # noqa: BLE001
        info["extras"] = f"error: {type(e).__name__}: {e}"
    try:   # lyrics from YouTube Music: the package and its language files must be inside the exe
        from ytmusicapi import YTMusic
        YTMusic()
        info["ytmusic"] = True
    except Exception as e:  # noqa: BLE001
        info["ytmusic"] = f"error: {type(e).__name__}: {e}"
    return info


def run(path=None) -> int:
    text = json.dumps(collect(), indent=2, ensure_ascii=False)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    elif sys.stdout is not None:
        print(text)
    return 0
