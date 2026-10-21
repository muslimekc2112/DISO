"""The "Nostalji" look: the grey Windows of the 2000s and the download window laid out like the download
managers of that time (menu bar, toolbar, categories, a table, a progress window per download)."""
import json
import os
import subprocess
import sys

import pytest

from app import classic_ui, look
from app.models import DONE, DOWNLOADING, ERROR, PAUSED, QUEUED, Item

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def item(url, kind="auto", state=QUEUED, **kw):
    it = Item(url, kind=kind)
    it.state = state
    for k, v in kw.items():
        setattr(it, k, v)
    return it


# ------------------------------------------------------------------------------ without a window
@pytest.mark.parametrize("url,kind,path,expected", [
    ("https://x.com/a/setup.exe", "file", "", "program"),
    ("https://x.com/a/arsiv.rar?token=1", "file", "", "archive"),
    ("https://x.com/kitap.pdf", "auto", "", "document"),
    ("https://youtube.com/watch?v=abc", "auto", "", "video"),
    ("https://youtube.com/watch?v=abc", "audio", "", "audio"),
    ("https://youtube.com/watch?v=abc", "auto", "C:/m/Şarkı.mp3", "audio"),
    ("https://youtube.com/watch?v=abc", "video", "C:/v/film.mkv", "video"),
    ("https://x.com/files/data.bin", "file", "", "other"),
])
def test_every_download_has_a_type(url, kind, path, expected):
    assert classic_ui.file_type(item(url, kind, final_path=path)) == expected


def test_the_categories_choose_by_type_and_by_state():
    done = item("https://x.com/a.mp3", "file", DONE)
    failed = item("https://x.com/b.zip", "file", ERROR)
    waiting = item("https://x.com/c.exe", "file", QUEUED)
    assert [k for k in classic_ui.CATEGORY_KEYS if classic_ui.in_category(k, done)] == ["all", "audio", "finished"]
    assert [k for k in classic_ui.CATEGORY_KEYS if classic_ui.in_category(k, failed)] == \
        ["all", "archive", "unfinished", "error"]
    assert [k for k in classic_ui.CATEGORY_KEYS if classic_ui.in_category(k, waiting)] == \
        ["all", "program", "unfinished", "queue"]


def test_a_row_of_the_table():
    it = item("https://x.com/big.iso", "file", DOWNLOADING, title="big.iso", done=2 * 1024 ** 3,
              total=5 * 1024 ** 3, fraction=0.4, speed=3 * 1024 ** 2, eta=65, conns=8, added=0)
    name, (size, status, eta, speed, date, desc) = classic_ui.row_values(it)
    assert name == "big.iso" and size == "5.0 GB" and status == "40.00%" and speed == "3.0 MB/s"
    assert eta and date and desc == ""
    it.state, it.error = ERROR, "Sunucu 404 dedi"
    assert classic_ui.row_values(it)[1][1] == "Hata" and classic_ui.row_values(it)[1][5] == "Sunucu 404 dedi"
    it.state = PAUSED
    assert classic_ui.status_text(it) == "Duraklatıldı 40.00%"
    it.state = QUEUED
    assert classic_ui.row_values(it, "Zamanlayıcı 02:00'yi bekliyor")[1][5] == "Zamanlayıcı 02:00'yi bekliyor"


def test_the_pictures_are_drawn_for_every_name():
    from app import classic_icons
    for name in classic_icons.NAMES:
        img = classic_icons.image(name, 32)
        assert img.size == (32, 32) and img.getchannel("A").getbbox() is not None, name
        faded = classic_icons.image(name, 16, disabled=True)
        assert faded.getchannel("A").getextrema()[1] < 140, name          # see-through: cannot be pressed


