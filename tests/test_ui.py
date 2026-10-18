"""The real window, hidden. Skipped when customtkinter or a display is missing."""
import gc
import json
import os
import time
import types

import pytest

pytest.importorskip("customtkinter")

from app import notify, updater  # noqa: E402
from app.models import (DONE, DOWNLOADING, ERROR, PAUSED, QUEUED, Item)  # noqa: E402
from app.segmented_downloader import LIMITER  # noqa: E402
from conftest import dump_threads, wait_for  # noqa: E402

pytestmark = pytest.mark.gui
MB = 1024 * 1024


class FakeCountdown:
    """Stands in for the countdown window: records the question and answers 'yes' at once."""
    log = []

    def __init__(self, app, text, seconds, on_done):
        FakeCountdown.log.append((text, seconds))
        on_done()


@pytest.fixture
def make_app(monkeypatch, isolated_home):
    from app import ui
    FakeCountdown.log = []
    notes = {"sound": [], "toast": [], "power": []}
    monkeypatch.setattr(updater.Updater, "start", lambda self: None)          # no network
    monkeypatch.setattr(notify, "play_sound", lambda kind="done": notes["sound"].append(kind))
    monkeypatch.setattr(notify, "toast", lambda title, body: notes["toast"].append((title, body)))
    monkeypatch.setattr(notify, "power_action", lambda kind: notes["power"].append(kind) or True)
    monkeypatch.setattr(ui, "CountdownDialog", FakeCountdown)
    made = []

    def make():
        try:
            app = ui.App()
        except Exception as e:  # noqa: BLE001 - no display
            pytest.skip(f"no display: {e}")
        app.withdraw()
        app.update()
        app.notes = notes
        made.append(app)
        return app

    yield make
    for app in made:
        try:
            app._closing = True
            app.manager.shutdown()
            gc.collect()      # same rule as the real window: collect Tk objects on this thread
            app.destroy()
        except Exception:  # noqa: BLE001 - already closed by the test
            pass
    gc.collect()
    gc.enable()


@pytest.fixture
def app(make_app):
    return make_app()


def add_item(app, title, state, **kw):
    it = Item(f"http://x/{title.lower()}", kind="file", title=title)
    it.state = state
    for k, v in kw.items():
        setattr(it, k, v)
    app.manager.items.append(it)
    return it


def shown(app):
    app._sync_rows()
    return [app.rows[i].item.title for i in app._order]


def notice(app):
    return app._notice


def local_urls(server, n, size=2000):
    return [server.url("f", server.file(size)[0]) for _ in range(n)]


# ------------------------------------------------------------------------------ list
def test_an_empty_list_shows_a_hint(app):
    app._sync_rows()
    assert "Henüz indirme yok" in app.empty_label.cget("text")


@pytest.fixture
def four(app):
    add_item(app, "Alpha", DONE, total=300, added=1)
    add_item(app, "Beta", PAUSED, total=100, added=2)
    add_item(app, "Gamma", ERROR, total=200, added=3)
    add_item(app, "Delta", DOWNLOADING, done=50, added=4)
    return app


def test_newest_first_is_the_default_order(four):
    assert shown(four) == ["Delta", "Gamma", "Beta", "Alpha"]


@pytest.mark.parametrize("flt,expected", [
    ("Hepsi", ["Delta", "Gamma", "Beta", "Alpha"]),
    ("Aktif", ["Delta"]), ("Sırada", []), ("Duraklatılmış", ["Beta"]),
    ("Tamamlanan", ["Alpha"]), ("Hatalı", ["Gamma"]),
])
def test_filters(four, flt, expected):
    four.filter_menu.set(flt)
    four._on_filter(flt)
    assert shown(four) == expected
    assert four.cfg.get("filter") == flt                 # remembered
    if not expected:
        assert "uyan indirme yok" in four.empty_label.cget("text")


def test_search_matches_names_and_links(four):
    four.search_entry.insert(0, "alp")
    assert shown(four) == ["Alpha"]
    four.search_entry.delete(0, "end")
    four.search_entry.insert(0, "x/gam")                 # part of the link, not the name
    assert shown(four) == ["Gamma"]
    four.search_entry.delete(0, "end")
    four.search_entry.insert(0, "nothing like this")
    assert shown(four) == []


