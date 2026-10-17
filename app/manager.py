"""
DownloadManager - the "IDM / FDM" part.

* keeps the list of downloads (and saves it, so unfinished ones survive a restart)
* runs up to max_parallel downloads at the same time (changeable while running),
  the rest wait in a queue in the order they were added
* pause / resume / cancel / remove for every item
* expands playlists into one item per video
* refuses a link that is already in the list (optional)
"""
import json
import os
import queue
import threading
from urllib.parse import urlsplit

from . import jobs
from . import video_engine as ve
from .models import (ACTIVE_STATES, CANCELLED, DONE, DOWNLOADING, ERROR, PAUSED, PROCESSING,
                     QUEUED, RESOLVING, RESTARTABLE_STATES, Item, Settings)
from .segmented_downloader import DownloadStopped, FastDownloader
from .utils import app_data_dir, default_download_dir, normalize_url

MAX_PARALLEL = 3


def url_key(url: str) -> tuple:
    """Two links with the same key are the same download (case of host, '/' at the end and
    #fragment do not matter)."""
    p = urlsplit(normalize_url(url))
    return (p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), p.query)


class DownloadManager:
    def __init__(self, max_parallel=MAX_PARALLEL, store_path=None):
        self.items = []
        self.notices = queue.Queue()      # short messages for the UI status bar
        self.events = queue.Queue()       # ("done"|"error", item) for notifications
        self.lock = threading.RLock()
        self._save_lock = threading.Lock()
        self.q = queue.Queue()
        self.store_path = store_path or os.path.join(app_data_dir(), "downloads.json")
        self._last_save = 0.0
        self.max_parallel = max(1, int(max_parallel))
        self._slots = threading.Condition()   # guards _running / max_parallel
        self._running = 0
        self._load()
        threading.Thread(target=self._dispatch, daemon=True).start()

    def set_max_parallel(self, n):
        """Takes effect at once: waiting downloads start when the limit goes up."""
        with self._slots:
            self.max_parallel = max(1, int(n))
            self._slots.notify_all()

    # ------------------------------------------------------------------ persistence
    def _load(self):
        try:
            with open(self.store_path, encoding="utf-8") as f:
                data = json.load(f)
            self.items = [Item.from_dict(d) for d in data.get("items", [])][-200:]
        except Exception:
            self.items = []

    def save(self):
        with self.lock:
            data = {"items": [i.to_dict() for i in self.items]}
        tmp = self.store_path + ".tmp"
        with self._save_lock:  # workers and the window both save; one writer at a time
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(tmp, self.store_path)
            except OSError:
                pass

    # ------------------------------------------------------------------------ adding
    def find_duplicate(self, url: str):
        """The list item that already downloads this link, or None."""
        key = url_key(url)
        with self.lock:
            for it in self.items:
                if it.state != CANCELLED and url_key(it.url) == key:
                    return it
        return None

    def add_url(self, url: str, s: Settings, start=True, skip_duplicates=False) -> bool:
        """Add one link. Returns False if it was skipped because it is already in the list.
        Playlists are expanded in a background thread."""
        if skip_duplicates and self.find_duplicate(url):
            return False
        folder = s.folder or default_download_dir()
        if s.playlist and s.kind in ("auto", "video", "audio"):
            threading.Thread(target=self._add_playlist, args=(url, s, folder, start, skip_duplicates),
                             daemon=True).start()
            return True
        self._add_item(Item(url, s.kind, s.quality, s.bitrate, s.connections, folder, s.cookies), start)
        return True

    def _add_item(self, item: Item, start=True):
        item.state = PAUSED           # a fresh item is "not queued yet"; start() queues it
        with self.lock:
            self.items.append(item)
        if start:
            self.start(item)
        self.save()

    def _add_playlist(self, url, s, folder, start, skip_duplicates=False):
        try:
            entries = ve.expand_playlist(url, s.cookies)
        except Exception as e:
            self.notices.put(f"Liste okunamadı: {ve.pretty_error(e)}")
            entries = [(url, "")]
        kind = "video" if s.kind == "auto" else s.kind
        added = skipped = 0
        for u, title in entries:
            if skip_duplicates and self.find_duplicate(u):
                skipped += 1
                continue
            self._add_item(Item(u, kind, s.quality, s.bitrate, s.connections, folder, s.cookies, title), start)
            added += 1
        if len(entries) > 1:
            text = f"{added} video listeye eklendi"
            if skipped:
                text += f" ({skipped} tanesi zaten listedeydi)"
            self.notices.put(text)

    # ---------------------------------------------------------------------- controls
    def start(self, item: Item):
        with self.lock:
            if item.state in ACTIVE_STATES:
                return
            item.state = QUEUED
            item.stop_reason = None
            item.error = ""
            item.message = ""
            item.speed, item.eta = 0.0, None
        self.q.put(item)

    def pause(self, item: Item):
        with self.lock:
            if item.state == QUEUED:
                item.state = PAUSED
            elif item.state in ACTIVE_STATES:
                item.request_stop("pause")
        self.save()

    def resume(self, item: Item):
        if item.state in RESTARTABLE_STATES:
            self.start(item)

    def cancel(self, item: Item):
        with self.lock:
            if item.state in (RESOLVING, DOWNLOADING, PROCESSING):
                item.request_stop("cancel")
                return
            if item.state == QUEUED:
                item.state = CANCELLED
        self._cleanup(item)
        self.save()

    def remove(self, item: Item):
        item.removed = True
        if item.state in ACTIVE_STATES:
            item.request_stop("cancel")
        else:
            self._cleanup(item)
        with self.lock:
            if item in self.items:
                self.items.remove(item)
        self.save()

    def pause_all(self):
        for it in list(self.items):
            self.pause(it)

    def resume_all(self):
        for it in list(self.items):
            if it.state in (PAUSED, ERROR):
                self.start(it)

    def clear_finished(self):
        with self.lock:
            self.items = [i for i in self.items if i.state not in (DONE, CANCELLED)]
        self.save()

    def shutdown(self):
        """Window is closing: ask everything that runs to pause and remember the list.
        Returns at once (the window must not freeze); poll busy() to see when it is done."""
        for it in list(self.items):
            if it.state in ACTIVE_STATES:
                it.request_stop("pause")
        self.save()

    def busy(self) -> bool:
        """True while a worker thread still runs (used when closing)."""
        return any(i.state in (RESOLVING, DOWNLOADING, PROCESSING) for i in self.items)

    # ------------------------------------------------------------------------ workers
    def _cleanup(self, item: Item):
        if item.dest:
            FastDownloader.cleanup(item.dest)
        for p in item.temp_files:
            FastDownloader.cleanup(p)
            try:
                os.remove(p)
            except OSError:
                pass
        item.temp_files = []

    def _dispatch(self):
        """One thread hands queued items to worker threads, oldest first, as long as fewer
        than max_parallel run. An item that is paused / removed while it waits is skipped."""
        while True:
            item = self.q.get()
            with self._slots:
                while self._running >= self.max_parallel and item.state == QUEUED and not item.removed:
                    self._slots.wait(0.5)
                with self.lock:
                    if item.state != QUEUED or item.removed:
                        continue
                    item.state = RESOLVING
                self._running += 1
            threading.Thread(target=self._work, args=(item,), daemon=True).start()

    def _work(self, item: Item):
        try:
            self._run(item)
        finally:
            with self._slots:
                self._running -= 1
                self._slots.notify_all()

    def _run(self, item: Item):
        try:
            if item.kind == "auto":
                jobs.classify(item)
            if item.stop_reason:
                raise DownloadStopped(item.stop_reason)
            if item.kind == "file":
                jobs.run_file(item)
            else:
                jobs.run_media(item)
            item.state = DONE
            item.fraction = 1.0
            self.events.put(("done", item))
        except DownloadStopped as e:
            if e.reason == "cancel":
                self._cleanup(item)
                item.state = CANCELLED
            else:
                item.state = PAUSED
        except Exception as e:
            if item.stop_reason == "cancel":
                self._cleanup(item)
                item.state = CANCELLED
            elif item.stop_reason == "pause":
                item.state = PAUSED
            else:
                item.state = ERROR
                item.error = ve.pretty_error(e) if not isinstance(e, ve.MissingFFmpeg) else str(e)
                self.events.put(("error", item))
        finally:
            item._fd = None
            item._proc = None
            item.speed, item.eta, item.conns = 0.0, None, 0
            self.save()