def test_the_look_is_grey_square_and_always_light():
    import customtkinter
    try:
        assert look.apply("Nostalji") == "Nostalji" and look.is_nostalgia() and not look.is_new()
        theme = customtkinter.ThemeManager.theme
        assert theme["CTk"]["fg_color"] == [look.N_FACE, look.N_FACE]
        assert theme["CTkButton"]["corner_radius"] == 3 and theme["CTkButton"]["text_color"] == ["#000000"] * 2
        assert theme["CTkFont"]["family"] == "Tahoma"
        assert look.appearance("dark") == "light" and look.grey_text() == look.N_GREY_TEXT
    finally:
        look.apply("Klasik")
    assert look.appearance("dark") == "dark" and not look.is_nostalgia()


def test_the_texts_are_readable_on_the_grey():
    from test_look import contrast
    for surface in (look.N_FACE, look.N_FIELD, look.N_BUTTON, look.N_HOVER):
        assert contrast(look.N_TEXT, surface) >= 7
    assert contrast(look.N_GREY_TEXT, look.N_FACE) >= 4.5


# ------------------------------------------------------------------------------ the window
pytest.importorskip("customtkinter")
from ui_support import add_item  # noqa: E402


@pytest.fixture
def old(make_app, monkeypatch):
    """A hidden App in the "Nostalji" look (and the stock look back for the other tests)."""
    look.apply("Nostalji")
    yield make_app
    look.apply("Klasik")


@pytest.fixture
def napp(old):
    return old()


def table_names(app):
    app._sync_rows()
    return [app.table.item(i, "text").strip() for i in app.table.get_children()]


@pytest.mark.gui
def test_the_window_is_menu_toolbar_categories_and_table(napp):
    app = napp
    assert app.nostalgia and app.list_frame is None and app.filter_menu is None
    menus = [app.menubar.entrycget(i, "label") for i in range(app.menubar.index("end") + 1)]
    assert menus == ["Görevler", "İndirmeler", "Görünüm", "Araçlar", "Yardım"]
    assert list(app.tool_buttons) == ["add", "resume", "pause", "pause_all", "delete", "delete_done", "options",
                                      "scheduler", "start_all", "update", "music", "channels", "history"]
    assert [b.cget("state") for b in app.sel_buttons] == ["disabled"] * 3        # nothing chosen yet
    assert app.category_tree.selection() == ("all",)
    assert app.table.heading("#0")["text"] == "Dosya adı"
    for name in ("url_entry", "kind_menu", "quality_menu", "bitrate_menu", "conn_menu", "cookie_menu", "subs_menu",
                 "folder_entry", "search_entry", "status", "mode_bar", "language_switch"):
        assert getattr(app, name).winfo_exists(), name


@pytest.mark.gui
def test_the_table_shows_the_downloads_and_follows_them(napp):
    app = napp
    app._sync_rows()
    assert "şimdilik bomboş" in app.empty_label.cget("text") and app.empty_label.winfo_manager() == "place"
    a = add_item(app, "Alpha.mp3", DONE, total=300, added=1, final_path="C:/m/Alpha.mp3")
    b = add_item(app, "Beta.zip", DOWNLOADING, done=50, total=200, fraction=0.25, speed=1000, eta=5, added=2)
    assert table_names(app) == ["Beta.zip", "Alpha.mp3"]                         # newest first
    assert app.empty_label.winfo_manager() == ""
    assert app.table.item(b.id, "values")[1] == "25.00%"
    b.fraction, b.done = 0.5, 100
    app._sync_rows()
    assert app.table.item(b.id, "values")[1] == "50.00%"
    assert app.table.item(a.id, "values")[1] == "Tamamlandı"
    app.manager.items.remove(a)
    assert table_names(app) == ["Beta.zip"]


@pytest.mark.gui
def test_the_categories_and_the_search_choose_the_rows(napp):
    app = napp
    add_item(app, "song.mp3", DONE, final_path="C:/m/song.mp3", added=1)
    add_item(app, "setup.exe", ERROR, added=2)
    add_item(app, "pack.zip", PAUSED, added=3)
    for category, expected in (("audio", ["song.mp3"]), ("error", ["setup.exe"]), ("finished", ["song.mp3"]),
                               ("unfinished", ["pack.zip", "setup.exe"]), ("archive", ["pack.zip"]),
                               ("all", ["pack.zip", "setup.exe", "song.mp3"])):
        app.category_tree.selection_set(category)
        app._n_on_category()
        assert table_names(app) == expected, category
    assert app.cfg.get("category") == "all"                                      # remembered
    app.search_entry.insert(0, "set")
    assert table_names(app) == ["setup.exe"]


