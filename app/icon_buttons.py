"""The "Standart" look: the emoji at the start of a button ("📋", "⬇ İndir", "⚙ Ayarlar" ...) is shown as one of
the colourful pictures of the "Nostalji" look (app/classic_icons.py), next to the words. Windows draws emoji in one
flat colour; these are drawn in colour, with a shine.

Installed once (look.apply), before any window exists: every CTkButton made or given a new text afterwards gets its
picture. The program itself keeps reading and writing the whole text (cget("text") gives "⬇ İndir" back), so nothing
else has to know. Media keys (⏮ ▶ ⏸ ⏭ ...) on their own stay the plain symbols a player has."""
import customtkinter as ctk

from . import classic_icons

# emoji -> picture
PICTURES = {
    "⬇": "download", "📂": "folder", "📁": "folder", "📋": "paste", "✖": "delete", "⟳": "update", "🔄": "update", "🧩": "puzzle",
    "💾": "disk", "🐞": "bug", "👤": "person", "⚙": "options", "🎤": "mic", "✎": "pencil", "✏": "pencil",
    "📜": "document", "📊": "history", "＋": "plus", "➕": "plus", "🎬": "video", "🎵": "music", "✓": "check",
    "✔": "check", "🔑": "key", "🗗": "program", "🎛": "sliders", "🎧": "headphones", "🔎": "search", "🔍": "search",
    "🌐": "globe", "🔔": "bell", "🎉": "star", "⌨": "keyboard", "🩺": "heart", "🚀": "rocket", "✉": "mail",
    "📄": "file_links", "🧲": "magnet", "📱": "phone", "📺": "channels", "🧹": "delete_done", "🗑": "trash",
    "ℹ": "info", "👋": "info", "🖼": "picture", "📬": "mail", "📧": "mail",
}
# only with words after them: on their own they are the player's keys
WITH_WORDS = {"▶": "start_all", "⏸": "pause_all"}
SMALL, BIG = 18, 24            # picture sizes: a normal button, a tall one (44 px and more)
_images = {}
_installed = False
active = False                 # the look in use is "Standart" (set by look.apply)


def split(text):
    """("picture name", the words after the emoji) or None when the text does not start with a known one."""
    if not isinstance(text, str) or not text:
        return None
    head, _, rest = text.partition(" ")
    head = head.replace("️", "")
    name = PICTURES.get(head)
    if name is None and rest.strip():
        name = WITH_WORDS.get(head)
    return (name, rest.strip()) if name else None


def picture(name, size, master=None):
    """The picture as a CTkImage. One per Tk interpreter: a CTkImage keeps the Tk images it made, and those belong
    to the interpreter that was running then (a second one would find "pyimage12 does not exist")."""
    import tkinter
    root = master if master is not None else tkinter._default_root
    key = (id(root.tk) if root is not None else 0, name, size)
    if key not in _images:
        img = classic_icons.image(name, size * 2)          # drawn twice as big: sharp on a scaled screen
        _images[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    return _images[key]


def _size(widget, height=None):
    try:
        height = height or widget.cget("height")
    except Exception:  # noqa: BLE001
        height = 28
    return BIG if (height or 0) >= 40 else SMALL


def install():
    """Patch CTkButton (once): its emoji turns into a picture."""
    global _installed
    if _installed:
        return
    _installed = True
    init, configure, cget = ctk.CTkButton.__init__, ctk.CTkButton.configure, ctk.CTkButton.cget

    def new_init(self, *args, **kw):
        found = split(kw.get("text")) if active and "image" not in kw else None
        if found:
            self._full_text = kw["text"]
            kw["text"] = found[1]
            master = args[0] if args else kw.get("master")
            kw["image"] = picture(found[0], BIG if (kw.get("height") or 0) >= 40 else SMALL, master)
            kw.setdefault("compound", "left")
        init(self, *args, **kw)

    def new_configure(self, require_redraw=False, **kw):
        if "text" in kw and "image" not in kw and hasattr(self, "_full_text"):
            found = split(kw["text"])
            self._full_text = kw["text"]
            if found:
                kw["text"] = found[1]
                kw["image"] = picture(found[0], _size(self), self)
            else:
                kw["image"] = None
        elif active and "text" in kw and "image" not in kw:
            found = split(kw["text"])
            if found and not self.cget("image"):
                self._full_text = kw["text"]
                kw["text"] = found[1]
                kw["image"] = picture(found[0], _size(self), self)
                kw.setdefault("compound", "left")
        return configure(self, require_redraw=require_redraw, **kw)

    def new_cget(self, attribute_name):
        if attribute_name == "text" and hasattr(self, "_full_text"):
            return self._full_text
        return cget(self, attribute_name)

    ctk.CTkButton.__init__, ctk.CTkButton.configure, ctk.CTkButton.cget = new_init, new_configure, new_cget
