"""
Shared test setup.

* every test gets its own empty "home" folder, so nothing touches the real
  ~/.hizli_indirici (settings, download list, updated packages, FFmpeg)
* `server` is a local HTTP server that behaves like the awkward servers the downloader
  must survive: no Range support, connections that drop, a connection limit, 404 ...
  It also plays PyPI for the updater tests. No test needs the internet.
"""
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import time
import uuid

import pytest

pytest_plugins = ["media_support", "ui_support"]   # shared media fixtures (media, served, stand_in)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import updater  # noqa: E402
from app.segmented_downloader import LIMITER  # noqa: E402
from app.utils import setup_environment  # noqa: E402

setup_environment()  # the project's ffmpeg/ folder is found like in the real app


# ------------------------------------------------------------------------- isolation
@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))  # restored after the test
    return home


@pytest.fixture(autouse=True)
def clean_globals():
    """Undo what a test did to process-wide state (speed limit, import hook, modules)."""
    meta_path = list(sys.meta_path)
    modules = set(sys.modules)
    yield
    LIMITER.set_rate(0)
    from app import segmented_downloader
    segmented_downloader.set_proxy("")
    import logging.handlers
    from app.logs import log
    for h in list(log.handlers):          # the log file belongs to the test's private home
        if isinstance(h, logging.handlers.RotatingFileHandler):
            log.removeHandler(h)
            h.close()
    sys.meta_path[:] = meta_path
    updater._overrides.clear()
    updater._active.clear()
    updater._finder = None
    updater._instance = None
    updater._ytdlp_checked = False
    updater._started = False
    updater.ready.clear()
    while not updater.notices.empty():
        updater.notices.get_nowait()
    for name in set(sys.modules) - modules:
        if name.startswith(("fakepkg_", "yt_dlp")):
            del sys.modules[name]


def dump_threads():
    """Where every thread is right now (for a failing test's message)."""
    import traceback
    names = {t.ident: t.name for t in threading.enumerate()}
    return "\n".join(f"--- {names.get(i, i)}\n" + "".join(traceback.format_stack(f)[-6:])
                     for i, f in sys._current_frames().items())


def wait_for(cond, timeout=15.0, interval=0.05):
    """Poll until cond() is truthy; returns its value (or the last falsy one at timeout)."""
    end = time.time() + timeout
    value = cond()
    while not value and time.time() < end:
        time.sleep(interval)
        value = cond()
    return value


