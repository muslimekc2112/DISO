"""1.2 downloads from any site: the extension finds the streams a page plays (with the player's own headers) and
counts them on its button, the popup sends the chosen ones (quality, subtitles), and DISO downloads a stream
that only answers its player — also when the page itself is not a video site (it falls back to the stream),
names it after the page, saves and embeds the subtitles, and goes on after a pause."""
import http.server
import os
import socketserver
import subprocess
import threading
import time

import pytest
from test_extension import app, needs_node, run  # noqa: F401 - the bridge fixture

from app import bridge, jobs, utils
from app.models import Item

PLAYER = "http://player.example/embed/77"


# ------------------------------------------------------------------------------ the extension
@needs_node
def test_the_extension_finds_what_the_page_plays_and_sends_it_with_the_players_headers(app):  # noqa: F811
    api, b = app
    data = run(b.port, "sniff")
    answer, log = data["answer"], data["log"]
    found = answer["found"]
    assert [m["url"] for m in found["media"]] == ["http://cdn.example/hls/master.m3u8?token=a",
                                                  "http://cdn.example/hls/720/index.m3u8?token=a"]
    assert found["subs"] == [{"url": "http://cdn.example/subs/turkce.vtt", "lang": "tr", "ext": "vtt"}]
    assert found["title"] == "Güzel Bir Film İzle"
    first = found["media"][0]
    assert (first["referer"], first["origin"], first["cookies"]) == (PLAYER, "http://player.example", "pl=1")
    assert "extraHeaders" in log["webRequestExtra"]                                  # Chrome gives Referer / Cookie
    assert "9:1" in log["badge"] and "9:2" in log["badge"] and "4:1" in log["badge"]  # counted per tab
    assert answer["sent"]["ok"]
    sent = [a for a in api.added if a["kind"] == "video" and "title" in a["extra"]]
    assert [a["extra"]["title"] for a in sent[:2]] == ["Güzel Bir Film İzle (1)", "Güzel Bir Film İzle (2)"]
    extra = sent[0]["extra"]
    assert sent[0]["urls"] == ["http://cdn.example/hls/master.m3u8?token=a"]
    assert extra["referer"] == PLAYER and extra["cookie"] == "pl=1" and extra["headers"] == {"Origin": "http://player.example"}
    assert extra["quality"] == "720p"
    assert extra["sub_urls"] == [{"url": "http://cdn.example/subs/turkce.vtt", "lang": "tr", "ext": "vtt"}]
    page = api.added[-1]                                             # MP4 of the page: the page, its streams as the way out
    assert page["urls"] == ["http://films.example/watch/film-1"] and page["kind"] == "video"
    assert [a["url"] for a in page["extra"]["alternates"]] == ["http://cdn.example/hls/master.m3u8?token=a",
                                                                 "http://cdn.example/hls/720/index.m3u8?token=a"]
    assert page["extra"]["alternates"][0]["referer"] == PLAYER
    assert page["extra"]["title"] == "Güzel Bir Film İzle"
    assert answer["after"]["media"] == [] and "9:" in log["badge"]   # another page in the tab: forgotten


@needs_node
def test_finding_videos_can_be_switched_off(app):  # noqa: F811
    api, b = app
    assert run(b.port, "sniff-off")["answer"]["media"] == []


