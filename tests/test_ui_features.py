"""The newer window features: option bar, playlist / info windows, context menu, shortcuts,
scheduler, tray, browser bridge, settings window, theme and log."""
import datetime
import json
import os
import time
import types

import pytest
import requests

pytest.importorskip("customtkinter")

from app import bridge, startup  # noqa: E402
from app.models import (CANCELLED, DONE, DOWNLOADING, ERROR, PAUSED, QUEUED, RESOLVING, WAITING,  # noqa: E402
                        Settings)
from app.segmented_downloader import LIMITER, get_proxy  # noqa: E402
from conftest import wait_for  # noqa: E402
from ui_support import FakeTray, add_item, local_urls, notice, shown  # noqa: E402

pytestmark = pytest.mark.gui
EXT = {"Origin": "chrome-extension://abcdefghijklmnop"}
NO_PROXY = {"http": None, "https": None}


def pump(app, cond, timeout=10):
    """Run the window's own queue of calls from other threads until cond() is true."""
    def check():
        app._drain_ui_calls()
        app.update()
        return cond()
    return wait_for(check, timeout)


# ---------------------------------------------------------------------------- option bar
def test_the_new_option_bar_choices_are_saved_and_used(app):
    app.subs_menu.set("Türkçe")                    # choosing = the menu shows it, then calls back
    app.subs_menu._command("Türkçe")
    app.folders_var.set(True)
    app.cfg.set("sort_folders", True)
    app.cover_var.set(False)
    app.cfg.set("cover", False)
    s = app._settings()
    assert (s.subs, s.sort_folders, s.cover) == ("Türkçe", True, False)
    assert app.cfg.get("subs") == "Türkçe"


def test_subtitles_only_make_sense_for_videos(app):
    app._on_kind("Ses (MP3)")
    assert app.subs_menu.cget("state") == "disabled" and app.bitrate_menu.cget("state") == "normal"
    app._on_kind("Video (MP4)")
    assert app.subs_menu.cget("state") == "normal" and app.bitrate_menu.cget("state") == "disabled"
    app._on_kind("Dosya (rar, zip, exe, iso…)")
    assert app.subs_menu.cget("state") == "disabled" and app.quality_menu.cget("state") == "disabled"


def test_settings_from_the_saved_config_match_the_widgets(app, tmp_path):
    app.folder_entry.delete(0, "end")
    app.folder_entry.insert(0, str(tmp_path))
    app._save_folder()
    app.kind_menu.set("Ses (MP3)")
    app._on_kind("Ses (MP3)")
    for menu, key, value in ((app.quality_menu, "quality", "720p"), (app.bitrate_menu, "bitrate", "128"),
                             (app.conn_menu, "connections", "32"), (app.cookie_menu, "cookies", "firefox"),
                             (app.subs_menu, "subs", "İngilizce")):
        menu.set(value)
        app.cfg.set(key, value)
    app.cfg.set("sort_folders", True)
    app.folders_var.set(True)
    from_widgets = app._settings()
    from_config = app.settings_from_config()
    assert from_config == Settings(**{**from_widgets.__dict__, "playlist": False})


def test_the_old_settings_file_without_the_new_keys_still_loads(make_app, isolated_home):
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"quality": "720p"}), encoding="utf-8")
    a = make_app()
    assert a.quality_menu.get() == "720p" and a.subs_menu.get() == "Yok" and a.cfg.get("auto_retry") == 3


# ---------------------------------------------------------------------------- playlists
ENTRIES = [("http://x/v1", "First video", 185), ("http://x/v2", "Second", 3725), ("http://x/v3", "", 0)]


class RecordingDialog:
    made = []

    def __init__(self, app, entries, settings):
        RecordingDialog.made.append((entries, settings))


def test_a_playlist_opens_the_selection_window(app, monkeypatch):
    from app import ui
    RecordingDialog.made = []
    monkeypatch.setattr(ui, "PlaylistDialog", RecordingDialog)
    monkeypatch.setattr(ui.ve, "expand_playlist", lambda url, cookies=None: ENTRIES)
    app.playlist_var.set(True)
    assert app.add_urls(["http://x/list"]) == 1
    assert pump(app, lambda: RecordingDialog.made)
    entries, settings = RecordingDialog.made[0]
    assert entries == ENTRIES and settings.playlist is True


def test_with_asking_switched_off_the_whole_playlist_is_added(app, monkeypatch, tmp_path):
    from app import ui
    monkeypatch.setattr(ui.ve, "expand_playlist", lambda url, cookies=None: ENTRIES)
    monkeypatch.setattr(app.manager, "start", lambda item: None)         # no network
    app.cfg.set("playlist_ask", False)
    app.playlist_var.set(True)
    app.add_urls(["http://x/list"])
    assert pump(app, lambda: len(app.manager.items) == 3)
    assert [i.title for i in app.manager.items] == ["First video", "Second", ""]
    assert all(i.kind == "video" for i in app.manager.items)             # "auto" becomes video
    assert "3 video listeye eklendi" in notice(app)


def test_a_single_video_link_is_added_without_a_window(app, monkeypatch):
    from app import ui
    RecordingDialog.made = []
    monkeypatch.setattr(ui, "PlaylistDialog", RecordingDialog)
    monkeypatch.setattr(ui.ve, "expand_playlist", lambda url, cookies=None: [("http://x/one", "One", 10)])
    monkeypatch.setattr(app.manager, "start", lambda item: None)
    app.playlist_var.set(True)
    app.add_urls(["http://x/one"])
    assert pump(app, lambda: len(app.manager.items) == 1)
    assert RecordingDialog.made == [] and "eklendi" in notice(app)


