"""The music player window: playlists, the track table, cover picture, transport buttons, seek and
volume, and "🔍 Şarkı bul" (find songs on the internet and download them as MP3). It is independent of
the download window; they share the mode bar at the bottom, the playlists (a finished download can
add to them) and the download queue (a found song is downloaded there, in the background)."""
import os
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import equalizer, i18n, look, lyrics, mediakeys, music_search, playlists, smtc, tags
from . import taskbar as taskbar_module
from .logs import log
from .playlists import FADE_CHOICES
from .player import AUDIO_EXTENSIONS, REPEAT_MODES, artist_and_title, track_label
from .ui_common import fit_geometry, logo_image, set_if_changed, set_window_icon
from .utils import is_url, open_in_file_manager

MODE_DOWNLOAD = "İndirme modu"
MODE_MUSIC = "Müzik çalar modu"
MODES = [MODE_DOWNLOAD, MODE_MUSIC]
VIEW_LISTS = "🎵 Listelerim"
VIEW_FIND = "🔍 Şarkı bul"
PLAY_ICON, PAUSE_ICON = "▶", "⏸"
COVER_PX = 112
SAVE_DELAY = 1500          # ms: tags that keep arriving are written to the file once, after a pause
PRUNE_EVERY = 5.0          # s: how often the lists are checked for deleted files
REMEMBER_EVERY = 5.0       # s: how often the place in the song is noted (written to the file on exit)
SLEEP_OFF = "😴 Uyku: kapalı"
SMART_EMPTY = {
    "⭐ En çok dinlenenler": "Henüz hiçbir şarkıyı dinlemedin.\nBir şarkı 30 saniye çalınca burada sayılır.",
    "🆕 Son eklenenler": "Listelerinde hiç şarkı yok.\nŞarkı ekleyince en yenileri burada görünür.",
    "💤 Hiç dinlenmeyenler": "Her şarkıyı en az bir kez dinlemişsin. 🎉",
}
SLEEP_TRACK = "Parça bitince"
SLEEP_CHOICES = [SLEEP_OFF, "15 dk", "30 dk", "45 dk", "60 dk", "90 dk", SLEEP_TRACK]
SORT_COLUMNS = {"title": "title", "artist": "artist", "time": "time"}


def mode_bar(parent, current, command, height=32):
    """The 'İndirme modu | Müzik çalar modu' switch that sits at the bottom of both windows."""
    bar = ctk.CTkSegmentedButton(parent, values=MODES, command=command, height=height)
    bar.set(current)
    return bar


