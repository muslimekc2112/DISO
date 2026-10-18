"""Finding songs on the internet for the music player ("🔍 Şarkı bul").

The search itself is yt-dlp's YouTube search (no account, no key). A pasted link is not searched but
opened: one video or the songs of a playlist. `Searcher` runs one search at a time on another thread;
only the answer to the newest question is kept (an older, slower one is thrown away)."""
import os
import threading

from . import video_engine as ve
from .logs import log
from .utils import app_data_dir, is_url, normalize_url

LIMIT = 20
SEARCH_TIMEOUT = 10        # s without an answer before a request is tried again
MUSIC_DIR_NAME = "Müzik"


def music_dir() -> str:
    """Where songs downloaded from the music player are kept: %LOCALAPPDATA%\\DISO\\Müzik."""
    path = os.path.join(app_data_dir(), MUSIC_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _entry_url(e: dict) -> str:
    u = e.get("webpage_url") or e.get("url") or ""
    if u.startswith("http"):
        return u
    vid = e.get("id") or u
    return f"https://www.youtube.com/watch?v={vid}" if vid else ""


def result_from(e: dict):
    """One search answer as {url, title, channel, duration (s)}; None for what cannot be a song
    (a live stream, a channel, an entry without a link)."""
    if not isinstance(e, dict) or e.get("live_status") in ("is_live", "is_upcoming") or e.get("is_live"):
        return None
    if (e.get("ie_key") or "").lower() in ("youtubetab",) or e.get("_type") == "playlist":
        return None
    url = _entry_url(e)
    title = (e.get("title") or "").strip()
    if not url or not title:
        return None
    duration = e.get("duration")
    return {"url": url, "title": title,
            "channel": (e.get("channel") or e.get("uploader") or "").strip(),
            "duration": int(duration) if isinstance(duration, (int, float)) and duration > 0 else 0}


class Found(list):
    """Search answers; `title` is the playlist's / album's name when a list link was opened."""

    def __init__(self, items=(), title=""):
        super().__init__(items)
        self.title = title or ""


def search(query: str, limit=LIMIT) -> list:
    """The songs found for `query` (a few words or a link). Raises on network / yt-dlp errors.
    A playlist or album link (YouTube, YouTube Music) gives its songs, with its name as .title."""
    query = " ".join((query or "").split())
    if not query:
        return []
    if is_url(query):
        entries = ve.expand_playlist(normalize_url(query))
        return Found([{"url": u, "title": t or u, "channel": "", "duration": int(d or 0)} for u, t, d in entries],
                     getattr(entries, "title", "") if len(entries) > 1 else "")
    yt_dlp = ve._yt_dlp()
    opts = ve.base_opts()
    # a search is a few small requests: one that hangs is given up sooner and asked again
    opts.update({"extract_flat": True, "skip_download": True, "noplaylist": False,
                 "socket_timeout": SEARCH_TIMEOUT, "extractor_retries": 3})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{int(limit)}:{query}", download=False) or {}
    out, seen = [], set()
    for e in info.get("entries") or []:
        r = result_from(e)
        if r and r["url"] not in seen:
            seen.add(r["url"])
            out.append(r)
    return out


SUGGEST_URL = "https://suggestqueries.google.com/complete/search"


def suggest(query: str, get=None) -> list:
    """What YouTube would suggest for what is typed so far (up to 8). Raises on network errors."""
    query = " ".join((query or "").split())
    if len(query) < 2 or is_url(query):
        return []
    import requests

    from .segmented_downloader import get_proxies
    r = (get or requests.get)(SUGGEST_URL, params={"client": "firefox", "ds": "yt", "q": query},
                              timeout=6, proxies=get_proxies())
    r.raise_for_status()
    data = r.json()
    words = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
    return [w for w in words if isinstance(w, str) and w.strip()][:8]


# ------------------------------------------------------------------ 30 second preview
PREVIEW_SECONDS = 30


def preview_start(duration: float) -> int:
    """Where the preview starts: about a third in (often the chorus), never too close to the end."""
    if duration < 70:
        return 0
    return int(max(0, min(duration * 0.3, duration - PREVIEW_SECONDS - 5)))


def make_preview(url: str, out: str, duration=0, run=None) -> str:
    """Cut 30 seconds of the song's sound straight from YouTube into an MP3 (nothing else is downloaded)."""
    import subprocess

    from .utils import find_ffmpeg, subprocess_flags
    info = ve.resolve(url, "audio", "En iyi")
    fmt = (info.get("requested_formats") or [info])[0]
    source = fmt.get("url")
    ffmpeg = find_ffmpeg()
    if not source:
        raise RuntimeError("Bu şarkının sesine ulaşamadım")
    if not ffmpeg:
        raise ve.MissingFFmpeg("FFmpeg bulunamadı")
    headers = fmt.get("_fast_headers") or fmt.get("http_headers") or {}
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
           "-ss", str(preview_start(duration or info.get("duration") or 0)), "-t", str(PREVIEW_SECONDS)]
    if headers:
        cmd += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in headers.items())]
    cmd += ["-i", source, "-vn", "-c:a", "libmp3lame", "-b:a", "128k", out]
    (run or subprocess.run)(cmd, check=True, capture_output=True, timeout=120, **subprocess_flags())
    if not os.path.isfile(out) or os.path.getsize(out) < 1000:
        raise RuntimeError("Önizleme oluşmadı")
    return out


def preview_dir() -> str:
    path = os.path.join(app_data_dir(), "preview")
    os.makedirs(path, exist_ok=True)
    return path


class Searcher:
    """search(query) in the background; poll() returns (query, results, error) once, for the
    newest question only. `busy` is True while that question is still open."""

    def __init__(self, find=search):
        self._find = find
        self._lock = threading.Lock()
        self._generation = 0
        self._answer = None
        self.busy = False
        self.query = ""

    def search(self, query: str):
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._answer = None
            self.busy = True
            self.query = query
        threading.Thread(target=self._run, args=(generation, query), daemon=True).start()

    def _run(self, generation, query):
        try:
            results, error = self._find(query), ""
        except Exception as e:  # noqa: BLE001 - shown to the user, the window goes on
            log.info("music search failed: %s", e)
            results, error = [], ve.pretty_error(e)
        with self._lock:
            if generation == self._generation:            # a newer question replaced this one
                self._answer = (query, results, error)
                self.busy = False

    def poll(self):
        with self._lock:
            answer, self._answer = self._answer, None
            return answer
