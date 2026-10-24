"""Subtitles, MP3 cover art, the info summary and the yt-dlp fallback options."""
import os

import pytest

from app import jobs
from app import video_engine as ve
from app.models import Item
from app.segmented_downloader import set_proxy
from media_support import (fmt, has_attached_picture, needs_ffmpeg, new_item, probe_json, streams_of)


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return str(d)


def entries(*exts, base="http://x/sub"):
    return [{"ext": e, "url": f"{base}.{e}"} for e in exts]


INFO = {
    "subtitles": {"tr": entries("vtt", "srt"), "en-US": entries("vtt"), "de": entries("srt"),
                  "live_chat": entries("json")},
    "automatic_captions": {"tr": entries("vtt", base="http://x/auto-tr"),
                           "en": entries("srt", base="http://x/auto-en"),
                           "fr": entries("vtt", base="http://x/auto-fr")},
}


# -------------------------------------------------------------------- choosing subtitles
def test_no_subtitles_unless_asked():
    assert ve.pick_subtitles(INFO, "Yok") == []
    assert ve.pick_subtitles(INFO, None) == []
    assert ve.pick_subtitles(INFO, "Klingon") == []


def test_turkish_prefers_srt_over_vtt():
    assert ve.pick_subtitles(INFO, "Türkçe") == [{"lang": "tr", "url": "http://x/sub.srt", "ext": "srt"}]


def test_english_matches_a_regional_variant():
    assert ve.pick_subtitles(INFO, "İngilizce") == [{"lang": "en", "url": "http://x/sub.vtt", "ext": "vtt"}]


def test_the_uploaders_subtitles_win_over_automatic_captions():
    picked = ve.pick_subtitles(INFO, "Türkçe")[0]
    assert "auto" not in picked["url"]


def test_automatic_captions_are_the_fallback():
    info = {"subtitles": {"de": entries("srt")}, "automatic_captions": INFO["automatic_captions"]}
    assert ve.pick_subtitles(info, "İngilizce") == [
        {"lang": "en", "url": "http://x/auto-en.srt", "ext": "srt"}]
    assert ve.pick_subtitles({"subtitles": {}, "automatic_captions": {}}, "Türkçe") == []


def test_all_languages_means_the_uploaders_own_subtitles_without_chat():
    langs = sorted(s["lang"] for s in ve.pick_subtitles(INFO, "Tüm diller"))
    assert langs == ["de", "en-US", "tr"]                   # no live_chat, no automatic captions


def test_formats_we_cannot_use_are_ignored():
    info = {"subtitles": {"tr": [{"ext": "ttml", "url": "http://x/a.ttml"}, {"ext": "srt"}]}}
    assert ve.pick_subtitles(info, "Türkçe") == []          # no srt/vtt with a link


def test_the_videos_own_language_when_the_wanted_one_cannot_be_had():
    auto = {"tr": entries("srt", base="http://x/tr"), "en-orig": entries("vtt", base="http://x/orig"),
            "en": entries("srt", base="http://x/en")}
    assert ve.original_subtitles({"automatic_captions": auto}, skip={"tr"}) == [
        {"lang": "en", "url": "http://x/orig.vtt", "ext": "vtt"}]
    manual = {"subtitles": {"live_chat": entries("json"), "de-DE": entries("srt")}, "automatic_captions": auto,
              "language": "en"}
    assert ve.original_subtitles(manual, skip={"tr"})[0]["lang"] == "de-DE"     # the uploader's own one first
    assert ve.original_subtitles({"automatic_captions": {"tr-orig": entries("srt")}}, skip={"tr"}) == []
    assert ve.original_subtitles({}) == []


# --------------------------------------------------------------------- saving subtitles
def test_too_many_requests_is_asked_once_more(tmp_path, monkeypatch):
    calls, waits = [], []

    class Busy(Exception):
        response = type("R", (), {"status_code": 429})()

    def fake(url, headers=None):
        calls.append(url)
        if len(calls) == 1:
            raise Busy("429")
        return b"1\n00:00:00,000 --> 00:00:01,000\nTamam\n"

    monkeypatch.setattr(ve, "_download_small", fake)
    saved = ve.download_subtitles(Item("http://x"), [{"lang": "tr", "url": "u", "ext": "srt"}], str(tmp_path / "V"),
                                  sleep=waits.append)
    assert saved == [str(tmp_path / "V") + ".tr.srt"] and len(calls) == 2 and waits == [ve.SUB_RETRY_WAIT]


