"""The music window and the mode switch, with a silent fake backend."""
import os
import time

import pytest
from music_support import FakeBackend, FakeReader, make_wav
from ui_support import notice

from app import player, tags
from app.music_ui import MODE_DOWNLOAD, MODE_MUSIC, fmt_time

pytestmark = pytest.mark.gui


@pytest.fixture
def music_app(app, monkeypatch):
    """The download window with the music player switched on (fake backend); returns (app, music)."""
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app._ensure_music()
    return app, app.music


@pytest.fixture
def songs(tmp_path):
    return [make_wav(tmp_path / f"{n}.wav") for n in ("Sabah", "Ogle", "Aksam", "Gece")]


def titles(music):
    return [t["title"] for t in music.store.tracks(music.viewed)]


def rows(music):
    """What the table shows: [(number or ▶, title, artist, length), ...]."""
    return [music.tree.item(i, "values") for i in music.tree.get_children()]


def marks(music):
    return [r[0] for r in rows(music)]


def add(music, songs):
    music._pick_files = lambda: songs
    music._add_files()


def table_colour():
    from tkinter import ttk
    return ttk.Style().lookup("Music.Treeview", "background")


def select(music, *indexes):
    music.tree.selection_set([str(i) for i in indexes])


# ------------------------------------------------------------------------------ the two modes
def test_the_download_window_has_a_mode_bar_and_the_music_window_starts_hidden(music_app):
    app, music = music_app
    assert app.mode == MODE_DOWNLOAD and app.mode_bar.get() == MODE_DOWNLOAD
    assert music.state() == "withdrawn"
    assert music.mode_bar.get() == MODE_MUSIC


def test_switching_modes_swaps_the_windows(music_app):
    app, music = music_app
    app.deiconify()
    app.update()
    app._switch_mode(MODE_MUSIC)
    app.update()
    assert app.mode == MODE_MUSIC and app.state() == "withdrawn" and music.state() == "normal"
    music._on_mode(MODE_DOWNLOAD)                      # the bar of the music window
    app.update()
    assert app.mode == MODE_DOWNLOAD and app.state() == "normal" and music.state() == "withdrawn"
    assert app.mode_bar.get() == MODE_DOWNLOAD
    app.withdraw()


def test_music_keeps_playing_when_the_window_changes(music_app, songs):
    app, music = music_app
    add(music, songs)
    select(music, 1)
    music._play_selected()
    app._switch_mode(MODE_MUSIC)
    app._switch_mode(MODE_DOWNLOAD)
    assert music.controller.state == "playing" and music.controller.current_title() == "Ogle"
    app.withdraw()


def test_the_music_window_is_only_made_when_it_is_wanted(app):
    assert app.music is None


def test_a_player_that_cannot_start_leaves_the_download_window_alone(app, monkeypatch):
    def broken(alias=""):
        raise OSError("no winmm")
    monkeypatch.setattr(player, "new_backend", broken)
    app._switch_mode(MODE_MUSIC)
    assert app.music is None and app.mode == MODE_DOWNLOAD and app.mode_bar.get() == MODE_DOWNLOAD
    assert "başlatamadım" in notice(app)


def test_closing_the_app_stops_the_music_and_saves_the_lists(music_app, songs):
    app, music = music_app
    add(music, songs[:2])
    select(music, 0)
    music._play_selected()
    path = music.store.path
    music.store.lists[music.viewed].append({"path": songs[2], "title": "Aksam"})   # not saved yet
    app._on_close()
    assert music.controller.state == "stopped" and music.controller.backend.active.loaded is None
    assert "Aksam" in open(path, encoding="utf-8").read()


# ------------------------------------------------------------------------------ playlists
def test_adding_files_and_folders(music_app, songs, tmp_path):
    app, music = music_app
    assert "Liste bomboş" in music.empty_hint.cget("text") and music.count_label.cget("text") == ""
    add(music, songs + [str(tmp_path / "x.txt")])
    assert titles(music) == ["Sabah", "Ogle", "Aksam", "Gece"] and music.count_label.cget("text") == "4 parça"
    assert rows(music)[0] == ("1", "Sabah", "", "")
    folder = tmp_path / "klasor"
    folder.mkdir()
    make_wav(folder / "Ekstra.wav")
    music._pick_folder = lambda: str(folder)
    music._add_folder()
    assert titles(music)[-1] == "Ekstra" and "1 parça eklendi" in music.note_label.cget("text")
    music._pick_files = lambda: ()
    music._add_files()                                   # cancelled: nothing changes
    assert len(titles(music)) == 5


