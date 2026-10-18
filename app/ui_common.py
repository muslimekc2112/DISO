"""Small helpers shared by the download window and the music window."""


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
