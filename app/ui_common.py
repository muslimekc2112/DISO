"""Small helpers shared by the download window and the music window."""
import time


def fit_geometry(win, width, height, margin=(40, 120)):
    """Give a window its size, but never larger than the screen (room is left for the title bar
    and the taskbar). Sizes are in the app's own units: customtkinter multiplies them by the
    display scaling, so a 125 % / 150 % laptop screen is taken into account. Returns (w, h)."""
    try:
        scale = float(win._get_window_scaling())
    except Exception:
        scale = 1.0
    max_w = int(win.winfo_screenwidth() / scale) - margin[0]
    max_h = int(win.winfo_screenheight() / scale) - margin[1]
    w, h = max(360, min(width, max_w)), max(360, min(height, max_h))
    win.geometry(f"{w}x{h}")
    return w, h


def set_if_changed(widget, **options):
    """widget.configure(...) for the options whose value really differs. customtkinter redraws a
    widget on every configure, even with the same value; doing that several times a second makes
    the text flicker."""
    from . import i18n
    changed = {}
    for key, value in options.items():
        try:
            if widget.cget(key) in (value, i18n.tr(value) if key == "text" else value):
                continue
        except Exception:  # noqa: BLE001 - an option cget does not know: just set it
            pass
        changed[key] = value
    if changed:
        widget.configure(**changed)


