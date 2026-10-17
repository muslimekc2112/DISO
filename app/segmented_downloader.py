"""
IDM / FDM style multi-connection download engine.

How it works
------------
1. probe()  : asks the server for bytes 0-0 (a 1-byte Range request). A "206 Partial
              Content" answer proves the server supports Range and tells us the full
              file size (Content-Range: bytes 0-0/TOTAL).
2. The file is pre-allocated on disk (name.ext.part) and cut into many small BLOCKS
   (256 KB - 8 MB). Blocks wait in a queue.
3. N worker threads (8/16/32 "connections") each take the next block from the queue,
   download it with its own HTTP Range request and write it at the right offset.
   Because blocks are small, fast connections simply take more blocks, so all
   connections finish at about the same time (this is the trick that makes IDM fast).
4. Every finished block is remembered in name.ext.part.json. If the app is closed or
   the download is paused, the next start skips finished blocks -> real RESUME.
5. A block that fails is retried with back-off (and continues from the byte where it
   stopped). If the server refuses too many parallel connections (HTTP 429/503/403),
   the failing worker retires and the remaining ones finish the job (auto slow-down).
6. If the server has no Range support, a single normal stream is used.
"""
import json
import mimetypes
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from requests.structures import CaseInsensitiveDict

from .utils import sanitize_filename

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CHUNK = 128 * 1024
MIN_BLOCK = 256 * 1024
MAX_BLOCK = 8 * 1024 * 1024
MAX_TRIES = 6
TIMEOUT = (12, 25)  # (connect, read) seconds
FATAL_STATUS = {400, 401, 404, 410}  # retrying these answers is pointless


class DownloadStopped(Exception):
    """Raised by run() when the download was paused or cancelled on purpose."""

    def __init__(self, reason: str = "pause"):
        super().__init__(reason)
        self.reason = reason


class DownloadError(Exception):
    pass


@dataclass
class ProbeResult:
    url: str
    final_url: str
    total: int = 0
    resumable: bool = False
    filename: str = "download"
    content_type: str = ""