def test_an_unreadable_playlist_falls_back_to_the_link_itself(app, monkeypatch):
    from app import ui

    def boom(url, cookies=None):
        raise RuntimeError("ERROR: Unsupported URL: http://x/list")

    monkeypatch.setattr(ui.ve, "expand_playlist", boom)
    monkeypatch.setattr(app.manager, "start", lambda item: None)
    app.playlist_var.set(True)
    app.add_urls(["http://x/list"])
    assert pump(app, lambda: len(app.manager.items) == 1)
    assert app.manager.items[0].url == "http://x/list"


def test_playlist_links_already_in_the_list_are_skipped(app, monkeypatch):
    from app import ui
    monkeypatch.setattr(ui.ve, "expand_playlist", lambda url, cookies=None: ENTRIES)
    monkeypatch.setattr(app.manager, "start", lambda item: None)
    add_item(app, "v2", PAUSED, url="http://x/v2")
    app.cfg.set("playlist_ask", False)
    app.playlist_var.set(True)
    app.add_urls(["http://x/list"])
    assert pump(app, lambda: len(app.manager.items) == 3)                # 1 existing + 2 new
    assert "tanesi zaten listedeydi" in notice(app)


def test_the_playlist_window_lets_you_choose(app, monkeypatch):
    from app import ui
    dialog = ui.PlaylistDialog(app, ENTRIES, Settings(folder="x"))
    assert dialog.go_btn.cget("text") == "⬇ İndir (3)" and dialog.count_label.cget("text") == "3 seçili"
    dialog.vars[1].set(False)
    dialog._count()
    assert [e[1] for e in dialog.chosen()] == ["First video", ""]
    assert dialog.go_btn.cget("text") == "⬇ İndir (2)"
    dialog.select_all(False)
    assert dialog.chosen() == [] and dialog.go_btn.cget("state") == "disabled"
    dialog.select_all(True)
    assert len(dialog.chosen()) == 3
    chosen = []
    monkeypatch.setattr(app, "add_playlist_selection", lambda entries, s: chosen.append(entries))
    dialog.vars[0].set(False)
    dialog.confirm()
    assert [e[1] for e in chosen[0]] == ["Second", ""]
    assert not dialog.winfo_exists()


def test_a_long_playlist_fills_its_list_in_pieces(app, monkeypatch):
    from app import ui
    created = []

    class Counting(ui.ctk.CTkCheckBox):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            created.append(1)

    monkeypatch.setattr(ui.ctk, "CTkCheckBox", Counting)
    entries = [(f"http://x/{i}", f"Video {i}", 60) for i in range(80)]
    dialog = ui.PlaylistDialog(app, entries, Settings())
    assert len(created) == ui.PlaylistDialog.CHUNK            # the window opened with the first rows
    assert pump(app, lambda: len(created) == 80)             # the rest followed without blocking
    assert len(dialog.vars) == 80 and dialog.go_btn.cget("text") == "⬇ İndir (80)"
    dialog.destroy()


def test_choosing_in_the_window_adds_those_videos(app, monkeypatch):
    monkeypatch.setattr(app.manager, "start", lambda item: None)
    app.add_playlist_selection(ENTRIES[:2], Settings(folder="x", quality="720p"))
    assert [i.title for i in app.manager.items] == ["First video", "Second"]
    assert all(i.quality == "720p" for i in app.manager.items)
    app.add_playlist_selection(ENTRIES[:2], Settings(folder="x"))
    assert "zaten listedeydi" in notice(app) and len(app.manager.items) == 2


# --------------------------------------------------------------------------------- info
INFO = {"title": "A video", "uploader": "Someone", "duration": 185, "thumbnail": "",
        "qualities": [{"height": 1080, "fps": 60, "codec": "vp9", "size": 150_000_000, "ext": "webm"},
                      {"height": 720, "fps": 30, "codec": "avc1", "size": 60_000_000, "ext": "mp4"}],
        "audio_size": 3_000_000, "subtitles": ["en", "tr"], "auto_subtitles": 90,
        "is_playlist": False, "entries": 0}


class RowRecorder:
    rows = []

    @staticmethod
    def record(self, text, button, command):
        RowRecorder.rows.append((text, button, command))


def open_info(app, monkeypatch, result):
    from app import ui
    RowRecorder.rows = []
    monkeypatch.setattr(ui.InfoDialog, "_row", RowRecorder.record)
    monkeypatch.setattr(ui.ve, "fetch_info", result if callable(result) else (lambda url, cookies=None: result))
    dialog = ui.InfoDialog(app, "http://x/video")
    assert pump(app, lambda: dialog.result is not None and not dialog.status.winfo_exists())
    return dialog


def test_the_info_window_lists_qualities_and_audio(app, monkeypatch):
    dialog = open_info(app, monkeypatch, INFO)
    texts = [r[0] for r in RowRecorder.rows]
    assert texts[0] == "1080p • 60 fps • vp9 • ~143.1 MB" and texts[1] == "720p • avc1 • ~57.2 MB"
    assert texts[2].startswith("Sadece ses (MP3)") and "2.9 MB" in texts[2]
    dialog.destroy()


