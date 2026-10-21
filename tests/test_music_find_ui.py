"""The music window's newer parts, driven like a person would: '🔍 Şarkı bul', the download of a found
song and the 'which list?' question, deleted files leaving the list, the search box, sorting, the
right-click menu, the sleep timer, carrying on where the music stopped, and the media keys."""
import os
import time

import pytest
from music_support import FakeBackend, FakeReader, make_wav
from ui_support import notice

from app import music_search, player, tags
from app.models import DONE, DOWNLOADING, ERROR, PROCESSING, QUEUED, Item
from app.music_ui import (SLEEP_OFF, SLEEP_TRACK, VIEW_FIND, VIEW_LISTS, MusicWindow, SongListDialog,
                          song_status)
from app.playlists import DEFAULT_NAME

pytestmark = pytest.mark.gui


@pytest.fixture
def music_app(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app.manager.set_gate(False)                         # found songs are queued, never really downloaded
    app._ensure_music()
    return app, app.music


@pytest.fixture
def songs(tmp_path):
    return [make_wav(tmp_path / f"{n}.wav") for n in ("Sabah", "Ogle", "Aksam", "Gece")]


def add(music, paths):
    music._pick_files = lambda: paths
    music._add_files()


def shown_titles(music):
    return [music.tree.item(i, "values")[1] for i in music.tree.get_children()]


def results(music):
    return [music.results_tree.item(i, "values") for i in music.results_tree.get_children()]


def found(n=3):
    return [{"url": f"https://www.youtube.com/watch?v=id{i}", "title": f"Şarkı {i}", "channel": "Kanal",
             "duration": 200 + i} for i in range(n)]


def search(music, answer):
    music.search_entry.insert(0, "tarkan")
    music._search()
    music.searcher.give(answer)
    music._tick()


def finish_song(app, item, tmp_path, name="İnen"):
    """The download of a found song ends: its MP3 is on the disk and the 'done' event arrives."""
    item.final_path = make_wav(tmp_path / f"{name}.mp3")
    item.state = DONE
    item.fraction = 1.0
    app.manager.events.put(("done", item))
    app._drain_events()


# ------------------------------------------------------------------------------ the two views
def test_the_window_opens_on_the_lists_and_switches_to_the_search(music_app):
    app, music = music_app
    assert music.view == VIEW_LISTS and music.list_box.winfo_manager() == "grid"
    assert music.find_box.winfo_manager() == ""
    music._show_view(VIEW_FIND)
    assert music.find_box.winfo_manager() == "grid" and music.list_box.winfo_manager() == ""
    assert music.find_hint.winfo_manager() == "place"                   # the "write a song" hint, no results yet
    music._show_view(VIEW_LISTS)
    assert music.list_box.winfo_manager() == "grid"


def test_searching_shows_the_results_and_how_many(music_app):
    app, music = music_app
    music._show_view(VIEW_FIND)
    search(music, found(3))
    assert music.searcher.asked == ["tarkan"]
    assert music.searcher.more == ()                                 # no artist: the search is not narrowed
    assert results(music) == [("Şarkı 0", "Kanal", "", "3:20", "⬇"), ("Şarkı 1", "Kanal", "", "3:21", "⬇"),
                              ("Şarkı 2", "Kanal", "", "3:22", "⬇")]
    assert "3 sonuç" in music.find_label.cget("text") and music.search_btn.cget("state") == "normal"
    assert music.find_hint.winfo_manager() == ""


def test_an_artist_narrows_the_search_and_is_enough_alone(music_app):
    app, music = music_app
    music._show_view(VIEW_FIND)
    music.artist_entry.insert(0, "  Barış   Manço ")
    music.search_entry.insert(0, "gülpembe")
    music._search()
    assert music.searcher.asked == ["gülpembe"] and music.searcher.more == ("Barış Manço",)
    assert "gülpembe (Barış Manço)" in music.find_label.cget("text")
    music.searcher.give([dict(found(1)[0], views=105_000_000)])
    music._tick()
    assert results(music) == [("Şarkı 0", "Kanal", "105 Mn", "3:20", "⬇")]
    music.search_entry.delete(0, "end")                              # only the artist: their songs
    music._search()
    assert music.searcher.asked[-1] == "" and music.searcher.more == ("Barış Manço",)
    assert music.store.state["searches"] == ["gülpembe"]             # an empty search is not remembered


def test_a_link_ignores_the_artist(music_app):
    app, music = music_app
    music.artist_entry.insert(0, "Tarkan")
    music.search_entry.insert(0, "https://www.youtube.com/playlist?list=PL1")
    music._search()
    assert music.searcher.more == ()


def test_an_empty_box_is_not_searched(music_app):
    app, music = music_app
    music._search()
    assert music.searcher.asked == [] and "ne arayacağımı" in music.find_label.cget("text")


def test_while_searching_the_button_waits(music_app):
    app, music = music_app
    music.search_entry.insert(0, "x")
    music._search()
    assert music.search_btn.cget("state") == "disabled" and "aranıyor" in music.find_label.cget("text")


def test_a_slow_search_shows_that_it_is_still_going(music_app):
    app, music = music_app
    music.search_entry.insert(0, "yavaş")
    music._search()
    music._search_started -= 12
    music._tick()
    assert "12 sn" in music.find_label.cget("text") and "yavaş" in music.find_label.cget("text")
    music.searcher.give(found(1))
    music._tick()
    assert "1 sonuç" in music.find_label.cget("text")


def test_nothing_found_and_an_error_are_said_plainly(music_app):
    app, music = music_app
    search(music, [])
    assert "bulamadım" in music.find_label.cget("text")
    music.search_entry.delete(0, "end")
    music.search_entry.insert(0, "y")
    music._search()
    music.searcher.give([], error="Unable to download webpage\nmore")
    music._tick()
    assert music.find_label.cget("text") == "Arayamadım: Unable to download webpage"


# ------------------------------------------------------------------------------ downloading a found song
def test_a_found_song_is_queued_as_mp3_into_the_music_folder(music_app):
    app, music = music_app
    search(music, found(2))
    music.results_tree.selection_set("1")
    music._download_selected()
    [it] = app.song_items()
    assert it.url == "https://www.youtube.com/watch?v=id1" and it.title == "Şarkı 1"
    assert it.kind == "audio" and it.origin == "music" and it.folder == music_search.music_dir()
    assert it.cover and not it.sort_folders
    assert "İniyor" in music.note_label.cget("text")
    assert results(music)[1][4] == "Sırada" and results(music)[0][4] == "⬇"


def test_only_the_percentage_is_shown_while_it_downloads(music_app):
    app, music = music_app
    search(music, found(1))
    music.results_tree.selection_set("0")
    music._download_selected()
    [it] = app.song_items()
    it.state, it.fraction = DOWNLOADING, 0.456
    music._tick()
    assert results(music)[0][4] == "%45"
    assert music.dl_label.cget("text") == "⬇ Şarkı 0 • %45"
    it.state = PROCESSING
    music._tick()
    assert results(music)[0][4] == "%99"


def test_two_songs_at_once_show_one_line(music_app):
    app, music = music_app
    search(music, found(2))
    music.results_tree.selection_set(("0", "1"))
    music._download_selected()
    a, b = app.song_items()
    a.state, a.fraction = DOWNLOADING, 0.2
    b.state, b.fraction = DOWNLOADING, 0.6
    music._tick()
    assert music.dl_label.cget("text") == "⬇ 2 şarkı iniyor • %40"


def test_the_same_song_twice_is_not_downloaded_twice(music_app):
    app, music = music_app
    search(music, found(1))
    music.results_tree.selection_set("0")
    music._download_selected()
    music._download_selected()
    assert len(app.song_items()) == 1 and "zaten iniyor" in music.note_label.cget("text")


def test_a_failed_song_is_tried_again(music_app):
    app, music = music_app
    search(music, found(1))
    music.results_tree.selection_set("0")
    music._download_selected()
    [it] = app.song_items()
    it.state = ERROR
    assert app.download_song(found(1)[0]) == "restarted" and it.state == QUEUED
    assert len(app.song_items()) == 1


def test_nothing_chosen_nothing_downloaded(music_app):
    app, music = music_app
    search(music, found(1))
    music._download_selected()
    assert app.song_items() == [] and "seç" in music.find_label.cget("text")


def test_the_status_words():
    it = Item("u")
    for state, fraction, text in ((QUEUED, 0, "Sırada"), (DOWNLOADING, 0.999, "%99"), (DOWNLOADING, 0.07, "%7"),
                                  (DONE, 1, "✓ İndi"), (ERROR, 0, "✖ Olmadı")):
        it.state, it.fraction = state, fraction
        assert song_status(it) == text


# ------------------------------------------------------------------------------ 'which list?'
def song_dialog(app):
    d = app.song_dialog
    assert isinstance(d, SongListDialog)
    return d


def download_one(app, music, tmp_path, n=1):
    search(music, found(n))
    music.results_tree.selection_set([str(i) for i in range(n)])
    music._download_selected()
    return app.song_items()


def test_a_finished_song_asks_which_list_and_goes_there(music_app, tmp_path):
    app, music = music_app
    spor = app._store().create("Spor")
    [it] = download_one(app, music, tmp_path)
    finish_song(app, it, tmp_path)
    d = song_dialog(app)
    assert "“Şarkı 0” bilgisayarına indi" in d.text.cget("text")
    assert app._store().tracks(DEFAULT_NAME) == [] and app._store().tracks(spor) == []   # nothing before the answer
    d.menu.set(spor)
    d._on_pick(spor)
    d.choose()
    assert [t["title"] for t in app._store().tracks(spor)] == ["İnen"]
    assert music.viewed == spor and "“Spor” listesine eklendi" in music.note_label.cget("text")
    assert app.song_dialog is None and app._store().state["ask_list"] == spor


def test_the_last_chosen_list_is_offered_first(music_app, tmp_path):
    app, music = music_app
    app._store().create("Spor")
    app._store().set_state(ask_list="Spor")
    [it] = download_one(app, music, tmp_path)
    finish_song(app, it, tmp_path)
    assert song_dialog(app).menu.get() == "Spor"
    song_dialog(app).skip()


def test_a_new_list_can_be_made_in_the_question(music_app, tmp_path):
    app, music = music_app
    [it] = download_one(app, music, tmp_path)
    finish_song(app, it, tmp_path)
    d = song_dialog(app)
    d.menu.set(SongListDialog.NEW)
    d._on_pick(SongListDialog.NEW)
    d.choose()                                                         # no name yet: asks for one
    assert d.winfo_exists() and "ad ver" in d.error.cget("text")
    d.name_entry.insert(0, "Yeni Keşifler")
    d.choose()
    assert [t["title"] for t in app._store().tracks("Yeni Keşifler")] == ["İnen"]


def test_saying_not_now_adds_nothing_and_keeps_the_file(music_app, tmp_path):
    app, music = music_app
    [it] = download_one(app, music, tmp_path)
    finish_song(app, it, tmp_path)
    song_dialog(app).skip()
    assert all(app._store().tracks(n) == [] for n in app._store().names())
    assert os.path.isfile(it.final_path) and "eklemedim" in music.note_label.cget("text")


def test_songs_that_finish_together_are_one_question(music_app, tmp_path):
    app, music = music_app
    a, b, c = download_one(app, music, tmp_path, 3)
    finish_song(app, a, tmp_path, "Bir")
    finish_song(app, b, tmp_path, "Iki")
    finish_song(app, c, tmp_path, "Uc")
    d = song_dialog(app)
    assert d.text.cget("text").startswith("3 şarkı indi")
    d.choose()
    assert [t["title"] for t in app._store().tracks(DEFAULT_NAME)] == ["Bir", "Iki", "Uc"]


def test_found_songs_never_go_into_a_list_by_themselves(music_app, tmp_path):
    app, music = music_app
    assert app.cfg.get("auto_music")
    [it] = download_one(app, music, tmp_path)
    finish_song(app, it, tmp_path)
    assert "İndirilenler" not in app._store().names()
    song_dialog(app).skip()


def test_an_already_downloaded_song_asks_again_instead_of_downloading(music_app, tmp_path):
    app, music = music_app
    [it] = download_one(app, music, tmp_path)
    finish_song(app, it, tmp_path)
    song_dialog(app).skip()
    assert app.download_song(found(1)[0]) == "done" and len(app.song_items()) == 1
    song_dialog(app).choose()
    assert [t["title"] for t in app._store().tracks(DEFAULT_NAME)] == ["İnen"]


def test_adding_the_same_song_to_the_same_list_twice_is_refused_kindly(music_app, tmp_path):
    app, music = music_app
    [it] = download_one(app, music, tmp_path)
    finish_song(app, it, tmp_path)
    song_dialog(app).choose()
    assert app.songs_to_list([it.final_path], DEFAULT_NAME) == 0
    assert "zaten var" in notice(app) and len(app._store().tracks(DEFAULT_NAME)) == 1


# ------------------------------------------------------------------------------ deleted files leave the list
def test_a_deleted_file_leaves_the_list_by_itself(music_app, songs):
    app, music = music_app
    add(music, songs)
    os.remove(songs[1])
    music._next_prune = 0
    music._tick()
    end = time.time() + 5
    while time.time() < end and len(shown_titles(music)) == 4:
        music._tick()
        time.sleep(0.02)
    assert shown_titles(music) == ["Sabah", "Aksam", "Gece"]
    assert "1 parça" in music.note_label.cget("text") and "çıkarıldı" in music.note_label.cget("text")


def test_deleting_the_playing_lists_file_keeps_the_music_going(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("2")
    music._play_selected()
    os.remove(songs[0])
    assert music.prune_missing() == 1
    c = music.controller
    assert c.state == "playing" and c.current_title() == "Aksam" and c.index == 1
    assert [t["title"] for t in c.tracks] == ["Ogle", "Aksam", "Gece"]


def test_nothing_deleted_nothing_said(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.note_label.configure(text="")
    assert music.prune_missing() == 0 and music.note_label.cget("text") == ""


# ------------------------------------------------------------------------------ search box, sorting, menu
def test_the_search_box_filters_the_list(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._apply_filter("ge")
    assert shown_titles(music) == ["Gece"] and music.count_label.cget("text").startswith("1 / 4 parça")
    music._apply_filter("xyz")
    assert shown_titles(music) == [] and "eşleşen parça yok" in music.empty_hint.cget("text")
    music._clear_filter()
    assert len(shown_titles(music)) == 4


def test_a_filtered_row_still_plays_the_right_track(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._apply_filter("aksam")
    music.tree.selection_set(music.tree.get_children()[0])
    music._play_selected()
    assert music.controller.current_title() == "Aksam"


def test_moving_is_refused_while_filtered(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._apply_filter("gece")
    music.tree.selection_set("3")
    music._move(-1)
    assert [t["title"] for t in music.store.tracks(music.viewed)] == ["Sabah", "Ogle", "Aksam", "Gece"]
    assert "aramayı temizle" in music.note_label.cget("text")


def test_clicking_a_column_title_sorts_and_twice_turns_it_round(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._sort("title")
    assert shown_titles(music) == ["Aksam", "Gece", "Ogle", "Sabah"] and "sıralandı" in music.note_label.cget("text")
    music._sort("title")
    assert shown_titles(music) == ["Sabah", "Ogle", "Gece", "Aksam"]


def test_sorting_the_playing_list_keeps_the_song(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("0")
    music._play_selected()
    music._sort("title")
    assert music.controller.current_title() == "Sabah" and music.controller.state == "playing"
    assert music.controller.index == 3


def test_the_right_click_menu_offers_play_folder_copy_and_remove(music_app, songs, monkeypatch):
    app, music = music_app
    add(music, songs)
    music.store.create("Spor")
    music.tree.selection_set(("0", "2"))
    items = music.track_menu_items()
    labels = [e[0] for e in items if e]
    assert labels == ["▶ Çal", "⏭ Sıradaki olarak çal", "➕ Sıraya ekle", "📂 Klasörde göster",
                      "🎤 Şarkı sözlerini internette bul", "✎ Sözleri elle yaz / düzenle",
                      "🏷 Bilgileri düzenle (ad, sanatçı, kapak)…", "➕ Başka listeye ekle", "✖ Listeden çıkar"]
    sub = dict(items[7][1])
    assert list(sub) == ["Spor", "＋ Yeni liste…"]
    sub["Spor"]()
    assert [t["title"] for t in music.store.tracks("Spor")] == ["Sabah", "Aksam"]
    shown = []
    monkeypatch.setattr("app.music_ui.open_in_file_manager", shown.append)
    music._reveal_selected()
    assert shown == [songs[0]]


def test_the_right_click_menu_really_opens(music_app, songs, monkeypatch):
    app, music = music_app
    add(music, songs)
    popped = []
    monkeypatch.setattr(music, "_popup", lambda menu, event: popped.append(menu.index("end")))
    music.deiconify()
    music.update()
    bbox = music.tree.bbox("1")
    if not bbox:
        pytest.skip("the table is not drawn")
    event = type("E", (), {"x": bbox[0] + 5, "y": bbox[1] + 5, "x_root": 0, "y_root": 0})()
    music._track_menu(event)
    assert popped == [9] and music._selected() == [1]                # 10 entries (one a line), row 1 selected
    music.withdraw()


# ------------------------------------------------------------------------------ sleep timer
def test_the_sleep_timer_stops_the_music_when_the_time_comes(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._play_selected()
    music._set_sleep("15 dk")
    assert music.sleep_menu.get() == "😴 15 dk" and "15 dakika" in music.note_label.cget("text")
    music.sleep_at = time.time() - 1
    music._tick()
    assert music.controller.state == "stopped" and "İyi uykular" in music.note_label.cget("text")
    assert music.sleep_menu.get() == SLEEP_OFF


def test_the_sleep_timer_can_stop_after_the_song(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._play_selected()
    music._set_sleep(SLEEP_TRACK)
    music.controller.backend.active.ended = True
    music._tick()
    assert music.controller.state == "stopped" and music.controller.current_title() == "Sabah"
    assert music.sleep_menu.get() == SLEEP_OFF


def test_the_sleep_timer_can_be_switched_off(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._play_selected()
    music._set_sleep("30 dk")
    music._set_sleep(SLEEP_OFF)
    assert music.sleep_at is None and music.sleep_menu.get() == SLEEP_OFF


# ------------------------------------------------------------------------------ carrying on
def make_music(app, monkeypatch):
    app.music = None
    app._ensure_music()
    return app.music


def test_the_place_in_the_song_is_remembered_and_play_goes_on_from_there(music_app, songs, monkeypatch):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("2")
    music._play_selected()
    music.controller.backend.active.position = 83000
    music.shutdown()
    music.destroy()
    st = app._store().state
    assert (st["resume_path"], st["resume_ms"]) == (os.path.abspath(songs[2]), 83000)
    again = make_music(app, monkeypatch)
    assert again.now_label.cget("text") == "Kaldığın yer: Aksam" and "1:23" in again.sub_label.cget("text")
    again._toggle()
    c = again.controller
    assert c.state == "playing" and c.current_title() == "Aksam" and c.backend.position == 83000


def test_stopping_forgets_the_place(music_app, songs, monkeypatch):
    app, music = music_app
    add(music, songs)
    music._play_selected()
    music._stop()
    music.shutdown()
    music.destroy()
    again = make_music(app, monkeypatch)
    assert again.now_label.cget("text") == "Şu an bir şey çalmıyor"


def test_choosing_another_song_ignores_the_place(music_app, songs, monkeypatch):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("2")
    music._play_selected()
    music.shutdown()
    music.destroy()
    again = make_music(app, monkeypatch)
    again.tree.selection_set("0")
    again._toggle()
    assert again.controller.current_title() == "Sabah" and again.controller.backend.active.position == 0


def test_a_remembered_song_that_was_deleted_is_not_offered(music_app, songs, monkeypatch):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("1")
    music._play_selected()
    music.shutdown()
    music.destroy()
    os.remove(songs[1])
    again = make_music(app, monkeypatch)
    assert again.now_label.cget("text") == "Şu an bir şey çalmıyor"


# ------------------------------------------------------------------------------ media keys
def test_media_keys_are_taken_only_while_music_plays(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._tick()
    assert not music.keys.active
    music._play_selected()
    music._tick()
    assert music.keys.active
    music._toggle()                                              # paused: still ours
    music._tick()
    assert music.keys.active
    music._stop()
    music._tick()
    assert not music.keys.active


def test_media_keys_drive_the_player(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._play_selected()
    music._tick()
    music.keys.pressed.put("next")
    music._tick()
    assert music.controller.current_title() == "Ogle"
    music.keys.pressed.put("toggle")
    music._tick()
    assert music.controller.state == "paused"
    music.keys.pressed.put("previous")
    music._tick()
    assert music.controller.current_title() == "Sabah"
    music.keys.pressed.put("stop")
    music._tick()
    assert music.controller.state == "stopped"


def test_closing_gives_the_keys_back(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._play_selected()
    music._tick()
    music.shutdown()
    assert not music.keys.active


def test_stopping_by_hand_switches_the_sleep_timer_off(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._play_selected()
    music._set_sleep("30 dk")
    music._stop()
    assert music.sleep_at is None and music.sleep_menu.get() == SLEEP_OFF


# ------------------------------------------------------------------------------ shuffling the list for good
def test_shuffling_the_list_changes_its_order_and_ctrl_z_brings_it_back(music_app, songs):
    app, music = music_app
    add(music, songs)
    before = shown_titles(music)
    music._shuffle_list()
    after = shown_titles(music)
    assert sorted(after) == sorted(before) and after != before and "karıştırıldı" in music.note_label.cget("text")
    assert [t["title"] for t in music.store.tracks(music.viewed)] == after              # kept in the file too
    music._undo_shuffle()
    assert shown_titles(music) == before and "Eski sıraya" in music.note_label.cget("text")


def test_shuffling_the_playing_list_keeps_the_song(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("2")
    music._play_selected()
    music._shuffle_list()
    c = music.controller
    assert c.state == "playing" and c.current_title() == "Aksam"
    assert [t["title"] for t in c.tracks] == [t["title"] for t in music.store.tracks(music.viewed)]


def test_one_song_is_not_shuffled(music_app, songs):
    app, music = music_app
    add(music, songs[:1])
    music._shuffle_list()
    assert "en az iki" in music.note_label.cget("text")


# ------------------------------------------------------------------------------ lyrics
LRC = "[ar:Barış Manço]\n[00:01.00]Birinci satır\n[00:05.50]İkinci satır\n[00:09.00]\n[00:12.00]Dördüncü satır\n"


def lyrics_for(path, text=LRC):
    from app import lyrics
    lyrics.save(path, text)


def test_the_lyrics_button_shows_only_for_a_song_with_lyrics(music_app, songs):
    app, music = music_app
    add(music, songs)
    lyrics_for(songs[1])
    music.tree.selection_set("0")
    music._update_lyrics_button()
    assert music.lyrics_btn.winfo_manager() == ""
    music.tree.selection_set("1")
    music._update_lyrics_button()
    assert music.lyrics_btn.winfo_manager() == "place"
    music._play_selected()                                         # the playing song decides while it plays
    music.tree.selection_set("0")
    music._tick()
    assert music.lyrics_btn.winfo_manager() == "place"
    music._next()
    music._tick()
    assert music.lyrics_btn.winfo_manager() == ""


def test_synced_lyrics_follow_the_song_and_a_click_jumps(music_app, songs):
    app, music = music_app
    add(music, songs)
    lyrics_for(songs[0])
    music.tree.selection_set("0")
    music._play_selected()
    music.open_lyrics()
    win = music.lyrics_window
    assert win.synced and win.lines() == ["Birinci satır", "İkinci satır", "♪", "Dördüncü satır"]
    assert "akar" in win.badge.cget("text") and win.title_label.cget("text") == "Sabah"
    music.controller.backend.active.position = 6000
    music._tick()
    assert win.current == 1 and win.text.tag_ranges("now")
    now = win.text.get(*win.text.tag_ranges("now")).strip()
    assert now == "İkinci satır"
    win.update()
    bbox = win.text.bbox("4.0")
    if bbox:
        win._on_click(type("E", (), {"x": bbox[0] + 2, "y": bbox[1] + 2})())
        assert music.controller.backend.active.position == 12000
    win._resize(+4)
    assert win.size == 20 and win.current == 1


def test_the_lyrics_window_follows_to_the_next_song(music_app, songs):
    app, music = music_app
    add(music, songs)
    lyrics_for(songs[0])
    music._play_selected()
    music.open_lyrics()
    music._next()
    music._tick()
    win = music.lyrics_window
    assert win.title_label.cget("text") == "Ogle" and win.data is None
    assert win.empty.winfo_manager() == "place" and "yok" in win.empty_text.cget("text")


def test_plain_lyrics_are_shown_without_following(music_app, songs):
    app, music = music_app
    add(music, songs)
    lyrics_for(songs[0], "Düz bir satır\nİkincisi\n")
    music.tree.selection_set("0")
    music.open_lyrics()
    win = music.lyrics_window
    assert not win.synced and win.lines() == ["Düz bir satır", "İkincisi"] and "Sözler" in win.badge.cget("text")


def test_lyrics_can_be_looked_up_from_the_menu(music_app, songs, monkeypatch):
    from app import lyrics
    app, music = music_app
    add(music, songs)
    asked = []
    monkeypatch.setattr(lyrics, "fetch", lambda artist, title, seconds=0: asked.append((artist, title)) or LRC)
    music.tree.selection_set("2")
    dict((e[0], e[1]) for e in music.track_menu_items() if e)["🎤 Şarkı sözlerini internette bul"]()
    assert "arıyorum" in music.note_label.cget("text")
    end = time.time() + 5
    while time.time() < end and not lyrics.has_lyrics(songs[2]):
        time.sleep(0.02)
    music._tick()
    assert asked == [("", "Aksam")] and lyrics.has_lyrics(songs[2])
    assert "buldum" in music.note_label.cget("text") and music.lyrics_btn.winfo_manager() == "place"
    labels = [e[0] for e in music.track_menu_items() if e]
    assert "🎤 Şarkı sözlerini göster" in labels


def test_no_lyrics_found_is_said(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("0")
    music._lyrics_for_selected()
    end = time.time() + 5
    while time.time() < end and "bulamadım" not in music.note_label.cget("text"):
        music._tick()
        time.sleep(0.02)
    assert "şarkı sözü bulamadım" in music.note_label.cget("text")


def test_a_found_song_brings_its_lyrics(music_app, tmp_path, monkeypatch):
    from app import lyrics
    app, music = music_app
    asked = []
    monkeypatch.setattr(lyrics, "fetch", lambda artist, title, seconds=0: asked.append((artist, title)) or LRC)
    search(music, [{"url": "https://www.youtube.com/watch?v=g", "title": "Barış Manço - Gülpembe", "channel": "k",
                    "duration": 300}])
    music.results_tree.selection_set("0")
    music._download_selected()
    [it] = app.song_items()
    finish_song(app, it, tmp_path, "Gülpembe")
    end = time.time() + 5
    while time.time() < end and not lyrics.has_lyrics(it.final_path):
        time.sleep(0.02)
    assert asked == [("Barış Manço", "Gülpembe")] and lyrics.has_lyrics(it.final_path)
    song_dialog(app).skip()


# ------------------------------------------------------------------------------ the DISO icon everywhere
def test_every_window_wears_the_diso_icon_not_customtkinters(music_app, songs, tmp_path):
    from app import ui
    app, music = music_app
    add(music, songs)
    lyrics_for(songs[0])
    music.tree.selection_set("0")
    music.open_lyrics()
    [it] = download_one(app, music, tmp_path)
    finish_song(app, it, tmp_path)
    windows = [music, music.lyrics_window, app.song_dialog, ui.AboutDialog(app, provider=lambda: [("Sürüm", "x")])]
    app._open_settings()
    windows.append(app.settings_panel if hasattr(app, "settings_panel") else None)
    for w in [w for w in windows if w is not None]:
        assert w._iconbitmap_method_called, type(w).__name__
    assert music._logo is not None                                   # the header shows the real logo too
    app.song_dialog.skip()
