"""The music player's logic: saved playlists, the play queue (with a fake backend) and the real
Windows MCI backend (silent: volume 0)."""
import json
import os
import random
import sys
import time

import pytest

from app import player
from app.player import Controller
from app.playlists import SMART, DEFAULT_NAME, PlaylistStore
from media_support import ffmpeg, needs_ffmpeg
from music_support import FakeBackend, make_wav


@pytest.fixture
def songs(tmp_path):
    return [make_wav(tmp_path / f"{n}.wav") for n in ("a", "b", "c", "d")]


@pytest.fixture
def store(tmp_path):
    return PlaylistStore(str(tmp_path / "playlists.json"))


def tracks_of(store, name):
    return [t["title"] for t in store.tracks(name)]


# ------------------------------------------------------------------------------ playlists
def test_a_new_store_has_one_empty_list(store):
    assert store.user_names() == [DEFAULT_NAME] and store.state["last"] == DEFAULT_NAME
    assert store.names() == [DEFAULT_NAME, *SMART]                          # the smart lists always come last
    assert store.tracks(DEFAULT_NAME) == []


def test_lists_are_created_renamed_and_deleted_in_order(store):
    a = store.create("Spor")
    b = store.create("Spor")                             # the same name is made unique
    assert (a, b) == ("Spor", "Spor (2)")
    assert store.rename("Spor", "Koşu") == "Koşu"
    assert store.user_names() == [DEFAULT_NAME, "Koşu", "Spor (2)"]
    assert store.rename("Koşu", "  ") == "Koşu"              # an empty name changes nothing
    assert store.rename("Koşu", "Spor (2)") == "Spor (2) (2)"   # never overwrites another list
    store.state["last"] = "Spor (2) (2)"
    assert store.delete("Spor (2) (2)") == DEFAULT_NAME      # the neighbour becomes current
    assert store.delete("Spor (2)") == DEFAULT_NAME
    assert store.delete(DEFAULT_NAME) == DEFAULT_NAME        # the last list is emptied, not removed
    assert store.user_names() == [DEFAULT_NAME]