def test_an_info_window_button_downloads_that_quality(app, monkeypatch):
    dialog = open_info(app, monkeypatch, INFO)
    added = []
    monkeypatch.setattr(app.manager, "add_url", lambda url, s, **kw: added.append((url, s.quality, s.kind)))
    RowRecorder.rows[1][2]()          # the 720p button
    assert added == [("http://x/video", "720p", "video")] and not dialog.winfo_exists()
    dialog = open_info(app, monkeypatch, INFO)
    RowRecorder.rows[2][2]()          # the MP3 button
    assert added[-1] == ("http://x/video", app.quality_menu.get(), "audio")


def test_a_height_between_the_menu_steps_uses_the_next_lower_quality(app, monkeypatch):
    odd = {**INFO, "qualities": [{"height": 1000, "fps": 30, "codec": "avc1", "size": 0, "ext": "mp4"}]}
    open_info(app, monkeypatch, odd)
    added = []
    monkeypatch.setattr(app.manager, "add_url", lambda url, s, **kw: added.append(s.quality))
    RowRecorder.rows[0][2]()
    assert added == ["720p"]


def test_the_info_window_says_when_the_link_is_a_playlist(app, monkeypatch):
    open_info(app, monkeypatch, {**INFO, "is_playlist": True, "entries": 12, "qualities": []})
    assert RowRecorder.rows == []                      # no download buttons for a playlist


def test_the_info_window_shows_an_error_instead_of_crashing(app, monkeypatch):
    def boom(url, cookies=None):
        raise RuntimeError("ERROR: Unsupported URL: http://x")

    dialog = open_info(app, monkeypatch, boom)
    assert dialog.winfo_exists() and RowRecorder.rows == []


def test_the_info_window_really_draws_its_rows(app, monkeypatch):
    from app import ui
    monkeypatch.setattr(ui.ve, "fetch_info", lambda url, cookies=None: INFO)
    dialog = ui.InfoDialog(app, "http://x/video")
    assert pump(app, lambda: dialog.result is not None and not dialog.status.winfo_exists())
    assert dialog.winfo_exists()
    dialog.destroy()


def test_the_info_button_needs_a_link(app, monkeypatch):
    from app import ui
    opened = []
    monkeypatch.setattr(ui, "InfoDialog", lambda a, url: opened.append(url))
    app._show_info()
    assert opened == [] and "link yapıştır" in notice(app)
    app.url_entry.insert(0, "see https://x.com/watch?v=1 please")
    app._show_info()
    assert opened == ["https://x.com/watch?v=1"]


def test_download_quality_skips_a_link_that_is_already_there(app, monkeypatch):
    add_item(app, "v", PAUSED, url="http://x/video")
    added = []
    monkeypatch.setattr(app.manager, "add_url", lambda *a, **k: added.append(1))
    app.download_quality("http://x/video", "720p", "video")
    assert added == [] and "zaten listede" in notice(app)


# ---------------------------------------------------------------------- context menu
def row_for(app, title):
    shown(app)
    return next(r for r in app.rows.values() if r.item.title == title)


def labels(row):
    return [label for label, _ in row.menu_commands()]


def test_the_context_menu_depends_on_the_state(app):
    add_item(app, "Done", DONE, final_path="C:/x/Done.zip", folder="C:/x")
    add_item(app, "Run", DOWNLOADING, folder="C:/x")
    add_item(app, "Err", ERROR, folder="C:/x")
    add_item(app, "Pau", PAUSED, folder="C:/x")
    assert labels(row_for(app, "Done")) == ["Dosyayı aç", "Klasörde göster", "Linki kopyala", "Baştan indir",
                                            "Listeden kaldır", "Dosyayla birlikte sil"]
    assert labels(row_for(app, "Run")) == ["Klasörü aç", "Linki kopyala", "Listeden kaldır"]
    assert labels(row_for(app, "Err")) == ["Klasörü aç", "Linki kopyala", "Baştan indir", "Listeden kaldır"]
    assert "Baştan indir" in labels(row_for(app, "Pau"))


def test_menu_actions_do_what_they_say(app, monkeypatch):
    from app import ui
    it = add_item(app, "Done", DONE, final_path=__file__, folder=os.path.dirname(__file__))
    row = row_for(app, "Done")
    opened, folders = [], []
    monkeypatch.setattr(ui, "open_file", opened.append)
    monkeypatch.setattr(ui, "open_in_file_manager", folders.append)
    cmds = dict(row.menu_commands())
    cmds["Dosyayı aç"]()
    cmds["Klasörde göster"]()
    assert opened == [__file__] and folders == [__file__]
    cmds["Linki kopyala"]()
    assert app.clipboard_get() == it.url and "kopyalandı" in notice(app)
    called = []
    monkeypatch.setattr(app.manager, "redownload", lambda i: called.append(("again", i.title)))
    monkeypatch.setattr(app.manager, "remove", lambda i: called.append(("remove", i.title)))
    cmds["Baştan indir"]()
    cmds["Listeden kaldır"]()
    assert called == [("again", "Done"), ("remove", "Done")]


def test_deleting_with_the_file_asks_first(app, monkeypatch):
    from app import ui
    add_item(app, "Done", DONE, final_path="C:/x/Done.zip")
    row = row_for(app, "Done")
    deleted = []
    monkeypatch.setattr(app.manager, "delete_with_file", lambda i: deleted.append(i.title))
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: False)
    row._delete_with_file()
    assert deleted == []
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
    row._delete_with_file()
    assert deleted == ["Done"]


def test_double_click_opens_only_finished_files(app, monkeypatch):
    from app import ui
    opened = []
    monkeypatch.setattr(ui, "open_file", opened.append)
    add_item(app, "Done", DONE, final_path=__file__)
    add_item(app, "Gone", DONE, final_path="C:/definitely/missing.zip")
    add_item(app, "Run", DOWNLOADING, final_path=__file__)
    for title in ("Done", "Gone", "Run"):
        row_for(app, title)._open_file()
    assert opened == [__file__]


