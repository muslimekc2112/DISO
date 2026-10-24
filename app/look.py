"""How the program looks. "Yeni" is our own palette (warm paper / deep ink with an orange accent),
"Klasik" is customtkinter's stock blue theme, "Nostalji" the grey Windows of the 2000s (and the download
window laid out like the download managers of that time: see app/classic_ui.py). The look is applied once,
before any window exists, by recoloring customtkinter's theme tables; no widget has to know about it."""
import customtkinter as ctk

STYLES = ["Standart", "Yeni", "Klasik", "Nostalji"]
DEFAULT_STYLE = "Standart"
LABELS = {"Standart": "Standart (Önerilen)"}     # how a style is called in the menus

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
BUTTON = ("#F0E6F4", "#2A1C35")             # "Standart": a button's calm face

# 🎨 the accent colour ("Yeni" and "Standart"): the whole palette above is turned to its hue, then made readable
# again where a hue is lighter than pink (text on a button, white on a selected tab)
ACCENTS = {"Pembe": None, "Mavi": 215, "Yeşil": 150, "Turuncu": 24, "Mor": 262, "Kırmızı": 352}
DEFAULT_ACCENT = "Pembe"
PALETTE = ("WINDOW", "CARD", "CARD_HIGH", "INPUT", "BORDER", "TRACK", "TEXT", "ACCENT", "ACCENT_HOVER", "ACCENT_TEXT",
           "ACCENT_SOFT", "ACCENT_DEEP", "SEGMENT_TRACK", "BUTTON", "STATE_IDLE")
STATE_DONE = "#2F9E63"
STATE_ERROR = "#CF4B45"
STATE_PAUSED = "#D9962B"
STATE_IDLE = ("#AD9CB6", "#52405F")

# "Nostalji": the grey Windows of the 2000s, light; or the same in dark grey ("Koyu" theme). One set of
# colours at a time: the set is chosen before the first window exists (a change needs a new start).
N_LIGHT = {
    "N_FACE": "#F0F0F0",          # window and dialog background
    "N_FIELD": "#FFFFFF",         # text boxes, lists
    "N_BUTTON": "#E1E1E1",
    "N_HOVER": "#E5F1FB",         # a button under the mouse (light blue)
    "N_BORDER": "#ADADAD",        # button frame
    "N_FRAME": "#828790",         # list and text box frame
    "N_LINE": "#D5DFE5",          # group box line
    "N_TEXT": "#000000",
    "N_GREY_TEXT": "#6D6D6D",     # hints
    "N_DISABLED": "#A0A0A0",
    "N_SELECT": "#3399FF",        # selected row
    "N_GREEN": "#06B025",         # progress
    "N_BLUE": "#0078D7",
    "N_HIGH": "#F7F7F7",          # a frame's top part, a heading
    "N_HEADER": "#E3E3E3",        # the "Kategoriler" header
    "N_MARK": "#333333",          # check box frame
    "N_PLACEHOLDER": "#8C8C8C",
    "N_TRACK": "#E6E6E6",         # empty part of a progress bar
    "N_TRACK_EDGE": "#BCBCBC",
    "N_SLIDER": "#D6D6D6",
    "N_KNOB": "#5A5A5A",
    "N_SWITCH": "#C4C4C4",
    "N_SCROLL": "#C2C2C2",
    "N_SCROLL_HOVER": "#A8A8A8",
    "N_MENU_HOVER": "#CCE8FF",
    "N_ERROR_TEXT": "#C00000",
    "N_DONE_TEXT": "#1F1F1F",
}
N_DARK = dict(N_LIGHT, **{
    "N_FACE": "#2B2B2B", "N_FIELD": "#1E1E1E", "N_BUTTON": "#3A3A3A", "N_HOVER": "#2F4A63",
    "N_BORDER": "#5C5C5C", "N_FRAME": "#6A6A6A", "N_LINE": "#4A4A4A", "N_TEXT": "#E8E8E8",
    "N_GREY_TEXT": "#A8A8A8", "N_DISABLED": "#707070", "N_SELECT": "#2E6FB8", "N_GREEN": "#1DB43A",
    "N_BLUE": "#3C9BFF", "N_HIGH": "#333333", "N_HEADER": "#383838", "N_MARK": "#B0B0B0",
    "N_PLACEHOLDER": "#8A8A8A", "N_TRACK": "#252525", "N_TRACK_EDGE": "#555555", "N_SLIDER": "#4A4A4A",
    "N_KNOB": "#D0D0D0", "N_SWITCH": "#555555", "N_SCROLL": "#4E4E4E", "N_SCROLL_HOVER": "#666666",
    "N_MENU_HOVER": "#2F4A63", "N_ERROR_TEXT": "#FF7070", "N_DONE_TEXT": "#D8D8D8",
})
globals().update(N_LIGHT)

