"""A torrent world on this computer for the tests: .torrent files made here, a tiny tracker, and an aria2c
that shares (seeds) the files, so DISO's aria2 can download them without the internet."""
import hashlib
import http.server
import os
import socket
import socketserver
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlsplit


def bencode(x) -> bytes:
    if isinstance(x, int):
        return b"i%de" % x
    if isinstance(x, str):
        x = x.encode("utf-8")
    if isinstance(x, bytes):
        return b"%d:" % len(x) + x
    if isinstance(x, list):
        return b"l" + b"".join(bencode(v) for v in x) + b"e"
    if isinstance(x, dict):
        return b"d" + b"".join(bencode(k) + bencode(x[k]) for k in sorted(x)) + b"e"
    raise TypeError(type(x))


def make_torrent(root, name, announce, piece=1 << 18) -> bytes:
    """The .torrent of root/name (a file or a folder)."""
    top = os.path.join(root, name)
    if os.path.isdir(top):
        files = []
        for base, dirs, names in os.walk(top):
            dirs.sort()
            for n in sorted(names):
                full = os.path.join(base, n)
                files.append((os.path.relpath(full, top).replace("\\", "/").split("/"), full))
    else:
        files = [(None, top)]
    data = b"".join(open(full, "rb").read() for _, full in files)
    pieces = b"".join(hashlib.sha1(data[i:i + piece]).digest() for i in range(0, len(data), piece))
    info = {"name": name, "piece length": piece, "pieces": pieces}
    if files[0][0] is None:
        info["length"] = len(data)
    else:
        info["files"] = [{"path": parts, "length": os.path.getsize(full)} for parts, full in files]
    return bencode({"announce": announce, "info": info})


class Tracker:
    """Answers every announce with the peers that announced before (compact form)."""

    def __init__(self):
        peers = self.peers = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                q = parse_qs(urlsplit(self.path).query)
                port = int(q.get("port", ["0"])[0])
                me = (self.client_address[0], port)
                if port:
                    peers[me] = time.time()
                compact = b"".join(socket.inet_aton(ip) + p.to_bytes(2, "big") for ip, p in peers if (ip, p) != me)
                body = bencode({"interval": 2, "min interval": 1, "peers": compact})
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        self.httpd = Server(("127.0.0.1", 0), Handler)
        self.announce = f"http://127.0.0.1:{self.httpd.server_address[1]}/announce"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def seed(aria2c, torrent_file, folder, limit="0"):
    """An aria2c that shares the files of torrent_file found in folder (until it is killed); `limit`: its
    upload speed (aria2's --max-upload-limit, "2M" ...), so a test has time to pause."""
    port = free_port()
    return subprocess.Popen([aria2c, f"--dir={folder}", "--check-integrity=true", "--seed-ratio=0.0",
                             f"--max-upload-limit={limit}",
                             "--enable-dht=false", "--bt-enable-lpd=false", "--enable-peer-exchange=false",
                             f"--listen-port={port}", "--console-log-level=error", "--summary-interval=0",
                             "--bt-tracker-interval=1", torrent_file],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
