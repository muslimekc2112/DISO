"""🖼 A cover picture from the internet for a song that has none: YouTube Music's own picture of the very
video the song was downloaded from, else of its song with the same name and artist (the same matching as
the lyrics, so another song's picture does not come). The picture is written into the file (tags.write_tags).
Nothing here touches the window: `Finder` works on another thread, the window polls drain()."""
import os
import queue
import re
import tempfile
import threading
import time

import requests

from . import lyrics, tags
from .logs import log
from .segmented_downloader import build_headers, get_proxies

RETRY_WAIT = 2                                # seconds before asking again after a dropped connection
SIZE = 544                                   # pixels: what YouTube Music shows on its big player
_SIZE_IN_URL = re.compile(r"=w\d+-h\d+")


def big(url: str) -> str:
    """The same picture in SIZE x SIZE (Google's picture links carry their size)."""
    return _SIZE_IN_URL.sub(f"=w{SIZE}-h{SIZE}", url) if _SIZE_IN_URL.search(url or "") else url


def _largest(thumbnails) -> str:
    good = [t for t in thumbnails or [] if isinstance(t, dict) and t.get("url")]
    if not good:
        return ""
    return big(max(good, key=lambda t: int(t.get("width") or 0))["url"])


def picture_url(artist="", title="", seconds=0, video_id="", api=None) -> str:
    """The link of the cover, or "" when no song that is surely this one is found."""
    api = lyrics._ytmusic(api)
    if video_id:
        tracks = (api.get_watch_playlist(videoId=video_id) or {}).get("tracks") or []
        if tracks and tracks[0].get("videoId") == video_id:
            url = _largest(tracks[0].get("thumbnail") or tracks[0].get("thumbnails"))
            if url:
                return url
    if not (title or "").strip():
        return ""
    query = f"{artist} {lyrics.clean_title(title)}".strip()
    found = [r for r in (api.search(query, filter="songs", limit=10) or [])[:10] if lyrics._same_song(title, artist, r)]

    def gap(r):
        length = r.get("duration_seconds")
        return abs(float(length) - seconds) if seconds and isinstance(length, (int, float)) else 0.0
    for r in sorted(found, key=gap):
        url = _largest(r.get("thumbnails"))
        if url:
            return url
    return ""


def download(url: str, target: str) -> str:
    r = requests.get(url, headers=build_headers(), timeout=20, proxies=get_proxies())
    r.raise_for_status()
    if not r.content or not r.headers.get("Content-Type", "image").startswith("image"):
        raise OSError("resim gelmedi")
    with open(target, "wb") as f:
        f.write(r.content)
    return target


def fetch_picture(artist="", title="", seconds=0, video_id="", api=None):
    """The cover as a picture file in the temp folder, or None. Raises when YouTube Music cannot be reached."""
    url = picture_url(artist, title, seconds, video_id, api)
    if not url:
        return None
    fd, target = tempfile.mkstemp(prefix="diso-cover-", suffix=".jpg")
    os.close(fd)
    try:
        return download(url, target)
    except Exception:
        os.remove(target)
        raise


class Finder:
    """find(path, artist, title, seconds, video_id) on one worker thread. drain() gives (path, result, detail):
    "done" (written into the file), "later" (a picture to write when the window lets go of the file: detail
    is its path), "none" (not found), "has" (it had one), "cant" (this kind of file takes no cover) or
    "error" (detail: why). busy(path) -> True for the song that plays (Windows does not let it be rewritten)."""

    def __init__(self, find=None, busy=lambda path: False):
        self._find = find or fetch_picture
        self.busy = busy
        self._jobs, self._done = queue.Queue(), queue.Queue()
        self._lock = threading.Lock()
        self._waiting = set()
        self._thread = None

    def find(self, path, artist, title, seconds=0, video_id="", force=False) -> bool:
        with self._lock:
            if path in self._waiting:
                return False
            self._waiting.add(path)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._work, daemon=True, name="covers")
                self._thread.start()
        self._jobs.put((path, artist, title, seconds, video_id, force))
        return True

    def pending(self) -> int:
        return len(self._waiting)

    def _work(self):
        while True:
            try:
                job = self._jobs.get(timeout=30)
            except queue.Empty:
                with self._lock:
                    if self._jobs.empty():
                        self._thread = None
                        return
                continue
            path = job[0]
            try:
                result = self._one(*job)
            except Exception as e:  # noqa: BLE001 - said to the user; the song is fine
                log.info("cover for %s: %s", path, e)
                result = ("error", str(e)[:200])
            with self._lock:
                self._waiting.discard(path)
            self._done.put((path,) + result)

    def _one(self, path, artist, title, seconds, video_id, force):
        if os.path.splitext(path)[1].lower() not in tags.COVER_FORMATS:
            return ("cant", "")
        if not force and tags.probe(path).get("cover"):
            return ("has", "")
        try:
            picture = self._find(artist, title, seconds, video_id)
        except OSError as e:                                  # a dropped connection: once more, a bit later
            log.info("cover for %s, asking again: %s", path, e)
            time.sleep(RETRY_WAIT)
            picture = self._find(artist, title, seconds, video_id)
        if not picture:
            return ("none", "")
        if self.busy(path):
            return ("later", picture)
        try:
            tags.write_tags(path, {}, cover=picture)
        finally:
            try:
                os.remove(picture)
            except OSError:
                pass
        return ("done", "")

    def drain(self):
        out = []
        while True:
            try:
                out.append(self._done.get_nowait())
            except queue.Empty:
                return out
