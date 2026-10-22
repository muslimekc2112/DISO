"""📱 Send a link from the phone: DISO shows a QR code; the phone (on the same Wi-Fi) opens a small page
from DISO and the links pasted there download on the computer.

A tiny web server listens on the local network while it is on. Its address carries a random key, so only a
phone that read the QR code can add downloads; other requests are refused. Nothing leaves the local network."""
import html
import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .logs import log

MAX_BODY = 64 * 1024
HOST = "0.0.0.0"                  # every network of this PC (the tests listen on 127.0.0.1 only)

TEXTS = {
    "tr": {"title": "DISO'ya gönder", "hint": "Linki yapıştır, bilgisayardaki DISO indirsin.",
           "auto": "Otomatik", "video": "Video (MP4)", "audio": "Müzik (MP3)", "send": "⬇ İndir",
           "sent": "Gönderildi ✓ DISO indiriyor.", "none": "Link bulamadım.", "fail": "Gönderemedim; DISO açık mı?",
           "paste": "📋 Yapıştır"},
    "en": {"title": "Send to DISO", "hint": "Paste a link; DISO downloads it on the computer.",
           "auto": "Automatic", "video": "Video (MP4)", "audio": "Music (MP3)", "send": "⬇ Download",
           "sent": "Sent ✓ DISO is downloading.", "none": "No link found.", "fail": "Could not send; is DISO open?",
           "paste": "📋 Paste"},
}

PAGE = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#16121c;color:#eee}}
main{{max-width:520px;margin:0 auto;padding:22px 16px}}
h1{{font-size:22px;margin:4px 0 6px}} p{{color:#aaa;margin:0 0 14px}}
textarea{{width:100%;box-sizing:border-box;min-height:120px;border-radius:12px;border:1px solid #444;
background:#221c2b;color:#eee;padding:12px;font-size:16px}}
.row{{display:flex;gap:8px;margin:10px 0}} select,button{{font-size:16px;border-radius:10px;border:0;padding:12px}}
select{{flex:1;background:#221c2b;color:#eee;border:1px solid #444}}
button{{background:#b35ec9;color:#fff;font-weight:600}} button.alt{{background:#332a3d}}
#msg{{margin-top:12px;min-height:22px}}
</style></head><body><main>
<h1>🎵 {title}</h1><p>{hint}</p>
<textarea id="t" placeholder="https://"></textarea>
<div class="row"><select id="k"><option value="auto">{auto}</option><option value="video">{video}</option>
<option value="audio">{audio}</option></select><button class="alt" id="p">{paste}</button></div>
<button id="s" style="width:100%">{send}</button><div id="msg"></div>
<script>
const key = new URLSearchParams(location.search).get("k");
const msg = (t) => document.getElementById("msg").textContent = t;
document.getElementById("p").onclick = async () => {{
  try {{ document.getElementById("t").value = await navigator.clipboard.readText(); }} catch (e) {{}}
}};
document.getElementById("s").onclick = async () => {{
  const text = document.getElementById("t").value;
  try {{
    const r = await fetch("/add?k=" + encodeURIComponent(key), {{method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{text, kind: document.getElementById("k").value}})}});
    const j = await r.json();
    if (j.added > 0) {{ msg({sent}); document.getElementById("t").value = ""; }} else msg({none});
  }} catch (e) {{ msg({fail}); }}
}};
</script></main></body></html>"""


def local_address() -> str:
    """This computer's address on the local network (what the phone can reach)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))        # nothing is sent: it only picks the network that would be used
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def page(lang="tr") -> str:
    t = TEXTS.get(lang, TEXTS["tr"])
    js = {k: json.dumps(v) for k, v in t.items() if k in ("sent", "none", "fail")}
    plain = {k: html.escape(v) for k, v in t.items() if k not in js}
    return PAGE.format(lang=lang, **plain, **js)


class PhoneLink:
    """start() -> the address for the QR code; on_links(text, kind) is called for every page that sends
    (on the server's thread: the window hands it over to its own)."""

    def __init__(self, on_links, language=lambda: "tr", port=0):
        self.on_links = on_links
        self.language = language
        self.port = port
        self.key = secrets.token_urlsafe(12)
        self.server = None

    @property
    def running(self) -> bool:
        return self.server is not None

    def url(self) -> str:
        return f"http://{local_address()}:{self.server.server_address[1]}/?k={self.key}" if self.server else ""

    def start(self) -> str:
        if self.server is None:
            link = self

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *a):
                    pass

                def _key_ok(self):
                    got = parse_qs(urlsplit(self.path).query).get("k", [""])[0]
                    return secrets.compare_digest(got, link.key)

                def _send(self, code, body, kind="application/json"):
                    data = body.encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", f"{kind}; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)

                def do_GET(self):
                    if urlsplit(self.path).path != "/" or not self._key_ok():
                        return self._send(403, '{"error": "forbidden"}')
                    self._send(200, page(link.language()), "text/html")

                def do_POST(self):
                    if urlsplit(self.path).path != "/add" or not self._key_ok():
                        return self._send(403, '{"error": "forbidden"}')
                    try:
                        size = int(self.headers.get("Content-Length") or 0)
                        if size > MAX_BODY:
                            return self._send(413, '{"error": "too big"}')
                        data = json.loads(self.rfile.read(size) or b"{}")
                        text = str(data.get("text") or "")[:20000]
                        kind = data.get("kind") if data.get("kind") in ("auto", "video", "audio") else "auto"
                    except (ValueError, TypeError):
                        return self._send(400, '{"error": "bad request"}')
                    from .utils import extract_urls
                    urls = extract_urls(text)
                    if urls:
                        link.on_links(urls, kind)
                    self._send(200, json.dumps({"added": len(urls)}))

            self.server = ThreadingHTTPServer((HOST, self.port), Handler)
            self.server.daemon_threads = True
            threading.Thread(target=self.server.serve_forever, daemon=True, name="phone-link").start()
            log.info("phone link on port %s", self.server.server_address[1])
        return self.url()

    def stop(self):
        server, self.server = self.server, None
        if server is not None:
            server.shutdown()
            server.server_close()
            self.key = secrets.token_urlsafe(12)            # an old QR code no longer works


def qr_image(url, scale=8):
    """The QR code of `url` as a PIL image."""
    import io

    import segno
    from PIL import Image
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=scale, border=2, dark="#000000", light="#ffffff")
    buf.seek(0)
    return Image.open(buf).convert("RGB")