def test_an_empty_subtitle_is_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(ve, "_download_small", lambda url, headers=None: b"  \n")
    assert ve.download_subtitles(Item("http://x"), [{"lang": "tr", "url": "u", "ext": "srt"}], str(tmp_path / "V")) == []
    assert not os.path.exists(str(tmp_path / "V") + ".tr.srt")
def test_subtitles_are_saved_next_to_the_video(server, tmp_path):
    srt = server.add("1\n00:00:00,000 --> 00:00:01,000\nMerhaba\n".encode(), ".srt")
    base = str(tmp_path / "Movie")
    subs = [{"lang": "tr", "url": server.url("f", srt), "ext": "srt"},
            {"lang": "xx", "url": server.url("f", "missing.vtt"), "ext": "vtt"}]
    saved = ve.download_subtitles(Item("http://x"), subs, base)
    assert saved == [base + ".tr.srt"]                       # the broken one is skipped, not fatal
    assert "Merhaba" in open(base + ".tr.srt", encoding="utf-8").read()
    assert not os.path.exists(base + ".xx.vtt")


@needs_ffmpeg
def test_a_video_download_saves_the_chosen_subtitle(server, media, served, stand_in, folder):
    srt = server.add(b"1\n00:00:00,000 --> 00:00:01,000\nHello\n", ".srt")
    info = {"title": "Movie", "requested_formats": [
        fmt(server.url("f", served["video"]), "mp4", media["video"], vcodec="avc1"),
        fmt(server.url("f", served["audio"]), "m4a", media["audio"], acodec="mp4a.40.2")],
        "subtitles": {"en": [{"ext": "srt", "url": server.url("f", srt)}]}}
    stand_in["info"] = info
    item = new_item("http://page", "video", folder, subs="İngilizce")
    jobs.run_media(item)
    assert sorted(os.listdir(folder)) == ["Movie.en.srt", "Movie.mp4"]
    assert item.message == "1 altyazı kaydedildi (videonun içinde de var)"
    subs = [s for s in probe_json(os.path.join(folder, "Movie.mp4"))["streams"] if s["codec_type"] == "subtitle"]
    assert [(s["codec_name"], s.get("tags", {}).get("language")) for s in subs] == [("mov_text", "eng")]


@needs_ffmpeg
def test_a_refused_translation_keeps_the_videos_own_language(server, media, served, stand_in, folder, monkeypatch):
    """YouTube answers 'too many requests' to its translated captions: the spoken language is kept."""
    srt = server.add(b"1\n00:00:00,000 --> 00:00:01,000\nHello\n", ".srt")
    stand_in["info"] = {"title": "Movie", "language": "en", **fmt(server.url("f", served["full"]), "mp4", media["full"]),
                        "automatic_captions": {"tr": [{"ext": "srt", "url": server.url("f", "refused.srt")}],
                                               "en-orig": [{"ext": "srt", "url": server.url("f", srt)}]}}
    monkeypatch.setattr(ve, "SUB_RETRY_WAIT", 0)
    item = new_item("http://page", "video", folder, subs="Türkçe")
    jobs.run_media(item)
    assert sorted(os.listdir(folder)) == ["Movie.en.srt", "Movie.mp4"]
    assert "Türkçe altyazıyı YouTube vermedi" in item.message and "(en)" in item.message


@needs_ffmpeg
def test_no_subtitle_available_is_reported_not_an_error(server, media, served, stand_in, folder):
    stand_in["info"] = {"title": "Movie", **fmt(server.url("f", served["full"]), "mp4", media["full"])}
    item = new_item("http://page", "video", folder, subs="Türkçe")
    jobs.run_media(item)
    assert os.listdir(folder) == ["Movie.mp4"] and "altyazı bulamadım" in item.message


@needs_ffmpeg
def test_subtitles_are_not_fetched_for_audio_or_when_off(server, media, served, stand_in, folder):
    stand_in["info"] = {"title": "Movie", "subtitles": {"tr": [{"ext": "srt", "url": server.url("f", "x.srt")}]},
                        **fmt(server.url("f", served["full"]), "mp4", media["full"])}
    jobs.run_media(new_item("http://page", "video", folder, subs="Yok"))
    assert os.listdir(folder) == ["Movie.mp4"]


# ------------------------------------------------------------------------- cover art
@needs_ffmpeg
@pytest.mark.parametrize("kind", ["jpg", "webp"])
def test_the_thumbnail_becomes_the_mp3_cover(server, media, served, stand_in, folder, kind):
    stand_in["info"] = {"title": "Song", "artist": "Me", "thumbnail": server.url("f", served[kind]),
                        **fmt(server.url("f", served["audio"]), "m4a", media["audio"], acodec="mp4a.40.2")}
    item = new_item("http://page", "audio", folder, cover=True)
    jobs.run_media(item)
    assert os.listdir(folder) == ["Song.mp3"]                # no cover temp files left behind
    codecs, tags, _ = streams_of(item.final_path)
    assert codecs == {"audio": "mp3", "video": "mjpeg"}      # WebP was converted to JPEG
    assert has_attached_picture(item.final_path) and tags["artist"] == "Me"


