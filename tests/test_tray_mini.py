"""The tray menu (music controls, downloads, the language of the moment) and the bigger mini player."""
import pytest
from music_support import FakeBackend, FakeReader, make_wav
from ui_support import FakeTray, add_item

from app import player, tags, tray
from app.models import DOWNLOADING, PAUSED, QUEUED
from app.music_ui import SLEEP_OFF, MiniPlayer

needs_tray = pytest.mark.skipif(not tray.AVAILABLE, reason="pystray is not installed")


# ------------------------------------------------------------------------------ the menu itself
def entries(menu):
    """{text: item} of a pystray menu, separators left out."""
    return {i.text: i for i in menu.items if i.text and i.text != "- - - -"}


@needs_tray
def test_the_menu_shows_the_song_and_its_buttons_call_back_with_a_value():
    events = []
    icon = tray.TrayIcon("t", lambda name, value=None: events.append((name, value)))
    icon.set_state(player="playing", track="Gül Pembe", artist="Barış Manço", time="1:02 / 4:10",
                   next="Dönence", playing_list="Sevdiklerim", lists=["Sevdiklerim", "Yol"], volume=50,
                   repeat="Liste", shuffle=True)
    items = entries(icon._icon.menu)
    assert "♪ Barış Manço — Gül Pembe" in items
    assert "     1:02 / 4:10   •   Sevdiklerim" in items and "     Sıradaki: Dönence" in items
    assert not items["♪ Barış Manço — Gül Pembe"].enabled                # only shows
    items["⏸ Duraklat"](icon._icon)
    items["⏭ Sonraki şarkı"](icon._icon)
    assert items["🔀 Karışık çal"].checked
    repeat = entries(items["🔁 Tekrar: Liste"].submenu)
    assert repeat["Liste"].checked and not repeat["Tek"].checked
    repeat["Tek"](icon._icon)
    volume = entries(items["🔊 Ses: %50"].submenu)
    assert volume["%50"].checked
    volume["➕ Sesi aç"](icon._icon)
    volume["%25"](icon._icon)
    volume["🔇 Sessiz"](icon._icon)
    lists = entries(items["📋 Çalma listesi"].submenu)
    assert lists["Sevdiklerim"].checked
    lists["Yol"](icon._icon)
    sleep = entries(items["😴 Uyku zamanlayıcısı: Kapalı"].submenu)
    sleep["30 dk"](icon._icon)
    sleep["Parça bitince"](icon._icon)
    assert events == [("music", "toggle"), ("music", "next"), ("repeat", "Tek"), ("volume", "+"), ("volume", 25),
                      ("volume", "mute"), ("play_list", "Yol"), ("sleep", "30 dk"), ("sleep", "track")]


@needs_tray
def test_with_nothing_playing_the_menu_offers_to_play_and_greys_out_the_rest():
    icon = tray.TrayIcon("t", lambda *a: None)
    items = entries(icon._icon.menu)
    assert "♪ Şu an müzik çalmıyor" in items and "▶ Müzik çal" in items
    assert not items["⏹ Durdur"].enabled and not items["🎤 Şarkı sözleri"].enabled
    assert not items["⏸ Hepsini duraklat"].enabled and not items["▶ Hepsini başlat"].enabled
    assert "⬇ Şu an indirme yok" in items
    icon.set_state(can_resume=True, active=2, queued=3, paused=1, speed="1.5 MB")
    items = entries(icon._icon.menu)
    assert "▶ Kaldığın yerden çal" in items
    assert "⬇ 2 indiriliyor • 1.5 MB/s • 3 sırada • 1 duraklatıldı" in items
    assert items["⏸ Hepsini duraklat"].enabled and items["▶ Hepsini başlat"].enabled