XFT_COLOR_OK = 20305          # libXft 2.3.5: the first that can draw colour (emoji) glyphs
REJECT_COLOR_FONTS = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <selectfont><rejectfont><pattern><patelt name="color"><bool>true</bool></patelt></pattern></rejectfont></selectfont>
</fontconfig>
"""


def guard_color_emoji(folder=None, version=None, environ=None) -> bool:
    """Linux: Tk draws its text with libXft, and a libXft older than 2.3.5 makes the whole program die
    ("BadLength") the moment a colour emoji font (Noto Color Emoji: there by default on Ubuntu 22.04,
    Mint 21 ...) is asked for a glyph like 🎵. Then fontconfig is told to leave colour fonts out (the
    emoji come from the plain fonts or stay empty). Must run before the first window. True if it did."""
    import os
    import sys
    environ = os.environ if environ is None else environ
    if version is None:
        if not sys.platform.startswith("linux") or environ.get("FONTCONFIG_FILE"):
            return False
        try:
            import ctypes

            import _tkinter  # noqa: F401 - loads Tk and with it the libXft it uses
            version = ctypes.CDLL("libXft.so.2").XftGetVersion()
        except Exception:  # noqa: BLE001 - no libXft (not X11): nothing to guard
            return False
    if version >= XFT_COLOR_OK:
        return False
    if folder is None:
        from .utils import app_data_dir
        folder = app_data_dir()
    path = os.path.join(folder, "fonts-no-color.conf")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(REJECT_COLOR_FONTS)
    except OSError:
        return False
    environ["FONTCONFIG_FILE"] = path
    return True


SCROLL_FRAME_MS = 16          # wheel steps that arrive within this time are scrolled together


def repaint(canvas):
    """Paint the canvas and every row on it again, now (Windows kept the old pictures of the rows that
    had moved, when the tabs were scrolled up and down: update_idletasks alone does not repaint them)."""
    canvas.update_idletasks()
    try:
        import ctypes
        # RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW
        ctypes.windll.user32.RedrawWindow(canvas.winfo_id(), None, None, 0x1 | 0x4 | 0x80 | 0x100)
    except Exception:  # noqa: BLE001 - only a repaint
        pass


def install_smooth_scrolling():
    """Fast wheel scrolling in a customtkinter scrollable frame (the settings ...) left copies of rows
    on the screen: every wheel step moved all the rows at once, and when the steps came faster than
    Windows painted, the old pictures stayed behind. The steps are now added up and scrolled once per
    frame, followed by a full repaint. Must run before the first scrollable frame is made."""
    import sys
    import tkinter as tk

    import customtkinter as ctk
    cls = ctk.CTkScrollableFrame
    if not sys.platform.startswith("win") or getattr(cls, "_smooth_scrolling", False):
        return
    cls._smooth_scrolling = True
    original = cls._mouse_wheel_all

    def flush(frame):
        frame._wheel_after = None
        units, frame._wheel_units = getattr(frame, "_wheel_units", 0), 0
        if not units:
            return
        try:
            canvas = frame._parent_canvas
            canvas.yview("scroll", units, "units")
            repaint(canvas)
        except tk.TclError:                                    # the window was closed meanwhile
            pass

    def drag(frame, *args):
        """The scroll bar dragged: the same full repaint (there too, rows were left behind)."""
        try:
            frame._parent_canvas.yview(*args)
            repaint(frame._parent_canvas)
        except tk.TclError:
            pass

    original_init = cls.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            self._scrollbar.configure(command=lambda *a: drag(self, *a))
        except (AttributeError, tk.TclError, ValueError):
            pass

    cls.__init__ = init

    def wheel(self, event):
        if self._shift_pressed or not self._check_if_valid_scroll(event.widget):
            return original(self, event)
        try:
            if self._parent_canvas.yview() == (0.0, 1.0):      # everything is visible: nothing to scroll
                return None
        except tk.TclError:
            return None
        self._wheel_units = getattr(self, "_wheel_units", 0) - int(event.delta / 6)
        if getattr(self, "_wheel_after", None) is None:
            self._wheel_after = self.after(SCROLL_FRAME_MS, lambda: flush(self))
        return None

    cls._mouse_wheel_all = wheel


def _stretched(widget) -> bool:
    """True when the widget fills the width of its place (grid sticky "ew", pack fill x)."""
    try:
        manager = widget.winfo_manager()
        if manager == "grid":
            sticky = widget.grid_info().get("sticky", "")
            return "e" in sticky and "w" in sticky
        if manager == "pack":
            return widget.pack_info().get("fill") in ("x", "both")
    except Exception:  # noqa: BLE001
        pass
    return False


def fit_wrap(label):
    """A label that fills its row wraps its lines at the width the row really has, never more than the
    wraplength it was made with. Without this a narrower window cut the end of long texts off."""
    try:
        width = label.winfo_width()
        if width <= 1 or not _stretched(label):
            return
        room = int(width / float(label._get_widget_scaling())) - 6
        current = label.cget("wraplength") or 0
        if width < label._label.winfo_reqwidth() - 2:            # cut off: wrap shorter
            wrap = max(60, min(label._wrap_max, room))
        elif room > current + 2 and current < label._wrap_max:   # room again: longer lines, up to the original
            wrap = min(label._wrap_max, room)
        else:
            return                                               # (never shrinks a label that fits: no creeping)
        if abs(wrap - current) > 2:
            label.configure(wraplength=wrap)
    except Exception:  # noqa: BLE001 - only looks
        pass


RESIZE_SETTLE = 90       # ms without a size change: the edge stopped; the scrolling content takes the width
WRAP_AFTER = 120         # ms after the last size change: the long texts wrap to their new width


def install_light_resizing():
    """Dragging the edge of a window with a lot in it (the settings) ran at 5 pictures a second: every pixel
    made customtkinter redraw each scroll bar whole, colours included, and then force every waiting layout
    at once (update_idletasks), and made the scrolling content take the new width, which laid out all its
    rows again (some 120 texts and buttons redrawn: 160 ms each time). Now a scroll bar only moves its handle (and
    only when it really moved; its full redraw, update_idletasks included, stays as it was: skipping that
    crashed Tk in some orders of events), and the content takes the new width once the edge stops moving
    (RESIZE_SETTLE): the edge moves smoothly, the rows settle once."""
    import tkinter as tk

    import customtkinter as ctk
    bar = ctk.CTkScrollbar
    if getattr(bar, "_light", False):
        return
    bar._light = True
    def set(self, start_value, end_value):
        start, end = float(start_value), float(end_value)
        if (start, end) == (self._start_value, self._end_value):
            return
        self._start_value, self._end_value = start, end
        lo, hi = self._get_scrollbar_values_for_minimum_pixel_size()
        recolour = self._draw_engine.draw_rounded_scrollbar(
            self._apply_widget_scaling(self._current_width), self._apply_widget_scaling(self._current_height),
            self._apply_widget_scaling(self._corner_radius), self._apply_widget_scaling(self._border_spacing),
            lo, hi, self._orientation)
        if recolour:                                       # new parts were made: they need their colours
            self._draw()

    bar.set = set

    frame = ctk.CTkScrollableFrame
    original_fit = frame._fit_frame_dimensions_to_canvas

    def _fit_frame_dimensions_to_canvas(self, event=None):
        job = getattr(self, "_fit_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            self._fit_job = None
        if not getattr(self, "_fitted_at", 0.0):          # its first size: at once (nothing is on the screen yet)
            self._fitted_at = time.monotonic()
            original_fit(self, event)
        else:                                              # the edge is moving: the rows wait until it stops,
            _hold_painting(self, True)                     # and are not painted again and again meanwhile
            self._fit_job = self.after(RESIZE_SETTLE, lambda: _fit_now(self))

    def _fit_now(self):
        self._fit_job = None
        self._fitted_at = time.monotonic()
        _hold_painting(self, False)
        try:
            original_fit(self, None)
        except tk.TclError:
            pass
        repaint(self._parent_canvas)

    frame._fit_frame_dimensions_to_canvas = _fit_frame_dimensions_to_canvas
    # the frame bound the old function by name when it was made: frames made from now on use the new one
    original_init = frame.__init__

    def __init__(self, *args, **kw):
        original_init(self, *args, **kw)
        self._parent_canvas.bind("<Configure>", self._fit_frame_dimensions_to_canvas)
        self._parent_canvas.bind("<Destroy>", lambda e, frame=self: _let_go(frame), "+")

    frame.__init__ = __init__

    # A window's own size handler was bound to the window, and Tk runs a window's bindings for every widget in
    # it too: one size change of the settings window called it some 200 times (each one a Python event and two
    # size questions). It now hears only the window itself.
    for cls in (ctk.CTk, ctk.CTkToplevel):
        cls.__init__ = _own_configure_only(cls.__init__)


def _own_configure_only(original_init):
    import tkinter as tk

    def __init__(self, *args, **kw):
        original_init(self, *args, **kw)
        try:
            tk.Misc.unbind(self, "<Configure>")
            tag = f"own-size-{id(self)}"
            self.bindtags((tag, *self.bindtags()))
            self.bind_class(tag, "<Configure>", self._update_dimensions_event)
        except tk.TclError:
            pass
    return __init__


def _let_go(frame):
    """The window closes (maybe in the middle of a drag): its picture and its waiting job go now, here. Left to
    Python, the picture was freed later on whatever thread ran then (the music's, the downloads'), and a Tk image
    deleted outside Tk's own thread brought the whole program down."""
    job = getattr(frame, "_fit_job", None)
    if job is not None:
        try:
            frame.after_cancel(job)
        except Exception:  # noqa: BLE001
            pass
        frame._fit_job = None
    frame._painting_held = False
    frame.__dict__.pop("_still", None)                     # the last reference: it is freed right here, right now


