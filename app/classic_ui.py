"""The "Nostalji" look of the download window, laid out like the download managers of the 2000s: a menu bar,
a toolbar of big pictures, the new-download box, the categories on the left and the downloads as a table,
a status bar at the bottom. Double click on a download shows its progress window; a finished one opens.

`NostalgiaWindow` is mixed into the App: it builds the same widgets the rest of the window code works with
(url_entry, kind_menu, status, sel_buttons ...) and puts a table where the other looks have rows of cards."""
import os
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import TclError, ttk

import customtkinter as ctk

from . import brand, classic_icons, i18n, look
from .config import THEMES
from .models import (CANCELLED, DONE, DOWNLOADING, ERROR, PAUSED, PROCESSING, QUEUED, RESOLVING,
                     SUBTITLE_CHOICES, WAITING)
from .utils import human_eta, human_size, open_file, open_in_file_manager

FONT = ("Tahoma", 8)
BOLD = ("Tahoma", 8, "bold")
TREE_STYLE = "Classic.Treeview"

AUDIO_EXT = {"mp3", "m4a", "aac", "wav", "flac", "ogg", "opus", "wma", "alac", "aiff"}
VIDEO_EXT = {"mp4", "mkv", "webm", "avi", "mov", "wmv", "flv", "m4v", "3gp", "ts", "mpg", "mpeg"}
ARCHIVE_EXT = {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "iso", "img", "cab", "zst"}
DOCUMENT_EXT = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "odt", "ods", "epub", "csv",
                "rtf", "md", "srt", "vtt"}
PROGRAM_EXT = {"exe", "msi", "apk", "appx", "msix", "msixbundle", "bat", "cmd", "jar", "xapk"}
TYPE_EXT = (("audio", AUDIO_EXT), ("video", VIDEO_EXT), ("archive", ARCHIVE_EXT), ("document", DOCUMENT_EXT),
            ("program", PROGRAM_EXT))

# the category tree: (key, text, picture, parent)
CATEGORIES = (
    ("all", "Tüm indirmeler", "folder", ""),
    ("video", "Video", "video", "all"),
    ("audio", "Müzik", "audio", "all"),
    ("archive", "Sıkıştırılmış", "archive", "all"),
    ("document", "Belgeler", "document", "all"),
    ("program", "Programlar", "program", "all"),
    ("other", "Diğer", "other", "all"),
    ("unfinished", "Bitmemiş", "unfinished", ""),
    ("finished", "Bitmiş", "finished", ""),
    ("queue", "Sırada", "queue", ""),
    ("error", "Hatalı", "error", ""),
)
CATEGORY_KEYS = [c[0] for c in CATEGORIES]
TYPE_KEYS = ("video", "audio", "archive", "document", "program", "other")

# the table: (column, heading, width, anchor, stretch, the sort it asks for)
COLUMNS = (
    ("size", "Boyut", 66, "e", False, "Boyut (büyük üstte)"),
    ("status", "Durum", 118, "w", False, "Duruma göre"),
    ("eta", "Kalan süre", 66, "e", False, None),
    ("speed", "Hız", 74, "e", False, None),
    ("date", "Eklenme", 104, "w", False, "date"),
    ("desc", "Açıklama", 150, "w", True, None),
)
NAME_SORT = "Ad (A→Z)"
STATE_TEXT = {QUEUED: "Sırada", WAITING: "Yeniden denenecek", RESOLVING: "Bağlanıyor", PROCESSING: "İşleniyor",
              DONE: "Tamamlandı", PAUSED: "Duraklatıldı", ERROR: "Hata", CANCELLED: "İptal edildi"}


# ------------------------------------------------------------------ pure helpers (tested without a window)
def file_type(item) -> str:
    """video / audio / archive / document / program / other: what the download is, for the category tree
    and its picture. The file's extension decides; without one, what was asked for (a video page is a video)."""
    name = item.final_path or item.dest or ""
    if not name:
        path = item.url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        name = path.rsplit("/", 1)[-1] if "/" in path else ""
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    for key, extensions in TYPE_EXT:
        if ext in extensions:
            return key
    if item.kind == "audio":
        return "audio"
    if item.kind == "video":
        return "video"
    if item.kind == "auto" and not ext:
        return "video"                  # a page link without a file name: the video on that page
    return "other"


def in_category(key, item) -> bool:
    if key in TYPE_KEYS:
        return file_type(item) == key
    if key == "unfinished":
        return item.state != DONE
    if key == "finished":
        return item.state == DONE
    if key == "queue":
        return item.state in (QUEUED, WAITING)
    if key == "error":
        return item.state == ERROR
    return True


def percent(item) -> str:
    return f"{item.fraction * 100:.2f}%"


def status_text(item) -> str:
    if item.state == DOWNLOADING:
        return percent(item)
    if item.state == PAUSED and item.fraction > 0:
        return f"Duraklatıldı {percent(item)}"
    return STATE_TEXT.get(item.state, item.state)


