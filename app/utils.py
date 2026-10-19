"""Small helpers shared by the whole app: paths, formatting, file names, tool lookup."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul",
             *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


# ----------------------------------------------------------------------------- paths
def resource_path(relative: str) -> str:
    """Correct path both when running from source and from the PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
    return os.path.join(base, relative)


def local_appdata() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) if base else Path.home() / "AppData" / "Local"


def migrate_legacy_data(legacy: Path, new: Path) -> str:
    """Earlier versions kept their data in %LOCALAPPDATA%\\DISO. Bring it to the new place once.
    Returns the folder to use: the new one, or (if it could not be brought over) the old one,
    so that nothing the user had is ever lost or hidden."""
    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(new))                 # one rename on the same drive
        return str(new)
    except OSError:
        pass
    try:                                                   # a file is in use (the old program is still open): copy instead
        shutil.copytree(legacy, new, dirs_exist_ok=True)
        return str(new)
    except (OSError, shutil.Error):
        shutil.rmtree(new, ignore_errors=True)             # a half copy must not pass for the real thing
        return str(legacy)


def app_data_dir() -> str:
    """%LOCALAPPDATA%\\DISO (settings, playlists, the download list, downloaded tools)."""
    from . import brand
    new = local_appdata() / brand.DATA_DIR_NAME
    if not new.exists():
        for name in brand.LEGACY_DATA_DIR_NAMES:
            legacy = Path.home() / name
            if legacy.is_dir():
                return migrate_legacy_data(legacy, new)
    new.mkdir(parents=True, exist_ok=True)
    return str(new)


def user_tools_dir() -> str:
    """Folder where the app stores tools it downloads itself (ffmpeg)."""
    d = Path(app_data_dir()) / "tools"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def bundled_ffmpeg_dirs() -> list:
    """Where the FFmpeg that comes with DISO is: inside the program, or beside the installed DISO.exe."""
    dirs = [resource_path("ffmpeg")]
    if getattr(sys, "frozen", False):
        dirs.append(os.path.join(os.path.dirname(sys.executable), "ffmpeg"))
    return dirs


def tool_dirs() -> list:
    # the tools folder first: an FFmpeg that DISO updated there is newer than the one it came with
    dirs = [user_tools_dir()] + bundled_ffmpeg_dirs()
    if getattr(sys, "frozen", False):
        # put there by the installer: YouTube needs a JavaScript runtime
        dirs.append(os.path.join(os.path.dirname(sys.executable), "deno"))
    return dirs


def setup_environment() -> None:
    """Put every folder that may contain ffmpeg / deno on PATH (yt-dlp finds them there)."""
    extra = [d for d in tool_dirs() if os.path.isdir(d)]
    os.environ["PATH"] = os.pathsep.join(extra + [os.environ.get("PATH", "")])


def find_ffmpeg():
    return shutil.which("ffmpeg")


def subprocess_flags() -> dict:
    """Hide the black console window that would flash when running ffmpeg from a GUI .exe."""
    if sys.platform.startswith("win"):
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


def default_download_dir() -> str:
    d = Path.home() / "Downloads"
    return str(d if d.exists() else Path.home())


def open_in_file_manager(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            if os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(os.path.dirname(path) if not os.path.isdir(path) else path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path] if os.path.isfile(path) else ["open", path])
        else:
            subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])
    except Exception:
        pass


# ------------------------------------------------------------------------- formatting
def human_size(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def human_eta(seconds) -> str:
    if seconds is None or seconds <= 0 or seconds == float("inf"):
        return "--:--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def human_duration(seconds) -> str:
    """185 -> '3:05', 3725 -> '1:02:05', 0 / None -> ''."""
    seconds = int(seconds or 0)
    if seconds <= 0:
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------------------- file names
def sanitize_filename(name: str, maxlen: int = 150) -> str:
    name = _INVALID.sub("_", str(name or ""))
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > maxlen:
        stem, ext = os.path.splitext(name)
        if not ext or len(ext) > 10:
            stem, ext = name, ""
        name = (stem[: maxlen - len(ext)].rstrip(" .")) + ext
    if name.split(".")[0].lower() in _RESERVED:
        name = "_" + name
    return name or "download"


def unique_path(folder: str, filename: str) -> str:
    """folder/filename, or folder/filename (1) ... if it (or its .part) already exists."""
    def taken(p):
        return os.path.exists(p) or os.path.exists(p + ".part")

    path = os.path.join(folder, filename)
    if not taken(path):
        return path
    base, ext = os.path.splitext(filename)
    i = 1
    while taken(os.path.join(folder, f"{base} ({i}){ext}")):
        i += 1
    return os.path.join(folder, f"{base} ({i}){ext}")


# ------------------------------------------------------------------------ type folders
CATEGORIES = {
    "Video": (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".3gp"),
    "Müzik": (".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".mid"),
    "Arşiv": (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".img", ".cab"),
    "Belge": (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt",
              ".ods", ".csv", ".epub"),
    "Program": (".exe", ".msi", ".apk", ".dmg", ".deb", ".rpm", ".appx", ".msix", ".jar"),
    "Resim": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".tif", ".tiff", ".ico", ".heic"),
}
OTHER_CATEGORY = "Diğer"


def category_for(filename: str) -> str:
    """Sub-folder name for a file: Video, Müzik, Arşiv, Belge, Program, Resim or Diğer."""
    ext = os.path.splitext(filename or "")[1].lower()
    for name, exts in CATEGORIES.items():
        if ext in exts:
            return name
    return OTHER_CATEGORY


def category_folder(base: str, filename: str) -> str:
    return os.path.join(base, category_for(filename))


def media_folder(base: str, kind: str, sort: bool) -> str:
    """Where a finished video / MP3 goes: the chosen folder, or its Video / Müzik sub-folder."""
    if not sort:
        return base
    return os.path.join(base, "Müzik" if kind == "audio" else "Video")


# ------------------------------------------------------------------------------- URLs
_URL_RE = re.compile(r"^https?://\S+$", re.I)


def normalize_url(text: str) -> str:
    text = (text or "").strip()
    if text.lower().startswith("www."):
        text = "https://" + text
    return text


def is_url(text: str) -> bool:
    return bool(_URL_RE.match(normalize_url(text)))


_FIND_URLS = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.I)


def extract_urls(text: str) -> list:
    """Every link in a text (a pasted block, a .txt file ...), in order, without repeats."""
    out, seen = [], set()
    for raw in _FIND_URLS.findall(text or ""):
        raw = raw.rstrip(".,;")
        while raw[-1:] in (")", "]") and raw.count(")" if raw[-1] == ")" else "]") > \
                raw.count("(" if raw[-1] == ")" else "["):
            raw = raw[:-1].rstrip(".,;")  # "(see https://a.b/c)." : the bracket is not the link's
        url = normalize_url(raw)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def urls_from_file(path: str, limit: int = 2_000_000) -> list:
    """Links inside a text file (.txt, .csv, .url shortcut ...)."""
    try:
        with open(path, "rb") as f:
            raw = f.read(limit)
    except OSError:
        return []
    for enc in ("utf-8-sig", "cp1254"):
        try:
            return extract_urls(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    return extract_urls(raw.decode("utf-8", "replace"))


def open_file(path: str) -> bool:
    """Open a file with the program Windows (or the OS) associates with it."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False
