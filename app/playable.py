"""Playable copies of files that Windows' MCI cannot open.

MCI refuses some files that are fine: an MP3 whose cover picture is bigger than about 128 KB (the
MPEG reader gives up looking for the sound behind it), or a video whose sound is Opus / Vorbis
(YouTube's VP9 / AV1 downloads). For those, ffmpeg makes an MP3 in a cache folder (the sound only:
copied as it is when it already is MP3, else converted) and that is what plays. The user's file is
never changed.

The window never waits: `request()` starts the work on a background thread, `ready()` says when the
copy is there (also in later sessions: the copy stays in the cache)."""
import hashlib
import json
import os
import subprocess
import threading

from .logs import log
from .utils import app_data_dir, subprocess_flags

TIMEOUT = 300                      # a long song converted on a slow machine
CACHE_LIMIT = 1024 * 1024 * 1024   # the cache is kept below 1 GB, oldest copies go first


def cache_dir() -> str:
    d = os.path.join(app_data_dir(), "play_cache")
    os.makedirs(d, exist_ok=True)
    return d


def copy_path(path: str) -> str:
    """Where the playable copy of this file is (or would be) kept. A changed file gets a new copy."""
    try:
        st = os.stat(path)
        sig = f"{int(st.st_mtime)}|{st.st_size}"
    except OSError:
        sig = "0|0"
    key = hashlib.sha1(f"{os.path.abspath(path)}|{sig}".encode("utf-8")).hexdigest()
    return os.path.join(cache_dir(), key + ".mp3")


def _tool(name):
    from .tags import _tool as find
    return find(name)


def audio_codec(path: str) -> str:
    """The codec of the first sound stream ('mp3', 'opus', ...), '' if it cannot be told."""
    ffprobe = _tool("ffprobe")
    if not ffprobe:
        return ""
    try:
        proc = subprocess.run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                               "stream=codec_name", "-print_format", "json", path],
                              capture_output=True, timeout=30, stdin=subprocess.DEVNULL, **subprocess_flags())
        streams = json.loads(proc.stdout.decode("utf-8", "replace") or "{}").get("streams") or []
        return str(streams[0].get("codec_name") or "") if streams else ""
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""


def make_args(path: str, out: str, codec: str) -> list:
    """ffmpeg arguments (without the program) for the copy: the sound only, tags kept, no picture."""
    args = ["-y", "-hide_banner", "-loglevel", "error", "-i", path, "-map", "0:a:0", "-vn"]
    if codec == "mp3":
        args += ["-c:a", "copy"]                         # same sound, only the big cover goes
    else:
        args += ["-c:a", "libmp3lame", "-b:a", "192k"]   # constant rate: MCI misjudges the length of VBR
    return args + ["-id3v2_version", "3", "-f", "mp3", out]


def _prune(keep: str):
    """Delete the oldest copies while the cache is bigger than CACHE_LIMIT (never `keep`)."""
    try:
        entries = []
        for name in os.listdir(cache_dir()):
            full = os.path.join(cache_dir(), name)
            st = os.stat(full)
            entries.append((st.st_mtime, st.st_size, full))
    except OSError:
        return
    total = sum(e[1] for e in entries)
    for _, size, full in sorted(entries):
        if total <= CACHE_LIMIT:
            break
        if os.path.normcase(full) == os.path.normcase(keep):
            continue
        try:
            os.remove(full)
            total -= size
        except OSError:
            pass


class Preparer:
    """Makes playable copies one at a time on a background thread.

    request(path) -> starts the work (asking twice is fine)
    ready(path)   -> the copy's path once it is made, else None
    failed(path)  -> True when no copy could be made (no ffmpeg, no sound in the file, ...)
    """

    def __init__(self, run=None):
        self._run = run or self._ffmpeg
        self._lock = threading.Lock()
        self._wanted = []                 # paths waiting, in order
        self._busy = None
        self._failed = set()
        self._proc = None
        self._stopped = False
        self._wake = threading.Event()
        self._thread = None

    def ready(self, path: str):
        target = copy_path(path)
        return target if os.path.isfile(target) and os.path.getsize(target) > 0 else None

    def failed(self, path: str) -> bool:
        with self._lock:
            return os.path.abspath(path) in self._failed

    def busy(self, path: str) -> bool:
        key = os.path.abspath(path)
        with self._lock:
            return self._busy == key or key in self._wanted

    def request(self, path: str):
        key = os.path.abspath(path)
        with self._lock:
            if self._stopped or key in self._failed or key == self._busy or key in self._wanted:
                return
            self._wanted.append(key)
            if self._thread is None:
                self._thread = threading.Thread(target=self._work, daemon=True, name="playable")
                self._thread.start()
        self._wake.set()

    def stop(self):
        """Give up: what waits is dropped, a running ffmpeg is ended (its half copy is deleted)."""
        with self._lock:
            self._stopped = True
            self._wanted.clear()
            proc = self._proc
        self._wake.set()
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass

    # ------------------------------------------------------------------ the work
    def _work(self):
        while True:
            self._wake.wait()
            with self._lock:
                if self._stopped:
                    return
                if not self._wanted:
                    self._wake.clear()
                    continue
                path = self._busy = self._wanted.pop(0)
            ok = False
            try:
                ok = self.ready(path) is not None or self._make(path)
            except Exception:  # noqa: BLE001 - one bad file must not stop the others
                log.exception("cannot make a playable copy of %s", path)
            with self._lock:
                self._busy = None
                if not ok and not self._stopped:
                    self._failed.add(path)

    def _make(self, path: str) -> bool:
        if not os.path.isfile(path):
            return False
        target = copy_path(path)
        part = target + ".part"
        try:
            if self._run(path, part) and os.path.isfile(part) and os.path.getsize(part) > 0:
                os.replace(part, target)
                log.info("playable copy made for %s", path)
                _prune(target)
                return True
            log.info("no playable copy for %s", path)
            return False
        finally:
            try:
                os.remove(part)
            except OSError:
                pass

    def _ffmpeg(self, path: str, out: str) -> bool:
        ffmpeg = _tool("ffmpeg")
        if not ffmpeg:
            return False
        args = [ffmpeg] + make_args(path, out, audio_codec(path))
        with self._lock:
            if self._stopped:
                return False
            self._proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.PIPE, **subprocess_flags())
        try:
            _, err = self._proc.communicate(timeout=TIMEOUT)
            if self._proc.returncode != 0:
                log.info("ffmpeg could not copy %s: %s", path, err.decode("utf-8", "replace")[-300:])
            return self._proc.returncode == 0
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.communicate()
            return False
        finally:
            with self._lock:
                self._proc = None