@needs_tray
def test_the_menu_switches_language_at_once():
    icon = tray.TrayIcon("t", lambda *a: None, language="tr")
    assert "Göster" in entries(icon._icon.menu)
    icon.set_language("English")
    icon.set_state(player="paused", track="Song", volume=70, sleep="12 dk")
    items = entries(icon._icon.menu)
    for text in ("Show", "Quit", "⏸ Song", "▶ Play", "⏭ Next song", "🔀 Shuffle", "🔁 Repeat: Off", "🔊 Volume: 70%",
                 "😴 Sleep timer: 12 min left", "⬇ Nothing is downloading", "📋 Download the link in the clipboard",
                 "⬇ Download window", "🎵 Music player", "⚙ Settings"):
        assert text in items, text
    assert not any(any(ch in t for ch in "çğışöüÇĞİŞÖÜ") for t in items)        # not a Turkish word left
    icon.set_language("Türkçe")
    assert "Göster" in entries(icon._icon.menu)


@needs_tray
def test_a_long_song_name_is_cut_and_many_lists_do_not_make_a_huge_menu():
    icon = tray.TrayIcon("t", lambda *a: None)
    icon.set_state(player="playing", track="x" * 200, lists=[f"L{i}" for i in range(60)])
    items = entries(icon._icon.menu)
    head = next(t for t in items if t.startswith("♪ "))
    assert len(head) <= 50 and head.endswith("…")
    assert len(entries(items["📋 Çalma listesi"].submenu)) == tray.MAX_LISTS


@needs_tray
def test_changing_nothing_keeps_the_same_state_object():
    icon = tray.TrayIcon("t", lambda *a: None)
    before = icon.state
    icon.set_state(volume=80)                 # the same as it was
    assert icon.state is before


# ------------------------------------------------------------------------------ the app behind the menu
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


def press(app, name, value=None):
    """As the tray's thread does it: through the queue, then the window's turn."""
    tray_icon = FakeTray.instances[0]
    tray_icon.on_event(name, value) if value is not None else tray_icon.on_event(name)
    app._drain_ui_calls()


pytestmark = pytest.mark.gui


def test_the_tray_controls_the_music_and_shows_what_plays(music_app, songs):
    app, music = music_app
    add(music, songs)
    app.apply_setting("tray_on_close", True)
    icon = FakeTray.instances[0]
    assert icon.state["player"] == "stopped" and music.viewed in icon.state["lists"]
    press(app, "music", "toggle")
    assert music.controller.state == "playing" and icon.state["track"] == "Sabah"
    assert icon.state["next"] == "Ogle" and icon.state["time"] == "0:00 / 0:05"
    press(app, "music", "next")
    assert music.controller.current_title() == "Ogle" and icon.state["track"] == "Ogle"
    press(app, "music", "shuffle")
    assert music.controller.shuffle and music.shuffle_var.get() and icon.state["shuffle"]
    assert icon.state["next"] == ""                              # shuffle picks it later: not known yet
    press(app, "repeat", "Tek")
    assert music.controller.repeat == "Tek" and music.store.state["repeat"] == "Tek"
    assert icon.state["next"] == "Ogle"
    press(app, "volume", 30)
    assert int(music.volume.get()) == 30 and music.controller.backend.active.volume == 30
    press(app, "volume", "+")
    assert int(music.volume.get()) == 40 and icon.state["volume"] == 40
    press(app, "volume", "mute")
    assert int(music.volume.get()) == 0 and icon.state["muted"]
    press(app, "volume", "mute")
    assert int(music.volume.get()) == 40 and not icon.state["muted"]
    press(app, "sleep", "30 dk")
    assert music.sleep_at and icon.state["sleep"] == "30 dk"
    press(app, "sleep", "track")
    assert music.sleep_after_track and icon.state["sleep"] == "track"
    press(app, "sleep", "off")
    assert not music.sleep_at and not music.sleep_after_track and music.sleep_menu.get() == SLEEP_OFF
    press(app, "music", "pause" if False else "toggle")
    assert music.controller.state == "paused" and icon.state["player"] == "paused"
    press(app, "music", "stop")
    assert music.controller.state == "stopped"


def test_the_tray_plays_a_chosen_list_from_its_start(music_app, songs):
    app, music = music_app
    add(music, songs[:2])
    other = app.new_music_list("Yol")
    music.show_list(other)
    add(music, songs[2:])
    music.show_list(music.store.user_names()[0])
    app.apply_setting("tray_on_close", True)
    press(app, "play_list", other)
    assert music.playing_list == other and music.controller.current_title() == "Aksam"
    assert FakeTray.instances[0].state["playing_list"] == other
    press(app, "play_list", "yok böyle bir liste")
    assert music.playing_list == other