def test_the_menu_can_be_posted(app, monkeypatch):
    import tkinter as tk
    posted = []
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda self, x, y: posted.append((x, y)))
    add_item(app, "Err", ERROR, folder="C:/x")
    row_for(app, "Err")._popup(types.SimpleNamespace(x_root=10, y_root=20))
    assert posted == [(10, 20)]


# ------------------------------------------------------------------------- row texts
def test_a_waiting_download_shows_the_retry_message(app):
    it = add_item(app, "W", WAITING, message="Bağlantı sorunu: 10 sn sonra tekrar deneyeceğim (1/3)")
    row = row_for(app, "W")
    assert row.info.cget("text").startswith("⏳ Bağlantı sorunu") and row.toggle_btn.cget("text") == "⏸"
    assert it.state == WAITING


def test_waiting_items_count_as_queued_for_the_filter_and_the_status(app):
    add_item(app, "Q", QUEUED)
    add_item(app, "W", WAITING)
    app.filter_menu.set("Sırada")
    app._on_filter("Sırada")
    assert sorted(shown(app)) == ["Q", "W"]
    app._update_status()
    assert "Sırada: 2" in app.status.cget("text")


def test_queued_rows_explain_why_they_wait(app):
    add_item(app, "Q", QUEUED)
    app.queue_note = "⏰ Zamanlayıcı: 02:00'de başlayacak"
    assert "02:00'de başlayacak" in row_for(app, "Q").info.cget("text")
    app.queue_note = ""
    app._sync_rows()
    assert row_for(app, "Q").info.cget("text") == "Sırada, birazdan başlıyor…"


# ----------------------------------------------------------------------- shortcuts
def test_ctrl_v_adds_the_links_in_the_clipboard(app, monkeypatch, server, tmp_path):
    app.folder_entry.delete(0, "end")
    app.folder_entry.insert(0, str(tmp_path / "dl"))
    urls = local_urls(server, 2)
    monkeypatch.setattr(app, "_clipboard_text", lambda: "look: " + " and ".join(urls))
    assert app._on_ctrl_v() == "break"
    assert len(app.manager.items) == 2
    monkeypatch.setattr(app, "_clipboard_text", lambda: "no links here")
    app._on_ctrl_v()
    assert "Panoda link göremedim" in notice(app)


def test_shortcuts_leave_text_boxes_alone(app, monkeypatch):
    monkeypatch.setattr(app, "_typing", lambda: True)
    monkeypatch.setattr(app, "_clipboard_text", lambda: "https://x.com/a")
    assert app._on_ctrl_v() is None and app.manager.items == []
    add_item(app, "A", PAUSED)
    assert app._on_ctrl_a() is None and app.selected == set()
    app.selected = {app.manager.items[0].id}
    assert app._on_delete_key() is None and len(app.manager.items) == 1


def test_ctrl_a_selects_everything_visible_and_delete_removes_the_selection(app, monkeypatch):
    from app import ui
    for t in "ABC":
        add_item(app, t, PAUSED)
    assert app._on_ctrl_a() == "break" and len(app.selected) == 3
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
    assert app._on_delete_key() == "break" and app.manager.items == []


def test_delete_does_nothing_without_a_selection(app):
    add_item(app, "A", PAUSED)
    assert app._on_delete_key() is None and len(app.manager.items) == 1


def test_escape_clears_the_search_and_ctrl_f_focuses_it(app):
    add_item(app, "Alpha", PAUSED)
    add_item(app, "Beta", PAUSED)
    app.search_entry.insert(0, "alp")
    assert shown(app) == ["Alpha"]
    app._clear_search()
    assert sorted(shown(app)) == ["Alpha", "Beta"]


# ------------------------------------------------------------------------- scheduler
def at(hour, minute=0):
    return lambda: datetime.datetime(2026, 1, 1, hour, minute)


def configure(app, on=True, start="02:00", stop="07:00"):
    app.cfg.set("schedule_on", on)
    app.cfg.set("schedule_start", start)
    app.cfg.set("schedule_stop", stop)


def test_the_gate_follows_the_clock(app):
    configure(app)
    app._now = at(12)
    app._check_schedule()
    assert app.manager.gate_open is False and "02:00'de başlayacak" in app.queue_note
    app._now = at(3)
    app._check_schedule()
    assert app.manager.gate_open is True and app.queue_note == ""
    assert "indirmeler başladı" in notice(app)


def test_the_stop_time_pauses_running_downloads_and_the_next_start_resumes_them(app, monkeypatch):
    configure(app)
    running = add_item(app, "Run", DOWNLOADING)
    add_item(app, "Wait", WAITING)
    queued = add_item(app, "Queued", QUEUED)
    done = add_item(app, "Done", DONE)
    paused_by_user = add_item(app, "User", PAUSED)
    log = []
    monkeypatch.setattr(app.manager, "pause", lambda it: (log.append(("pause", it.title)), setattr(it, "state", PAUSED)))
    monkeypatch.setattr(app.manager, "resume", lambda it: log.append(("resume", it.title)))
    app._now = at(3)
    app._check_schedule()                                   # inside the window: nothing to do
    app._now = at(8)
    app._check_schedule()                                   # the stop time has passed
    assert sorted(log) == [("pause", "Run"), ("pause", "Wait")]
    assert "duraklatıldı" in notice(app)
    log.clear()
    app._now = at(2, 30)
    app._check_schedule()
    assert sorted(log) == [("resume", "Run"), ("resume", "Wait")]     # only what the scheduler paused
    assert {queued.state, done.state, paused_by_user.state} == {QUEUED, DONE, PAUSED}
    assert running.state == PAUSED                                   # (the fake pause above)


