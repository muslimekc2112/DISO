"""Reading title / artist / album / length / cover out of music files (real ffmpeg / ffprobe)."""
import os
import time

import pytest
from media_support import FFMPEG, FFPROBE, ffmpeg
from music_support import make_wav

from app import tags

pytestmark = [pytest.mark.ffmpeg,
              pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not found")]


def make_mp3(path, seconds=1.5, title="Şarkı Adı", artist="Sanatçı Ğ", album="Albüm", cover=False):
    args = ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    if cover:
        from PIL import Image
        png = str(path) + ".cover.png"
        Image.new("RGB", (600, 600), (220, 90, 30)).save(png)
        args += ["-i", png, "-map", "0:a", "-map", "1:v", "-c:v", "mjpeg", "-disposition:v", "attached_pic"]
    args += ["-c:a", "libmp3lame", "-id3v2_version", "3"]
    for key, value in (("title", title), ("artist", artist), ("album", album)):
        if value:
            args += ["-metadata", f"{key}={value}"]
    ffmpeg(*args, str(path))
    return str(path)


@pytest.fixture
def isolated(isolated_home):
    return isolated_home


# ------------------------------------------------------------------------------ probe
def test_probe_reads_the_tags_and_the_length(tmp_path):
    info = tags.probe(make_mp3(tmp_path / "a.mp3"))
    assert info["title"] == "Şarkı Adı" and info["artist"] == "Sanatçı Ğ" and info["album"] == "Albüm"
    assert 1300 <= info["duration"] <= 1800 and info["cover"] is False


def test_probe_sees_a_cover(tmp_path):
    assert tags.probe(make_mp3(tmp_path / "c.mp3", cover=True))["cover"] is True


def test_a_file_without_tags_still_has_a_length(tmp_path):
    info = tags.probe(make_mp3(tmp_path / "plain.mp3", title="", artist="", album=""))
    assert info["title"] == "" and info["artist"] == "" and info["duration"] > 1000


def test_probe_reads_a_wav(tmp_path):
    info = tags.probe(make_wav(tmp_path / "w.wav", seconds=2))
    assert 1900 <= info["duration"] <= 2100 and info["title"] == ""


def test_probe_of_a_file_that_is_not_music_is_empty(tmp_path):
    bad = tmp_path / "x.mp3"
    bad.write_bytes(b"not music at all" * 20)
    assert tags.probe(str(bad)) == {}
    assert tags.probe(str(tmp_path / "missing.mp3")) == {}


def test_probe_without_ffprobe_falls_back_to_ffmpeg(tmp_path, monkeypatch):
    real = tags._tool
    monkeypatch.setattr(tags, "_tool", lambda name: None if name == "ffprobe" else real(name))
    info = tags.probe(make_mp3(tmp_path / "f.mp3", cover=True))
    assert info["title"] == "Şarkı Adı" and info["artist"] == "Sanatçı Ğ" and info["album"] == "Albüm"
    assert 1300 <= info["duration"] <= 1800 and info["cover"] is True


def test_the_ffmpeg_text_parser_on_a_typical_output():
    text = ("Input #0, mp3, from 'a.mp3':\n  Metadata:\n    title           : Hello World\n"
            "    artist          : The Band\n    album           : First\n  Duration: 00:03:42.35, start: 0.025, bitrate: 320 kb/s\n"
            "  Stream #0:0: Audio: mp3\n  Stream #0:1: Video: mjpeg (Baseline), yuvj444p, 600x600 (attached pic)\n")
    info = tags._from_ffmpeg_text(text)
    assert info == {"duration": 222350, "title": "Hello World", "artist": "The Band", "album": "First", "cover": True}
    assert tags._from_ffmpeg_text("nothing useful")["duration"] == 0


def test_the_probe_parser_handles_tags_kept_in_the_stream_and_odd_values():
    data = {"format": {"duration": "abc", "tags": {"TITLE": "  Big  ", "ARTIST": ""}},
            "streams": [{"tags": {"album": "A", "artist": "Per stream"}, "disposition": {"attached_pic": 0}}]}
    info = tags._from_probe(data)
    assert info["title"] == "Big" and info["album"] == "A" and info["duration"] == 0
    assert info["artist"] == "Per stream" and info["cover"] is False
    assert tags._from_probe({})["duration"] == 0


# ------------------------------------------------------------------------------ cover
def test_the_cover_is_saved_as_a_small_jpeg_and_reused(tmp_path, isolated):
    from PIL import Image
    mp3 = make_mp3(tmp_path / "c.mp3", cover=True)
    out = tags.extract_cover(mp3)
    assert out and out.endswith(".jpg") and os.path.isfile(out)
    with Image.open(out) as im:
        assert im.format == "JPEG" and im.width <= tags.COVER_SIZE
    assert tags.extract_cover(mp3) == out                              # the second call reuses the file
    assert not [f for f in os.listdir(tags.covers_dir()) if f.endswith(".part.jpg")]


def test_no_cover_means_none(tmp_path, isolated):
    assert tags.extract_cover(make_mp3(tmp_path / "n.mp3")) is None
    assert tags.extract_cover(str(tmp_path / "missing.mp3")) is None


def test_a_changed_file_gets_its_own_cover_file(tmp_path, isolated):
    mp3 = make_mp3(tmp_path / "c.mp3", cover=True)
    first = tags.cover_file(mp3)
    time.sleep(1.1)
    make_mp3(tmp_path / "c.mp3", cover=True, seconds=2)
    assert tags.cover_file(mp3) != first


# ------------------------------------------------------------------------------ reader
def wait_for(reader, count, timeout=20):
    got, deadline = [], time.time() + timeout
    while len(got) < count and time.time() < deadline:
        got += reader.drain()
        time.sleep(0.02)
    return got


@pytest.fixture
def reader(isolated):
    r = tags.TagReader()
    yield r
    r.stop()


def test_the_reader_answers_in_the_background_and_remembers(tmp_path, isolated):
    mp3 = make_mp3(tmp_path / "a.mp3")
    calls = []
    real = tags.probe

    def counting(path):
        calls.append(path)
        return real(path)

    r = tags.TagReader(read=counting)
    try:
        r.request(mp3)
        r.request(mp3)                                                # asked twice while pending: read once
        (kind, path, info), *rest = wait_for(r, 1)
        assert kind == "tags" and path == mp3 and info["title"] == "Şarkı Adı"
        assert len(calls) == 1
        r.request(mp3)                                                # remembered: answered, not read again
        assert wait_for(r, 1)[0][2]["artist"] == "Sanatçı Ğ" and len(calls) == 1
    finally:
        r.stop()
    again = tags.TagReader(read=counting)                             # remembered after a restart
    try:
        again.request(mp3)
        assert wait_for(again, 1)[0][2]["album"] == "Albüm" and len(calls) == 1
    finally:
        again.stop()


def test_a_changed_file_is_read_again(tmp_path, isolated):
    mp3 = make_mp3(tmp_path / "a.mp3", title="Eski")
    r = tags.TagReader()
    try:
        r.request(mp3)
        assert wait_for(r, 1)[0][2]["title"] == "Eski"
        time.sleep(1.1)
        make_mp3(tmp_path / "a.mp3", title="Yeni", seconds=2)
        r.request(mp3)
        assert wait_for(r, 1)[0][2]["title"] == "Yeni"
    finally:
        r.stop()


def test_missing_and_broken_files_give_an_empty_answer_not_an_error(tmp_path, reader):
    bad = tmp_path / "x.mp3"
    bad.write_bytes(b"junk" * 50)
    reader.request(str(bad))
    reader.request(str(tmp_path / "gone.mp3"))
    got = {p: info for _, p, info in wait_for(reader, 2)}
    assert got == {str(bad): {}, str(tmp_path / "gone.mp3"): {}}


def test_a_failing_read_does_not_stop_the_reader(tmp_path, isolated):
    mp3 = make_mp3(tmp_path / "ok.mp3")
    boom = tmp_path / "boom.mp3"
    boom.write_bytes(b"x")

    def flaky(path):
        if path == str(boom):
            raise RuntimeError("bug in the reading code")
        return tags.probe(path)

    r = tags.TagReader(read=flaky)
    try:
        r.request(str(boom))
        r.request(mp3)
        got = {p: info for _, p, info in wait_for(r, 2)}
        assert got[str(boom)] == {} and got[mp3]["title"] == "Şarkı Adı"
    finally:
        r.stop()


def test_the_reader_delivers_covers(tmp_path, reader):
    with_cover = make_mp3(tmp_path / "c.mp3", cover=True)
    without = make_mp3(tmp_path / "n.mp3")
    reader.request_cover(with_cover)
    reader.request_cover(without)
    got = {p: v for k, p, v in wait_for(reader, 2) if k == "cover"}
    assert got[with_cover] and os.path.isfile(got[with_cover]) and got[without] is None


def test_a_damaged_cache_file_is_ignored(tmp_path, isolated):
    path = tmp_path / "cache.json"
    path.write_text("{broken", encoding="utf-8")
    r = tags.TagReader(cache_path=str(path))
    try:
        mp3 = make_mp3(tmp_path / "a.mp3")
        r.request(mp3)
        assert wait_for(r, 1)[0][2]["title"] == "Şarkı Adı"
    finally:
        r.stop()


def test_stopping_the_reader_twice_or_after_asking_is_safe(tmp_path, isolated):
    r = tags.TagReader()
    r.stop()
    r.request(str(tmp_path / "late.mp3"))                              # ignored, no error, no hang
    assert r.drain() == []


def test_stopping_drops_what_is_still_waiting_and_returns_at_once(tmp_path, isolated):
    """Closing DISO with a big list still being read must not wait for every file."""
    import threading
    first = threading.Event()
    read = []

    def slow(path):
        read.append(path)
        first.set()
        time.sleep(0.3)
        return {"duration": 1000}

    r = tags.TagReader(read=slow)
    for i in range(200):
        r.request(str(make_wav(tmp_path / f"{i}.wav")))
    first.wait(5)
    t = time.time()
    r.stop()
    assert time.time() - t < 1.2 and len(read) <= 3
