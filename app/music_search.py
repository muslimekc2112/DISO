"""Finding songs on the internet for the music player ("🔍 Şarkı bul").

The search is YouTube Music's song search (ytmusicapi; no account, no key), so shorts and ordinary
videos do not crowd the songs out; the ones that match what was typed come first, most listened to
first. An artist / channel name narrows the answers to that artist (empty: no narrowing). When
YouTube Music cannot be reached, yt-dlp's YouTube search is the fallback (without shorts). A pasted
link is not searched but opened: one video or the songs of a playlist. `Searcher` runs one search at
a time on another thread; only the answer to the newest question is kept (an older, slower one is
thrown away)."""
import os
import re
import threading
import unicodedata

from . import video_engine as ve
from .logs import log
from .utils import app_data_dir, is_url, normalize_url

LIMIT = 50                 # songs asked from YouTube Music
FALLBACK_LIMIT = 30        # videos asked from YouTube when YouTube Music cannot be reached
FEW = 5                    # fewer matching songs than this: YouTube Music's music videos are added
SHORT_ANSWER = 20         # fewer songs than this from YouTube Music: it is asked once more
SHORT_SECONDS = 60         # a video this short is a short, not a song
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


def fold(text) -> str:
    """Text for comparing names: no case, no accents, Turkish ı/İ as i ("Şımarık" == "simarik")."""
    text = str(text or "").replace("ı", "i").replace("İ", "i").casefold()
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def has_words(words: str, text: str) -> bool:
    """Every word of `words` is in `text` (both folded)."""
    words, text = fold(words), fold(text)
    have = set(text.split())
    # "gülpembe" also finds "Gül Pembe"
    return all(w in have for w in words.split()) or words.replace(" ", "") in text.replace(" ", "")


_VIEWS = re.compile(r"([\d.,]+)\s*([KMB])?", re.I)


def views_count(text) -> int:
    """'238M' / '1.1M' / '447K' / '12,345' (YouTube Music's listen counts) as a number; 0 if unknown."""
    m = _VIEWS.search(str(text or ""))
    if not m:
        return 0
    number, unit = m.group(1), (m.group(2) or "").upper()
    if unit:
        number = number.replace(",", ".")
        if number.count(".") > 1:
            number = number.replace(".", "")
    else:
        number = number.replace(",", "").replace(".", "")
    try:
        value = float(number)
    except ValueError:
        return 0
    return int(value * {"K": 10 ** 3, "M": 10 ** 6, "B": 10 ** 9}.get(unit, 1))


def short_views(n) -> str:
    """A listen count for the table: '238 Mn', '1,1 Mn', '447 B' (English: '238M', '1.1M', '447K')."""
    from . import i18n
    n = int(n or 0)
    if n <= 0:
        return ""
    for power, tr_unit, en_unit in ((10 ** 9, "Mr", "B"), (10 ** 6, "Mn", "M"), (10 ** 3, "B", "K")):
        if n >= power:
            value = n / power
            one = round(value, 1)
            text = f"{one:.1f}" if one < 10 and one != int(one) else f"{int(round(value))}"
            if i18n.current == "en":
                return text + en_unit
            return text.replace(".", ",") + " " + tr_unit
    return str(n)


def ytmusic_result(r: dict):
    """One YouTube Music answer as {url, title, channel, duration, views, album}; None for what has no video."""
    if not isinstance(r, dict) or not r.get("videoId") or r.get("isAvailable") is False:
        return None
    title = (r.get("title") or "").strip()
    if not title:
        return None
    artists = ", ".join(a.get("name", "").strip() for a in r.get("artists") or []
                        if isinstance(a, dict) and (a.get("name") or "").strip())
    album = r.get("album")
    duration = r.get("duration_seconds")
    return {"url": f"https://www.youtube.com/watch?v={r['videoId']}", "title": title, "channel": artists,
            "duration": int(duration) if isinstance(duration, (int, float)) and duration > 0 else 0,
            "views": views_count(r.get("views")),
            "album": (album.get("name") or "").strip() if isinstance(album, dict) else ""}


def _same_song(r: dict) -> tuple:
    return fold(r["title"]), fold(r.get("channel", ""))


def _text(r: dict) -> str:
    return " ".join((r["title"], r.get("channel", ""), r.get("album", "")))


def arrange(results, words="", artist=""):
    """The answers in the order they are shown, without repeats: when an artist is given, only that
    artist's songs (all of them if there are none); the songs whose name / artist / album hold every
    typed word first, then the rest; most listened to first in each part."""
    out, seen = [], set()
    for r in results:
        if r and r["url"] not in seen and _same_song(r) not in seen:
            seen.update((r["url"], _same_song(r)))
            out.append(r)
    if artist.strip():
        own = [r for r in out if has_words(artist, r.get("channel", ""))]
        if own:
            out = own
    order = {id(r): i for i, r in enumerate(out)}
    return sorted(out, key=lambda r: (0 if has_words(words, _text(r)) else 1, -int(r.get("views") or 0),
                                      order[id(r)]))