_BASE = {name: globals()[name] for name in PALETTE}       # the pink palette as drawn
_shift = 0.0                  # degrees the palette's hue is turned by (0: pink)
_accent = DEFAULT_ACCENT
_active = "Klasik"
_dark = False                 # "Nostalji" in dark grey
_FONT = "Segoe UI"
_N_FONT = "Tahoma"


def _rgb(hex_colour):
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{round(max(0, min(1, v)) * 255):02X}" for v in rgb)


def _turn(hex_colour, degrees):
    import colorsys
    h, l, s = colorsys.rgb_to_hls(*_rgb(hex_colour))
    return _hex(colorsys.hls_to_rgb((h + degrees / 360) % 1, l, s))


def _t(pair):
    """A (light, dark) colour pair of the pink palette, in the chosen accent's hue."""
    return tuple(_turn(c, _shift) for c in pair) if _shift else pair


def luminance(hex_colour):
    def lin(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in _rgb(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _readable(colour, text, need=4.6):
    """colour made darker (or lighter, under dark text) until text on it reads well."""
    import colorsys
    h, l, s = colorsys.rgb_to_hls(*_rgb(colour))
    lighter = luminance(text) < 0.2
    for _ in range(80):
        if contrast(colour, text) >= need:
            break
        l = min(0.97, l + 0.01) if lighter else max(0.03, l - 0.01)
        colour = _hex(colorsys.hls_to_rgb(h, l, s))
    return colour


def use_accent(name):
    """Turn the palette to an accent colour (a name of ACCENTS; an unknown one is pink). Returns the name used."""
    global _shift, _accent
    import colorsys
    name = name if name in ACCENTS else DEFAULT_ACCENT
    hue = ACCENTS[name]
    base_hue = colorsys.rgb_to_hls(*_rgb(_BASE["ACCENT"][0]))[0] * 360
    _accent, _shift = name, (0.0 if hue is None else hue - base_hue)
    g = globals()
    for key, pair in _BASE.items():
        g[key] = _t(pair)
    if _shift:
        white = "#FFFFFF"
        g["ACCENT"] = (_readable(g["ACCENT"][0], white), _readable(g["ACCENT"][1], g["ACCENT_TEXT"][1]))
        g["ACCENT_HOVER"] = (_readable(g["ACCENT_HOVER"][0], white, 4.0), g["ACCENT_HOVER"][1])
        g["ACCENT_DEEP"] = tuple(_readable(c, white) for c in g["ACCENT_DEEP"])
        g["SEGMENT_TRACK"] = tuple(_readable(c, white) for c in g["SEGMENT_TRACK"])
    return name


def accent_name() -> str:
    return _accent


def is_new() -> bool:
    """Our own palette: "Yeni", and "Standart" (the same with colourful pictures on the buttons)."""
    return _active in ("Yeni", "Standart")


def is_standard() -> bool:
    return _active == "Standart"


def label(style) -> str:
    return LABELS.get(style, style)


def style_of(label_text) -> str:
    """The style a menu's text stands for."""
    return next((s for s, text in LABELS.items() if text == label_text), label_text)


def is_nostalgia() -> bool:
    return _active == "Nostalji"


def is_dark_nostalgia() -> bool:
    return is_nostalgia() and _dark


def appearance(theme_mode):
    """The customtkinter appearance mode to use: "Nostalji" is light or dark as chosen when it started (it
    cannot change while it runs), the others follow the setting."""
    if is_nostalgia():
        return "dark" if _dark else "light"
    return theme_mode


def wants_dark(theme) -> bool:
    """"Koyu", "Açık" or "Sistem" (Windows' own choice of apps' colour) -> dark?"""
    if theme in ("Koyu", "dark"):
        return True
    if theme in ("Sistem", "system"):
        try:
            import darkdetect
            return bool(darkdetect.isDark())
        except Exception:  # noqa: BLE001 - not known: light, like the Windows it remembers
            return False
    return False


def grey_text():
    """Colour of the small grey hints."""
    return N_GREY_TEXT if is_nostalgia() else "gray"


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


def apply(style=DEFAULT_STYLE, theme="Açık", accent=None) -> str:
    """Load the base theme, then recolor it for the chosen style. Returns the style in use. `theme` (the
    "Görünüm" setting) only matters to "Nostalji", which takes its light or dark colours from it here."""
    global _active, _dark
    ctk.ThemeManager.load_theme("blue")                    # start from the stock tables every time
    use_accent(accent if style in ("Yeni", "Standart") and accent else DEFAULT_ACCENT)
    _dark = style == "Nostalji" and wants_dark(theme)
    globals().update(N_DARK if _dark else N_LIGHT)
    if style == "Nostalji":
        _active = "Nostalji"
        _apply_nostalgia(ctk.ThemeManager.theme)
        return _active
    from . import icon_buttons
    icon_buttons.active = style == "Standart"
    if icon_buttons.active:
        icon_buttons.install()
    if style not in ("Yeni", "Standart"):
        _active = "Klasik"
        return _active
    _active = style
    t = ctk.ThemeManager.theme
    _set(t, "CTk", fg_color=WINDOW)
    _set(t, "CTkToplevel", fg_color=WINDOW)
    _set(t, "CTkFrame", corner_radius=14, fg_color=CARD, top_fg_color=CARD_HIGH, border_color=BORDER)
    _set(t, "CTkButton", corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=BORDER,
         text_color=ACCENT_TEXT, text_color_disabled=_t(("#C0B2C8", "#6A5878")))
    _set(t, "CTkLabel", text_color=TEXT)
    _set(t, "CTkEntry", corner_radius=10, border_width=1, fg_color=INPUT, border_color=BORDER,
         text_color=TEXT, placeholder_text_color=_t(("#9C8AA6", "#7A6A88")))
    _set(t, "CTkCheckBox", corner_radius=6, border_width=2, fg_color=ACCENT, hover_color=ACCENT_HOVER,
         border_color=_t(("#8F7C99", "#5A4668")), checkmark_color=ACCENT_TEXT, text_color=TEXT)
    _set(t, "CTkSwitch", fg_color=_t(("#D3C6DA", "#3B2A47")), progress_color=ACCENT,
         button_color=("#FFFFFF", "#F2F3F8"), button_hover_color=("#F4F4F4", "#FFFFFF"), text_color=TEXT)
    _set(t, "CTkRadioButton", fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=_t(("#8F7C99", "#5A4668")),
         text_color=TEXT)
    _set(t, "CTkProgressBar", fg_color=TRACK, progress_color=ACCENT)
    _set(t, "CTkSlider", fg_color=TRACK, progress_color=ACCENT, button_color=ACCENT,
         button_hover_color=ACCENT_HOVER)
    _set(t, "CTkOptionMenu", corner_radius=10, fg_color=CARD_HIGH, button_color=ACCENT,
         button_hover_color=ACCENT_HOVER, text_color=TEXT, text_color_disabled=_t(("#C0B2C8", "#6A5878")))
    _set(t, "CTkComboBox", corner_radius=10, fg_color=INPUT, border_color=BORDER, button_color=ACCENT,
         button_hover_color=ACCENT_HOVER, text_color=TEXT)
    _set(t, "CTkScrollbar", button_color=_t(("#CDBFD4", "#443255")), button_hover_color=_t(("#B3A3BC", "#5B4770")))
    _set(t, "CTkSegmentedButton", corner_radius=10, border_width=2, fg_color=SEGMENT_TRACK, selected_color=ACCENT_DEEP,
         selected_hover_color=_t(("#8E2390", "#B335AE")), unselected_color=SEGMENT_TRACK,
         unselected_hover_color=_t(("#6A5774", "#40304D")), text_color=("#FFFFFF", "#F1F2F7"))
    _set(t, "CTkTextbox", corner_radius=10, fg_color=INPUT, border_color=BORDER, text_color=TEXT)
    _set(t, "CTkScrollableFrame", label_fg_color=CARD_HIGH)
    _set(t, "DropdownMenu", fg_color=CARD, hover_color=ACCENT_SOFT, text_color=TEXT)
    if style == "Standart":       # calm buttons: the colourful pictures stand out; the accent marks the main ones
        _set(t, "CTkButton", fg_color=BUTTON, hover_color=ACCENT_SOFT, border_width=1, border_color=BORDER,
             text_color=TEXT)
    _set_font(t, _FONT)
    return _active


def _set_font(t, family, size=None):
    font = t.get("CTkFont")
    if isinstance(font, dict):                             # a flat table, or one per platform
        for table in ([font] if "family" in font else [v for v in font.values() if isinstance(v, dict)]):
            table["family"] = family
            if size:
                table["size"] = size


def _apply_nostalgia(t):
    """Grey faces, white fields, thin frames, square corners, Tahoma: the Windows of the 2000s (in dark grey
    when the dark colours are chosen)."""
    def both(colour):
        return (colour, colour)
    face, field, text = both(N_FACE), both(N_FIELD), both(N_TEXT)
    _set(t, "CTk", fg_color=face)
    _set(t, "CTkToplevel", fg_color=face)
    _set(t, "CTkFrame", corner_radius=0, border_width=0, fg_color=face, top_fg_color=both(N_HIGH),
         border_color=both(N_LINE))
    _set(t, "CTkButton", corner_radius=3, border_width=1, fg_color=both(N_BUTTON), hover_color=both(N_HOVER),
         border_color=both(N_BORDER), text_color=text, text_color_disabled=both(N_DISABLED))
    _set(t, "CTkLabel", text_color=text, text_color_disabled=both(N_DISABLED))
    _set(t, "CTkEntry", corner_radius=0, border_width=1, fg_color=field, border_color=both(N_FRAME),
         text_color=text, placeholder_text_color=both(N_PLACEHOLDER))
    _set(t, "CTkCheckBox", corner_radius=0, border_width=1, fg_color=field, hover_color=both(N_HOVER),
         border_color=both(N_MARK), checkmark_color=text, text_color=text, text_color_disabled=both(N_DISABLED))
    _set(t, "CTkSwitch", corner_radius=3, border_width=2, fg_color=both(N_SWITCH), progress_color=both(N_BLUE),
         button_color=both(N_FIELD), button_hover_color=both(N_HOVER), text_color=text)
    _set(t, "CTkRadioButton", fg_color=both(N_BLUE), hover_color=both(N_HOVER), border_color=both(N_MARK),
         text_color=text)
    _set(t, "CTkProgressBar", corner_radius=0, border_width=1, fg_color=both(N_TRACK),
         progress_color=both(N_GREEN), border_color=both(N_TRACK_EDGE))
    _set(t, "CTkSlider", corner_radius=2, button_corner_radius=2, fg_color=both(N_SLIDER),
         progress_color=both(N_BLUE), button_color=both(N_KNOB), button_hover_color=both(N_BLUE))
    _set(t, "CTkOptionMenu", corner_radius=0, fg_color=field, button_color=both(N_BUTTON),
         button_hover_color=both(N_HOVER), text_color=text, text_color_disabled=both(N_DISABLED))
    _set(t, "CTkComboBox", corner_radius=0, border_width=1, fg_color=field, border_color=both(N_FRAME),
         button_color=both(N_BUTTON), button_hover_color=both(N_HOVER), text_color=text)
    _set(t, "CTkScrollbar", corner_radius=0, button_color=both(N_SCROLL), button_hover_color=both(N_SCROLL_HOVER))
    _set(t, "CTkSegmentedButton", corner_radius=2, border_width=1, fg_color=both(N_BORDER),
         selected_color=both(N_FIELD), selected_hover_color=both(N_FIELD), unselected_color=both(N_BUTTON),
         unselected_hover_color=both(N_HOVER), text_color=text, text_color_disabled=both(N_DISABLED))
    _set(t, "CTkTextbox", corner_radius=0, border_width=1, fg_color=field, border_color=both(N_FRAME),
         text_color=text)
    _set(t, "CTkScrollableFrame", label_fg_color=both(N_HIGH))
    _set(t, "DropdownMenu", fg_color=field, hover_color=both(N_MENU_HOVER), text_color=text)
    _set_font(t, _N_FONT, 11)
