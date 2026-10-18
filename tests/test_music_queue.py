"""The player's "play next" line and cross-fading between songs (no window, fake backends, a fake clock)."""
import pytest
from music_support import FakeBackend, make_wav

from app.player import Controller


@pytest.fixture
def songs(tmp_path):
    return [{"path": make_wav(tmp_path / f"{n}.wav"), "title": n} for n in ("a", "b", "c", "d")]


@pytest.fixture
def extra(tmp_path):
    return [{"path": make_wav(tmp_path / f"x{n}.wav"), "title": f"x{n}"} for n in (1, 2)]


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def make(songs, spare=False, clock=None):
    c = Controller(FakeBackend(), spare=FakeBackend() if spare else None, clock=clock or Clock())
    c.set_tracks(songs)
    return c


def finish(c):
    c.backend.ended = True
    c.tick()


# ------------------------------------------------------------------------------ play next / add to the line
def test_a_song_played_next_comes_before_the_list_goes_on(songs, extra):
    c = make(songs)
    c.play_index(0)
    c.play_next([extra[0]])
    finish(c)
    assert c.current_title() == "x1" and c.extra is not None and c.index == 0
    finish(c)
    assert c.current_title() == "b"                                       # the list goes on where it was


def test_the_line_keeps_its_order_and_play_next_jumps_ahead(songs, extra):
    c = make(songs)
    c.play_index(0)
    c.add_to_queue([extra[0]])
    c.add_to_queue([extra[1]])
    c.play_next([songs[3]])
    order = []
    for _ in range(4):
        finish(c)
        order.append(c.current_title())
    assert order == ["d", "x1", "x2", "b"]


def test_next_by_hand_also_takes_the_line(songs, extra):
    c = make(songs)
    c.play_index(1)
    c.add_to_queue(extra)
    c.next()
    assert c.current_title() == "x1"


def test_previous_from_a_lined_up_song_goes_back_to_the_list(songs, extra):
    c = make(songs)
    c.play_index(2)
    c.play_next([extra[0]])
    c.next()
    c.previous()
    assert c.current_title() == "c" and c.extra is None


def test_a_deleted_lined_up_file_is_skipped(songs, extra):
    import os
    c = make(songs)
    c.play_index(0)
    c.add_to_queue(extra)
    os.remove(extra[0]["path"])
    finish(c)
    assert c.current_title() == "x2"


def test_editing_the_list_keeps_a_lined_up_song_playing(songs, extra):
    c = make(songs)
    c.play_index(1)
    c.play_next([extra[0]])
    c.next()
    c.set_tracks(songs[:2], keep_current=True)
    assert c.state == "playing" and c.current_title() == "x1"


def test_repeat_one_repeats_a_lined_up_song_too(songs, extra):
    c = make(songs)
    c.repeat = "Tek"
    c.play_index(0)
    c.play_next([extra[0]])
    c.next()
    finish(c)
    assert c.current_title() == "x1"


def test_stopping_keeps_the_line_but_forgets_the_lined_up_song(songs, extra):
    c = make(songs)
    c.play_index(0)
    c.add_to_queue(extra)
    c.next()
    c.stop()
    assert c.extra is None and [t["title"] for t in c.queue] == ["x2"]


# ------------------------------------------------------------------------------ cross-fade
def test_without_a_second_player_there_is_no_cross_fade(songs):
    c = make(songs)
    c.fade_ms = 4000
    c.play_index(0)
    c.backend.position = c.backend.length - 1000
    c.tick()
    assert not c.fading and c.current_title() == "a"


def test_near_the_end_the_next_song_fades_in_while_this_one_fades_out(songs):
    clock = Clock()
    c = make(songs, spare=True, clock=clock)
    c.fade_ms = 4000
    c.backend.length = 20000
    c.set_volume(60)
    c.play_index(0)
    first = c.backend
    first.position = 15000                                            # 5 s left: not yet
    c.tick()
    assert not c.fading
    first.position = 16500                                            # 3.5 s left: starts
    c.spare.length = 20000
    c.tick()
    second = c.backend
    assert c.fading and second is not first and c.current_title() == "b" and second.playing
    assert second.volume == 0 and first.playing
    clock.now += 2.0
    c.tick()
    assert second.volume == 30 and first.volume == 30                 # half way
    clock.now += 2.5
    c.tick()
    assert not c.fading and second.volume == 60 and first.loaded is None   # the old song is closed
    assert c.spare is first                                            # ready for the next fade


def test_a_fade_is_finished_at_once_by_a_jump_or_a_stop(songs):
    clock = Clock()
    c = make(songs, spare=True, clock=clock)
    c.fade_ms = 4000
    c.backend.length = 20000
    c.play_index(0)
    c.backend.position = 17000
    c.spare.length = 20000
    c.tick()
    old = c.spare
    assert c.fading
    c.next()                                                          # the user presses next mid-fade
    assert not c.fading and old.loaded is None and c.current_title() == "c" and c.backend.volume == c.volume


def test_short_songs_and_the_end_of_the_list_are_not_faded(songs):
    c = make(songs, spare=True)
    c.fade_ms = 4000
    c.backend.length = 9000                                           # shorter than 3 fades
    c.play_index(0)
    c.backend.position = 8000
    c.tick()
    assert not c.fading
    c2 = make(songs, spare=True)
    c2.fade_ms = 4000
    c2.backend.length = 20000
    c2.play_index(3)                                                  # the last song, repeat off
    c2.backend.position = 19000
    c2.tick()
    assert not c2.fading


def test_the_volume_slider_does_not_jump_a_fade(songs):
    clock = Clock()
    c = make(songs, spare=True, clock=clock)
    c.fade_ms = 4000
    c.backend.length = 20000
    c.play_index(0)
    c.backend.position = 17000
    c.spare.length = 20000
    c.tick()
    c.set_volume(40)
    assert c.backend.volume == 0                                      # the fade decides the volumes now
    clock.now += 5
    c.tick()
    assert c.backend.volume == 40


def test_cross_fading_into_a_lined_up_song(songs, extra):
    c = make(songs, spare=True)
    c.fade_ms = 3000
    c.backend.length = 20000
    c.play_index(0)
    c.play_next([extra[0]])
    c.backend.position = 18000
    c.spare.length = 20000
    c.tick()
    assert c.fading and c.current_title() == "x1" and c.queue == []