def matching(results, words="", artist="") -> int:
    """How many answers really are what was asked (every word, and the artist when given)."""
    return sum(1 for r in results if has_words(words, _text(r))
               and (not artist.strip() or has_words(artist, r.get("channel", ""))))


def _ytmusic():
    """A YouTube Music client whose requests give up after SEARCH_TIMEOUT (and use DISO's proxy)."""
    import requests
    from ytmusicapi import YTMusic

    from .segmented_downloader import get_proxies

    class Session(requests.Session):
        def request(self, *a, **k):
            k.setdefault("timeout", SEARCH_TIMEOUT)
            return super().request(*a, **k)
    return YTMusic(requests_session=Session(), proxies=get_proxies())


def ytmusic_search(words: str, artist="", api=None, limit=LIMIT) -> list:
    """YouTube Music's songs for `words` (+ artist); its music videos too when few songs match."""
    from concurrent.futures import ThreadPoolExecutor
    api = api if api is not None else _ytmusic()
    query = " ".join(f"{words} {artist}".split())
    # both questions at once: the videos are only looked at when few songs match, but waiting for
    # the songs first would make every such search twice as slow
    with ThreadPoolExecutor(2) as pool:
        songs = pool.submit(api.search, query, filter="songs", limit=limit)
        videos = pool.submit(api.search, query, filter="videos", limit=20)
        raw = list(songs.result() or [])
        if len(raw) < SHORT_ANSWER:
            # YouTube Music now and then answers with only its first page: once more, both together
            try:
                raw += list(api.search(query, filter="songs", limit=limit) or [])
            except Exception as e:  # noqa: BLE001 - the first answer is still something
                log.info("YouTube Music asked again, failed: %s", e)
        found = arrange([ytmusic_result(r) for r in raw], words, artist)
        if matching(found, words, artist) < FEW:
            try:
                more = [v for v in (ytmusic_result(r) for r in videos.result() or [])
                        if v and v["duration"] > SHORT_SECONDS]
            except Exception as e:  # noqa: BLE001 - the songs are enough
                log.info("YouTube Music video search failed: %s", e)
                more = []
            found = arrange(found + more, words, artist)
    return found


def youtube_search(words: str, artist="", limit=FALLBACK_LIMIT) -> list:
    """yt-dlp's YouTube search, without shorts and live streams (when YouTube Music cannot be reached)."""
    yt_dlp = ve._yt_dlp()
    opts = ve.base_opts()
    # a search is a few small requests: one that hangs is given up sooner and asked again
    opts.update({"extract_flat": True, "skip_download": True, "noplaylist": False,
                 "socket_timeout": SEARCH_TIMEOUT, "extractor_retries": 3})
    query = " ".join(f"{words} {artist}".split())
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{int(limit)}:{query}", download=False) or {}
    out = []
    for e in info.get("entries") or []:
        r = result_from(e)
        if r and "/shorts/" not in r["url"] and not 0 < r["duration"] <= SHORT_SECONDS:
            r["views"] = int(e.get("view_count") or 0)
            out.append(r)
    return arrange(out, words, artist)


def search(query: str, artist="", limit=LIMIT) -> list:
    """The songs found for `query` (a few words or a link) and, if given, by `artist` (a singer or
    channel name; empty: anyone). Raises on network errors. A playlist or album link (YouTube,
    YouTube Music) gives its songs, with its name as .title."""
    query = " ".join((query or "").split())
    artist = " ".join((artist or "").split())
    if is_url(query):
        entries = ve.expand_playlist(normalize_url(query))
        return Found([{"url": u, "title": t or u, "channel": "", "duration": int(d or 0)} for u, t, d in entries],
                     getattr(entries, "title", "") if len(entries) > 1 else "")
    if not query and not artist:
        return []
    try:
        return ytmusic_search(query, artist, limit=limit)
    except Exception as e:  # noqa: BLE001 - YouTube Music unreachable / changed: plain YouTube instead
        log.info("YouTube Music search failed, searching YouTube: %s", e)
        return youtube_search(query, artist)


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

    def search(self, query: str, *more):
        """`more` goes to the search after the query (the music search's artist)."""
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._answer = None
            self.busy = True
            self.query = query
        threading.Thread(target=self._run, args=(generation, query, more), daemon=True).start()

    def _run(self, generation, query, more=()):
        try:
            results, error = self._find(query, *more), ""
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