def row_values(item, queue_note=""):
    """The cells of one download in the table: name, (size, status, time left, speed, added, description)."""
    st = item.state
    size = human_size(item.total) if item.total else (human_size(item.done) if item.done else "")
    working = st == DOWNLOADING
    if st == ERROR:
        desc = item.error
    elif st == QUEUED and queue_note:
        desc = queue_note
    else:
        desc = item.message or ""
    return (item.display_name, (
        size, status_text(item),
        human_eta(item.eta) if working else "",
        f"{human_size(item.speed)}/s" if working else "",
        time.strftime("%d.%m.%Y %H:%M", time.localtime(item.added)),
        desc.replace("\n", "  ")))


def scale_of(widget) -> float:
    try:
        return float(ctk.ScalingTracker.get_window_scaling(widget.winfo_toplevel()))
    except Exception:  # noqa: BLE001 - not a customtkinter window
        return 1.0


def style_tree(widget, name=TREE_STYLE):
    """The tables in the look of Windows itself (its own list view theme), Tahoma, white. Dark: the same
    in dark grey (Windows' own theme cannot be dark, the plain one takes the colours)."""
    style = ttk.Style(widget)
    dark = look.is_dark_nostalgia()
    theme = "vista" if "vista" in style.theme_names() and not dark else "clam"
    if style.theme_use() != theme:              # once per window root: switching restyles every ttk widget
        style.theme_use(theme)
    linespace = tkfont.Font(root=widget, font=FONT).metrics("linespace")
    style.configure(name, background=look.N_FIELD, fieldbackground=look.N_FIELD, foreground=look.N_TEXT,
                    font=FONT, rowheight=linespace + int(7 * scale_of(widget)))
    style.configure(name + ".Heading", font=FONT)
    if dark:
        style.configure(name, bordercolor=look.N_FRAME, lightcolor=look.N_FIELD, darkcolor=look.N_FIELD)
        style.configure(name + ".Heading", background=look.N_BUTTON, foreground=look.N_TEXT, relief="raised",
                        bordercolor=look.N_BORDER, lightcolor=look.N_HIGH, darkcolor=look.N_FACE)
        style.map(name + ".Heading", background=[("active", look.N_HOVER)])
        style.map(name, background=[("selected", look.N_SELECT)], foreground=[("selected", "#FFFFFF")])
        for bar in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(bar, background=look.N_BUTTON, troughcolor=look.N_FACE, bordercolor=look.N_BORDER,
                            arrowcolor=look.N_TEXT, lightcolor=look.N_HIGH, darkcolor=look.N_FACE)
            style.map(bar, background=[("disabled", look.N_FACE), ("pressed", look.N_BORDER), ("active", look.N_HOVER)],
                      arrowcolor=[("disabled", look.N_DISABLED)])
        style.configure("TNotebook", background=look.N_FACE, bordercolor=look.N_BORDER)
        style.configure("TNotebook.Tab", background=look.N_BUTTON, foreground=look.N_TEXT, bordercolor=look.N_BORDER,
                        lightcolor=look.N_HIGH)
        style.map("TNotebook.Tab", background=[("selected", look.N_FACE)])
        style.configure("Classic.TFrame", background=look.N_FACE)
    return style


# ------------------------------------------------------------------ small classic widgets
class ToolButton(tk.Frame):
    """A toolbar button: a big picture with its name under it. Flat until the mouse comes, then raised;
    pressed in while clicked. configure(text=..., state=...) and cget work like a button's."""

    def __init__(self, master, icon, text, command, size=32):
        super().__init__(master, bg=look.N_FACE, bd=1, relief="flat", highlightthickness=0)
        self._icon, self._text, self._command, self._state, self._size = icon, text, command, "normal", size
        self._inside = self._pressed = False
        self.picture = tk.Label(self, bg=look.N_FACE, bd=0, image=classic_icons.photo(self, icon, size))
        self.picture.pack(side="top", padx=8, pady=(3, 1))
        self.label = tk.Label(self, bg=look.N_FACE, bd=0, text=i18n.tr(text), font=FONT, fg=look.N_TEXT)
        self.label.pack(side="top", padx=4, pady=(0, 3))
        for w in (self, self.picture, self.label):
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)
            w.bind("<ButtonPress-1>", self._press)
            w.bind("<ButtonRelease-1>", self._release)

    def _enter(self, event=None):
        self._inside = True
        if self._state == "normal":
            tk.Frame.configure(self, relief="sunken" if self._pressed else "raised")

    def _leave(self, event=None):
        self._inside = False
        tk.Frame.configure(self, relief="flat")

    def _press(self, event=None):
        if self._state == "normal":
            self._pressed = True
            tk.Frame.configure(self, relief="sunken")

    def _release(self, event=None):
        was, self._pressed = self._pressed, False
        if self._state != "normal":
            return
        x, y = self.winfo_pointerxy()
        inside = self.winfo_containing(x, y) in (self, self.picture, self.label)
        tk.Frame.configure(self, relief="raised" if inside else "flat")
        if was and inside:
            self.invoke()

    def invoke(self):
        if self._state == "normal" and self._command:
            self._command()

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        return super().cget(key)

    def configure(self, cnf=None, **kw):
        if "text" in kw:
            self._text = kw.pop("text")
            self.label.configure(text=i18n.tr(self._text))
        if "state" in kw:
            self._state = kw.pop("state")
            off = self._state != "normal"
            self.picture.configure(image=classic_icons.photo(self, self._icon, self._size, disabled=off))
            self.label.configure(fg=look.N_DISABLED if off else look.N_TEXT)
            if off:
                tk.Frame.configure(self, relief="flat")
        if cnf or kw:
            return super().configure(cnf, **kw)
        return None

    config = configure