@pytest.mark.parametrize("sort,expected", [
    ("Eski üstte", ["Alpha", "Beta", "Gamma", "Delta"]),
    ("Ad (A→Z)", ["Alpha", "Beta", "Delta", "Gamma"]),
    ("Boyut (büyük üstte)", ["Alpha", "Gamma", "Beta", "Delta"]),
    ("Duruma göre", ["Delta", "Beta", "Gamma", "Alpha"]),       # active, paused, error, done
])
def test_sorting(four, sort, expected):
    four.sort_menu.set(sort)
    four._on_sort(sort)
    assert shown(four) == expected
    assert four.cfg.get("sort") == sort


def test_filter_search_and_sort_work_together(four):
    four.filter_menu.set("Hepsi")
    four.search_entry.insert(0, "a")                      # Alpha, Beta, Gamma, Delta all contain 'a'
    four.sort_menu.set("Ad (A→Z)")
    four._on_sort("Ad (A→Z)")
    assert shown(four) == ["Alpha", "Beta", "Delta", "Gamma"]
    four.filter_menu.set("Duraklatılmış")
    four._on_filter("Duraklatılmış")
    assert shown(four) == ["Beta"]


def test_rows_are_removed_when_items_disappear(four):
    four.manager.items.pop(0)
    assert shown(four) == ["Delta", "Gamma", "Beta"]
    assert len(four.rows) == 3


# ------------------------------------------------------------------------- selection
def test_select_all_selects_what_is_visible_and_enables_the_bulk_buttons(four):
    shown(four)
    four.select_all_var.set(True)
    four._on_select_all()
    assert len(four.selected) == 4 and four.sel_label.cget("text") == "4 seçili"
    assert all(b.cget("state") == "normal" for b in four.sel_buttons)
    four.select_all_var.set(False)
    four._on_select_all()
    assert four.selected == set() and all(b.cget("state") == "disabled" for b in four.sel_buttons)


def test_select_all_only_touches_visible_rows(four):
    four.filter_menu.set("Hatalı")
    four._on_filter("Hatalı")
    four.select_all_var.set(True)
    four._on_select_all()
    four.filter_menu.set("Hepsi")
    four._on_filter("Hepsi")
    assert {four.rows[i].item.title for i in four.selected} == {"Gamma"}
    assert four.select_all_var.get() is False             # not everything is selected


def test_ticking_a_row_selects_that_item(four):
    shown(four)
    row = next(r for r in four.rows.values() if r.item.title == "Beta")
    row.sel_var.set(True)
    row._on_select()
    assert four.selected == {row.item.id}
    assert four.sel_label.cget("text") == "1 seçili"


def test_selected_items_that_are_removed_leave_the_selection(four):
    shown(four)
    four.selected = {i.id for i in four.manager.items}
    four.manager.items.pop()
    four._sync_rows()
    assert len(four.selected) == 3


def test_bulk_pause_and_resume_go_to_the_manager_for_selected_items_only(four, monkeypatch):
    shown(four)
    calls = []
    monkeypatch.setattr(four.manager, "pause", lambda it: calls.append(("pause", it.title)))
    monkeypatch.setattr(four.manager, "resume", lambda it: calls.append(("resume", it.title)))
    four.selected = {i.id for i in four.manager.items if i.title in ("Beta", "Delta")}
    four._sel_pause()
    four._sel_resume()
    assert sorted(calls) == [("pause", "Beta"), ("pause", "Delta"), ("resume", "Beta"), ("resume", "Delta")]


def test_bulk_remove_asks_before_deleting_several_items(four, monkeypatch):
    from app import ui
    shown(four)
    four.selected = {i.id for i in four.manager.items if i.title in ("Alpha", "Beta")}
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: False)
    four._sel_remove()
    assert len(four.manager.items) == 4                   # declined: nothing happens
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
    four._sel_remove()
    assert sorted(i.title for i in four.manager.items) == ["Delta", "Gamma"]
    assert four.selected == set()


def test_removing_one_selected_item_needs_no_question(four, monkeypatch):
    from app import ui
    shown(four)
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: pytest.fail("should not ask"))
    four.selected = {next(i.id for i in four.manager.items if i.title == "Beta")}
    four._sel_remove()
    assert sorted(i.title for i in four.manager.items) == ["Alpha", "Delta", "Gamma"]


