"""
Local bridge for the browser extension (and for the "one window only" check).

A tiny HTTP server on 127.0.0.1 only. The extension sends it the links it catches:

  GET  /ping    -> {"app": "DISO", "version": ...}         (is the app running?)
  GET  /status  -> {"active": n, "queued": n, "speed": bytes/s ...}
  POST /add     -> {"urls": [...], "referer", "userAgent", "cookies", "kind"}
  POST /show    -> brings the window to the front (a second launch uses this)

Safety: a web page must not be able to start downloads. Browsers always put an Origin header on
cross-site POST requests, so POST is refused unless the Origin is a browser *extension* (or there
is no Origin at all: a local program). The Host header must be 127.0.0.1 / localhost, which
stops DNS-rebinding tricks. /add can also be switched off in the settings.
"""
import http.server
import json
import socketserver
import threading
from urllib.parse import urlsplit

import requests

from . import __version__
from .utils import is_url

APP_ID = "DISO"
DEFAULT_PORT = 17653
MAX_BODY = 1_000_000
MAX_URLS = 500
KINDS = ("auto", "video", "audio", "file")
_EXTENSION_ORIGINS = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


def origin_allowed(origin) -> bool:
    """No Origin = a local program (curl, our own second launch). Otherwise only extensions."""
    return not origin or origin.startswith(_EXTENSION_ORIGINS)


def host_allowed(host, port) -> bool:
    return (host or "") in (f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost")


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False   # a busy port must really fail: that is how we know another copy runs
    request_queue_size = 32


class Bridge:
    """api must offer: add(urls, extra, kind) -> dict, status() -> dict, show() -> None,
    and an `add_enabled` attribute; extension_seen() (optional) is called when an extension talks to us."""

    def __init__(self, api, port: int = DEFAULT_PORT):
        self.api = api
        self.port = int(port)
        self._httpd = None

    def start(self) -> bool:
        """False if the port is taken (probably another copy of the app)."""
        bridge = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            # ---------------------------------------------------------------- plumbing
            def _origin_ok(self):
                origin = self.headers.get("Origin")
                if not origin_allowed(origin) or not host_allowed(self.headers.get("Host"), bridge.port):
                    self._send(403, {"error": "forbidden"})
                    return False
                if origin and origin.startswith(_EXTENSION_ORIGINS):
                    seen = getattr(bridge.api, "extension_seen", None)      # the extension is in a browser
                    if seen:
                        seen()
                return True

            def _send(self, status, payload=None):
                body = b"" if payload is None else json.dumps(payload).encode("utf-8")
                self.send_response(status)
                origin = self.headers.get("Origin")
                if origin and origin_allowed(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _json_body(self):
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    return None
                if n <= 0 or n > MAX_BODY:
                    return None
                try:
                    data = json.loads(self.rfile.read(n).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    return None
                return data if isinstance(data, dict) else None

            # ----------------------------------------------------------------- routes
            def do_OPTIONS(self):  # CORS pre-flight of the extension
                origin = self.headers.get("Origin")
                if not origin_allowed(origin) or not origin or not host_allowed(self.headers.get("Host"), bridge.port):
                    return self._send(403, {"error": "forbidden"})
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-HI-Client")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Access-Control-Max-Age", "600")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                if not self._origin_ok():
                    return
                path = urlsplit(self.path).path
                if path == "/ping":
                    language = getattr(bridge.api, "language", None)
                    return self._send(200, {"app": APP_ID, "version": __version__,
                                            "add": bool(bridge.api.add_enabled),
                                            "language": language() if callable(language) else ""})
                if path == "/status":
                    return self._send(200, bridge.api.status())
                self._send(404, {"error": "not found"})

            def do_POST(self):
                if not self._origin_ok():
                    return
                path = urlsplit(self.path).path
                if path == "/show":
                    bridge.api.show()
                    return self._send(200, {"ok": True})
                if path != "/add":
                    return self._send(404, {"error": "not found"})
                if not bridge.api.add_enabled:
                    return self._send(403, {"error": "disabled"})
                data = self._json_body()
                urls = data.get("urls") if data else None
                if not isinstance(urls, list):
                    return self._send(400, {"error": "urls required"})
                urls = [u for u in urls[:MAX_URLS] if isinstance(u, str) and is_url(u)]
                if not urls:
                    return self._send(400, {"error": "no valid http(s) link"})
                kind = data.get("kind") if data.get("kind") in KINDS else None
                extra = {"referer": _text(data.get("referer"), 2000),
                         "user_agent": _text(data.get("userAgent"), 500),
                         "cookie": _text(data.get("cookies"), 8000)}
                self._send(200, bridge.api.add(urls, extra, kind))

        try:
            self._httpd = _Server(("127.0.0.1", self.port), Handler)
        except OSError:
            return False
        self.port = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        return True

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


def _text(value, limit):
    return value[:limit] if isinstance(value, str) else ""


# ----------------------------------------------------------- "is the app already running?"
def _local(url_path, port, method="GET"):
    url = f"http://127.0.0.1:{port}{url_path}"
    kw = {"timeout": 1.5, "proxies": {"http": None, "https": None}}
    return requests.post(url, data=b"{}", **kw) if method == "POST" else requests.get(url, **kw)


def port_taken(port: int) -> bool:
    """Does something listen on 127.0.0.1:port? Found out by trying to take the port ourselves: instant. (Asking
    a port where nothing listens takes Windows 1.5–2 seconds to give up: that was every start of DISO.)"""
    import socket
    if not port:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", int(port)))
        except OSError:
            return True
    return False


def ping_existing(port: int = DEFAULT_PORT) -> bool:
    """True if a copy of this app already listens on `port`."""
    if not port_taken(port):
        return False                                     # nothing there: no need to wait for an answer
    try:
        r = _local("/ping", port)
        return r.status_code == 200 and r.json().get("app") == APP_ID
    except Exception:
        return False


def show_existing(port: int = DEFAULT_PORT) -> bool:
    """Ask the running copy to bring its window to the front."""
    try:
        return _local("/show", port, "POST").status_code == 200
    except Exception:
        return False
