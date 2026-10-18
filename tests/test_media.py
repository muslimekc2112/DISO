"""Video / MP3 pipeline with real ffmpeg. yt-dlp is replaced by a stand-in that points to
media files on the local test server, so no website is needed."""
import json
import os
import shutil
import subprocess
import threading
import time

import pytest

from app import jobs
from app import video_engine as ve
from app.models import Item
from app.segmented_downloader import DownloadStopped
from app.utils import find_ffmpeg

FFMPEG = find_ffmpeg()
FFPROBE = shutil.which("ffprobe")

def needs_ffmpeg(test):
    """Marks a test 'ffmpeg' (so it can be deselected) and skips it when ffmpeg is missing."""
    test = pytest.mark.ffmpeg(test)
    return pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not found")(test)



def ffmpeg(*args):
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *args], check=True,
                   stdin=subprocess.DEVNULL)


def streams_of(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name",
                          "-show_entries", "format=bit_rate:format_tags=title,artist", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    return ({s["codec_type"]: s["codec_name"] for s in data["streams"]},
            {k.lower(): v for k, v in data.get("format", {}).get("tags", {}).items()},
            int(data["format"].get("bit_rate") or 0))


@pytest.fixture(scope="session")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    v, a, o, mkv, full = (str(d / n) for n in ("v.mp4", "a.m4a", "o.webm", "x.mkv", "full.mp4"))
    video = ["-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=15"]
    audio = ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    ffmpeg(*video, "-c:v", "libx264", "-pix_fmt", "yuv420p", v)
    ffmpeg(*audio, "-c:a", "aac", a)
    ffmpeg(*audio, "-c:a", "libopus", o)
    ffmpeg(*video, *audio, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", mkv)
    ffmpeg(*video, *audio, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", full)
    return {"video": v, "audio": a, "opus": o, "mkv": mkv, "full": full}


def fmt(url, ext, path, acodec="none", vcodec="none"):
    return {"url": url, "ext": ext, "protocol": "https", "filesize": os.path.getsize(path),
            "acodec": acodec, "vcodec": vcodec, "http_headers": {}, "_fast_headers": {}}


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return str(d)


def new_item(url, kind, folder, **kw):
    it = Item(url, kind=kind, quality="En iyi", bitrate="192", connections=4, folder=folder)
    for k, v in kw.items():
        setattr(it, k, v)
    return it


# ------------------------------------------------------------------------- selectors
def test_format_selector():
    assert ve.format_selector("audio", "En iyi") == "bestaudio/best"
    assert ve.format_selector("video", "En iyi") == "bv*+ba/b"
    s = ve.format_selector("video", "1080p")
    assert "height<=?1080" in s and "avc1" in s           # H.264 + AAC plays everywhere
    assert "avc1" not in ve.format_selector("video", "2160p")


def test_is_fast_only_for_one_plain_http_file():
    ok = {"url": "http://x/a.mp4", "protocol": "https"}
    assert ve.is_fast(ok)
    assert not ve.is_fast({**ok, "protocol": "m3u8_native"})
    assert not ve.is_fast({**ok, "fragments": [{}]})
    assert not ve.is_fast({**ok, "ext": "mhtml"})
    assert not ve.is_fast({**ok, "has_drm": True})
    assert not ve.is_fast({"protocol": "https"})


def test_pretty_error_adds_hints_and_strips_colour_codes():
    assert "Giriş çerezleri" in ve.pretty_error(Exception("ERROR: Sign in to confirm you're not a bot"))
    assert "video sayfası" in ve.pretty_error(Exception("\x1b[0;31mERROR:\x1b[0m Unsupported URL: http://x"))
    assert "\x1b" not in ve.pretty_error(Exception("\x1b[0;31mboom\x1b[0m"))
    assert len(ve.pretty_error(Exception("x" * 5000))) <= 600


# ------------------------------------------------------------------------- ffmpeg steps
@needs_ffmpeg
def test_merge_copies_video_and_keeps_aac(media, tmp_path):
    out = str(tmp_path / "m.mp4")
    ve.merge_to_mp4(media["video"], media["audio"], out, "mp4a.40.2", Item("x"))
    assert streams_of(out)[0] == {"video": "h264", "audio": "aac"}


@needs_ffmpeg
def test_merge_converts_opus_audio_to_aac(media, tmp_path):
    out = str(tmp_path / "m.mp4")
    ve.merge_to_mp4(media["video"], media["opus"], out, "opus", Item("x"))
    assert streams_of(out)[0] == {"video": "h264", "audio": "aac"}


@needs_ffmpeg
def test_mp3_conversion_writes_tags_and_uses_the_bitrate(media, tmp_path):
    out = str(tmp_path / "s.mp3")
    ve.to_mp3(media["audio"], out, "192", {"title": "Şarkı", "artist": "Ben"}, Item("x"))
    codecs, tags, bitrate = streams_of(out)
    assert codecs == {"audio": "mp3"} and tags == {"title": "Şarkı", "artist": "Ben"}
    assert 150_000 < bitrate < 230_000


@needs_ffmpeg
def test_remux_turns_mkv_into_mp4_without_reencoding_video(media, tmp_path):
    out = str(tmp_path / "r.mp4")
    ve.remux_to_mp4(media["mkv"], out, Item("x"))
    assert streams_of(out)[0] == {"video": "h264", "audio": "aac"}


@needs_ffmpeg
@pytest.mark.parametrize("reason", ["pause", "cancel"])
def test_a_running_ffmpeg_stops_quickly_when_asked(reason, tmp_path):
    item = Item("x")
    threading.Timer(0.6, lambda: item.request_stop(reason)).start()
    t0 = time.time()
    with pytest.raises(DownloadStopped) as stop:
        ve.run_ffmpeg(["-f", "lavfi", "-i", "testsrc=duration=600:size=1280x720:rate=30",
                       "-c:v", "libx264", "-preset", "veryslow", "-f", "null", "-"], item)
    assert stop.value.reason == reason and time.time() - t0 < 8
    assert item._proc is None


@needs_ffmpeg
def test_ffmpeg_errors_carry_ffmpegs_message(tmp_path):
    with pytest.raises(RuntimeError, match="ffmpeg:"):
        ve.run_ffmpeg(["-i", str(tmp_path / "does-not-exist.mp4"), str(tmp_path / "o.mp4")], Item("x"))


def test_missing_ffmpeg_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(ve, "find_ffmpeg", lambda: None)
    with pytest.raises(ve.MissingFFmpeg):
        ve.run_ffmpeg(["-version"], Item("x"))


# ------------------------------------------------------------------------ full pipeline
@pytest.fixture
def stand_in(monkeypatch):
    """Make ve.resolve return a prepared info dict instead of asking yt-dlp."""
    box = {}
    monkeypatch.setattr(ve, "resolve", lambda url, kind, quality, cookies=None: box["info"])
    return box


@pytest.fixture
def served(server, media):
    return {k: server.add(open(p, "rb").read(), os.path.splitext(p)[1]) for k, p in media.items()}


@needs_ffmpeg
def test_video_plus_audio_are_downloaded_and_merged_into_one_mp4(server, media, served, stand_in, folder):
    stand_in["info"] = {"title": "Test: Video?", "requested_formats": [
        fmt(server.url("f", served["video"]), "mp4", media["video"], vcodec="avc1"),
        fmt(server.url("f", served["audio"]), "m4a", media["audio"], acodec="mp4a.40.2")]}
    item = new_item("http://page", "video", folder)
    jobs.run_media(item)
    assert os.listdir(folder) == ["Test_ Video_.mp4"]            # no leftovers, safe file name
    assert item.final_path.endswith("Test_ Video_.mp4")
    assert streams_of(item.final_path)[0] == {"video": "h264", "audio": "aac"}
    assert item.title == "Test: Video?" and item.fraction == 1.0


@needs_ffmpeg
def test_audio_kind_produces_a_tagged_mp3(server, media, served, stand_in, folder):
    stand_in["info"] = {"title": "Şarkı", "artist": "Sanatçı", **fmt(
        server.url("f", served["audio"]), "m4a", media["audio"], acodec="mp4a.40.2")}
    item = new_item("http://page", "audio", folder, bitrate="128")
    jobs.run_media(item)
    assert os.listdir(folder) == ["Şarkı.mp3"]
    codecs, tags, bitrate = streams_of(item.final_path)
    assert codecs == {"audio": "mp3"} and tags == {"title": "Şarkı", "artist": "Sanatçı"}
    assert 100_000 < bitrate < 160_000


@needs_ffmpeg
def test_a_single_mp4_is_simply_moved_into_place(server, media, served, stand_in, folder):
    stand_in["info"] = {"title": "Clip", **fmt(server.url("f", served["full"]), "mp4", media["full"])}
    jobs.run_media(new_item("http://page", "video", folder))
    assert os.listdir(folder) == ["Clip.mp4"]


@needs_ffmpeg
def test_a_single_non_mp4_file_is_remuxed_to_mp4(server, media, served, stand_in, folder):
    stand_in["info"] = {"title": "Clip", **fmt(server.url("f", served["mkv"]), "mkv", media["mkv"])}
    item = new_item("http://page", "video", folder)
    jobs.run_media(item)
    assert os.listdir(folder) == ["Clip.mp4"]
    assert streams_of(item.final_path)[0] == {"video": "h264", "audio": "aac"}


@needs_ffmpeg
def test_two_videos_with_the_same_title_never_overwrite_each_other(server, media, served, stand_in, folder):
    stand_in["info"] = {"title": "Same title", "requested_formats": [
        fmt(server.url("f", served["video"]), "mp4", media["video"], vcodec="avc1"),
        fmt(server.url("f", served["audio"]), "m4a", media["audio"], acodec="mp4a.40.2")]}
    items = [new_item("http://page", "video", folder) for _ in range(3)]
    errors = []

    def go(it):
        try:
            jobs.run_media(it)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=go, args=(it,)) for it in items]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not errors
    assert sorted(os.listdir(folder)) == ["Same title (1).mp4", "Same title (2).mp4", "Same title.mp4"]
    for it in items:
        assert streams_of(it.final_path)[0] == {"video": "h264", "audio": "aac"}


@needs_ffmpeg
def test_a_pause_during_the_merge_keeps_the_parts_and_resume_does_not_download_again(
        server, media, served, stand_in, folder, monkeypatch):
    stand_in["info"] = {"title": "Resumable", "requested_formats": [
        fmt(server.url("f", served["video"]), "mp4", media["video"], vcodec="avc1"),
        fmt(server.url("f", served["audio"]), "m4a", media["audio"], acodec="mp4a.40.2")]}
    real_merge = ve.merge_to_mp4
    monkeypatch.setattr(ve, "merge_to_mp4", lambda *a, **k: (_ for _ in ()).throw(DownloadStopped("pause")))
    item = new_item("http://page", "video", folder)
    with pytest.raises(DownloadStopped):
        jobs.run_media(item)
    leftovers = os.listdir(folder)
    assert len(leftovers) == 2 and all(".f" in n for n in leftovers)       # both downloaded parts kept
    sent = server.sent(served["video"]), server.sent(served["audio"])

    monkeypatch.setattr(ve, "merge_to_mp4", real_merge)
    item.stop_reason = None
    jobs.run_media(item)
    assert (server.sent(served["video"]), server.sent(served["audio"])) == sent   # nothing re-downloaded
    assert os.listdir(folder) == ["Resumable.mp4"]


def test_a_page_that_yt_dlp_cannot_stream_over_http_uses_yt_dlps_own_downloader(
        server, stand_in, folder, monkeypatch):
    stand_in["info"] = {"title": "HLS", "url": "http://x/playlist.m3u8", "protocol": "m3u8_native", "ext": "mp4"}
    monkeypatch.setattr(ve, "ydl_download", lambda item: os.path.join(item.folder, "from-ytdlp.mp4"))
    monkeypatch.setattr(jobs, "find_ffmpeg", lambda: "/fake/ffmpeg")
    item = new_item("http://page", "video", folder)
    jobs.run_media(item)
    assert item.final_path.endswith("from-ytdlp.mp4")


def test_when_the_fast_engine_fails_yt_dlp_takes_over(server, stand_in, folder, monkeypatch):
    stand_in["info"] = {"title": "Gone", "url": server.url("f", "missing.mp4"), "protocol": "https",
                        "ext": "mp4", "filesize": 1000, "http_headers": {}, "_fast_headers": {}}
    monkeypatch.setattr(ve, "ydl_download", lambda item: os.path.join(item.folder, "rescued.mp4"))
    monkeypatch.setattr(jobs, "find_ffmpeg", lambda: "/fake/ffmpeg")
    item = new_item("http://page", "video", folder)
    jobs.run_media(item)
    assert item.final_path.endswith("rescued.mp4")


def test_a_resolve_error_becomes_a_readable_message(monkeypatch, folder):
    def fail(*a, **k):
        raise Exception("ERROR: Unsupported URL: http://nope")

    monkeypatch.setattr(ve, "resolve", fail)
    with pytest.raises(RuntimeError, match="video sayfası"):
        jobs.run_media(new_item("http://nope", "video", folder))


def test_a_pause_while_resolving_is_a_pause_not_an_error(monkeypatch, folder):
    item = new_item("http://page", "video", folder)

    def slow_resolve(*a, **k):
        item.request_stop("pause")
        raise Exception("interrupted")

    monkeypatch.setattr(ve, "resolve", slow_resolve)
    with pytest.raises(DownloadStopped):
        jobs.run_media(item)


def test_reserved_names_are_unique_and_released(folder):
    a = jobs.reserve_path(folder, "x.mp4")
    b = jobs.reserve_path(folder, "x.mp4")
    assert a != b and os.path.exists(a + ".part") and os.path.exists(b + ".part")
    jobs.release_path(a)
    assert not os.path.exists(a + ".part")
    assert os.path.exists(b + ".part")
