"""The download window: the music player's downloads are not listed here, ▶ ⏸ 🧹 🗑 for the whole list
(🗑 asks first when downloads are still going), and the 🧲 button for .torrent files."""
import os

import pytest
from ui_support import add_item, shown

from app import ui
from app.models import CANCELLED, DONE, DOWNLOADING, ERROR, PAUSED, QUEUED


@pytest.mark.gui
def test_what_the_music_player_downloads_is_not_listed_here(app):
    add_item(app, "Dosya", DONE)
    add_item(app, "Şarkı", DOWNLOADING, origin="music")
    add_item(app, "Listeden", QUEUED, origin="music-list")
    assert shown(app) == ["Dosya"]
    assert [i.title for i in app.download_items()] == ["Dosya"]
    app._update_status()
    assert "Aktif: 0/" in app.status.cget("text") and "Sırada: 0" in app.status.cget("text")


@pytest.mark.gui
def test_the_bulk_buttons_leave_the_music_players_downloads_alone(app, monkeypatch):
    mine = add_item(app, "Dosya", PAUSED)
    song = add_item(app, "Şarkı", PAUSED, origin="music")
    started = []
    monkeypatch.setattr(app.manager, "start", started.append)
    app.start_all()
    assert started == [mine]
    paused = []
    monkeypatch.setattr(app.manager, "pause", paused.append)
    app.pause_all()
    assert paused == [mine]
    mine.state, song.state = DONE, DONE
    app.clear_finished()
    assert app.manager.items == [song]


@pytest.mark.gui
def test_clear_all_asks_when_downloads_are_going_and_cancels_them(app, monkeypatch):
    for title, state in (("A", DOWNLOADING), ("B", DOWNLOADING), ("C", QUEUED), ("D", PAUSED), ("E", DONE)):
        add_item(app, title, state)
    song = add_item(app, "Şarkı", DOWNLOADING, origin="music")
    asked = []
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda title, text, **k: asked.append(text) or False)
    assert app.clear_all() is False and len(app.download_items()) == 5             # "Hayır": nothing changes
    assert asked == ["3 indirme devam ediyor.\n1 indirme duraklatılmış; yarım inen kısımları silinir.\n\n"
                     "İptal edip listeyi temizlemek istediğine emin misin?"]
    stopped = []
    for it in app.download_items():
        it.request_stop = lambda reason, it=it: stopped.append((it.title, reason))
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
    assert app.clear_all() is True
    assert app.manager.items == [song] and shown(app) == []
    assert sorted(stopped) == [("A", "cancel"), ("B", "cancel")]


@pytest.mark.gui
def test_clear_all_with_nothing_going_does_not_ask(app, monkeypatch):
    add_item(app, "E", DONE)
    add_item(app, "F", ERROR)
    add_item(app, "G", CANCELLED)
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: pytest.fail("nothing to ask"))
    assert app.clear_all() is True and app.manager.items == []
    assert app.clear_all() is False                                               # an empty list: nothing to do


@pytest.mark.gui
def test_switching_windows_shows_the_new_one_in_the_same_place_before_hiding_the_old(app, monkeypatch):
    from app.music_ui import MODE_DOWNLOAD, MODE_MUSIC
    from music_support import FakeBackend
    from app import player
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    app.deiconify()
    app.geometry("900x640+120+80")
    app.update()
    order = []
    for win, name in ((app, "download"), (app.music, "music")):
        for what in ("deiconify", "withdraw"):
            real = getattr(win, what)
            monkeypatch.setattr(win, what, lambda real=real, what=what, name=name: (order.append((name, what)), real())[1])
    app._switch_mode(MODE_MUSIC)
    app.update()
    assert order == [("music", "deiconify"), ("download", "withdraw")]       # never a moment with no window
    assert app.music.geometry() == app.geometry() or app.music.geometry().split("+")[1:] == ["120", "80"]
    order.clear()
    app._switch_mode(MODE_DOWNLOAD)
    app.update()
    assert order == [("download", "deiconify"), ("music", "withdraw")]
    assert app.mode == MODE_DOWNLOAD and app.mode_bar.get() == MODE_DOWNLOAD


@pytest.mark.gui
def test_the_torrent_button_adds_torrent_files(app, monkeypatch, tmp_path):
    files = [tmp_path / "ubuntu.torrent", tmp_path / "debian.torrent"]
    for f in files:
        f.write_bytes(b"d4:infod4:name1:xee")
    added = []
    monkeypatch.setattr(app, "add_urls", lambda urls, *a, **k: added.extend(urls) or len(urls))
    monkeypatch.setattr(ui.filedialog, "askopenfilenames", lambda **k: [str(f) for f in files])
    assert app.torrent_btn.cget("text") == "🧲"
    app.torrent_btn.invoke()
    assert added == [f.as_uri() for f in files]
    monkeypatch.setattr(ui.filedialog, "askopenfilenames", lambda **k: "")        # cancelled
    assert app.add_torrent_files() == 0 and len(added) == 2
    assert os.path.isfile(files[0])
