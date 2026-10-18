"""How the program looks. "Yeni" is our own palette (warm paper / deep ink with an orange accent),
"Klasik" is customtkinter's stock blue theme. The look is applied once, before any window exists,
by recoloring customtkinter's theme tables; no widget has to know about it."""
import customtkinter as ctk

STYLES = ["Yeni", "Klasik"]
DEFAULT_STYLE = "Yeni"

# every colour is (light mode, dark mode)
WINDOW = ("#F7F1F9", "#120A18")
CARD = ("#FFFFFF", "#1B1123")
CARD_HIGH = ("#F0E6F4", "#271A31")
INPUT = ("#FFFFFF", "#150D1C")
BORDER = ("#DCCCE3", "#3A2848")
TRACK = ("#E3D6EA", "#31223D")
TEXT = ("#25132C", "#F2EAF6")
ACCENT = ("#B02FAB", "#D775D5")
ACCENT_HOVER = ("#8E2390", "#E08EDF")
ACCENT_TEXT = ("#FFFFFF", "#1A0A1F")
ACCENT_SOFT = ("#F6E1F4", "#3B2342")
ACCENT_DEEP = ("#B02FAB", "#9B2A98")          # white text stays readable on it
SEGMENT_TRACK = ("#7C6A85", "#34253F")
STATE_DONE = "#2F9E63"
STATE_ERROR = "#CF4B45"
STATE_PAUSED = "#D9962B"
STATE_IDLE = ("#AD9CB6", "#52405F")

_active = "Klasik"
_FONT = "Segoe UI"


def is_new() -> bool:
    return _active == "Yeni"


def style_name() -> str:
    return _active


def entry_border():
    """The normal border colour of an entry (it is put back after a wrong value is marked red)."""
    return ctk.ThemeManager.theme["CTkEntry"]["border_color"]


def _set(theme, widget, **values):
    table = theme.get(widget)
    if table is None:
        return
    for key, value in values.items():
        if key in table:                       # a customtkinter version without the key: skip it
            table[key] = list(value) if isinstance(value, tuple) else value


def apply(style=DEFAULT_STYLE) -> str:
    """Load the base theme, then recolor it for the chosen style. Returns the style in use."""
    global _active
    ctk.ThemeManager.load_theme("blue")                    # start from the stock tables every time
    if style != "Yeni":
        _active = "Klasik"
        return _active
    _active = "Yeni"
    t = ctk.ThemeManager.theme
    _set(t, "CTk", fg_color=WINDOW)
    _set(t, "CTkToplevel", fg_color=WINDOW)
    _set(t, "CTkFrame", corner_radius=14, fg_color=CARD, top_fg_color=CARD_HIGH, border_color=BORDER)
    _set(t, "CTkButton", corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=BORDER,
         text_color=ACCENT_TEXT, text_color_disabled=("#C0B2C8", "#6A5878"))
    _set(t, "CTkLabel", text_color=TEXT)
    _set(t, "CTkEntry", corner_radius=10, border_width=1, fg_color=INPUT, border_color=BORDER,
         text_color=TEXT, placeholder_text_color=("#9C8AA6", "#7A6A88"))
    _set(t, "CTkCheckBox", corner_radius=6, border_width=2, fg_color=ACCENT, hover_color=ACCENT_HOVER,
         border_color=("#8F7C99", "#5A4668"), checkmark_color=ACCENT_TEXT, text_color=TEXT)
    _set(t, "CTkSwitch", fg_color=("#D3C6DA", "#3B2A47"), progress_color=ACCENT,
         button_color=("#FFFFFF", "#F2F3F8"), button_hover_color=("#F4F4F4", "#FFFFFF"), text_color=TEXT)
    _set(t, "CTkRadioButton", fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=("#8F7C99", "#5A4668"),
         text_color=TEXT)
    _set(t, "CTkProgressBar", fg_color=TRACK, progress_color=ACCENT)
    _set(t, "CTkSlider", fg_color=TRACK, progress_color=ACCENT, button_color=ACCENT,
         button_hover_color=ACCENT_HOVER)
    _set(t, "CTkOptionMenu", corner_radius=10, fg_color=CARD_HIGH, button_color=ACCENT,
         button_hover_color=ACCENT_HOVER, text_color=TEXT, text_color_disabled=("#C0B2C8", "#6A5878"))
    _set(t, "CTkComboBox", corner_radius=10, fg_color=INPUT, border_color=BORDER, button_color=ACCENT,
         button_hover_color=ACCENT_HOVER, text_color=TEXT)
    _set(t, "CTkScrollbar", button_color=("#CDBFD4", "#443255"), button_hover_color=("#B3A3BC", "#5B4770"))
    _set(t, "CTkSegmentedButton", corner_radius=10, border_width=2, fg_color=SEGMENT_TRACK, selected_color=ACCENT_DEEP,
         selected_hover_color=("#8E2390", "#B335AE"), unselected_color=SEGMENT_TRACK,
         unselected_hover_color=("#6A5774", "#40304D"), text_color=("#FFFFFF", "#F1F2F7"))
    _set(t, "CTkTextbox", corner_radius=10, fg_color=INPUT, border_color=BORDER, text_color=TEXT)
    _set(t, "CTkScrollableFrame", label_fg_color=CARD_HIGH)
    _set(t, "DropdownMenu", fg_color=CARD, hover_color=ACCENT_SOFT, text_color=TEXT)
    font = t.get("CTkFont")
    if isinstance(font, dict):                             # a flat table, or one per platform
        for table in ([font] if "family" in font else [v for v in font.values() if isinstance(v, dict)]):
            table["family"] = _FONT
    return _active