def fmt_time(ms) -> str:
    s = max(0, int(ms // 1000))
    return f"{s // 60}:{s % 60:02d}"


def fmt_total(ms) -> str:
    """'48 dk' / '1 sa 12 dk' for the length of a whole list."""
    minutes = max(0, int(ms // 60000))
    return f"{minutes // 60} sa {minutes % 60} dk" if minutes >= 60 else f"{minutes} dk"


def _themed(pair):
    """One colour of a (light, dark) customtkinter colour pair, for the current appearance."""
    if isinstance(pair, (tuple, list)):
        return pair[0] if ctk.get_appearance_mode() == "Light" else pair[1]
    return pair


def square_cover(path, px=COVER_PX * 2):
    """The cover picture cut to a centred square and scaled (kept at twice the shown size: sharp on
    high-resolution screens). None if the file cannot be read as a picture."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGB")
            side = min(im.size)
            left, top = (im.width - side) // 2, (im.height - side) // 2
            return im.crop((left, top, left + side, top + side)).resize((px, px), Image.LANCZOS)
    except Exception:  # noqa: BLE001 - a damaged picture is simply not shown
        return None


def rounded(img, radius):
    """The picture with rounded corners (transparent outside them)."""
    from PIL import Image, ImageDraw
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def placeholder_image(px=COVER_PX * 2, shown=COVER_PX):
    """The 'no cover' tile, one colour for each appearance."""
    from PIL import Image
    if look.is_nostalgia():                      # a plain grey square, like the album art of old players
        tile = Image.new("RGB", (px, px), "#D4D0C8")
        return ctk.CTkImage(light_image=tile, dark_image=tile, size=(shown, shown))
    tiles = [rounded(Image.new("RGB", (px, px), colour), px // 8) for colour in ("#EADFF0", "#2A1B36")]
    return ctk.CTkImage(light_image=tiles[0], dark_image=tiles[1], size=(shown, shown))


def style_table(widget, name="Music.Treeview"):
    """Colours of the plain ttk tables (music, history) for the current theme: ttk does not follow it."""
    if look.is_nostalgia():                      # Windows' own list look
        from .classic_ui import style_tree
        style_tree(widget, name)
        return
    theme = ctk.ThemeManager.theme
    style = ttk.Style(widget)
    if style.theme_use() != "clam":
        style.theme_use("clam")                  # the one built-in theme that accepts our colours
    body = _themed(theme["CTkFrame"]["fg_color"])
    head = _themed(theme["CTkFrame"]["top_fg_color"])
    text = _themed(theme["CTkLabel"]["text_color"])
    accent = _themed(theme["CTkButton"]["fg_color"])
    accent_text = _themed(theme["CTkButton"]["text_color"])
    family = ctk.ThemeManager.theme.get("CTkFont", {}).get("family", "Segoe UI")
    family = family if isinstance(family, str) else "Segoe UI"
    font = tkfont.Font(family=family, size=11)
    style.layout(name, [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure(name, background=body, fieldbackground=body, foreground=text,
                    borderwidth=0, font=font, rowheight=int(font.metrics("linespace") * 1.9))
    style.configure(name + ".Heading", background=head, foreground=text, relief="flat",
                    borderwidth=0, font=(family, 10, "bold"), padding=(6, 5))
    style.map(name, background=[("selected", accent)], foreground=[("selected", accent_text)])
    style.map(name + ".Heading", background=[("active", head)])


def song_status(item) -> str:
    """What the music window shows for a song it is downloading: just how far it is."""
    from .models import DONE, DOWNLOADING, ERROR, PAUSED, PROCESSING, RESOLVING, CANCELLED
    state = item.state
    if state == DONE:
        return "✓ İndi"
    if state == DOWNLOADING:
        return f"%{min(99, int(item.fraction * 100))}"
    if state == PROCESSING:
        return "%99"
    if state == RESOLVING:
        return "%0"
    if state == ERROR:
        return "✖ Olmadı"
    if state in (PAUSED, CANCELLED):
        return "⏸ Durdu"
    return "Sırada"


def matches(track, words) -> bool:
    text = " ".join(str(track.get(k) or "") for k in ("title", "tag_title", "artist", "album")).casefold()
    return all(w in text for w in words)


class MusicWindow(ctk.CTkToplevel):
    _ttk_ready = False

    def __init__(self, app, store, controller, on_close, on_mode, reader=None, keys=None, searcher=None,
                 lyrics_fetcher=None, suggester=None, previewer=None, overlay=None, thumbbar=None):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.store = store
        self.controller = controller
        self.reader = reader if reader is not None else tags.TagReader()
        self.keys = keys if keys is not None else mediakeys.MediaKeys()
        self.searcher = searcher if searcher is not None else music_search.Searcher()
        self.lyrics_fetcher = (lyrics_fetcher if lyrics_fetcher is not None
                               else getattr(app, "lyrics_fetcher", None) or lyrics.Fetcher())
        self.lyrics_window = None
        self._lyrics_shown = False
        self.suggester = suggester if suggester is not None else music_search.Searcher(find=music_search.suggest)
        self.previewer = previewer if previewer is not None else music_search.Searcher(find=self._make_preview)
        self.overlay = overlay if overlay is not None else smtc.MediaOverlay()
        self.thumbbar = thumbbar if thumbbar is not None else taskbar_module.ThumbBar()
        self.mini = None                             # the small always-on-top player, while it is open
        self.preview = None                          # {"result", "path", "until", "resume"} while a preview sounds
        self._preview_backend = None
        self._preview_wanted = None                  # the result whose preview is being made
        self._suggest_rows = []
        self._suggest_index = -1
        self._suggest_after = None
        self.results_title = ""                      # the playlist / album whose songs the results are
                   # is the 🎤 button on the screen
        self._lyrics_asked = set()                   # songs whose lyrics the user asked for here
        self._undo_order = None                      # (list, order before the last shuffle)
        self._on_mode = on_mode
        self.title("DISO • Müzik çalar")
        fit_geometry(self, 900, 760)
        self.minsize(720, 600)
        self.protocol("WM_DELETE_WINDOW", on_close)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.viewed = store.state["last"]            # the list shown in the window
        self.playing_list = None                     # the list the queue was taken from
        self.view = VIEW_LISTS
        self.results = []                            # the songs the last search found
        self.filter_text = ""
        self.sort_by = (None, False)                 # (column, reversed) of the last sort
        self._shown_marker = None
        self._dragging = False
        self._note_until = 0
        self._closed = False
        self._volume_save = None
        self._tags_save = None
        self._cover_path = None                      # the track whose cover is shown (or asked for)
        self._cover_image = None
        self._covers = {}                            # path -> jpeg path or None, for this session
        self._missing = None                         # deleted files found by the background check
        self._checking = False
        self._next_prune = 0.0
        self._next_remember = 0.0
        self.sleep_at = None                         # time.time() when the music stops by itself
        self.sleep_after_track = False
        self._resume = self._saved_place()           # (list, index, ms) to go on from, or None

        controller.shuffle = bool(store.state["shuffle"])
        controller.repeat = store.state["repeat"]
        controller.set_volume(store.state["volume"])
        controller.fade_ms = int(store.state["fade"]) * 1000
        self.eq_window = None
        if not equalizer.is_flat(store.state["eq"]):
            self.apply_eq(store.state["eq"], remember=False)

        self._build_top()
        self._build_toolbars()
        self._build_table()
        self._build_results()
        self._build_list_buttons()
        self._build_find_buttons()
        self._build_player()
        self.mode_bar = mode_bar(self, MODE_MUSIC, self._on_mode)
        self.mode_bar.grid(row=6, column=0, sticky="ew", padx=16, pady=(4, 12))
        if look.is_nostalgia():
            self._build_menu_bar()
        self._bind_keys()
        self._refresh_lists()
        self.recolor()
        self._show_view(VIEW_LISTS)
        self._update_status()                        # "Kaldığın yer: …" at once, not a quarter second later
        self.after(250, self._tick)

    # ------------------------------------------------------------------ layout
    def _build_top(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        head.columnconfigure(1, weight=1)
        old = look.is_nostalgia()
        self._logo = logo_image(24 if old else 36)   # kept on self: a picture nobody holds disappears
        ctk.CTkLabel(head, text=" Müzik çalar" if self._logo else "🎵 Müzik çalar", image=self._logo,
                     compound="left", font=ctk.CTkFont(size=16 if old else 24, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 16))
        self.view_switch = ctk.CTkSegmentedButton(head, values=[VIEW_LISTS, VIEW_FIND], command=self._show_view,
                                                  height=32)
        self.view_switch.grid(row=0, column=2, sticky="e")
        self.mini_btn = ctk.CTkButton(head, text="🗗 Mini", width=78, height=32, command=self.open_mini)
        self.mini_btn.grid(row=0, column=3, padx=(8, 0))
        self.eq_btn = ctk.CTkButton(head, text="🎛 EQ", width=64, height=32, command=self.open_eq)
        self.eq_btn.grid(row=0, column=4, padx=(8, 0))
        self.menu_btn = ctk.CTkButton(head, text="⚙", width=40, height=32, command=self._open_player_menu)
        self.menu_btn.grid(row=0, column=5, padx=(8, 0))

    def player_menu_items(self):
        """The ⚙ menu: cross-fade length, the mini player, the keyboard shortcuts."""
        fade = self.store.state["fade"]
        fades = [((("● " if s == fade else "   ") + (f"{s} sn" if s else "Kapalı")), lambda s=s: self.set_fade(s))
                 for s in FADE_CHOICES]
        items = [("🎚 Şarkılar arası geçiş", fades), ("🎛 Ekolayzır…", self.open_eq), ("🗗 Mini oynatıcı", self.open_mini)]
        shortcuts = getattr(self.app, "open_shortcuts", None)
        if shortcuts:
            items += [None, ("⌨ Klavye kısayolları  (F1)", shortcuts)]
        return items

    def _build_menu_bar(self):
        """"Nostalji": the player's commands in a menu bar too, like the players of those days."""
        bar = self.menubar = tk.Menu(self, tearoff=0)
        mode = lambda: self._on_mode(MODE_DOWNLOAD)     # noqa: E731
        groups = (
            ("Dosya", [("Dosya ekle…", self._add_files), ("Klasör ekle…", self._add_folder), None,
                       ("İndirme moduna geç", mode)]),
            ("Liste", [("Yeni liste…", self._new_list), ("Yeniden adlandır…", self._rename_list),
                       ("Listeyi sil", self._delete_list), None, ("Karıştır", self._shuffle_list),
                       ("Karıştırmayı geri al", self._undo_shuffle), ("Listeyi temizle", self._clear_list)]),
            ("Çalma", [("Çal / duraklat", self._toggle), ("Önceki", self._previous), ("Sonraki", self._next),
                       ("Durdur", self._stop), None, ("Tekrar", self._cycle_repeat)]),
            ("Araçlar", [("Şarkı bul", lambda: self._show_view(VIEW_FIND)),
                         ("Çalma listelerim", lambda: self._show_view(VIEW_LISTS)), None,
                         ("Ekolayzır…", self.open_eq), ("Mini oynatıcı", self.open_mini),
                         ("Şarkı sözleri", self.open_lyrics)]),
            ("Yardım", [("Klavye kısayolları", lambda: getattr(self.app, "open_shortcuts", lambda: None)())]),
        )
        for label, entries in groups:
            menu = tk.Menu(bar, tearoff=0)
            for entry in entries:
                if entry is None:
                    menu.add_separator()
                else:
                    menu.add_command(label=entry[0], command=entry[1])
            bar.add_cascade(label=label, menu=menu)
        tk.Toplevel.configure(self, menu=bar)

    def _open_player_menu(self):
        menu = tk.Menu(self, tearoff=0)
        self._fill_menu(menu, self.player_menu_items())
        x = self.menu_btn.winfo_rootx()
        y = self.menu_btn.winfo_rooty() + self.menu_btn.winfo_height()
        self._popup(menu, type("E", (), {"x_root": x, "y_root": y})())

    # ------------------------------------------------------------------ 🎛 equalizer
    def apply_eq(self, gains, remember=True) -> bool:
        """Put this equalizer setting on the sound (both voices of a cross-fade). False: not possible here."""
        gains = equalizer.clean(gains)
        text = equalizer.ffmpeg_filter(gains)
        ok = True
        for backend in (self.controller.backend, self.controller.spare):
            if backend is not None and hasattr(backend, "set_filter"):
                ok = backend.set_filter(text) and ok
        if ok and remember:
            self.store.set_state(eq=gains)
        return ok

    def open_eq(self):
        from .eq_ui import EqualizerWindow
        try:
            if self.eq_window is not None and self.eq_window.winfo_exists():
                self.eq_window.deiconify()
                self.eq_window.lift()
                return self.eq_window
        except tk.TclError:
            pass
        self.eq_window = EqualizerWindow(self)
        return self.eq_window

    def set_fade(self, seconds):
        self.store.set_state(fade=int(seconds))
        self.controller.fade_ms = int(seconds) * 1000
        self.note(f"🎚 Şarkılar artık {seconds} saniyede birbirine geçecek" if seconds
                  else "🎚 Şarkılar arası geçiş kapandı: her şarkı bitince öbürü başlar")

    def _build_toolbars(self):
        # the lists: which one is shown, make / rename / delete, and a search inside it
        bar = self.list_bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.columnconfigure(5, weight=1)
        ctk.CTkLabel(bar, text="Çalma listesi:", text_color="gray").grid(row=0, column=0, padx=(0, 6))
        self.list_menu = ctk.CTkOptionMenu(bar, values=["-"], width=200, command=self._select_list)
        self.list_menu.grid(row=0, column=1)
        self.edit_buttons = []          # what a smart list (filled by itself) cannot do
        for col, (text, cmd) in enumerate((("＋", self._new_list), ("✎", self._rename_list),
                                           ("🗑", self._delete_list)), start=2):
            b = ctk.CTkButton(bar, text=text, width=36, command=cmd)
            b.grid(row=0, column=col, padx=(6, 0))
            if text != "＋":
                self.edit_buttons.append(b)
        self.filter_entry = ctk.CTkEntry(bar, placeholder_text="🔎 Bu listede ara", width=200)
        self.filter_entry.grid(row=0, column=5, sticky="e", padx=(12, 0))
        self.filter_entry.bind("<KeyRelease>", lambda e: self._apply_filter(self.filter_entry.get()))
        self.filter_entry.bind("<Escape>", lambda e: self._clear_filter() or "break")

        # finding songs on the internet
        bar = self.find_bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(bar, placeholder_text="Şarkı adı ya da YouTube linki yaz…", height=34)
        self.search_entry.grid(row=0, column=0, sticky="ew")
        self.search_entry.bind("<Return>", self._on_search_return)
        self.search_entry.bind("<KeyRelease>", self._on_search_key, add="+")
        self.search_entry.bind("<FocusIn>", lambda e: self._show_suggestions(), add="+")
        self.search_entry.bind("<FocusOut>", lambda e: self.after(200, self._hide_suggestions_if_away), add="+")
        self.search_entry.bind("<Down>", lambda e: self._move_suggestion(+1) or "break")
        self.search_entry.bind("<Up>", lambda e: self._move_suggestion(-1) or "break")
        self.search_entry.bind("<Escape>", lambda e: self._hide_suggestions() or "break")
        self.suggest_box = ctk.CTkFrame(self, corner_radius=10, border_width=1)
        # only that singer's / channel's songs; left empty it changes nothing
        self.artist_entry = ctk.CTkEntry(bar, placeholder_text="Sanatçı / kanal (boş da olur)", width=220, height=34)
        self.artist_entry.grid(row=0, column=1, padx=(8, 0))
        self.artist_entry.bind("<Return>", lambda e: self._search() or "break")
        self.artist_entry.bind("<FocusIn>", lambda e: self._hide_suggestions(), add="+")
        self.search_btn = ctk.CTkButton(bar, text="Ara", width=90, height=34, command=self._search)
        self.search_btn.grid(row=0, column=2, padx=(8, 0))

    def _make_tree(self, parent, columns):
        tree = ttk.Treeview(parent, columns=[c[0] for c in columns], show="headings",
                            selectmode="extended", style="Music.Treeview")
        for name, text, width, anchor, stretch in columns:
            tree.heading(name, text=text, anchor=anchor)
            tree.column(name, width=width, minwidth=44, anchor=anchor, stretch=stretch)
        tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        if look.is_nostalgia():
            bar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        else:
            bar = ctk.CTkScrollbar(parent, command=tree.yview)
        bar.grid(row=0, column=1, sticky="ns", pady=8, padx=(0, 4))
        tree.configure(yscrollcommand=bar.set)
        return tree

    def _build_table(self):
        box = self.list_box = ctk.CTkFrame(self)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.tree = self._make_tree(box, (("no", "#", 56, "center", False),
                                          ("title", "Parça", 320, "w", True),
                                          ("artist", "Sanatçı", 190, "w", False),
                                          ("time", "Süre", 70, "e", False)))
        for column in SORT_COLUMNS:
            self.tree.heading(column, command=lambda c=column: self._sort(c))
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._track_menu)
        hint_bg = look.N_FIELD if look.is_nostalgia() else "transparent"     # on the white table
        self.empty_hint = ctk.CTkLabel(box, text="Liste bomboş.\n“＋ Dosya” ya da “📁 Klasör” ile müzik ekle,\n"
                                                 "ya da “🔍 Şarkı bul” ile internetten bul.",
                                       text_color="gray", justify="center", fg_color=hint_bg)

    def _build_results(self):
        box = self.find_box = ctk.CTkFrame(self)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.results_tree = self._make_tree(box, (("title", "Şarkı", 340, "w", True),
                                                  ("channel", "Sanatçı / kanal", 170, "w", False),
                                                  ("views", "Dinlenme", 80, "e", False),
                                                  ("time", "Süre", 64, "e", False),
                                                  ("state", "Durum", 84, "center", False)))
        self.results_tree.bind("<Double-Button-1>", self._on_result_double_click)
        self.results_tree.bind("<Return>", lambda e: self._download_selected() or "break")
        self.results_tree.bind("<Button-3>", self._result_menu)
        self.find_hint = ctk.CTkLabel(box, text="Dinlemek istediğin şarkıyı yukarıya yaz, Enter'a bas.\n"
                                                "Beğendiğini çift tıkla: MP3 olarak iner, sonra hangi listeye\n"
                                                "koyacağımı sorarım.",
                                      text_color="gray", justify="center",
                                      fg_color=look.N_FIELD if look.is_nostalgia() else "transparent")

    def _build_list_buttons(self):
        row = self.list_buttons = ctk.CTkFrame(self, fg_color="transparent")
        row.columnconfigure(10, weight=1)
        buttons = (("＋ Dosya", self._add_files), ("📁 Klasör", self._add_folder),
                   ("▲", lambda: self._move(-1)), ("▼", lambda: self._move(+1)),
                   ("✖ Kaldır", self._remove_selected), ("Listeyi temizle", self._clear_list),
                   ("🔀 Karıştır", self._shuffle_list))
        for col, (text, cmd) in enumerate(buttons):
            b = ctk.CTkButton(row, text=text, width=36 if len(text) == 1 else 100, command=cmd)
            b.grid(row=0, column=col, padx=(0, 6))
            if text != "🔀 Karıştır":
                self.edit_buttons.append(b)
        self.queue_btn = ctk.CTkButton(row, text="📋 Sıra", width=90, command=self._open_queue_menu)
        self.queue_btn.grid(row=0, column=len(buttons), padx=(0, 6))
        self.count_label = ctk.CTkLabel(row, text="", text_color="gray")
        self.count_label.grid(row=0, column=10, sticky="e")

    def _build_find_buttons(self):
        row = self.find_buttons = ctk.CTkFrame(self, fg_color="transparent")
        row.columnconfigure(2, weight=1)
        self.download_btn = ctk.CTkButton(row, text="⬇ İndir (MP3)", width=130, command=self._download_selected)
        self.download_btn.grid(row=0, column=0, padx=(0, 6))
        self.preview_btn = ctk.CTkButton(row, text="🎧 Önizle", width=100, command=self._preview_selected)
        self.preview_btn.grid(row=0, column=1, padx=(0, 6))
        ctk.CTkButton(row, text="📂 İnenler", width=100, command=self._open_music_folder).grid(row=0, column=2)
        self.import_btn = ctk.CTkButton(row, text="", width=150, command=self._download_all)
        self.find_label = ctk.CTkLabel(row, text="", text_color="gray")
        self.find_label.grid(row=0, column=4, sticky="e")
        row.columnconfigure(4, weight=1)
        row.columnconfigure(2, weight=0)

    def _build_player(self):
        box = ctk.CTkFrame(self)
        box.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 4))
        box.columnconfigure(1, weight=1)
        # The label always holds a real image (never None): customtkinter does not let go of a
        # picture that was removed with image=None, and Tk then fails on the next change.
        self._placeholder = placeholder_image()
        self.cover_label = ctk.CTkLabel(box, text="♪", image=self._placeholder, compound="center",
                                        width=COVER_PX, height=COVER_PX, fg_color="transparent",
                                        text_color=("#B7A3C2", "#5A4668"), font=ctk.CTkFont(size=44))
        self.cover_label.grid(row=0, column=0, rowspan=2, padx=(14, 4), pady=14, sticky="n")
        body = ctk.CTkFrame(box, fg_color="transparent")
        body.grid(row=0, column=1, rowspan=2, sticky="nsew", pady=(8, 8), padx=(8, 0))
        body.columnconfigure(1, weight=1)

        self.now_label = ctk.CTkLabel(body, text="Şu an bir şey çalmıyor", anchor="w",
                                      font=ctk.CTkFont(size=16, weight="bold"))
        self.now_label.grid(row=0, column=0, columnspan=3, sticky="ew", padx=(6, 118))
        # pinned to the corner, outside the grid: showing / hiding it never moves the controls
        self.lyrics_btn = ctk.CTkButton(body, text="🎤 Sözler", width=96, height=28, command=self.open_lyrics)
        self.sub_label = ctk.CTkLabel(body, text=" ", anchor="w", text_color="gray")
        self.sub_label.grid(row=1, column=0, columnspan=3, sticky="ew", padx=(6, 14))
        self.pos_label = ctk.CTkLabel(body, text="0:00", width=44, text_color="gray")
        self.pos_label.grid(row=2, column=0, padx=(2, 4))
        self.seek = ctk.CTkSlider(body, from_=0, to=1000, command=self._on_seek_drag)
        self.seek.set(0)
        self.seek.grid(row=2, column=1, sticky="ew", pady=6)
        self.seek.bind("<ButtonPress-1>", lambda e: setattr(self, "_dragging", True), add="+")
        self.seek.bind("<ButtonRelease-1>", self._on_seek_release, add="+")
        self.len_label = ctk.CTkLabel(body, text="0:00", width=44, text_color="gray")
        self.len_label.grid(row=2, column=2, padx=(4, 14))

        ctl = ctk.CTkFrame(body, fg_color="transparent")
        ctl.grid(row=3, column=0, columnspan=3, sticky="ew")
        ctl.columnconfigure(5, weight=1)
        self.prev_btn = ctk.CTkButton(ctl, text="⏮", width=44, command=self._previous)
        self.play_btn = ctk.CTkButton(ctl, text=PLAY_ICON, width=60, font=ctk.CTkFont(size=18),
                                      command=self._toggle)
        self.next_btn = ctk.CTkButton(ctl, text="⏭", width=44, command=self._next)
        self.stop_btn = ctk.CTkButton(ctl, text="⏹", width=44, command=self._stop)
        for col, b in enumerate((self.prev_btn, self.play_btn, self.next_btn, self.stop_btn)):
            b.grid(row=0, column=col, padx=(0, 6))
        self.shuffle_var = ctk.BooleanVar(value=self.controller.shuffle)
        ctk.CTkCheckBox(ctl, text="🔀 Karışık", variable=self.shuffle_var, width=90,
                        command=self._on_shuffle).grid(row=0, column=4, padx=(8, 6))
        self.repeat_btn = ctk.CTkButton(ctl, text="", width=104, command=self._cycle_repeat)
        self.repeat_btn.grid(row=0, column=5, sticky="w")
        self.sleep_menu = ctk.CTkOptionMenu(ctl, values=SLEEP_CHOICES, width=128, command=self._set_sleep)
        self.sleep_menu.set(SLEEP_OFF)
        self.sleep_menu.grid(row=0, column=6, padx=(6, 6))
        ctk.CTkLabel(ctl, text="🔊", text_color="gray").grid(row=0, column=7, padx=(4, 2))
        self.volume = ctk.CTkSlider(ctl, from_=0, to=100, width=110, command=self._on_volume)
        self.volume.set(self.store.state["volume"])
        self.volume.grid(row=0, column=8, padx=(0, 6))
        self._update_repeat_text()

        notes = ctk.CTkFrame(self, fg_color="transparent")
        notes.grid(row=5, column=0, sticky="ew", padx=20)
        notes.columnconfigure(0, weight=1)
        self.note_label = ctk.CTkLabel(notes, text="", anchor="w", text_color="gray")
        self.note_label.grid(row=0, column=0, sticky="ew")
        self.dl_label = ctk.CTkLabel(notes, text="", anchor="e", text_color="gray")
        self.dl_label.grid(row=0, column=1, sticky="e")

    def _bind_keys(self):
        self.bind("<space>", self._key_space)
        self.tree.bind("<space>", self._key_space)           # before the table's own "toggle selection"
        self.results_tree.bind("<space>", self._key_space)
        self.tree.bind("<Return>", lambda e: self._play_selected() or "break")
        self.tree.bind("<Delete>", lambda e: self._remove_selected() or "break")
        self.tree.bind("<Control-Up>", lambda e: self._move(-1) or "break")
        self.tree.bind("<Control-Down>", lambda e: self._move(+1) or "break")
        self.tree.bind("<Control-a>", lambda e: self.tree.selection_set(self.tree.get_children()) or "break")
        self.bind("<Control-f>", lambda e: self._focus_search() or "break")
        self.bind("<Control-z>", lambda e: self._undo_shuffle() or "break")
        self.bind("<F1>", lambda e: getattr(self.app, "open_shortcuts", lambda: None)() or "break")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_lyrics_button(), add="+")

    def _key_space(self, event):
        if isinstance(event.widget, (tk.Entry, tk.Text)) or "entry" in str(event.widget).lower():
            return None
        self._toggle()
        return "break"

    def _focus_search(self):
        (self.search_entry if self.view == VIEW_FIND else self.filter_entry).focus_set()

    # ------------------------------------------------------------------ the two views
    def _show_view(self, view):
        """'🎵 Listelerim' (the playlists) or '🔍 Şarkı bul' (search the internet)."""
        self.view = view
        self.view_switch.set(view)
        lists = view == VIEW_LISTS
        shown, hidden = ((self.list_bar, self.list_box, self.list_buttons),
                         (self.find_bar, self.find_box, self.find_buttons))
        if not lists:
            shown, hidden = hidden, shown
        for w in hidden:
            w.grid_forget()
        shown[0].grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 2))
        shown[1].grid(row=2, column=0, sticky="nsew", padx=16, pady=(4, 4))
        shown[2].grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 6))
        if not lists:
            self._refresh_results()
            self.search_entry.focus_set()

    # ------------------------------------------------------------------ colours
    def recolor(self):
        """The plain ttk table does not follow the theme by itself."""
        style_table(self)
        MusicWindow._ttk_ready = True
        win = getattr(self, "lyrics_window", None)
        try:
            if win is not None and win.winfo_exists() and win.data:     # its line colours follow the theme too
                current, win.current = win.current, -1
                win._fill()
                if current >= 0:
                    win._mark(current)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ playlists
    def _refresh_lists(self):
        names = self.store.names()
        self.list_menu.configure(values=names)
        if self.viewed not in names:
            self.viewed = names[0]
        self.list_menu.set(self.viewed)
        self._refresh_tracks()

    def reload(self):
        """The lists were changed from outside (a download finished into one): show it and keep playing."""
        if self._closed:
            return
        self._sync_queue()
        keep = self._selected()
        self._refresh_lists()
        keep = [str(i) for i in keep if self.tree.exists(str(i))]
        if keep:
            self.tree.selection_set(keep)

    def _select_list(self, name):
        self.viewed = name
        if playlists.is_smart(name) and name != self.playing_list:     # up to date when it is opened
            self.store.refresh_smart(only=name)
        self.store.set_state(last=name)
        self.sort_by = (None, False)
        self._refresh_tracks()

    def show_list(self, name):
        """Open this list in the window (after a found song was put into it)."""
        if name in self.store.names():
            self.viewed = name
            self.store.set_state(last=name)
            self._refresh_lists()

    def note(self, text, seconds=6):
        self.note_label.configure(text=text)
        self._note_until = time.time() + seconds

    def _ask_name(self, title, text, initial=""):
        dialog = ctk.CTkInputDialog(text=text, title=title)
        set_window_icon(dialog)
        if initial:
            dialog.after(150, lambda: self._prefill(dialog, initial))
        answer = dialog.get_input()
        return answer.strip() if answer and answer.strip() else None

    @staticmethod
    def _prefill(dialog, initial):
        try:
            dialog._entry.insert(0, initial)
            dialog._entry.select_range(0, "end")
        except Exception:  # noqa: BLE001 - only a convenience
            pass

    def _confirm(self, text) -> bool:
        return messagebox.askyesno("DISO", text, parent=self)

    def _new_list(self):
        name = self._ask_name("Yeni liste", "Çalma listesinin adı:")
        if name:
            self.viewed = self.store.create(name)
            self.store.set_state(last=self.viewed)
            self._refresh_lists()

    def _rename_list(self):
        name = self._ask_name("Adı değiştir", "Yeni ad:", self.viewed)
        if name:
            if self.playing_list == self.viewed:
                self.playing_list = self.store.rename(self.viewed, name)
                self.viewed = self.playing_list
            else:
                self.viewed = self.store.rename(self.viewed, name)
            self._refresh_lists()

    def _delete_list(self):
        count = len(self.store.tracks(self.viewed))
        if not self._confirm(f"“{self.viewed}” listesi silinsin mi? ({count} parça)\nDosyalar silinmez."):
            return
        if self.playing_list == self.viewed:
            self.controller.stop()
            self.controller.set_tracks([])
            self.playing_list = None
        self.viewed = self.store.delete(self.viewed)
        self._refresh_lists()

    # ------------------------------------------------------------------ the table
    @staticmethod
    def _row_values(i, track, marker):
        artist, name = artist_and_title(track)
        if not os.path.isfile(track["path"]):
            name += i18n.tr("   (dosya yok)")
        length = fmt_time(track["duration"]) if track.get("duration") else ""
        return ("▶" if marker else str(i + 1), name, artist, length)

    def _refresh_tracks(self, select=()):
        tracks = self.store.tracks(self.viewed)
        self.tree.delete(*self.tree.get_children())
        marker = self._marker_index()
        words = self.filter_text.casefold().split()
        for i, t in enumerate(tracks):
            if not words or matches(t, words):
                self.tree.insert("", "end", iid=str(i), values=self._row_values(i, t, i == marker))
        if select:
            self.tree.selection_set([str(i) for i in select if 0 <= i < len(tracks) and self.tree.exists(str(i))])
        self._shown_marker = marker
        smart = playlists.is_smart(self.viewed)
        for b in self.edit_buttons:
            set_if_changed(b, state="disabled" if smart else "normal")
        self._update_count()
        if not tracks and smart:
            self.empty_hint.configure(text=SMART_EMPTY.get(self.viewed, ""))
            self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")
        elif not tracks:
            self.empty_hint.configure(text="Liste bomboş.\n“＋ Dosya” ya da “📁 Klasör” ile müzik ekle,\n"
                                           "ya da “🔍 Şarkı bul” ile internetten bul.")
            self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")
        elif not self.tree.get_children():
            self.empty_hint.configure(text=f"“{self.filter_text.strip()}” ile eşleşen parça yok.")
            self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.empty_hint.place_forget()
        self._request_tags(tracks)

    def _update_count(self):
        tracks = self.store.tracks(self.viewed)
        if not tracks:
            self.count_label.configure(text="")
            return
        shown = len(self.tree.get_children())
        text = f"{shown} / {len(tracks)} parça" if self.filter_text.strip() else f"{len(tracks)} parça"
        total, complete = self.store.total_ms(self.viewed)
        if complete and total:
            text += f" • {fmt_total(total)}"
        if playlists.is_smart(self.viewed):
            text = "✨ Kendiliğinden dolar • " + text
        self.count_label.configure(text=text)

    def _apply_filter(self, text):
        if text != self.filter_text:
            self.filter_text = text
            self._refresh_tracks()

    def _clear_filter(self):
        self.filter_entry.delete(0, "end")
        self._apply_filter("")

    def _sort(self, column):
        """A click on a column title: the list is put in that order (a second click turns it round)."""
        if not self.store.tracks(self.viewed):
            return
        last, reverse = self.sort_by
        reverse = (not reverse) if last == column else False
        self.sort_by = (column, reverse)
        self.store.sort(self.viewed, SORT_COLUMNS[column], reverse)
        self._sync_queue()
        self._refresh_tracks()
        what = {"title": "parça adına", "artist": "sanatçıya", "time": "süreye"}[column]
        self.note(f"Liste {what} göre sıralandı" + (" (tersten)" if reverse else ""))

    def _marker_index(self):
        c = self.controller
        if self.playing_list == self.viewed and c.state != "stopped" and c.index >= 0 and c.extra is None:
            return c.index
        return None

    def _selected(self):
        return sorted(int(i) for i in self.tree.selection())

    def _update_marker(self):
        """Move the ▶ without rebuilding the table (keeps the selection and the scroll position)."""
        marker = self._marker_index()
        if marker == self._shown_marker:
            return
        tracks = self.store.tracks(self.viewed)
        for i in {self._shown_marker, marker}:
            if i is not None and 0 <= i < len(tracks) and self.tree.exists(str(i)):
                self.tree.item(str(i), values=self._row_values(i, tracks[i], i == marker))
        self._shown_marker = marker
        if marker is not None and self.tree.exists(str(marker)):
            self.tree.see(str(marker))

    def _on_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self._play_selected()

    def _sync_queue(self):
        """The list being played was edited: the queue follows, the current track keeps playing."""
        if self.playing_list == self.viewed:
            self.controller.set_tracks(self.store.tracks(self.viewed), keep_current=True)

    def _pick_files(self):
        patterns = " ".join("*" + e for e in AUDIO_EXTENSIONS)
        return filedialog.askopenfilenames(parent=self, title="Müzik dosyaları seç",
                                           filetypes=[("Müzik dosyaları", patterns), ("Hepsi", "*.*")])

    def _pick_folder(self):
        return filedialog.askdirectory(parent=self, title="Müzik klasörü seç")

    def _add_files(self):
        paths = self._pick_files()
        if paths:
            n = self.store.add(self.viewed, paths)
            self.note(f"{n} parça eklendi" if n else "Seçtiklerinin arasında müzik dosyası yok")
            self._sync_queue()
            self._refresh_tracks()

    def _add_folder(self):
        folder = self._pick_folder()
        if folder:
            n = self.store.add_folder(self.viewed, folder)
            self.note(f"{n} parça eklendi" if n else "O klasörde müzik bulamadım")
            self._sync_queue()
            self._refresh_tracks()

    def _move(self, offset):
        picked = self._selected()
        if picked and self.filter_text.strip():
            self.note("Sırayı değiştirmek için önce aramayı temizle")
            return
        if picked:
            self._move_to(self.store.move(self.viewed, picked, offset))

    def _move_to(self, new_indexes):
        self._sync_queue()
        self._refresh_tracks(select=new_indexes)
        if new_indexes and self.tree.exists(str(new_indexes[0])):
            self.tree.see(str(new_indexes[0]))

    def _remove_selected(self):
        picked = self._selected()
        if picked:
            self.store.remove(self.viewed, picked)
            self._sync_queue()
            self._refresh_tracks()

    def _clear_list(self):
        if self.store.tracks(self.viewed) and self._confirm(f"“{self.viewed}” listesindeki tüm parçalar çıkarılsın mı?"):
            self.store.clear(self.viewed)
            self._sync_queue()
            self._refresh_tracks()

    # ------------------------------------------------------------------ right-click menus
    def _popup(self, menu, event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def track_menu_items(self):
        """[(label, command or [(label, command), ...]), ...] for the selected tracks (None = a line)."""
        picked = self._selected()
        if not picked:
            return []
        others = [n for n in self.store.user_names() if n != self.viewed]
        tracks = self.store.tracks(self.viewed)
        first = tracks[picked[0]] if picked[0] < len(tracks) else None
        has = bool(first) and lyrics.has_lyrics(first["path"])
        words = "🎤 Şarkı sözlerini göster" if has else "🎤 Şarkı sözlerini internette bul"
        again = [("🔄 Sözler yanlış, yeniden bul", lambda: self.find_lyrics(first))] if has else []
        return [("▶ Çal", self._play_selected),
                ("⏭ Sıradaki olarak çal", self._play_next_selected),
                ("➕ Sıraya ekle", self._queue_selected),
                ("📂 Klasörde göster", self._reveal_selected),
                (words, self._lyrics_for_selected), *again,
                ("➕ Başka listeye ekle", [(n, lambda n=n: self._copy_selected(n)) for n in others]
                 + [("＋ Yeni liste…", self._copy_to_new_list)]),
                *([] if playlists.is_smart(self.viewed) else [None, ("✖ Listeden çıkar", self._remove_selected)])]

    def _fill_menu(self, menu, items):
        for entry in items:
            if entry is None:
                menu.add_separator()
            elif isinstance(entry[1], list):
                sub = tk.Menu(menu, tearoff=0)
                self._fill_menu(sub, entry[1])
                menu.add_cascade(label=entry[0], menu=sub)
            else:
                menu.add_command(label=entry[0], command=entry[1])

    def _track_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        if row not in self.tree.selection():
            self.tree.selection_set(row)
        menu = tk.Menu(self, tearoff=0)
        self._fill_menu(menu, self.track_menu_items())
        self._popup(menu, event)

    def _picked_tracks(self):
        tracks = self.store.tracks(self.viewed)
        return [tracks[i] for i in self._selected() if i < len(tracks)]

    def _play_next_selected(self):
        picked = self._picked_tracks()
        if not picked:
            return
        if self.controller.state == "stopped":                 # nothing plays: "next" means "now"
            self.controller.add_to_queue(picked)
            self.controller.next()
            self._after_action()
            self.note(f"▶ {track_label(picked[0])}")
            return
        self.controller.play_next(picked)
        self._update_queue_button()
        self.note(f"⏭ Bu şarkıdan sonra: {track_label(picked[0])}" if len(picked) == 1
                  else f"⏭ Bu şarkıdan sonra {len(picked)} şarkı çalacak")

    def _queue_selected(self):
        picked = self._picked_tracks()
        if picked:
            self.controller.add_to_queue(picked)
            self._update_queue_button()
            self.note(f"➕ Sıraya eklendi ({len(self.controller.queue)} şarkı sırada)")

    def queue_menu_items(self):
        """The 📋 button: what is lined up (a click takes it out), and 'clear'."""
        items = [(f"{i + 1}. {track_label(t)}   ✖", lambda i=i: self._unqueue(i))
                 for i, t in enumerate(self.controller.queue[:25])]
        if len(self.controller.queue) > 25:
            items.append((f"… ve {len(self.controller.queue) - 25} şarkı daha", lambda: None))
        return items + [None, ("Sırayı temizle", self._clear_queue)] if items else [("Sırada şarkı yok", lambda: None)]

    def _open_queue_menu(self):
        menu = tk.Menu(self, tearoff=0)
        self._fill_menu(menu, self.queue_menu_items())
        b = self.queue_btn
        self._popup(menu, type("E", (), {"x_root": b.winfo_rootx(), "y_root": b.winfo_rooty() - 10})())

    def _unqueue(self, i):
        if 0 <= i < len(self.controller.queue):
            del self.controller.queue[i]
            self._update_queue_button()

    def _clear_queue(self):
        self.controller.queue.clear()
        self._update_queue_button()
        self.note("Sıra temizlendi")

    def _update_queue_button(self):
        n = len(self.controller.queue)
        set_if_changed(self.queue_btn, text=f"📋 Sıra ({n})" if n else "📋 Sıra")

    def _reveal_selected(self):
        tracks = self.store.tracks(self.viewed)
        picked = self._selected()
        if picked and picked[0] < len(tracks):
            path = tracks[picked[0]]["path"]
            if os.path.isfile(path):
                open_in_file_manager(path)
            else:
                self.note("Bu parçanın dosyası yerinde yok")

    def _copy_selected(self, name):
        tracks = self.store.tracks(self.viewed)
        picked = [tracks[i] for i in self._selected() if i < len(tracks)]
        n = self.store.copy_to(name, picked)
        self.reload()                                   # the new list shows up in the menu; the selection stays
        self.note(f"{n} parça “{name}” listesine eklendi" if n else f"Hepsi zaten “{name}” listesinde")

    def _copy_to_new_list(self):
        name = self._ask_name("Yeni liste", "Çalma listesinin adı:")
        if name:
            self._copy_selected(self.store.create(name))

    def _shuffle_list(self):
        """'🔀 Karıştır': the list gets a new random order for good (Ctrl+Z brings the old one back)."""
        if len(self.store.tracks(self.viewed)) < 2:
            self.note("Karıştırmak için listede en az iki parça olmalı")
            return
        self._undo_order = (self.viewed, self.store.shuffle(self.viewed))
        self._sync_queue()
        self._refresh_tracks()
        self.note("🔀 Liste karıştırıldı. Beğenmediysen Ctrl+Z ile eski sırasına dönerim.", 10)

    def _undo_shuffle(self):
        if not self._undo_order or isinstance(self.focus_get(), tk.Entry):
            return
        name, order = self._undo_order
        self._undo_order = None
        self.store.set_order(name, order)
        if self.viewed == name:
            self._sync_queue()
            self._refresh_tracks()
        self.note("↶ Eski sıraya döndüm")

    # ------------------------------------------------------------------ lyrics
    def _lyrics_track(self):
        """The song the 🎤 button is about: the one playing, else the one chosen in the list."""
        c = self.controller
        if c.state != "stopped":
            return c.current_track()
        picked = self._selected()
        tracks = self.store.tracks(self.viewed)
        return tracks[picked[0]] if picked and picked[0] < len(tracks) else None

    def _update_lyrics_button(self):
        track = self._lyrics_track()
        show = bool(track) and lyrics.has_lyrics(track["path"])
        if show != self._lyrics_shown:
            self._lyrics_shown = show
            if show:
                self.lyrics_btn.place(relx=1.0, x=-14, y=2, anchor="ne")
            else:
                self.lyrics_btn.place_forget()

    def open_lyrics(self, track=None):
        track = track or self._lyrics_track()
        if not track:
            return
        if self.lyrics_window is not None:
            try:
                if self.lyrics_window.winfo_exists():
                    self.lyrics_window.show(track)
                    self.lyrics_window.deiconify()
                    self.lyrics_window.lift()
                    return
            except tk.TclError:
                pass
        self.lyrics_window = LyricsWindow(self, on_seek=self._seek_ms, on_find=self.find_lyrics)
        self.lyrics_window.show(track)

    def find_lyrics(self, track) -> bool:
        """Look the song's lyrics up on the internet (in the background)."""
        if not track or not os.path.isfile(track["path"]):
            self.note("Bu parçanın dosyası yerinde yok")
            return False
        artist, title = artist_and_title(track)
        self._lyrics_asked.add(track["path"])
        video = getattr(self.app, "video_id_for", lambda path: "")(track["path"])
        if self.lyrics_fetcher.find(track["path"], artist, title, (track.get("duration") or 0) / 1000,
                                    video_id=video):
            self.note(f"🎤 “{track_label(track)}” için şarkı sözlerini arıyorum…", 30)
        return True

    def _lyrics_for_selected(self):
        tracks = self.store.tracks(self.viewed)
        picked = self._selected()
        if not picked or picked[0] >= len(tracks):
            return
        track = tracks[picked[0]]
        if lyrics.has_lyrics(track["path"]):
            self.open_lyrics(track)
        else:
            self.find_lyrics(track)

    def _take_lyrics(self):
        for path, found, error in self.lyrics_fetcher.drain():
            asked = path in self._lyrics_asked
            self._lyrics_asked.discard(path)
            name = os.path.splitext(os.path.basename(path))[0]
            if found:
                self.note(f"🎤 “{name}” için şarkı sözlerini buldum. Sağdaki 🎤 Sözler düğmesine bas.", 10)
            elif asked:
                self.note(f"“{name}” için şarkı sözlerine bakamadım: bağlantıyı kontrol et" if error
                          else f"“{name}” için şarkı sözü bulamadım", 8)
            win = self.lyrics_window
            try:
                if (win is not None and win.winfo_exists() and win.path
                        and os.path.normcase(win.path) == os.path.normcase(path)):
                    win.show(win.track)
            except tk.TclError:
                pass
        self._update_lyrics_button()

    def _follow_lyrics(self):
        win = self.lyrics_window
        if win is None:
            return
        try:
            if not win.winfo_exists():
                self.lyrics_window = None
                return
        except tk.TclError:
            self.lyrics_window = None
            return
        c = self.controller
        if c.state != "stopped" and c.current_track():
            win.follow(c.current_track(), c.position_ms())

    def _seek_ms(self, ms):
        if self.controller.state != "stopped":
            self.controller.backend.seek(max(0, int(ms)))
            self._update_status()

    # ------------------------------------------------------------------ deleted files
    def _check_missing(self):
        """Look for deleted files on another thread (a big list on a slow disk must not stop the window)."""
        if self._checking:
            return
        self._checking = True

        def work():
            try:
                self._missing = self.store.missing_paths()
            except Exception:  # noqa: BLE001 - tried again next time
                log.exception("could not check the playlists for deleted files")
                self._missing = set()
            self._checking = False

        threading.Thread(target=work, daemon=True).start()

    def prune_missing(self, paths=None):
        """Take deleted files out of every list; returns how many tracks went."""
        paths = self.store.missing_paths() if paths is None else paths
        removed = self.store.prune(paths) if paths else {}
        if not removed:
            return 0
        if self.playing_list in removed:
            self.controller.set_tracks(self.store.tracks(self.playing_list), keep_current=True)
        if self._resume and self._resume[0] in removed:
            self._resume = self._saved_place(self._resume)
        self._refresh_lists()
        total = sum(removed.values())
        where = f"“{next(iter(removed))}” listesinden" if len(removed) == 1 else "listelerden"
        self.note(f"🗑 Dosyası silinen {total} parça {where} çıkarıldı", 8)
        return total

    # ------------------------------------------------------------------ tags and cover
    def _request_tags(self, tracks):
        for t in tracks:
            if not t.get("probed"):
                self.reader.request(t["path"])

    def _drain_reader(self):
        infos, covers = {}, []
        for kind, path, value in self.reader.drain():
            if kind == "tags":
                infos[path] = value
            else:
                covers.append((path, value))
        if infos and self.store.apply_tags(infos, persist=False):
            self._schedule_tags_save()
            self._refresh_rows_for(infos)
            self._update_count()
            self._show_now_playing()
        for path, jpg in covers:
            self._covers[path] = jpg
            if self._cover_path is not None and os.path.normcase(path) == os.path.normcase(self._cover_path):
                self._set_cover(jpg)

    def _refresh_rows_for(self, infos):
        wanted = {os.path.normcase(os.path.abspath(p)) for p in infos}
        marker = self._marker_index()
        for i, t in enumerate(self.store.tracks(self.viewed)):
            if os.path.normcase(os.path.abspath(t["path"])) in wanted and self.tree.exists(str(i)):
                self.tree.item(str(i), values=self._row_values(i, t, i == marker))

    def _schedule_tags_save(self):
        if self._tags_save is not None:
            self.after_cancel(self._tags_save)
        self._tags_save = self.after(SAVE_DELAY, self._save_tags)

    def _save_tags(self):
        self._tags_save = None
        self.store.save()

    def _set_cover(self, jpg):
        """Show the cover (or the placeholder when there is none)."""
        img = square_cover(jpg) if jpg else None
        if img is None:
            self.cover_label.configure(image=self._placeholder, text="♪")
            self._cover_image = None
            return
        img = rounded(img, img.width // 8)
        new = ctk.CTkImage(light_image=img, dark_image=img, size=(COVER_PX, COVER_PX))
        self.cover_label.configure(image=new, text="")
        self._cover_image = new

    def _show_now_playing(self):
        """Title, artist / album and the cover of the track that plays."""
        c = self.controller
        track = c.current_track() if c.state != "stopped" else None
        if track is None:
            resume = self._resume_track()
            set_if_changed(self.now_label, text=f"Kaldığın yer: {track_label(resume)}" if resume
                           else "Şu an bir şey çalmıyor")
            set_if_changed(self.sub_label, text=f"▶ ile {fmt_time(self._resume[2])}'den devam et" if resume else " ")
            if self._cover_path is not None:
                self._cover_path = None
                self._set_cover(None)
            return
        mark = {"playing": "", "preparing": "⏳  "}.get(c.state, "⏸  ")
        set_if_changed(self.now_label, text=mark + track_label(track))
        sub = " • ".join(x for x in (artist_and_title(track)[0], track.get("album")) if x)
        if c.state == "preparing":
            sub = "Çalmaya hazırlanıyor… (bu dosyayı ilk kez açıyorum, birkaç saniye sürer)"
        set_if_changed(self.sub_label, text=sub or " ")
        if self._cover_path != track["path"]:
            self._cover_path = track["path"]
            self._set_cover(None)                                  # not the previous track's picture
            if track["path"] in self._covers:
                self._set_cover(self._covers[track["path"]])
            else:
                self.reader.request_cover(track["path"])

    # ------------------------------------------------------------------ where the music stopped
    def _saved_place(self, old=None):
        """(list, index, ms) of the song that played when DISO was closed, if it is still there."""
        st = self.store.state
        name, path, ms = (old[0], st["resume_path"], old[2]) if old else (st["resume_list"], st["resume_path"],
                                                                          st["resume_ms"])
        tracks = self.store.tracks(name)
        for i, t in enumerate(tracks):
            if t["path"] == path and os.path.isfile(path):
                return name, i, ms
        return None

    def _resume_track(self):
        if not self._resume:
            return None
        name, i, _ = self._resume
        tracks = self.store.tracks(name)
        return tracks[i] if 0 <= i < len(tracks) else None

    def _remember_place(self):
        c = self.controller
        if c.state != "stopped" and self.playing_list and c.current_path():
            self.store.set_state(_persist=False, resume_list=self.playing_list, resume_path=c.current_path(),
                                 resume_ms=int(c.position_ms()))

    def _forget_place(self):
        self._resume = None
        self.store.set_state(_persist=False, resume_list="", resume_path="", resume_ms=0)

    def go_on(self):
        """Carry on with the song where it stopped (DISO started again with a new look, say)."""
        if self.controller.state == "stopped" and self._go_on():
            self._after_action()

    def _go_on(self) -> bool:
        """▶ with nothing playing and nothing chosen: carry on from where the music stopped last time."""
        track = self._resume_track()
        resume, self._resume = self._resume, None
        if track is None:
            return False
        name, i, ms = resume
        if name != self.viewed:
            self.show_list(name)
        self.controller.stop()
        self.controller.set_tracks(self.store.tracks(name))
        self.playing_list = name
        if self.controller.play_index(i) and ms > 0:
            self.controller.backend.seek(ms)
        return True

    # ------------------------------------------------------------------ playing
    def _load_viewed(self):
        """Make the shown list the play queue (unless it already is)."""
        if self.playing_list != self.viewed:
            self.controller.stop()
            self.controller.set_tracks(self.store.tracks(self.viewed))
            self.playing_list = self.viewed

    def _play_selected(self):
        picked = self._selected()
        tracks = self.store.tracks(self.viewed)
        if not tracks:
            return
        self._resume = None
        self._load_viewed()
        self.controller.play_index(picked[0] if picked else 0)
        self._after_action()

    def _toggle(self):
        if self.controller.state == "stopped":
            picked = self._selected()
            if picked or not self._go_on():
                self._resume = None
                self._load_viewed()
                if self.controller.tracks:
                    self.controller.play_index(picked[0] if picked else 0)
        else:
            self.controller.toggle()
        self._after_action()

    def _next(self):
        self._resume = None
        if not self.controller.tracks:
            self._load_viewed()
        self.controller.next()
        self._after_action()

    def _previous(self):
        self._resume = None
        if not self.controller.tracks:
            self._load_viewed()
        self.controller.previous(self.controller.position_ms())
        self._after_action()

    def _stop(self):
        self.controller.stop()
        self._forget_place()
        if self.sleep_at or self.sleep_after_track:             # nothing left to put to sleep
            self.sleep_at, self.sleep_after_track = None, False
            self._update_sleep_text()
        self._after_action()

    def _after_action(self):
        if self.controller.error:
            self.note(self.controller.error)
        self._update_status()

    def _on_seek_drag(self, value):
        if self._dragging:
            length = self.controller.length_ms()
            self.pos_label.configure(text=fmt_time(length * value / 1000))

    def _on_seek_release(self, event=None):
        self._dragging = False
        self.controller.seek_fraction(self.seek.get() / 1000)

    def _on_volume(self, value):
        self.controller.set_volume(int(value))
        self.store.set_state(_persist=False, volume=int(value))       # a drag makes dozens of calls:
        if self._volume_save is not None:
            self.after_cancel(self._volume_save)
        self._volume_save = self.after(500, self._save_volume)          # ... write the file once, after it

    def _save_volume(self):
        self._volume_save = None
        self.store.save()

    def _on_shuffle(self):
        self.controller.shuffle = bool(self.shuffle_var.get())
        self.store.set_state(shuffle=self.controller.shuffle)

    def _cycle_repeat(self):
        c = self.controller
        c.repeat = REPEAT_MODES[(REPEAT_MODES.index(c.repeat) + 1) % len(REPEAT_MODES)]
        self.store.set_state(repeat=c.repeat)
        self._update_repeat_text()

    def _update_repeat_text(self):
        self.repeat_btn.configure(text=f"🔁 Tekrar: {self.controller.repeat}")

    # ------------------------------------------------------------------ sleep timer
    def _set_sleep(self, choice):
        self.sleep_at, self.sleep_after_track = None, False
        if choice == SLEEP_TRACK:
            self.sleep_after_track = True
            self.note("😴 Bu parça bitince müziği durduracağım")
        elif choice != SLEEP_OFF:
            minutes = int(choice.split()[0])
            self.sleep_at = time.time() + minutes * 60
            self.note(f"😴 {minutes} dakika sonra müziği durduracağım")
        else:
            self.note("Uyku zamanlayıcısı kapandı")
        self._update_sleep_text()

    def _update_sleep_text(self):
        if self.sleep_at:
            left = max(1, int((self.sleep_at - time.time() + 59) // 60))
            if self.sleep_menu.get() != f"😴 {left} dk":
                self.sleep_menu.set(f"😴 {left} dk")
        elif self.sleep_after_track:
            if self.sleep_menu.get() != f"😴 {SLEEP_TRACK}":
                self.sleep_menu.set(f"😴 {SLEEP_TRACK}")
        elif self.sleep_menu.get() != SLEEP_OFF:
            self.sleep_menu.set(SLEEP_OFF)

    def _check_sleep(self):
        """Stop the music when the sleep time came or the chosen track ended (before moving on)."""
        c = self.controller
        if self.sleep_at and time.time() >= self.sleep_at:
            self.sleep_at = None
            if c.state != "stopped":
                self._remember_place()
                c.stop()
                self.note("😴 Uyku zamanı: müziği durdurdum. İyi uykular!", 30)
            self._update_sleep_text()
        elif self.sleep_after_track and c.state == "playing" and c.backend.finished():
            self.sleep_after_track = False
            c.stop()
            self.note("😴 Parça bitti, müziği durdurdum. İyi uykular!", 30)
            self._update_sleep_text()
        elif self.sleep_at:
            self._update_sleep_text()

    # ------------------------------------------------------------------ media keys
    def _check_keys(self):
        """Take the keyboard's media keys while music plays or is paused; give them back when it stops."""
        want = self.controller.state != "stopped"
        if want and not self.keys.active:
            self.keys.start()
        elif not want and self.keys.active:
            self.keys.stop()
        while True:
            try:
                key = self.keys.pressed.get_nowait()
            except Exception:  # noqa: BLE001 - queue.Empty
                break
            {"toggle": self._toggle, "next": self._next, "previous": self._previous,
             "stop": self._stop}.get(key, lambda: None)()

    # ------------------------------------------------------------------ finding songs
    def _search(self):
        query = " ".join(self.search_entry.get().split())
        artist = "" if is_url(query) else " ".join(self.artist_entry.get().split())   # a link is opened as it is
        if not query and not artist:
            self.find_label.configure(text="Önce ne arayacağımı yaz 🙂")
            return
        self._hide_suggestions()
        if query:
            self.store.remember_search(query)
        if artist:
            self.searcher.search(query, artist)
        else:
            self.searcher.search(query)
        self._search_started = time.time()
        self.search_btn.configure(state="disabled", text="Arıyor…")
        shown = f"{query} ({artist})" if query and artist else query or artist
        self.find_label.configure(text=f"“{shown}” aranıyor…")

    def _take_answer(self):
        answer = self.searcher.poll()
        if answer is None:
            started = getattr(self, "_search_started", None)
            if started and self.searcher.busy and time.time() - started >= 5:   # a slow connection: show it is alive
                set_if_changed(self.find_label, text=f"“{self.searcher.query}” aranıyor… "
                                                     f"({int(time.time() - started)} sn, bağlantı yavaş)")
            return
        self._search_started = None
        query, results, error = answer
        self.search_btn.configure(state="normal", text="Ara")
        self.results = results
        self.results_title = getattr(results, "title", "") if len(results) > 1 else ""
        self._refresh_results()
        if self.results_title:
            self.import_btn.configure(text=f"⬇ Hepsini indir → “{self.results_title[:28]}”")
            self.import_btn.grid(row=0, column=3, padx=(6, 0))
        else:
            self.import_btn.grid_forget()
        if error:
            self.find_label.configure(text="Arayamadım: " + error.splitlines()[0][:120])
        elif not results:
            self.find_label.configure(text=f"“{query}” için bir şey bulamadım, başka türlü yazmayı dene")
        elif self.results_title:
            self.find_label.configure(text=f"Bu bir çalma listesi: {len(results)} şarkı")
        else:
            self.find_label.configure(text=f"{len(results)} sonuç • çift tıkla ya da ⬇ İndir: MP3 olarak iner")

    # ------------------------------------------------------------------ a whole playlist / album at once
    def _download_all(self):
        """'⬇ Hepsini indir': every song of the opened list as MP3, into a playlist of the same name (in order)."""
        download = getattr(self.app, "download_playlist", None)
        if not (self.results and self.results_title and download):
            return
        added, name = download(list(self.results), self.results_title)
        self.import_btn.grid_forget()
        self.note(f"⬇ {added} şarkı iniyor; bittikçe sırasıyla “{name}” listesine giriyor" if added
                  else f"Bu listenin şarkıları zaten “{name}” listesinde ya da iniyor", 10)
        self._update_result_states()

    # ------------------------------------------------------------------ suggestions and the last searches
    def suggestion_rows(self, typed=None):
        """[(text, kind)] under the search box: the last searches (when nothing is typed, or the ones
        that start like it) and YouTube's suggestions; kind is "history" or "suggest"."""
        typed = (self.search_entry.get() if typed is None else typed).strip()
        history = self.store.state["searches"]
        if not typed:
            return [(q, "history") for q in history[:8]]
        low = typed.casefold()
        rows = [(q, "history") for q in history if q.casefold().startswith(low) and q.casefold() != low][:3]
        seen = {q.casefold() for q, _ in rows} | {low}
        rows += [(s, "suggest") for s in self._suggestions if s.casefold() not in seen][:8 - len(rows)]
        return rows

    _suggestions = ()

    def _on_search_key(self, event):
        if event.keysym in ("Return", "Escape", "Up", "Down", "Tab"):
            return
        self._suggest_index = -1
        if self._suggest_after is not None:
            self.after_cancel(self._suggest_after)
        typed = self.search_entry.get().strip()
        self._suggestions = [s for s in self._suggestions if s.casefold().startswith(typed.casefold()[:1])]
        self._show_suggestions()
        if len(typed) >= 2:
            self._suggest_after = self.after(250, lambda: self.suggester.search(typed))

    def _take_suggestions(self):
        answer = self.suggester.poll()
        if answer is None:
            return
        typed, words, _error = answer
        if typed == self.search_entry.get().strip() and self.view == VIEW_FIND:
            self._suggestions = list(words or [])
            self._show_suggestions()

    def _show_suggestions(self):
        rows = self.suggestion_rows()
        for w in self._suggest_rows:
            w.destroy()
        self._suggest_rows = []
        if not rows or self.view != VIEW_FIND:
            self.suggest_box.place_forget()
            return
        for text, kind in rows:
            b = ctk.CTkButton(self.suggest_box, text=("🕘  " if kind == "history" else "🔎  ") + text, anchor="w",
                              fg_color="transparent", text_color=("gray10", "gray90"), height=28,
                              hover_color=("gray85", "gray25"), command=lambda t=text: self._pick_suggestion(t))
            b.pack(fill="x", padx=6, pady=(4 if not self._suggest_rows else 0, 0))
            self._suggest_rows.append(b)
        if not self.search_entry.get().strip():
            b = ctk.CTkButton(self.suggest_box, text="Geçmişi temizle", anchor="e", fg_color="transparent",
                              text_color="gray", height=24, hover_color=("gray85", "gray25"),
                              command=self._clear_history)
            b.pack(fill="x", padx=6, pady=(0, 4))
            self._suggest_rows.append(b)
        self.suggest_box.place(in_=self.search_entry, relx=0, rely=1.0, y=4, relwidth=1.0)
        self.suggest_box.lift()
        self._paint_suggestion()

    def _hide_suggestions(self):
        self.suggest_box.place_forget()
        self._suggest_index = -1

    def _hide_suggestions_if_away(self):
        try:
            focus = self.focus_get()
        except (KeyError, tk.TclError):
            focus = None
        inside = focus is not None and str(focus).startswith(str(self.suggest_box))
        if not inside and focus is not getattr(self.search_entry, "_entry", None):
            self._hide_suggestions()

    def _move_suggestion(self, step):
        rows = self.suggestion_rows()
        if not rows:
            return
        if self.suggest_box.winfo_manager() != "place":
            self._show_suggestions()
        self._suggest_index = max(-1, min(len(rows) - 1, self._suggest_index + step))
        self._paint_suggestion()

    def _paint_suggestion(self):
        rows = self.suggestion_rows()
        for i, b in enumerate(self._suggest_rows[:len(rows)]):
            set_if_changed(b, fg_color=("gray82", "gray28") if i == self._suggest_index else "transparent")

    def _on_search_return(self, event=None):
        rows = self.suggestion_rows()
        if 0 <= self._suggest_index < len(rows) and self.suggest_box.winfo_manager() == "place":
            self._pick_suggestion(rows[self._suggest_index][0])
        else:
            self._search()
        return "break"

    def _pick_suggestion(self, text):
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, text)
        self._search()

    def _clear_history(self):
        self.store.set_state(searches=[])
        self._hide_suggestions()
        self.note("Arama geçmişi temizlendi")

    # ------------------------------------------------------------------ 30 second preview
    def _make_preview(self, result):
        """Runs on the previewer's thread: the 30 second MP3 of a search result."""
        out = os.path.join(music_search.preview_dir(), f"onizleme-{abs(hash(result['url'])) % 10 ** 8}.mp3")
        return music_search.make_preview(result["url"], out, result.get("duration") or 0)

    def _preview_selected(self):
        picked = self._selected_results()
        if not picked:
            self.find_label.configure(text="Önce listeden bir şarkı seç")
            return
        r = picked[0]
        if self.preview and self.preview["result"] is r or self._preview_wanted is r:
            self.stop_preview()
            return
        self.stop_preview()
        self._preview_wanted = r
        self.previewer.search(r)
        self.preview_btn.configure(text="⏳ Hazırlanıyor…")
        self.find_label.configure(text=f"🎧 “{r['title'][:50]}” için 30 saniyelik önizleme hazırlanıyor…")

    def _take_preview(self):
        answer = self.previewer.poll()
        if answer is not None:
            result, path, error = answer
            if result is not self._preview_wanted:
                return
            self._preview_wanted = None
            if error or not path:
                self.preview_btn.configure(text="🎧 Önizle")
                self.find_label.configure(text="Önizlemeyi hazırlayamadım: " + (error or "").splitlines()[0][:100]
                                          if error else "Önizlemeyi hazırlayamadım")
                return
            self._start_preview(result, path)
        p = self.preview
        if p is None:
            return
        backend = self._preview_backend
        if self.controller.state == "playing" and not p["resume"]:
            self.stop_preview(resume=False)                      # the user started the music: it wins
        elif time.time() >= p["until"] or backend.finished():
            self.stop_preview()

    def _start_preview(self, result, path):
        if self._preview_backend is None:
            from . import player
            self._preview_backend = player.new_backend(alias="hizli_preview")
        resume = self.controller.state == "playing"
        if resume:
            self.controller.toggle()                             # the music waits while the preview sounds
        b = self._preview_backend
        if not b.load(path):
            self.preview_btn.configure(text="🎧 Önizle")
            self.find_label.configure(text="Önizlemeyi çalamadım")
            return
        b.set_volume(self.controller.volume)
        b.play()
        self.preview = {"result": result, "path": path, "until": time.time() + music_search.PREVIEW_SECONDS + 1,
                        "resume": resume}
        self.preview_btn.configure(text="⏹ Durdur")
        self.find_label.configure(text=f"🎧 Önizleniyor: {result['title'][:50]} • beğendiysen ⬇ İndir")

    def stop_preview(self, resume=True):
        self._preview_wanted = None
        p, self.preview = self.preview, None
        try:
            self.preview_btn.configure(text="🎧 Önizle")
        except tk.TclError:
            pass
        if p is None:
            return
        if self._preview_backend is not None:
            self._preview_backend.stop()
            self._preview_backend.close()
        try:
            os.remove(p["path"])
        except OSError:
            pass
        if resume and p["resume"] and self.controller.state == "paused":
            self.controller.toggle()
        try:
            self.find_label.configure(text="")
        except tk.TclError:
            pass

    def _song_items(self):
        get = getattr(self.app, "song_items", None)
        return get() if get else []

    def _status_by_url(self):
        from .manager import url_key
        out = {}
        for it in self._song_items():
            out[url_key(it.url)] = song_status(it)
        return out

    def _result_values(self, r, statuses):
        from .manager import url_key
        length = fmt_time(r["duration"] * 1000) if r.get("duration") else ""
        return (r["title"], r.get("channel", ""), music_search.short_views(r.get("views")), length,
                i18n.tr(statuses.get(url_key(r["url"]), "⬇")))

    def _refresh_results(self):
        tree = self.results_tree
        keep = tree.selection()
        tree.delete(*tree.get_children())
        statuses = self._status_by_url()
        for i, r in enumerate(self.results):
            tree.insert("", "end", iid=str(i), values=self._result_values(r, statuses))
        keep = [k for k in keep if tree.exists(k)]
        if keep:
            tree.selection_set(keep)
        if self.results:
            self.find_hint.place_forget()
        else:
            self.find_hint.place(relx=0.5, rely=0.5, anchor="center")

    def _update_result_states(self):
        """Only the 'Durum' column changes while songs download (no rebuild: selection and scroll stay)."""
        if not self.results:
            return
        statuses = self._status_by_url()
        for i, r in enumerate(self.results):
            iid = str(i)
            if self.results_tree.exists(iid):
                values = self._result_values(r, statuses)
                if tuple(self.results_tree.item(iid, "values")) != values:
                    self.results_tree.item(iid, values=values)

    def _update_downloads(self):
        """'⬇ Şarkı adı • %45' under the player while found songs download (in either view)."""
        from .models import ACTIVE_STATES
        active = [it for it in self._song_items() if it.state in ACTIVE_STATES]
        if not active:
            text = ""
        elif len(active) == 1:
            name = active[0].display_name
            text = f"⬇ {name[:40] + '…' if len(name) > 41 else name} • {song_status(active[0])}"
        else:
            avg = sum(it.fraction for it in active) / len(active)
            text = f"⬇ {len(active)} şarkı iniyor • %{min(99, int(avg * 100))}"
        set_if_changed(self.dl_label, text=text)

    def _selected_results(self):
        return [self.results[int(i)] for i in self.results_tree.selection() if int(i) < len(self.results)]

    def _on_result_double_click(self, event):
        if self.results_tree.identify_region(event.x, event.y) != "cell":
            return
        row = self.results_tree.identify_row(event.y)
        if row:
            self.results_tree.selection_set(row)
            self._download_selected()

    def _download_selected(self):
        picked = self._selected_results()
        if not picked:
            self.find_label.configure(text="Önce listeden bir şarkı seç")
            return
        download = getattr(self.app, "download_song", None)
        if download is None:
            return
        answers = [download(r) for r in picked]
        started = answers.count("added") + answers.count("restarted")
        if started:
            self.note(f"⬇ {started} şarkı iniyor. Bitince hangi listeye koyacağımı soracağım." if started > 1
                      else "⬇ İniyor. Bitince hangi listeye koyacağımı soracağım.")
        elif "running" in answers:
            self.note("Bu şarkı zaten iniyor, biraz sabır 🙂")
        self._update_result_states()
        self._update_downloads()

    def _result_menu(self, event):
        row = self.results_tree.identify_row(event.y)
        if not row:
            return
        if row not in self.results_tree.selection():
            self.results_tree.selection_set(row)
        menu = tk.Menu(self, tearoff=0)
        self._fill_menu(menu, [("⬇ İndir (MP3)", self._download_selected),
                               ("🎧 Önizle (30 sn)", self._preview_selected),
                               ("🌐 Tarayıcıda aç", self._open_result)])
        self._popup(menu, event)

    def _open_result(self):
        picked = self._selected_results()
        if picked:
            webbrowser.open(picked[0]["url"])

    def _open_music_folder(self):
        open_in_file_manager(music_search.music_dir())

    # ------------------------------------------------------------------ clock
    def _update_status(self):
        c = self.controller
        playing = c.state in ("playing", "preparing")
        set_if_changed(self.play_btn, text=PAUSE_ICON if playing else PLAY_ICON)
        self._show_now_playing()
        if c.state == "stopped":
            set_if_changed(self.pos_label, text="0:00")
            set_if_changed(self.len_label, text="0:00")
            if not self._dragging and self.seek.get() != 0:
                self.seek.set(0)
        else:
            pos, length = c.position_ms(), c.length_ms()
            if not self._dragging:
                set_if_changed(self.pos_label, text=fmt_time(pos))
                value = 1000 * pos / length if length else 0
                if abs(self.seek.get() - value) >= 0.5:       # half a thousandth: not visible, not redrawn
                    self.seek.set(value)
            set_if_changed(self.len_label, text=fmt_time(length))
        self._update_marker()

    def _count_listening(self):
        """A song played for PLAYED_AFTER_MS (a short one: half of it) counts once for the smart lists;
        played again from the start, it counts again."""
        c = self.controller
        path = c.current_path() if c.state == "playing" else None
        if path != getattr(self, "_listen_path", None):
            self._listen_path, self._listen_counted = path, False
        if not path:
            return
        at = c.position_ms()
        if self._listen_counted:
            if at < 2000:
                self._listen_counted = False
            return
        length = c.length_ms()
        if at >= (min(playlists.PLAYED_AFTER_MS, length // 2) if length else playlists.PLAYED_AFTER_MS):
            self._listen_counted = True
            self.store.count_play(path)

    def _tick(self):
        """Four times a second: the end of a track, new answers, the clock. An error in one round
        is logged and the next round still runs (otherwise playback would stop moving on)."""
        if self._closed:
            return
        try:
            self._check_sleep()
            self.controller.tick()
            self._count_listening()
            if self.controller.error:
                self.note(self.controller.error)
                self.controller.error = ""
            self._drain_reader()
            self._check_keys()
            self._take_answer()
            self._take_lyrics()
            self._follow_lyrics()
            self._update_result_states()
            self._update_downloads()
            self._update_queue_button()
            self._take_suggestions()
            self._take_preview()
            self._sync_outside()
            now = time.time()
            if self._missing is not None:
                missing, self._missing = self._missing, None
                self.prune_missing(missing)
            if now >= self._next_prune:
                self._next_prune = now + PRUNE_EVERY
                self._check_missing()
            if now >= self._next_remember:
                self._next_remember = now + REMEMBER_EVERY
                self._remember_place()
            self._update_status()
            if self._note_until and time.time() > self._note_until:
                self.note_label.configure(text="")
                self._note_until = 0
        except Exception:  # noqa: BLE001 - see above
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:                  # the window is gone
                return
            log.exception("the music window could not update")
        self.after(250, self._tick)

    # ------------------------------------------------------------------ mini player, media panel, taskbar
    def open_mini(self):
        """The small always-on-top player; the big window steps aside until '⤢' is pressed."""
        if self.mini is not None:
            try:
                self.mini.lift()
                return
            except tk.TclError:
                self.mini = None
        self.mini = MiniPlayer(self)
        self.withdraw()

    def close_mini(self, show=True):
        mini, self.mini = self.mini, None
        if mini is not None:
            try:
                mini.destroy()
            except tk.TclError:
                pass
        if show and not self._closed:
            self.deiconify()
            self.lift()

    def _press(self, name):
        {"toggle": self._toggle, "next": self._next, "previous": self._previous,
         "stop": self._stop}.get(name, lambda: None)()

    def _sync_outside(self):
        """The mini player, Windows' media panel and the taskbar buttons show what plays; their buttons work."""
        c = self.controller
        if self.mini is not None:
            try:
                self.mini.refresh()
            except tk.TclError:
                self.mini = None
        for source in (self.overlay, self.thumbbar):           # buttons first: what is shown is then up to date
            while True:
                try:
                    name = source.pressed.get_nowait()
                except Exception:  # noqa: BLE001 - queue.Empty
                    break
                self._press(name)
        track = c.current_track() if c.state != "stopped" else None
        if track is not None:
            artist, title = artist_and_title(track)
            self.overlay.show(title, artist, track.get("album", ""), self._covers.get(track["path"]))
        self.overlay.status(c.state)
        if not self.thumbbar.active and self.winfo_ismapped():
            self.thumbbar.attach(self._frame_handle(), os.path.join(tags.covers_dir(), "..", "icons"))
        self.thumbbar.set_playing(c.state == "playing")

    def _frame_handle(self):
        try:
            import ctypes
            return ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
        except Exception:  # noqa: BLE001
            return self.winfo_id()

    def shutdown(self):
        """The app is closing: note where the music is, stop the sound, give the media keys back,
        finish the tag reading and save the lists."""
        self._closed = True
        try:
            self._remember_place()
            self.controller.stop()
        except Exception:  # noqa: BLE001 - closing anyway
            pass
        for step in (self.stop_preview, lambda: self.close_mini(show=False), self.thumbbar.detach, self.overlay.close):
            try:
                step()
            except Exception:  # noqa: BLE001 - closing anyway
                pass
        if self.lyrics_window is not None:
            try:
                self.lyrics_window.destroy()
            except tk.TclError:
                pass
            self.lyrics_window = None
        prepare = getattr(self.controller, "prepare", None)
        for stop in (self.keys.stop, self.reader.stop, prepare.stop if prepare else lambda: None):
            try:
                stop()
            except Exception:  # noqa: BLE001
                pass
        self.store.save()


class SongListDialog(ctk.CTkToplevel):
    """'🎉 İndi! Hangi listeye ekleyeyim?' after songs found in the music player were downloaded.
    Songs that finish while it is open join it. `on_choose(paths, name)` puts them in; closing
    the window (or 'Şimdilik ekleme') leaves them only in the music folder."""

    NEW = "＋ Yeni liste…"

    def __init__(self, parent, names, default, songs, on_choose):
        super().__init__(parent)
        set_window_icon(self)
        self.title("DISO • Şarkı indi")
        self.resizable(False, False)
        self.on_choose = on_choose
        self.songs = []                                   # [(title, path), ...]
        self.columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="🎉 İndi!", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 2))
        self.text = ctk.CTkLabel(self, text="", justify="left", anchor="w", wraplength=380)
        self.text.grid(row=1, column=0, sticky="ew", padx=20)
        ctk.CTkLabel(self, text="Hangi çalma listesine ekleyeyim?", text_color="gray").grid(
            row=2, column=0, sticky="w", padx=20, pady=(12, 4))
        choices = list(names) + [self.NEW]
        self.menu = ctk.CTkOptionMenu(self, values=choices, width=280, command=self._on_pick)
        self.menu.set(default if default in names else (names[0] if names else self.NEW))
        self.menu.grid(row=3, column=0, sticky="w", padx=20)
        self.name_entry = ctk.CTkEntry(self, placeholder_text="Yeni listenin adı", width=280)
        self.error = ctk.CTkLabel(self, text="", text_color=("#B3261E", "#F2B8B5"))
        self.error.grid(row=5, column=0, sticky="w", padx=20)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=6, column=0, sticky="e", padx=20, pady=(6, 16))
        ctk.CTkButton(buttons, text="Şimdilik ekleme", width=120, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.skip).pack(side="left", padx=(0, 8))
        self.add_btn = ctk.CTkButton(buttons, text="Ekle", width=110, command=self.choose)
        self.add_btn.pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.skip)
        self.bind("<Return>", lambda e: self.choose())
        self.bind("<Escape>", lambda e: self.skip())
        self.add(songs)
        self._on_pick(self.menu.get())
        try:
            self.transient(parent)
        except tk.TclError:
            pass
        self.after(50, self._to_front)

    def _to_front(self):
        try:
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def add(self, songs):
        """More songs finished while the question is open."""
        known = {p for _, p in self.songs}
        self.songs += [(t, p) for t, p in songs if p not in known]
        if len(self.songs) == 1:
            text = f"“{self.songs[0][0]}” bilgisayarına indi."
        else:
            shown = ", ".join(f"“{t}”" for t, _ in self.songs[:3])
            text = f"{len(self.songs)} şarkı indi: {shown}" + (" …" if len(self.songs) > 3 else "")
        self.text.configure(text=text)

    def _on_pick(self, choice):
        if choice == self.NEW:
            self.name_entry.grid(row=4, column=0, sticky="w", padx=20, pady=(8, 0))
            self.name_entry.focus_set()
        else:
            self.name_entry.grid_forget()
        self.error.configure(text="")

    def choose(self):
        name = self.menu.get()
        if name == self.NEW:
            name = self.name_entry.get().strip()
            if not name:
                self.error.configure(text="Yeni listeye bir ad ver")
                return
            name = ("new", name)
        paths = [p for _, p in self.songs]
        self.destroy()
        self.on_choose(paths, name)

    def skip(self):
        self.destroy()
        self.on_choose([p for _, p in self.songs], None)


class LyricsWindow(ctk.CTkToplevel):
    """The lyrics of a song. Synced lyrics follow the music: the line being sung is large and in the
    accent colour, the sung ones fade, and a click on a line jumps there. It follows the player to
    the next song by itself."""

    SIZES = (12, 26)

    def __init__(self, parent, on_seek, on_find):
        super().__init__(parent)
        set_window_icon(self)
        self.on_seek, self.on_find = on_seek, on_find
        self.title("DISO • Şarkı sözleri")
        fit_geometry(self, 480, 660)
        self.minsize(360, 420)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.track, self.path, self.data = None, None, None
        self.current = -1
        self.size = 16

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        head.columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(head, text="", anchor="w", justify="left", wraplength=400,
                                        font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.artist_label = ctk.CTkLabel(head, text="", anchor="w", text_color="gray")
        self.artist_label.grid(row=1, column=0, sticky="w")
        self.badge = ctk.CTkLabel(head, text="", height=22, corner_radius=8, font=ctk.CTkFont(size=11, weight="bold"),
                                  fg_color=("gray85", "gray25"))
        self.badge.grid(row=1, column=1, sticky="e")

        self.box = ctk.CTkTextbox(self, wrap="word", activate_scrollbars=True, border_spacing=18, corner_radius=14)
        self.box.grid(row=1, column=0, sticky="nsew", padx=16, pady=6)
        self.text = self.box._textbox
        self.text.bind("<Button-1>", self._on_click)
        self.text.bind("<Motion>", self._on_motion)

        self.empty = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.empty, text="🎤", font=ctk.CTkFont(size=44)).pack(pady=(0, 6))
        self.empty_text = ctk.CTkLabel(self.empty, text="", text_color="gray", justify="center")
        self.empty_text.pack()
        self.find_btn = ctk.CTkButton(self.empty, text="🔎 İnternette ara", command=self._find)
        self.find_btn.pack(pady=(12, 0))

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 14))
        foot.columnconfigure(2, weight=1)
        ctk.CTkButton(foot, text="A−", width=40, command=lambda: self._resize(-2)).grid(row=0, column=0, padx=(0, 6))
        ctk.CTkButton(foot, text="A+", width=40, command=lambda: self._resize(+2)).grid(row=0, column=1)
        self.hint = ctk.CTkLabel(foot, text="", text_color="gray")
        self.hint.grid(row=0, column=2, padx=10)
        self.again_btn = ctk.CTkButton(foot, text="🔄 Yanlışsa yeniden bul", width=150, fg_color="transparent",
                                       border_width=1, text_color=("gray20", "gray85"), command=self._find)
        self.again_btn.grid(row=0, column=3, padx=(0, 8))
        ctk.CTkButton(foot, text="Kapat", width=90, command=self.destroy).grid(row=0, column=4)
        self.bind("<Escape>", lambda e: self.destroy())
        try:
            self.transient(parent)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ what is shown
    @property
    def synced(self):
        return bool(self.data and self.data["synced"])

    def lines(self):
        if not self.data:
            return []
        if self.synced:
            return [words or "♪" for _, words in self.data["synced"]]
        return self.data["plain"]

    def show(self, track):
        """Show this song's lyrics (or say there are none and offer to look)."""
        self.track, self.path = track, track["path"]
        self.data = lyrics.load(self.path)
        self.current = -1
        artist, title = artist_and_title(track)
        set_if_changed(self.title_label, text=title)
        set_if_changed(self.artist_label, text=artist or " ")
        if not self.data:
            self.box.grid_remove()
            self.badge.grid_remove()
            self.empty_text.configure(text="Bu şarkının sözleri bende yok.\nİstersen internette arayayım.")
            self.find_btn.configure(state="normal", text="🔎 İnternette ara")
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
            set_if_changed(self.hint, text="")
            return
        self.empty.place_forget()
        self.again_btn.configure(state="normal", text="🔄 Yanlışsa yeniden bul")
        self.box.grid()
        self.badge.grid()
        self.badge.configure(text="  ⏱ Şarkıyla akar  " if self.synced else "  📝 Sözler  ")
        set_if_changed(self.hint, text="Bir satıra tıkla, oradan çalsın" if self.synced else "")
        self._fill()

    def _colors(self):
        theme = ctk.ThemeManager.theme
        return (_themed(theme["CTkButton"]["fg_color"]), _themed(theme["CTkLabel"]["text_color"]),
                "gray55")

    def _fill(self):
        accent, text, faded = self._colors()
        family = ctk.ThemeManager.theme.get("CTkFont", {}).get("family", "Segoe UI")
        family = family if isinstance(family, str) else "Segoe UI"
        t = self.text
        t.configure(state="normal", cursor="hand2" if self.synced else "arrow")
        t.delete("1.0", "end")
        t.tag_configure("all", justify="center", spacing1=int(self.size * 0.45), spacing3=int(self.size * 0.45),
                        font=(family, self.size), foreground=text if not self.synced else faded)
        t.tag_configure("past", foreground=faded)
        t.tag_configure("now", foreground=accent, font=(family, self.size + 5, "bold"))
        t.tag_configure("next", foreground=text)
        for line in self.lines():
            t.insert("end", line + "\n", ("all",))
        t.configure(state="disabled")
        t.yview_moveto(0)

    def _resize(self, step):
        self.size = max(self.SIZES[0], min(self.SIZES[1], self.size + step))
        if self.data:
            current, self.current = self.current, -1
            self._fill()
            if current >= 0:
                self._mark(current)

    # ------------------------------------------------------------------ following the song
    def follow(self, track, ms):
        """Called by the player a few times a second while it plays."""
        if track is None:
            return
        if track["path"] != self.path:
            self.show(track)
        if self.synced:
            self._mark(lyrics.line_at(self.data["synced"], ms + 250))     # a little early: easier to sing along

    def _mark(self, index):
        if index == self.current:
            return
        t = self.text
        t.tag_remove("now", "1.0", "end")
        t.tag_remove("past", "1.0", "end")
        t.tag_remove("next", "1.0", "end")
        if index >= 0:
            t.tag_add("past", "1.0", f"{index + 1}.0")
            t.tag_add("now", f"{index + 1}.0", f"{index + 2}.0")
            t.tag_add("next", f"{index + 2}.0", f"{index + 5}.0")
            total = max(1, len(self.lines()))
            t.yview_moveto(max(0.0, (index - 4) / total))
        else:
            t.tag_add("next", "1.0", "4.0")
        self.current = index

    def _line_under(self, event):
        try:
            return int(self.text.index(f"@{event.x},{event.y}").split(".")[0]) - 1
        except (tk.TclError, ValueError):
            return -1

    def _on_click(self, event):
        if not self.synced:
            return None
        i = self._line_under(event)
        if 0 <= i < len(self.data["synced"]):
            self.on_seek(self.data["synced"][i][0])
        return "break"

    def _on_motion(self, event):
        return None

    def _find(self):
        if self.track and self.on_find(self.track):
            self.find_btn.configure(state="disabled", text="Arıyorum…")
            self.again_btn.configure(state="disabled", text="Arıyorum…")


