"""Files Windows' MCI cannot open (an MP3 with a big cover, Opus sound in an MP4): the player makes a
playable copy and plays that, the song that was clicked, not the next one."""
import os
import threading

import pytest
from media_support import ffmpeg, needs_ffmpeg
from music_support import FakeBackend, make_wav

from app import playable, player
from app import video_engine as ve
from app.models import Item
from app.player import Controller


class FakePrepare:
    """Same methods as playable.Preparer; the test says when a copy is made or fails."""

    def __init__(self, tmp_path):
        self.dir = tmp_path
        self.made, self.bad, self.asked = {}, set(), []

    def ready(self, path):
        return self.made.get(path)

    def failed(self, path):
        return path in self.bad

    def busy(self, path):
        return path in self.asked and path not in self.made and path not in self.bad

    def request(self, path):
        if path not in self.asked:
            self.asked.append(path)

    def make(self, path):
        self.made[path] = make_wav(self.dir / ("copy-" + os.path.basename(path) + ".wav"))
        return self.made[path]

    def stop(self):
        pass


@pytest.fixture
def songs(tmp_path):
    return [{"path": make_wav(tmp_path / f"{n}.wav"), "title": n} for n in ("a", "b", "c")]


def make(songs, tmp_path, refuse=()):
    backend = FakeBackend()
    backend.fail_for = set(refuse)            # what "MCI" refuses (the copies are other files)
    c = Controller(backend, prepare=FakePrepare(tmp_path))
    c.set_tracks(songs)
    return c


# ------------------------------------------------------------------------------ the controller
def test_a_refused_song_is_prepared_and_then_that_song_plays(songs, tmp_path):
    c = make(songs, tmp_path, refuse={"b.wav"})
    assert c.play_index(1)
    assert c.state == "preparing" and c.index == 1 and c.current_title() == "b"
    assert c.prepare.asked == [songs[1]["path"]]
    assert c.position_ms() == 0 and c.length_ms() == 0
    c.tick()
    assert c.state == "preparing"                                   # still waiting: nothing else starts
    copy = c.prepare.make(songs[1]["path"])
    c.tick()
    assert c.state == "playing" and c.index == 1 and c.backend.loaded == copy and c.backend.playing
    assert c.error == ""


def test_a_copy_made_earlier_is_used_at_once(songs, tmp_path):
    c = make(songs, tmp_path, refuse={"a.wav"})
    copy = c.prepare.make(songs[0]["path"])
    assert c.play_index(0)
    assert c.state == "playing" and c.backend.loaded == copy and c.prepare.asked == []


def test_when_no_copy_can_be_made_the_next_song_plays_and_the_user_is_told(songs, tmp_path):
    c = make(songs, tmp_path, refuse={"a.wav"})
    c.play_index(0)
    c.prepare.bad.add(songs[0]["path"])
    c.tick()
    assert c.state == "playing" and c.current_title() == "b"
    assert "Çalamadım" in c.error and "a" in c.error


def test_a_song_that_never_plays_does_not_loop_forever(tmp_path):
    only = [{"path": make_wav(tmp_path / "a.wav"), "title": "a"}]
    c = make(only, tmp_path, refuse={"a.wav"})
    c.repeat = "Liste"
    c.play_index(0)
    c.prepare.bad.add(only[0]["path"])
    c.tick()
    assert c.state == "stopped" and c.error == "Çalamadım: a"
    assert not c.play_index(0) and c.state == "stopped"           # known bad: not asked again


def test_pressing_play_pause_while_preparing_stops_it(songs, tmp_path):
    c = make(songs, tmp_path, refuse={"a.wav"})
    c.play_index(0)
    c.toggle()
    assert c.state == "stopped"
    c.prepare.make(songs[0]["path"])
    c.tick()
    assert c.state == "stopped"                                     # a late copy does not start by itself


def test_next_while_preparing_goes_on(songs, tmp_path):
    c = make(songs, tmp_path, refuse={"a.wav"})
    c.play_index(0)
    c.next()
    assert c.state == "playing" and c.current_title() == "b"


def test_a_queued_song_is_prepared_too(songs, tmp_path):
    c = make(songs, tmp_path, refuse={"x.wav"})
    x = {"path": make_wav(tmp_path / "x.wav"), "title": "x"}
    c.play_index(0)
    c.play_next([x])
    c.backend.ended = True
    c.tick()
    assert c.state == "preparing" and c.current_title() == "x"
    c.prepare.make(x["path"])
    c.tick()
    assert c.state == "playing" and c.current_title() == "x"


def test_the_copy_of_the_next_song_is_asked_for_before_the_crossfade(songs, tmp_path):
    c = Controller(FakeBackend(), spare=FakeBackend(), prepare=FakePrepare(tmp_path))
    c.spare.fail_for = {"b.wav"}
    c.set_tracks(songs)
    c.fade_ms = 1000
    c.play_index(0)
    c.backend.position = c.backend.length - 500
    c.tick()
    assert not c.fading and c.prepare.asked == [songs[1]["path"]]   # no fade now, but the copy is coming


def test_without_a_preparer_a_skipped_song_is_named(songs):
    backend = FakeBackend()
    backend.fail_for = {"a.wav"}
    c = Controller(backend)
    c.set_tracks(songs)
    assert c.play_index(0)
    assert c.current_title() == "b" and c.error == "Çalamadım, sıradakine geçtim: a"


