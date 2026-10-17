"""Plain data classes shared by the UI, the manager and the job runners."""
import time
import uuid
from dataclasses import dataclass

# ---- item states
QUEUED = "queued"
RESOLVING = "resolving"        # finding out the file / video info
DOWNLOADING = "downloading"
PROCESSING = "processing"      # ffmpeg merge / MP3 conversion
DONE = "done"
PAUSED = "paused"
ERROR = "error"
CANCELLED = "cancelled"

ACTIVE_STATES = (QUEUED, RESOLVING, DOWNLOADING, PROCESSING)
RESTARTABLE_STATES = (PAUSED, ERROR, CANCELLED)


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


class Item:
    """One entry of the download list."""

    PERSISTED = ("id", "url", "kind", "quality", "bitrate", "connections", "folder",
                 "cookies", "title", "state", "dest", "final_path", "error", "added")

    def __init__(self, url, kind="auto", quality="En iyi", bitrate="320", connections=16,
                 folder="", cookies="Yok", title=""):
        self.id = uuid.uuid4().hex[:10]
        self.url = url
        self.kind = kind
        self.quality = quality
        self.bitrate = bitrate
        self.connections = int(connections)
        self.folder = folder
        self.cookies = cookies
        self.title = title
        self.state = QUEUED
        self.dest = ""             # final path of a plain file download (kept for resume)
        self.final_path = ""
        self.error = ""
        self.added = time.time()
        # ---- runtime only (not saved)
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
        self._fd = None
        self._proc = None
        self._probe = None

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
        return self.title or (self.dest and self.dest.split("/")[-1].split("\\")[-1]) or self.url

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