def test_only_existing_audio_files_are_added(store, songs, tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    n = store.add(DEFAULT_NAME, songs[:2] + [str(tmp_path / "notes.txt"), str(tmp_path / "missing.mp3")])
    assert n == 2 and tracks_of(store, DEFAULT_NAME) == ["a", "b"]
    assert store.tracks(DEFAULT_NAME)[0]["path"] == os.path.abspath(songs[0])


def test_a_folder_is_added_with_its_subfolders(store, tmp_path):
    (tmp_path / "album").mkdir()
    make_wav(tmp_path / "album" / "z.wav")
    make_wav(tmp_path / "b.wav")
    make_wav(tmp_path / "A.wav")
    assert store.add_folder(DEFAULT_NAME, str(tmp_path)) == 3
    assert tracks_of(store, DEFAULT_NAME) == ["A", "b", "z"] or sorted(tracks_of(store, DEFAULT_NAME)) == ["A", "b", "z"]
    store.clear(DEFAULT_NAME)
    assert store.add_folder(DEFAULT_NAME, str(tmp_path), recursive=False) == 2


def test_tracks_move_as_a_block_and_stop_at_the_ends(store, songs):
    store.add(DEFAULT_NAME, songs)
    assert store.move(DEFAULT_NAME, [2, 3], -1) == [1, 2]
    assert tracks_of(store, DEFAULT_NAME) == ["a", "c", "d", "b"]
    assert store.move(DEFAULT_NAME, [0, 1], -1) == [0, 1]            # already at the top: nothing moves
    assert tracks_of(store, DEFAULT_NAME) == ["a", "c", "d", "b"]
    assert store.move(DEFAULT_NAME, [1], +1) == [2]
    assert tracks_of(store, DEFAULT_NAME) == ["a", "d", "c", "b"]
    assert store.move(DEFAULT_NAME, [3], +1) == [3]
    assert store.move(DEFAULT_NAME, [], +1) == []


def test_tracks_are_removed_by_index(store, songs):
    store.add(DEFAULT_NAME, songs)
    store.remove(DEFAULT_NAME, [0, 2, 99])
    assert tracks_of(store, DEFAULT_NAME) == ["b", "d"]


def test_everything_survives_a_restart(store, songs, tmp_path):
    other = store.create("Gece")
    store.add(other, songs[:2])
    store.set_state(last=other, volume=35, shuffle=True, repeat="Liste", resume_list=other,
                    resume_path=songs[1], resume_ms=61000, ask_list="Gece")
    again = PlaylistStore(str(tmp_path / "playlists.json"))
    assert again.user_names() == [DEFAULT_NAME, "Gece"] and tracks_of(again, "Gece") == ["a", "b"]
    assert again.state == {"last": "Gece", "volume": 35, "shuffle": True, "repeat": "Liste", "resume_list": "Gece",
                           "resume_path": songs[1], "resume_ms": 61000, "ask_list": "Gece", "fade": 0,
                           "searches": [], "eq": [0] * 8, "level": False,
                           "rename_pattern": "{sanatçı} - {şarkı}", "mini_top": True, "mini_place": ""}


def test_a_damaged_file_is_ignored(tmp_path):
    path = tmp_path / "playlists.json"
    path.write_text("{not json", encoding="utf-8")
    assert PlaylistStore(str(path)).user_names() == [DEFAULT_NAME]
    path.write_text(json.dumps({"playlists": {"ok": [{"path": "x.mp3", "title": "x"}, 5, {"path": 1}],
                                              "": [], "bad": "no"},
                                "state": {"volume": 500, "repeat": "Garip", "shuffle": "yes"}}), encoding="utf-8")
    s = PlaylistStore(str(path))
    assert s.user_names() == ["ok"] and tracks_of(s, "ok") == ["x"]
    assert s.state["volume"] == 100 and s.state["repeat"] == "Kapalı" and s.state["shuffle"] is False


# ------------------------------------------------------------------------------ tags and downloads
def test_a_track_is_labelled_from_its_tags_or_its_file_name():
    plain = {"path": "x.mp3", "title": "dosya adi"}
    assert player.track_label(plain) == "dosya adi"
    assert player.track_label({**plain, "tag_title": "Parça", "artist": "Sanatçı"}) == "Sanatçı – Parça"
    assert player.track_label({**plain, "tag_title": "Parça"}) == "Parça"
    assert player.track_label({**plain, "artist": "Sanatçı"}) == "Sanatçı – dosya adi"


def test_tags_reach_every_track_with_that_file_in_any_list(store, songs):
    other = store.create("Başka")
    store.add(DEFAULT_NAME, songs[:2])
    store.add(other, songs[:1])
    info = {"title": "Güzel", "artist": "Biri", "album": "Alb", "duration": 61000}
    assert store.apply_tags({songs[0].upper() if os.name == "nt" else songs[0]: info}) is True
    for name in (DEFAULT_NAME, other):
        t = store.tracks(name)[0]
        assert (t["tag_title"], t["artist"], t["album"], t["duration"], t["probed"]) == ("Güzel", "Biri", "Alb", 61000, True)
    assert "artist" not in store.tracks(DEFAULT_NAME)[1]                 # the other file is untouched
    assert store.apply_tags({songs[0]: info}) is False                   # nothing new: nothing written
    assert store.apply_tags({songs[1]: {}}) is True                      # an empty answer still marks it as read
    assert store.tracks(DEFAULT_NAME)[1] == {**store.tracks(DEFAULT_NAME)[1], "probed": True}
    assert "artist" not in store.tracks(DEFAULT_NAME)[1]


def test_tags_are_saved_and_come_back(store, songs, tmp_path):
    store.add(DEFAULT_NAME, songs[:1])
    store.apply_tags({songs[0]: {"title": "T", "artist": "A", "duration": 5000}})
    again = PlaylistStore(str(tmp_path / "playlists.json"))
    t = again.tracks(DEFAULT_NAME)[0]
    assert t["tag_title"] == "T" and t["artist"] == "A" and t["duration"] == 5000 and t["probed"] is True


def test_wrongly_typed_fields_in_the_file_are_dropped(tmp_path):
    path = tmp_path / "playlists.json"
    path.write_text(json.dumps({"playlists": {"x": [
        {"path": "a.mp3", "title": "a", "artist": 5, "duration": "long", "album": "", "probed": "yes", "added": True},
        {"path": "b.mp3", "title": "b", "artist": "Ok", "duration": 1500, "probed": True, "added": 12.5, "junk": 1}]}}),
        encoding="utf-8")
    first, second = PlaylistStore(str(path)).tracks("x")
    assert first == {"path": "a.mp3", "title": "a"}
    assert second == {"path": "b.mp3", "title": "b", "artist": "Ok", "duration": 1500, "probed": True, "added": 12.5}


def test_a_finished_download_is_added_once_and_only_if_it_is_music(store, tmp_path):
    song = make_wav(tmp_path / "Gelen.wav")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x" * 10)
    assert store.add_download("İndirilenler", song, 1.0) is True
    assert store.add_download("İndirilenler", song, 2.0) is False        # already there
    assert store.add_download("İndirilenler", str(video), 3.0) is False  # a video is not music
    assert store.add_download("İndirilenler", str(tmp_path / "gone.mp3"), 4.0) is False
    assert store.add_download("İndirilenler", str(tmp_path / "notes.txt"), 5.0) is False
    assert tracks_of(store, "İndirilenler") == ["Gelen"] and "İndirilenler" in store.names()


def test_downloads_keep_the_order_they_were_started_in(store, tmp_path):
    files = {n: make_wav(tmp_path / f"{n}.wav") for n in "abcde"}
    for name, added in (("c", 3.0), ("a", 1.0), ("e", 5.0), ("b", 2.0), ("d", 4.0)):     # finish out of order
        store.add_download("Liste", files[name], added)
    assert tracks_of(store, "Liste") == ["a", "b", "c", "d", "e"]
    manual = make_wav(tmp_path / "mine.wav")
    store.add("Liste", [manual])                                          # a track the user added by hand
    late = make_wav(tmp_path / "late.wav")
    store.add_download("Liste", late, 0.5)                                # before everything that was downloaded
    assert tracks_of(store, "Liste")[0] == "late"
    store.move("Liste", [0], +1)                                          # the user re-orders: later downloads still land sanely
    after = make_wav(tmp_path / "after.wav")
    store.add_download("Liste", after, 99.0)
    assert tracks_of(store, "Liste")[-1] == "after"


def test_ensure_trims_limits_and_defaults_the_name(store):
    assert store.ensure("  Gece  ") == "Gece" and store.ensure("Gece") == "Gece"
    assert store.names().count("Gece") == 1
    assert store.ensure("") == "İndirilenler" and store.ensure("   ") == "İndirilenler"
    assert len(store.ensure("x" * 200)) == 80


def test_the_total_length_of_a_list(store, songs):
    store.add(DEFAULT_NAME, songs[:3])
    assert store.total_ms(DEFAULT_NAME) == (0, False)
    store.apply_tags({songs[0]: {"duration": 60000}, songs[1]: {"duration": 90000}})
    assert store.total_ms(DEFAULT_NAME) == (150000, False)               # one length is still unknown
    store.apply_tags({songs[2]: {"duration": 30000}})
    assert store.total_ms(DEFAULT_NAME) == (180000, True)
    assert store.total_ms("nope") == (0, True)


def test_the_queue_shows_the_tag_title(songs):
    c, b = make_controller(songs)
    c.tracks[0]["tag_title"], c.tracks[0]["artist"] = "Parça", "Sanatçı"
    c.play_index(0)
    assert c.current_title() == "Sanatçı – Parça" and c.current_track() is c.tracks[0]
    assert Controller(FakeBackend()).current_track() is None


# ------------------------------------------------------------------------------ queue
def make_controller(songs, **kw):
    backend = FakeBackend()
    c = Controller(backend, rng=random.Random(1))
    c.set_tracks([{"path": p, "title": os.path.basename(p)} for p in songs])
    for k, v in kw.items():
        setattr(c, k, v)
    return c, backend


def test_play_pause_resume_stop(songs):
    c, b = make_controller(songs)
    c.toggle()
    assert c.state == "playing" and c.index == 0 and b.loaded == os.path.abspath(songs[0]) or b.loaded == songs[0]
    c.toggle()
    assert c.state == "paused" and not b.playing
    c.toggle()
    assert c.state == "playing" and b.playing
    c.stop()
    assert c.state == "stopped" and b.loaded is None and c.position_ms() == 0


def test_tracks_play_in_order_and_the_list_ends(songs):
    c, b = make_controller(songs)
    c.play_index(2)
    b.ended = True
    c.tick()
    assert c.index == 3
    b.ended = True
    c.tick()
    assert c.state == "stopped"                                # repeat off: the end of the list stops


def test_repeat_modes(songs):
    c, b = make_controller(songs, repeat="Liste")
    c.play_index(3)
    b.ended = True
    c.tick()
    assert c.index == 0 and c.state == "playing"               # the whole list starts again
    c.repeat = "Tek"
    b.ended = True
    c.tick()
    assert c.index == 0                                        # the same track again
    c.next()                                                   # the user's own 'next' still moves on
    assert c.index == 1


def test_next_and_previous_buttons_wrap_around(songs):
    c, b = make_controller(songs)
    c.play_index(3)
    c.next()
    assert c.index == 0
    c.previous(position_ms=0)
    assert c.index == 3
    b.position = 10000
    c.previous(position_ms=10000)                               # late in a track: restart it
    assert c.index == 3 and b.position == 0


def test_shuffle_plays_every_track_once_per_round(songs):
    c, b = make_controller(songs, shuffle=True)
    c.play_index(0)
    seen = [c.index]
    for _ in range(3):
        b.ended = True
        c.tick()
        seen.append(c.index)
    assert sorted(seen) == [0, 1, 2, 3]
    b.ended = True
    c.tick()
    assert c.state == "stopped"                                # repeat off: the round is over
    c.repeat = "Liste"
    c.play_index(0)
    for _ in range(8):
        b.ended = True
        c.tick()
    assert c.state == "playing"


def test_previous_in_shuffle_goes_back_through_what_was_played(songs):
    c, b = make_controller(songs, shuffle=True)
    c.play_index(0)
    order = [c.index]
    for _ in range(2):
        c.next()
        order.append(c.index)
    c.previous(position_ms=0)
    assert c.index == order[1]
    c.previous(position_ms=0)
    assert c.index == order[0]


def test_a_missing_file_is_skipped(songs):
    c, b = make_controller(songs)
    os.remove(songs[1])
    c.play_index(1)
    assert c.index == 2 and c.state == "playing"
    c, b = make_controller(songs)
    for p in songs:
        if os.path.exists(p):
            os.remove(p)
    c.play_index(0)
    assert c.state == "stopped" and "Çalamadım" in c.error


def test_a_file_the_backend_refuses_is_skipped(songs):
    c, b = make_controller(songs)
    b.fail_for = {"a.wav"}
    c.play_index(0)
    assert c.index == 1 and c.state == "playing"


def test_replacing_the_queue_keeps_the_current_track_when_it_is_still_there(songs):
    c, b = make_controller(songs)
    c.play_index(2)
    extra = [{"path": songs[3], "title": "d"}, {"path": songs[2], "title": "c"}]
    c.set_tracks(extra, keep_current=True)
    assert c.index == 1 and c.state == "playing"
    c.set_tracks(extra[:1], keep_current=True)                   # the playing one was removed
    assert c.index == -1 and c.state == "stopped"


def test_seek_uses_a_fraction_of_the_length(songs):
    c, b = make_controller(songs)
    c.seek_fraction(0.5)
    assert b.position == 0                                      # nothing is playing yet
    c.toggle()
    c.seek_fraction(0.5)
    assert b.position == 2500
    c.seek_fraction(7)
    assert b.position == 5000


def test_an_empty_queue_does_nothing():
    c = Controller(FakeBackend())
    c.toggle()
    c.next()
    c.previous()
    assert c.state == "stopped" and c.current_title() == ""


# ------------------------------------------------------------------------------ real MCI
windows_only = pytest.mark.skipif(not sys.platform.startswith("win"), reason="MCI is a Windows API")


@pytest.fixture
def mci():
    if not player.MciBackend.available():
        pytest.skip("winmm is not available")
    backend = player.MciBackend()
    backend.set_volume(0)                                       # tests must be silent
    yield backend
    backend.close()


def open_or_skip(backend, path):
    if not backend.load(path):
        pytest.skip(f"no audio device / codec for MCI: {backend.last_error}")


@windows_only
def test_mci_plays_pauses_seeks_and_finishes(mci, tmp_path):
    open_or_skip(mci, make_wav(tmp_path / "s.wav", seconds=1.5))
    assert 1400 <= mci.length_ms() <= 1600
    mci.play()
    time.sleep(0.4)
    assert mci.is_playing() and 200 <= mci.position_ms() <= 900
    mci.pause()
    frozen = mci.position_ms()
    time.sleep(0.3)
    assert not mci.is_playing() and mci.position_ms() == frozen
    mci.resume()
    mci.seek(1200)
    assert mci.position_ms() >= 1200 and mci.is_playing()
    deadline = time.time() + 5
    while time.time() < deadline and not mci.finished():
        time.sleep(0.05)
    assert mci.finished()
    mci.stop()
    assert mci.position_ms() == 0 and not mci.finished()


@windows_only
def test_mci_refuses_a_file_that_is_not_audio(mci, tmp_path):
    bad = tmp_path / "x.mp3"
    bad.write_bytes(b"this is not an mp3 at all" * 10)
    assert mci.load(str(bad)) is False and mci.last_error
    assert mci.position_ms() == 0 and not mci.is_playing()


@windows_only
def test_mci_handles_a_path_with_unusual_characters(mci, tmp_path):
    folder = tmp_path / "Müzik şğü İ"
    folder.mkdir()
    open_or_skip(mci, make_wav(folder / "şarkı (1).wav"))
    mci.play()
    assert mci.is_playing()


@windows_only
@needs_ffmpeg
def test_mci_plays_an_mp3(mci, tmp_path):
    mp3 = str(tmp_path / "t.mp3")
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=1.2", "-c:a", "libmp3lame", mp3)
    open_or_skip(mci, mp3)
    assert 1000 <= mci.length_ms() <= 1500
    mci.play()
    time.sleep(0.3)
    assert mci.is_playing()


@windows_only
def test_the_controller_drives_the_real_backend(mci, tmp_path):
    first = make_wav(tmp_path / "1.wav", seconds=0.6)
    second = make_wav(tmp_path / "2.wav", seconds=0.6)
    c = Controller(mci)
    c.set_tracks([{"path": first, "title": "1"}, {"path": second, "title": "2"}])
    c.toggle()
    if c.state != "playing":
        pytest.skip(f"no audio device: {mci.last_error}")
    deadline = time.time() + 5
    while time.time() < deadline and c.index == 0:
        c.tick()
        time.sleep(0.05)
    assert c.index == 1                                          # moved on by itself
    while time.time() < deadline and c.state == "playing":
        c.tick()
        time.sleep(0.05)
    assert c.state == "stopped"                                   # and the list ended
