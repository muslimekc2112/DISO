"""
DownloadManager - the "IDM / FDM" part.

* keeps the list of downloads (and saves it, so unfinished ones survive a restart)
* runs up to max_parallel downloads at the same time (changeable while running),
  the rest wait in a queue in the order they were added
* pause / resume / cancel / remove for every item
* expands playlists into one item per video
* refuses a link that is already in the list (optional)
* tries again by itself when the connection drops (WAITING state, growing delays)
* a "gate" the scheduler can close: nothing new starts while it is closed
"""
import collections
import os
import queue
import threading
import time
from urllib.parse import urlsplit

from . import jobs, safefile, torrent
from . import video_engine as ve
from .logs import log
from .models import (ACTIVE_STATES, CANCELLED, DONE, DOWNLOADING, ERROR, PAUSED, PROCESSING,
                     QUEUED, RESOLVING, RESTARTABLE_STATES, WAITING, Item, Settings)
from .segmented_downloader import DownloadStopped, FastDownloader, is_transient
from .utils import app_data_dir, default_download_dir, normalize_url

MAX_PARALLEL = 3
MAX_RETRIES = 3
RETRY_DELAYS = (10, 30, 60, 120, 300)   # seconds before automatic retry 1, 2, 3 ... (tests shorten it)


def url_key(url: str) -> tuple:
    """Two links with the same key are the same download (case of host, '/' at the end and
    #fragment do not matter)."""
    p = urlsplit(normalize_url(url))
    return (p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), p.query)


class LineQueue:
    """The waiting line: first come first served, but one can be moved to the front ("⏫ En üste al")."""

    def __init__(self):
        self._items = collections.deque()
        self._ready = threading.Condition()

    def put(self, item):
        with self._ready:
            self._items.append(item)
            self._ready.notify()

    def get(self):
        with self._ready:
            while not self._items:
                self._ready.wait()
            return self._items.popleft()

    def to_front(self, item) -> bool:
        with self._ready:
            if item not in self._items:
                return False
            self._items.remove(item)
            self._items.appendleft(item)
            return True

    def position(self, item) -> int:
        """1 for the next one, 0 when it is not waiting."""
        with self._ready:
            waiting = [i for i in self._items if getattr(i, "state", QUEUED) == QUEUED and not getattr(i, "removed", False)]
            return waiting.index(item) + 1 if item in waiting else 0


