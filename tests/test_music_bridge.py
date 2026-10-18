"""Downloads and the music player: the playlist's name travels with its videos, finished music
goes into a playlist by itself, and the row menu can put a song into a list."""
import os
import types

import pytest
from music_support import FakeBackend, FakeReader, make_wav
from ui_support import notice

from app import player, tags, ui
from app import video_engine as ve
from app.models import DONE, ERROR, Item
from app.playlists import DOWNLOADS_NAME

pytestmark = pytest.mark.gui


def names(app):
    return app._store().names()


def titles(app, name):
    return [t["title"] for t in app._store().tracks(name)]


def finished(app, tmp_path, name, *, group="", added=1000.0, ext=".mp3", create=True, state=DONE):
    """A finished download: an Item with a file on disk (the content does not matter for the list)."""
    it = Item(f"http://x/{name}", kind="audio", title=name, group=group)
    it.added = added
    it.state = state
    it.final_path = str(tmp_path / (name + ext))
    if create:
        make_wav(it.final_path)
    app.manager.items.append(it)
    return it


def finish(app, *items):
    for it in items:
        app.manager.events.put(("done", it))
    app._drain_events()


@pytest.fixture
def mapp(app, monkeypatch):
    """The download window with a fake music backend / reader, in case the music window is opened."""
    monkeypatch.setattr(player, "MciBackend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    return app


# ------------------------------------------------------------------------------ the playlist's name
def test_a_playlist_knows_its_name_and_a_single_video_does_not(monkeypatch):
    class FakeYDL:
        info = None

        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            return FakeYDL.info

    monkeypatch.setattr(ve, "_yt_dlp", lambda: type("M", (), {"YoutubeDL": FakeYDL}))
    FakeYDL.info = {"_type": "playlist", "title": "Yaz Hitleri", "entries": [
        {"webpage_url": "https://x/1", "title": "Bir", "duration": 10},
        None,
        {"url": "https://x/2", "title": "İki", "duration": 20}]}
    out = ve.expand_playlist("https://x/list")
    assert isinstance(out, ve.PlaylistEntries) and out.title == "Yaz Hitleri"
    assert out == [("https://x/1", "Bir", 10), ("https://x/2", "İki", 20)]
    FakeYDL.info = {"_type": "video", "title": "Tek", "duration": 5}
    single = ve.expand_playlist("https://x/video")
    assert single == [("https://x/video", "Tek", 5)] and single.title == ""
    FakeYDL.info = {"_type": "playlist", "title": None, "entries": []}
    assert ve.expand_playlist("https://x/empty").title == "" and ve.expand_playlist("https://x/empty") == [("https://x/empty", "", 0)]


def test_entries_keep_the_name_only_through_like():
    e = ve.PlaylistEntries([("a", "A", 1), ("b", "B", 2)], "Liste")
    assert e == [("a", "A", 1), ("b", "B", 2)] and e.title == "Liste"
    assert e[:1] == [("a", "A", 1)] and not hasattr(e[:1], "title")
    assert e.like(e[:1]).title == "Liste" and ve.PlaylistEntries().title == ""


def test_the_videos_of_a_playlist_remember_which_playlist(app, monkeypatch):
    monkeypatch.setattr(app.manager, "start", lambda item: None)
    entries = ve.PlaylistEntries([("http://x/1", "Bir", 1), ("http://x/2", "İki", 2)], "Yaz Hitleri")
    app.add_playlist_selection(entries, app.settings_from_config())
    assert [i.group for i in app.manager.items] == ["Yaz Hitleri", "Yaz Hitleri"]
    app.add_playlist_selection([("http://x/3", "Üç", 3)], app.settings_from_config())     # a plain list: no group
    assert app.manager.items[-1].group == ""


def test_the_selection_window_keeps_the_name_for_what_was_ticked(app):
    entries = ve.PlaylistEntries([("http://x/1", "Bir", 1), ("http://x/2", "İki", 2), ("http://x/3", "Üç", 3)], "Liste")
    dialog = ui.PlaylistDialog(app, entries, app.settings_from_config())
    dialog.withdraw()
    dialog.vars[1].set(False)
    picked = dialog.chosen()
    assert [e[1] for e in picked] == ["Bir", "Üç"] and picked.title == "Liste"
    dialog.destroy()
    plain = ui.PlaylistDialog(app, [("http://x/1", "Bir", 1)], app.settings_from_config())
    plain.withdraw()
    assert plain.chosen() == [("http://x/1", "Bir", 1)]
    plain.destroy()


def test_the_group_is_saved_with_the_download_list():
    it = Item("http://x", group="Yaz Hitleri")
    assert Item.from_dict(it.to_dict()).group == "Yaz Hitleri"
    old = it.to_dict()
    del old["group"]                                            # a list saved before this existed
    assert Item.from_dict(old).group == ""


# ------------------------------------------------------------------------------ finished music
def test_a_single_finished_song_goes_into_the_downloads_list(mapp, tmp_path):
    song = finished(mapp, tmp_path, "Tek Şarkı")
    finish(mapp, song)
    assert DOWNLOADS_NAME in names(mapp) and titles(mapp, DOWNLOADS_NAME) == ["Tek Şarkı"]
    assert "1 müzik “İndirilenler” çalma listesine eklendi" in notice(mapp)


def test_a_finished_playlist_lands_in_a_list_of_its_name_in_playlist_order(mapp, tmp_path):
    items = [finished(mapp, tmp_path, f"Parça {i}", group="Yaz Hitleri", added=100.0 + i) for i in range(1, 6)]
    for batch in ([items[2]], [items[0], items[4]], [items[3]], [items[1]]):      # they finish out of order
        finish(mapp, *batch)
    assert titles(mapp, "Yaz Hitleri") == [f"Parça {i}" for i in range(1, 6)]
    assert DOWNLOADS_NAME not in names(mapp)


def test_several_lists_in_one_round_are_summarised(mapp, tmp_path):
    a = finished(mapp, tmp_path, "A", group="Bir")
    b = finished(mapp, tmp_path, "B", group="İki")
    c = finished(mapp, tmp_path, "C")
    finish(mapp, a, b, c)
    assert {"Bir", "İki", DOWNLOADS_NAME} <= set(names(mapp))
    assert "3 müzik çalma listelerine eklendi" in notice(mapp)


def test_only_music_that_exists_is_added(mapp, tmp_path):
    video = finished(mapp, tmp_path, "Klip", ext=".mp4")
    text = finished(mapp, tmp_path, "Not", ext=".txt")
    gone = finished(mapp, tmp_path, "Silinmiş", create=False)
    empty = Item("http://x/e", kind="audio")
    empty.state = DONE
    mapp.manager.items.append(empty)
    finish(mapp, video, text, gone, empty)
    assert DOWNLOADS_NAME not in names(mapp) and notice(mapp) == ""


def test_a_failed_download_is_not_added(mapp, tmp_path):
    bad = finished(mapp, tmp_path, "Bozuk", state=ERROR)
    mapp.manager.events.put(("error", bad))
    mapp._drain_events()
    assert DOWNLOADS_NAME not in names(mapp)


def test_the_same_song_is_not_added_twice_even_when_downloaded_again(mapp, tmp_path):
    song = finished(mapp, tmp_path, "Tekrar")
    finish(mapp, song)
    finish(mapp, song)
    again = finished(mapp, tmp_path, "Tekrar", added=2000.0, create=False)       # "Baştan indir": same file
    finish(mapp, again)
    assert titles(mapp, DOWNLOADS_NAME) == ["Tekrar"]


def test_the_switch_turns_the_automatic_adding_off(mapp, tmp_path):
    mapp.cfg.set("auto_music", False)
    finish(mapp, finished(mapp, tmp_path, "Sessiz"))
    assert DOWNLOADS_NAME not in names(mapp)
    mapp.cfg.set("auto_music", True)
    finish(mapp, finished(mapp, tmp_path, "Sesli"))
    assert titles(mapp, DOWNLOADS_NAME) == ["Sesli"]


def test_a_playlist_name_is_cleaned_up(mapp, tmp_path):
    finish(mapp, finished(mapp, tmp_path, "X", group="  Yaz   \n Hitleri  "))
    assert "Yaz Hitleri" in names(mapp)
    finish(mapp, finished(mapp, tmp_path, "Y", group="a" * 300))
    assert max(len(n) for n in names(mapp)) == 80


def test_an_open_music_window_shows_the_new_song_and_keeps_playing(mapp, tmp_path):
    first = finished(mapp, tmp_path, "Birinci", added=1.0)
    finish(mapp, first)
    mapp._ensure_music()
    music = mapp.music
    music.viewed = DOWNLOADS_NAME
    music._refresh_lists()
    music.tree.selection_set(["0"])
    music._play_selected()
    second = finished(mapp, tmp_path, "İkinci", added=2.0)
    finish(mapp, second)
    assert [r[1] for r in (music.tree.item(i, "values") for i in music.tree.get_children())] == ["Birinci", "İkinci"]
    assert music.controller.state == "playing" and music.controller.current_title() == "Birinci"
    assert music.controller.tracks[-1]["title"] == "İkinci"                     # the queue follows too


def test_the_store_is_shared_with_the_music_window(mapp, tmp_path):
    finish(mapp, finished(mapp, tmp_path, "Önce"))                               # before the window exists
    mapp._ensure_music()
    assert mapp.music.store is mapp._store() and DOWNLOADS_NAME in mapp.music.list_menu.cget("values")


# ------------------------------------------------------------------------------ the row menu
def labels(row):
    return [label for label, _ in row.menu_commands()]


def row_for(app, item):
    app._sync_rows()
    row = app.rows[item.id]
    row.refresh()
    return row


def test_a_finished_song_has_a_music_menu_with_every_list(mapp, tmp_path):
    song = finished(mapp, tmp_path, "Menü")
    mapp._store().create("Spor")
    row = row_for(mapp, song)
    assert "Müzik listesine ekle" in labels(row)
    sub = dict(row.menu_commands())["Müzik listesine ekle"]
    assert [label for label, _ in sub] == names(mapp) + ["＋ Yeni liste…"]


def test_the_music_menu_only_appears_for_finished_audio(mapp, tmp_path):
    for it in (finished(mapp, tmp_path, "Klip", ext=".mp4x"), finished(mapp, tmp_path, "Gone", create=False),
               finished(mapp, tmp_path, "Busy", state="downloading")):
        assert "Müzik listesine ekle" not in labels(row_for(mapp, it))


def test_choosing_a_list_in_the_menu_adds_the_song(mapp, tmp_path):
    song = finished(mapp, tmp_path, "Seçilen")
    mapp._store().create("Spor")
    row = row_for(mapp, song)
    sub = dict(dict(row.menu_commands())["Müzik listesine ekle"])
    sub["Spor"]()
    assert titles(mapp, "Spor") == ["Seçilen"] and "“Spor” çalma listesine eklendi" in notice(mapp)
    sub["Spor"]()
    assert titles(mapp, "Spor") == ["Seçilen"] and "zaten var" in notice(mapp)


def test_a_new_list_from_the_menu(mapp, tmp_path, monkeypatch):
    song = finished(mapp, tmp_path, "Yeniye")
    row = row_for(mapp, song)

    class Dialog:
        answer = "Gece Listesi"

        def __init__(self, *a, **k):
            pass

        def get_input(self):
            return Dialog.answer

    monkeypatch.setattr(ui.ctk, "CTkInputDialog", Dialog)
    row._add_to_new_music_list()
    assert titles(mapp, "Gece Listesi") == ["Yeniye"]
    Dialog.answer = "   "
    row._add_to_new_music_list()                                # an empty name does nothing
    Dialog.answer = None
    row._add_to_new_music_list()
    assert names(mapp).count("Gece Listesi") == 1 and len(names(mapp)) == 2


def test_adding_a_file_that_disappeared_is_reported(mapp, tmp_path):
    song = finished(mapp, tmp_path, "Kayıp")
    os.remove(song.final_path)
    assert mapp.add_to_music_list(song, "Spor") is False
    assert "bulamadım" in notice(mapp) and "Spor" not in names(mapp)


def test_adding_by_hand_accepts_any_audio_file_and_refreshes_an_open_window(mapp, tmp_path):
    mapp._ensure_music()
    song = finished(mapp, tmp_path, "Elle", ext=".mp4")                       # a video the user wants as music
    assert mapp.add_to_music_list(song, mapp.music.viewed) is True
    assert [r[1] for r in (mapp.music.tree.item(i, "values") for i in mapp.music.tree.get_children())] == ["Elle"]


def test_the_right_click_menu_with_a_sub_menu_opens(mapp, tmp_path, monkeypatch):
    song = finished(mapp, tmp_path, "Sağ Tık")
    row = row_for(mapp, song)
    shown = []
    monkeypatch.setattr(ui.tk.Menu, "tk_popup", lambda self, x, y: shown.append(self.index("end")))
    row._popup(types.SimpleNamespace(x_root=5, y_root=5))
    assert shown and shown[0] >= 2


# ------------------------------------------------------------------------------ settings
def test_the_setting_exists_and_is_on_by_default(mapp):
    assert mapp.cfg.get("auto_music") is True
    mapp._open_settings()
    panel = mapp.settings_panel
    assert bool(panel.auto_music_switch.get()) is True
    panel.auto_music_switch.toggle()
    assert mapp.cfg.get("auto_music") is False
    panel.auto_music_switch.toggle()
    assert mapp.cfg.get("auto_music") is True