def test_the_tray_opens_and_closes_the_mini_player_and_switches_windows(music_app, songs):
    app, music = music_app
    add(music, songs)
    app.apply_setting("tray_on_close", True)
    press(app, "music", "mini")
    assert isinstance(music.mini, MiniPlayer) and FakeTray.instances[0].state["mini"]
    press(app, "music", "mini")
    assert music.mini is None and music.state() == "withdrawn"            # closed from the tray: no big window
    press(app, "show_music")
    app.update()
    assert app.mode == "Müzik çalar modu" and music.state() == "normal"
    assert FakeTray.instances[0].state["mode"] == "music"
    press(app, "show_download")
    app.update()
    assert app.mode == "İndirme modu" and music.state() == "withdrawn" and app.state() == "normal"


def test_the_tray_shows_the_downloads_and_follows_the_language(app):
    app.apply_setting("tray_on_close", True)
    add_item(app, "A", DOWNLOADING, speed=2 * 1024 * 1024)
    add_item(app, "B", QUEUED)
    add_item(app, "C", PAUSED)
    app._update_tray_state()
    s = FakeTray.instances[0].state
    assert (s["active"], s["queued"], s["paused"], s["speed"]) == (1, 1, 1, "2.0 MB")
    assert s["lang"] == "tr"
    app.apply_setting("language", "English")
    assert FakeTray.instances[0].state["lang"] == "en"         # before DISO starts again


def test_the_tray_downloads_the_link_in_the_clipboard(app, monkeypatch):
    app.apply_setting("tray_on_close", True)
    added = []
    monkeypatch.setattr(app, "add_urls", lambda urls, kind=None: added.append(urls))
    monkeypatch.setattr(app, "_clipboard_text", lambda: "bak: https://example.com/a.zip ve magnet:?xt=urn:btih:abc")
    press(app, "paste")
    assert added == [["https://example.com/a.zip", "magnet:?xt=urn:btih:abc"]]
    monkeypatch.setattr(app, "_clipboard_text", lambda: "link yok")
    press(app, "paste")
    assert len(added) == 1 and app.notes["toast"]


def test_the_tray_opens_the_download_folder(app, monkeypatch, tmp_path):
    from app import ui
    opened = []
    monkeypatch.setattr(ui, "open_file", opened.append)
    app.folder_entry.delete(0, "end")
    app.folder_entry.insert(0, str(tmp_path / "inenler"))
    app.apply_setting("tray_on_close", True)
    press(app, "open_folder")
    assert opened == [str(tmp_path / "inenler")] and (tmp_path / "inenler").is_dir()