def _hold_painting(frame, hold):
    """While a window's edge is dragged, the rows of its scrolling content stand still (they take the new width
    when it stops), yet Windows painted their hundreds of little windows again at every pixel: that was what
    made the drag slow. Meanwhile a picture of them stands in their place (the same pixels, one image to paint)."""
    import sys
    import tkinter as tk
    if bool(getattr(frame, "_painting_held", False)) == hold or not sys.platform.startswith("win"):
        return
    canvas = frame._parent_canvas
    try:
        if hold:
            from PIL import ImageGrab, ImageTk
            x, y, w, h = canvas.winfo_rootx(), canvas.winfo_rooty(), canvas.winfo_width(), canvas.winfo_height()
            if w < 20 or h < 20 or not canvas.winfo_viewable():
                return
            shot = ImageTk.PhotoImage(ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True), master=canvas)
            frame._still = shot                            # (kept: a Tk image nobody holds disappears)
            canvas.create_image(canvas.canvasx(0), canvas.canvasy(0), image=shot, anchor="nw", tags="still")
            canvas.itemconfigure(frame._create_window_id, state="hidden")
        else:
            canvas.itemconfigure(frame._create_window_id, state="normal")
            canvas.delete("still")
            frame._still = None
        frame._painting_held = hold
    except (tk.TclError, OSError, ValueError):
        frame._painting_held = False
        try:
            canvas.itemconfigure(frame._create_window_id, state="normal")
            canvas.delete("still")
        except tk.TclError:
            pass


