"""Song lyrics for the music player.

Lyrics come first from YouTube Music (the lyrics of the very video a found song was downloaded from, so
they belong to that song; for other songs YouTube Music is searched). LRCLIB (lrclib.net) adds the time
of every line ("synced": the player can follow the song), but only when its text is the same song's text:
LRCLIB alone sometimes has another song of the same name. They are kept next to the song as '<song>.lrc', the usual
place music players look, so a song carries its lyrics with it. A file without time marks is plain
lyrics. Nothing here touches the window: `Fetcher` works on another thread and the window polls it."""
import os
import queue
import re
import threading

import requests

from . import brand
from .logs import log
from .segmented_downloader import get_proxies

API = "https://lrclib.net/api/search"
TIMEOUT = 15
SYNC_TOLERANCE = 4          # s: synced lyrics only from a recording this close in length
_STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_META = re.compile(r"^\[(ar|ti|al|by|offset|length|re|ve|au|la|#):.*\]$", re.I)
_NOISE = re.compile(r"\s*[\(\[](?:official|resmi|lyrics?|sözleri|audio|video|hd|4k|klip|music video|"
                    r"official video|official audio|lyric video|remaster(?:ed)?)[^\)\]]*[\)\]]", re.I)


def lyrics_path(audio_path: str) -> str:
    return os.path.splitext(audio_path)[0] + ".lrc"


def has_lyrics(audio_path: str) -> bool:
    try:
        return os.path.getsize(lyrics_path(audio_path)) > 0
    except OSError:
        return False


