"""📺 Followed channels: DISO looks at them now and then and tells when a new video has come.

It never downloads anything by itself: new videos are only announced (a notification) and listed;
the user picks what to download. A channel is a YouTube channel (a link, an @name, or one of its
videos) or any other site's channel / playlist yt-dlp can list. Its newest videos are read without
downloading anything (yt-dlp "flat"); the first look only remembers what is already there, so
following a channel never floods the list with its old videos. Kept in %LOCALAPPDATA%\\DISO\\channels.json.
`Watcher` does the looking on its own thread; the window takes the news with drain()."""
import json
import os
import queue
import re
import threading
import time

from .logs import log
from .utils import app_data_dir

LATEST = 15                 # newest videos read from a channel at each look
KEEP_SEEN = 300             # video ids remembered per channel (to know what is new)
KEEP_NEW = 300              # announced videos kept in the list
FIRST_LOOK = 20             # s after DISO starts before the first look
EVERY = {"30 dakikada bir": 30 * 60, "Saatte bir": 3600, "3 saatte bir": 3 * 3600, "6 saatte bir": 6 * 3600,
         "Günde bir": 24 * 3600}
DEFAULT_EVERY = "Saatte bir"

_YT = re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/", re.I)
_YT_CHANNEL = re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/((?:@[^/?#]+)|(?:channel|c|user)/[^/?#]+)", re.I)
_YT_VIDEO = re.compile(r"^https?://(?:(?:www\.|m\.|music\.)?youtube\.com/(?:watch|shorts/|live/)|youtu\.be/)", re.I)


def channel_link(text: str) -> str:
    """What the user typed as the link that lists the channel's videos ("" when it is no link):
    '@name' / youtube.com/@name/featured -> youtube.com/@name/videos; other sites stay as they are."""
    text = (text or "").strip()
    if re.fullmatch(r"@[\w.\-·]+", text):
        return f"https://www.youtube.com/{text}/videos"
    if not re.match(r"^https?://\S+$", text, re.I):
        return ""
    m = _YT_CHANNEL.match(text)
    if m:
        return f"https://www.youtube.com/{m.group(1)}/videos"
    return text


def is_video_link(url: str) -> bool:
    """A YouTube video (not a channel): its channel is looked up first."""
    return bool(_YT_VIDEO.match(url or ""))


def _name(info: dict) -> str:
    name = info.get("channel") or info.get("uploader") or info.get("title") or ""
    return re.sub(r"\s+-\s+(Videos|Videolar)$", "", str(name).strip())


def _video(e: dict, base: str):
    """One video of a channel as {id, url, title, duration}; None for what is not one."""
    if not isinstance(e, dict) or e.get("live_status") in ("is_live", "is_upcoming"):
        return None
    vid = str(e.get("id") or "")
    url = e.get("webpage_url") or e.get("url") or ""
    if url and not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={vid or url}" if _YT.match(base) else ""
    if not url or not vid:
        return None
    duration = e.get("duration")
    return {"id": vid, "url": url, "title": str(e.get("title") or url).strip(),
            "duration": int(duration) if isinstance(duration, (int, float)) and duration > 0 else 0}


def read_channel(url: str, limit=LATEST, ydl_class=None, opts=None) -> dict:
    """{"url", "name", "videos": [newest first]} of a channel (raises on network errors). A video link
    gives its channel."""
    if ydl_class is None:
        from . import video_engine as ve
        ydl_class, opts = ve._yt_dlp().YoutubeDL, ve.base_opts()
    opts = dict(opts or {})
    opts.update({"quiet": True, "skip_download": True, "noplaylist": False, "socket_timeout": 20})
    if is_video_link(url):
        with ydl_class(dict(opts, extract_flat=False)) as ydl:
            info = ydl.extract_info(url, download=False, process=False) or {}
        owner = info.get("channel_url") or info.get("uploader_url") or ""
        if not owner:
            raise ValueError("Bu videonun kanalını bulamadım")
        url = channel_link(owner)
    opts.update({"extract_flat": "in_playlist", "playlistend": int(limit)})
    with ydl_class(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    if info.get("_type") != "playlist":
        raise ValueError("Bu link bir kanal değil")
    videos = [v for v in (_video(e, url) for e in info.get("entries") or []) if v]
    return {"url": url, "name": _name(info) or url, "videos": videos[:int(limit)]}


class Store:
    """The followed channels and the new videos found on them (thread safe, saved at once)."""

    def __init__(self, path=None):
        self.path = path or os.path.join(app_data_dir(), "channels.json")
        self._lock = threading.Lock()
        self.channels = []          # [{url, name, seen: [ids, newest first], added, checked, error}]
        self.new = []               # [{id, url, title, duration, channel, found}], newest first
        self.every = DEFAULT_EVERY
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.channels = [c for c in data.get("channels", []) if isinstance(c, dict) and c.get("url")]
            self.new = [v for v in data.get("new", []) if isinstance(v, dict) and v.get("url")]
            if data.get("every") in EVERY:
                self.every = data["every"]
        except Exception:  # noqa: BLE001 - nothing followed yet, or a broken file
            pass
        for c in self.channels:
            c.setdefault("name", c["url"])
            c["seen"] = [str(s) for s in c.get("seen") or []][:KEEP_SEEN]
            c.setdefault("checked", 0)
            c.setdefault("error", "")

    def save(self):
        with self._lock:
            data = {"channels": self.channels, "new": self.new, "every": self.every}
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)

    def find(self, url):
        return next((c for c in self.channels if c["url"].rstrip("/").lower() == url.rstrip("/").lower()), None)

    def follow(self, read: dict) -> bool:
        """Start following the channel read by read_channel (its videos now are not new). False: already followed."""
        with self._lock:
            if self.find(read["url"]):
                return False
            self.channels.append({"url": read["url"], "name": read["name"], "added": time.time(),
                                  "seen": [v["id"] for v in read["videos"]][:KEEP_SEEN],
                                  "checked": time.time(), "error": ""})
        self.save()
        return True

    def unfollow(self, url):
        with self._lock:
            self.channels = [c for c in self.channels if c["url"] != url]
        self.save()

    def update(self, url, read=None, error="") -> list:
        """Takes one look's answer: the videos not seen before go to `new` (and are returned)."""
        found = []
        with self._lock:
            c = self.find(url)
            if c is None:
                return []
            c["checked"] = time.time()
            c["error"] = error
            if read is not None:
                c["name"] = read["name"] or c["name"]
                seen = set(c["seen"])
                found = [dict(v, channel=c["name"], found=time.time()) for v in read["videos"] if v["id"] not in seen]
                c["seen"] = ([v["id"] for v in found] + c["seen"])[:KEEP_SEEN]
                known = {v["url"] for v in self.new}
                self.new = ([v for v in found if v["url"] not in known] + self.new)[:KEEP_NEW]
        self.save()
        return found

    def dismiss(self, urls):
        """These new videos are dealt with (downloaded, or the user saw them)."""
        urls = set(urls)
        with self._lock:
            self.new = [v for v in self.new if v["url"] not in urls]
        self.save()

    def set_every(self, label):
        if label in EVERY:
            self.every = label
            self.save()


class Watcher:
    """Looks at every followed channel now and then (and when asked) on its own thread. drain() gives
    the news for the window: ("new", channel name, [videos]) / ("followed", read or None, error) /
    ("checked", None, None) after a whole round."""

    def __init__(self, store, read=None, first_look=FIRST_LOOK):
        self.store, self._read, self._first = store, read, first_look
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._out = queue.Queue()
        self._follow = queue.Queue()
        self._thread = None
        self.busy = False
        self.last_round = 0.0

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="channels", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def check_now(self):
        self.start()
        self._wake.set()

    def follow(self, text):
        """Read and follow the channel the user typed (in the background; the answer comes via drain)."""
        self._follow.put(text)
        self.start()

    def _run(self):
        if self._first and self._wait(self._first):
            return
        while not self._stop.is_set():
            while not self._follow.empty():
                self._add(self._follow.get())
            if self._wake.is_set() or time.time() - self.last_round >= EVERY.get(self.store.every, 3600):
                self._wake.clear()
                self.round()
            if self._wait(5):
                return

    def _wait(self, seconds) -> bool:
        """Sleeps (a wake-up ends it sooner); True when DISO is closing."""
        end = time.time() + seconds
        while time.time() < end and not self._stop.is_set():
            if self._wake.is_set() or not self._follow.empty():
                break
            time.sleep(min(0.5, max(0.0, end - time.time())))
        return self._stop.is_set()

    def _add(self, text):
        link = channel_link(text)
        if not link:
            self._out.put(("followed", None, "Bu bir kanal linki değil"))
            return
        try:
            read = (self._read or read_channel)(link)
        except Exception as e:  # noqa: BLE001 - shown to the user
            log.info("channel %s: %s", link, e)
            self._out.put(("followed", None, _short(e)))
            return
        if not self.store.follow(read):
            self._out.put(("followed", None, "Bu kanalı zaten takip ediyorsun"))
            return
        self._out.put(("followed", read, ""))

    def round(self):
        """Looks at every channel once (on this thread)."""
        self.busy = True
        try:
            for c in list(self.store.channels):
                if self._stop.is_set():
                    return
                try:
                    found = self.store.update(c["url"], (self._read or read_channel)(c["url"]))
                except Exception as e:  # noqa: BLE001 - one channel failing does not stop the others
                    log.info("channel %s: %s", c["url"], e)
                    self.store.update(c["url"], error=_short(e))
                    continue
                if found:
                    self._out.put(("new", c["name"], found))
            self.last_round = time.time()
            self._out.put(("checked", None, None))
        finally:
            self.busy = False

    def drain(self):
        out = []
        while True:
            try:
                out.append(self._out.get_nowait())
            except queue.Empty:
                return out


def _short(e) -> str:
    from .video_engine import pretty_error
    return (pretty_error(e) or str(e)).splitlines()[0][:160]


def announcement(news) -> tuple:
    """(title, text) of the notification for some ("new", channel, videos) news."""
    videos = [(name, v) for kind, name, found in news if kind == "new" for v in found]
    channels = list(dict.fromkeys(name for name, _ in videos))
    if len(videos) == 1:
        return f"📺 {channels[0]}: yeni video", videos[0][1]["title"]
    if len(channels) == 1:
        return f"📺 {channels[0]}: {len(videos)} yeni video", videos[0][1]["title"]
    return f"📺 {len(videos)} yeni video", ", ".join(channels[:4])