class MiniPlayer(ctk.CTkToplevel):
    """A small always-on-top player in the corner: cover, title, ⏮ ⏯ ⏭, how far the song is, and ⤢ back to
    the big window. It only shows what the big window's player does (it has no player of its own)."""

    COVER = 60

    def __init__(self, music):
        super().__init__(music.app)
        set_window_icon(self)
        self.music = music
        self.title("DISO")
        self.resizable(False, False)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        w, h = 400, 118
        try:
            scale = float(self._get_window_scaling())
        except Exception:  # noqa: BLE001
            scale = 1.0
        x = int(self.winfo_screenwidth() / scale) - w - 24
        y = int(self.winfo_screenheight() / scale) - h - 90
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        self.protocol("WM_DELETE_WINDOW", lambda: music.close_mini())
        self.columnconfigure(1, weight=1)
        self._placeholder = placeholder_image(shown=self.COVER)
        self._cover_for = None
        self._cover_image = None
        self.cover = ctk.CTkLabel(self, text="♪", image=self._placeholder, compound="center", width=self.COVER,
                                  height=self.COVER, font=ctk.CTkFont(size=24), text_color=("#B7A3C2", "#5A4668"))
        self.cover.grid(row=0, column=0, rowspan=3, padx=(12, 10), pady=12)
        self.title_label = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(size=14, weight="bold"))
        self.title_label.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(10, 0))
        self.sub_label = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self.sub_label.grid(row=1, column=1, columnspan=2, sticky="ew")
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=2, column=1, sticky="w")
        self.prev_btn = ctk.CTkButton(controls, text="⏮", width=38, height=28, command=music._previous)
        self.play_btn = ctk.CTkButton(controls, text=PLAY_ICON, width=46, height=28, command=music._toggle)
        self.next_btn = ctk.CTkButton(controls, text="⏭", width=38, height=28, command=music._next)
        for b in (self.prev_btn, self.play_btn, self.next_btn):
            b.pack(side="left", padx=(0, 6))
        self.big_btn = ctk.CTkButton(self, text="⤢", width=34, height=28, command=music.close_mini)
        self.big_btn.grid(row=2, column=2, padx=(0, 12), sticky="e")
        self.bar = ctk.CTkProgressBar(self, height=4)
        self.bar.set(0)
        self.bar.grid(row=3, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 8))
        self.refresh()

    def refresh(self):
        c = self.music.controller
        track = c.current_track() if c.state != "stopped" else None
        if track is None:
            set_if_changed(self.title_label, text="Şu an bir şey çalmıyor")
            set_if_changed(self.sub_label, text=" ")
        else:
            artist, title = artist_and_title(track)
            set_if_changed(self.title_label, text=title[:40] + ("…" if len(title) > 40 else ""))
            set_if_changed(self.sub_label, text=artist or " ")
        set_if_changed(self.play_btn, text=PAUSE_ICON if c.state == "playing" else PLAY_ICON)
        length = c.length_ms()
        value = c.position_ms() / length if length else 0
        if abs(self.bar.get() - value) >= 0.002:
            self.bar.set(value)
        path = track["path"] if track else None
        if path != self._cover_for:
            self._cover_for = path
            jpg = self.music._covers.get(path) if path else None
            img = square_cover(jpg, self.COVER * 2) if jpg else None
            if img is None:
                self.cover.configure(image=self._placeholder, text="♪")
                self._cover_image = None
            else:
                img = rounded(img, img.width // 8)
                self._cover_image = ctk.CTkImage(light_image=img, dark_image=img, size=(self.COVER, self.COVER))
                self.cover.configure(image=self._cover_image, text="")
