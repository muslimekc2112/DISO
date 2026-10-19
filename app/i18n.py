"""The interface language. The program is written in Turkish; in English every text is translated on its way
to the screen (labels, buttons, menus, window titles, message boxes ...), so the code itself never changes.

Choices (option menus, segmented buttons) keep their Turkish values inside the program: only what is shown
is English, and what the program reads back (get(), the command) is the Turkish value again.
With Turkish nothing is patched at all."""
import re

LANGUAGES = {"Türkçe": "tr", "English": "en"}
current = "tr"
_plain = {}
_templates = []
_installed = False
_PREFIX = re.compile(r"^([^\w“\"'(\[]+)(.+)$", re.S)        # an icon / symbol in front of the words


def set_language(name_or_code):
    """'Türkçe' / 'English' (or 'tr' / 'en'). Call before the first window exists."""
    global current
    code = LANGUAGES.get(name_or_code, name_or_code)
    current = code if code in LANGUAGES.values() else "tr"
    if current == "en":
        _load()
        install()


def windows_language():
    """'Türkçe' when Windows itself speaks Turkish, 'English' for every other language."""
    import sys
    if not sys.platform.startswith("win"):
        return system_language()
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:  # noqa: BLE001
        return "Türkçe"
    return "Türkçe" if lang_id & 0x3FF == 0x1F else "English"


def system_language(environ=None, mac=None, apple_languages=None):
    """macOS / Linux: 'Türkçe' when the system's first language is Turkish, else 'English'. macOS keeps it in
    AppleLanguages (an app started from the Finder has no LANG); Linux in LANGUAGE / LC_ALL / LC_MESSAGES / LANG."""
    import os
    import sys
    environ = os.environ if environ is None else environ
    mac = sys.platform == "darwin" if mac is None else mac
    first = ""
    if mac:
        try:
            if apple_languages is None:
                import subprocess
                apple_languages = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True,
                                                 text=True, timeout=5).stdout
            first = next((p.strip(' "\t,') for p in apple_languages.splitlines() if p.strip(' "\t,()')), "")
        except Exception:  # noqa: BLE001 - then the environment decides
            first = ""
    if not first:
        for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
            if environ.get(name):
                first = environ[name].split(":")[0]
                break
    return "Türkçe" if first.lower().startswith("tr") else "English"


def saved_language(settings_path, fallback=None):
    """The language chosen in DISO's settings file; when nothing is chosen yet, `fallback` (or Windows' own)."""
    try:
        import json
        with open(settings_path, encoding="utf-8") as f:
            name = json.load(f).get("language")
        if name in LANGUAGES:
            return name
    except Exception:  # noqa: BLE001 - no settings yet, or a broken file
        pass
    return fallback or windows_language()


def _load():
    if _plain:
        return
    from . import lang_en
    _plain.update(lang_en.PLAIN)
    for tr_text, en_text in lang_en.TEMPLATES:
        parts = [re.escape(p) for p in tr_text.split("{}")]
        # a part never spans lines, nor pieces joined with a separator the template itself does not have
        seps = tuple(s for s in ("    |    ", "  •  ", " • ") if s not in tr_text)
        _templates.append((re.compile("^" + "([^\n]+?)".join(parts) + "$"), en_text, seps,
                           tr_text in lang_en.TRANSLATE_PARTS))


def tr(text):
    """The text in the current language (unchanged when no translation is known)."""
    if current == "tr" or not isinstance(text, str) or not text.strip():
        return text
    return _translate(text, 0)


def _translate(text, depth):
    hit = _plain.get(text)
    if hit is not None:
        return hit
    for pattern, english, seps, words in _templates:
        m = pattern.match(text)
        if m and not any(sep in g for g in m.groups() for sep in seps):                 # not across pieces
            return english.format(*[_plain.get(g, g) if words else g for g in m.groups()])
    if depth > 2:
        return text
    if "\n" in text:                                         # several lines: each on its own
        return "\n".join(_translate(line, depth + 1) if line.strip() else line for line in text.split("\n"))
    for sep in ("    |    ", "  •  ", " • "):                # status lines are pieces joined together
        if sep in text:
            return sep.join(_translate(p, depth + 1) for p in text.split(sep))
    m = _PREFIX.match(text)
    if m and m.group(2) in _plain:
        return m.group(1) + _plain[m.group(2)]
    return text


def back(shown, mapping):
    return mapping.get(shown, shown)