class StatusLabel(tk.Label):
    """A plain Tk label whose text goes through the interface language like customtkinter's do."""

    def __init__(self, master, **kw):
        if "text" in kw:
            kw["text"] = i18n.tr(kw["text"])
        super().__init__(master, **kw)

    def configure(self, cnf=None, **kw):
        if "text" in kw:
            kw["text"] = i18n.tr(kw["text"])
        return super().configure(cnf, **kw)

    config = configure


def separator(parent, vertical=True):
    if vertical:
        return tk.Frame(parent, width=2, bd=1, relief="sunken", bg=look.N_FACE)
    return tk.Frame(parent, height=2, bd=1, relief="sunken", bg=look.N_FACE)


def sunken_panel(parent):
    return tk.Frame(parent, bd=1, relief="sunken", bg=look.N_FACE)


class BlockBar(tk.Canvas):
    """The progress bar of those days: green blocks in a sunken white trough."""
    BLOCK, GAP = 8, 2

    def __init__(self, master, height=18):
        super().__init__(master, height=height, bg=look.N_FIELD, bd=1, relief="sunken", highlightthickness=0)
        self.value = 0.0
        self._drawn = None
        self.bind("<Configure>", lambda e: self._draw(force=True))

    def set(self, fraction):
        self.value = max(0.0, min(1.0, float(fraction or 0)))
        self._draw()

    def _draw(self, force=False):
        w, h = self.winfo_width() - 4, self.winfo_height() - 4
        if w <= 4 or h <= 2:
            return
        step = self.BLOCK + self.GAP
        n = int((w - 2) * self.value) // step
        if not force and n == self._drawn:
            return
        self._drawn = n
        self.delete("all")
        for i in range(n):
            x = 3 + i * step
            self.create_rectangle(x, 3, x + self.BLOCK - 1, h, fill=look.N_GREEN, outline="")
            self.create_rectangle(x, 3, x + self.BLOCK - 1, 3 + h // 3, fill="#7DDB8B", outline="")


# ------------------------------------------------------------------ windows
class AddressDialog(ctk.CTkToplevel):
    """'Yeni indirme': type or paste the address (what the clipboard holds is already in it)."""

    def __init__(self, app):
        super().__init__(app)
        from .ui_common import set_window_icon
        from .utils import extract_urls
        set_window_icon(self)
        self.app = app
        self.title("Yeni indirme")
        self.resizable(False, False)
        self.transient(app)
        self.columnconfigure(1, weight=1)
        tk.Label(self, image=classic_icons.photo(self, "add", 32), bg=look.N_FACE).grid(
            row=0, column=0, rowspan=2, padx=(14, 6), pady=14, sticky="n")
        ctk.CTkLabel(self, text="İndirmek istediğin dosyanın ya da videonun adresi:", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=(4, 14), pady=(14, 2))
        self.entry = ctk.CTkEntry(self, width=440)
        self.entry.grid(row=1, column=1, sticky="ew", padx=(4, 14))
        urls = extract_urls(app._clipboard_text())
        if urls:
            self.entry.insert(0, " ".join(urls))
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", padx=14, pady=14)
        ctk.CTkButton(buttons, text="Tamam", width=86, command=self.confirm).pack(side="left", padx=(0, 6))
        ctk.CTkButton(buttons, text="İptal", width=86, command=self.destroy).pack(side="left")
        self.entry.bind("<Return>", lambda e: self.confirm())
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(120, self._focus)

    def _focus(self):
        try:
            self.lift()
            self.entry.focus_set()
            self.entry.select_range(0, "end")
        except TclError:
            pass

    def confirm(self):
        urls = self.entry.get().split()
        if not urls:
            self.app.notice("Önce bir link yapıştır bakalım.")
            return
        if self.app.add_urls(urls):
            self.destroy()


class ProgressWindow(ctk.CTkToplevel):
    """The window of one download: address, state, size, how much came, speed, time left, the block bar;
    Duraklat / Devam, and when it is finished: open the file or its folder."""
    FIELDS = (("url", "Adres"), ("state", "Durum"), ("size", "Dosya boyutu"), ("done", "İnen"),
              ("speed", "Hız"), ("eta", "Kalan süre"), ("conns", "Bağlantı"), ("place", "Kaydedilen yer"))

    def __init__(self, app, item):
        super().__init__(app)
        from .ui_common import set_window_icon
        set_window_icon(self)
        self.app, self.item = app, item
        self._cache = {}
        self.resizable(False, False)
        self.columnconfigure(0, weight=1)
        box = tk.LabelFrame(self, text=i18n.tr("İndirme durumu"), bg=look.N_FACE, font=FONT, padx=10, pady=6)
        box.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        box.columnconfigure(1, weight=1)
        self.values = {}
        for row, (key, text) in enumerate(self.FIELDS):
            tk.Label(box, text=i18n.tr(text), bg=look.N_FACE, font=FONT, anchor="w").grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=1)
            value = tk.Label(box, text="", bg=look.N_FACE, font=BOLD if key == "state" else FONT, anchor="w",
                             width=58, justify="left")
            value.grid(row=row, column=1, sticky="w", pady=1)
            self.values[key] = value
        self.bar = BlockBar(self)
        self.bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(6, 4))
        from .speed_graph import SpeedGraph
        frame = tk.Frame(self, bd=1, relief="sunken", bg=look.N_FACE)     # 📈 this download's speed
        frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 4))
        self.graph = SpeedGraph(frame, width=420, height=int(60 * scale_of(self)))
        self.graph.pack(fill="x")
        self.graph.show(app.speeds.of(item.id) if hasattr(app, "speeds") else [])
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="ew", padx=10, pady=(4, 10))
        self.open_btn = ctk.CTkButton(buttons, text="Dosyayı aç", width=100, command=self._open_file)
        self.folder_btn = ctk.CTkButton(buttons, text="Klasörü aç", width=100, command=self._open_folder)
        self.folder_btn.pack(side="left")
        ctk.CTkButton(buttons, text="Kapat", width=86, command=self.destroy).pack(side="right")
        self.toggle_btn = ctk.CTkButton(buttons, text="Duraklat", width=96, command=self._toggle)
        self.toggle_btn.pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        self.refresh()
        self.after(300, self._tick)

    def _set(self, key, value, apply):
        if self._cache.get(key) != value:
            self._cache[key] = value
            apply(value)

    def refresh(self):
        it = self.item
        st = it.state
        done = st == DONE
        name = it.display_name
        title = f"{name}" if done else f"{percent(it)} {name}" if st == DOWNLOADING else name
        self._set("title", title, lambda v: self.title(v[:90]))
        state = {DOWNLOADING: "İniyor", DONE: "İndirme tamamlandı"}.get(st, STATE_TEXT.get(st, st))
        if st == ERROR and it.error:
            state = f"{i18n.tr('Hata')}: {it.error}"
        elif it.message and st not in (DONE, ERROR):
            state = f"{i18n.tr(state)} • {it.message}"
        place = it.final_path or it.dest or it.folder
        cells = {
            "url": it.url if len(it.url) <= 80 else it.url[:77] + "…",
            "state": state,
            "size": human_size(it.total) if it.total else "?",
            "done": f"{human_size(it.total if done and it.total else it.done)} ({percent(it)})"
                    if it.done or it.total else "",
            "speed": f"{human_size(it.speed)}/s" if st == DOWNLOADING else "",
            "eta": human_eta(it.eta) if st == DOWNLOADING else "",
            "conns": str(it.conns) if it.conns and st == DOWNLOADING else "",
            "place": place if len(place) <= 80 else "…" + place[-79:],
        }
        for key, text in cells.items():
            self._set(key, text, lambda v, k=key: self.values[k].configure(text=i18n.tr(v)))
        self._set("bar", round(it.fraction, 3), self.bar.set)
        can_toggle = st not in (DONE, PROCESSING)
        toggle = "Duraklat" if st in (QUEUED, WAITING, RESOLVING, DOWNLOADING) else "Devam et"
        self._set("toggle", (toggle, can_toggle),
                  lambda v: self.toggle_btn.configure(text=v[0], state="normal" if v[1] else "disabled"))
        self._set("done", done, self._show_done)

    def _show_done(self, done):
        if done:
            self.open_btn.pack(side="left", before=self.folder_btn, padx=(0, 6))
            self.toggle_btn.pack_forget()
            self.bar.set(1.0)
        else:
            self.open_btn.pack_forget()

    def _tick(self):
        try:
            if not self.winfo_exists():
                return
            if self.item.removed:
                self.destroy()
                return
            self.refresh()
            self.after(300, self._tick)
        except TclError:
            return

    def _toggle(self):
        m = self.app.manager
        if self.item.state in (QUEUED, WAITING, RESOLVING, DOWNLOADING):
            m.pause(self.item)
        else:
            m.resume(self.item)

    def _open_file(self):
        it = self.item
        if it.final_path and os.path.exists(it.final_path):
            open_file(it.final_path)
            self.destroy()

    def _open_folder(self):
        it = self.item
        open_in_file_manager(it.final_path or it.dest or it.folder)