def test_reordering_and_removing(music_app, songs):
    app, music = music_app
    add(music, songs)
    select(music, 2, 3)
    music._move(-1)
    assert titles(music) == ["Sabah", "Aksam", "Gece", "Ogle"]
    assert music._selected() == [1, 2]                   # the selection follows the moved tracks
    music._remove_selected()
    assert titles(music) == ["Sabah", "Ogle"]
    music._confirm = lambda text: False
    music._clear_list()
    assert len(titles(music)) == 2
    music._confirm = lambda text: True
    music._clear_list()
    assert titles(music) == []


def test_several_lists_each_keeps_its_own_order(music_app, songs):
    app, music = music_app
    first = music.viewed
    add(music, songs[:2])
    music._ask_name = lambda *a: "Spor"
    music._new_list()
    assert music.viewed == "Spor" and music.list_menu.get() == "Spor" and titles(music) == []
    add(music, songs[2:])
    music._select_list(first)
    assert titles(music) == ["Sabah", "Ogle"]
    music._select_list("Spor")
    assert titles(music) == ["Aksam", "Gece"] and music.store.state["last"] == "Spor"
    music._ask_name = lambda *a: "Koşu"
    music._rename_list()
    assert music.viewed == "Koşu" and "Spor" not in music.store.names()
    music._ask_name = lambda *a: None                    # a cancelled dialog changes nothing
    music._new_list()
    assert music.store.user_names() == [first, "Koşu"]
    music._confirm = lambda text: True
    music._delete_list()
    assert music.store.user_names() == [first] and music.viewed == first


def test_the_lists_come_back_after_a_restart(music_app, songs):
    app, music = music_app
    first = music.viewed
    add(music, songs)
    music._ask_name = lambda *a: "Gece listesi"
    music._new_list()
    add(music, songs[:1])
    music.volume.set(30)
    music._on_volume(30)
    time.sleep(0.7)
    app.update()                                         # the volume is written shortly after the drag
    music._cycle_repeat()
    music.shuffle_var.set(True)
    music._on_shuffle()
    again = type(music.store)(music.store.path)
    assert again.user_names() == [first, "Gece listesi"] and again.state["last"] == "Gece listesi"
    assert again.state["volume"] == 30 and again.state["repeat"] == "Liste" and again.state["shuffle"] is True


def test_dragging_the_volume_writes_the_file_once(music_app):
    app, music = music_app
    writes = []
    music.store.save = lambda: writes.append(music.store.state["volume"])
    for v in range(10, 90, 4):
        music._on_volume(v)
    assert writes == [] and music.controller.backend.active.volume == 86       # nothing written during the drag
    time.sleep(0.7)
    app.update()
    assert writes == [86]


def test_a_missing_file_is_marked(music_app, songs):
    app, music = music_app
    add(music, songs)
    os.remove(songs[1])
    music._refresh_tracks()
    assert "(dosya yok)" in rows(music)[1][1] and "(dosya yok)" not in rows(music)[0][1]


# ------------------------------------------------------------------------------ playing
def test_double_click_plays_that_track_and_marks_it(music_app, songs):
    app, music = music_app
    add(music, songs)
    select(music, 2)
    music._play_selected()
    c = music.controller
    assert c.state == "playing" and c.index == 2 and music.playing_list == music.viewed
    assert marks(music)[2] == "▶" and marks(music)[1] == "2"
    assert music.play_btn.cget("text") == "⏸" and music.now_label.cget("text") == "Aksam"


