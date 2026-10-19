"""Builds the program with PyInstaller (build.bat calls this).

  python tools/build_exe.py              dist/DISO.exe: one file that runs anywhere (with ffmpeg/ inside it if
                                         that folder has ffmpeg.exe)
  python tools/build_exe.py --no-ffmpeg  smaller exe: ffmpeg is downloaded on first use instead
  python tools/build_exe.py --onedir     build/app/DISO/: DISO.exe with its files beside it (_internal). This is
                                         what the installer puts on the PC: it starts in a second or two, because
                                         nothing has to be unpacked into %TEMP% on every start (a one-file exe does
                                         that with ~115 MB each time, and deletes it again on exit)
"""
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

ONEDIR_DIST = os.path.join(ROOT, "build", "app")
ONEDIR_APP = os.path.join(ONEDIR_DIST, "DISO")


def _version_file() -> str:
    """The version tab of the exe's properties (also what Windows shows as the publisher)."""
    from app import __version__, __version_label__
    from version_info import write_version_file
    return write_version_file(os.path.join(ROOT, "build", "versions", "app.txt"), "DISO - indirme yöneticisi",
                              "DISO.exe", __version__, __version_label__)


def command(no_ffmpeg: bool = False, onedir: bool = False) -> list:
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconsole", "--onedir" if onedir else "--onefile", "--clean",
           "--noconfirm", "--name", "DISO", "--icon", os.path.join("assets", "icon.ico"),
           "--collect-all", "customtkinter", "--collect-all", "yt_dlp", "--collect-all", "certifi",
           "--hidden-import", "pystray._win32", "--version-file", _version_file(),
           "--exclude-module", "pygame",                 # the music player of macOS / Linux (sdl_player.py)
           "--add-data", f"assets{sep}assets", "--add-data", f"browser_extension{sep}browser_extension"]
    if onedir:
        cmd += ["--distpath", ONEDIR_DIST, "--workpath", os.path.join(ROOT, "build", "app-work"),
                "--contents-directory", "_internal"]
    if importlib.util.find_spec("yt_dlp_ejs"):          # YouTube's JavaScript challenge solver
        cmd += ["--collect-all", "yt_dlp_ejs"]
    if importlib.util.find_spec("winrt"):               # Windows' media panel (song, cover, buttons)
        cmd += ["--collect-all", "winrt"]
    if importlib.util.find_spec("ytmusicapi"):          # lyrics from YouTube Music (with its language files)
        cmd += ["--collect-all", "ytmusicapi"]
    if not no_ffmpeg and os.path.exists(os.path.join(ROOT, "ffmpeg", "ffmpeg.exe")):
        cmd += ["--add-data", f"ffmpeg{sep}ffmpeg"]
    return cmd + ["main.py"]


def main(argv) -> int:
    cmd = command("--no-ffmpeg" in argv, "--onedir" in argv)
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
