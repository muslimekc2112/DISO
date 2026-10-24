"""🔊 Even volume: how loud every song is, so a loud one does not jump out after a quiet one.

ffmpeg measures a song's loudness the way radio and the streaming services do (EBU R128, in LUFS) on a
background thread; the answer is kept (loudness.json) so a song is measured once. A song louder than
TARGET is played that much softer; a quieter one plays as it is (Windows' MCI cannot play louder than the
file, so nothing is ever made louder). Nothing here touches the window."""
import json
import os
import queue
import re
import subprocess
import threading

from .logs import log
from .utils import app_data_dir, subprocess_flags

TARGET = -14.0                 # LUFS: what the streaming services play at
MOST = 12.0                    # dB: a song is never made softer than this
TIMEOUT = 180
_INTEGRATED = re.compile(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS")


def _tool(name):
    from .tags import _tool as find
    return find(name)


def measure(path: str):
    """The loudness of a song in LUFS, or None when it cannot be measured (no ffmpeg, no sound)."""
    ffmpeg = _tool("ffmpeg")
    if not ffmpeg:
        return None
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0", "-vn",
                               "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                              capture_output=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL, **subprocess_flags())
    except (OSError, subprocess.SubprocessError) as e:
        log.info("cannot measure %s: %s", path, e)
        return None
    found = _INTEGRATED.findall(proc.stderr.decode("utf-8", "replace"))
    if not found:
        return None
    value = float(found[-1])                      # the summary at the end
    return value if value > -70 else None         # silence


def factor(lufs) -> float:
    """How much of the volume a song of this loudness gets (1.0: as it is)."""
    if lufs is None:
        return 1.0
    cut = min(MOST, max(0.0, lufs - TARGET))
    return round(10 ** (-cut / 20), 3)


def _signature(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [int(st.st_mtime), st.st_size]


class Leveler:
    """request(path) measures in the background; gain(path) is the volume factor (1.0 until it is known);
    drain() gives the paths measured since the last call."""

    def __init__(self, cache_path=None, measure_fn=None):
        self.cache_path = cache_path or os.path.join(app_data_dir(), "loudness.json")
        self._measure = measure_fn or measure
        self._lock = threading.Lock()
        self._jobs = queue.Queue()
        self._done = queue.Queue()
        self._pending = set()
        self._thread = None
        self._stopped = False
        self._cache = self._load()

    def _load(self):
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001 - a missing or damaged file is simply empty
            return {}

    def _save(self):
        with self._lock:
            data = dict(self._cache)
        tmp = self.cache_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.cache_path)
        except OSError:
            pass

    @staticmethod
    def _key(path):
        return os.path.normcase(os.path.abspath(path))

    def known(self, path) -> bool:
        entry = self._cache.get(self._key(path))
        return bool(entry) and entry.get("sig") == _signature(path)

    def gain(self, path) -> float:
        entry = self._cache.get(self._key(path)) if path else None
        if not entry or entry.get("sig") != _signature(path):
            return 1.0
        return factor(entry.get("lufs"))

    def request(self, path):
        if not path or self._stopped or self.known(path) or not os.path.isfile(path):
            return
        key = self._key(path)
        with self._lock:
            if key in self._pending:
                return
            self._pending.add(key)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._work, daemon=True, name="loudness")
                self._thread.start()
        self._jobs.put(path)

    def _work(self):
        while not self._stopped:
            try:
                path = self._jobs.get(timeout=30)
            except queue.Empty:
                with self._lock:
                    if self._jobs.empty():
                        self._thread = None
                        return
                continue
            try:
                lufs = self._measure(path)
                sig = _signature(path)
                if sig is not None:
                    with self._lock:
                        self._cache[self._key(path)] = {"sig": sig, "lufs": lufs}
                    self._save()
            except Exception:  # noqa: BLE001 - one bad file must not stop the others
                log.exception("loudness of %s", path)
            finally:
                with self._lock:
                    self._pending.discard(self._key(path))
                self._done.put(path)

    def drain(self):
        out = []
        while True:
            try:
                out.append(self._done.get_nowait())
            except queue.Empty:
                return out

    def stop(self):
        self._stopped = True