# ------------------------------------------------------------------ hooking the widgets
def _wrap_text_init(cls, keys=("text",)):
    orig = cls.__init__

    def __init__(self, *args, **kw):
        for k in keys:
            if k in kw:
                kw[k] = tr(kw[k])
        orig(self, *args, **kw)

    cls.__init__ = __init__
    orig_conf = cls.configure

    def configure(self, *args, **kw):
        for k in keys:
            if k in kw:
                kw[k] = tr(kw[k])
        return orig_conf(self, *args, **kw)

    cls.configure = configure


def _wrap_choices(cls):
    """Option menus and segmented buttons: English shown, Turkish read back."""
    orig_init, orig_conf, orig_set, orig_get = cls.__init__, cls.configure, cls.set, cls.get

    def shown_values(self, values):
        out = []
        back = self.__dict__.setdefault("_i18n_back", {})    # made before English was switched on
        for v in values:
            s = tr(v)
            back[s] = v
            out.append(s)
        return out

    def wrap_command(self, command):
        if command is None:
            return None
        return lambda value: command(getattr(self, "_i18n_back", {}).get(value, value))

    def __init__(self, *args, **kw):
        self._i18n_back = {}
        if kw.get("values") is not None:
            kw["values"] = shown_values(self, kw["values"])
        if "command" in kw:
            kw["command"] = wrap_command(self, kw["command"])
        orig_init(self, *args, **kw)

    def configure(self, *args, **kw):
        if kw.get("values") is not None:
            kw["values"] = shown_values(self, kw["values"])
        if "command" in kw:
            kw["command"] = wrap_command(self, kw["command"])
        return orig_conf(self, *args, **kw)

    def set_(self, value, *args, **kw):
        return orig_set(self, tr(value), *args, **kw)

    def get(self):
        value = orig_get(self)
        return getattr(self, "_i18n_back", {}).get(value, value)

    cls.__init__, cls.configure, cls.set, cls.get = __init__, configure, set_, get


def install():
    """Hook every place a text reaches the screen (once)."""
    global _installed
    if _installed:
        return
    _installed = True
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    import customtkinter as ctk

    for cls in (ctk.CTkLabel, ctk.CTkButton, ctk.CTkCheckBox, ctk.CTkSwitch, ctk.CTkRadioButton):
        _wrap_text_init(cls)
    _wrap_text_init(ctk.CTkEntry, keys=("placeholder_text",))
    for cls in (ctk.CTkOptionMenu, ctk.CTkSegmentedButton):
        _wrap_choices(cls)

    orig_input = ctk.CTkInputDialog.__init__

    def input_init(self, *args, **kw):
        for k in ("text", "title"):
            if k in kw:
                kw[k] = tr(kw[k])
        orig_input(self, *args, **kw)

    ctk.CTkInputDialog.__init__ = input_init

    orig_title = tk.Wm.wm_title

    def wm_title(self, string=None):
        return orig_title(self, tr(string) if string is not None else None)

    tk.Wm.wm_title = tk.Wm.title = wm_title
    for name in ("add_command", "add_cascade", "add_radiobutton", "add_checkbutton"):
        orig = getattr(tk.Menu, name)

        def menu_add(self, cnf=None, _orig=orig, **kw):
            if "label" in kw:
                kw["label"] = tr(kw["label"])
            return _orig(self, cnf, **kw)

        setattr(tk.Menu, name, menu_add)

    orig_heading = ttk.Treeview.heading

    def heading(self, column, option=None, **kw):
        if "text" in kw:
            kw["text"] = tr(kw["text"])
        return orig_heading(self, column, option, **kw)

    ttk.Treeview.heading = heading

    for name in ("showinfo", "showerror", "showwarning", "askyesno", "askokcancel", "askyesnocancel"):
        orig = getattr(messagebox, name)

        def box(title=None, message=None, _orig=orig, **kw):
            return _orig(tr(title), tr(message), **kw)

        setattr(messagebox, name, box)
    for name in ("askopenfilename", "askopenfilenames", "asksaveasfilename", "askdirectory"):
        orig = getattr(filedialog, name)

        def ask(_orig=orig, **kw):
            if "title" in kw:
                kw["title"] = tr(kw["title"])
            if "filetypes" in kw:
                kw["filetypes"] = [(tr(a), b) for a, b in kw["filetypes"]]
            return _orig(**kw)

        setattr(filedialog, name, ask)

    from . import notify
    orig_toast = notify.toast
    notify.toast = lambda title, body: orig_toast(tr(title), tr(body))