def test_row_buttons_talk_to_the_manager(four, monkeypatch):
    shown(four)
    calls = []
    monkeypatch.setattr(four.manager, "resume", lambda it: calls.append(("resume", it.title)))
    monkeypatch.setattr(four.manager, "pause", lambda it: calls.append(("pause", it.title)))
    monkeypatch.setattr(four.manager, "remove", lambda it: calls.append(("remove", it.title)))
    rows = {r.item.title: r for r in four.rows.values()}
    rows["Beta"]._toggle()        # paused  -> resume
    rows["Delta"]._toggle()       # running -> pause
    rows["Alpha"]._remove()
    assert calls == [("resume", "Beta"), ("pause", "Delta"), ("remove", "Alpha")]


def test_a_rows_text_follows_the_items_state(four):
    shown(four)
    rows = {r.item.title: r for r in four.rows.values()}
    assert "Tamamlandı" in rows["Alpha"].info.cget("text")
    assert "Duraklatıldı" in rows["Beta"].info.cget("text")
    assert "❌" in rows["Gamma"].info.cget("text")
    assert rows["Alpha"].open_btn.cget("state") == "normal"
    assert rows["Beta"].open_btn.cget("state") == "disabled"
    assert rows["Delta"].toggle_btn.cget("text") == "⏸" and rows["Beta"].toggle_btn.cget("text") == "▶"


# ----------------------------------------------------------------------------- settings
def test_settings_apply_immediately_and_are_saved(app, isolated_home):
    app.apply_setting("max_parallel", 5)
    app.apply_setting("speed_limit", "1 MB/s")
    assert app.manager.max_parallel == 5 and LIMITER.rate == MB
    saved = json.load(open(isolated_home / ".hizli_indirici" / "settings.json", encoding="utf-8"))
    assert saved["max_parallel"] == 5 and saved["speed_limit"] == "1 MB/s"
    app.apply_setting("speed_limit", "Sınırsız")
    assert LIMITER.rate == 0 and "kaldırıldı" in notice(app)


def test_the_option_bar_choices_are_saved(app):
    app._on_kind("Ses (MP3)")
    app.quality_menu._command("720p")
    app.bitrate_menu._command("128")
    app.conn_menu._command("32")
    app.cookie_menu._command("firefox")
    app.playlist_var.set(True)
    app.playlist_var.set(True)
    from app import ui
    assert ui.KIND_LABELS[app.cfg.get("kind")] == "audio"
    assert (app.cfg.get("quality"), app.cfg.get("bitrate"), app.cfg.get("connections"),
            app.cfg.get("cookies")) == ("720p", "128", "32", "firefox")


def test_saved_settings_come_back_at_the_next_start(make_app, isolated_home, tmp_path):
    folder = str(tmp_path / "my downloads")
    d = isolated_home / ".hizli_indirici"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({
        "quality": "720p", "connections": "32", "bitrate": "128", "cookies": "firefox",
        "playlist": True, "folder": folder, "max_parallel": 6, "speed_limit": "512 KB/s",
        "filter": "Hatalı", "sort": "Ad (A→Z)", "block_duplicates": False}), encoding="utf-8")
    a = make_app()
    assert (a.quality_menu.get(), a.conn_menu.get(), a.bitrate_menu.get(), a.cookie_menu.get()) == \
           ("720p", "32", "128", "firefox")
    assert a.playlist_var.get() is True and a.folder_entry.get() == folder
    assert a.manager.max_parallel == 6 and LIMITER.rate == 512 * 1024
    assert (a.filter_menu.get(), a.sort_menu.get()) == ("Hatalı", "Ad (A→Z)")
    assert a._settings().folder == folder and a._settings().connections == 32


def test_saved_values_that_no_longer_exist_fall_back_to_defaults(make_app, isolated_home):
    d = isolated_home / ".hizli_indirici"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"quality": "9999p", "max_parallel": 99,
                                                 "speed_limit": "1 GB/s"}), encoding="utf-8")
    a = make_app()
    assert a.quality_menu.get() == "En iyi" and a.manager.max_parallel == 3 and LIMITER.rate == 0


def test_the_end_action_is_never_restored_from_a_previous_session(make_app, isolated_home):
    d = isolated_home / ".hizli_indirici"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"after_all": "Bilgisayarı kapat"}), encoding="utf-8")
    assert make_app().after_all == "Hiçbir şey yapma"