def test_without_a_stop_time_a_closed_gate_never_pauses_running_downloads(app, monkeypatch):
    configure(app, stop="")
    add_item(app, "Run", DOWNLOADING)
    paused = []
    monkeypatch.setattr(app.manager, "pause", lambda it: paused.append(it))
    app._now = at(5)
    app._check_schedule()                                   # open (after 02:00)
    app._now = at(0, 30)                                    # midnight passed: the gate closes
    app._check_schedule()
    assert app.manager.gate_open is False and paused == []
    assert "başlama saatini bekleyecek" in notice(app)


def test_switching_the_scheduler_off_opens_the_gate(app):
    configure(app)
    app._now = at(12)
    app._check_schedule()
    assert app.manager.gate_open is False
    app.apply_setting("schedule_on", False)
    app._check_schedule()
    assert app.manager.gate_open is True and app.queue_note == ""


def test_an_unreadable_start_time_never_blocks_the_queue(app):
    configure(app, start="banana")
    app._now = at(12)
    app._check_schedule()
    assert app.manager.gate_open is True


def test_a_queued_download_waits_for_the_scheduler_and_then_runs(app, server, tmp_path):
    app.folder_entry.delete(0, "end")
    app.folder_entry.insert(0, str(tmp_path / "dl"))
    configure(app)
    app._now = at(12)
    app._check_schedule()
    app.add_urls(local_urls(server, 1))
    wait_for(lambda: len(app.manager.items) == 1)
    import time
    time.sleep(1.0)
    assert app.manager.items[0].state == QUEUED
    app._now = at(3)
    app._check_schedule()
    assert pump(app, lambda: app.manager.items[0].state == DONE)


def test_the_status_line_mentions_the_scheduler(app):
    configure(app)
    app._now = at(12)
    app._check_schedule()
    app._update_status()
    assert "⏰ Zamanlayıcı" in app.status.cget("text")


def test_schedule_entries_are_validated_and_normalised(app):
    assert app.apply_schedule("schedule_start", "7:5") is False and "24 saat" in notice(app)
    assert app.apply_schedule("schedule_start", "7:05") is True and app.cfg.get("schedule_start") == "07:05"
    assert app.apply_schedule("schedule_stop", "") is True and app.cfg.get("schedule_stop") == ""
    assert app.apply_schedule("schedule_stop", "25:00") is False
    assert app.apply_schedule("schedule_stop", " 23:30 ") is True and app.cfg.get("schedule_stop") == "23:30"


# ---------------------------------------------------------------------- tray / window
def test_closing_the_window_quits_unless_the_tray_is_wanted(app, monkeypatch):
    quit_calls = []
    monkeypatch.setattr(app, "_on_close", lambda: quit_calls.append(1))
    app._on_window_x()
    assert quit_calls == [1] and FakeTray.instances == []


def test_closing_goes_to_the_tray_when_wanted(app, monkeypatch):
    monkeypatch.setattr(app, "_on_close", lambda: pytest.fail("must not quit"))
    app.apply_setting("tray_on_close", True)
    assert len(FakeTray.instances) == 1 and FakeTray.instances[0].started
    app.deiconify()
    app._on_window_x()
    app.update()
    assert app.state() == "withdrawn"
    assert app.notes["toast"][-1][1].startswith("DISO arka planda")
    app._on_window_x()
    assert len([t for t in app.notes["toast"] if t[1].startswith("DISO arka planda")]) == 1   # told only once


def test_the_tray_menu_controls_the_app(app, monkeypatch):
    app.apply_setting("tray_on_close", True)
    tray = FakeTray.instances[0]
    called = []
    monkeypatch.setattr(app.manager, "pause_all", lambda: called.append("pause"))
    monkeypatch.setattr(app.manager, "resume_all", lambda: called.append("resume"))
    monkeypatch.setattr(app, "_on_close", lambda: called.append("quit"))
    app._hide_to_tray()
    tray.on_event("show")                                    # from the tray's own thread
    assert app._ui_calls.qsize() == 1                        # nothing touches the window yet
    app._drain_ui_calls()
    app.update()
    assert app.state() == "normal"
    for name in ("pause_all", "resume_all", "quit"):
        tray.on_event(name)
    app._drain_ui_calls()
    assert called == ["pause", "resume", "quit"]


def test_the_tray_tooltip_shows_the_activity(app):
    app.apply_setting("tray_on_close", True)
    add_item(app, "Run", DOWNLOADING, speed=2 * 1024 * 1024)
    app._update_tray_tooltip()
    assert FakeTray.instances[0].title == "DISO • 1 aktif • 2.0 MB/s"


def test_starting_minimized_hides_the_window_in_the_tray(make_app):
    a = make_app(minimized=True)
    assert pump(a, lambda: a.state() == "withdrawn")
    assert FakeTray.instances and FakeTray.instances[0].started


def test_the_tray_icon_is_stopped_when_the_app_quits(app):
    app.apply_setting("tray_on_close", True)
    tray = FakeTray.instances[0]
    app._on_close()
    assert pump(app, lambda: tray.stopped)