# ------------------------------------------------------------------------------ the mini player
def test_the_mini_player_has_shuffle_repeat_volume_and_the_next_song(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("0")
    music._play_selected()
    music.open_mini()
    mini = music.mini
    music._tick()
    assert mini.next_label.cget("text") == "Sıradaki: Ogle"
    assert mini.len_label.cget("text") == "0:05"
    mini.shuffle_btn.invoke()
    assert music.controller.shuffle and music.shuffle_var.get()
    music._tick()
    assert mini.next_label.cget("text") == " "
    mini.shuffle_btn.invoke()
    mini.repeat_btn.invoke()
    assert music.controller.repeat == "Liste"
    mini.repeat_btn.invoke()
    music._tick()
    assert music.controller.repeat == "Tek" and mini.repeat_btn.cget("text") == "🔂"
    assert mini.next_label.cget("text") == "Sıradaki: Sabah"
    mini._on_volume(35)
    assert int(music.volume.get()) == 35 and music.controller.backend.active.volume == 35
    mini._on_wheel(type("E", (), {"delta": 120})())
    assert int(music.volume.get()) == 40
    music.set_volume(10)
    music._tick()
    assert int(mini.volume.get()) == 10 and mini.mute_btn.cget("text") == "🔉"
    mini.mute_btn.invoke()
    music._tick()
    assert int(music.volume.get()) == 0 and mini.mute_btn.cget("text") == "🔇"
    mini.mute_btn.invoke()
    assert int(music.volume.get()) == 10


def test_the_mini_player_seeks_with_its_bar_and_the_arrow_keys(music_app, songs):
    app, music = music_app
    add(music, songs)
    music.tree.selection_set("0")
    music._play_selected()
    music.open_mini()
    mini = music.mini
    backend = music.controller.backend.active
    mini.bar.set(0.6)
    mini._on_seek_release()
    assert backend.position == 3000
    mini._seek_by(-5000)
    assert backend.position == 0
    mini._seek_by(+1500)
    assert backend.position == 1500
    music._tick()
    assert mini.pos_label.cget("text") == "0:01"


def test_the_mini_player_remembers_where_it_was_and_whether_it_stays_on_top(music_app):
    app, music = music_app
    music.open_mini()
    mini = music.mini
    assert mini.attributes("-topmost")
    mini.pin_btn.invoke()
    assert not mini.attributes("-topmost") and music.store.state["mini_top"] is False
    mini.geometry("+130+140")
    mini.update()
    music.close_mini(show=False)
    assert music.store.state["mini_place"]
    x, y = (int(v) for v in music.store.state["mini_place"].strip("+").split("+"))
    music.open_mini()
    mini = music.mini
    mini.update()
    assert not mini.attributes("-topmost")
    assert (mini.winfo_x(), mini.winfo_y()) == (x, y) == (130, 140)
    music.close_mini(show=False)


def test_the_mini_player_forgets_a_place_that_is_off_the_screen(music_app):
    app, music = music_app
    music.store.set_state(mini_place="+99999+99999")
    music.open_mini()
    mini = music.mini
    mini.update()
    assert mini.winfo_x() < mini.winfo_screenwidth()
    music.close_mini(show=False)


def test_the_mini_player_menu_and_the_big_window_button(music_app, songs, monkeypatch):
    app, music = music_app
    add(music, songs)
    music.open_mini()
    mini = music.mini
    items = {e[0]: e[1] for e in mini.menu_items() if e}
    sleeps = dict(items["😴 Uyku zamanlayıcısı"])
    sleeps["   30 dk"]()
    assert music.sleep_at
    items["✓ 📌 Hep üstte"]()
    assert not mini._on_top
    app.mode = "İndirme modu"                       # opened from the tray while the download window was shown
    switched = []
    monkeypatch.setattr(music, "_on_mode", switched.append)
    mini.big_btn.invoke()
    assert music.mini is None and switched == ["Müzik çalar modu"] and music.state() == "normal"
    music.withdraw()


def test_the_mini_player_in_english(music_app, songs):
    from app import lang_en
    assert ("Sıradaki: {}", "Up next: {}") in lang_en.TEMPLATES
    for text in ("Hep üstte", "Büyük pencere", "Uyku zamanlayıcısı", "Şarkı sözleri", "Çalmaya hazırlanıyor…"):
        assert text in lang_en.PLAIN


# ------------------------------------------------------------------------------ what the extension's popup gets
def test_the_extension_gets_the_downloads_and_the_language(app):
    from app.ui import BridgeApi
    a = add_item(app, "Ubuntu", DOWNLOADING, speed=1024, url="magnet:?xt=urn:btih:abc", fraction=0.25)
    add_item(app, "B", QUEUED)
    add_item(app, "C", PAUSED)
    for n in range(6):
        add_item(app, f"Q{n}", QUEUED)
    s = app.bridge_status()
    assert (s["active"], s["queued"]) == (1, 7) and len(s["items"]) == app.BRIDGE_ROWS
    assert s["items"][0] == {"name": "Ubuntu", "fraction": 0.25, "speed": 1024, "state": "active", "torrent": True}
    assert s["items"][1]["state"] == "queued" and s["items"][1]["name"] == "B"
    assert a.state == DOWNLOADING
    api = BridgeApi(app)
    assert api.language() == "tr"
    app.cfg.set("language", "English")
    assert api.language() == "en"
