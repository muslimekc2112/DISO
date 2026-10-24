"""✨ Soft transitions and ⚡ speed: windows fade in and out, the download window and the music player cross-fade,
the cover melts into the next one; the settings open at once (their groups are made one after another) and the
music player is made in the background before it is first needed."""
import time

import pytest
from music_support import FakeBackend, FakeReader, make_wav

from app import player, tags, ui_common

pytestmark = pytest.mark.gui


@pytest.fixture
def animate(monkeypatch):
    monkeypatch.setenv("DISO_ANIMATE", "1")


def run_for(win, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        win.update()
        time.sleep(0.005)


def test_the_curves_start_fast_and_end_softly():
    assert ui_common.ease_out(0) == 0 and ui_common.ease_out(1) == 1
    assert ui_common.ease_out(0.5) > 0.8                             # most of the way in the first half
    assert ui_common.ease_in_out(0.5) == pytest.approx(0.5)
    assert ui_common.ease_in_out(0.1) < 0.1 and ui_common.ease_in_out(0.9) > 0.9
    assert ui_common.ease_out(-1) == 0 and ui_common.ease_out(7) == 1


def test_animations_are_off_in_tests_unless_asked(monkeypatch):
    assert not ui_common.animations_on()
    monkeypatch.setenv("DISO_ANIMATE", "1")
    assert ui_common.animations_on()


def test_a_fade_goes_smoothly_to_its_end_and_says_so(app):
    seen, done = [], []
    real = app.attributes

    def spy(*args):
        if args[:1] == ("-alpha",) and len(args) == 2:
            seen.append(round(float(args[1]), 3))
        return real(*args)
    app.attributes = spy
    try:
        app.deiconify()
        app.update()                                                  # (its first drawing is not part of the fade)
        ui_common.fade(app, 0.0, 1.0, 150, done=lambda: done.append(1))
        run_for(app, 0.4)
    finally:
        app.attributes = real
    assert done == [1] and seen[0] == 0.0 and seen[-1] == 1.0
    assert len(seen) >= 5 and seen == sorted(seen)                   # many small steps, never back
    app.withdraw()


def test_a_newer_fade_takes_over(app):
    done = []
    app.deiconify()
    ui_common.fade(app, 0.0, 1.0, 300, done=lambda: done.append("first"))
    ui_common.fade(app, 1.0, 0.5, 60, done=lambda: done.append("second"))
    run_for(app, 0.45)
    assert done == ["second"] and float(app.attributes("-alpha")) == pytest.approx(0.5, abs=0.01)
    app.attributes("-alpha", 1.0)
    app.withdraw()


def test_a_new_window_fades_in_and_its_x_fades_it_out(app, animate):
    import customtkinter as ctk
    ui_common.install_soft_windows()
    win = ctk.CTkToplevel(app)
    assert float(win.attributes("-alpha")) == 0.0                    # unseen while customtkinter draws it
    run_for(win, 0.5)
    assert float(win.attributes("-alpha")) == pytest.approx(1.0)
    win.tk.eval(win.protocol("WM_DELETE_WINDOW"))                    # the ×
    run_for(app, 0.05)
    assert win.winfo_exists() and float(win.attributes("-alpha")) < 1.0   # going …
    run_for(app, 0.3)
    assert not win.winfo_exists()                                    # … gone


def test_a_window_that_stays_hidden_is_whole_when_shown_later(app, animate):
    import customtkinter as ctk
    ui_common.install_soft_windows()
    win = ctk.CTkToplevel(app)
    win.withdraw()
    run_for(app, 0.3)
    assert float(win.attributes("-alpha")) == 1.0
    win.destroy()


def test_switching_to_the_music_player_cross_fades(app, animate, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    app.deiconify()
    app.update()
    assert app._ensure_music()
    music = app.music
    seen = []
    real = music.attributes

    def spy(*args):
        if args[:1] == ("-alpha",) and len(args) == 2:
            seen.append(float(args[1]))
        return real(*args)
    music.attributes = spy
    app._switch_mode("Müzik çalar modu")
    assert music.winfo_viewable() and app.winfo_viewable()          # both, while the new one comes in
    run_for(app, 0.5)
    music.attributes = real
    steps = [a for a in seen if 0.0 < a < 1.0]
    assert len(steps) >= 6 and steps == sorted(steps)                # really faded in, frame by frame
    assert float(music.attributes("-alpha")) == 1.0 and not app.winfo_viewable()
    app._switch_mode("İndirme modu")
    run_for(app, 0.5)
    assert app.winfo_viewable() and not music.winfo_viewable() and float(app.attributes("-alpha")) == 1.0
    app.withdraw()


def test_the_cover_melts_into_the_next_one(app, animate, monkeypatch, tmp_path):
    from PIL import Image
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    assert app._ensure_music()
    music = app.music
    covers = []
    for colour in ("#ff0000", "#0000ff"):
        p = str(tmp_path / f"{colour[1:]}.jpg")
        Image.new("RGB", (300, 300), colour).save(p)
        covers.append(p)
    shown = []
    real = music._show_cover_picture
    music._show_cover_picture = lambda img: shown.append(img.getpixel((112, 112))) or real(img)
    music._set_cover(covers[0])
    music._set_cover(None, final=False)                             # the next song's cover is being read:
    assert len(shown) == 1                                          # the old one stays meanwhile
    music._set_cover(covers[1])
    run_for(music, 0.5)
    assert shown[0][0] > 200 and shown[-1][2] > 200                  # red … blue
    middle = shown[len(shown) // 2]
    assert len(shown) >= 6 and 30 < middle[0] < 230 and 30 < middle[2] < 230     # purple in between


def test_the_settings_open_at_once_and_fill_in_after(app):
    app._open_settings()
    panel = app.settings_panel
    assert panel.__dict__.get("_pending")                            # only the first group yet
    assert "Ekstralar" not in panel._cards
    assert panel.defender_switch is not None                        # asked for: the rest is made at once
    assert not panel.__dict__.get("_pending") and "Bitince" in panel._cards
    panel.destroy()
    app._open_settings()
    panel = app.settings_panel
    run_for(app, 0.6)                                               # left alone: they come one by one
    assert not panel.__dict__.get("_pending") and len(panel._cards) == 8
    with pytest.raises(AttributeError):
        panel._no_such_thing                                         # noqa: B018
    panel.show_tab("Bitince")
    panel.destroy()


def test_the_music_player_is_made_in_the_background(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(app, "_recent_input", lambda: False)
    assert app.music is None
    app._prepare_music()
    assert app.music is not None and not app.music.winfo_viewable()
    made = app.music
    app._prepare_music()                                             # once
    assert app.music is made


def test_a_busy_user_is_not_interrupted(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(app, "_recent_input", lambda: True)
    monkeypatch.setattr(app, "focus_displayof", lambda: app)
    later = []
    monkeypatch.setattr(app, "after", lambda ms, fn=None, *a: later.append(ms))
    app._prepare_music()
    assert app.music is None and later == [2000]


def test_the_settings_stay_unseen_until_every_group_is_there_then_fade_in_once(app, animate):
    ui_common.install_soft_windows()
    app.deiconify()
    app.update()
    t0 = time.perf_counter()
    app._open_settings()
    panel = app.settings_panel
    seen = []                                                          # (alpha, groups made) as it opens
    end = time.perf_counter() + 1.5
    while time.perf_counter() < end:
        app.update()
        seen.append((round(float(panel.attributes("-alpha")), 2), len(panel._cards)))
        if seen[-1][0] == 1.0:
            break
        time.sleep(0.005)
    took = time.perf_counter() - t0
    assert seen[-1] == (1.0, 8) and took < 1.5
    assert all(groups == 8 for alpha, groups in seen if alpha > 0)    # never seen half made
    rising = [a for a, _ in seen if 0 < a < 1]
    assert len(rising) >= 3 and rising == sorted(rising)               # one smooth fade
    panel.destroy()
    app.withdraw()