# ------------------------------------------------------------------------------ helpers
def build_headers(extra=None) -> CaseInsensitiveDict:
    h = CaseInsensitiveDict({"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "identity"})
    for k, v in (extra or {}).items():
        if str(k).lower() in ("range", "accept-encoding", "host", "content-length"):
            continue
        h[k] = v
    return h


def make_session(pool: int = 1) -> requests.Session:
    s = requests.Session()
    ad = HTTPAdapter(pool_connections=pool, pool_maxsize=pool, max_retries=0)
    s.mount("http://", ad)
    s.mount("https://", ad)
    return s


def filename_from_response(headers, final_url: str, content_type: str = "") -> str:
    cd = headers.get("Content-Disposition", "") or ""
    name = ""
    m = re.search(r"filename\*\s*=\s*(?:[\w-]+'[^']*')?([^;]+)", cd, re.I)
    if m:
        name = unquote(m.group(1).strip().strip('"'))
    else:
        m = re.search(r'filename\s*=\s*"?([^";]+)"?', cd, re.I)
        if m:
            name = unquote(m.group(1).strip())
    if not name:
        name = unquote(os.path.basename(urlparse(final_url).path))
    name = sanitize_filename(name, 200) if name else "download"
    if not os.path.splitext(name)[1]:
        ct = (content_type or "").split(";")[0].strip().lower()
        if ct and ct != "application/octet-stream":
            ext = mimetypes.guess_extension(ct) or ""
            name += ".html" if ext == ".htm" else ext
    return name


def probe(url: str, headers=None, timeout=20) -> ProbeResult:
    """Find out size, Range support, real URL (after redirects) and file name."""
    base = build_headers(headers)

    def fetch(with_range: bool):
        h = CaseInsensitiveDict(base)
        if with_range:
            h["Range"] = "bytes=0-0"
        return requests.get(url, headers=h, stream=True, timeout=timeout, allow_redirects=True)

    r = fetch(True)
    if r.status_code >= 400:  # some servers reject Range on the first request
        r.close()
        r = fetch(False)
    try:
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "") or ""
        total, resumable = 0, False
        if r.status_code == 206:
            m = re.search(r"/(\d+)\s*$", r.headers.get("Content-Range", "") or "")
            if m:
                total = int(m.group(1))
                resumable = total > 0
        else:
            total = int(r.headers.get("Content-Length", 0) or 0)
        return ProbeResult(url, r.url, total, resumable,
                           filename_from_response(r.headers, r.url, ct), ct)
    finally:
        r.close()


# ---------------------------------------------------------------------------- speed limit
class RateLimiter:
    """Global download speed limit shared by every connection of every download.

    A token bucket: each received chunk is charged to the bucket and the caller sleeps
    for as long as the bucket is in debt. rate = 0 means unlimited."""

    def __init__(self):
        self.rate = 0.0           # bytes per second
        self.tokens = 0.0
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def set_rate(self, bytes_per_second):
        with self.lock:
            self.rate = max(0.0, float(bytes_per_second or 0))
            self.tokens = 0.0
            self.last = time.monotonic()

    def consume(self, n, stop_event=None):
        if self.rate <= 0:
            return
        with self.lock:
            rate = self.rate
            now = time.monotonic()
            self.tokens = min(self.tokens + (now - self.last) * rate, rate)  # burst: 1 second
            self.last = now
            self.tokens -= n
            wait = -self.tokens / rate if self.tokens < 0 else 0.0
        if wait > 0:
            if stop_event is not None:
                stop_event.wait(wait)
            else:
                time.sleep(wait)


LIMITER = RateLimiter()


# ------------------------------------------------------------------------------- engine
class FastDownloader:
    def __init__(self, url, dest, connections=16, headers=None, on_progress=None, probe_result=None,
                 limited=True):
        self.url = url.strip()
        self.limiter = LIMITER if limited else None  # tools the app downloads itself pass False
        self.dest = dest
        self.connections = max(1, int(connections))
        self.extra_headers = dict(headers or {})
        self.headers = build_headers(self.extra_headers)
        self.on_progress = on_progress or (lambda *a, **k: None)
        self.probe_result = probe_result

        self.stop_event = threading.Event()
        self.stop_reason = None
        self.lock = threading.Lock()
        self.downloaded = 0
        self.total = 0
        self.resumable = False
        self.error = None
        self.active = 0
        self.url_now = self.url

        self._todo = deque()
        self._done = set()
        self._blocks = []
        self._block = 0
        self._last_err = ""

    # ------------------------------------------------------------------ public control
    def stop(self, reason: str = "pause"):
        self.stop_reason = reason
        self.stop_event.set()

    @staticmethod
    def cleanup(dest: str):
        for p in (dest + ".part", dest + ".part.json", dest + ".part.json.tmp"):
            try:
                os.remove(p)
            except OSError:
                pass

    # ----------------------------------------------------------------------- meta file
    def _save_meta(self):
        if not self._blocks:
            return
        with self.lock:
            snap = sorted(self._done)
        data = {"total": self.total, "block": self._block, "done": snap}
        tmp = self.dest + ".part.json.tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.dest + ".part.json")
        except OSError:
            pass

    def _prepare_blocks(self, tmp):
        total = self.total
        block = max(MIN_BLOCK, min(MAX_BLOCK, -(-total // (self.connections * 4))))
        done = set()
        meta = self.dest + ".part.json"
        reuse = False
        if os.path.exists(tmp) and os.path.exists(meta) and os.path.getsize(tmp) == total:
            try:
                with open(meta) as f:
                    m = json.load(f)
                if m.get("total") == total and int(m.get("block", 0)) > 0:
                    block = int(m["block"])
                    done = set(int(i) for i in m.get("done", []))
                    reuse = True
            except Exception:
                reuse = False
        if not reuse:
            done = set()
            with open(tmp, "wb") as f:
                f.truncate(total)
        n = -(-total // block)
        self._block = block
        self._blocks = [(i * block, min(total - 1, (i + 1) * block - 1)) for i in range(n)]
        done = {i for i in done if 0 <= i < n}
        self._done = done
        self.downloaded = sum(self._blocks[i][1] - self._blocks[i][0] + 1 for i in done)
        self._todo = deque(i for i in range(n) if i not in done)

    # ---------------------------------------------------------------------- workers
    def _throttle(self, n):
        if self.limiter is not None:
            self.limiter.consume(n, self.stop_event)

    def _exit_locked(self):
        """Called with self.lock held by every worker when it leaves."""
        self.active -= 1
        if self.active == 0 and self._todo and not self.stop_event.is_set() and self.error is None:
            self.error = DownloadError(self._last_err or "Connection failed")
            self.stop_event.set()

    def _fetch_block(self, session, fh, start, end):
        """Returns 'ok', 'stopped' or 'failed'."""
        pos, tries, counted = start, 0, 0
        while pos <= end:
            if self.stop_event.is_set():
                return "stopped", counted
            before = pos
            try:
                h = CaseInsensitiveDict(self.headers)
                h["Range"] = f"bytes={pos}-{end}"
                r = session.get(self.url_now, headers=h, stream=True, timeout=TIMEOUT)
                try:
                    if r.status_code != 206:
                        if r.status_code == 200:  # server ignores Range: retrying cannot help
                            raise DownloadError("Sunucu parçalı indirmeyi (Range) desteklemiyor")
                        if r.status_code in FATAL_STATUS:
                            raise DownloadError(f"HTTP {r.status_code}: dosya bulunamadı veya erişim reddedildi")
                        raise IOError(f"HTTP {r.status_code}")
                    fh.seek(pos)
                    for chunk in r.iter_content(CHUNK):
                        if self.stop_event.is_set():
                            return "stopped", counted
                        if not chunk:
                            continue
                        room = end - pos + 1
                        if len(chunk) > room:
                            chunk = chunk[:room]
                        fh.write(chunk)
                        pos += len(chunk)
                        counted += len(chunk)
                        with self.lock:
                            self.downloaded += len(chunk)
                        self._throttle(len(chunk))
                        if pos > end:
                            break
                finally:
                    r.close()
                tries = 0 if pos > before else tries + 1
            except DownloadError:  # fatal answer from the server: do not retry
                raise
            except OSError as e:
                if isinstance(e, (PermissionError, FileNotFoundError)) or getattr(e, "errno", None) in (28,):
                    raise  # disk problems are not retryable
                self._last_err = str(e)
                tries += 1
            except Exception as e:
                self._last_err = str(e)
                tries += 1
            if pos <= end:
                if tries > MAX_TRIES:
                    return "failed", counted
                if tries:
                    self.stop_event.wait(min(0.5 * 2 ** tries, 4))
        return "ok", counted

    def _block_worker(self, tmp):
        session = make_session(1)
        try:
            with open(tmp, "r+b") as fh:
                while True:
                    with self.lock:
                        if self.stop_event.is_set() or not self._todo:
                            self._exit_locked()
                            return
                        idx = self._todo.popleft()
                    status, counted = self._fetch_block(session, fh, *self._blocks[idx])
                    with self.lock:
                        if status == "ok":
                            self._done.add(idx)
                            continue
                        if status == "failed":
                            self.downloaded -= counted  # will be downloaded again by someone else
                            self._todo.appendleft(idx)
                            self._exit_locked()
                            return
                        # stopped
                        self._exit_locked()
                        return
        except Exception as e:  # disk full, permission denied ...
            with self.lock:
                self.error = e
                self.stop_event.set()
                self._exit_locked()
        finally:
            session.close()

    def _single_worker(self, tmp):
        session = make_session(1)
        try:
            r = session.get(self.url_now, headers=self.headers, stream=True, timeout=TIMEOUT)
            try:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(CHUNK):
                        if self.stop_event.is_set():
                            return
                        if chunk:
                            f.write(chunk)
                            with self.lock:
                                self.downloaded += len(chunk)
                            self._throttle(len(chunk))
            finally:
                r.close()
        except Exception as e:
            self.error = e
            self.stop_event.set()
        finally:
            session.close()

    # -------------------------------------------------------------------------- run
    def run(self) -> str:
        """Download (blocking). Returns the final file path."""
        os.makedirs(os.path.dirname(self.dest) or ".", exist_ok=True)
        if self.stop_event.is_set():
            raise DownloadStopped(self.stop_reason or "pause")

        pr = self.probe_result or probe(self.url, self.extra_headers)
        self.url_now = pr.final_url
        self.total = pr.total
        self.resumable = pr.resumable
        tmp = self.dest + ".part"

        threads = []
        if pr.resumable and pr.total > 0:
            self._prepare_blocks(tmp)
            n = max(0, min(self.connections, len(self._todo)))
            self.active = n
            threads = [threading.Thread(target=self._block_worker, args=(tmp,), daemon=True) for _ in range(n)]
        else:
            self.active = 1
            threads = [threading.Thread(target=self._single_worker, args=(tmp,), daemon=True)]

        for t in threads:
            t.start()
        self._monitor(threads)
        for t in threads:
            t.join()

        # ---- how did it end?
        if self.error is not None:
            if not self.resumable:
                self.cleanup(self.dest)
            else:
                self._save_meta()
            raise self.error if isinstance(self.error, Exception) else DownloadError(str(self.error))
        if self.stop_event.is_set():
            if self.stop_reason == "cancel" or not self.resumable:
                self.cleanup(self.dest)
            else:
                self._save_meta()
            raise DownloadStopped(self.stop_reason or "pause")

        size = os.path.getsize(tmp) if os.path.exists(tmp) else -1
        if self.total and size != self.total:
            raise DownloadError(f"Size mismatch ({size} of {self.total} bytes)")
        os.replace(tmp, self.dest)
        try:
            os.remove(self.dest + ".part.json")
        except OSError:
            pass
        self.on_progress(self.downloaded, self.total, 0.0, 0.0, 0)
        return self.dest

    def _monitor(self, threads):
        window = deque(maxlen=12)
        last_save = time.time()
        while any(t.is_alive() for t in threads):
            time.sleep(0.25)
            now = time.time()
            with self.lock:
                d, act = self.downloaded, self.active
            window.append((now, d))
            speed = 0.0
            if len(window) >= 2:
                dt = window[-1][0] - window[0][0]
                if dt > 0:
                    speed = max(0.0, (window[-1][1] - window[0][1]) / dt)
            eta = (self.total - d) / speed if speed > 0 and self.total else None
            self.on_progress(d, self.total, speed, eta, act)
            if self._blocks and now - last_save > 2:
                self._save_meta()
                last_save = now