def test_the_bridge_checks_every_part_of_a_found_video():
    extra = bridge.media_extra({"url": "http://cdn/a.m3u8", "title": "  Film \n Adı ", "referer": "http://p/",
                                "headers": {"Origin": "http://p", "Host": "evil", "Cookie": "x=1", "X-Requested-With": "x"},
                                "subs": [{"url": "http://cdn/tr.srt", "lang": "tr", "ext": "SRT"}, {"url": "javascript:1"}, "bad"],
                                "quality": "9999p"}, {"userAgent": "UA", "quality": "1080p"})
    assert extra["title"] == "Film Adı" and extra["user_agent"] == "UA" and extra["referer"] == "http://p/"
    assert extra["headers"] == {"Origin": "http://p", "X-Requested-With": "x"}    # never Host / Cookie this way
    assert extra["sub_urls"] == [{"url": "http://cdn/tr.srt", "lang": "tr", "ext": "srt"}]
    assert "quality" not in extra                                                  # an unknown quality is dropped
    page = bridge.media_extra({"alternates": [{"url": "http://cdn/x.m3u8", "cookies": "a=1"}, {"url": "ftp://no"}, 5]}, {})
    assert page["alternates"] == [{"url": "http://cdn/x.m3u8", "referer": "", "user_agent": "", "cookie": "a=1",
                                   "headers": {}}]
    assert bridge.media_extra({}, {}) == {"referer": "", "user_agent": "", "cookie": ""}


def test_an_item_keeps_its_streams_but_not_their_logins():
    it = Item("http://films.example/watch/1", kind="video")
    it.name_hint = "Film"
    it.alternates = [{"url": "http://cdn/x.m3u8", "referer": PLAYER, "cookie": "secret=1", "headers": {"Origin": "http://p"}}]
    it.sub_urls = [{"url": "http://cdn/tr.vtt", "lang": "tr", "ext": "vtt"}]
    saved = it.to_dict()
    assert saved["alternates"] == [{"url": "http://cdn/x.m3u8", "referer": PLAYER, "headers": {"Origin": "http://p"}}]
    again = Item.from_dict(saved)
    assert again.name_hint == "Film" and again.sub_urls == it.sub_urls
    assert again.use_alternate() and again.url == "http://cdn/x.m3u8" and again.referer == PLAYER
    assert again.request_headers() == {"Referer": PLAYER, "Origin": "http://p"}
    assert not again.use_alternate()
    broken = Item.from_dict({"url": "http://x", "alternates": "nonsense", "sub_urls": [5], "header_extra": [1], "name_hint": 3})
    assert (broken.alternates, broken.sub_urls, broken.header_extra, broken.name_hint) == ([], [], {}, "")


# ------------------------------------------------------------------------------ a site only its player can read
class Site(http.server.SimpleHTTPRequestHandler):
    """The stream answers only with the player's Referer (like most film sites' servers); the page has no video."""
    counts = {}
    lock = threading.Lock()

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        with self.lock:
            self.counts[path] = self.counts.get(path, 0) + 1
        if path == "/watch/film-1":
            body = b"<html><head><title>Film</title></head><body>no video here</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.headers.get("Referer") != PLAYER:
            self.send_error(403)
            return
        return super().do_GET()


@pytest.fixture
def site(tmp_path):
    ff = utils.find_ffmpeg()
    if not ff:
        pytest.skip("needs ffmpeg")
    root = tmp_path / "site"
    (root / "hls").mkdir(parents=True)
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=60:size=160x120:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=60", "-c:v", "libx264", "-g", "5", "-c:a", "aac",
                    "-f", "hls", "-hls_time", "0.5", "-hls_list_size", "0", "-hls_segment_filename",
                    str(root / "hls" / "seg%02d.ts"), str(root / "hls" / "index.m3u8")],
                   check=True, **utils.subprocess_flags())
    (root / "tr.vtt").write_text("WEBVTT\n\n00:00:00.500 --> 00:00:03.000\nMerhaba dünya\n", encoding="utf-8")
    Site.counts = {}
    handler = lambda *a, **k: Site(*a, directory=str(root), **k)                          # noqa: E731
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _item(site, folder):
    it = Item(site + "/watch/film-1", kind="video", folder=str(folder))
    it.name_hint = it.title = "Güzel Bir Film"
    it.alternates = [{"url": site + "/hls/index.m3u8", "referer": PLAYER, "user_agent": "TestBrowser/1.0",
                      "cookie": "", "headers": {"Origin": "http://player.example"}}]
    it.sub_urls = [{"url": site + "/tr.vtt", "lang": "tr", "ext": "vtt"}]
    return it