def _wrap_later(label):
    """fit_wrap once the size stops changing (every change of a wrap lays the window out again)."""
    job = getattr(label, "_wrap_job", None)
    if job is not None:
        try:
            label.after_cancel(job)
        except Exception:  # noqa: BLE001
            pass
    try:
        label._wrap_job = label.after(WRAP_AFTER, lambda: (setattr(label, "_wrap_job", None), fit_wrap(label)))
    except Exception:  # noqa: BLE001 - closed meanwhile
        pass


def install_wrap_to_fit():
    """Every CTkLabel made with a wraplength follows the width of its row (see fit_wrap)."""
    import tkinter as tk

    import customtkinter as ctk
    cls = ctk.CTkLabel
    if getattr(cls, "_wrap_to_fit", False):
        return
    cls._wrap_to_fit = True
    original = cls.__init__

    def __init__(self, *args, **kw):
        original(self, *args, **kw)
        if kw.get("wraplength"):
            self._wrap_max = kw["wraplength"]
            tk.Misc.bind(self, "<Configure>", lambda e, label=self: _wrap_later(label), "+")

    cls.__init__ = __init__


def logo_image(px):
    """The program's icon as a CTkImage of px x px (a new one each time: a CTkImage keeps pictures that belong
    to the window it was first shown in, so it must not be shared between windows). None if the file is missing."""
    import os

    import customtkinter as ctk
    from PIL import Image

    from .utils import resource_path
    try:
        img = Image.open(resource_path(os.path.join("assets", "icon.png"))).convert("RGBA")
    except Exception:  # noqa: BLE001
        return None
    return ctk.CTkImage(light_image=img, dark_image=img, size=(px, px))


def bring_new_window_forward(win):
    """A window that was just opened comes in front (on Windows a customtkinter window is often made behind
    the one it was opened from, and had to be asked for a second time). Windows that stay hidden are left alone."""
    try:
        if not win.winfo_exists() or win.state() != "normal":
            return False
        win.lift()
        if not win.attributes("-topmost"):                # (one that stays on top by itself is left as it is)
            win.attributes("-topmost", True)              # over its parent for a moment, then like any window
            win.after(200, lambda: win.winfo_exists() and win.attributes("-topmost", False))
        win.focus_set()
        return True
    except Exception:  # noqa: BLE001 - only where it shows
        return False


_forward_installed = False


def install_bring_forward():
    """Every customtkinter window opened from now on comes in front by itself (once per program)."""
    global _forward_installed
    if _forward_installed:
        return
    _forward_installed = True
    import os

    import customtkinter as ctk
    orig = ctk.CTkToplevel.__init__

    def __init__(self, *args, **kw):
        orig(self, *args, **kw)
        if not os.environ.get("PYTEST_CURRENT_TEST"):     # the tests' windows must not jump over other programs
            self.after(60, lambda: bring_new_window_forward(self))
            self.after(260, lambda: bring_new_window_forward(self))    # after customtkinter's own late icon step

    ctk.CTkToplevel.__init__ = __init__


# ------------------------------------------------------------------------------ ✨ soft transitions
FRAME_MS = 15                 # ~60 frames a second
OPEN_MS = 190                 # a window fades in
CLOSE_MS = 130                # ... and out
SWITCH_MS = 210               # the download window and the music player cross-fade


def animations_on() -> bool:
    """Off in the tests (their windows are looked at at once), unless a test turns them on (DISO_ANIMATE=1)."""
    import os
    return os.environ.get("DISO_ANIMATE") == "1" or not os.environ.get("PYTEST_CURRENT_TEST")