@pytest.mark.gui
def test_a_click_on_a_heading_sorts(napp):
    app = napp
    for name, added in (("b", 1), ("c", 2), ("a", 3)):
        add_item(app, name, DONE, added=added, total=added * 100)
    app._n_sort(classic_ui.NAME_SORT)
    assert table_names(app) == ["a", "b", "c"] and app.table.heading("#0")["text"].endswith("▲")
    app._n_sort("Boyut (büyük üstte)")
    assert table_names(app) == ["a", "c", "b"]
    app._n_sort("date")                                     # newest first ...
    assert table_names(app) == ["a", "c", "b"]
    app._n_sort("date")                                     # ... and a second click: oldest first
    assert table_names(app) == ["b", "c", "a"] and app.cfg.get("sort") == "Eski üstte"


@pytest.mark.gui
def test_the_selection_drives_the_toolbar(napp, monkeypatch):
    from app import ui
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
    app = napp
    a = add_item(app, "A", PAUSED)
    b = add_item(app, "B", PAUSED)
    app._sync_rows()
    app.table.selection_set([a.id])
    app._n_on_select()
    assert app.selected == {a.id} and [x.cget("state") for x in app.sel_buttons] == ["normal"] * 3
    assert app.sel_label.cget("text") == "1 seçili"
    app._on_ctrl_a()
    assert set(app.table.selection()) == {a.id, b.id}
    app.tool_buttons["delete"].invoke()                     # two of them: asks first
    assert {it.id for it in app.manager.items} == set()


@pytest.mark.gui
def test_double_click_opens_a_finished_file_or_the_progress_window(napp, monkeypatch, tmp_path):
    from app import classic_ui as cu
    opened = []
    monkeypatch.setattr(cu, "open_file", opened.append)
    path = tmp_path / "x.mp3"
    path.write_bytes(b"x")
    done = add_item(napp, "x.mp3", DONE, final_path=str(path), total=1)
    busy = add_item(napp, "big.iso", DOWNLOADING, done=10, total=100, fraction=0.1, speed=5, eta=3, conns=4)
    napp._sync_rows()
    napp.table.focus(done.id)
    napp._n_on_double()
    assert opened == [str(path)]
    napp.table.focus(busy.id)
    napp._n_on_double()
    win = napp._progress[busy.id]
    assert win.values["done"].cget("text").endswith("(10.00%)") and win.title().startswith("10.00%")
    assert win.toggle_btn.cget("text") == "Duraklat"
    busy.state, busy.fraction, busy.done, busy.final_path = DONE, 1.0, 100, str(path)
    win.refresh()
    assert win.values["state"].cget("text") == "İndirme tamamlandı" and win.open_btn.winfo_manager() == "pack"
    assert napp.open_progress(busy) is win                                  # one window per download
    napp.manager.items.remove(busy)
    busy.removed = True
    win._tick()
    assert not win.winfo_exists()


@pytest.mark.gui
def test_the_right_click_menu_adds_the_progress_window(napp, monkeypatch):
    from app import ui
    shown = []
    monkeypatch.setattr(ui.ItemActions, "popup_menu", lambda self, parent, event, extra=(): shown.append(
        [label for label, _ in [*extra, *self.menu_commands()]]))
    it = add_item(napp, "A", PAUSED)
    napp._sync_rows()
    napp.update()
    y = napp.table.bbox(it.id)
    event = type("E", (), {"y": (y[1] + 2) if y else 0, "x_root": 0, "y_root": 0})()
    monkeypatch.setattr(napp.table, "identify_row", lambda y: it.id)
    napp._n_on_right(event)
    assert shown and shown[0][0] == "İlerleme penceresi" and "Listeden kaldır" in shown[0]
    assert napp.selected == {it.id}