# ------------------------------------------------------------------------------ the preparer
def test_the_preparer_makes_a_copy_in_the_background(tmp_path):
    song = make_wav(tmp_path / "a.wav")
    go = threading.Event()

    def run(path, out):
        go.wait(5)
        with open(out, "wb") as f:
            f.write(b"ID3" + b"\0" * 100)
        return True

    p = playable.Preparer(run=run)
    p.request(song)
    p.request(song)                                                 # twice is fine
    assert p.busy(song) and p.ready(song) is None
    go.set()
    for _ in range(100):
        if p.ready(song):
            break
        threading.Event().wait(0.05)
    assert p.ready(song) == playable.copy_path(song) and not p.failed(song)
    assert not os.path.exists(playable.copy_path(song) + ".part")
    p.stop()


def test_the_preparer_remembers_what_failed(tmp_path):
    song = make_wav(tmp_path / "a.wav")
    p = playable.Preparer(run=lambda path, out: False)
    p.request(song)
    for _ in range(100):
        if p.failed(song):
            break
        threading.Event().wait(0.05)
    assert p.failed(song) and p.ready(song) is None and not p.busy(song)
    p.stop()


def test_a_changed_file_gets_a_new_copy(tmp_path):
    song = make_wav(tmp_path / "a.wav")
    first = playable.copy_path(song)
    make_wav(tmp_path / "a.wav", seconds=2)
    os.utime(song, (1, 1))
    assert playable.copy_path(song) != first


def test_the_cache_keeps_below_its_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(playable, "CACHE_LIMIT", 250)
    d = playable.cache_dir()
    for i, name in enumerate(("old.mp3", "mid.mp3", "new.mp3")):
        path = os.path.join(d, name)
        with open(path, "wb") as f:
            f.write(b"x" * 100)
        os.utime(path, (1000 + i, 1000 + i))
    playable._prune(os.path.join(d, "old.mp3"))                     # the one just made is never deleted
    assert sorted(os.listdir(d)) == ["new.mp3", "old.mp3"]


def test_mp3_sound_is_copied_and_other_sound_converted():
    same = playable.make_args("in.mp3", "out", "mp3")
    assert same[same.index("-c:a") + 1] == "copy" and "-vn" in same          # the sound as it is, no picture
    other = playable.make_args("in.mp4", "out", "opus")
    assert "libmp3lame" in other and "-b:a" in other and "-q:a" not in other   # constant rate: right length


# ------------------------------------------------------------------------------ real files, real MCI
@pytest.fixture
def big_cover(tmp_path):
    """A noisy picture: as JPEG it is far bigger than the ~128 KB MCI copes with."""
    jpg = str(tmp_path / "big.jpg")
    ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=1000x1000", "-vf", "noise=alls=100:allf=t",
           "-frames:v", "1", "-q:v", "2", jpg)
    assert os.path.getsize(jpg) > 200_000
    return jpg


def _sine(tmp_path, name, *codec):
    out = str(tmp_path / name)
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=20", *codec, out)
    return out


def _play_for_real(path):
    """Like the app: MCI first, a copy when it refuses. Returns (state, length ms) once it sounds."""
    p = playable.Preparer()
    c = Controller(player.MciBackend(alias="test_playable"), prepare=p)
    c.set_volume(0)
    c.set_tracks([{"path": path, "title": "t"}])
    try:
        c.play_index(0)
        for _ in range(600):
            if c.state != "preparing":
                break
            c.tick()
            threading.Event().wait(0.05)
        return c.state, c.length_ms()
    finally:
        c.stop()
        p.stop()


@needs_ffmpeg
@pytest.mark.skipif(not player.MciBackend.available(), reason="needs Windows MCI")
def test_an_mp3_with_a_big_cover_plays(tmp_path, big_cover):
    sound = _sine(tmp_path, "s.mp3", "-c:a", "libmp3lame", "-b:a", "192k")
    song = str(tmp_path / "with cover.mp3")
    ffmpeg("-i", sound, "-i", big_cover, "-map", "0:a", "-map", "1:v", "-c", "copy", "-id3v2_version", "3",
           "-disposition:v", "attached_pic", song)
    mci = player.MciBackend(alias="test_refuse")
    assert not mci.load(song)                                       # the bug: Windows refuses it
    state, length = _play_for_real(song)
    assert state == "playing" and abs(length - 20_000) < 1500
    assert os.path.getsize(song) > os.path.getsize(sound)            # the user's file was not touched


@needs_ffmpeg
@pytest.mark.skipif(not player.MciBackend.available(), reason="needs Windows MCI")
def test_a_video_with_opus_sound_plays_with_the_right_length(tmp_path):
    song = _sine(tmp_path, "v.mp4", "-c:a", "libopus")
    assert not player.MciBackend(alias="test_refuse").load(song)
    state, length = _play_for_real(song)
    assert state == "playing" and abs(length - 20_000) < 1500       # VBR would show a wrong length


# ------------------------------------------------------------------------------ new downloads
@needs_ffmpeg
def test_a_downloaded_cover_is_kept_small_enough(tmp_path, big_cover, monkeypatch):
    with open(big_cover, "rb") as f:
        data = f.read()
    monkeypatch.setattr(ve, "_download_small", lambda url, headers=None: data)
    item = Item("https://example.com/v", kind="audio", folder=str(tmp_path))
    jpg = ve.fetch_cover({"thumbnail": "https://example.com/t.jpg"}, item)
    try:
        assert jpg and os.path.getsize(jpg) <= ve.COVER_MAX_BYTES
    finally:
        ve.discard_cover(jpg)