def test_the_play_button_plays_pauses_and_resumes(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._toggle()                                      # nothing selected: starts at the top
    assert music.controller.state == "playing" and music.controller.index == 0
    music._toggle()
    assert music.controller.state == "paused" and music.play_btn.cget("text") == "▶"
    assert music.now_label.cget("text").startswith("⏸")
    music._toggle()
    assert music.controller.state == "playing"
    music._stop()
    assert music.controller.state == "stopped" and music.now_label.cget("text") == "Şu an bir şey çalmıyor"
    assert "▶" not in marks(music)


def test_next_previous_and_the_end_of_a_track(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._toggle()
    music._next()
    assert music.controller.index == 1
    music._previous()
    assert music.controller.index == 0
    music.controller.backend.active.ended = True
    music._tick()
    assert music.controller.index == 1 and marks(music)[1] == "▶"


def test_the_clock_and_the_seek_bar(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._toggle()
    backend = music.controller.backend.active          # the one under the equalizer's switch
    backend.position, backend.length = 61000, 200000
    music._update_status()
    assert music.pos_label.cget("text") == "1:01" and music.len_label.cget("text") == "3:20"
    assert abs(music.seek.get() - 305) < 2
    music.seek.set(500)
    music._on_seek_release()
    assert backend.position == 100000
    assert fmt_time(0) == "0:00" and fmt_time(3599000) == "59:59" and fmt_time(-5) == "0:00"


def test_a_different_list_does_not_interrupt_what_plays(music_app, songs):
    app, music = music_app
    first = music.viewed
    add(music, songs)
    select(music, 0)
    music._play_selected()
    music._ask_name = lambda *a: "Baska"
    music._new_list()
    assert music.controller.state == "playing" and music.playing_list == first
    assert "▶" not in marks(music)                               # the marker belongs to the other list
    music._select_list(first)
    assert marks(music)[0] == "▶"
    music._select_list("Baska")
    add(music, songs[1:2])
    music._play_selected()                                       # playing from the new list takes over
    assert music.playing_list == "Baska" and music.controller.current_title() == "Ogle"


def test_editing_the_list_that_plays_keeps_the_track_going(music_app, songs):
    app, music = music_app
    add(music, songs)
    select(music, 2)
    music._play_selected()
    select(music, 0)
    music._remove_selected()                                     # an earlier track goes away
    c = music.controller
    assert c.state == "playing" and c.current_title() == "Aksam" and c.index == 1
    select(music, 1)
    music._remove_selected()                                     # the playing one goes away
    assert c.state == "stopped"


def test_deleting_the_list_that_plays_stops_it(music_app, songs):
    app, music = music_app
    first = music.viewed
    add(music, songs)
    music._ask_name = lambda *a: "Ikinci"
    music._new_list()
    music._select_list(first)
    music._toggle()
    music._confirm = lambda text: True
    music._delete_list()
    assert music.controller.state == "stopped" and music.playing_list is None


def test_shuffle_repeat_and_volume_reach_the_controller(music_app):
    app, music = music_app
    music.shuffle_var.set(True)
    music._on_shuffle()
    assert music.controller.shuffle is True
    assert music.repeat_btn.cget("text").endswith("Kapalı")
    music._cycle_repeat()
    music._cycle_repeat()
    assert music.controller.repeat == "Tek" and music.repeat_btn.cget("text").endswith("Tek")
    music._cycle_repeat()
    assert music.controller.repeat == "Kapalı"
    music._on_volume(42)
    assert music.controller.backend.active.volume == 42


def test_an_unplayable_track_is_reported(music_app, songs):
    app, music = music_app
    add(music, songs[:1])
    os.remove(songs[0])
    music._toggle()
    assert music.controller.state == "stopped" and "Çalamadım" in music.note_label.cget("text")


def test_the_list_follows_the_theme(music_app):
    import customtkinter
    app, music = music_app
    customtkinter.set_appearance_mode("light")
    music.recolor()
    light = table_colour()
    customtkinter.set_appearance_mode("dark")
    music.recolor()
    assert table_colour() != light


def test_the_theme_change_reaches_the_music_window(music_app):
    app, music = music_app
    app._apply_theme("Açık")
    time.sleep(0.1)
    app.update()
    light = table_colour()
    app._apply_theme("Koyu")
    app.update()
    assert table_colour() != light