def parse(text: str) -> dict:
    """{"synced": [(ms, line), ...] (empty when there are no time marks), "plain": [line, ...]}."""
    synced, plain = [], []
    for raw in (text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if _META.match(line):
            continue
        stamps = list(_STAMP.finditer(line))
        words = _STAMP.sub("", line).strip()
        if stamps and stamps[0].start() == 0:
            for m in stamps:
                frac = (m.group(3) or "0").ljust(3, "0")[:3]
                synced.append(((int(m.group(1)) * 60 + int(m.group(2))) * 1000 + int(frac), words))
        plain.append(words)
    while plain and not plain[0]:
        plain.pop(0)
    while plain and not plain[-1]:
        plain.pop()
    synced.sort(key=lambda x: x[0])
    return {"synced": synced, "plain": plain}


def load(audio_path: str):
    """The lyrics kept next to this song, or None."""
    try:
        with open(lyrics_path(audio_path), encoding="utf-8-sig") as f:
            data = parse(f.read())
    except (OSError, UnicodeDecodeError):
        return None
    return data if any(data["plain"]) else None


def line_at(synced, ms) -> int:
    """Index of the line being sung at `ms` (-1 before the first one)."""
    index = -1
    for i, (t, _) in enumerate(synced):
        if t > ms:
            break
        index = i
    return index


def clean_title(title: str) -> str:
    """'Gülpembe (Official Video) [4K]' -> 'Gülpembe' for the search."""
    out = _NOISE.sub("", title or "")
    out = re.sub(r"\s*\|.*$", "", out)
    return " ".join(out.split()).strip(" -–—") or (title or "").strip()


def _norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", (text or "").casefold()).strip()


def _same_name(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a in b or b in a)


def choose(found: list, title: str, seconds: float, artist: str = ""):
    """The best answer of a search: the name must match (and the artist, when it is known); synced
    lyrics only from a recording about as long as ours (else the lines would come at the wrong time),
    otherwise plain lyrics."""
    good = [f for f in found if isinstance(f, dict) and not f.get("instrumental")
            and (f.get("plainLyrics") or f.get("syncedLyrics"))
            and _same_name(title, f.get("trackName"))
            and (not artist or _same_name(artist, f.get("artistName")))]
    if not good:
        return None

    def gap(f):
        try:
            return abs(float(f.get("duration") or 0) - seconds) if seconds else 0.0
        except (TypeError, ValueError):
            return 1e9

    timed = [f for f in good if f.get("syncedLyrics") and (not seconds or gap(f) <= SYNC_TOLERANCE)]
    if timed:
        return min(timed, key=gap)["syncedLyrics"]
    best = min(good, key=gap)
    return best.get("plainLyrics") or _STAMP.sub("", best.get("syncedLyrics") or "")


def video_id_of(url: str) -> str:
    """The YouTube video id in a youtube.com / youtu.be / music.youtube.com link ("" if none)."""
    m = re.search(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


def _lrc_from_lines(lines) -> str:
    out = []
    for line in lines:
        ms = int(getattr(line, "start_time", 0) or 0)
        out.append(f"[{ms // 60000:02d}:{ms // 1000 % 60:02d}.{ms % 1000 // 10:02d}]{getattr(line, 'text', '') or ''}")
    return "\n".join(out)


def _ytmusic(api=None):
    if api is not None:
        return api
    from ytmusicapi import YTMusic
    return YTMusic()


def ytmusic_lyrics(video_id="", artist="", title="", api=None):
    """(text, timed) from YouTube Music, or None. With a video id: that video's own lyrics. Without
    one: the first song YouTube Music finds whose name (and artist) match."""
    api = _ytmusic(api)
    if not video_id:
        query = f"{artist} {clean_title(title)}".strip()
        for r in (api.search(query, filter="songs", limit=5) or [])[:5]:
            names = " ".join(a.get("name", "") for a in r.get("artists") or [] if isinstance(a, dict))
            if r.get("videoId") and _same_name(clean_title(title), r.get("title")) and \
                    (not artist or _same_name(artist, names)):
                video_id = r["videoId"]
                break
        if not video_id:
            return None
    browse = (api.get_watch_playlist(videoId=video_id) or {}).get("lyrics")
    if not browse:
        return None
    try:
        got = api.get_lyrics(browse, timestamps=True) or {}
    except Exception:  # noqa: BLE001 - an older answer without times
        got = api.get_lyrics(browse) or {}
    lines = got.get("lyrics")
    if got.get("hasTimestamps") and isinstance(lines, list) and lines:
        return _lrc_from_lines(lines), True
    if isinstance(lines, str) and lines.strip():
        return lines.strip(), False
    return None


def similar(a: str, b: str) -> bool:
    """Two lyrics are the same song's: most words of their first lines are the same."""
    def words(text):
        lines = [ln for ln in parse(text)["plain"] if ln.strip()][:6]
        return set(_norm(" ".join(lines)).split())
    wa, wb = words(a), words(b)
    return bool(wa and wb) and len(wa & wb) / max(1, min(len(wa), len(wb))) >= 0.6


def fetch(artist: str, title: str, seconds: float = 0, get=None, video_id="", ytm=None):
    """The lyrics of a song as LRC / plain text, or None. YouTube Music first (it knows the video);
    LRCLIB's synced lyrics are used when they are the same text (then the lines follow the song).
    Raises only when no source could be asked at all."""
    errors = []
    yt = None
    try:
        yt = ytmusic_lyrics(video_id, artist, title, api=ytm)
    except Exception as e:  # noqa: BLE001 - LRCLIB may still answer
        errors.append(e)
        log.info("YouTube Music lyrics failed: %s", e)
    if yt and yt[1]:
        return "[re:YouTube Music]\n" + yt[0]
    lrc = None
    try:
        lrc = fetch_lrclib(artist, title, seconds, get=get)
    except Exception as e:  # noqa: BLE001
        errors.append(e)
    if yt:
        if lrc and parse(lrc)["synced"] and similar(yt[0], lrc):
            return "[re:YouTube Music + LRCLIB]\n" + lrc
        return "[re:YouTube Music]\n" + yt[0]
    if lrc:
        return "[re:LRCLIB]\n" + lrc
    if len(errors) == 2:
        raise errors[-1]
    return None


def fetch_lrclib(artist: str, title: str, seconds: float = 0, get=None):
    """LRCLIB's lyrics of a song as LRC / plain text, or None. Raises on network errors."""
    get = get or requests.get
    title = clean_title(title)
    headers = {"User-Agent": f"DISO {brand.VERSION_LABEL} (müzik çalar)"}
    tries = []
    if artist:
        tries.append({"track_name": title, "artist_name": artist})
    tries.append({"q": f"{artist} {title}".strip()})
    for params in tries:
        r = get(API, params=params, headers=headers, timeout=TIMEOUT, proxies=get_proxies())
        r.raise_for_status()
        text = choose(r.json() or [], title, seconds, artist)
        if text:
            return text
    return None


def save(audio_path: str, text: str) -> str:
    path = lyrics_path(audio_path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    os.replace(tmp, path)
    return path


class Fetcher:
    """find(path, artist, title, seconds) on one worker thread; drain() gives (path, found: bool, error)."""

    def __init__(self, find=None):
        self._find = find                           # None: lyrics.fetch, looked up when it is needed
        self._jobs = queue.Queue()
        self._done = queue.Queue()
        self._busy = set()
        self._lock = threading.Lock()
        self._thread = None

    def find(self, path, artist, title, seconds=0, video_id="") -> bool:
        """Ask for the lyrics of this song (False when it is already being looked for)."""
        with self._lock:
            if path in self._busy:
                return False
            self._busy.add(path)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._work, name="lyrics", daemon=True)
                self._thread.start()
        self._jobs.put((path, artist, title, seconds, video_id))
        return True

    def busy(self, path) -> bool:
        return path in self._busy

    def _work(self):
        while True:
            try:
                path, artist, title, seconds, video_id = self._jobs.get(timeout=30)
            except queue.Empty:
                with self._lock:
                    if self._jobs.empty():
                        self._thread = None
                        return
                continue
            found, error = False, ""
            try:
                if not seconds:                             # the length picks the right recording
                    from . import tags
                    seconds = (tags.probe(path).get("duration") or 0) / 1000
                extra = {"video_id": video_id} if video_id else {}
                text = (self._find or fetch)(artist, title, seconds, **extra)
                if text and os.path.isfile(path):
                    save(path, text)
                    found = True
            except Exception as e:  # noqa: BLE001 - shown as "could not look"; the song is fine
                log.info("lyrics for %s: %s", path, e)
                error = str(e)[:200]
            with self._lock:
                self._busy.discard(path)
            self._done.put((path, found, error))

    def drain(self):
        out = []
        while True:
            try:
                out.append(self._done.get_nowait())
            except queue.Empty:
                return out