# ------------------------------------------------------------------ the main window
class NostalgiaWindow:
    """Mixed into the App: the "Nostalji" layout of the download window."""

    def _n_build(self):
        self.filter_menu = self.sort_menu = None          # the category tree and the table's headings do this
        self.list_frame = None
        self.select_all_var = ctk.BooleanVar(value=False)
        self.category = self.cfg.get("category") if self.cfg.get("category") in CATEGORY_KEYS else "all"
        self._n_cache = {}
        self._progress = {}                               # item id -> its progress window
        self._n_scale = scale_of(self)
        if look.is_dark_nostalgia():                      # plain tk widgets that name no colour: dark grey too
            for pattern, colour in (("*Background", look.N_FACE), ("*Foreground", look.N_TEXT),
                                    ("*activeBackground", look.N_HOVER), ("*activeForeground", look.N_TEXT),
                                    ("*selectColor", look.N_FIELD), ("*highlightBackground", look.N_FACE),
                                    ("*troughColor", look.N_FACE), ("*disabledForeground", look.N_DISABLED)):
                self.option_add(pattern, colour, "widgetDefault")
        style_tree(self)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._n_menu()
        self._n_toolbar()
        self._n_address()
        self._n_body()
        self._build_update_bar()
        self._n_status()
        self.bind("<Control-n>", lambda e: self.open_address_dialog())

    # ---- menu bar
    def _n_menu(self):
        bar = self.menubar = tk.Menu(self, tearoff=0)

        def menu(label, entries):
            m = tk.Menu(bar, tearoff=0)
            self._n_fill(m, entries)
            bar.add_cascade(label=label, menu=m)
            return m

        menu("Görevler", [
            ("Yeni indirme ekle…", self.open_address_dialog, "Ctrl+N"),
            ("Panodaki linkleri ekle", self._n_paste_links, "Ctrl+V"),
            ("Dosyadaki linkleri ekle…", self._import_file, None),
            ("Link bilgisi ve kalite seçimi…", self._show_info, None),
            None,
            ("Çıkış", self._on_close, None)])
        menu("İndirmeler", [
            ("Seçilenleri başlat", self._sel_resume, None),
            ("Seçilenleri durdur", self._sel_pause, None),
            ("Seçilenleri sil", self._sel_remove, "Del"),
            None,
            ("Hepsini başlat", self.manager.resume_all, None),
            ("Hepsini durdur", self.manager.pause_all, None),
            ("Bitenleri temizle", self.manager.clear_finished, None),
            None,
            ("Hepsini seç", self._on_ctrl_a, "Ctrl+A"),
            ("İndirme geçmişi", self.open_history, None)])
        # "Görünüm" alone is the theme setting in English: this one is the "View" menu
        view = menu("View" if i18n.current == "en" else "Görünüm", [
            ("Müzik çalar", self._n_music, None),
            ("Takip edilen kanallar", self.open_channels, None),
            None])
        self._look_var = tk.StringVar(value=look.style_name())
        styles = tk.Menu(view, tearoff=0)
        for name in look.STYLES:
            styles.add_radiobutton(label=name, value=name, variable=self._look_var,
                                   command=lambda n=name: self._n_choose("look", n))
        view.add_cascade(label="Görünüm stili", menu=styles)
        self._theme_var = tk.StringVar(value=self.cfg.get("theme"))
        themes = tk.Menu(view, tearoff=0)
        for name in THEMES:
            themes.add_radiobutton(label=name, value=name, variable=self._theme_var,
                                   command=lambda n=name: self._n_choose("theme", n))
        view.add_cascade(label="Renk (açık / koyu)", menu=themes)
        self._language_var = tk.StringVar(value=self.cfg.get("language"))
        languages = tk.Menu(view, tearoff=0)
        for name in i18n.LANGUAGES:
            languages.add_radiobutton(label=name, value=name, variable=self._language_var,
                                      command=lambda n=name: self._n_choose("language", n))
        view.add_cascade(label="Dil", menu=languages)
        menu("Araçlar", [
            ("Ayarlar…", self._open_settings, None),
            ("Zamanlayıcı…", lambda: self._open_settings("Zamanlayıcı"), None),
            ("Güncellemeler…", self._open_updates, None),
            ("Tarayıcı eklentisi…", self.open_extension_guide, None),
            None,
            ("Yedek al…", self.make_backup, None),
            ("Yedeği yükle…", self.restore_backup, None),
            None,
            ("Günlüğü aç", self.open_log, None)])
        menu("Yardım", [
            ("Klavye kısayolları", self.open_shortcuts, "F1"),
            ("Bize ulaş", lambda: webbrowser.open(brand.CONTACT_URL), None),
            None,
            (f"{brand.NAME} hakkında", self.open_about, None)])
        tk.Tk.configure(self, menu=bar)

    @staticmethod
    def _n_fill(menu, entries):
        for entry in entries:
            if entry is None:
                menu.add_separator()
                continue
            label, command, key = entry
            if key:
                menu.add_command(label=label, command=command, accelerator=key)
            else:
                menu.add_command(label=label, command=command)

    def _n_choose(self, key, value):
        if self.cfg.get(key) != value:
            self.apply_setting(key, value)
        self._n_show_choices()

    def _n_show_choices(self):
        """The menu's ticks follow the setting (a 'not now' answer leaves the look as it is until DISO starts)."""
        try:
            self._look_var.set(self.cfg.get("look"))
            self._theme_var.set(self.cfg.get("theme"))
            self._language_var.set(self.cfg.get("language"))
        except (AttributeError, TclError):
            pass

    def _n_paste_links(self):
        from .utils import extract_urls
        urls = extract_urls(self._clipboard_text())
        if urls:
            self.add_urls(urls)
        else:
            self.notice("Panoda link göremedim")

    def _n_music(self):
        from .music_ui import MODE_MUSIC
        self._switch_mode(MODE_MUSIC)

    def open_address_dialog(self):
        return self._single("address_dialog", lambda: AddressDialog(self))

    # ---- toolbar
    def _n_toolbar(self):
        bar = tk.Frame(self, bg=look.N_FACE)
        bar.grid(row=0, column=0, sticky="ew")
        separator(bar, vertical=False).pack(side="top", fill="x")
        row = tk.Frame(bar, bg=look.N_FACE)
        row.pack(side="top", fill="x", padx=4, pady=2)
        separator(bar, vertical=False).pack(side="top", fill="x")
        size = int(32 * self._n_scale)
        buttons = {}
        layout = (("add", "Yeni indirme", self.open_address_dialog), None,
                  ("resume", "Devam et", self._sel_resume), ("pause", "Durdur", self._sel_pause),
                  ("pause_all", "Hepsini durdur", self.manager.pause_all), ("delete", "Sil", self._sel_remove),
                  ("delete_done", "Bitenleri sil", self.manager.clear_finished), None,
                  ("options", "Ayarlar", self._open_settings),
                  ("scheduler", "Zamanlayıcı", lambda: self._open_settings("Zamanlayıcı")),
                  ("start_all", "Hepsini başlat", self.manager.resume_all), None,
                  ("update", "Güncellemeler", self._open_updates), ("music", "Müzik çalar", self._n_music),
                  ("channels", "Kanallar", self.open_channels), ("history", "Geçmiş", self.open_history))
        for entry in layout:
            if entry is None:
                separator(row).pack(side="left", fill="y", padx=4, pady=4)
                continue
            icon, text, command = entry
            buttons[icon] = ToolButton(row, icon, text, command, size=size)
            buttons[icon].pack(side="left", padx=1)
        self.tool_buttons = buttons
        self.sel_buttons = [buttons["resume"], buttons["pause"], buttons["delete"]]
        for b in self.sel_buttons:
            b.configure(state="disabled")
        self.updates_btn = buttons["update"]
        self.channels_btn = buttons["channels"]
        self.history_button = buttons["history"]

    # ---- the new-download box: address and the choices
    def _n_address(self):
        cfg = self.cfg
        box = tk.LabelFrame(self, text=i18n.tr("Yeni indirme"), bg=look.N_FACE, font=FONT, padx=6, pady=3)
        box.grid(row=1, column=0, sticky="ew", padx=8, pady=(6, 2))
        box.columnconfigure(0, weight=1)

        def line(r):
            f = tk.Frame(box, bg=look.N_FACE)
            f.grid(row=r, column=0, sticky="ew", pady=2)
            return f

        def label(parent, text):
            ctk.CTkLabel(parent, text=text, height=24).pack(side="left", padx=(0, 4))

        def option(parent, text, values, value, width, command):
            label(parent, text)
            m = ctk.CTkOptionMenu(parent, values=values, width=width, height=24, command=command)
            m.set(value)
            m.pack(side="left", padx=(0, 14))
            return m

        row = line(0)
        label(row, "Adres:")
        self.url_entry = ctk.CTkEntry(row, height=26, placeholder_text="Linki buraya yapıştır (birden fazlaysa "
                                                                       "araya boşluk koy)…")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.url_entry.bind("<Return>", lambda e: self.add_from_entry())
        ctk.CTkButton(row, text="⬇  İndir", width=96, height=26, font=ctk.CTkFont(weight="bold"),
                      command=self.add_from_entry).pack(side="right")
        ctk.CTkButton(row, text="Bilgi…", width=64, height=26, command=self._show_info).pack(side="right", padx=(0, 6))
        ctk.CTkButton(row, text="Dosyadan…", width=78, height=26, command=self._import_file).pack(side="right", padx=(0, 6))
        ctk.CTkButton(row, text="Yapıştır", width=70, height=26, command=self._paste).pack(side="right", padx=(0, 6))

        from . import video_engine as ve
        from .ui import CONNECTIONS, KIND_LABELS
        row = line(1)
        self.kind_menu = option(row, "Ne indirilecek", list(KIND_LABELS), cfg.get("kind"), 185, self._on_kind)
        self.quality_menu = option(row, "Video kalitesi", ve.QUALITIES, cfg.get("quality"), 104,
                                   lambda v: cfg.set("quality", v))
        self.bitrate_menu = option(row, "MP3 kalitesi (kbps)", ve.BITRATES, cfg.get("bitrate"), 70,
                                   lambda v: cfg.set("bitrate", v))
        self.subs_menu = option(row, "Altyazı (video)", SUBTITLE_CHOICES, cfg.get("subs"), 100,
                                lambda v: cfg.set("subs", v))

        row = line(2)
        self.conn_menu = option(row, "Bağlantı sayısı (hız)", CONNECTIONS, cfg.get("connections"), 60,
                                lambda v: cfg.set("connections", v))
        self.cookie_menu = option(row, "Giriş çerezleri", ve.BROWSERS, cfg.get("cookies"), 100,
                                  lambda v: cfg.set("cookies", v))
        label(row, "Kaydet:")
        from .utils import default_download_dir
        self.folder_entry = ctk.CTkEntry(row, height=24)
        self.folder_entry.insert(0, cfg.get("folder") or default_download_dir())
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.folder_entry.bind("<FocusOut>", lambda e: self._save_folder())
        self.folder_entry.bind("<Return>", lambda e: self._save_folder())
        ctk.CTkButton(row, text="Klasör Seç", width=86, height=24, command=self._pick_folder).pack(side="left")

        row = line(3)

        def check(text, var, command):
            ctk.CTkCheckBox(row, text=text, variable=var, command=command, checkbox_width=15,
                            checkbox_height=15, height=22).pack(side="left", padx=(0, 16))

        self.playlist_var = ctk.BooleanVar(value=bool(cfg.get("playlist")))
        check("Oynatma listesi", self.playlist_var, lambda: cfg.set("playlist", bool(self.playlist_var.get())))
        self.folders_var = ctk.BooleanVar(value=bool(cfg.get("sort_folders")))
        check("Türe göre klasör (Video, Müzik, Arşiv…)", self.folders_var,
              lambda: cfg.set("sort_folders", bool(self.folders_var.get())))
        self.cover_var = ctk.BooleanVar(value=bool(cfg.get("cover")))
        check("MP3'e kapak resmi", self.cover_var, lambda: cfg.set("cover", bool(self.cover_var.get())))
        self.clip_var = ctk.BooleanVar(value=False)
        check("Panoyu izle", self.clip_var, self._on_clip_toggle)

    # ---- categories on the left, the table on the right
    def _n_body(self):
        s = self._n_scale
        pane = tk.PanedWindow(self, orient="horizontal", bg=look.N_FACE, bd=0, sashwidth=int(6 * s),
                              sashrelief="flat", showhandle=False)
        pane.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 2))

        left = tk.Frame(pane, bg=look.N_FACE)
        # no textvariable here: customtkinter hides the placeholder when one is used
        self.search_entry = ctk.CTkEntry(left, height=24, placeholder_text="🔍 Listede ara…")
        self.search_entry.pack(side="top", fill="x", pady=(0, 4))
        self.search_entry.bind("<KeyRelease>", lambda e: self._sync_rows())
        self.search_entry.bind("<Escape>", lambda e: self._clear_search())
        head = tk.Label(left, text=i18n.tr("Kategoriler"), font=BOLD, bg=look.N_HEADER, fg=look.N_TEXT, anchor="w", bd=1,
                        relief="raised", padx=4)
        head.pack(side="top", fill="x")
        self.category_tree = tree = ttk.Treeview(left, show="tree", selectmode="browse", style=TREE_STYLE)
        tree.pack(side="top", fill="both", expand=True)
        small = int(16 * s)
        for key, text, icon, parent in CATEGORIES:
            tree.insert(parent, "end", iid=key, text=" " + i18n.tr(text), image=classic_icons.photo(tree, icon, small),
                        open=True)
        tree.selection_set(self.category)
        tree.see(self.category)
        tree.bind("<<TreeviewSelect>>", self._n_on_category)
        pane.add(left, width=int(190 * s), minsize=int(130 * s))

        right = tk.Frame(pane, bg=look.N_FACE)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.table = table = ttk.Treeview(right, columns=[c[0] for c in COLUMNS], show="tree headings",
                                          selectmode="extended", style=TREE_STYLE)
        table.heading("#0", text=i18n.tr("Dosya adı"), anchor="w", command=lambda: self._n_sort(NAME_SORT))
        table.column("#0", width=int(250 * s), minwidth=int(120 * s), stretch=True, anchor="w")
        for name, text, width, anchor, stretch, sort in COLUMNS:
            table.heading(name, text=i18n.tr(text), anchor=anchor,
                          command=(lambda v=sort: self._n_sort(v)) if sort else "")
            table.column(name, width=int(width * s), minwidth=int(40 * s), anchor=anchor, stretch=stretch)
        table.tag_configure("error", foreground=look.N_ERROR_TEXT)
        table.tag_configure("done", foreground=look.N_DONE_TEXT)
        table.grid(row=0, column=0, sticky="nsew")
        ys = ttk.Scrollbar(right, orient="vertical", command=table.yview)
        ys.grid(row=0, column=1, sticky="ns")
        xs = ttk.Scrollbar(right, orient="horizontal", command=table.xview)
        xs.grid(row=1, column=0, sticky="ew")
        table.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        table.bind("<<TreeviewSelect>>", self._n_on_select)
        table.bind("<Double-Button-1>", self._n_on_double)
        table.bind("<Return>", self._n_on_double)
        table.bind("<Button-3>", self._n_on_right)
        self.empty_label = tk.Label(table, text="", bg=look.N_FIELD, fg=look.N_GREY_TEXT, font=FONT, justify="center")
        pane.add(right, minsize=int(320 * s))
        self.rows = {}
        self._n_show_sort()

    def _n_on_category(self, event=None):
        sel = self.category_tree.selection()
        if not sel or sel[0] == self.category:
            return
        self.category = sel[0]
        self.cfg.set("category", self.category)
        self._sync_rows()

    def _n_sort(self, sort):
        if sort == "date":
            sort = "Eski üstte" if self.cfg.get("sort") == "Yeni üstte" else "Yeni üstte"
        self.cfg.set("sort", sort)
        self._n_show_sort()
        self._sync_rows()

    def _n_show_sort(self):
        """A small arrow on the heading the list is sorted by."""
        sort = self.cfg.get("sort")
        marks = {"#0": "▲" if sort == NAME_SORT else ""}
        for name, _, _, _, _, key in COLUMNS:
            marks[name] = ("▲" if sort == "Eski üstte" else "▼") if key == "date" and sort in ("Yeni üstte", "Eski üstte") \
                else ("▼" if key == sort else "")
        texts = {"#0": "Dosya adı", **{c[0]: c[1] for c in COLUMNS}}
        for name, mark in marks.items():
            text = i18n.tr(texts[name])
            self.table.heading(name, text=f"{text}  {mark}" if mark else text)

    # ---- the status bar
    def _n_status(self):
        from .music_ui import MODE_DOWNLOAD, mode_bar
        from .ui import LANGUAGE_NAMES, LANGUAGE_SHORT
        bar = tk.Frame(self, bg=look.N_FACE)
        bar.grid(row=7, column=0, sticky="ew", padx=2, pady=(0, 2))
        bar.columnconfigure(0, weight=1)
        panel = sunken_panel(bar)
        panel.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        # a plain label that asks for no width: a long status line is cut, the parts on the right stay
        self.status = StatusLabel(panel, text="", anchor="w", width=1, bg=look.N_FACE, font=FONT)
        self.status.pack(side="left", fill="x", expand=True, padx=4, pady=2)
        panel = sunken_panel(bar)
        panel.grid(row=0, column=1, sticky="ns", padx=(0, 2))
        self.sel_label = ctk.CTkLabel(panel, text="", width=74, height=20, font=ctk.CTkFont(size=11))
        self.sel_label.pack(padx=4)
        from .speed_graph import SpeedGraph
        panel = sunken_panel(bar)                                    # 📈 green on black, like back then
        panel.grid(row=0, column=2, sticky="ns", padx=(0, 2))
        self.speed_graph = SpeedGraph(panel, width=int(110 * self._n_scale), height=int(18 * self._n_scale), label=False)
        self.speed_graph.pack(padx=1, pady=1)
        self.language_switch = ctk.CTkSegmentedButton(bar, values=list(LANGUAGE_SHORT), width=70, height=22,
                                                      font=ctk.CTkFont(size=11), command=self._on_language_switch)
        self.language_switch.set(LANGUAGE_NAMES[self.cfg.get("language")])
        self.language_switch.grid(row=0, column=3, padx=(2, 4))
        self.mode_bar = mode_bar(bar, MODE_DOWNLOAD, self._switch_mode, height=22)
        self.mode_bar.grid(row=0, column=4)

    # ---- the table follows the download list
    def _n_sync(self):
        table = self.table
        items = list(self.manager.items)
        ids = {i.id for i in items}
        self.selected &= ids
        visible = self._visible_items()
        order = [it.id for it in visible]
        small = int(16 * self._n_scale)
        if order != self._order:
            keep = set(order)
            for iid in table.get_children():
                if iid not in keep:
                    table.delete(iid)
                    self._n_cache.pop(iid, None)
            for index, it in enumerate(visible):
                if table.exists(it.id):
                    table.move(it.id, "", index)
                else:
                    table.insert("", index, iid=it.id, text="")
            self._order = order
            if order:
                self.empty_label.place_forget()
            else:
                self.empty_label.configure(text=i18n.tr(
                    "Burası şimdilik bomboş. Bir link yapıştır, gerisini bana bırak." if not items
                    else "Aramana uyan bir şey çıkmadı."))
                self.empty_label.place(relx=0.5, rely=0.4, anchor="center")
        for it in visible:
            name, values = row_values(it, self.queue_note)
            kind = file_type(it)
            tag = "error" if it.state == ERROR else ("done" if it.state == DONE else "")
            shown = (name, values, kind, tag)
            if self._n_cache.get(it.id) != shown:
                self._n_cache[it.id] = shown
                table.item(it.id, text=" " + name[:200], values=[i18n.tr(v) for v in values],
                           image=classic_icons.photo(table, kind, small), tags=(tag,) if tag else ())
        want = [iid for iid in order if iid in self.selected]
        if tuple(table.selection()) != tuple(want) and set(table.selection()) != set(want):
            table.selection_set(want)
        self._update_selection_ui()

    def _n_on_select(self, event=None):
        shown = set(self._order or [])
        self.selected = (self.selected - shown) | set(self.table.selection())
        self._update_selection_ui()

    def _n_item(self, iid):
        return next((it for it in self.manager.items if it.id == iid), None)

    def _n_on_double(self, event=None):
        if event is not None and getattr(event, "y", None) is not None and event.type == tk.EventType.ButtonPress:
            iid = self.table.identify_row(event.y)
        else:
            iid = self.table.focus()
        it = self._n_item(iid) if iid else None
        if it is None:
            return None
        if it.state == DONE and it.final_path and os.path.exists(it.final_path):
            open_file(it.final_path)
        else:
            self.open_progress(it)
        return "break"

    def open_progress(self, item):
        win = self._progress.get(item.id)
        try:
            if win is not None and win.winfo_exists():
                self._bring_to_front(win)
                return win
        except TclError:
            pass
        win = self._progress[item.id] = ProgressWindow(self, item)
        return win

    def _n_on_right(self, event):
        iid = self.table.identify_row(event.y)
        it = self._n_item(iid) if iid else None
        if it is None:
            return
        if iid not in self.table.selection():
            self.table.selection_set(iid)
            self._n_on_select()
        self.table.focus(iid)
        from .ui import ItemMenu
        actions = ItemMenu(it, self)
        extra = [] if it.state == DONE else [("İlerleme penceresi", lambda: self.open_progress(it))]
        actions.popup_menu(self.table, event, extra)
