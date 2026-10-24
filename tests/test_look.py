"""The look of the program: the palette, the two styles and the windows built with the new one."""
import time

import customtkinter
import pytest
from ui_support import add_item, notice

from app import look
from app import ui as ui_module
from app.config import DEFAULTS, Config
from app.music_ui import MODE_MUSIC


@pytest.fixture
def new_look():
    look.apply("Yeni")
    yield
    look.apply("Klasik")                                   # the other tests expect the stock theme


def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def same(a, b):
    """Colour pairs come back as tuples or lists."""
    return (tuple(a) if isinstance(a, (list, tuple)) else a) == (tuple(b) if isinstance(b, (list, tuple)) else b)


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# ------------------------------------------------------------------------------ styles
def test_the_classic_style_is_the_stock_theme():
    look.apply("Klasik")
    assert not look.is_new() and look.style_name() == "Klasik"
    assert customtkinter.ThemeManager.theme["CTkButton"]["fg_color"] == ["#3B8ED0", "#1F6AA5"]
    assert customtkinter.ThemeManager.theme["CTkFont"]["family"] == "Roboto"


def test_the_new_style_recolors_the_theme_and_the_classic_one_brings_it_back(new_look):
    theme = customtkinter.ThemeManager.theme
    assert look.is_new() and look.style_name() == "Yeni"
    assert theme["CTkButton"]["fg_color"] == list(look.ACCENT) and theme["CTkButton"]["corner_radius"] == 10
    assert theme["CTkFrame"]["fg_color"] == list(look.CARD) and theme["CTkFrame"]["corner_radius"] == 14
    assert theme["CTk"]["fg_color"] == list(look.WINDOW)
    assert theme["CTkFont"]["family"] == "Segoe UI"
    look.apply("Klasik")
    assert customtkinter.ThemeManager.theme["CTkButton"]["fg_color"] == ["#3B8ED0", "#1F6AA5"]
    assert customtkinter.ThemeManager.theme["CTkFont"]["family"] == "Roboto"


def test_an_unknown_style_means_the_classic_one():
    assert look.apply("Neon") == "Klasik" and not look.is_new()


def test_the_entry_border_follows_the_style(new_look):
    assert look.entry_border() == list(look.BORDER)
    look.apply("Klasik")
    assert look.entry_border() == ["#979DA2", "#565B5E"]


def test_the_style_is_a_saved_setting(isolated_home):
    assert DEFAULTS["look"] == "Standart" and look.DEFAULT_STYLE == "Standart"
    cfg = Config()
    cfg.set("look", "Klasik")
    assert Config().get("look") == "Klasik"
    assert look.STYLES == ["Standart", "Yeni", "Klasik", "Nostalji"]                # the recommended one first
    assert look.label("Standart") == "Standart (Önerilen)" and look.style_of("Standart (Önerilen)") == "Standart"


def test_the_palette_is_readable_in_both_modes():
    white = ("#FFFFFF", "#F1F2F7")
    for mode in (0, 1):                                    # light, dark
        assert contrast(look.ACCENT_TEXT[mode], look.ACCENT[mode]) >= 4.5      # text on every button
        assert contrast(white[mode], look.ACCENT_DEEP[mode]) >= 4.5            # selected mode-bar tab
        assert contrast(white[mode], look.SEGMENT_TRACK[mode]) >= 4.5          # the other tab
        for surface in (look.WINDOW, look.CARD, look.CARD_HIGH, look.INPUT):
            assert contrast(look.TEXT[mode], surface[mode]) >= 7               # body text
        assert contrast(look.ACCENT[mode], look.CARD[mode]) >= 3               # accent as a shape


# ------------------------------------------------------------------------------ windows
def test_every_window_can_be_built_in_the_new_style(new_look, make_app, monkeypatch):
    from tkinter import ttk

    from music_support import FakeBackend, FakeReader

    from app import player, tags
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app = make_app()
    add_item(app, "A", "downloading", total=100, done=40)
    app._sync_rows()
    app._open_settings()
    app._open_updates()
    app._ensure_music()
    app.update()
    assert app.settings_panel.look_menu.get() == "Standart (Önerilen)"          # (the saved one: the default)
    selected = ttk.Style().lookup("Music.Treeview", "background", ["selected"])
    assert selected in (look.ACCENT[0], look.ACCENT[1])
    app._switch_mode(MODE_MUSIC)
    app._switch_mode("İndirme modu")
    app.withdraw()


def test_rows_show_their_state_in_colour(new_look, app):
    from app.models import CANCELLED, DONE, DOWNLOADING, ERROR, PAUSED, QUEUED
    expected = {DONE: look.STATE_DONE, ERROR: look.STATE_ERROR, PAUSED: look.STATE_PAUSED,
                DOWNLOADING: look.ACCENT, QUEUED: look.STATE_IDLE, CANCELLED: look.STATE_IDLE}
    items = {state: add_item(app, state, state) for state in expected}
    app._sync_rows()
    for state, colour in expected.items():
        row = app.rows[items[state].id]
        row.refresh()
        assert row.stripe is not None
        assert same(row.stripe.cget("fg_color"), colour), state
    done_bar = app.rows[items[DONE].id].bar.cget("progress_color")
    assert same(done_bar, look.STATE_DONE)


def test_the_classic_style_has_no_stripes(app):
    it = add_item(app, "A", "done")
    app._sync_rows()
    assert app.rows[it.id].stripe is None


def test_choosing_a_style_asks_for_a_restart_and_keeps_the_choice_when_declined(app, monkeypatch):
    asked = []
    monkeypatch.setattr(ui_module.messagebox, "askyesno", lambda *a, **k: asked.append(a) or False)
    app._open_settings()
    app.settings_panel.look_menu._command("Klasik")
    time.sleep(0.3)
    app.update()
    assert app.cfg.get("look") == "Klasik" and len(asked) == 1 and "yeniden açılsın" in asked[0][1]
    assert not app.restart_requested and "sonraki açılışta" in notice(app)


def test_accepting_the_restart_closes_the_program_and_asks_main_to_start_it_again(app, monkeypatch):
    monkeypatch.setattr(ui_module.messagebox, "askyesno", lambda *a, **k: True)
    closed = []
    monkeypatch.setattr(app, "_on_close", lambda: closed.append(True))
    app._open_settings()
    app.settings_panel.look_menu._command("Klasik")
    time.sleep(0.3)
    app.update()
    assert app.cfg.get("look") == "Klasik" and app.restart_requested and closed == [True]


def test_no_question_when_the_style_is_not_what_changed(app, monkeypatch):
    monkeypatch.setattr(ui_module.messagebox, "askyesno", lambda *a, **k: pytest.fail("asked"))
    app._open_settings()
    app.settings_panel.theme_menu._command("Açık")
    time.sleep(0.3)
    app.update()


def test_a_wrong_saved_style_falls_back_to_the_default(isolated_home, make_app):
    import json
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir(exist_ok=True)
    (d / "settings.json").write_text(json.dumps({"look": "Neon"}), encoding="utf-8")
    app = make_app()
    assert app.cfg.get("look") == "Standart"
