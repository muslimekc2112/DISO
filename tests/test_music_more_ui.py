"""The music window's newest parts, driven like a person would: the "play next" line, cross-fade setting,
the mini player, Windows' media panel and the taskbar buttons, the 30 second preview, search history and
suggestions, and downloading a whole (YouTube Music) playlist into a list of its own."""
import os
import time

import pytest
from music_support import FakeBackend, FakeReader, make_wav

from app import music_search, player, tags
from app.models import DONE
from app.music_ui import SLEEP_OFF, VIEW_FIND, VIEW_LISTS, MiniPlayer  # noqa: F401

pytestmark = pytest.mark.gui


@pytest.fixture
def music_app(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app.manager.set_gate(False)
    app._ensure_music()
    return app, app.music


@pytest.fixture
def songs(tmp_path):
    return [make_wav(tmp_path / f"{n}.wav") for n in ("Sabah", "Ogle", "Aksam", "Gece")]


def add(music, paths):
    music._pick_files = lambda: paths
    music._add_files()


def menu(items):
    return {e[0]: e[1] for e in items if e}


# ------------------------------------------------------------------------------ play next / the line
def test_play_next_and_add_to_the_line_from_the_menu(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("0")
    music._play_selected()
    music.tree.selection_set("3")
    menu(music.track_menu_items())["⏭ Sıradaki olarak çal"]()
    music.tree.selection_set("2")
    menu(music.track_menu_items())["➕ Sıraya ekle"]()
    assert music.queue_btn.cget("text") == "📋 Sıra (2)"
    music.controller.backend.ended = True
    music._tick()
    assert music.controller.current_title() == "Gece"
    assert music.now_label.cget("text") == "Gece" and "▶" not in [music.tree.item(i, "values")[0] for i in music.tree.get_children()]
    music.controller.backend.ended = True
    music._tick()
    assert music.controller.current_title() == "Aksam"
    music.controller.backend.ended = True
    music._tick()
    assert music.controller.current_title() == "Ogle"                      # the list goes on after the first song


def test_play_next_with_nothing_playing_plays_it_now(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("2")
    music._play_next_selected()
    assert music.controller.state == "playing" and music.controller.current_title() == "Aksam"


def test_the_line_can_be_looked_at_shortened_and_cleared(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set(("1", "2", "3"))
    music._queue_selected()
    items = music.queue_menu_items()
    assert [e[0] for e in items if e][:3] == ["1. Ogle   ✖", "2. Aksam   ✖", "3. Gece   ✖"]
    items[1][1]()                                                         # a click takes Aksam out
    assert [t["title"] for t in music.controller.queue] == ["Ogle", "Gece"]
    menu(music.queue_menu_items())["Sırayı temizle"]()
    assert music.controller.queue == [] and music.queue_btn.cget("text") == "📋 Sıra"
    assert [e[0] for e in music.queue_menu_items()] == ["Sırada şarkı yok"]


# ------------------------------------------------------------------------------ cross-fade setting
def test_the_cross_fade_is_chosen_in_the_menu_and_remembered(music_app):
    app, music = music_app
    fades = menu(menu(music.player_menu_items())["🎚 Şarkılar arası geçiş"])
    assert list(fades) == ["●  Kapalı".replace("●  ", "● "), "   3 sn", "   6 sn", "   10 sn"]
    fades["   6 sn"]()
    assert music.controller.fade_ms == 6000 and music.store.state["fade"] == 6
    assert "6 saniyede" in music.note_label.cget("text")
    assert "● 6 sn" in menu(menu(music.player_menu_items())["🎚 Şarkılar arası geçiş"])


def test_the_app_gives_the_player_a_second_voice_for_fades(music_app):
    app, music = music_app
    assert isinstance(music.controller.spare, FakeBackend) and music.controller.spare is not music.controller.backend


# ------------------------------------------------------------------------------ mini player
def test_the_mini_player_steps_in_and_out(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.deiconify()
    music.update()
    music.tree.selection_set("1")
    music._play_selected()
    music.open_mini()
    mini = music.mini
    assert isinstance(mini, MiniPlayer) and music.state() == "withdrawn"
    assert mini.attributes("-topmost") and mini._iconbitmap_method_called
    music._tick()
    assert mini.title_label.cget("text") == "Ogle" and mini.play_btn.cget("text") == "⏸"
    mini.next_btn.invoke()
    music._tick()
    assert mini.title_label.cget("text") == "Aksam"
    music.controller.backend.position = 2500
    music._tick()
    assert abs(mini.bar.get() - 0.5) < 0.01
    mini.big_btn.invoke()
    assert music.mini is None and music.state() == "normal"
    music.withdraw()


def test_closing_the_app_closes_the_mini_player(music_app, songs):
    app, music = music_app
    music.open_mini()
    mini = music.mini
    music.shutdown()
    assert music.mini is None and not mini.winfo_exists()


# ------------------------------------------------------------------------------ media panel and taskbar
def test_windows_media_panel_shows_the_song_and_its_buttons_work(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.store.apply_tags({songs[0]: {"title": "Sabah Şarkısı", "artist": "Ali", "album": "İlk"}})
    music.tree.selection_set("0")
    music._play_selected()
    music._tick()
    assert music.overlay.shown[-1] == ("Sabah Şarkısı", "Ali", "İlk", None)
    assert music.overlay.states[-1] == "playing"
    music.overlay.pressed.put("next")
    music._tick()
    assert music.controller.current_title() == "Ogle"
    music.overlay.pressed.put("toggle")
    music._tick()
    assert music.controller.state == "paused" and music.overlay.states[-1] == "paused"
    music.shutdown()
    assert music.overlay.closed


def test_taskbar_buttons_come_when_the_window_shows_and_drive_the_player(music_app, songs):
    app, music = music_app
    add(music, songs)
    music._tick()
    assert not music.thumbbar.active                                      # hidden window: no taskbar button
    music.deiconify()
    music.update()
    music._play_selected()
    music._tick()
    assert music.thumbbar.active and music.thumbbar.playing
    music.thumbbar.pressed.put("next")
    music._tick()
    assert music.controller.current_title() == "Ogle"
    music.thumbbar.pressed.put("toggle")
    music._tick()
    assert music.controller.state == "paused" and not music.thumbbar.playing
    music.shutdown()
    assert not music.thumbbar.active
    music.withdraw()


# ------------------------------------------------------------------------------ preview
def results():
    return [{"url": f"https://www.youtube.com/watch?v=p{i}", "title": f"Parça {i}", "channel": "k", "duration": 200}
            for i in range(2)]


def search(music, answer):
    music._show_view(VIEW_FIND)
    music.search_entry.delete(0, "end")
    music.search_entry.insert(0, "tarkan")
    music._search()
    music.searcher.give(answer)
    music._tick()


def test_a_preview_pauses_the_music_plays_30_seconds_and_gives_the_music_back(music_app, songs, tmp_path):
    app, music = music_app
    add(music, songs)
    music._show_view(VIEW_LISTS)
    music._play_selected()
    found = results()
    search(music, found)
    music.results_tree.selection_set("1")
    music._preview_selected()
    assert music.previewer.asked == [found[1]] and "hazırlanıyor" in music.find_label.cget("text")
    clip = make_wav(tmp_path / "clip.mp3")
    music.previewer.give(clip, query=found[1])
    music._tick()
    assert music.preview and music.controller.state == "paused"
    assert music._preview_backend.loaded == clip and music._preview_backend.playing
    assert music.preview_btn.cget("text") == "⏹ Durdur" and "Önizleniyor" in music.find_label.cget("text")
    music.preview["until"] = time.time() - 1                               # 30 seconds later
    music._tick()
    assert music.preview is None and music.controller.state == "playing" and not os.path.exists(clip)


def test_pressing_preview_again_stops_it(music_app, tmp_path):
    app, music = music_app
    found = results()
    search(music, found)
    music.results_tree.selection_set("0")
    music._preview_selected()
    music.previewer.give(make_wav(tmp_path / "c.mp3"), query=found[0])
    music._tick()
    music._preview_selected()
    assert music.preview is None and music.preview_btn.cget("text") == "🎧 Önizle"


def test_a_preview_that_cannot_be_made_is_said(music_app):
    app, music = music_app
    found = results()
    search(music, found)
    music.results_tree.selection_set("0")
    music._preview_selected()
    music.previewer.give(None, error="HTTP Error 403: Forbidden", query=found[0])
    music._tick()
    assert "hazırlayamadım" in music.find_label.cget("text") and music.preview is None


def test_starting_the_music_ends_a_preview(music_app, songs, tmp_path):
    app, music = music_app
    add(music, songs)
    found = results()
    search(music, found)
    music.results_tree.selection_set("0")
    music._preview_selected()
    music.previewer.give(make_wav(tmp_path / "c.mp3"), query=found[0])
    music._tick()
    music._show_view(VIEW_LISTS)
    music._play_selected()
    music._tick()
    assert music.preview is None and music.controller.state == "playing"


def test_the_preview_starts_about_a_third_in():
    assert music_search.preview_start(30) == 0
    assert music_search.preview_start(200) == 60
    assert music_search.preview_start(80) == 24
    assert music_search.preview_start(3600) == 1080


# ------------------------------------------------------------------------------ search history and suggestions
def test_searches_are_remembered_newest_first_without_doubles(music_app):
    app, music = music_app
    for q in ("tarkan", "sezen aksu", "Tarkan"):
        music.search_entry.delete(0, "end")
        music.search_entry.insert(0, q)
        music._search()
    assert music.store.state["searches"] == ["Tarkan", "sezen aksu"]
    music.search_entry.delete(0, "end")
    assert music.suggestion_rows() == [("Tarkan", "history"), ("sezen aksu", "history")]


def test_typing_asks_for_suggestions_and_shows_them_under_the_box(music_app):
    app, music = music_app
    music.store.remember_search("barış manço gülpembe")
    music._show_view(VIEW_FIND)
    music.search_entry.insert(0, "barış")
    music._on_search_key(type("E", (), {"keysym": "s"})())
    music.update()
    time.sleep(0.3)
    music.update()
    assert music.suggester.asked == ["barış"]
    music.suggester.give(["barış manço", "barış manço gülpembe", "barış akarsu"], query="barış")
    music._tick()
    assert music.suggestion_rows() == [("barış manço gülpembe", "history"), ("barış manço", "suggest"),
                                       ("barış akarsu", "suggest")]
    assert music.suggest_box.winfo_manager() == "place" and len(music._suggest_rows) == 3


def test_arrows_and_enter_pick_a_suggestion(music_app):
    app, music = music_app
    music._show_view(VIEW_FIND)
    music.search_entry.insert(0, "tar")
    music._suggestions = ["tarkan", "tarkan şımarık"]
    music._show_suggestions()
    music._move_suggestion(+1)
    music._move_suggestion(+1)
    music._on_search_return()
    assert music.search_entry.get() == "tarkan şımarık" and music.searcher.asked == ["tarkan şımarık"]
    assert music.suggest_box.winfo_manager() == ""


def test_an_old_suggestion_for_other_text_is_ignored(music_app):
    app, music = music_app
    music._show_view(VIEW_FIND)
    music.search_entry.insert(0, "sezen")
    music.suggester.give(["tarkan"], query="tar")
    music._tick()
    assert music.suggestion_rows() == []


def test_the_history_can_be_cleared(music_app):
    app, music = music_app
    music.store.remember_search("x")
    music._show_view(VIEW_FIND)
    music._show_suggestions()
    music._clear_history()
    assert music.store.state["searches"] == [] and music.suggest_box.winfo_manager() == ""


def test_youtubes_suggestion_answer_is_read():
    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return ["tar", ["tarkan", "tarkan şımarık", 5, ""]]

    asked = []
    assert music_search.suggest("tar", get=lambda url, params=None, **k: asked.append(params) or R()) == \
        ["tarkan", "tarkan şımarık"]
    assert asked[0]["ds"] == "yt" and music_search.suggest("a") == [] and music_search.suggest("https://x/y") == []


# ------------------------------------------------------------------------------ a whole playlist
def playlist():
    found = music_search.Found([{"url": f"https://music.youtube.com/watch?v=s{i}", "title": f"Şarkı {i}",
                                 "channel": "", "duration": 180} for i in range(3)], "Yolculuk Şarkıları")
    return found


def test_a_playlist_link_offers_to_download_all_into_a_list(music_app, tmp_path):
    app, music = music_app
    search(music, playlist())
    assert music.results_title == "Yolculuk Şarkıları" and music.import_btn.winfo_manager() == "grid"
    assert "çalma listesi: 3 şarkı" in music.find_label.cget("text")
    music._download_all()
    items = app.song_items()
    assert [it.title for it in items] == ["Şarkı 0", "Şarkı 1", "Şarkı 2"]
    assert {it.origin for it in items} == {"music-list"} and {it.group for it in items} == {"Yolculuk Şarkıları"}
    assert "Yolculuk Şarkıları" in music.store.names() and music.import_btn.winfo_manager() == ""
    for it, name in zip(reversed(items), ("c", "b", "a")):                   # they finish in the wrong order ...
        it.final_path = make_wav(tmp_path / f"{name}.mp3")
        it.state = DONE
        app.manager.events.put(("done", it))
        app._drain_events()
    assert [t["title"] for t in music.store.tracks("Yolculuk Şarkıları")] == ["a", "b", "c"]   # ... but keep the list's order
    assert app.song_dialog is None                                         # no "which list?" question


def test_a_single_video_link_offers_no_list(music_app):
    app, music = music_app
    search(music, music_search.Found([{"url": "u", "title": "t", "channel": "", "duration": 1}], "Liste"))
    assert music.results_title == "" and music.import_btn.winfo_manager() == ""


def test_downloading_the_same_playlist_twice_does_not_double_it(music_app, tmp_path):
    app, music = music_app
    search(music, playlist())
    music._download_all()
    added, name = app.download_playlist(list(playlist()), "Yolculuk Şarkıları")
    assert added == 0 and len(app.song_items()) == 3


def test_a_link_search_keeps_the_playlist_name(monkeypatch):
    from app import video_engine as ve
    monkeypatch.setattr(ve, "expand_playlist", lambda url, cookies=None: ve.PlaylistEntries(
        [("https://music.youtube.com/watch?v=a", "A", 100), ("https://music.youtube.com/watch?v=b", "B", 0)], "Albüm"))
    found = music_search.search("https://music.youtube.com/playlist?list=OLAK5uy_x")
    assert found.title == "Albüm" and [r["title"] for r in found] == ["A", "B"]