def test_status_line_shows_parallel_count_and_the_limit(app):
    app.apply_setting("speed_limit", "2 MB/s")
    app._update_status()
    text = app.status.cget("text")
    assert "Aktif: 0/3" in text and "Sınır: 2 MB/s" in text
    app.set_after_all("Bilgisayarı uyut")
    app._update_status()
    assert "Bitince: bilgisayarı uyut" in app.status.cget("text")


def test_settings_window_is_wired_to_the_app(app):
    app._open_settings()
    panel = app.settings_panel
    assert panel is not None
    app._open_settings()
    assert app.settings_panel is panel                    # not opened twice
    panel.parallel_menu._command("4")
    panel.speed_menu._command("256 KB/s")
    assert app.manager.max_parallel == 4 and LIMITER.rate == 256 * 1024
    panel.sound_switch.toggle()
    panel.toast_switch.toggle()
    panel.dup_switch.toggle()
    assert (app.cfg.get("notify_sound"), app.cfg.get("notify_toast"), app.cfg.get("block_duplicates")) == \
           (False, False, False)
    panel.after_menu._command("Bilgisayarı kapat")
    assert app.after_all == "Bilgisayarı kapat"
    app.after_all = "Hiçbir şey yapma"                    # the action fired: the menu follows
    panel._sync()
    assert panel.after_menu.get() == "Hiçbir şey yapma"
    panel.destroy()
    app._open_settings()
    assert app.settings_panel is not panel                # a closed window can be opened again


def test_test_notification_button(app):
    app.test_notification()
    assert app.notes["sound"] == ["done"] and app.notes["toast"][0][1].startswith("Bildirimler")


# ------------------------------------------------------------------------------ adding
def test_duplicate_links_are_skipped_with_a_notice(app, server, tmp_path):
    app.folder_entry.delete(0, "end")
    app.folder_entry.insert(0, str(tmp_path / "dl"))
    url = local_urls(server, 1)[0]
    assert app.add_urls([url]) == 1
    assert app.add_urls([url]) == 0 and "zaten listede" in notice(app)
    other = local_urls(server, 1)[0]
    assert app.add_urls([url, other]) == 1 and "zaten listedeydi" in notice(app)
    app.apply_setting("block_duplicates", False)
    assert app.add_urls([url]) == 1


def test_invalid_links_are_reported(app):
    assert app.add_urls(["not a link", "ftp://x/y"]) == 0
    assert "geçersiz" in notice(app)


def test_an_added_link_is_downloaded_into_the_chosen_folder(app, server, tmp_path):
    out = tmp_path / "dl"
    app.folder_entry.delete(0, "end")
    app.folder_entry.insert(0, str(out))
    name, data = server.file(5000, ".zip")
    app.url_entry.insert(0, server.url("f", name))
    app.add_from_entry()
    assert app.url_entry.get() == ""                      # the box is cleared after adding
    assert wait_for(lambda: [i.state for i in app.manager.items] == [DONE])
    assert (out / name).read_bytes() == data


def test_an_empty_box_asks_for_a_link(app):
    app.add_from_entry()
    assert "bağlantı yapıştır" in notice(app)


def test_dropped_links_and_text_files_are_added(app, server, tmp_path):
    app.folder_entry.delete(0, "end")
    app.folder_entry.insert(0, str(tmp_path / "dl"))
    urls = local_urls(server, 3)
    listing = tmp_path / "link list.txt"                  # a space in the path: tkdnd wraps it in {}
    listing.write_text(f"{urls[0]}\nnot a link\n{urls[1]}\n", encoding="utf-8")
    event = types.SimpleNamespace(data="{%s} %s" % (str(listing).replace("\\", "/"), urls[2]), action="copy")
    app._on_drop(event)
    assert len(app.manager.items) == 3 and "3 bağlantı eklendi" in notice(app)
    app._on_drop(event)                                   # dropping the same things again
    assert len(app.manager.items) == 3 and "zaten listede" in notice(app)