def _streams(path):
    ffprobe = os.path.join(os.path.dirname(utils.find_ffmpeg()), "ffprobe" + (".exe" if os.name == "nt" else ""))
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
                         capture_output=True, text=True, **utils.subprocess_flags()).stdout.split()
    return sorted(out)


def test_a_page_that_is_no_video_site_downloads_the_stream_it_played(site, tmp_path):
    folder = tmp_path / "out"
    it = _item(site, folder)
    jobs.run_media(it)
    assert it.final_path and os.path.basename(it.final_path) == "Güzel Bir Film.mp4"
    assert os.path.getsize(it.final_path) > 20000
    assert _streams(it.final_path) == ["audio", "subtitle", "video"]                 # the subtitle is inside too
    assert os.path.isfile(str(folder / "Video" / "Güzel Bir Film.tr.vtt")) or \
        any(name.endswith(".tr.vtt") for _, _, files in os.walk(folder) for name in files)
    assert Site.counts.get("/watch/film-1", 0) >= 1                                  # the page was tried first
    assert it.url.endswith("/hls/index.m3u8")


def test_without_the_players_referer_the_stream_is_refused(site, tmp_path):
    it = Item(site + "/hls/index.m3u8", kind="video", folder=str(tmp_path))
    with pytest.raises(Exception):
        jobs.run_media(it)


def test_a_paused_stream_goes_on_where_it_stopped(site, tmp_path):
    from app.segmented_downloader import DownloadStopped
    folder = tmp_path / "out"
    it = _item(site, folder)
    it.use_alternate()                                    # (straight to the stream)
    it.alternates = []

    original = Site.do_GET
    served = {"n": 0}

    def slow_then_pause(handler):
        path = handler.path.split("?")[0]
        if path.endswith(".ts"):
            time.sleep(0.05)                             # a slow server: the pause comes in the middle
        result = original(handler)
        if path.endswith(".ts"):
            with Site.lock:
                served["n"] += 1
                if served["n"] >= 40:
                    it.stop_reason = "pause"             # ⏸ after a good part of it
        return result
    Site.do_GET = slow_then_pause
    stopped = False
    try:
        jobs.run_media(it)
    except DownloadStopped:                               # (as the manager does: the error is not kept)
        stopped = True
    finally:
        Site.do_GET = original
    assert stopped
    first_round = sum(v for k, v in Site.counts.items() if k.endswith(".ts"))
    total = len([n for n in os.listdir(str(tmp_path / "site" / "hls")) if n.endswith(".ts")])
    assert first_round < total
    it.stop_reason = None                                 # ▶ again
    jobs.run_media(it)
    assert it.final_path and os.path.getsize(it.final_path) > 20000
    second_round = sum(v for k, v in Site.counts.items() if k.endswith(".ts")) - first_round
    assert second_round <= total - 25                     # the pieces it had stay: it goes on from there


def test_cancelling_a_stream_leaves_no_pieces_behind(site, tmp_path):
    from app.segmented_downloader import DownloadStopped
    from app.manager import DownloadManager
    folder = tmp_path / "out"
    it = _item(site, folder)
    it.use_alternate()
    original = Site.do_GET

    def stop_soon(handler):
        result = original(handler)
        if handler.path.split("?")[0].endswith(".ts") and Site.counts.get("/hls/seg30.ts"):
            it.stop_reason = "cancel"
        return result
    Site.do_GET = stop_soon
    try:
        with pytest.raises(DownloadStopped):
            jobs.run_media(it)
    finally:
        Site.do_GET = original
    left = jobs.ydl_leftovers(it)
    assert left and any(p.endswith(".ytdl") for p in left)
    (folder / "Başka Film.mp4.part").write_bytes(b"x")                   # another download's piece stays
    DownloadManager._cleanup(None, it)
    assert jobs.ydl_leftovers(it) == [] and (folder / "Başka Film.mp4.part").exists()
