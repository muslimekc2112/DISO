"""Tags, durations and cover pictures in the music window (a fake reader plays the part of ffprobe)."""
import os
import time
import types

import pytest
from music_support import FakeBackend, FakeReader, make_wav

from app import player, tags
from app.music_ui import fmt_total, square_cover

pytestmark = pytest.mark.gui


@pytest.fixture
def music_app(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app._ensure_music()
    return app, app.music


@pytest.fixture
def songs(tmp_path):
    return [make_wav(tmp_path / f"{n}.wav") for n in ("Sabah", "Ogle", "Aksam")]


@pytest.fixture
def jpg(tmp_path):
    from PIL import Image
    path = tmp_path / "cover.jpg"
    Image.new("RGB", (300, 200), (200, 80, 20)).save(path)
    return str(path)


def add(music, paths):
    music._pick_files = lambda: paths
    music._add_files()


def rows(music):
    return [music.tree.item(i, "values") for i in music.tree.get_children()]


def settle(music):
    music._drain_reader()
    music.update()


# ------------------------------------------------------------------------------ asking
def test_new_tracks_are_sent_to_the_reader_once_each(music_app, songs):
    app, music = music_app
    add(music, songs)
    assert sorted(music.reader.tag_requests) == sorted(os.path.abspath(p) for p in songs)
    music.reader.tag_requests.clear()
    music._refresh_tracks()                                    # shown again, still unread: asked again
    assert len(music.reader.tag_requests) == 3
    music.store.apply_tags({songs[0]: {}, songs[1]: {}})       # two are read (even if empty)
    music.reader.tag_requests.clear()
    music._refresh_tracks()
    assert music.reader.tag_requests == [os.path.abspath(songs[2])]


def test_the_window_starts_its_own_reader_and_stops_it(app, monkeypatch):
    made = []

    class Spy(FakeReader):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            made.append(self)

    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", Spy)
    app._ensure_music()
    assert len(made) == 1 and app.music.reader is made[0]
    app.music.shutdown()
    assert made[0].stopped is True


# ------------------------------------------------------------------------------ answers
def test_answers_fill_the_table_the_count_and_the_total(music_app, songs):
    app, music = music_app
    add(music, songs)
    assert rows(music)[0] == ("1", "Sabah", "", "") and music.count_label.cget("text") == "3 parça"
    music.reader.answer_tags(songs[0], title="Sabah Güneşi", artist="Ece", album="Gün", duration=204000)
    music.reader.answer_tags(songs[1], title="", artist="Ece", album="", duration=60000)
    settle(music)
    assert rows(music)[0] == ("1", "Sabah Güneşi", "Ece", "3:24")
    assert rows(music)[1] == ("2", "Ogle", "Ece", "1:00")                 # no title tag: the file name stays
    assert music.count_label.cget("text") == "3 parça"                      # one length is still unknown
    music.reader.answer_tags(songs[2], title="", artist="", album="", duration=96000)
    settle(music)
    assert music.count_label.cget("text") == "3 parça • 6 dk"


def test_a_long_list_shows_hours(music_app, songs):
    app, music = music_app
    add(music, songs)
    for p in songs:
        music.reader.answer_tags(p, duration=25 * 60000)
    settle(music)
    assert music.count_label.cget("text") == "3 parça • 1 sa 15 dk"
    assert fmt_total(59 * 60000 + 59000) == "59 dk" and fmt_total(0) == "0 dk" and fmt_total(-5) == "0 dk"


def test_the_answers_are_remembered_in_the_file_but_written_once(music_app, songs, monkeypatch):
    app, music = music_app
    add(music, songs)
    writes = []
    music.store.save = lambda: writes.append(1)
    for p in songs:                                             # the answers trickle in
        music.reader.answer_tags(p, title="T", duration=1000)
        music._drain_reader()
    assert writes == []                                         # nothing is written while they arrive
    time.sleep(1.8)
    app.update()
    assert writes == [1]
    music.reader.answer_tags(songs[0], title="T", duration=1000)       # an answer that changes nothing
    music._drain_reader()
    time.sleep(1.8)
    app.update()
    assert writes == [1]


def test_an_answer_keeps_the_selection(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set(["1", "2"])
    music.reader.answer_tags(songs[0], title="X", duration=2000)
    music.reader.answer_tags(songs[1], title="Y", duration=3000)
    settle(music)
    assert music._selected() == [1, 2] and rows(music)[1][1] == "Y"


def test_answers_for_files_that_are_gone_or_in_another_list_do_no_harm(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.reader.answer_tags(os.path.join(os.path.dirname(songs[0]), "never.wav"), title="Ghost", duration=1)
    music._remove_selected()
    music.tree.selection_set(["0"])
    music._remove_selected()                                    # the first track is removed ...
    music.reader.answer_tags(songs[0], title="Late", duration=1)            # ... and its answer arrives later
    settle(music)
    assert [r[1] for r in rows(music)] == ["Ogle", "Aksam"]
    other = music.store.create("Başka")
    music.store.add(other, songs[:1])
    music.reader.answer_tags(songs[0], title="Elsewhere", duration=1000)
    settle(music)
    assert music.store.tracks(other)[0]["tag_title"] == "Elsewhere"          # the other list learned it too
    assert [r[1] for r in rows(music)] == ["Ogle", "Aksam"]                 # the shown one is unchanged


# ------------------------------------------------------------------------------ now playing
def play(music, index):
    music.tree.selection_set([str(index)])
    music._play_selected()


def test_the_title_artist_and_album_of_the_playing_track(music_app, songs):
    app, music = music_app
    add(music, songs)
    play(music, 0)
    assert music.now_label.cget("text") == "Sabah" and music.sub_label.cget("text").strip() == ""
    music.reader.answer_tags(songs[0], title="Sabah Güneşi", artist="Ece", album="Gün Doğumu", duration=5000)
    settle(music)
    assert music.now_label.cget("text") == "Ece – Sabah Güneşi"
    assert music.sub_label.cget("text") == "Ece • Gün Doğumu"
    music._toggle()
    assert music.now_label.cget("text") == "⏸  Ece – Sabah Güneşi"
    music._stop()
    assert music.now_label.cget("text") == "Şu an bir şey çalmıyor" and music.sub_label.cget("text").strip() == ""


def test_a_track_with_only_an_artist_or_only_an_album(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.reader.answer_tags(songs[0], artist="Yalnız Sanatçı")
    music.reader.answer_tags(songs[1], album="Yalnız Albüm")
    settle(music)
    play(music, 0)
    assert music.now_label.cget("text") == "Yalnız Sanatçı – Sabah" and music.sub_label.cget("text") == "Yalnız Sanatçı"
    play(music, 1)
    assert music.now_label.cget("text") == "Ogle" and music.sub_label.cget("text") == "Yalnız Albüm"


# ------------------------------------------------------------------------------ cover
def shown_cover(music):
    return music._cover_image is not None


def test_the_cover_is_asked_for_and_shown_when_it_arrives(music_app, songs, jpg):
    app, music = music_app
    add(music, songs)
    assert not shown_cover(music) and music.cover_label.cget("text") == "♪"
    play(music, 0)
    assert music.reader.cover_requests == [songs[0]] or music.reader.cover_requests == [os.path.abspath(songs[0])]
    music.reader.answer_cover(music.reader.cover_requests[0], jpg)
    settle(music)
    assert shown_cover(music) and music.cover_label.cget("text") == ""


def test_the_previous_cover_is_not_shown_for_the_next_track(music_app, songs, jpg):
    app, music = music_app
    add(music, songs)
    play(music, 0)
    first = music.reader.cover_requests[0]
    music.reader.answer_cover(first, jpg)
    settle(music)
    assert shown_cover(music)
    play(music, 1)                                              # another track: placeholder until its own cover
    assert not shown_cover(music) and music.cover_label.cget("text") == "♪"
    music.reader.answer_cover(first, jpg)                       # a late answer for the old track is ignored
    settle(music)
    assert not shown_cover(music)
    second = music.reader.cover_requests[-1]
    music.reader.answer_cover(second, None)                     # this one has no picture
    settle(music)
    assert not shown_cover(music)
    play(music, 0)                                              # back to the first: remembered, no new request
    count = len(music.reader.cover_requests)
    assert shown_cover(music) and len(music.reader.cover_requests) == count


def test_a_damaged_cover_picture_means_the_placeholder(music_app, songs, tmp_path):
    app, music = music_app
    add(music, songs)
    play(music, 0)
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a picture")
    music.reader.answer_cover(music.reader.cover_requests[0], str(bad))
    settle(music)
    assert not shown_cover(music) and music.cover_label.cget("text") == "♪"


def test_stopping_clears_the_cover(music_app, songs, jpg):
    app, music = music_app
    add(music, songs)
    play(music, 0)
    music.reader.answer_cover(music.reader.cover_requests[0], jpg)
    settle(music)
    music._stop()
    assert not shown_cover(music) and music.cover_label.cget("text") == "♪"


def test_the_cover_is_cut_to_a_square(jpg, tmp_path):
    img = square_cover(jpg)
    assert img.size == (224, 224)
    assert square_cover(str(tmp_path / "missing.jpg")) is None


# ------------------------------------------------------------------------------ outside changes
def test_lists_changed_from_outside_show_up_and_keep_playing(music_app, songs):
    app, music = music_app
    add(music, songs[:2])
    play(music, 1)
    music.tree.selection_set(["0"])
    music.store.lists[music.viewed].insert(0, {"path": songs[2], "title": "Aksam"})      # e.g. a finished download
    music.reload()
    assert [r[1] for r in rows(music)] == ["Aksam", "Sabah", "Ogle"]
    assert music.controller.state == "playing" and music.controller.current_title() == "Ogle"
    assert music.controller.index == 2 and rows(music)[2][0] == "▶"
    assert music._selected() == [0]
    music.store.create("Yeni")
    music.reload()
    assert "Yeni" in music.list_menu.cget("values")


def test_reload_after_the_window_closed_does_nothing(music_app, songs):
    app, music = music_app
    music.shutdown()
    music.reload()


# ------------------------------------------------------------------------------ keys and mouse
def test_double_click_plays_the_row_under_the_mouse(music_app, songs, monkeypatch):
    app, music = music_app
    add(music, songs)
    monkeypatch.setattr(music.tree, "identify_region", lambda x, y: "cell")
    monkeypatch.setattr(music.tree, "identify_row", lambda y: "2")
    music._on_double_click(types.SimpleNamespace(x=10, y=10))
    assert music.controller.index == 2 and music.controller.state == "playing"
    monkeypatch.setattr(music.tree, "identify_region", lambda x, y: "heading")
    music._on_double_click(types.SimpleNamespace(x=10, y=10))               # a click on the header does nothing
    assert music.controller.index == 2
    monkeypatch.setattr(music.tree, "identify_region", lambda x, y: "cell")
    monkeypatch.setattr(music.tree, "identify_row", lambda y: "")           # empty space under the rows
    music._on_double_click(types.SimpleNamespace(x=10, y=900))
    assert music.controller.index == 2


def test_the_space_bar_plays_and_pauses_even_in_the_table(music_app, songs):
    app, music = music_app
    add(music, songs)
    event = types.SimpleNamespace(widget=music.tree)
    assert music._key_space(event) == "break" and music.controller.state == "playing"
    assert music._key_space(event) == "break" and music.controller.state == "paused"


def test_select_all_and_delete_from_the_keyboard(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.event_generate("<Control-a>")
    music.update()
    music.tree.selection_set(music.tree.get_children())
    assert music._selected() == [0, 1, 2]
    music._remove_selected()
    assert rows(music) == []


# ------------------------------------------------------------------------------ robustness
def test_one_failing_round_does_not_stop_the_clock(music_app, songs, monkeypatch):
    app, music = music_app
    add(music, songs)
    calls = []
    real = music._drain_reader

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("a bug in one round")
        real()

    monkeypatch.setattr(music, "_drain_reader", flaky)
    music._tick()
    music._tick()
    assert len(calls) == 2                                      # the second round ran after the first failed
    pending = [a for a in music.tk.call("after", "info")]
    assert pending                                               # and the next one is scheduled


def test_a_tick_after_the_window_is_gone_ends_quietly(music_app):
    app, music = music_app
    music.destroy()
    music._tick()                                                # no error, nothing scheduled


def test_switching_between_tracks_with_and_without_covers_many_times(music_app, songs, jpg):
    app, music = music_app
    add(music, songs)
    for round_ in range(6):
        for i in range(3):
            play(music, i)
            path = music.reader.cover_requests[-1]
            music.reader.answer_cover(path, jpg if (i + round_) % 2 == 0 else None)
            music._covers.pop(path, None)                        # forget, so every round asks again
            settle(music)
    play(music, 0)
    music._stop()
    assert not shown_cover(music)
