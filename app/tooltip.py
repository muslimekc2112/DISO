"""Little explanations that show when the mouse rests on a button for a moment (as Windows does over
its icons): one or two words, in the language of the interface at that moment.

Every customtkinter button gets them (install() hooks its creation); what a button says is looked up by
its text when the explanation is about to show (so "▶" / "⏸" of the same button each get theirs, and
"📺 3" is still the channels' button). set() gives one button an explanation of its own."""
import tkinter as tk

DELAY = 1000                   # ms the mouse rests on a button before the explanation shows
OFFSET = (12, 20)              # px from the mouse pointer

# by the button's (Turkish) text; for "📺 3" and the like the first word counts
TIPS = {
    "📋": "Panodaki linki yapıştır", "📄": "Dosyadaki linkleri ekle", "🧲": "Torrent dosyası ekle",
    "ℹ": "Linkin bilgilerini göster", "📊": "İndirme geçmişi", "📺": "Takip edilen kanallar",
    "⚙": "Ayarlar", "✖": "Listeden kaldır", "▶": "Başlat", "⏸": "Duraklat", "⏹": "Durdur",
    "⏮": "Önceki şarkı", "⏭": "Sonraki şarkı", "🔀": "Karışık çal", "🔁": "Tekrar",
    "🔊": "Sesi kapat", "🔇": "Sesi aç", "📌": "Hep üstte tut", "⤢": "Büyük pencereye dön",
    "📂": "Klasörde göster", "＋": "Yeni liste", "✎": "Listenin adını değiştir", "🗑": "Listeyi sil",
    "▲": "Yukarı taşı", "▼": "Aşağı taşı", "A−": "Yazıyı küçült", "A+": "Yazıyı büyüt",
    "🎛 EQ": "Ekolayzır", "🗗 Mini": "Mini oynatıcı", "📋 Sıra": "Sıradaki şarkılar",
    "🎧 Önizle": "30 saniye dinle", "🎤 Sözler": "Şarkı sözleri", "📂 İnenler": "İndirilenler klasörü",
    "🧹 Bitenleri temizle": "Bitenleri listeden kaldır",
    "🗑 Hepsini temizle": "Listeyi boşalt (dosyalar kalır)",
}

_installed = False
_reverse = None                # English button text -> the Turkish one (built the first time it is needed)


def _turkish(text):
    """The Turkish text of a button that shows English now (the explanations are kept by the Turkish one)."""
    global _reverse
    from . import i18n
    if i18n.current == "tr":
        return text
    if _reverse is None:
        from . import lang_en
        _reverse = {en: tr_text for tr_text, en in lang_en.PLAIN.items()}
    return _reverse.get(text, text)


def text_for(widget):
    """What this button's explanation says now (in the interface's language), "" when it has none."""
    from . import i18n
    own = getattr(widget, "_tip_text", None)
    if own is None:
        try:
            shown = str(widget.cget("text")).strip()
        except (tk.TclError, AttributeError, ValueError):
            return ""
        key = _turkish(shown)
        own = TIPS.get(key) or TIPS.get(shown) or TIPS.get(key.split(" ")[0] if key else "", "")
    return i18n.tr(own) if own else ""


def set(widget, text):  # noqa: A001 - tooltip.set(button, "…") reads well
    """This button's own explanation (Turkish; shown in the interface's language)."""
    widget._tip_text = text
    attach(widget)


class _Tip:
    """The explanation of one button: waits DELAY ms after the mouse came, goes when it leaves or clicks."""

    def __init__(self, widget):
        self.widget = widget
        self.job = None
        self.win = None

    def enter(self, event=None):
        self.cancel()
        try:
            self.job = self.widget.after(DELAY, self.show)
        except tk.TclError:
            pass

    def leave(self, event=None):
        try:                                     # moving onto the button's own text is not leaving it
            x, y = self.widget.winfo_pointerxy()
            under = self.widget.winfo_containing(x, y)
            if under is not None and (under is self.widget or str(under).startswith(str(self.widget) + ".")):
                return
        except (tk.TclError, KeyError):
            pass
        self.cancel()

    def cancel(self, event=None):
        if self.job is not None:
            try:
                self.widget.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        self.hide()

    def show(self):
        self.job = None
        text = text_for(self.widget)
        if not text or self.win is not None:
            return
        try:
            if not self.widget.winfo_viewable() or str(self.widget.cget("state")) == "disabled":
                return
            x, y = self.widget.winfo_pointerxy()
            win = tk.Toplevel(self.widget)
            win.wm_overrideredirect(True)
            win.attributes("-topmost", True)
            dark = _is_dark()
            tk.Label(win, text=text, justify="left", padx=7, pady=3, font=("Segoe UI", 9),
                     background="#2B2B2B" if dark else "#FFFFF0", foreground="#F0F0F0" if dark else "#202020",
                     relief="solid", borderwidth=1).pack()
            win.update_idletasks()
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            left = min(x + OFFSET[0], sw - win.winfo_reqwidth() - 4)
            top = y + OFFSET[1] if y + OFFSET[1] + win.winfo_reqheight() < sh else y - win.winfo_reqheight() - 6
            win.wm_geometry(f"+{left}+{top}")
            self.win = win
        except tk.TclError:
            self.win = None

    def hide(self):
        win, self.win = self.win, None
        if win is not None:
            try:
                win.destroy()
            except tk.TclError:
                pass


def _is_dark():
    try:
        import customtkinter as ctk
        return ctk.get_appearance_mode() == "Dark"
    except Exception:  # noqa: BLE001
        return False


def attach(widget):
    """Give a button its explanation (once)."""
    if getattr(widget, "_tip", None) is not None:
        return widget._tip
    tip = widget._tip = _Tip(widget)
    for sequence, handler in (("<Enter>", tip.enter), ("<Leave>", tip.leave), ("<ButtonPress>", tip.cancel)):
        try:
            widget.bind(sequence, handler, add="+")
        except (tk.TclError, TypeError, ValueError):
            pass
    try:
        tk.Misc.bind(widget, "<Destroy>", lambda e: tip.cancel() if e.widget is widget else None, add="+")
    except tk.TclError:
        pass
    return tip


def install():
    """Every customtkinter button made from now on gets its explanation (once per program)."""
    global _installed
    if _installed:
        return
    _installed = True
    import customtkinter as ctk
    orig = ctk.CTkButton.__init__

    def __init__(self, *args, **kw):
        orig(self, *args, **kw)
        attach(self)

    ctk.CTkButton.__init__ = __init__
