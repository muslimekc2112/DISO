"""Plain data classes shared by the UI, the manager and the job runners."""
import time
import uuid
from dataclasses import dataclass

from .utils import clip_text

# ---- item states
QUEUED = "queued"
WAITING = "waiting"            # connection problem: will try again by itself (see manager)
RESOLVING = "resolving"        # finding out the file / video info
DOWNLOADING = "downloading"
PROCESSING = "processing"      # ffmpeg merge / MP3 conversion
DONE = "done"
PAUSED = "paused"
ERROR = "error"
CANCELLED = "cancelled"

ACTIVE_STATES = (QUEUED, WAITING, RESOLVING, DOWNLOADING, PROCESSING)
RESTARTABLE_STATES = (PAUSED, ERROR, CANCELLED)

SUBTITLE_CHOICES = ["Yok", "Türkçe", "İngilizce", "Tüm diller"]


@dataclass
class Settings:
    """What the user chose in the option bar when pressing the download button."""
    kind: str = "auto"          # auto | video | audio | file
    quality: str = "En iyi"     # video height limit
    bitrate: str = "320"        # MP3 kbps
    connections: int = 16       # parallel connections per download
    folder: str = ""
    playlist: bool = False
    cookies: str = "Yok"        # browser to read login cookies from
    subs: str = "Yok"           # subtitles to save next to a video (SUBTITLE_CHOICES)
    cover: bool = True          # put the thumbnail into an MP3 as cover art
    sort_folders: bool = False  # save into Video / Müzik / Arşiv ... sub-folders


class Item:
    """One entry of the download list."""

    PERSISTED = ("id", "url", "kind", "quality", "bitrate", "connections", "folder",
                 "cookies", "title", "state", "dest", "final_path", "error", "added",
                 "subs", "cover", "sort_folders", "referer", "user_agent", "group", "origin", "clip",
                 "torrent_select")

    def __init__(self, url, kind="auto", quality="En iyi", bitrate="320", connections=16,
                 folder="", cookies="Yok", title="", *, subs="Yok", cover=True,
                 sort_folders=False, referer="", user_agent="", cookie_header="", group="", origin="",
                 clip=None):
        self.id = uuid.uuid4().hex[:10]
        self.url = url
        self.kind = kind
        self.quality = quality
        self.bitrate = bitrate
        self.connections = int(connections)
        self.folder = folder
        self.cookies = cookies
        self.title = title
        self.subs = subs
        self.cover = cover
        self.sort_folders = sort_folders
        self.referer = referer          # sent as the Referer header (browser extension)
        self.user_agent = user_agent    # ... and as User-Agent
        self.group = group              # name of the playlist it was taken from ("" = a single link)
        self.origin = origin            # "music": found in the music player (asks for a list when done)
        self.clip = list(clip) if clip else None   # [start, end] seconds: only this part of the video (✂)
        self.torrent_select = None      # 🧲 the files of a torrent to download (aria2's 1-based indexes; None: ask)
        self.state = QUEUED
        self.dest = ""             # final path of a plain file download (kept for resume)
        self.final_path = ""
        self.error = ""
        self.added = time.time()
        # ---- runtime only (not saved)
        # The browser's cookies for this download stay in memory only: they are a login.
        self.cookie_header = cookie_header
        self.done = 0
        self.total = 0
        self.fraction = 0.0
        self.speed = 0.0
        self.eta = None
        self.conns = 0
        self.message = ""
        self.stop_reason = None    # None | "pause" | "cancel"
        self.temp_files = []
        self.removed = False
        self.retries = 0           # automatic retries after connection problems
        self.started = 0.0         # when it last started working (for the speed in the history)
        self._timer = None         # pending automatic retry
        self._start_again = False  # "start" came while a pause was still stopping it: start once stopped
        self._fd = None
        self._proc = None
        self._probe = None
        self.torrent_files = []    # 🧲 the files of the torrent, once known (torrent.files_of)
        self.reselect = None       # 🧲 a new choice of files made while it downloads

    # ---------------------------------------------------------------- persistence
    def to_dict(self):
        return {k: getattr(self, k) for k in self.PERSISTED}

    @classmethod
    def from_dict(cls, d):
        it = cls(d.get("url", ""))
        for k in cls.PERSISTED:
            if k in d:
                setattr(it, k, d[k])
        if it.state in ACTIVE_STATES:      # app was closed while it was running
            it.state = PAUSED
        if it.state == DONE:
            it.fraction = 1.0
        return it

    # ------------------------------------------------------------------- control
    @property
    def display_name(self):
        name = self.title or (self.dest and self.dest.split("/")[-1].split("\\")[-1]) or self.url
        return f"{name}  ✂ {clip_text(self.clip)}" if self.clip else name

    def request_headers(self) -> dict:
        """Extra headers for the requests of this download (Referer / User-Agent / Cookie)."""
        h = {}
        if self.referer:
            h["Referer"] = self.referer
        if self.user_agent:
            h["User-Agent"] = self.user_agent
        if self.cookie_header:
            h["Cookie"] = self.cookie_header
        return h

    def attach(self, fd):
        """Register the engine that is downloading right now so stop requests reach it."""
        self._fd = fd
        if self.stop_reason:
            fd.stop(self.stop_reason)

    def request_stop(self, reason):
        self.stop_reason = reason
        fd = self._fd
        if fd is not None:
            fd.stop(reason)
        proc = self._proc
        if proc is not None:  # a running ffmpeg merge stops too; the parts are kept for resume
            try:
                proc.kill()
            except Exception:
                pass

    def on_progress(self, done, total, speed, eta, conns):
        self.done, self.total = done, total
        self.fraction = (done / total) if total else 0.0
        self.speed, self.eta, self.conns = speed, eta, conns