@needs_ffmpeg
def test_cover_art_can_be_switched_off(server, media, served, stand_in, folder):
    stand_in["info"] = {"title": "Song", "thumbnail": server.url("f", served["jpg"]),
                        **fmt(server.url("f", served["audio"]), "m4a", media["audio"], acodec="mp4a.40.2")}
    item = new_item("http://page", "audio", folder, cover=False)
    jobs.run_media(item)
    assert streams_of(item.final_path)[0] == {"audio": "mp3"}


@needs_ffmpeg
@pytest.mark.parametrize("thumbnail", ["http://127.0.0.1:9/nope.jpg", "", None])
def test_a_missing_thumbnail_never_breaks_the_mp3(server, media, served, stand_in, folder, thumbnail):
    stand_in["info"] = {"title": "Song", "thumbnail": thumbnail,
                        **fmt(server.url("f", served["audio"]), "m4a", media["audio"], acodec="mp4a.40.2")}
    item = new_item("http://page", "audio", folder, cover=True)
    jobs.run_media(item)
    assert os.listdir(folder) == ["Song.mp3"]
    assert streams_of(item.final_path)[0] == {"audio": "mp3"}


@needs_ffmpeg
def test_a_broken_image_is_skipped(server, media, served, stand_in, folder):
    junk = server.add(b"this is not an image", ".jpg")
    stand_in["info"] = {"title": "Song", "thumbnail": server.url("f", junk),
                        **fmt(server.url("f", served["audio"]), "m4a", media["audio"], acodec="mp4a.40.2")}
    item = new_item("http://page", "audio", folder, cover=True)
    jobs.run_media(item)
    assert streams_of(item.final_path)[0] == {"audio": "mp3"}


def test_thumbnail_choice():
    assert ve.pick_thumbnail({"thumbnail": "http://x/a.jpg"}) == "http://x/a.jpg"
    assert ve.pick_thumbnail({"thumbnails": [{"url": "http://x/small"}, {"url": "http://x/big"}]}) == "http://x/big"
    assert ve.pick_thumbnail({"thumbnails": [{"id": "1"}]}) == ""
    assert ve.pick_thumbnail({}) == ""


def test_discard_cover_removes_the_temp_folder_and_accepts_none(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "cover.jpg").write_text("x")
    ve.discard_cover(str(d / "cover.jpg"))
    assert not d.exists()
    ve.discard_cover(None)


# ------------------------------------------------------------------------------- info
RAW = {
    "title": "A video", "uploader": "Someone", "duration": 185, "thumbnail": "http://x/t.jpg",
    "formats": [
        {"height": 1080, "fps": 30, "vcodec": "avc1.64", "filesize": 100, "ext": "mp4"},
        {"height": 1080, "fps": 60, "vcodec": "vp9", "filesize": 150, "ext": "webm"},
        {"height": 720, "fps": 30, "vcodec": "avc1.4d", "filesize_approx": 60, "ext": "mp4"},
        {"height": 360, "fps": 30, "vcodec": "avc1", "ext": "mp4"},
        {"height": None, "vcodec": "none", "acodec": "mp4a", "filesize": 20},
        {"height": None, "vcodec": "none", "acodec": "opus", "filesize": 30},
        {"height": 240, "vcodec": "none", "acodec": "none"},
    ],
    "subtitles": {"tr": [], "en": [], "live_chat": []},
    "automatic_captions": {"tr": [], "en": [], "fr": []},
}


def test_the_info_summary_lists_the_best_format_of_every_height():
    s = ve.summarize_info(RAW)
    assert [q["height"] for q in s["qualities"]] == [1080, 720, 360]
    assert s["qualities"][0] == {"height": 1080, "fps": 60, "codec": "vp9", "size": 150, "ext": "webm"}
    assert s["qualities"][1]["size"] == 60                  # filesize_approx is used when needed
    assert s["audio_size"] == 30
    assert (s["title"], s["uploader"], s["duration"], s["thumbnail"]) == \
           ("A video", "Someone", 185, "http://x/t.jpg")
    assert s["subtitles"] == ["en", "tr"] and s["auto_subtitles"] == 3
    assert s["is_playlist"] is False


def test_the_info_summary_copes_with_nothing():
    s = ve.summarize_info({})
    assert s["qualities"] == [] and s["title"] == "" and s["duration"] == 0 and s["audio_size"] == 0


