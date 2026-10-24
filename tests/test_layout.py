"""How the windows look: texts that fit their place, fast wheel scrolling without left-over pictures,
and the TR | EN switch at the top left of the main window."""
import sys
import time

import pytest
from ui_support import notice

pytestmark = pytest.mark.gui
ctk = pytest.importorskip("customtkinter")

from app import ui  # noqa: E402 - app.ui installs the scrolling and wrapping fixes


@pytest.fixture
def root():
    try:
        r = ctk.CTk()
    except Exception as e:  # noqa: BLE001 - no display
        pytest.skip(f"no display: {e}")
    r.geometry("400x300+40+40")
    yield r
    r.destroy()


def pump(widget, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        widget.update()
        time.sleep(0.01)


def cut_texts(win):
    """The visible labels whose text is wider than the label (the end of the text is cut off)."""
    out = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, ctk.CTkLabel) and c.winfo_ismapped() and str(c.cget("text")).strip():
                if c._label.winfo_reqwidth() > c.winfo_width() + 2:
                    out.append(str(c.cget("text"))[:50])
            walk(c)
    walk(win)
    return out


# --------------------------------------------------------------------------- fast wheel scrolling
@pytest.mark.skipif(not sys.platform.startswith("win"), reason="the wheel fix is for Windows")
def test_fast_wheel_steps_are_scrolled_together_and_painted(root):
    frame = ctk.CTkScrollableFrame(root)
    frame.pack(fill="both", expand=True)
    for i in range(80):
        ctk.CTkLabel(frame, text=f"Satır {i}").pack(anchor="w")
    pump(root)
    canvas = frame._parent_canvas
    calls = []
    real = canvas.yview

    def spy(*args):
        if args and args[0] == "scroll":
            calls.append(args)
        return real(*args)

    canvas.yview = spy
    for _ in range(5):                                   # five wheel steps before the window can paint
        canvas.event_generate("<MouseWheel>", delta=-120, x=10, y=10, when="tail")
    pump(root, 0.2)
    assert calls == [("scroll", 100, "units")]           # once, all of them together
    assert canvas.yview()[0] > 0
    calls.clear()
    canvas.event_generate("<MouseWheel>", delta=120, x=10, y=10)
    pump(root, 0.2)
    assert calls == [("scroll", -20, "units")]


def test_a_frame_closed_while_scrolling_is_no_error(root):
    frame = ctk.CTkScrollableFrame(root)
    frame.pack(fill="both", expand=True)
    for i in range(80):
        ctk.CTkLabel(frame, text=f"Satır {i}").pack(anchor="w")
    pump(root)
    frame._parent_canvas.event_generate("<MouseWheel>", delta=-120, x=10, y=10)
    frame.destroy()
    pump(root, 0.2)                                      # the waiting scroll finds no window: nothing happens


# --------------------------------------------------------------------------- texts that fit
LONG = "Bu uzun bir açıklama metni, dar bir pencerede sonu kesilmeden alt satıra geçmeli ve tamamı okunmalı."


def test_a_long_text_wraps_at_the_room_it_has_and_grows_back(root):
    box = ctk.CTkFrame(root, width=260, height=200)
    box.pack_propagate(False)
    box.pack(anchor="nw")
    label = ctk.CTkLabel(box, text=LONG, wraplength=600, justify="left", anchor="w")
    label.pack(fill="x")
    pump(root)
    scale = float(label._get_widget_scaling())
    assert label.cget("wraplength") <= 260 and cut_texts(root) == []
    box.configure(width=900)
    root.geometry("1000x300")
    pump(root)
    assert label.cget("wraplength") == 600                # room again: back to its own width, not wider


def test_a_text_that_fits_never_creeps_narrower(root):
    label = ctk.CTkLabel(root, text=LONG, wraplength=300, justify="left", anchor="w")
    label.grid(row=0, column=0, sticky="ew")              # stretched, but its column is only as wide as the text
    for _ in range(5):
        pump(root, 0.1)
        label.event_generate("<Configure>")
    assert label.cget("wraplength") == 300


def test_a_label_that_is_not_stretched_is_left_alone(root):
    label = ctk.CTkLabel(root, text=LONG, wraplength=500, justify="left")
    label.place(x=0, y=0)
    pump(root)
    assert label.cget("wraplength") == 500


# --------------------------------------------------------------------------- the settings window
def test_every_text_of_the_settings_fits_and_the_version_is_at_the_top(app):
    app._open_settings()
    panel = app.settings_panel
    panel.deiconify()
    for size in ("620x720", "560x420"):                   # the usual size and the smallest it allows
        panel.geometry(size)
        pump(panel, 0.4)
        canvas = panel.body._parent_canvas
        for pos in (0.0, 0.25, 0.5, 0.75, 1.0):
            canvas.yview_moveto(pos)
            pump(panel, 0.15)
            assert cut_texts(panel) == [], (size, pos)
    assert panel.version_label.grid_info()["row"] == 0 and "1.5" in panel.version_label.cget("text")


# --------------------------------------------------------------------------- TR | EN
def test_the_language_switch_at_the_top_left_offers_a_restart(app, monkeypatch):
    asked = []
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: asked.append(a[1]) or False)
    assert app.language_switch.get() == ("TR" if app.cfg.get("language") == "Türkçe" else "EN")
    app.cfg.set("language", "Türkçe")
    app._show_language()
    app._open_settings()
    assert app.language_switch.get() == "TR"
    app.language_switch._command("EN")                    # a click on "EN"
    pump(app, 0.4)
    assert app.cfg.get("language") == "English" and len(asked) == 1 and "yeniden" in asked[0]
    assert "bir sonraki açılışta" in notice(app)
    assert app.language_switch.get() == "EN" and app.settings_panel.language_menu.get() == "English"
    app.language_switch._command("EN")                    # the same again: nothing is asked
    pump(app, 0.3)
    assert len(asked) == 1


def test_the_settings_menu_moves_the_switch_too(app, monkeypatch):
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: False)
    app.cfg.set("language", "Türkçe")
    app._show_language()
    app.apply_setting("language", "English")
    assert app.language_switch.get() == "EN"