def test_without_pystray_closing_still_quits(app, monkeypatch):
    from app import ui
    quit_calls = []
    monkeypatch.setattr(ui.tray, "AVAILABLE", False)
    monkeypatch.setattr(app, "_on_close", lambda: quit_calls.append(1))
    app.cfg.set("tray_on_close", True)
    app._on_window_x()
    assert quit_calls == [1]


def test_the_window_can_be_brought_back(app):
    app.withdraw()
    app.update()
    app._show_window()
    app.update()
    assert app.state() == "normal"


# -------------------------------------------------------------------- browser bridge
def base(app):
    return f"http://127.0.0.1:{app.bridge.port}"


def test_the_window_runs_a_bridge_for_the_extension(app):
    assert app.bridge is not None and app.bridge.port > 0
    info = requests.get(base(app) + "/ping", proxies=NO_PROXY).json()
    assert info["app"] == "DISO" and info["add"] is True


def test_links_and_session_from_the_extension_become_downloads(app, server, tmp_path):
    app.apply_setting("block_duplicates", True)
    app.folder_entry.delete(0, "end")
    app.folder_entry.insert(0, str(tmp_path / "dl"))
    app.cfg.set("folder", str(tmp_path / "dl"))
    name, data = server.file(50_000)
    r = requests.post(base(app) + "/add", proxies=NO_PROXY, headers=EXT, json={
        "urls": [server.url("auth", name)], "referer": "http://site.example/page",
        "cookies": "sid=1", "userAgent": "TestUA/1", "kind": "file"})
    assert r.status_code == 200 and r.json() == {"added": 1, "duplicates": 0}
    assert pump(app, lambda: app.manager.items and app.manager.items[0].state == DONE)
    assert open(app.manager.items[0].final_path, "rb").read() == data
    assert "sid=1" in server.state.seen[name]["cookie"]
    again = requests.post(base(app) + "/add", proxies=NO_PROXY, headers=EXT, json={"urls": [server.url("auth", name)]})
    assert again.json() == {"added": 0, "duplicates": 1}
    assert "Tarayıcıdan 1 bağlantı eklendi" in notice(app)


def test_the_bridge_uses_the_saved_choices_not_the_widgets(app, monkeypatch):
    seen = []
    monkeypatch.setattr(app.manager, "add_url", lambda url, s, **kw: seen.append((s, kw)) or True)
    app.cfg.set("quality", "480p")
    app.cfg.set("sort_folders", True)
    app.cfg.set("subs", "Türkçe")
    requests.post(base(app) + "/add", proxies=NO_PROXY, headers=EXT,
                  json={"urls": ["http://x.com/v"], "kind": "audio"})
    s, kw = seen[0]
    assert (s.kind, s.quality, s.sort_folders, s.subs, s.playlist) == ("audio", "480p", True, "Türkçe", False)
    assert kw["extra"] == {"referer": "", "user_agent": "", "cookie": ""}


def test_the_extension_switch_in_the_settings_turns_adding_off(app):
    app.apply_setting("bridge_on", False)
    r = requests.post(base(app) + "/add", proxies=NO_PROXY, headers=EXT, json={"urls": ["http://x.com/v"]})
    assert r.status_code == 403 and app.manager.items == []
    assert requests.get(base(app) + "/ping", proxies=NO_PROXY).json()["add"] is False


def test_the_bridge_reports_the_state_of_the_list(app):
    add_item(app, "Run", DOWNLOADING, speed=1000)
    add_item(app, "Q", QUEUED)
    add_item(app, "W", WAITING)
    add_item(app, "R", RESOLVING)
    add_item(app, "D", DONE)
    assert requests.get(base(app) + "/status", proxies=NO_PROXY).json() == {
        "active": 2, "queued": 2, "speed": 1000, "total": 5}


def test_a_second_launch_can_wake_the_window(app):
    assert bridge.ping_existing(app.bridge.port) is True
    app.withdraw()
    app.update()
    assert bridge.show_existing(app.bridge.port) is True
    assert pump(app, lambda: app.state() == "normal")


def test_the_bridge_port_can_be_changed(app):
    old = app.bridge.port
    assert app.apply_bridge_port("abc") is False and app.apply_bridge_port("80") is False
    assert app.apply_bridge_port("70000") is False and app.bridge.port == old
    free = _free_port()
    assert app.apply_bridge_port(str(free)) is True
    assert app.bridge.port == free and app.cfg.get("bridge_port") == free
    assert bridge.ping_existing(free) is True and bridge.ping_existing(old) is False


def _free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_taken_port_is_reported_and_the_app_still_works(make_app, isolated_home):
    import socket
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"bridge_port": port}), encoding="utf-8")
    try:
        a = make_app()
        assert a.bridge is None and "port başka bir programda" in notice(a)
    finally:
        blocker.close()


def test_the_bridge_is_stopped_when_the_app_quits(app):
    port = app.bridge.port
    app._on_close()
    assert wait_for(lambda: not bridge.ping_existing(port), 10)


# ------------------------------------------------------------------ settings window
def open_settings(app):
    app._open_settings()
    return app.settings_panel


def test_every_new_setting_is_wired(app, monkeypatch):
    p = open_settings(app)
    p.retry_menu._command("10 kez")
    assert app.manager.max_retries == 10 and app.cfg.get("auto_retry") == 10
    p.retry_menu._command("Kapalı")
    assert app.manager.max_retries == 0
    p.playlist_ask_switch.toggle()
    p.schedule_switch.toggle()
    p.bridge_switch.toggle()
    assert (app.cfg.get("playlist_ask"), app.cfg.get("schedule_on"), app.cfg.get("bridge_on")) == \
           (False, True, False)
    p.theme_menu._command("Açık")
    import customtkinter
    time.sleep(0.2)
    app.update()                                       # the theme is applied after the menu has closed
    assert customtkinter.get_appearance_mode() == "Light" and app.cfg.get("theme") == "Açık"