@pytest.mark.gui
def test_the_new_download_window_takes_the_clipboard(napp, monkeypatch):
    added = []
    monkeypatch.setattr(napp, "add_urls", lambda urls: added.append(urls) or 1)
    monkeypatch.setattr(napp, "_clipboard_text", lambda: "https://example.com/a.zip")   # not the real clipboard
    win = napp.open_address_dialog()
    assert win.entry.get() == "https://example.com/a.zip"
    win.confirm()
    assert added == [["https://example.com/a.zip"]] and not win.winfo_exists()


@pytest.mark.gui
def test_toolbar_texts_follow_the_counts(napp):
    napp._drain_channels()
    assert napp.channels_btn.cget("text") == "Kanallar"
    napp.channel_store.new = [{"url": "https://y/1"}, {"url": "https://y/2"}]
    napp._drain_channels()
    assert napp.channels_btn.cget("text") == "Kanallar (2)"
    napp._update_update_widgets()
    assert napp.updates_btn.cget("text").startswith("Güncellemeler")


@pytest.mark.gui
def test_the_settings_are_tabs_with_tick_boxes(napp):
    import customtkinter
    napp._open_settings("Zamanlayıcı")
    panel = napp.settings_panel
    assert panel.current_tab() == "Zamanlayıcı"
    assert [panel.body.tab(t, "text") for t in panel.body.tabs()] == \
        ["İndirme", "Bildirimler", "Zamanlayıcı", "Sistem", "Yedek ve yardım", "Bitince"]
    assert isinstance(panel.schedule_switch, customtkinter.CTkCheckBox)
    panel.schedule_switch.select()
    panel.schedule_switch.toggle()
    assert napp.cfg.get("schedule_on") is False                                   # a tick box like the switch
    assert panel.theme_menu.cget("state") == "disabled"
    napp._open_settings("Sistem")                                                 # the open window changes tab
    assert panel.current_tab() == "Sistem"


@pytest.mark.gui
def test_the_music_player_has_a_menu_bar_and_plain_tables(old, monkeypatch):
    from tkinter import ttk

    from music_support import FakeBackend, FakeReader

    from app import player, tags
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app = old()
    app._ensure_music()
    labels = [app.music.menubar.entrycget(i, "label") for i in range(app.music.menubar.index("end") + 1)]
    assert labels == ["Dosya", "Liste", "Çalma", "Araçlar", "Yardım"]
    assert ttk.Style(app.music).theme_use() in ("vista", "clam")
    assert isinstance(app.music.tree.master.grid_slaves(row=0, column=1)[0], ttk.Scrollbar)


@pytest.mark.gui
def test_a_restart_brings_the_windows_back_where_they_were(old, monkeypatch):
    from music_support import FakeBackend, FakeReader

    from app import player, tags
    from app.config import Config
    from app.music_ui import MODE_MUSIC
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app = old()
    app.geometry("930x640+40+50")
    app._open_settings("Bitince")
    app._ensure_music()
    app._switch_mode(MODE_MUSIC)
    app.update()
    app._remember_view()
    view = Config().get("restart_view")
    assert view["mode"] == MODE_MUSIC and view["settings"] == "Bitince" and view["geometry"].startswith("930x640")
    assert view["playing"] is False


@pytest.mark.gui
def test_the_new_start_puts_them_back(old, monkeypatch):
    from music_support import FakeBackend, FakeReader

    from app import player, tags
    from app.config import Config
    from app.music_ui import MODE_MUSIC
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    Config().set("restart_view", {"mode": MODE_MUSIC, "settings": "Sistem", "geometry": "910x600+30+40",
                                  "music_geometry": "800x620+60+70"})
    app = old()
    app._restore_view()
    app.update()
    assert app.mode == MODE_MUSIC and app.music is not None and app.music.geometry().startswith("800x620")
    assert app.settings_panel.current_tab() == "Sistem"
    assert app._geometry_of(app) == "910x600+30+40"
    assert Config().get("restart_view") == {}                                   # used once


