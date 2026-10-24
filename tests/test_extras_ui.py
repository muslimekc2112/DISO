"""📊 history, ⌨ shortcuts (F1) and backup / restore, from the download window."""
import json
import os

import pytest
from ui_support import notice

from app import backup
from app.extra_ui import SHORTCUTS, HistoryWindow, ShortcutsWindow
from app.models import DONE, Item

pytestmark = pytest.mark.gui


def finished(app, tmp_path, name, size=4000):
    it = Item(f"https://www.youtube.com/watch?v={name}", kind="video", title=name)
    it.state, it.started = DONE, 1.0
    it.final_path = str(tmp_path / f"{name}.mp4")
    open(it.final_path, "wb").write(b"x" * size)
    app.manager.items.append(it)
    app.manager.events.put(("done", it))
    return it


def test_finished_downloads_go_into_the_history_and_its_window(app, tmp_path):
    finished(app, tmp_path, "Bir")
    finished(app, tmp_path, "Iki", 8000)
    app._drain_events()
    assert [e["title"] for e in app.history.entries] == ["Iki", "Bir"]
    win = app.open_history()
    assert isinstance(win, HistoryWindow) and win._iconbitmap_method_called
    rows = [win.tree.item(i, "values") for i in win.tree.get_children()]
    assert [r[1] for r in rows] == ["Iki", "Bir"] and rows[0][2] == "Video"
    assert win.card_labels["total"][0].cget("text") == "2 indirme"
    win.search.insert(0, "bir")
    win.refresh()
    assert [win.tree.item(i, "values")[1] for i in win.tree.get_children()] == ["Bir"]
    assert app.open_history() is win                                     # one window, brought to the front


def test_clearing_the_history_asks_first(app, tmp_path, monkeypatch):
    from tkinter import messagebox
    finished(app, tmp_path, "Bir")
    app._drain_events()
    win = app.open_history()
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)
    win.clear()
    assert len(app.history.entries) == 1
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    win.clear()
    assert app.history.entries == [] and win.empty.winfo_manager() == "place"


def test_the_history_button_is_in_the_link_row(app):
    assert app.history_button.cget("text") == "📊"


def test_f1_opens_the_shortcuts_everywhere(app):
    win = app.open_shortcuts()
    assert isinstance(win, ShortcutsWindow) and win._iconbitmap_method_called
    assert len(win.rows) == sum(len(items) for _, items in SHORTCUTS)
    assert ("F1", "Bu pencere") in win.rows
    assert app.open_shortcuts() is win
    assert "<Key-F1>" in app.bind()


def test_a_backup_is_made_and_restored_on_the_next_start(app, tmp_path, monkeypatch):
    app.apply_setting("theme", "Açık")
    app._store().create("Benim Listem")
    target = str(tmp_path / "yedek.disoyedek")
    assert app.make_backup(target) == target and "Yedek hazır" in notice(app)
    with open(target, "rb"):
        pass
    content = backup.read_backup(target)
    assert "Benim Listem" in json.loads(content["files"]["playlists.json"])["playlists"]
    closed = []
    monkeypatch.setattr(app, "_on_close", lambda: closed.append(True))
    assert app.restore_backup(target, ask=False)
    assert app.restart_requested and closed
    from app.utils import app_data_dir
    assert os.path.isdir(os.path.join(app_data_dir(), backup.PENDING))


def test_a_wrong_backup_file_is_explained(app, tmp_path, monkeypatch):
    from app import ui
    shown = []
    monkeypatch.setattr(ui.messagebox, "showerror", lambda title, text, **k: shown.append(text))
    p = tmp_path / "x.disoyedek"
    p.write_text("çöp")
    assert app.restore_backup(str(p), ask=False) is False
    assert shown and "bozuk" in shown[0] and not app.restart_requested


def test_saying_no_to_the_restart_keeps_the_backup_for_later(app, tmp_path, monkeypatch):
    from app import ui
    target = str(tmp_path / "y.disoyedek")
    app.make_backup(target)
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: False)
    assert app.restore_backup(target)
    assert not app.restart_requested and "bir dahaki açışında" in notice(app)


def test_the_settings_have_the_backup_and_help_buttons(app):
    app._open_settings()
    panel = app.settings_panel
    assert panel.backup_button.cget("text") == "💾 Yedek al"
    assert panel.restore_button.cget("text") == "📂 Yedeği yükle"
    assert panel.shortcuts_button.cget("text") == "⌨ Kısayollar"