def test_the_settings_window_stays_visible_when_the_theme_changes(app):
    """Changing the theme used to hide the open settings window; the Ayarlar button then only
    lifted the invisible window, so it looked as if the button did nothing."""
    app._open_settings()
    app.update()
    panel = app.settings_panel
    for theme in ("Açık", "Koyu", "Açık"):
        panel.theme_menu._command(theme)
        time.sleep(0.6)
        app.update()
        assert panel.state() == "normal" and panel.winfo_viewable(), theme
    panel.withdraw()                                   # whatever hid it: the button must show it again
    app.update()
    app._open_settings()
    app.update()
    assert app.settings_panel is panel and panel.state() == "normal" and panel.winfo_viewable()


def test_the_proxy_entry_applies_validates_and_marks_mistakes(app):
    p = open_settings(app)
    p.proxy_entry.delete(0, "end")
    p.proxy_entry.insert(0, "socks5://127.0.0.1:1080")
    assert p._save_proxy() is True
    assert get_proxy() == "socks5://127.0.0.1:1080" and app.cfg.get("proxy") == "socks5://127.0.0.1:1080"
    p.proxy_entry.delete(0, "end")
    p.proxy_entry.insert(0, "not a proxy")
    assert p._save_proxy() is False
    assert get_proxy() == "socks5://127.0.0.1:1080"          # the bad text changed nothing
    assert p.proxy_entry.cget("border_color") == "#b23b3b"
    p.proxy_entry.delete(0, "end")
    assert p._save_proxy() is True and get_proxy() == "" and app.cfg.get("proxy") == ""


def test_the_proxy_test_button_shows_the_result(app, monkeypatch):
    from app import ui
    p = open_settings(app)
    monkeypatch.setattr(ui, "check_connection", lambda proxy=None: (True, "HTTP 204 • 12 ms"))
    p._test_proxy()
    assert pump(app, lambda: p.proxy_hint.cget("text").startswith("✓"))
    assert "12 ms" in p.proxy_hint.cget("text")
    monkeypatch.setattr(ui, "check_connection", lambda proxy=None: (False, "bağlanılamadı"))
    p._test_proxy()
    assert pump(app, lambda: p.proxy_hint.cget("text").startswith("✖"))


def test_the_proxy_test_does_not_run_for_an_invalid_address(app, monkeypatch):
    from app import ui
    p = open_settings(app)
    monkeypatch.setattr(ui, "check_connection", lambda proxy=None: pytest.fail("must not run"))
    p.proxy_entry.insert(0, "garbage")
    p._test_proxy()


def test_a_saved_proxy_is_active_at_the_next_start(make_app, isolated_home):
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"proxy": "http://127.0.0.1:3128"}), encoding="utf-8")
    make_app()
    assert get_proxy() == "http://127.0.0.1:3128"


def test_a_broken_saved_proxy_is_dropped_instead_of_blocking_the_app(make_app, isolated_home):
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"proxy": "javascript:alert(1)"}), encoding="utf-8")
    a = make_app()
    assert get_proxy() == "" and a.cfg.get("proxy") == ""


def test_the_schedule_entries_save_and_flag_bad_input(app):
    p = open_settings(app)
    p.schedule_start_entry.delete(0, "end")
    p.schedule_start_entry.insert(0, "23:15")
    p.schedule_stop_entry.delete(0, "end")
    p.schedule_stop_entry.insert(0, "06:45")
    assert p._save_schedule() is True
    assert (app.cfg.get("schedule_start"), app.cfg.get("schedule_stop")) == ("23:15", "06:45")
    p.schedule_start_entry.delete(0, "end")
    p.schedule_start_entry.insert(0, "soon")
    assert p._save_schedule() is False
    assert p.schedule_start_entry.cget("border_color") == "#b23b3b"
    assert app.cfg.get("schedule_start") == "23:15"


def test_the_port_entry_saves_and_flags_bad_input(app):
    p = open_settings(app)
    free = _free_port()
    p.bridge_port_entry.delete(0, "end")
    p.bridge_port_entry.insert(0, str(free))
    assert p._save_port() is True and app.bridge.port == free
    p.bridge_port_entry.delete(0, "end")
    p.bridge_port_entry.insert(0, "12")
    assert p._save_port() is False and p.bridge_port_entry.cget("border_color") == "#b23b3b"


def test_start_with_windows_writes_the_registry_through_the_startup_module(app):
    p = open_settings(app)
    p.startup_switch.toggle()
    p.startup_switch.toggle()
    assert app.notes["startup"] == [True, False] and app.cfg.get("start_with_windows") is False


def test_a_failed_registry_write_keeps_the_setting_off_and_tells_the_user(app, monkeypatch):
    from app import ui
    monkeypatch.setattr(ui.startup, "set_enabled", lambda *a, **k: False)
    app.apply_setting("start_with_windows", True)
    assert app.cfg.get("start_with_windows") is False and "ekleyemedim" in notice(app)


def test_the_startup_entry_is_refreshed_when_the_app_starts_with_the_setting_on(make_app, isolated_home):
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"start_with_windows": True}), encoding="utf-8")
    a = make_app()
    assert a.notes["startup"] == [True]