def test_a_playlist_is_recognised():
    s = ve.summarize_info({"_type": "playlist", "title": "List", "entries": [{}, {}, {}]})
    assert s["is_playlist"] is True and s["entries"] == 3


@pytest.mark.parametrize("height,expected", [(2160, "2160p"), (4320, "2160p"), (1440, "1440p"),
                                              (1080, "1080p"), (1079, "720p"), (720, "720p"),
                                              (480, "480p"), (360, "360p"), (144, "360p")])
def test_quality_for_height(height, expected):
    assert ve.quality_for_height(height) == expected


def test_fetch_info_asks_yt_dlp_without_downloading(monkeypatch):
    seen = {}

    class FakeYDL:
        def __init__(self, opts):
            seen["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            seen["url"], seen["download"] = url, download
            return RAW

    monkeypatch.setattr(ve, "_yt_dlp", lambda: type("M", (), {"YoutubeDL": FakeYDL}))
    s = ve.fetch_info("http://x/video", "firefox")
    assert seen["url"] == "http://x/video" and seen["download"] is False
    assert seen["opts"]["skip_download"] is True and seen["opts"]["cookiesfrombrowser"] == ("firefox",)
    assert s["title"] == "A video"


def test_fetch_info_with_no_answer_is_an_error(monkeypatch):
    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            return None

    monkeypatch.setattr(ve, "_yt_dlp", lambda: type("M", (), {"YoutubeDL": FakeYDL}))
    with pytest.raises(RuntimeError):
        ve.fetch_info("http://x")


# ------------------------------------------------------------------- yt-dlp options
def test_fallback_options_leave_the_subtitles_to_diso(folder):
    """yt-dlp fails the whole video when YouTube refuses a subtitle: DISO fetches them afterwards."""
    for subs in ("Türkçe", "Tüm diller", "Yok"):
        o = ve.ydl_options(new_item("http://x", "video", folder, subs=subs, quality="720p"))
        assert o["merge_output_format"] == "mp4" and "height<=?720" in o["format"] and "postprocessors" not in o
        assert not ({"writesubtitles", "writeautomaticsub", "subtitleslangs"} & set(o))


def test_fallback_options_for_mp3_with_cover(folder):
    o = ve.ydl_options(new_item("http://x", "audio", folder, bitrate="128", cover=True))
    keys = [p["key"] for p in o["postprocessors"]]
    assert keys[0] == "FFmpegExtractAudio" and o["postprocessors"][0]["preferredquality"] == "128"
    assert "EmbedThumbnail" in keys and o["writethumbnail"] is True
    o = ve.ydl_options(new_item("http://x", "audio", folder, cover=False))
    assert [p["key"] for p in o["postprocessors"]] == ["FFmpegExtractAudio"]


def test_fallback_options_follow_sorting_proxy_and_speed_limit(folder):
    from app.segmented_downloader import LIMITER
    it = new_item("http://x", "video", folder, sort_folders=True)
    assert os.path.dirname(ve.ydl_options(it)["outtmpl"]) == os.path.join(folder, "Video")
    it = new_item("http://x", "audio", folder, sort_folders=True)
    assert os.path.dirname(ve.ydl_options(it)["outtmpl"]) == os.path.join(folder, "Müzik")
    assert ve.ydl_options(it)["ratelimit"] is None
    LIMITER.set_rate(500_000)
    set_proxy("socks5://127.0.0.1:1080")
    o = ve.ydl_options(it)
    assert o["ratelimit"] == 500_000 and o["proxy"] == "socks5://127.0.0.1:1080"


# ------------------------------------------------------------------- well-known video sites
@pytest.mark.parametrize("url, video", [
    ("https://www.youtube.com/watch?v=x", True), ("https://youtu.be/x", True), ("https://m.youtube.com/x", True),
    ("https://music.youtube.com/watch?v=x", True), ("https://www.instagram.com/reel/x", True),
    ("https://vm.tiktok.com/x", True), ("https://x.com/a/status/1", True),
    ("https://example.com/youtube.com.zip", False), ("https://notyoutube.com/x", False),
    ("http://127.0.0.1:8000/f/file.bin", False)])
def test_well_known_video_sites_are_not_asked_first(url, video, monkeypatch):
    asked = []
    monkeypatch.setattr(jobs, "probe", lambda *a, **k: asked.append(a) or (_ for _ in ()).throw(OSError("x")))
    assert jobs.is_video_site(url) is video
    it = Item(url)
    jobs.classify(it)
    assert it.kind == "video" and (asked == []) is video
