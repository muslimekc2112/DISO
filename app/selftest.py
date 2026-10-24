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
    try:   # the music player talks to Windows' own MCI (macOS / Linux: SDL, through pygame)
        from . import player
        player.new_backend(alias="diso_selftest_probe")
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
    if not sys.platform.startswith("win"):
        info["playable"] = _plays_anything()
    else:
        info["playable"] = _playable_copy()
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
    try:   # the tray icon (Windows: pystray's Windows backend; Linux: its X11 one; macOS has none, see tray.py)
        from . import tray
        if tray.AVAILABLE or sys.platform.startswith("win"):
            tray.TrayIcon("selftest", lambda name: None)
            info["tray_icon"] = True
        else:
            info["tray_icon"] = "none on this system"
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
    try:   # 🎛 the equalizer plays with ffmpeg + SDL: pygame (and SDL's DLLs) must be inside the exe
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame
        from . import equalizer
        info["equalizer"] = bool(pygame.mixer) and bool(equalizer.ffmpeg_filter(equalizer.PRESETS["Rock"]))
    except Exception as e:  # noqa: BLE001
        info["equalizer"] = f"error: {type(e).__name__}: {e}"
    try:   # 🌈 the visualizer needs numpy (its compiled parts) inside the exe
        from . import visualizer
        frames, _level = visualizer.analyse_samples([0.0] * visualizer.WINDOW * 2)
        info["visualizer"] = frames.shape[1] == visualizer.BANDS
    except Exception as e:  # noqa: BLE001
        info["visualizer"] = f"error: {type(e).__name__}: {e}"
    try:   # 📱 the phone's QR code (segno) and 👤 the Google window's connection (websockets)
        from . import phone_link
        import websockets.sync.client  # noqa: F401
        info["phone_qr"] = phone_link.qr_image("http://192.168.1.2:1/?k=x").size[0] > 50
    except Exception as e:  # noqa: BLE001
        info["phone_qr"] = f"error: {type(e).__name__}: {e}"
    return info


def _song(d, cover_too=True):
    """A 3 s MP3 made with ffmpeg (with a 1000 px cover: the kind MCI refuses)."""
    import subprocess

    from .utils import subprocess_flags
    song, cover = os.path.join(d, "s.mp3"), os.path.join(d, "c.jpg")
    steps = [["-f", "lavfi", "-i", "sine=duration=3", "-c:a", "libmp3lame", song]]
    if cover_too:
        steps = [["-f", "lavfi", "-i", "color=c=gray:s=1000x1000", "-vf", "noise=alls=100:allf=t",
                  "-frames:v", "1", "-q:v", "2", cover],
                 ["-f", "lavfi", "-i", "sine=duration=3", "-i", cover, "-map", "0:a", "-map", "1:v",
                  "-c:a", "libmp3lame", "-c:v", "copy", "-disposition:v", "attached_pic",
                  "-id3v2_version", "3", song]]
    for args in steps:
        subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", *args],
                       check=True, capture_output=True, timeout=60, **subprocess_flags())
    return song


def _plays_anything():
    """macOS / Linux: ffmpeg decodes a song and SDL takes the sound (a second of it)."""
    import shutil
    import tempfile
    import time
    d = tempfile.mkdtemp(prefix="diso-selftest-")
    try:
        from . import player
        backend = player.new_backend(alias="diso_selftest")
        if not backend.load(_song(d)):
            return f"error: {backend.last_error}"
        backend.play()
        end = time.monotonic() + 5
        while backend.position_ms() < 500 and time.monotonic() < end:
            time.sleep(0.05)
        ok = backend.position_ms() >= 500
        backend.close()
        return ok
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _playable_copy():
    """Windows: an MP3 with a big cover (MCI refuses it) gets a playable copy, and MCI opens that."""
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix="diso-selftest-")
    try:
        from . import playable, player
        song = _song(d)
        made = playable.Preparer()._make(song)
        mci = player.MciBackend(alias="diso_selftest")
        result = bool(made and mci.load(playable.copy_path(song)))
        mci.close()
        os.remove(playable.copy_path(song))
        return result
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run(path=None) -> int:
    text = json.dumps(collect(), indent=2, ensure_ascii=False)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    elif sys.stdout is not None:
        print(text)
    return 0