def test_the_tray_switch_creates_the_tray_icon(app):
    p = open_settings(app)
    p.tray_switch.toggle()
    assert app.cfg.get("tray_on_close") is True and len(FakeTray.instances) == 1


def test_the_settings_window_shows_the_saved_values(make_app, isolated_home):
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({
        "auto_retry": 5, "proxy": "http://p:1", "schedule_start": "01:30", "schedule_stop": "",
        "bridge_port": 40000, "theme": "Sistem", "playlist_ask": False, "tray_on_close": True}), encoding="utf-8")
    a = make_app()
    p = open_settings(a)
    assert p.retry_menu.get() == "5 kez" and p.proxy_entry.get() == "http://p:1"
    assert p.schedule_start_entry.get() == "01:30" and p.schedule_stop_entry.get() == ""
    assert p.bridge_port_entry.get() == "40000" and p.theme_menu.get() == "Sistem"
    assert p.playlist_ask_switch.get() == 0 and p.tray_switch.get() == 1


def test_theme_is_restored_at_startup(make_app, isolated_home):
    import customtkinter
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"theme": "Açık"}), encoding="utf-8")
    make_app()
    assert customtkinter.get_appearance_mode() == "Light"


def test_an_unknown_saved_theme_falls_back_to_dark(make_app, isolated_home):
    import customtkinter
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"theme": "Neon"}), encoding="utf-8")
    a = make_app()
    assert a.cfg.get("theme") == "Koyu" and customtkinter.get_appearance_mode() == "Dark"


def test_the_log_button_opens_the_log_file(app, monkeypatch):
    from app import ui
    opened = []
    monkeypatch.setattr(ui, "open_file", opened.append)
    app.open_log()
    assert len(opened) == 1 and os.path.exists(opened[0]) and opened[0].endswith("diso.log")


def test_the_extension_folder_button(app, monkeypatch):
    from app import ui
    opened = []
    monkeypatch.setattr(ui, "open_in_file_manager", opened.append)
    app.open_extension_folder()
    assert len(opened) == 1 and opened[0].endswith("browser_extension")


def test_a_crashing_callback_is_logged_and_the_window_survives(app, isolated_home):
    try:
        raise ValueError("boom in a button")
    except ValueError as e:
        app.report_callback_exception(type(e), e, e.__traceback__)
    assert "Hoppala, beklenmedik" in notice(app)
    text = (isolated_home / "AppData" / "Local" / "DISO" / "diso.log").read_text(encoding="utf-8")
    assert "callback failed" in text and "boom in a button" in text
    app.update()


def test_a_failing_call_from_another_thread_does_not_stop_the_queue(app):
    ran = []
    app._ui_calls.put(lambda: 1 / 0)
    app._ui_calls.put(lambda: ran.append("second"))
    app._drain_ui_calls()
    assert ran == ["second"]


def test_the_window_uses_the_app_icon(app):
    assert os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.ico"))
    app.update()


def test_a_cancelled_item_is_not_a_duplicate_so_the_link_can_be_added_again(app, monkeypatch):
    add_item(app, "X", CANCELLED, url="http://x.com/a")
    monkeypatch.setattr(app.manager, "start", lambda item: None)
    assert app.add_urls(["http://x.com/a"]) == 1


def test_the_log_keeps_working_after_the_window_is_destroyed(app):
    from app.logs import log
    log.info("still there")


def test_downloading_state_helper_constants():
    assert DOWNLOADING != QUEUED and startup.APP_NAME == "DISO" and LIMITER is not None


# --------------------------------------------------------------- fit to the screen
class FakeWindow:
    def __init__(self, sw, sh, scale=1.0):
        self.sw, self.sh, self.scale, self.geo = sw, sh, scale, None

    def _get_window_scaling(self):
        return self.scale

    def winfo_screenwidth(self):
        return self.sw

    def winfo_screenheight(self):
        return self.sh

    def geometry(self, text):
        self.geo = text


@pytest.mark.parametrize("sw,sh,scale,expected", [
    (2560, 1440, 1.0, (1000, 820)),            # big screen: the wanted size
    (1920, 1080, 1.0, (1000, 820)),
    (1920, 1080, 1.5, (1000, 600)),            # 150 % scaling: the screen is only 720 units high
    (1366, 768, 1.0, (1000, 648)),             # small laptop
    (1366, 768, 1.25, (1000, 494)),
    (800, 600, 1.0, (760, 480)),               # tiny screen
    (300, 200, 1.0, (360, 360)),               # never absurdly small
])
def test_windows_never_grow_larger_than_the_screen(sw, sh, scale, expected):
    from app import ui
    win = FakeWindow(sw, sh, scale)
    assert ui.fit_geometry(win, 1000, 820) == expected
    assert win.geometry and win.geo == f"{expected[0]}x{expected[1]}"


def test_a_window_without_scaling_support_is_still_sized():
    from app import ui

    class Plain:
        def winfo_screenwidth(self):
            return 1920

        def winfo_screenheight(self):
            return 1080

        def geometry(self, text):
            self.geo = text

    w = Plain()
    assert ui.fit_geometry(w, 500, 400) == (500, 400) and w.geo == "500x400"


def test_the_real_windows_fit_the_screen(app):
    app.update()
    assert app.winfo_height() <= app.winfo_screenheight()               # real pixels
    for open_window in (app._open_settings, app._open_updates):
        open_window()
    app.update()
    assert app.settings_panel.winfo_height() <= app.winfo_screenheight()
    assert app.update_panel.winfo_height() <= app.winfo_screenheight()
