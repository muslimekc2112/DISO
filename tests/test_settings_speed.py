"""⚡ The settings window: opened at once (made unseen in advance) and smooth while its edge is dragged (the scroll
bars only move their handle, the rows take the new width once the edge stops). 🎨 The accent colours."""
import time

import customtkinter as ctk
import pytest

from app import look, ui, ui_common  # noqa: F401 - importing ui installs the hooks
from app.config import Config


def run_for(win, seconds):
    end = time.time() + seconds
    while time.time() < end:
        win.update()
        time.sleep(0.01)


# ------------------------------------------------------------------------------ resizing
def test_a_scroll_bar_that_did_not_move_is_not_drawn_again():
    root = ctk.CTk()
    try:
        bar = ctk.CTkScrollbar(root)
        bar.pack()
        root.update()
        drawn = []
        real = bar._draw_engine.draw_rounded_scrollbar
        bar._draw_engine.draw_rounded_scrollbar = lambda *a: drawn.append(a) or real(*a)
        bar.set(0.0, 0.5)
        bar.set(0.0, 0.5)                                   # the same again: nothing to do
        bar.set(0.1, 0.6)
        assert len(drawn) == 2 and bar.get() == (0.1, 0.6)
    finally:
        root.destroy()


def test_the_rows_take_the_new_width_once_the_edge_stops():
    root = ctk.CTk()
    try:
        root.geometry("400x300")
        frame = ctk.CTkScrollableFrame(root)
        frame.pack(fill="both", expand=True)
        for i in range(30):
            ctk.CTkLabel(frame, text=f"satır {i}").pack()
        run_for(root, 0.3)
        width = lambda: int(frame._parent_canvas.itemcget(frame._create_window_id, "width"))   # noqa: E731
        before = width()
        for w in range(420, 600, 20):                      # dragging the edge
            root.geometry(f"{w}x300")
            root.update()
        assert width() == before                           # meanwhile the rows stand still (a picture of them)
        run_for(root, (ui_common.RESIZE_SETTLE + 150) / 1000)
        assert width() > before                            # and take the new width once it stops
        assert not frame._parent_canvas.find_withtag("still") and not getattr(frame, "_painting_held", False)
        assert frame._parent_canvas.itemcget(frame._create_window_id, "state") in ("", "normal")
    finally:
        root.destroy()


def test_a_window_hears_only_its_own_size_changes():
    root = ctk.CTk()
    try:
        calls = []
        real = root._update_dimensions_event
        root._update_dimensions_event = lambda e=None: calls.append(e.widget) or real(e)
        root.bind_class(f"own-size-{id(root)}", "<Configure>", root._update_dimensions_event)
        for i in range(20):
            ctk.CTkButton(root, text=str(i)).pack()
        root.geometry("300x700")
        run_for(root, 0.3)
        assert calls and all(w is root for w in calls)     # not once for every button in it
    finally:
        root.destroy()


# ------------------------------------------------------------------------------ opening at once
def test_the_settings_are_made_in_advance_and_open_at_once(make_app, monkeypatch):
    app = make_app()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    app._prepare_settings()
    spare = app._spare_settings
    assert spare is not None and spare.state() == "withdrawn" and app.settings_panel is None
    while spare.__dict__.get("_pending"):
        app.update()
    assert spare.state() == "withdrawn"                     # made out of sight, all of it
    app._open_settings("Zamanlayıcı")
    assert app.settings_panel is spare and spare.state() == "normal" and app._spare_settings is None
    app._dialog_parent()                                    # (the open one is the parent of questions)
    spare.destroy()
    assert app._spare_job is not None                       # the next one is on its way
    app.after_cancel(app._spare_job)
    app._spare_job = None


def test_a_setting_changed_elsewhere_throws_the_waiting_window_away(make_app, monkeypatch):
    app = make_app()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    app.cfg.watchers.append(app._setting_changed)
    app._prepare_settings()
    spare = app._spare_settings
    app.cfg.set("kind", "MP3 (sadece ses)")                 # not shown in the settings: it stays
    assert app._spare_settings is spare
    app.cfg.set("notify_sound", not app.cfg.get("notify_sound"))     # shown there: it would be old
    assert app._spare_settings is None and not spare.winfo_exists()
    app.after_cancel(app._spare_job)
    app._spare_job = None


def test_a_config_tells_its_watchers(isolated_home):
    cfg = Config()
    seen = []
    cfg.watchers.append(seen.append)
    cfg.watchers.append(lambda key: 1 / 0)                  # a broken watcher stops nothing
    cfg.set("notify_sound", False)
    cfg.set("notify_sound", False)                          # no change: no news
    assert seen == ["notify_sound"] and Config().get("notify_sound") is False


# ------------------------------------------------------------------------------ 🎨 accent colours
@pytest.mark.parametrize("name", list(look.ACCENTS))
def test_every_accent_colour_reads_well(name):
    try:
        assert look.apply("Standart", "Koyu", name) == "Standart" and look.accent_name() == name
        for mode in (0, 1):
            assert look.contrast(look.ACCENT_TEXT[mode], look.ACCENT[mode]) >= 4.5
            assert look.contrast("#FFFFFF", look.ACCENT_DEEP[mode]) >= 4.5
            assert look.contrast("#FFFFFF", look.SEGMENT_TRACK[mode]) >= 4.5
            for surface in (look.WINDOW, look.CARD, look.CARD_HIGH, look.INPUT):
                assert look.contrast(look.TEXT[mode], surface[mode]) >= 7
    finally:
        look.apply("Yeni")


def test_pink_is_as_drawn_and_other_looks_keep_it():
    look.apply("Yeni", accent="Pembe")
    pink = look.ACCENT
    look.apply("Nostalji", accent="Mavi")                   # Nostalji has its own colours
    assert look.accent_name() == "Pembe"
    look.apply("Yeni", accent="Mavi")
    assert look.ACCENT != pink
    look.apply("Yeni", accent="Yok böyle")                  # an unknown one: pink
    assert look.ACCENT == pink and look.accent_name() == "Pembe"