# ------------------------------------------------------------------------- test server
class _State:
    def __init__(self):
        self.files = {}      # name -> bytes
        self.types = {}      # name -> content type
        self.pypi = {}       # package -> JSON document
        self.hits = {}       # name -> number of requests
        self.sent = {}       # name -> body bytes written
        self.lock = threading.Lock()
        self.limit = 3       # connections the "limit" mode allows at once
        self.active = 0
        self.flaky_counter = 0
        self.fail_requests = 0   # the next N requests get no answer at all (network down)
        self.seen = {}           # name -> headers of the last request for it


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, status, body=b"", headers=None):
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        st = self.server.state
        path = self.path.split("?")[0]
        mode, _, name = path.lstrip("/").partition("/")
        with st.lock:
            st.hits[name] = st.hits.get(name, 0) + 1
            st.seen[name] = {k.lower(): v for k, v in self.headers.items()}
            if st.fail_requests > 0 and mode != "pypi":
                st.fail_requests -= 1
                self.close_connection = True   # hang up without an answer
                return
        if mode == "auth" and (self.headers.get("Referer") != "http://site.example/page"
                               or "sid=1" not in (self.headers.get("Cookie") or "")):
            return self._reply(403)
        if mode == "pypi":
            doc = st.pypi.get(name.removesuffix("/json"))
            if doc is None:
                return self._reply(404)
            return self._reply(200, json.dumps(doc).encode(), {"Content-Type": "application/json"})
        data = st.files.get(name)
        if data is None:
            return self._reply(404)
        if mode == "limit":
            with st.lock:
                if st.active >= st.limit:
                    return self._reply(429)
                st.active += 1
            try:
                return self._serve(st, name, data, mode)
            finally:
                with st.lock:
                    st.active -= 1
        return self._serve(st, name, data, mode)

    def _serve(self, st, name, data, mode):
        headers = {"Content-Type": st.types.get(name, "application/octet-stream")}
        if mode == "disp":
            headers["Content-Disposition"] = "attachment; filename*=UTF-8''g%C3%BCzel%20dosya.zip"
        rng = re.match(r"bytes=(\d+)-(\d*)$", self.headers.get("Range", "") or "")
        probe = bool(rng) and rng.group(1) == "0" and rng.group(2) == "0"
        if not rng or mode == "norange" or (mode == "noblock" and not probe):
            return self._send_body(st, name, 200, data, headers, len(data), mode)
        start = int(rng.group(1))
        end = min(int(rng.group(2)) if rng.group(2) else len(data) - 1, len(data) - 1)
        chunk = data[start:end + 1]
        headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
        if mode == "flaky" and not probe:
            with st.lock:
                st.flaky_counter += 1
                drop = st.flaky_counter % 3 == 0
            if drop:  # promise the whole block, send half of it, hang up
                self.send_response(206)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(chunk)))
                self.end_headers()
                self.wfile.write(chunk[:len(chunk) // 2])
                self.wfile.flush()
                self.close_connection = True
                return
        return self._send_body(st, name, 206, chunk, headers, len(chunk), mode)

    def _send_body(self, st, name, status, body, headers, length, mode):
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        try:
            for i in range(0, len(body), 65536):
                self.wfile.write(body[i:i + 65536])
                with st.lock:
                    st.sent[name] = st.sent.get(name, 0) + len(body[i:i + 65536])
                if mode == "limit":
                    time.sleep(0.01)  # keep connections open long enough to overlap
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 256  # the default (5) drops connections when 16-32 arrive at once


class TestServer:
    """Handle the tests use. Modes are the first path part: f (normal), norange, noblock,
    flaky, limit, disp. Example: server.url("flaky", name)."""
    __test__ = False  # not a test class, despite the name

    def __init__(self):
        self.state = _State()
        self.httpd = _Server(("127.0.0.1", 0), _Handler)
        self.httpd.state = self.state
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def add(self, data, ext=".bin", content_type=None, name=None):
        name = name or f"{uuid.uuid4().hex[:10]}{ext}"
        self.state.files[name] = data
        if content_type:
            self.state.types[name] = content_type
        return name

    def file(self, size, ext=".bin"):
        """Add a file of random bytes; returns (name, data)."""
        data = os.urandom(size)
        return self.add(data, ext), data

    def url(self, mode, name):
        return f"{self.base}/{mode}/{name}"

    def sent(self, name):
        return self.state.sent.get(name, 0)

    def hits(self, name):
        return self.state.hits.get(name, 0)

    @property
    def pypi_url(self):
        return self.base + "/pypi/{}/json"


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    """A very small HTTP proxy: forwards absolute-URI GET requests (what requests sends)."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        import requests
        self.server.hits.append(self.path)
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() in ("range", "referer", "cookie", "user-agent")}
        try:
            r = requests.get(self.path, headers=headers, stream=True, timeout=10,
                             proxies={"http": None, "https": None})
        except Exception:  # noqa: BLE001
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = r.content
        self.send_response(r.status_code)
        for k in ("Content-Range", "Content-Type", "Content-Disposition"):
            if k in r.headers:
                self.send_header(k, r.headers[k])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class TestProxy:
    __test__ = False

    def __init__(self):
        self.httpd = _Server(("127.0.0.1", 0), _ProxyHandler)
        self.httpd.hits = []
        self.hits = self.httpd.hits
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()


@pytest.fixture
def proxy():
    """A local proxy. The speed of the proxy setting is reset after the test."""
    from app import segmented_downloader
    p = TestProxy()
    yield p
    segmented_downloader.set_proxy("")
    p.stop()


@pytest.fixture(scope="session")
def _server():
    s = TestServer()
    yield s
    s.httpd.shutdown()


@pytest.fixture
def server(_server):
    _server.state.limit = 3
    _server.state.active = 0
    _server.state.flaky_counter = 0
    _server.state.fail_requests = 0
    return _server