# ------------------------------------------------------------------------------ in English
SCRIPT = r'''
import json, os, sys, tkinter as tk
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from app import config, i18n, look
config.DEFAULTS["bridge_port"] = 0
i18n.set_language("English")
look.apply("Nostalji")
from app import player, tags
sys.path.insert(0, os.path.join(ROOT, "tests"))
from music_support import FakeBackend, FakeReader, FakeKeys, FakeSearcher, FakeOverlay, FakeThumbBar
from app import mediakeys, music_search, smtc, taskbar, updater
player.new_backend = FakeBackend; tags.TagReader = FakeReader; mediakeys.MediaKeys = FakeKeys
music_search.Searcher = FakeSearcher; smtc.MediaOverlay = FakeOverlay; taskbar.ThumbBar = FakeThumbBar
updater.Updater.start = lambda self: None
from app.models import Item, DONE, DOWNLOADING, ERROR, PAUSED, QUEUED
from app.ui import App
from app.classic_ui import ToolButton
app = App(); app.withdraw(); app.update()
for state in (DONE, DOWNLOADING, ERROR, PAUSED, QUEUED):
    it = Item("https://x.com/" + state + ".zip", kind="file", title=state + ".zip"); it.state = state
    it.fraction = 0.5 if state != DONE else 1.0; it.total = 100
    app.manager.items.append(it)
app._sync_rows()
app._open_settings(); app._ensure_music(); app.open_progress(app.manager.items[1]); app.open_address_dialog()
app.update()
texts = []
def menu_texts(menu):
    for i in range((menu.index("end") or -1) + 1):
        if menu.type(i) in ("command", "cascade", "radiobutton"):
            texts.append(menu.entrycget(i, "label"))
        if menu.type(i) == "cascade":
            menu_texts(menu.nametowidget(menu.entrycget(i, "menu")))
def walk(w):
    for c in w.winfo_children():
        if isinstance(c, tk.Menu):
            continue
        if isinstance(c, ToolButton):          # its own text is the Turkish name; the label under it is shown
            walk(c)
            continue
        try:
            t = c.cget("text")
            if isinstance(t, str) and t.strip(): texts.append(t)
        except Exception:
            pass
        try:
            ph = c.cget("placeholder_text")
            if isinstance(ph, str) and ph.strip(): texts.append(ph)
        except Exception:
            pass
        if c.winfo_class() == "Treeview":
            for col in ("#0",) + tuple(c["columns"]):
                texts.append(c.heading(col)["text"])
            def rows(parent=""):
                for iid in c.get_children(parent):
                    texts.append(c.item(iid, "text").strip()); texts.extend(str(v) for v in c.item(iid, "values")); rows(iid)
            rows()
        if c.winfo_class() == "TNotebook":
            texts.extend(c.tab(t, "text") for t in c.tabs())
        walk(c)
walk(app)
menu_texts(app.menubar); menu_texts(app.music.menubar)
json.dump({"texts": texts}, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
app._on_close()
'''


@pytest.mark.gui
def test_the_old_look_in_english(tmp_path, isolated_home):
    script = tmp_path / "en.py"
    script.write_text(SCRIPT.replace("ROOT", repr(ROOT)), encoding="utf-8")
    out = tmp_path / "out.json"
    done = subprocess.run([sys.executable, str(script), str(out)], capture_output=True, text=True, timeout=120,
                          env=dict(os.environ, HIZLI_NO_UPDATE="1"))
    if done.returncode != 0 and "no display" in done.stderr.lower():
        pytest.skip("no display")
    assert done.returncode == 0, done.stderr[-3000:]
    texts = json.load(open(out, encoding="utf-8"))["texts"]
    for english in ("Tasks", "Downloads", "View", "Tools", "Help", "New download", "Stop all", "Delete completed",
                    "Scheduler", "All downloads", "Unfinished", "File name", "Time left", "Complete", "Error",
                    "Download status", "Address:", "Categories", "Nostalgia", "Add files…", "Shuffle"):
        assert english in texts, english
    turkish = [t for t in texts if any(c in t for c in "çğıöşüÇĞİÖŞÜ")]
    assert turkish == [], turkish