def ease_out(t: float) -> float:
    """Fast at first, softly to the end (cubic)."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def fade(win, start, end, ms, done=None, curve=ease_out, clock=None):
    """Change the window's opacity from `start` to `end` over `ms` (frames by the clock, so a busy moment skips
    a frame instead of making it slower). done() is called at the end (also when it cannot fade)."""
    import time
    clock = clock or time.perf_counter
    began = []                                               # the clock starts at the first frame shown
    token = object()
    win._fade_token = token                                  # a newer fade of this window stops this one
    _fine_timer(True)

    def frame():
        try:
            if getattr(win, "_fade_token", None) is not token or not win.winfo_exists():
                _fine_timer(False)
                return
            if not began:
                began.append(clock())
            t = min(1.0, (clock() - began[0]) * 1000 / max(1, ms))
            win.attributes("-alpha", start + (end - start) * curve(t))
            if t < 1.0:
                win.after(FRAME_MS, frame)
                return
        except Exception:  # noqa: BLE001 - a window that went away
            pass
        _fine_timer(False)
        if getattr(win, "_fade_token", None) is token:
            win._fade_token = None
        if done:
            done()
    try:
        win.attributes("-alpha", start)
    except Exception:  # noqa: BLE001
        _fine_timer(False)
        if done:
            done()
        return
    frame()


_fine = [0]


def _fine_timer(on):
    """While something moves, Windows' timer ticks every 1 ms instead of every 15.6 ms: the frames come evenly.
    Counted, so overlapping fades end it only once the last one is over."""
    import sys
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        if on:
            _fine[0] += 1
            if _fine[0] == 1:
                ctypes.windll.winmm.timeBeginPeriod(1)
        elif _fine[0] > 0:
            _fine[0] -= 1
            if _fine[0] == 0:
                ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:  # noqa: BLE001 - frames a little less even
        pass


def fade_in(win, ms=OPEN_MS):
    if not animations_on():
        return False
    try:
        if win.state() != "normal":
            win.attributes("-alpha", 1.0)                     # stays hidden: whole again for when it is shown
            return False
    except Exception:  # noqa: BLE001
        return False
    fade(win, 0.0, 1.0, ms)
    return True


def fade_out_and(win, then, ms=CLOSE_MS):
    """Fade the window out, then then() (destroy / withdraw); at once when animations are off."""
    if not animations_on():
        then()
        return

    def finish():
        try:
            then()
        finally:
            try:
                if win.winfo_exists():
                    win.attributes("-alpha", 1.0)             # (a withdrawn window is whole when it comes back)
            except Exception:  # noqa: BLE001
                pass
    try:
        if win.state() != "normal":
            finish()
            return
    except Exception:  # noqa: BLE001
        finish()
        return
    fade(win, float(win.attributes("-alpha") or 1.0), 0.0, ms, done=finish, curve=ease_in_out)


def cross_fade(old, new, place=True, ms=SWITCH_MS):
    """`new` takes the place (and size) of `old` and fades in over it; `old` goes once it is covered."""
    try:
        if place and old.winfo_viewable():
            if old.state() == "zoomed":
                new.state("zoomed")
            else:
                new.geometry(old.geometry())                  # (customtkinter's own units: the screen's scale stays right)
    except Exception:  # noqa: BLE001
        pass
    if not animations_on():
        new.deiconify()
        new.lift()
        new.update_idletasks()
        old.withdraw()
        return
    new._shown_softly = True                                  # (its own first fade must not cut this one off)
    try:
        new.attributes("-alpha", 0.0)
    except Exception:  # noqa: BLE001
        pass
    new.deiconify()
    new.lift()
    try:
        new.update_idletasks()                                # laid out and drawn (unseen) before it fades in:
        new.update()                                          # nothing pops up, no frame of the fade is skipped
    except Exception:  # noqa: BLE001
        pass

    def covered():
        try:
            old.withdraw()
            old.attributes("-alpha", 1.0)
            new.attributes("-alpha", 1.0)
        except Exception:  # noqa: BLE001
            pass
    fade(new, 0.0, 1.0, ms, done=covered, curve=ease_in_out)


_fade_installed = False


def install_soft_windows():
    """Every customtkinter window opened from now on fades in, and fades out when its × is pressed."""
    global _fade_installed
    if _fade_installed:
        return
    _fade_installed = True
    import customtkinter as ctk
    orig = ctk.CTkToplevel.__init__

    def __init__(self, *args, **kw):
        orig(self, *args, **kw)
        if not animations_on():
            return
        try:
            self.attributes("-alpha", 0.0)                    # unseen until customtkinter has finished drawing it
        except Exception:  # noqa: BLE001
            return
        self.after(40, lambda: _first_fade(self))
        # the × fades it out first (a window that sets its own close action keeps it)
        self.protocol("WM_DELETE_WINDOW", lambda: fade_out_and(self, self.destroy))

    ctk.CTkToplevel.__init__ = __init__


def _first_fade(win):
    """The fade a new window gets when it first shows (not when it was already shown softly, e.g. cross_fade)."""
    if getattr(win, "_shown_softly", False) or getattr(win, "_fade_token", None) is not None:
        return
    win._shown_softly = True
    if not fade_in(win):
        _whole(win)


def _whole(win):
    """A window that did not fade in (it stays hidden for now) must not stay invisible."""
    try:
        if win.winfo_exists() and getattr(win, "_fade_token", None) is None:
            win.attributes("-alpha", 1.0)
    except Exception:  # noqa: BLE001
        pass


def fill_monitor(win) -> bool:
    """Make a full-screen window cover its whole monitor. Tk knows the screen only in scaled units (a 1920×1080
    screen at 125 % is 1536×864 to it), so its "-fullscreen" alone covered just the top-left part of it."""
    import sys
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]
        hwnd = int(win.wm_frame(), 16)
        monitor = ctypes.windll.user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)     # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        r = info.rcMonitor
        # HWND_TOP, SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE
        return bool(ctypes.windll.user32.SetWindowPos(wintypes.HWND(hwnd), 0, r.left, r.top, r.right - r.left,
                                                      r.bottom - r.top, 0x0004 | 0x0020 | 0x0010))
    except Exception:  # noqa: BLE001 - Tk's own full screen stays
        return False


def no_window_animation(win):
    """Windows' open / close animation off for this window: switching between the download and the music
    window then shows the other one at once, not a shrinking and a growing window for a moment."""
    import sys
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        win.update_idletasks()
        hwnd = int(win.wm_frame(), 16)
        on = ctypes.c_int(1)
        return ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 3, ctypes.byref(on), ctypes.sizeof(on)) == 0
    except Exception:  # noqa: BLE001 - only looks: the animation stays
        return False


def set_window_icon(win):
    """The DISO icon in the window's title bar (and on the taskbar). Without this every customtkinter
    window shows customtkinter's own blue icon; once iconbitmap was called it no longer puts that back."""
    import os

    from .utils import resource_path
    ico = resource_path(os.path.join("assets", "icon.ico"))
    if os.name == "nt" and os.path.exists(ico):
        try:
            win.iconbitmap(ico)
        except Exception:  # noqa: BLE001 - only looks
            pass
    elif os.name != "nt":                 # macOS / Linux: a picture (kept on the window, Tk does not keep it)
        png = resource_path(os.path.join("assets", "icon.png"))
        try:
            import tkinter
            win._diso_icon = tkinter.PhotoImage(master=win, file=png)
            win.iconphoto(False, win._diso_icon)
            win._iconbitmap_method_called = True        # customtkinter's mark: "the window has its own icon"
        except Exception:  # noqa: BLE001 - only looks
            pass


def retint(frame, colour):
    """A frame takes a new fill colour (a "#rrggbb" or a (light, dark) pair) without customtkinter's full redraw
    of everything below it (that is 20+ ms: the colour of a music-following background could not move at more than
    a few frames a second). Only the colours are set on the canvases; `frame.configure(fg_color=...)` later makes
    everything exact again."""
    frame._fg_color = colour
    shade = frame._apply_appearance_mode

    def paint(canvas, fill):
        canvas.itemconfig("inner_parts", fill=shade(fill), outline=shade(fill))

    paint(frame._canvas, colour)

    def down(parent):
        for child in parent.winfo_children():
            if not hasattr(child, "_bg_color") or not hasattr(child, "_canvas"):
                continue
            child._bg_color = colour
            child._canvas.configure(bg=shade(colour))
            if child._fg_color == "transparent":
                paint(child._canvas, colour)
                label = getattr(child, "_label", None)
                if label is not None:
                    label.configure(bg=shade(colour))
                down(child)

    down(frame)
