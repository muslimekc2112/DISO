"""Song lyrics for the music player.

Lyrics come only from YouTube Music: the lyrics of the very video a found song was downloaded from, so
they belong to that song; for other songs (or a video without lyrics) YouTube Music's song of the same
name and artist. Other lyrics sites are not asked: they too often had another song of the same name.
Most come with the time of every line ("synced": the player can follow the song). They are kept next
to the song as '<song>.lrc', the usual place music players look, so a song carries its lyrics with it. A file without time marks is plain
lyrics. Nothing here touches the window: `Fetcher` works on another thread and the window polls it."""
import os
import queue
import re
import threading
import time

from .logs import log

RETRY_WAIT = 2                                      # seconds before asking again after a dropped connection

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
    from .music_search import fold                    # "Şımarık" == "Simarik", as in the song search
    return fold(text)


def _same_name(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a in b or b in a)


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
    from .music_search import _ytmusic as client      # gives up on a hanging request, uses DISO's proxy
    return client()


def _core(title: str) -> str:
    """The bare name of a song: 'On & On (Lyrics) feat. Daniel Levi' -> 'on on'."""
    out = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", clean_title(title))
    out = re.split(r"\s(?:feat|ft|featuring)\.?\s", f" {out} ", flags=re.I)[0]
    return _norm(out)


def _same_song(title: str, artist: str, r: dict) -> bool:
    """A YouTube Music song is this one: the same name (and the same artist when it is known; without
    an artist the name must be exactly the same, a name alone is too little)."""
    if not isinstance(r, dict) or not r.get("videoId"):
        return False
    names = " ".join(a.get("name", "") for a in r.get("artists") or [] if isinstance(a, dict))
    if artist:
        return _same_name(_core(title), _core(r.get("title"))) and _same_name(artist, names)
    return bool(_core(title)) and _core(title) == _core(r.get("title"))


def _songs(api, artist: str, title: str, seconds: float = 0) -> list:
    """YouTube Music's songs that are this song, the one closest in length first."""
    query = f"{artist} {clean_title(title)}".strip()
    found = [r for r in (api.search(query, filter="songs", limit=10) or [])[:10] if _same_song(title, artist, r)]

    def gap(r):
        length = r.get("duration_seconds")
        return abs(float(length) - seconds) if seconds and isinstance(length, (int, float)) else 0.0
    return [r["videoId"] for r in sorted(found, key=gap)]


def _lyrics_of(api, video_id: str):
    """(text, timed) of one YouTube Music video / song, or None."""
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


def ytmusic_lyrics(video_id="", artist="", title="", seconds=0, api=None):
    """(text, timed) from YouTube Music, or None. First the lyrics of the very video the song was
    downloaded from; when it has none (or there is no video), YouTube Music's own song of that name
    and artist, the one closest in length."""
    api = _ytmusic(api)
    if video_id:
        found = _lyrics_of(api, video_id)
        if found:
            return found
    if not (title or "").strip():
        return None
    for song in _songs(api, artist, title, seconds)[:2]:
        if song != video_id:
            found = _lyrics_of(api, song)
            if found:
                return found
    return None


def fetch(artist: str, title: str, seconds: float = 0, video_id="", ytm=None):
    """The lyrics of a song as LRC / plain text, or None. Only from YouTube Music: other lyrics sites
    too often had another song of the same name. Raises when YouTube Music cannot be reached."""
    found = ytmusic_lyrics(video_id, artist, title, seconds, api=ytm)
    return "[re:YouTube Music]\n" + found[0] if found else None


def raw(audio_path: str) -> str:
    """The lyrics file of this song as it is written (time marks and all), "" when there is none."""
    try:
        with open(lyrics_path(audio_path), encoding="utf-8-sig") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def write_by_hand(audio_path: str, text: str) -> bool:
    """✎ Lyrics written or pasted by the user. Empty text deletes the lyrics (True: there are lyrics now)."""
    if (text or "").strip():
        save(audio_path, text)
        return True
    try:
        os.remove(lyrics_path(audio_path))
    except OSError:
        pass
    return False


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
                try:
                    text = (self._find or fetch)(artist, title, seconds, **extra)
                except OSError as e:                        # a dropped connection: once more, a bit later
                    log.info("lyrics for %s, asking again: %s", path, e)
                    time.sleep(RETRY_WAIT)
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