class DownloadManager:
    def __init__(self, max_parallel=MAX_PARALLEL, store_path=None, max_retries=MAX_RETRIES):
        self.items = []
        self.notices = queue.Queue()      # short messages for the UI status bar
        self.events = queue.Queue()       # ("done"|"error", item) for notifications
        self.lock = threading.RLock()
        self._save_lock = threading.Lock()
        self.q = LineQueue()
        self.store_path = store_path or os.path.join(app_data_dir(), "downloads.json")
        self._last_save = 0.0
        self.max_parallel = max(1, int(max_parallel))
        self.max_retries = max(0, int(max_retries))
        self._slots = threading.Condition()   # guards _running / max_parallel / _gate_open
        self._running = 0
        self._gate_open = True
        self.torrent_ask = None               # 🧲 (item, files, reply): the window asks which files (torrent.run)
        self._load()
        threading.Thread(target=self._dispatch, daemon=True).start()

    def set_max_parallel(self, n):
        """Takes effect at once: waiting downloads start when the limit goes up."""
        with self._slots:
            self.max_parallel = max(1, int(n))
            self._slots.notify_all()

    def set_max_retries(self, n):
        self.max_retries = max(0, int(n))

    def set_gate(self, open_: bool):
        """Scheduler: while the gate is closed queued downloads wait, running ones go on."""
        with self._slots:
            self._gate_open = bool(open_)
            self._slots.notify_all()

    @property
    def gate_open(self) -> bool:
        return self._gate_open

    # ------------------------------------------------------------------ persistence
    def _load(self):
        try:
            data = safefile.read_json(self.store_path)            # a broken file comes back from its copy
            self.items = [Item.from_dict(d) for d in data.get("items", [])][-200:]
        except Exception:
            self.items = []

    def save(self):
        # workers and the window both save; one writer at a time. The list is read inside the same turn:
        # read before it, an older picture of the list could be written over a newer one.
        with self._save_lock:
            with self.lock:
                data = {"items": [i.to_dict() for i in self.items]}
            try:
                safefile.write_json(self.store_path, data)
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

    @staticmethod
    def _make_item(url, s: Settings, folder, title="", kind=None, extra=None, group="") -> Item:
        extra = extra or {}
        return Item(url, kind or s.kind, s.quality, s.bitrate, s.connections, folder, s.cookies, title,
                    subs=s.subs, cover=s.cover, sort_folders=s.sort_folders,
                    referer=extra.get("referer", ""), user_agent=extra.get("user_agent", ""),
                    cookie_header=extra.get("cookie", ""), group=group, clip=extra.get("clip"))

    def add_url(self, url: str, s: Settings, start=True, skip_duplicates=False, extra=None) -> bool:
        """Add one link. Returns False if it was skipped because it is already in the list.
        Playlists are expanded in a background thread. `extra` may hold referer, user_agent
        and cookie (a link handed over by the browser extension)."""
        if skip_duplicates and self.find_duplicate(url):
            return False
        folder = s.folder or default_download_dir()
        if s.playlist and s.kind in ("auto", "video", "audio") and not jobs.is_plain_file_link(url):
            threading.Thread(target=self._add_playlist, args=(url, s, folder, start, skip_duplicates),
                             daemon=True).start()
            return True
        self._add_item(self._make_item(url, s, folder, extra=extra), start)
        return True

    def _add_item(self, item: Item, start=True):
        item.state = PAUSED           # a fresh item is "not queued yet"; start() queues it
        with self.lock:
            self.items.append(item)
        if start:
            self.start(item)
        self.save()

    def add_entries(self, entries, s: Settings, start=True, skip_duplicates=False):
        """Add the chosen videos of a playlist: entries = [(url, title, ...), ...].
        Returns (added, skipped)."""
        folder = s.folder or default_download_dir()
        kind = "video" if s.kind == "auto" else s.kind
        group = getattr(entries, "title", "") or ""     # the playlist's name, when these are its videos
        added = skipped = 0
        for entry in entries:
            url, title = entry[0], (entry[1] if len(entry) > 1 else "")
            if skip_duplicates and self.find_duplicate(url):
                skipped += 1
                continue
            self._add_item(self._make_item(url, s, folder, title, kind, group=group), start)
            added += 1
        return added, skipped

    def add_song(self, url: str, title: str, s: Settings, origin="music") -> Item:
        """A song found in the music player: always MP3, one video (never a playlist), started at once."""
        item = self._make_item(url, s, s.folder or default_download_dir(), title, kind="audio")
        item.origin = origin
        self._add_item(item, True)
        return item

    def _add_playlist(self, url, s, folder, start, skip_duplicates=False):
        try:
            entries = ve.expand_playlist(url, s.cookies)
        except Exception as e:
            self.notices.put(f"Listeyi okuyamadım: {ve.pretty_error(e)}")
            entries = [(url, "", 0)]
        added, skipped = self.add_entries(entries, s, start, skip_duplicates)
        if len(entries) > 1:
            text = f"{added} video listeye eklendi"
            if skipped:
                text += f" ({skipped} tanesi zaten listedeydi)"
            self.notices.put(text)

    # ---------------------------------------------------------------------- controls
    def start(self, item: Item):
        with self.lock:
            if item.state in ACTIVE_STATES:
                # ⏸ then ▶ quickly: it is still stopping. It starts again as soon as it has stopped.
                if item.stop_reason == "pause":
                    item._start_again = True
                return
            item.state = QUEUED
            item.stop_reason = None
            item.error = ""
            item.message = ""
            item.retries = 0                  # the user is trying again: start counting afresh
            item.speed, item.eta = 0.0, None
        self.q.put(item)

    def _cancel_timer(self, item: Item):
        timer, item._timer = item._timer, None
        if timer is not None:
            timer.cancel()

    def pause(self, item: Item):
        with self.lock:
            item._start_again = False
            if item.state in (QUEUED, WAITING):
                self._cancel_timer(item)
                item.state = PAUSED
                item.message = ""
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
            if item.state in (QUEUED, WAITING):
                self._cancel_timer(item)
                item.state = CANCELLED
                item.message = ""
        self._cleanup(item)
        self.save()

    def remove(self, item: Item):
        item.removed = True
        if item.state in (RESOLVING, DOWNLOADING, PROCESSING):
            item.request_stop("cancel")
        else:
            self._cancel_timer(item)
            self._cleanup(item)
        with self.lock:
            if item in self.items:
                self.items.remove(item)
        self.save()

    def redownload(self, item: Item):
        """Download this item again from the start (the old file, if any, is left alone)."""
        with self.lock:
            if item.state in ACTIVE_STATES:
                return
        self._cleanup(item)
        item.dest = item.final_path = ""
        item.fraction, item.done, item.total = 0.0, 0, 0
        self.start(item)
        self.save()

    def delete_with_file(self, item: Item):
        """Remove from the list AND delete the downloaded file from the disk."""
        path = item.final_path
        self.remove(item)
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    def pause_all(self, items=None):
        """⏸ every download (or only `items`: the download window leaves the music player's alone)."""
        for it in list(self.items if items is None else items):
            self.pause(it)

    def resume_all(self, items=None):
        """▶ every paused or failed download, and the ones still stopping after ⏸ (they start once stopped)."""
        for it in list(self.items if items is None else items):
            if it.state in (PAUSED, ERROR) or (it.state in ACTIVE_STATES and it.stop_reason == "pause"):
                self.start(it)

    def clear_all(self, items=None):
        """🧹 Empty the list (or remove `items`): running ones are cancelled, downloaded files stay on the disk."""
        for it in list(self.items if items is None else items):
            it.removed = True
            if it.state in (RESOLVING, DOWNLOADING, PROCESSING):
                it.request_stop("cancel")
            else:
                self._cancel_timer(it)
                self._cleanup(it)
        with self.lock:
            self.items = [i for i in self.items if not i.removed]
        self.save()

    def clear_finished(self, items=None):
        """🧹 Take the finished and cancelled downloads off the list (or only those among `items`)."""
        with self.lock:
            among = None if items is None else {id(i) for i in items}
            self.items = [i for i in self.items
                          if i.state not in (DONE, CANCELLED) or (among is not None and id(i) not in among)]
        self.save()

    def shutdown(self):
        """Window is closing: ask everything that runs to pause and remember the list.
        Returns at once (the window must not freeze); poll busy() to see when it is done."""
        for it in list(self.items):
            if it.state == WAITING:
                self._cancel_timer(it)
                it.state = PAUSED
            elif it.state in ACTIVE_STATES:
                it.request_stop("pause")
        self.save()

    def busy(self) -> bool:
        """True while a download is still writing (used when closing). One that is only being
        looked up (RESOLVING) has nothing on the disk yet and yt-dlp cannot be stopped mid-question:
        it is not waited for (it is saved as paused and starts again next time)."""
        return any(i.state in (DOWNLOADING, PROCESSING) for i in self.items)

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
        if item.temp_files and torrent.is_torrent_link(item.url):     # a torrent's own folders, now empty
            torrent.remove_empty_dirs(item.temp_files, item.folder)
        item.temp_files = []

    def to_front(self, item) -> bool:
        """⏫ This queued download is the next one to start."""
        return item.state == QUEUED and self.q.to_front(item)

    def _dispatch(self):
        """One thread hands queued items to worker threads, in the order of the line (oldest first unless one
        was moved to the front), as long as fewer than max_parallel run and the scheduler's gate is open. A
        place is waited for before the next one is taken, so a move to the front still counts. An item that is
        paused / removed while it waits is skipped."""
        while True:
            with self._slots:
                while self._running >= self.max_parallel or not self._gate_open:
                    self._slots.wait(0.5)
            item = self.q.get()
            with self._slots:
                while (self._running >= self.max_parallel or not self._gate_open) \
                        and item.state == QUEUED and not item.removed:
                    self._slots.wait(0.5)
                with self.lock:
                    if item.state != QUEUED or item.removed:
                        continue
                    item.state = RESOLVING
                item.started = time.time()
                self._running += 1
            threading.Thread(target=self._work, args=(item,), daemon=True).start()

    def _work(self, item: Item):
        try:
            self._run(item)
        finally:
            with self._slots:
                self._running -= 1
                self._slots.notify_all()

    def _schedule_retry(self, item: Item, error) -> bool:
        """Connection problem: wait a little, then try again by itself (the partial file is
        kept, so it continues where it stopped). False if it is not worth retrying."""
        if item.removed or item.retries >= self.max_retries or not is_transient(error):
            return False
        item.retries += 1
        delay = RETRY_DELAYS[min(item.retries - 1, len(RETRY_DELAYS) - 1)]
        item.error = ""
        item.message = f"Bağlantı sorunu: {delay:g} sn sonra tekrar deneyeceğim ({item.retries}/{self.max_retries})"
        item.state = WAITING
        timer = threading.Timer(delay, self._requeue, args=(item,))
        timer.daemon = True
        item._timer = timer
        timer.start()
        log.info("connection problem, retry %d/%d in %gs: %s (%s)", item.retries, self.max_retries,
                 delay, item.url, error)
        return True

    def _requeue(self, item: Item):
        with self.lock:
            item._timer = None
            if item.state != WAITING or item.removed:
                return
            if item.stop_reason == "pause":
                item.state = PAUSED
                item.message = ""
                return
            item.state = QUEUED
            item.stop_reason = None
            item.message = ""
        self.q.put(item)

    def _run(self, item: Item):
        try:
            if torrent.is_torrent_link(item.url):          # 🧲 whatever was chosen: aria2 downloads it
                torrent.run(item, ask=self.torrent_ask)
                item.state = DONE
                item.fraction = 1.0
                item.retries = 0
                self.events.put(("done", item))
                log.info("done: %s -> %s", item.url, item.final_path)
                return
            if item.kind == "auto":
                jobs.classify(item)
            elif item.kind in ("video", "audio") and item.origin != "music":
                jobs.keep_files_as_they_are(item)
            if item.stop_reason:
                raise DownloadStopped(item.stop_reason)
            if item.kind == "file":
                jobs.run_file(item)
            else:
                jobs.run_media(item)
            item.state = DONE
            item.fraction = 1.0
            item.retries = 0
            self.events.put(("done", item))
            log.info("done: %s -> %s", item.url, item.final_path)
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
            elif self._schedule_retry(item, e):
                pass
            else:
                item.state = ERROR
                item.error = ve.pretty_error(e) if not isinstance(e, ve.MissingFFmpeg) else str(e)
                self.events.put(("error", item))
                log.error("failed: %s: %s", item.url, item.error, exc_info=True)
        finally:
            item._fd = None
            item._proc = None
            item.speed, item.eta, item.conns = 0.0, None, 0
            again, item._start_again = item._start_again, False
            if again and item.state == PAUSED and not item.removed:
                self.start(item)
            self.save()
