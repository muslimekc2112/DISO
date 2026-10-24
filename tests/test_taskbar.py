"""The taskbar preview buttons, on a real (small) window: Windows takes them, a click reaches us,
and the window gets its own message function back."""
import ctypes
import sys
import time

import pytest

from app import taskbar

pytestmark = [pytest.mark.gui, pytest.mark.skipif(sys.platform != "win32", reason="Windows only")]


def _has_taskbar():
    """The thumbnail buttons live on the taskbar: a desktop of its own (tools/run_hidden.py) has none."""
    return bool(sys.platform == "win32" and ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None))


needs_taskbar = pytest.mark.skipif(not _has_taskbar(), reason="no taskbar on this desktop")


@pytest.fixture
def window():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    root.title("DISO test")
    root.geometry("200x80+50+50")
    root.update()
    yield root
    root.destroy()


def frame(root):
    return ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()


def test_the_icons_are_drawn(tmp_path):
    icons = taskbar.draw_icons(str(tmp_path))
    assert set(icons) == {"previous", "play", "pause", "next"}
    from PIL import Image
    for path in icons.values():
        with Image.open(path) as im:
            assert im.format == "ICO"


@needs_taskbar
def test_buttons_are_added_and_a_click_comes_through(window, tmp_path):
    bar = taskbar.ThumbBar()
    hwnd = frame(window)
    assert bar.attach(hwnd, str(tmp_path))
    end = time.time() + 5
    while time.time() < end and not bar.added:                 # Windows may still be making the taskbar button
        window.update()
        bar._add()
        time.sleep(0.1)
    assert bar.added
    for bid, name in ((3, "next"), (1, "previous"), (2, "toggle")):
        ctypes.windll.user32.SendMessageW(hwnd, taskbar.WM_COMMAND, (taskbar.THBN_CLICKED << 16) | bid, 0)
        assert bar.pressed.get_nowait() == name
    bar.set_playing(True)
    assert bar.playing
    bar.detach()
    assert not bar.active
    ctypes.windll.user32.SendMessageW(hwnd, taskbar.WM_COMMAND, (taskbar.THBN_CLICKED << 16) | 3, 0)
    window.update()
    assert bar.pressed.empty()                                  # detached: the window is its old self again


@needs_taskbar
def test_other_messages_still_reach_the_window(window, tmp_path):
    bar = taskbar.ThumbBar()
    assert bar.attach(frame(window), str(tmp_path))
    try:
        window.title("Başka başlık")                            # handled by Tk's own message function
        window.update()
        buf = ctypes.create_unicode_buffer(100)
        ctypes.windll.user32.GetWindowTextW(frame(window), buf, 100)
        assert buf.value == "Başka başlık"
    finally:
        bar.detach()