def test_a_drop_without_links_says_so(app, tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("nothing here", encoding="utf-8")
    app._on_drop(types.SimpleNamespace(data=str(empty).replace("\\", "/"), action="copy"))
    assert "bulunamadı" in notice(app) and app.manager.items == []
    app._on_drop(types.SimpleNamespace(data="just words", action="copy"))
    assert "bulunamadı" in notice(app)


def test_the_import_file_button_adds_every_link_of_a_file(app, server, tmp_path):
    app.folder_entry.delete(0, "end")
    app.folder_entry.insert(0, str(tmp_path / "dl"))
    f = tmp_path / "l.txt"
    f.write_text("\n".join(local_urls(server, 2)), encoding="utf-8")
    assert app._add_from_paths([str(f)]) == 2
    f2 = tmp_path / "none.txt"
    f2.write_text("no links", encoding="utf-8")
    assert app._add_from_paths([str(f2)]) == 0 and "Dosyada bağlantı bulunamadı" in notice(app)


# --------------------------------------------------------------------- notifications
def test_finished_downloads_play_a_sound_and_show_a_toast(app):
    a = Item("http://x/a", title="a.zip")
    app.manager.events.put(("done", a))
    app._drain_events()
    assert app.notes["sound"] == ["done"] and app.notes["toast"] == [("İndirme tamamlandı", "a.zip")]


def test_several_finished_downloads_give_one_summary(app):
    for n in "abc":
        app.manager.events.put(("done", Item(f"http://x/{n}", title=n)))
    app._drain_events()
    assert app.notes["toast"] == [("İndirme tamamlandı", "3 indirme tamamlandı")]
    assert app.notes["sound"] == ["done"]


def test_failures_use_the_error_sound_and_title(app):
    app.manager.events.put(("error", Item("http://x/a", title="broken.zip")))
    app._drain_events()
    assert app.notes["sound"] == ["error"] and app.notes["toast"] == [("İndirme başarısız", "broken.zip")]


def test_sound_and_toast_can_be_switched_off_separately(app):
    app.apply_setting("notify_sound", False)
    app.manager.events.put(("done", Item("http://x/a", title="a")))
    app._drain_events()
    assert app.notes["sound"] == [] and len(app.notes["toast"]) == 1
    app.apply_setting("notify_toast", False)
    app.manager.events.put(("done", Item("http://x/b", title="b")))
    app._drain_events()
    assert len(app.notes["toast"]) == 1


# ------------------------------------------------------------------------ end action
def finish(app, state=DONE, done_in_phase=1):
    app._phase_done = done_in_phase
    for it in app.manager.items:
        it.state = state
    app._check_after_all()


def test_shutdown_after_the_last_download_with_a_countdown(app):
    app.set_after_all("Bilgisayarı kapat")
    add_item(app, "A", DOWNLOADING)
    app._check_after_all()                                # work in progress: nothing yet
    assert app.notes["power"] == []
    finish(app)
    assert app.notes["power"] == ["shutdown"]
    assert FakeCountdown.log[-1][1] == 30 and "Bilgisayar kapanacak" in FakeCountdown.log[-1][0]
    assert app.after_all == "Hiçbir şey yapma"            # one-shot
    app._check_after_all()
    assert app.notes["power"] == ["shutdown"]             # not twice


def test_sleep_action(app):
    app.set_after_all("Bilgisayarı uyut")
    add_item(app, "A", DOWNLOADING)
    app._check_after_all()
    finish(app)
    assert app.notes["power"] == ["sleep"]


def test_close_action_closes_the_app_after_ten_seconds(app, monkeypatch):
    closed = []
    monkeypatch.setattr(app, "_on_close", lambda: closed.append(1))
    app.set_after_all("Uygulamayı kapat")
    add_item(app, "A", DOWNLOADING)
    app._check_after_all()
    finish(app)
    assert closed == [1] and FakeCountdown.log[-1][1] == 10 and app.notes["power"] == []


def test_a_paused_download_means_not_finished_so_nothing_happens(app):
    app.set_after_all("Bilgisayarı kapat")
    add_item(app, "A", DOWNLOADING)
    add_item(app, "B", PAUSED)
    app._check_after_all()
    app.manager.items[0].state = DONE
    app._phase_done = 1
    app._check_after_all()
    assert app.notes["power"] == [] and FakeCountdown.log == []


def test_downloads_still_waiting_in_the_queue_mean_not_finished(app):
    app.set_after_all("Bilgisayarı kapat")
    add_item(app, "A", DOWNLOADING)
    add_item(app, "B", QUEUED)
    app._check_after_all()
    app.manager.items[0].state = DONE
    app._phase_done = 1
    app._check_after_all()
    assert app.notes["power"] == []


def test_only_failures_do_not_trigger_the_end_action(app):
    app.set_after_all("Bilgisayarı kapat")
    add_item(app, "A", DOWNLOADING)
    app._check_after_all()
    finish(app, state=ERROR, done_in_phase=0)
    assert app.notes["power"] == []


def test_without_a_chosen_action_nothing_happens(app):
    add_item(app, "A", DOWNLOADING)
    app._check_after_all()
    finish(app)
    assert app.notes["power"] == [] and FakeCountdown.log == []


def test_a_new_batch_after_a_pause_can_still_trigger_the_action(app):
    app.set_after_all("Bilgisayarı kapat")
    it = add_item(app, "A", DOWNLOADING)
    app._check_after_all()
    it.state = PAUSED
    app._check_after_all()
    assert app.notes["power"] == []
    it.state = DOWNLOADING                                 # user resumes
    app._check_after_all()
    finish(app)
    assert app.notes["power"] == ["shutdown"]


# ------------------------------------------------------------------ update widgets
def test_update_button_shows_how_many_updates_are_waiting(app):
    comps = app.updates.components
    comps["yt-dlp"].status = "available"
    comps["ffmpeg"].status = "available"
    app._update_update_widgets()
    assert app.updates_btn.cget("text") == "⟳ Güncellemeler (2)"
    comps["yt-dlp"].status = comps["ffmpeg"].status = "current"
    app._update_update_widgets()
    assert app.updates_btn.cget("text") == "⟳ Güncellemeler"


def test_a_running_update_shows_a_progress_strip(app):
    assert app.update_bar.winfo_manager() == ""           # hidden when idle
    comp = app.updates.components["yt-dlp"]
    comp.status, comp.progress, comp.message = "working", 0.4, "İndiriliyor… 1 MB / 3 MB"
    app._update_update_widgets()
    assert app.update_bar.winfo_manager() == "grid"
    assert "yt-dlp" in app.update_label.cget("text") and "İndiriliyor" in app.update_label.cget("text")
    comp.status = "done"
    app._update_update_widgets()
    assert app.update_bar.winfo_manager() == ""


def test_update_panel_lists_every_component_and_refreshes(app):
    app._open_updates()
    panel = app.update_panel
    assert set(panel.cards) == {"yt-dlp", "yt-dlp-ejs", "ffmpeg"}
    app.updates.components["yt-dlp"].status = "available"
    app.updates.components["yt-dlp"].installed, app.updates.components["yt-dlp"].latest = "1.0", "2.0"
    panel._refresh()
    card = panel.cards["yt-dlp"]
    assert "Güncelleme var" in card.badge.cget("text") and "Son: 2.0" in card.versions.cget("text")
    assert card.button.cget("text") == "Güncelle"
    app.updates.components["ffmpeg"].status = "missing"
    panel._refresh()
    assert panel.cards["ffmpeg"].button.cget("text") == "Kur"
    app._open_updates()
    assert app.update_panel is panel


# ------------------------------------------------------------------------------ closing
def destroyed(app):
    try:
        app.update()
        return not app.winfo_exists()
    except Exception:  # noqa: BLE001 - Tcl error: the window is gone
        return True


def test_closing_returns_at_once_and_closes_the_window(app):
    t0 = time.time()
    app._on_close()
    assert time.time() - t0 < 0.5
    assert wait_for(lambda: destroyed(app), 5)


def test_closing_remembers_the_folder_and_pauses_running_downloads(app, server, isolated_home, tmp_path):
    out = tmp_path / "dl"
    app.folder_entry.delete(0, "end")
    app.folder_entry.insert(0, str(out))
    app.apply_setting("speed_limit", "128 KB/s")
    name, _ = server.file(4 * MB)
    app.add_urls([server.url("f", name)])
    assert wait_for(lambda: any(i.state == DOWNLOADING and i.done > 20_000 for i in app.manager.items), 20)
    t0 = time.time()
    app._on_close()
    assert time.time() - t0 < 0.5                          # the window does not wait for the workers
    assert wait_for(lambda: destroyed(app), 10), dump_threads()
    data = json.load(open(isolated_home / ".hizli_indirici" / "downloads.json", encoding="utf-8"))
    assert [i["state"] for i in data["items"]] == [PAUSED]
    settings = json.load(open(isolated_home / ".hizli_indirici" / "settings.json", encoding="utf-8"))
    assert settings["folder"] == str(out)
    assert os.path.exists(str(out / name) + ".part")        # the partial file is kept for resume


def test_closing_twice_is_harmless(app):
    app._on_close()
    app._on_close()
    assert wait_for(lambda: destroyed(app), 5)
