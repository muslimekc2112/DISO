"""Main window (customtkinter): link bar, options, the live download list, the settings
window, the update panel, the info / playlist windows, the tray icon and the browser bridge."""
import dataclasses
import datetime
import gc
import os
import pathlib
import queue
import re
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import TclError, filedialog, messagebox

import customtkinter as ctk

from . import __version__, about, app_update, brand, notify, schedule, startup, tray, updater
from . import bridge as bridge_module
from . import backup, channels, classic_ui, extension_setup, history, i18n, look, lyrics, music_search, playable, player, playlists, repair
from .channels_ui import ChannelsWindow
from .classic_ui import NostalgiaWindow
from .extra_ui import HistoryWindow, ShortcutsWindow
from . import video_engine as ve
from .config import (AFTER_ALL, AUTO_RETRY, FILTERS, MAX_PARALLEL_CHOICES, SORTS, SPEED_LIMITS,
                     THEMES, Config)
from .logs import log, setup_logging
from .manager import DownloadManager
from .music_ui import MODE_DOWNLOAD, MODE_MUSIC, MusicWindow, SongListDialog, mode_bar
from .models import (ACTIVE_STATES, CANCELLED, DONE, DOWNLOADING, ERROR, PAUSED, PROCESSING,
                     QUEUED, RESOLVING, SUBTITLE_CHOICES, WAITING, Settings)
from .segmented_downloader import LIMITER, check_connection, set_proxy
from .ui_common import fit_geometry, logo_image, set_if_changed, set_window_icon  # noqa: F401 - fit_geometry is also used by the tests
from .ui_common import guard_color_emoji, install_smooth_scrolling, install_wrap_to_fit

guard_color_emoji()                 # Linux with an old libXft: before the first window
install_smooth_scrolling()
install_wrap_to_fit()
from .utils import (MAC, WINDOWS, app_data_dir, clip_text, default_download_dir, extract_urls, find_ffmpeg,
                    human_duration, human_eta, human_size, is_url, normalize_url, open_file, open_in_file_manager,
                    parse_time, resource_path, urls_from_file)

KIND_LABELS = {
    "Otomatik (dosya / video)": "auto",
    "Video (MP4)": "video",
    "Ses (MP3)": "audio",
    "Dosya (rar, zip, exe, iso…)": "file",
}
CONNECTIONS = ["8", "16", "32"]
LANGUAGE_SHORT = {"TR": "Türkçe", "EN": "English"}          # the switch at the top left of the main window
LANGUAGE_NAMES = {name: short for short, name in LANGUAGE_SHORT.items()}
EXTENSION_OFFER_DELAY = 4000            # ms after the start: "add DISO to your browser?" (once the window is settled)
EXTENSION_LATER = 3 * 24 * 3600         # s: "remind me later" asks again after three days
BAD = "#b23b3b"
BAD_HOVER = "#8f2e2e"
GOOD = "#2e9e5b"
WARN = "#d68a1f"
BUSY = "#3b78c9"
STATUS_STYLE = {  # updater status -> (text, colour)
    "idle": ("Bekliyor", "gray"),
    "checking": ("Kontrol ediliyor…", BUSY),
    "current": ("✓ Güncel", GOOD),
    "available": ("⬆ Güncelleme var", WARN),
    "working": ("⟳ Güncelleniyor", BUSY),
    "done": ("✓ Güncellendi", GOOD),
    "error": ("✖ Hata", BAD),
    "missing": ("Kurulu değil", "gray"),
    "manual": ("Ayrıca kurulu", "gray"),
}

# list filter -> states it shows (None = everything)
FILTER_STATES = {
    "Hepsi": None,
    "Aktif": (RESOLVING, DOWNLOADING, PROCESSING),
    "Sırada": (QUEUED, WAITING),
    "Duraklatılmış": (PAUSED,),
    "Tamamlanan": (DONE,),
    "Hatalı": (ERROR,),
}
_STATE_RANK = {DOWNLOADING: 0, PROCESSING: 0, RESOLVING: 0, QUEUED: 1, WAITING: 1, PAUSED: 2,
               ERROR: 3, DONE: 4, CANCELLED: 5}
SORT_KEYS = {
    "Yeni üstte": lambda it: -it.added,
    "Eski üstte": lambda it: it.added,
    "Ad (A→Z)": lambda it: it.display_name.lower(),
    "Boyut (büyük üstte)": lambda it: -(it.total or it.done),
    "Duruma göre": lambda it: (_STATE_RANK.get(it.state, 9), -it.added),
}
NO_END_ACTION = "Hiçbir şey yapma"


STATE_COLOURS = {DONE: look.STATE_DONE, ERROR: look.STATE_ERROR, CANCELLED: look.STATE_IDLE,
                 PAUSED: look.STATE_PAUSED, DOWNLOADING: look.ACCENT, PROCESSING: look.ACCENT,
                 RESOLVING: look.ACCENT, WAITING: look.STATE_PAUSED}


CLOSE_WAIT = 6              # s: the longest a closing waits for downloads to write down where they are

class ItemActions:
    """What can be done with one download: the buttons of its row and its right-click menu
    (the table of the "Nostalji" look uses them too, see ItemMenu)."""
    item = app = None

    def _open(self):
        it = self.item
        open_in_file_manager(it.final_path or it.dest or it.folder)

    def _open_file(self):
        it = self.item
        if it.state == DONE and it.final_path and os.path.exists(it.final_path):
            open_file(it.final_path)

    def _remove(self):
        self.app.manager.remove(self.item)

    def _copy_link(self):
        self.app.clipboard_clear()
        self.app.clipboard_append(self.item.url)
        self.app.notice("Link kopyalandı, yapıştırmaya hazır")

    def _redownload(self):
        self.app.manager.redownload(self.item)

    def _delete_with_file(self):
        it = self.item
        if messagebox.askyesno("DISO", f"{it.display_name}\n\nListeden kaldırılsın ve dosya "
                                                 "diskten SİLİNSİN mi?"):
            self.app.manager.delete_with_file(it)

    def menu_commands(self):
        """The entries of the right-click menu for the item's current state: [(label, action)]."""
        it = self.item
        finished = it.state == DONE and bool(it.final_path)
        cmds = []
        if finished:
            cmds += [("Dosyayı aç", self._open_file), ("Klasörde göster", self._open)]
        elif it.folder or it.dest:
            cmds.append(("Klasörü aç", self._open))
        cmds.append(("Linki kopyala", self._copy_link))
        if finished and player.is_audio(it.final_path) and os.path.isfile(it.final_path):
            names = self.app.playlist_names()
            cmds.append(("Müzik listesine ekle", [(n, lambda n=n: self.app.add_to_music_list(it, n)) for n in names]
                         + [("＋ Yeni liste…", self._add_to_new_music_list)]))
        if finished:
            cmds.append(("🔧 Dosyayı kontrol et / onar", lambda: self.app.check_file(it)))
        if it.state in (DONE, ERROR, CANCELLED, PAUSED):
            cmds.append(("Baştan indir", self._redownload))
        cmds.append(("Listeden kaldır", self._remove))
        if finished:
            cmds.append(("Dosyayla birlikte sil", self._delete_with_file))
        return cmds

    def _add_to_new_music_list(self):
        dialog = ctk.CTkInputDialog(text="Yeni çalma listesinin adı:", title="Yeni liste")
        set_window_icon(dialog)
        name = dialog.get_input()
        if name and name.strip():
            self.app.add_to_music_list(self.item, self.app.new_music_list(name))

    def popup_menu(self, parent, event, extra=()):
        menu = tk.Menu(parent, tearoff=0)
        for label, action in [*extra, *self.menu_commands()]:
            if isinstance(action, list):                       # a sub-menu: [(label, action), ...]
                sub = tk.Menu(menu, tearoff=0)
                for sub_label, sub_action in action:
                    sub.add_command(label=sub_label, command=sub_action)
                menu.add_cascade(label=label, menu=sub)
            else:
                menu.add_command(label=label, command=action)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


class ItemMenu(ItemActions):
    def __init__(self, item, app):
        self.item, self.app = item, app


class DownloadRow(ItemActions, ctk.CTkFrame):
    """One line of the list: checkbox, name, progress bar, status text and buttons.
    Right click opens a menu, double click opens the finished file."""

    def __init__(self, master, item, app):
        super().__init__(master, corner_radius=10)
        self.item, self.app = item, app
        self._cache = {}
        self.columnconfigure(1, weight=1)

        self.stripe = None
        if look.is_new():
            self.stripe = ctk.CTkFrame(self, width=5, corner_radius=3, fg_color=look.STATE_IDLE)
            self.stripe.place(x=8, rely=0.5, relheight=0.72, anchor="w")
        self.sel_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="", width=24, checkbox_width=20, checkbox_height=20,
                        variable=self.sel_var, command=self._on_select).grid(
            row=0, column=0, rowspan=3, padx=(22 if self.stripe else 12, 0))
        self.name = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.name.grid(row=0, column=1, sticky="ew", padx=(10, 6), pady=(8, 0))
        self.bar = ctk.CTkProgressBar(self, height=10)
        self.bar.set(0)
        self.bar.grid(row=1, column=1, sticky="ew", padx=(10, 6), pady=6)
        self.info = ctk.CTkLabel(self, text="", anchor="w", justify="left", text_color="gray",
                                 wraplength=600)
        self.info.grid(row=2, column=1, sticky="ew", padx=(10, 6), pady=(0, 8))

        box = ctk.CTkFrame(self, fg_color="transparent")
        box.grid(row=0, column=2, rowspan=3, padx=8)
        self.toggle_btn = ctk.CTkButton(box, text="⏸", width=38, command=self._toggle)
        self.toggle_btn.pack(side="left", padx=2)
        self.open_btn = ctk.CTkButton(box, text="📂", width=38, command=self._open)
        self.open_btn.pack(side="left", padx=2)
        self.del_btn = ctk.CTkButton(box, text="✖", width=38, fg_color=BAD, hover_color=BAD_HOVER,
                                     command=self._remove)
        self.del_btn.pack(side="left", padx=2)

        for w in (self, self.name, self.bar, self.info):
            w.bind("<Button-3>", self._popup)
        for w in (self.name, self.info):
            w.bind("<Double-Button-1>", lambda e: self._open_file())

    # ---- buttons
    def _on_select(self):
        self.app.set_selected(self.item.id, bool(self.sel_var.get()))

    def _toggle(self):
        it, m = self.item, self.app.manager
        if it.state in ACTIVE_STATES:
            m.pause(it)
        else:
            m.resume(it)

    def _popup(self, event):
        self.popup_menu(self, event)

    # ---- helpers
    def _set(self, key, value, apply):
        if self._cache.get(key) != value:
            self._cache[key] = value
            apply(value)

    def refresh(self):
        it = self.item
        st = it.state
        self._set("name", it.display_name, lambda v: self.name.configure(text=v[:110]))
        self._set("bar", round(it.fraction, 3), lambda v: self.bar.set(v))
        self._set("sel", it.id in self.app.selected, lambda v: self.sel_var.set(v))

        pct = f"{it.fraction * 100:.1f}%"
        sizes = f" • {human_size(it.done)} / {human_size(it.total)}" if it.total else \
            (f" • {human_size(it.done)}" if it.done else "")
        if st == QUEUED:
            text = "Sırada, birazdan başlıyor…"
            if self.app.queue_note:
                text += f"\n{self.app.queue_note}"
        elif st == WAITING:
            text = f"⏳ {it.message}"
        elif st == RESOLVING:
            text = it.message or "Sunucuya bağlanıyorum…"
        elif st == DOWNLOADING:
            text = f"{pct}{sizes} • {human_size(it.speed)}/s • Kalan {human_eta(it.eta)}"
            if it.conns:
                text += f" • {it.conns} bağlantı"
            if it.message:
                text += f"\n{it.message}"
        elif st == PROCESSING:
            text = it.message or "İşleniyor…"
        elif st == DONE:
            text = "✅ Bitti" + (f" • {human_size(it.total or it.done)}" if (it.total or it.done) else "")
            if it.message:
                text += f"\n{it.message}"
        elif st == PAUSED:
            text = f"⏸ Beklemede • {pct}"
        elif st == ERROR:
            text = f"❌ {it.error}"
        elif st == CANCELLED:
            text = "İptal edildi"
        else:
            text = st
        self._set("info", text, lambda v: self.info.configure(text=v))
        if self.stripe is not None:
            colour = STATE_COLOURS.get(st, look.STATE_IDLE)
            self._set("stripe", colour, lambda v: self.stripe.configure(fg_color=v))
            self._set("bar_colour", colour if st != DOWNLOADING else look.ACCENT,
                      lambda v: self.bar.configure(progress_color=v))

        icon = "⏸" if st in (QUEUED, WAITING, RESOLVING, DOWNLOADING) else "▶"
        self._set("icon", icon, lambda v: self.toggle_btn.configure(text=v))
        can_toggle = st not in (DONE, PROCESSING)
        self._set("can_toggle", can_toggle,
                  lambda v: self.toggle_btn.configure(state="normal" if v else "disabled"))
        self._set("can_open", st == DONE,
                  lambda v: self.open_btn.configure(state="normal" if v else "disabled"))


class ComponentCard(ctk.CTkFrame):
    """One tool in the update panel: versions, status, progress and its own button."""

    def __init__(self, master, comp, on_action):
        super().__init__(master, corner_radius=12)
        self.comp = comp
        self._cache = {}
        self.columnconfigure(0, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 0))
        head.columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text=comp.title, font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w")
        self.badge = ctk.CTkLabel(head, text="", font=ctk.CTkFont(weight="bold"))
        self.badge.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(self, text=comp.desc, text_color="gray", anchor="w", justify="left",
                     wraplength=440).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 0))
        self.versions = ctk.CTkLabel(self, text="", anchor="w")
        self.versions.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        self.button = ctk.CTkButton(self, text="", width=110, command=lambda: on_action(comp.key))
        self.button.grid(row=2, column=1, sticky="e", padx=16, pady=(10, 0))
        self.bar = ctk.CTkProgressBar(self, height=8)
        self.bar.set(0)
        self.bar.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 0))
        self.message = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=500)
        self.message.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 14))

    def _set(self, key, value, apply):
        if self._cache.get(key) != value:
            self._cache[key] = value
            apply(value)

    def refresh(self, busy):
        c = self.comp
        label, colour = STATUS_STYLE.get(c.status, (c.status, "gray"))
        self._set("badge", (label, colour),
                  lambda v: self.badge.configure(text=v[0], text_color=v[1]))

        parts = []
        if c.installed:
            parts.append(f"Kurulu: {c.installed}")
        elif c.status == "missing":
            parts.append("Kurulu değil")
        if c.latest:
            parts.append(f"Son: {c.latest}")
        self._set("versions", "   •   ".join(parts),
                  lambda v: self.versions.configure(text=v))

        working = c.status == "working"
        self._set("working", working, lambda v: self.bar.grid() if v else self.bar.grid_remove())
        if working:
            self.bar.set(c.progress)

        is_error = c.status == "error"
        self._set("msg", (c.message, is_error),
                  lambda v: self.message.configure(text=v[0], text_color=BAD if v[1] else "gray"))

        action = "Kur" if c.status == "missing" else "Güncelle"
        show = c.status in ("available", "missing")
        self._set("btn", (action, show, busy),
                  lambda v: self._apply_button(*v))

    def _apply_button(self, action, show, busy):
        self.button.configure(text=action, state="disabled" if busy else "normal")
        if show:
            self.button.grid()
        else:
            self.button.grid_remove()


class UpdatePanel(ctk.CTkToplevel):
    """Window that lists yt-dlp, yt-dlp-ejs and FFmpeg with their versions and progress."""

    def __init__(self, app):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.title("Güncellemeler")
        w, h = fit_geometry(self, 620, 640)
        self.minsize(min(560, w), min(420, h))
        self.transient(app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 6))
        ctk.CTkLabel(head, text="🔄 Güncellemeler" if look.is_nostalgia() else "⟳ Güncellemeler",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(head, text="yt-dlp ve FFmpeg her açılışta kontrol edilir, yeni sürüm kendiliğinden iner ve "
                                "SHA-256 ile doğrulanır. DISO'nun yeni sürümü yalnızca haber verilir: sen "
                                "“Güncelle” dersen kurulur.",
                     text_color="gray", wraplength=560, justify="left", anchor="w").pack(fill="x", pady=(2, 0))

        self.cards_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.cards_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=6)
        self.cards = {}
        diso = ComponentCard(self.cards_frame, app.app_update.comp, app.update_card)
        diso.pack(fill="x", padx=4, pady=6)
        self.cards["diso"] = diso
        for key, comp in app.updates.components.items():
            card = ComponentCard(self.cards_frame, comp, app.update_card)
            card.pack(fill="x", padx=4, pady=6)
            self.cards[key] = card

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=22, pady=(6, 18))
        foot.columnconfigure(0, weight=1)
        self.last_label = ctk.CTkLabel(foot, text="", text_color="gray")
        self.last_label.grid(row=0, column=0, sticky="w")
        self.check_btn = ctk.CTkButton(foot, text="🔍 Kontrol et", width=130,
                                       command=lambda: app.check_updates(install=False))
        self.check_btn.grid(row=0, column=1, padx=4)
        self.all_btn = ctk.CTkButton(foot, text="⬇ Tümünü güncelle", width=160,
                                     command=lambda: app.check_updates(install=True))
        self.all_btn.grid(row=0, column=2, padx=4)

        self.after(300, self._refresh)

    def _refresh(self):
        try:
            busy = self.app.updates.running
            for key, card in self.cards.items():
                card.refresh(self.app.app_update.running if key == "diso" else busy)
            state = "disabled" if busy else "normal"
            self.check_btn.configure(state=state, text="Kontrol ediliyor…" if busy else "🔍 Kontrol et")
            self.all_btn.configure(state=state)
            last = max(self.app.updates.last_check, self.app.app_update.last_check)
            self.last_label.configure(text=f"Son kontrol: {time.strftime('%H:%M:%S', time.localtime(last))}"
                                      if last else "Henüz bakmadım")
            self.after(300, self._refresh)
        except TclError:  # the window was closed
            return


class SettingsPanel(ctk.CTkToplevel):
    """Everything that is not in the option bar, in groups. Changes apply at once."""

    def __init__(self, app):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.title("Ayarlar")
        w, h = fit_geometry(self, 620, 720)
        self.minsize(min(560, w), min(420, h))
        self.transient(app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        cfg = app.cfg

        self._cards = {}
        self.nostalgia = look.is_nostalgia()
        if not self.nostalgia:
            ctk.CTkLabel(self, text="⚙ Ayarlar", font=ctk.CTkFont(size=22, weight="bold")).grid(
                row=0, column=0, sticky="w", padx=24, pady=(14, 4))
        # up here, not among the buttons below: there it was squeezed and cut ("SO 0.11.4 be")
        self.version_label = ctk.CTkLabel(self, text=f"{brand.NAME} {brand.VERSION_LABEL}", text_color=look.grey_text())
        self.version_label.grid(row=0, column=0, sticky="e", padx=24, pady=(14, 4) if not self.nostalgia else (6, 0))
        if self.nostalgia:           # the options dialog of those days: one tab for each group
            from tkinter import ttk
            ttk.Style(self).configure("Classic.TFrame", background=look.N_FACE)
            self.body = ttk.Notebook(self)
            self.body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(2, 4))
        else:
            self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
            self.body.grid(row=1, column=0, sticky="nsew", padx=14, pady=4)

        # ---- general
        card = self._card("İndirme")
        self.parallel_menu = ctk.CTkOptionMenu(
            card, values=MAX_PARALLEL_CHOICES, width=150,
            command=lambda v: app.apply_setting("max_parallel", int(v)))
        self.parallel_menu.set(str(cfg.get("max_parallel")))
        self._add(card, "Aynı anda indirme", "Fazlası sırada bekler, sıra gelince başlar", self.parallel_menu)

        self.speed_menu = ctk.CTkOptionMenu(
            card, values=list(SPEED_LIMITS), width=150,
            command=lambda v: app.apply_setting("speed_limit", v))
        self.speed_menu.set(cfg.get("speed_limit"))
        self._add(card, "Hız sınırı", "Hepsinin toplamı; internetin başka işlere de kalsın", self.speed_menu)

        self.retry_menu = ctk.CTkOptionMenu(
            card, values=list(AUTO_RETRY), width=150,
            command=lambda v: app.apply_setting("auto_retry", AUTO_RETRY[v]))
        self.retry_menu.set(next((k for k, v in AUTO_RETRY.items() if v == cfg.get("auto_retry")), "3 kez"))
        self._add(card, "Bağlantı kopunca otomatik dene", "İnternet kopsa bile pes etmem, gelince kaldığı yerden devam ederim",
                  self.retry_menu)

        proxy_box = ctk.CTkFrame(card, fg_color="transparent")
        self.proxy_entry = ctk.CTkEntry(proxy_box, width=200, placeholder_text="boş = sistem ayarı")
        self.proxy_entry.insert(0, cfg.get("proxy"))
        self.proxy_entry.pack(side="left")
        self.proxy_entry.bind("<Return>", lambda e: self._save_proxy())
        self.proxy_entry.bind("<FocusOut>", lambda e: self._save_proxy())
        self.proxy_test_btn = ctk.CTkButton(proxy_box, text="Dene", width=50, command=self._test_proxy)
        self.proxy_test_btn.pack(side="left", padx=(6, 0))
        _, self.proxy_hint = self._add(card, "Proxy", "http://adres:port veya socks5://adres:port", proxy_box)

        self.clip_ask_switch = self._switch(card, command=lambda: app.apply_setting(
            "clip_ask", bool(self.clip_ask_switch.get())))
        self._set_switch(self.clip_ask_switch, cfg.get("clip_ask"))
        self._add(card, "Kopyalanan linki indirmeden önce sor",
                  "“Panoyu izle” açıkken kopyaladığın link için köşede küçük bir pencere çıkar: MP4, MP3 ya da "
                  "İndir. Kapalıysa sormadan listeye eklerim.", self.clip_ask_switch)

        self.dup_switch = self._switch(card, command=lambda: app.apply_setting(
            "block_duplicates", bool(self.dup_switch.get())))
        self._set_switch(self.dup_switch, cfg.get("block_duplicates"))
        self._add(card, "Aynı linki tekrar ekleme", "Aynı link listedeyse ikinciyi eklemem", self.dup_switch)

        self.playlist_ask_switch = self._switch(card, command=lambda: app.apply_setting(
            "playlist_ask", bool(self.playlist_ask_switch.get())))
        self._set_switch(self.playlist_ask_switch, cfg.get("playlist_ask"))
        self._add(card, "Oynatma listesinde videoları seç", "Kapalıysa listedeki her şeyi sormadan eklerim",
                  self.playlist_ask_switch)

        self.auto_music_switch = self._switch(card, command=lambda: app.apply_setting(
            "auto_music", bool(self.auto_music_switch.get())))
        self._set_switch(self.auto_music_switch, cfg.get("auto_music"))
        self._add(card, "Biten müzikleri çalma listesine ekle",
                  "MP3'ler “İndirilenler” listesine, YouTube listeleri kendi adıyla yeni bir listeye gider",
                  self.auto_music_switch)

        # ---- notifications
        card = self._card("Bildirimler")
        self.sound_switch = self._switch(card, command=lambda: app.apply_setting(
            "notify_sound", bool(self.sound_switch.get())))
        self._set_switch(self.sound_switch, cfg.get("notify_sound"))
        self._add(card, "Bildirim sesi", "İndirme bitince veya hata verince", self.sound_switch)

        self.toast_switch = self._switch(card, command=lambda: app.apply_setting(
            "notify_toast", bool(self.toast_switch.get())))
        self._set_switch(self.toast_switch, cfg.get("notify_toast"))
        self._add(card, "Windows bildirimi", "Sağ alttaki bildirim balonu", self.toast_switch)

        # ---- scheduler
        card = self._card("Zamanlayıcı")
        self.schedule_switch = self._switch(card, command=lambda: app.apply_setting(
            "schedule_on", bool(self.schedule_switch.get())))
        self._set_switch(self.schedule_switch, cfg.get("schedule_on"))
        self._add(card, "Zamanlanmış indirme", "Kapalıyken yeni indirmeler başlama saatini bekler",
                  self.schedule_switch)
        times = ctk.CTkFrame(card, fg_color="transparent")
        self.schedule_start_entry = ctk.CTkEntry(times, width=62, justify="center")
        self.schedule_start_entry.insert(0, cfg.get("schedule_start"))
        self.schedule_stop_entry = ctk.CTkEntry(times, width=62, justify="center", placeholder_text="--:--")
        self.schedule_stop_entry.insert(0, cfg.get("schedule_stop"))
        ctk.CTkLabel(times, text="Başlangıç").pack(side="left", padx=(0, 4))
        self.schedule_start_entry.pack(side="left")
        ctk.CTkLabel(times, text="Bitiş").pack(side="left", padx=(10, 4))
        self.schedule_stop_entry.pack(side="left")
        for entry in (self.schedule_start_entry, self.schedule_stop_entry):
            entry.bind("<Return>", lambda e: self._save_schedule())
            entry.bind("<FocusOut>", lambda e: self._save_schedule())
        self._add(card, "Saatler (24 saat, ör. 02:00)", "Bitiş saatini boş bırakırsan başladıktan sonra hep açık kalır",
                  times)

        # ---- system
        card = self._card("Sistem")
        self.tray_switch = self._switch(card, command=lambda: app.apply_setting(
            "tray_on_close", bool(self.tray_switch.get())))
        self._set_switch(self.tray_switch, cfg.get("tray_on_close"))
        if MAC:
            hint = "Pencereyi kapatınca Dock'a küçülür"
        elif tray.AVAILABLE:
            hint = "Pencereyi kapatınca sağ alttaki simgeye iner" if WINDOWS else "Pencereyi kapatınca paneldeki simgeye iner"
        else:
            hint = "pystray kurulu değil"
        self._add(card, "Kapatınca arka planda çalış", hint, self.tray_switch)

        self.startup_switch = self._switch(card, command=lambda: app.apply_setting(
            "start_with_windows", bool(self.startup_switch.get())))
        self._set_switch(self.startup_switch, cfg.get("start_with_windows"))
        self._add(card, "Windows açılışında başlat" if WINDOWS else "Oturum açılınca başlat",
                  "Açılışta pencere göstermeden, simge olarak başlar", self.startup_switch)

        self.bridge_switch = self._switch(card, command=lambda: app.apply_setting(
            "bridge_on", bool(self.bridge_switch.get())))
        self._set_switch(self.bridge_switch, cfg.get("bridge_on"))
        self._add(card, "Tarayıcı eklentisinden link al", "Sadece bu bilgisayardaki eklentiyi dinlerim; dışarıdan kimse link gönderemez",
                  self.bridge_switch)
        self.guide_button = ctk.CTkButton(card, text="🧩 Tarayıcıya ekle", width=150, command=app.open_extension_guide)
        self._add(card, "Tarayıcı eklentisi", "Chrome, Edge, Brave, Opera, Firefox: linke sağ tık → DISO ile indir. "
                                              "DISO kapalıysa kendisi açılır", self.guide_button)

        port_box = ctk.CTkFrame(card, fg_color="transparent")
        self.bridge_port_entry = ctk.CTkEntry(port_box, width=70, justify="center")
        self.bridge_port_entry.insert(0, str(cfg.get("bridge_port")))
        self.bridge_port_entry.pack(side="left")
        self.bridge_port_entry.bind("<Return>", lambda e: self._save_port())
        self.bridge_port_entry.bind("<FocusOut>", lambda e: self._save_port())
        self.ext_button = ctk.CTkButton(port_box, text="Eklenti klasörü", width=110, command=app.open_extension_folder)
        self.ext_button.pack(side="left", padx=(6, 0))
        self._add(card, "Eklenti bağlantı noktası", "Eklentideki port ile aynı olsun, yoksa konuşamayız", port_box)

        self.theme_menu = ctk.CTkOptionMenu(card, values=list(THEMES), width=150,
                                            command=lambda v: app.apply_setting("theme", v))
        self.theme_menu.set(cfg.get("theme"))
        self._add(card, "Görünüm", "Koyu ya da açık gri (değişince DISO yeniden açılır)" if self.nostalgia
                  else "Koyu, açık ya da Windows ne derse o", self.theme_menu)
        self.look_menu = ctk.CTkOptionMenu(card, values=look.STYLES, width=150,
                                           command=lambda v: app.apply_setting("look", v))
        self.look_menu.set(cfg.get("look"))
        self._add(card, "Görünüm stili", "Renk ve şekil takımı (değişince DISO yeniden açılır)", self.look_menu)
        self.language_menu = ctk.CTkOptionMenu(card, values=list(i18n.LANGUAGES), width=150,
                                               command=lambda v: app.apply_setting("language", v))
        self.language_menu.set(cfg.get("language"))
        self._add(card, "Dil", "Arayüzün dili (değişince DISO yeniden açılır)", self.language_menu)

        # ---- backup, history, help
        card = self._card("Yedek ve yardım")
        self.backup_button = ctk.CTkButton(card, text="💾 Yedek al", width=150, command=app.make_backup)
        self._add(card, "Yedek al", "Ayarlar, çalma listeleri, indirme listesi ve geçmiş tek bir dosyaya", self.backup_button)
        self.restore_button = ctk.CTkButton(card, text="📂 Yedeği yükle", width=150, command=app.restore_backup)
        self._add(card, "Yedeği geri yükle", "Başka bilgisayardan ya da eskiden aldığın yedeği geri getir", self.restore_button)
        self.history_settings_button = ctk.CTkButton(card, text="📊 Geçmiş", width=150, command=app.open_history)
        self._add(card, "İndirme geçmişi", "Ne zaman ne indi, ne kadar hızlı", self.history_settings_button)
        self.shortcuts_button = ctk.CTkButton(card, text="⌨ Kısayollar", width=150, command=app.open_shortcuts)
        self._add(card, "Klavye kısayolları", "F1 ile her yerden açılır", self.shortcuts_button)

        # ---- when everything is finished
        card = self._card("Bitince")
        self.after_menu = ctk.CTkOptionMenu(card, values=list(AFTER_ALL), width=150,
                                            command=app.set_after_all)
        self.after_menu.set(app.after_all)
        self._add(card, "Tüm indirmeler bitince", "Bir kere çalışır, kaydedilmez", self.after_menu)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=24, pady=(8, 14))
        foot.columnconfigure(3, weight=1)
        ctk.CTkButton(foot, text="🔔 Bildirimi dene", width=140, command=app.test_notification).grid(row=0, column=0)
        self.log_button = ctk.CTkButton(foot, text="📜 Günlüğü aç", width=120, command=app.open_log)
        self.log_button.grid(row=0, column=1, padx=8)
        self.about_button = ctk.CTkButton(foot, text="ℹ Hakkında", width=110, command=app.open_about)
        self.about_button.grid(row=0, column=2)
        ctk.CTkButton(foot, text="Kapat", width=100, command=self.destroy).grid(row=0, column=4)

        self._proxy_result = None
        self.after(500, self._sync)

    # ---- layout helpers
    def _card(self, title):
        if self.nostalgia:
            from tkinter import ttk
            page = ttk.Frame(self.body, style="Classic.TFrame")
            self.body.add(page, text=i18n.tr(title))
            scroll = ctk.CTkScrollableFrame(page, fg_color=look.N_FACE)      # a ttk page has no colour to take
            scroll.pack(fill="both", expand=True, padx=4, pady=6)
            card = ctk.CTkFrame(scroll, fg_color="transparent")
            card.pack(fill="x")
            card._page = page
        else:
            ctk.CTkLabel(self.body, text=title, font=ctk.CTkFont(size=14, weight="bold"), text_color="gray",
                         anchor="w").pack(fill="x", padx=8, pady=(10, 2))
            card = ctk.CTkFrame(self.body, corner_radius=12)
            card.pack(fill="x", padx=4, pady=2)
        card.columnconfigure(0, weight=1)
        card._row = 0
        self._cards[title] = card
        return card

    def show_tab(self, title):
        """Show one group: its tab ("Nostalji"), or scroll the list down to it."""
        card = self._cards.get(title)
        if card is None:
            return
        try:
            if self.nostalgia:
                self.body.select(card._page)
            else:
                self.update_idletasks()
                self.body._parent_canvas.yview_moveto(max(0.0, card.winfo_y() - 30) / max(1, self.body.winfo_height()))
        except (TclError, AttributeError):
            pass

    def current_tab(self):
        """The group whose tab is open ("" when the groups are one long list)."""
        if not self.nostalgia:
            return ""
        try:
            shown = str(self.body.select())
            return next((t for t, c in self._cards.items() if str(c._page) == shown), "")
        except TclError:
            return ""

    def _add(self, card, title, hint, widget):
        # both fill their column and wrap at its width (a wide control next to them leaves less room)
        t = ctk.CTkLabel(card, text=title, anchor="w", font=ctk.CTkFont(weight="bold"), wraplength=380,
                         justify="left")
        t.grid(row=card._row, column=0, sticky="ew", padx=16, pady=(8, 0))
        h = ctk.CTkLabel(card, text=hint, anchor="w", text_color=look.grey_text(), font=ctk.CTkFont(size=11),
                         wraplength=380, justify="left")
        h.grid(row=card._row + 1, column=0, sticky="ew", padx=16, pady=(0, 6))
        widget.grid(row=card._row, column=1, rowspan=2, padx=16, sticky="e")
        card._row += 2
        return t, h

    def _switch(self, card, command):
        """An on / off control: a switch, or a plain tick box in the "Nostalji" look (no switches back then)."""
        if self.nostalgia:
            return ctk.CTkCheckBox(card, text="", width=24, checkbox_width=16, checkbox_height=16, command=command)
        return ctk.CTkSwitch(card, text="", command=command)

    @staticmethod
    def _set_switch(switch, on):
        switch.select() if on else switch.deselect()

    # ---- entries
    def _save_proxy(self):
        ok = self.app.apply_proxy(self.proxy_entry.get())
        self.proxy_entry.configure(border_color=look.entry_border() if ok else BAD)
        return ok

    def _test_proxy(self):
        if not self._save_proxy():
            return
        self.proxy_hint.configure(text="Deneniyor…", text_color=BUSY)
        proxy = self.proxy_entry.get().strip()

        def work():
            self._proxy_result = check_connection(proxy=proxy)

        threading.Thread(target=work, daemon=True).start()

    def _save_schedule(self):
        ok_start = self.app.apply_schedule("schedule_start", self.schedule_start_entry.get())
        ok_stop = self.app.apply_schedule("schedule_stop", self.schedule_stop_entry.get())
        normal = look.entry_border()
        self.schedule_start_entry.configure(border_color=normal if ok_start else BAD)
        self.schedule_stop_entry.configure(border_color=normal if ok_stop else BAD)
        return ok_start and ok_stop

    def _save_port(self):
        ok = self.app.apply_bridge_port(self.bridge_port_entry.get())
        self.bridge_port_entry.configure(border_color=look.entry_border() if ok else BAD)
        return ok

    def _sync(self):
        """The end action is one-shot (the menu goes back to 'do nothing' when it fires) and the
        proxy test answers from another thread."""
        try:
            if self.after_menu.get() != self.app.after_all:
                self.after_menu.set(self.app.after_all)
            if self._proxy_result is not None:
                ok, text = self._proxy_result
                self._proxy_result = None
                self.proxy_hint.configure(text=("✓ " if ok else "✖ ") + text, text_color=GOOD if ok else BAD)
            self.after(500, self._sync)
        except TclError:
            return


class CountdownDialog(ctk.CTkToplevel):
    """'The computer will shut down in N seconds' with a cancel button."""

    def __init__(self, app, text, seconds, on_done):
        super().__init__(app)
        set_window_icon(self)
        self.title("DISO")
        self.geometry("420x190")
        self.resizable(False, False)
        self.transient(app)
        self.attributes("-topmost", True)
        self.text, self.left, self.on_done = text, int(seconds), on_done
        self._cancelled = False
        self.label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=15), justify="center")
        self.label.pack(expand=True, padx=20, pady=(24, 8))
        ctk.CTkButton(self, text="İptal", width=130, fg_color=BAD, hover_color=BAD_HOVER,
                      command=self.cancel).pack(pady=(0, 22))
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self._tick()

    def cancel(self):
        self._cancelled = True
        self.destroy()

    def _tick(self):
        try:
            if self._cancelled:
                return
            if self.left <= 0:
                self.destroy()
                self.on_done()
                return
            self.label.configure(text=f"{self.text}\n\n{self.left} saniye sonra")
            self.left -= 1
            self.after(1000, self._tick)
        except TclError:
            return


class PlaylistDialog(ctk.CTkToplevel):
    """A playlist was found: tick the videos you want."""

    CHUNK = 25   # rows are created a few at a time so a 500-video list does not freeze the window

    def __init__(self, app, entries, settings):
        super().__init__(app)
        set_window_icon(self)
        self.app, self.entries, self.settings = app, entries, settings
        self.vars = [ctk.BooleanVar(value=True) for _ in entries]
        self.title("Oynatma listesi")
        w, h = fit_geometry(self, 660, 640)
        self.minsize(min(520, w), min(400, h))
        self.transient(app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text=f"{len(entries)} video bulundu", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 0))
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=20, pady=8)
        ctk.CTkButton(bar, text="Hepsini seç", width=110, height=28,
                      command=lambda: self.select_all(True)).pack(side="left")
        ctk.CTkButton(bar, text="Hiçbirini seçme", width=120, height=28,
                      command=lambda: self.select_all(False)).pack(side="left", padx=6)
        self.count_label = ctk.CTkLabel(bar, text="", text_color="gray")
        self.count_label.pack(side="left", padx=10)
        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 6))
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=20, pady=(6, 16))
        foot.columnconfigure(0, weight=1)
        ctk.CTkButton(foot, text="İptal", width=100, fg_color="gray40", command=self.destroy).grid(row=0, column=1, padx=6)
        self.go_btn = ctk.CTkButton(foot, text="", width=150, command=self.confirm)
        self.go_btn.grid(row=0, column=2)
        self._count()
        self._fill(0)

    def _fill(self, start):
        try:
            for i in range(start, min(start + self.CHUNK, len(self.entries))):
                title = (self.entries[i][1] or self.entries[i][0])[:80]
                length = human_duration(self.entries[i][2] if len(self.entries[i]) > 2 else 0)
                text = f"{i + 1}. {title}" + (f"   ({length})" if length else "")
                ctk.CTkCheckBox(self.list_frame, text=text, variable=self.vars[i],
                                command=self._count).pack(anchor="w", padx=8, pady=3)
            if start + self.CHUNK < len(self.entries):
                self.after(15, lambda: self._fill(start + self.CHUNK))
        except TclError:  # closed while filling
            return

    def _count(self):
        n = sum(1 for v in self.vars if v.get())
        self.count_label.configure(text=f"{n} seçili")
        self.go_btn.configure(text=f"⬇ İndir ({n})", state="normal" if n else "disabled")

    def select_all(self, flag):
        for v in self.vars:
            v.set(flag)
        self._count()

    def chosen(self):
        picked = [e for e, v in zip(self.entries, self.vars) if v.get()]
        like = getattr(self.entries, "like", None)          # keeps the playlist's name
        return like(picked) if like else picked

    def confirm(self):
        chosen = self.chosen()
        self.destroy()
        if chosen:
            self.app.add_playlist_selection(chosen, self.settings)


class InfoDialog(ctk.CTkToplevel):
    """What yt-dlp knows about a link: qualities with sizes, subtitles. Pick one to download it."""

    def __init__(self, app, url):
        super().__init__(app)
        set_window_icon(self)
        self.app, self.url = app, url
        self.title("Bağlantı bilgisi")
        w, h = fit_geometry(self, 560, 560)
        self.minsize(min(480, w), min(360, h))
        self.transient(app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.status = ctk.CTkLabel(self.body, text="Bilgi alıyorum…", text_color="gray")
        self.status.pack(pady=40)
        self.result = None   # ("ok", info) / ("error", text), set by the loading thread
        threading.Thread(target=self._load, daemon=True).start()
        self.after(150, self._poll)

    def _load(self):
        try:
            self.result = ("ok", ve.fetch_info(self.url, self.app.cookie_menu.get()))
        except Exception as e:  # noqa: BLE001
            self.result = ("error", ve.pretty_error(e))

    def _poll(self):
        try:
            if self.result is None:
                self.after(150, self._poll)
                return
            kind, data = self.result
            self.status.destroy()
            self._render(data) if kind == "ok" else self._fail(data)
        except TclError:
            return

    def _fail(self, text):
        ctk.CTkLabel(self.body, text="Bu link hakkında bilgi alamadım", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=8, pady=(8, 4))
        ctk.CTkLabel(self.body, text=text, text_color=BAD, wraplength=480, justify="left").pack(anchor="w", padx=8)

    def _render(self, info):
        ctk.CTkLabel(self.body, text=info["title"] or self.url, font=ctk.CTkFont(size=17, weight="bold"),
                     wraplength=490, justify="left").pack(anchor="w", padx=8, pady=(4, 2))
        meta = " • ".join(x for x in (info["uploader"], human_duration(info["duration"])) if x)
        if meta:
            ctk.CTkLabel(self.body, text=meta, text_color="gray").pack(anchor="w", padx=8)
        if info["is_playlist"]:
            ctk.CTkLabel(self.body, text=f"Bu bir oynatma listesi ({info['entries']} video). "
                                         "İndirmek için 'Oynatma listesi' kutusunu işaretleyip ekle.",
                         wraplength=490, justify="left", text_color=WARN).pack(anchor="w", padx=8, pady=8)
            return
        self._clip_box(info["duration"])
        ctk.CTkLabel(self.body, text="Video kaliteleri", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=(14, 4))
        for q in info["qualities"][:14]:
            self._row(self._quality_text(q), "İndir", lambda q=q: self._download(ve.quality_for_height(q["height"]), "video"))
        if not info["qualities"]:
            ctk.CTkLabel(self.body, text="Kalite listesini çıkaramadım, en iyi kaliteyle indiririm.",
                         text_color="gray").pack(anchor="w", padx=8)
            self._row("En iyi kalite", "İndir", lambda: self._download("En iyi", "video"))
        size = f" • ~{human_size(info['audio_size'])}" if info["audio_size"] else ""
        self._row(f"Sadece ses (MP3){size}", "MP3 indir", lambda: self._download(None, "audio"))
        if info["subtitles"] or info["auto_subtitles"]:
            text = "Altyazı: " + (", ".join(info["subtitles"]) or "yok")
            if info["auto_subtitles"]:
                text += f"  (+{info['auto_subtitles']} otomatik dil)"
            ctk.CTkLabel(self.body, text=text, text_color="gray", wraplength=490, justify="left").pack(
                anchor="w", padx=8, pady=(12, 0))

    @staticmethod
    def _quality_text(q):
        parts = [f"{q['height']}p"]
        if q["fps"] > 30:
            parts.append(f"{q['fps']} fps")
        if q["codec"]:
            parts.append(q["codec"])
        if q["size"]:
            parts.append(f"~{human_size(q['size'])}")
        return " • ".join(parts)

    def _row(self, text, button, command):
        row = ctk.CTkFrame(self.body)
        row.pack(fill="x", padx=8, pady=3)
        ctk.CTkLabel(row, text=text, anchor="w").pack(side="left", padx=12, pady=8)
        ctk.CTkButton(row, text=button, width=90, height=28, command=command).pack(side="right", padx=8)

    # ------------------------------------------------------------------ ✂ only a part of the video
    def _clip_box(self, duration):
        self.duration = duration or 0
        box = ctk.CTkFrame(self.body)
        box.pack(fill="x", padx=8, pady=(12, 0))
        ctk.CTkLabel(box, text="✂ Sadece bir kısmını indir", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(8, 4))
        self.clip_start = ctk.CTkEntry(box, width=90, placeholder_text="0:00")
        self.clip_end = ctk.CTkEntry(box, width=90, placeholder_text=human_duration(duration) or "—")
        for col, (text, entry) in enumerate((("Başlangıç", self.clip_start), ("Bitiş", self.clip_end))):
            ctk.CTkLabel(box, text=text).grid(row=1, column=col * 2, padx=(12, 6), pady=(0, 4), sticky="w")
            entry.grid(row=1, column=col * 2 + 1, pady=(0, 4), sticky="w")
            entry.bind("<KeyRelease>", lambda e: self._show_clip())
        self.clip_note = ctk.CTkLabel(box, text="", text_color="gray", anchor="w", justify="left", wraplength=470)
        self.clip_note.grid(row=2, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 8))
        self._show_clip()

    def clip(self):
        """(None, None): the whole video; ([start, end], None): only that part; (None, why): not right."""
        try:
            start = parse_time(self.clip_start.get())
            end = parse_time(self.clip_end.get())
        except ValueError:
            return None, "Zamanı 1:30 ya da 1:02:03 gibi yaz"
        if start is None and end is None:
            return None, None
        start = start or 0.0
        if end is None:
            if not self.duration:
                return None, "Bitişi de yaz (videonun uzunluğunu bilmiyorum)"
            end = float(self.duration)
        if self.duration:
            end = min(end, float(self.duration))
            if start >= self.duration:
                return None, f"Başlangıç videonun sonundan sonra (video {human_duration(self.duration)})"
        if end - start < 1:
            return None, "Bitiş başlangıçtan sonra olmalı"
        return [start, end], None

    def _show_clip(self):
        clip, why = self.clip()
        if why:
            text, colour = why, BAD
        elif clip:
            text, colour = f"Yalnızca {clip_text(clip)} arası inecek ({human_duration(clip[1] - clip[0])})", GOOD
        else:
            text, colour = "Boş bırakırsan videonun tamamı iner. Doldurursan aşağıdaki düğmeler yalnızca o kısmı indirir.", "gray"
        set_if_changed(self.clip_note, text=text, text_color=colour)

    def _download(self, quality, kind):
        clip, why = self.clip() if hasattr(self, "clip_start") else (None, None)
        if why:
            self._show_clip()
            return
        self.destroy()
        self.app.download_quality(self.url, quality, kind, clip=clip)


class AboutDialog(ctk.CTkToplevel):
    """Which version this is, where everything lives, and one button that copies the details
    to send when something does not work. The facts are looked up away from the window (starting
    deno to ask for its version takes a moment)."""

    def __init__(self, app, provider=about.facts):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.title(f"{brand.NAME} hakkında")
        w, h = fit_geometry(self, 660, 660)
        self.minsize(min(500, w), min(460, h))
        self.transient(app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.rows = None
        self._events = queue.Queue()

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 8))
        self._logo = logo_image(88)
        ctk.CTkLabel(head, text="", image=self._logo).grid(row=0, column=0, rowspan=3, padx=(0, 18))
        ctk.CTkLabel(head, text=brand.NAME, font=ctk.CTkFont(size=32, weight="bold")).grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(head, text=f"Sürüm {brand.VERSION_LABEL}", font=ctk.CTkFont(size=14)).grid(row=1, column=1, sticky="w")
        ctk.CTkLabel(head, text="Dosya, video ve müzik indirme yöneticisi", text_color="gray").grid(
            row=2, column=1, sticky="nw")
        ctk.CTkLabel(self, text="Bir şey ters giderse aşağıdaki “Detayları kopyala”ya bas, sonra “Bize ulaş” ile GitHub'da "
                                "yeni bir sorun aç ve metni oraya yapıştır.",
                     wraplength=600, justify="left", anchor="w", text_color="gray").grid(
            row=1, column=0, sticky="ew", padx=28, pady=(0, 8))
        self.body = ctk.CTkScrollableFrame(self)
        self.body.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 6))
        self.body.columnconfigure(1, weight=1)
        self.waiting = ctk.CTkLabel(self.body, text="Bilgileri topluyorum…", text_color="gray")
        self.waiting.grid(row=0, column=0, columnspan=2, pady=20)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=24, pady=(6, 18))
        foot.columnconfigure(4, weight=1)
        self.copy_btn = ctk.CTkButton(foot, text="📋 Detayları kopyala", width=150, state="disabled", command=self.copy_details)
        self.copy_btn.grid(row=0, column=0)
        self.contact_btn = ctk.CTkButton(foot, text="✉ Bize ulaş", width=110, command=self.contact)
        self.contact_btn.grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(foot, text="📂 Veri klasörü", width=120, command=self.open_data).grid(row=0, column=2, padx=8)
        ctk.CTkButton(foot, text="📜 Günlük", width=90, command=app.open_log).grid(row=0, column=3)
        ctk.CTkButton(foot, text="Kapat", width=90, command=self.destroy).grid(row=0, column=5)

        threading.Thread(target=self._collect, args=(provider,), daemon=True, name="about-facts").start()
        self.after(100, self._poll)

    def _collect(self, provider):
        try:
            self._events.put(provider())
        except Exception:  # noqa: BLE001 - the window must not wait for ever
            log.exception("could not collect the details")
            self._events.put([("Sürüm", brand.VERSION_LABEL), ("Hata", "bilgiler toplanamadı, ayrıntı günlükte")])

    def _poll(self):
        try:
            self.rows = self._events.get_nowait()
        except queue.Empty:
            try:
                self.after(100, self._poll)
            except TclError:
                pass
            return
        try:
            self.waiting.destroy()
            for i, (key, value) in enumerate(self.rows):
                ctk.CTkLabel(self.body, text=key, text_color="gray", anchor="nw", width=120).grid(
                    row=i, column=0, sticky="nw", padx=(8, 10), pady=4)
                ctk.CTkLabel(self.body, text=value, anchor="w", justify="left", wraplength=340).grid(
                    row=i, column=1, sticky="ew", pady=4)
            self.copy_btn.configure(state="normal")
        except TclError:                                    # closed while the facts were coming
            return

    def copy_details(self):
        if self.rows is None:
            return
        self.clipboard_clear()
        self.clipboard_append(about.as_text(self.rows))
        self.app.notice("Detaylar panoya kopyalandı, “Bize ulaş” ile açılan sayfaya yapıştırabilirsin")

    def contact(self):
        webbrowser.open(brand.CONTACT_URL)

    def open_data(self):
        open_in_file_manager(app_data_dir())


class BridgeApi:
    """What the browser bridge (another thread) may do. Never touches widgets directly."""

    def __init__(self, app):
        self.app = app

    @property
    def add_enabled(self):
        return bool(self.app.cfg.get("bridge_on"))

    def add(self, urls, extra, kind):
        return self.app.bridge_add(urls, extra, kind)

    def status(self):
        return self.app.bridge_status()

    def show(self):
        self.app._ui_calls.put(self.app._show_window)

    def extension_seen(self):
        if not self.app.cfg.get("extension_seen"):
            self.app.cfg.set("extension_seen", True)


class App(NostalgiaWindow, ctk.CTk):
    def __init__(self, minimized=False):
        self.cfg = Config()
        ctk.set_appearance_mode(look.appearance(THEMES.get(self.cfg.get("theme"), "dark")))
        super().__init__()
        # Garbage collection must run on this (the window's) thread only. Collected Tk objects
        # (fonts ...) call into Tcl from their finalizer; on a download thread that call waits for
        # this thread, and if the download thread holds a lock this thread needs, both freeze.
        # So automatic collection is off and _tick() collects every few seconds instead.
        gc.disable()
        setup_logging()
        log.info("DISO %s started", __version__)
        self.title("DISO")
        w, h = fit_geometry(self, 1000, 820)
        self.minsize(min(900, w), min(560, h))
        self._set_icon()
        # where the windows were before "restart now" (a new look / language): DISO comes back the same way
        view = self.cfg.get("restart_view")
        self.cfg.set("restart_view", {})
        self._view = view if isinstance(view, dict) and not minimized else {}
        if self._view.get("geometry"):
            try:
                self.geometry(self._view["geometry"])
            except TclError:
                pass
        if self._view.get("mode") == MODE_MUSIC:
            self.withdraw()                  # the music window comes up instead (see _restore_view)

        self.cfg.sanitize({
            "kind": list(KIND_LABELS), "quality": ve.QUALITIES, "bitrate": ve.BITRATES,
            "connections": CONNECTIONS, "cookies": ve.BROWSERS, "speed_limit": list(SPEED_LIMITS),
            "sort": SORTS, "filter": FILTERS, "subs": SUBTITLE_CHOICES, "theme": list(THEMES), "look": look.STYLES,
            "language": list(i18n.LANGUAGES),
            "auto_retry": list(AUTO_RETRY.values()),
        })
        self.nostalgia = look.is_nostalgia()
        if not 1 <= self.cfg.get("max_parallel") <= 8:
            self.cfg.data["max_parallel"] = 3
        self.manager = DownloadManager(max_parallel=self.cfg.get("max_parallel"),
                                       max_retries=self.cfg.get("auto_retry"))
        LIMITER.set_rate(SPEED_LIMITS[self.cfg.get("speed_limit")] * 1024)
        try:
            set_proxy(self.cfg.get("proxy"))
        except ValueError:
            self.cfg.data["proxy"] = ""
        if self.cfg.get("start_with_windows"):
            startup.set_enabled(True)   # keeps the registry entry pointing at this copy of the app
        self.updates = updater.Updater()
        self.updates.ffmpeg_busy = lambda: any(i.state == PROCESSING for i in self.manager.items)
        self.update_panel = None
        self.settings_panel = None
        self.about_dialog = None
        self.bridge = None
        self.tray = None
        self.rows = {}
        self.selected = set()
        self.after_all = NO_END_ACTION   # one-shot, not saved
        self.queue_note = ""             # shown on queued rows while the scheduler holds the queue
        self._ui_calls = queue.Queue()   # functions other threads want run on this thread
        self._sched_paused = []          # items the scheduler paused at the stop time
        self._now = datetime.datetime.now
        self._order = None   # None: the list was never laid out yet
        self._had_work = False
        self._phase_done = 0
        self._last_clip = ""
        self._notice = ""
        self._notice_until = 0
        self._tick_no = 0
        self._ffmpeg_ok = bool(find_ffmpeg())
        self._closing = False
        self.restart_requested = False   # main() starts the program again after it has closed
        self._hidden_hint_shown = False
        self._btn_text = ""
        self.mode = MODE_DOWNLOAD
        self.music = None                # the music player window, made the first time it is wanted
        self.playlist_store = None       # the saved playlists, loaded the first time they are needed
        self.song_dialog = None          # 'Hangi listeye ekleyeyim?' while it is open
        self.lyrics_fetcher = lyrics.Fetcher()   # lyrics of found songs, looked up in the background
        self.history = history.History()         # every finished download, also after it leaves the list
        self.history_window = None
        self.shortcuts_window = None
        self.channel_store = channels.Store()             # 📺 followed channels: new videos are announced, never downloaded
        self.channel_watcher = channels.Watcher(self.channel_store)
        self.app_update = app_update.AppUpdate()
        self.channels_window = None
        self.address_dialog = None

        if self.nostalgia:
            self._n_build()          # menu bar, toolbar, categories and a table (app/classic_ui.py)
        else:
            self._build_layout()

        self._on_kind(self.kind_menu.get())
        self.clip_var.set(bool(self.cfg.get("clip_watch")))
        self._last_clip = self._clipboard_text()  # what is in the clipboard now is not "new"
        self.protocol("WM_DELETE_WINDOW", self._on_window_x)
        if MAC:     # the Dock icon brings the window back, ⌘Q quits the way the menu's "Quit" does
            self.createcommand("::tk::mac::ReopenApplication", self._show_window)
            self.createcommand("::tk::mac::Quit", self._on_close)
        self._bind_shortcuts()
        self._announce_version()         # before anything that can fail: a warning must be the last word
        self._start_bridge()
        self._started_hidden = minimized
        if not minimized:
            self.after(EXTENSION_OFFER_DELAY, self._maybe_offer_extension)
        if self.cfg.get("tray_on_close") or minimized:
            self._ensure_tray()
        if minimized:
            self.after(50, self._hide_to_tray)
        self.after(300, self._tick)
        if self._view:
            self.after(60, self._restore_view)
        self.updates.start()  # checks and updates yt-dlp / FFmpeg in the background
        self.app_update.start()  # looks for a new DISO now and then; only tells, never installs by itself
        self.channel_watcher.start()

    # ------------------------------------------------------------------------ layout
    def _build_layout(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)
        self._build_top()
        self._build_options()
        self._build_toolbar()
        self._build_filter_bar()
        self.list_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.list_frame.grid(row=5, column=0, sticky="nsew", padx=16, pady=(0, 6))
        self.empty_label = ctk.CTkLabel(self.list_frame, text="", text_color="gray")
        self._build_update_bar()
        self.status = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self.status.grid(row=7, column=0, sticky="ew", padx=20, pady=(0, 4))
        self.mode_bar = mode_bar(self, MODE_DOWNLOAD, self._switch_mode)
        self.mode_bar.grid(row=8, column=0, sticky="ew", padx=16, pady=(0, 12))

    def _set_icon(self):
        ico = resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(ico) and os.name == "nt":
            try:
                self.iconbitmap(ico)
                self.after(250, lambda: self.iconbitmap(ico))  # customtkinter puts its own icon back
            except Exception:
                pass
        elif os.name != "nt":
            set_window_icon(self)

    def _build_top(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        head.columnconfigure(1, weight=1)
        self._logo = logo_image(54)                          # kept on self: a picture nobody holds disappears
        ctk.CTkLabel(head, text="" if self._logo else "⚡", image=self._logo, width=58, height=58).grid(
            row=0, column=0, rowspan=2, padx=(0, 14))
        titlebox = ctk.CTkFrame(head, fg_color="transparent")
        titlebox.grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(titlebox, text=brand.NAME, font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        self.beta_badge = ctk.CTkLabel(
            titlebox, text=brand.CHANNEL.upper() or brand.VERSION_LABEL, width=48, height=22, corner_radius=8,
            fg_color=look.ACCENT_SOFT if look.is_new() else ("gray78", "gray28"),
            text_color=look.ACCENT if look.is_new() else ("gray20", "gray85"), font=ctk.CTkFont(size=11, weight="bold"))
        self.beta_badge.pack(side="left", padx=(10, 0), pady=(8, 0))
        self.beta_badge.bind("<Button-1>", lambda e: self.open_about())
        # the language, one click away (it changes when DISO starts again, which it offers)
        self.language_switch = ctk.CTkSegmentedButton(titlebox, values=list(LANGUAGE_SHORT), width=78, height=24,
                                                      font=ctk.CTkFont(size=11, weight="bold"),
                                                      command=self._on_language_switch)
        self.language_switch.set(LANGUAGE_NAMES[self.cfg.get("language")])
        self.language_switch.pack(side="left", padx=(10, 0), pady=(8, 0))
        ctk.CTkLabel(head, text="Linki yapıştır, gerisini bana bırak • Dosya, video, MP3 • YouTube, Instagram, TikTok, X…",
                     text_color="gray").grid(row=1, column=1, sticky="nw")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 0))
        row.columnconfigure(0, weight=1)
        hint = "Linki buraya yapıştır (birden fazlaysa araya boşluk koy)…"
        self.url_entry = ctk.CTkEntry(row, height=44, placeholder_text=hint)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.url_entry.bind("<Return>", lambda e: self.add_from_entry())
        ctk.CTkButton(row, text="📋", width=48, height=44, command=self._paste).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(row, text="📄", width=48, height=44, command=self._import_file).grid(
            row=0, column=2, padx=(0, 8))
        ctk.CTkButton(row, text="ℹ", width=48, height=44, command=self._show_info).grid(row=0, column=3, padx=(0, 8))
        self.history_button = ctk.CTkButton(row, text="📊", width=48, height=44, command=self.open_history)
        self.history_button.grid(row=0, column=4, padx=(0, 8))
        # 📺 followed channels; "📺 3" when 3 new videos came
        self.channels_btn = ctk.CTkButton(row, text="📺", width=48, height=44, command=self.open_channels)
        self.channels_btn.grid(row=0, column=5, padx=(0, 8))
        ctk.CTkButton(row, text="⬇  İndir", height=44, width=130, font=ctk.CTkFont(size=16, weight="bold"),
                      command=self.add_from_entry).grid(row=0, column=6)

    def _build_options(self):
        opt = ctk.CTkFrame(self)
        opt.grid(row=2, column=0, sticky="ew", padx=16, pady=10)
        for c in range(6):
            opt.columnconfigure(c, weight=1)
        cfg = self.cfg

        def label(text, col):
            ctk.CTkLabel(opt, text=text).grid(row=0, column=col, padx=10, pady=(8, 0), sticky="w")

        label("Ne indirilecek", 0)
        # wide enough for "Otomatik (dosya / video)" (it was cut off at the arrow)
        self.kind_menu = ctk.CTkOptionMenu(opt, values=list(KIND_LABELS), width=185, command=self._on_kind)
        self.kind_menu.set(cfg.get("kind"))
        self.kind_menu.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="ew")

        label("Video kalitesi", 1)
        self.quality_menu = ctk.CTkOptionMenu(opt, values=ve.QUALITIES,
                                              command=lambda v: cfg.set("quality", v))
        self.quality_menu.set(cfg.get("quality"))
        self.quality_menu.grid(row=1, column=1, padx=10, pady=(0, 6), sticky="ew")

        label("MP3 kalitesi (kbps)", 2)
        self.bitrate_menu = ctk.CTkOptionMenu(opt, values=ve.BITRATES,
                                              command=lambda v: cfg.set("bitrate", v))
        self.bitrate_menu.set(cfg.get("bitrate"))
        self.bitrate_menu.grid(row=1, column=2, padx=10, pady=(0, 6), sticky="ew")

        label("Bağlantı sayısı (hız)", 3)
        self.conn_menu = ctk.CTkOptionMenu(opt, values=CONNECTIONS,
                                           command=lambda v: cfg.set("connections", v))
        self.conn_menu.set(cfg.get("connections"))
        self.conn_menu.grid(row=1, column=3, padx=10, pady=(0, 6), sticky="ew")

        label("Giriş çerezleri", 4)
        self.cookie_menu = ctk.CTkOptionMenu(opt, values=ve.BROWSERS,
                                             command=lambda v: cfg.set("cookies", v))
        self.cookie_menu.set(cfg.get("cookies"))
        self.cookie_menu.grid(row=1, column=4, padx=10, pady=(0, 6), sticky="ew")

        label("Altyazı (video)", 5)
        self.subs_menu = ctk.CTkOptionMenu(opt, values=SUBTITLE_CHOICES, command=lambda v: cfg.set("subs", v))
        self.subs_menu.set(cfg.get("subs"))
        self.subs_menu.grid(row=1, column=5, padx=10, pady=(0, 6), sticky="ew")

        checks = ctk.CTkFrame(opt, fg_color="transparent")
        checks.grid(row=2, column=0, columnspan=6, sticky="w", padx=6, pady=(0, 4))
        self.playlist_var = ctk.BooleanVar(value=bool(cfg.get("playlist")))
        ctk.CTkCheckBox(checks, text="Oynatma listesi", variable=self.playlist_var,
                        command=lambda: cfg.set("playlist", bool(self.playlist_var.get()))).pack(
            side="left", padx=6)
        self.folders_var = ctk.BooleanVar(value=bool(cfg.get("sort_folders")))
        ctk.CTkCheckBox(checks, text="Türe göre klasör (Video, Müzik, Arşiv…)", variable=self.folders_var,
                        command=lambda: cfg.set("sort_folders", bool(self.folders_var.get()))).pack(
            side="left", padx=14)
        self.cover_var = ctk.BooleanVar(value=bool(cfg.get("cover")))
        ctk.CTkCheckBox(checks, text="MP3'e kapak resmi", variable=self.cover_var,
                        command=lambda: cfg.set("cover", bool(self.cover_var.get()))).pack(side="left", padx=6)

        folder = ctk.CTkFrame(opt, fg_color="transparent")
        folder.grid(row=3, column=0, columnspan=6, sticky="ew", padx=10, pady=(0, 10))
        folder.columnconfigure(0, weight=1)
        self.folder_entry = ctk.CTkEntry(folder, height=34)
        self.folder_entry.insert(0, cfg.get("folder") or default_download_dir())
        self.folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.folder_entry.bind("<FocusOut>", lambda e: self._save_folder())
        self.folder_entry.bind("<Return>", lambda e: self._save_folder())
        ctk.CTkButton(folder, text="Klasör Seç", width=110, height=34, command=self._pick_folder).grid(row=0, column=1)

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 6))
        ctk.CTkLabel(bar, text="İndirmeler", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=(4, 12))
        ctk.CTkButton(bar, text="▶ Hepsini başlat", width=130, height=30,
                      command=self.manager.resume_all).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="⏸ Hepsini duraklat", width=140, height=30,
                      command=self.manager.pause_all).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="🧹 Bitenleri temizle", width=140, height=30,
                      command=self.manager.clear_finished).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="⚙ Ayarlar", width=100, height=30,
                      command=self._open_settings).pack(side="right", padx=3)
        self.updates_btn = ctk.CTkButton(bar, text="⟳ Güncellemeler", width=120, height=30,
                                         command=self._open_updates)
        self.updates_btn.pack(side="right", padx=3)
        self.clip_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(bar, text="Panoyu izle", variable=self.clip_var,
                        command=self._on_clip_toggle).pack(side="right", padx=(6, 4))

    def _build_filter_bar(self):
        """Search, filter, sort and the actions for the ticked rows."""
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 6))
        bar.columnconfigure(0, weight=1)
        # no textvariable here: customtkinter hides the placeholder when one is used
        self.search_entry = ctk.CTkEntry(bar, height=30, placeholder_text="🔍 Listede ara…")
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.search_entry.bind("<KeyRelease>", lambda e: self._sync_rows())
        self.search_entry.bind("<Escape>", lambda e: self._clear_search())
        self.filter_menu = ctk.CTkOptionMenu(bar, values=FILTERS, width=130, height=30,
                                             command=self._on_filter)
        self.filter_menu.set(self.cfg.get("filter"))
        self.filter_menu.grid(row=0, column=1, padx=3)
        self.sort_menu = ctk.CTkOptionMenu(bar, values=SORTS, width=170, height=30,
                                           command=self._on_sort)
        self.sort_menu.set(self.cfg.get("sort"))
        self.sort_menu.grid(row=0, column=2, padx=3)

        self.select_all_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(bar, text="Hepsini seç", variable=self.select_all_var, width=110,
                        command=self._on_select_all).grid(row=0, column=3, padx=(12, 6))
        self.sel_label = ctk.CTkLabel(bar, text="", width=80, anchor="w", text_color="gray")
        self.sel_label.grid(row=0, column=4)
        self.sel_buttons = [
            ctk.CTkButton(bar, text="▶", width=38, height=30, command=self._sel_resume),
            ctk.CTkButton(bar, text="⏸", width=38, height=30, command=self._sel_pause),
            ctk.CTkButton(bar, text="✖", width=38, height=30, fg_color=BAD, hover_color=BAD_HOVER,
                          command=self._sel_remove),
        ]
        for i, b in enumerate(self.sel_buttons):
            b.grid(row=0, column=5 + i, padx=2)
            b.configure(state="disabled")

    def _build_update_bar(self):
        """Thin strip above the status line: shows what the startup update is doing."""
        self.update_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.update_bar.columnconfigure(0, weight=1)
        self.update_label = ctk.CTkLabel(self.update_bar, text="", anchor="w", text_color="gray")
        self.update_label.grid(row=0, column=0, sticky="ew", padx=4)
        self.update_progress = ctk.CTkProgressBar(self.update_bar, height=8)
        self.update_progress.set(0)
        self.update_progress.grid(row=1, column=0, sticky="ew", padx=4, pady=(2, 4))
        self.update_bar.grid(row=6, column=0, sticky="ew", padx=20, pady=(0, 2))
        self.update_bar.grid_remove()

    def _bind_shortcuts(self):
        self.bind("<Control-v>", self._on_ctrl_v)
        self.bind("<Control-a>", self._on_ctrl_a)
        self.bind("<Delete>", self._on_delete_key)
        self.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.bind("<F1>", lambda e: self.open_shortcuts())

    def _typing(self) -> bool:
        """True while the cursor is in a text box: its own shortcuts must work there."""
        try:
            return isinstance(self.focus_get(), (tk.Entry, tk.Text))
        except (KeyError, TclError):
            return False

    # ----------------------------------------------------------------------- actions
    def _on_kind(self, label):
        kind = KIND_LABELS.get(label, "auto")
        self.cfg.set("kind", label)
        self.quality_menu.configure(state="normal" if kind in ("auto", "video") else "disabled")
        self.bitrate_menu.configure(state="normal" if kind == "audio" else "disabled")
        self.subs_menu.configure(state="normal" if kind in ("auto", "video") else "disabled")

    def _clipboard_text(self):
        try:
            return self.clipboard_get().strip()
        except Exception:
            return ""

    def _on_clip_toggle(self):
        # links that are already in the clipboard are NOT added, only new ones
        self._last_clip = self._clipboard_text()
        self.cfg.set("clip_watch", bool(self.clip_var.get()))
        self.notice("Pano izleme açık: kopyaladığın her yeni linki kendim eklerim"
                    if self.clip_var.get() else "Pano izleme kapalı")

    def _watch_clipboard(self):
        if not self.clip_var.get():
            return
        text = self._clipboard_text()
        if text and text != self._last_clip:
            self._last_clip = text
            urls = [u for u in re.split(r"\s+", text) if is_url(u)]
            if urls and len(urls) == len(text.split()):
                if self.cfg.get("clip_ask"):
                    self.ask_clip(urls)
                    return
                self.add_urls(urls)
                self.notice(f"Panodan eklendi: {urls[0][:60]}")

    def ask_clip(self, urls):
        """📋 A link was copied: a small window in the corner asks what to do with it (it goes by itself)."""
        from .extra_ui import ClipPrompt
        old = getattr(self, "clip_prompt", None)
        try:
            if old is not None and old.winfo_exists():
                old.destroy()
        except TclError:
            pass
        self.clip_prompt = ClipPrompt(self, urls, self._clip_chosen)
        return self.clip_prompt

    def _clip_chosen(self, urls, kind):
        """The answer of the clipboard window: None = no, else "auto" / "video" / "audio"."""
        if kind is None:
            return
        if self.add_urls(urls, kind=kind) == 1:
            self.notice(f"Panodan eklendi: {urls[0][:60]}")

    def _on_ctrl_v(self, event=None):
        """Ctrl+V on the list (not in a text box) adds the links in the clipboard."""
        if self._typing():
            return
        urls = extract_urls(self._clipboard_text())
        if urls:
            self.add_urls(urls)
        else:
            self.notice("Panoda link göremedim")
        return "break"

    def _on_ctrl_a(self, event=None):
        if self._typing():
            return
        self.select_all_var.set(True)
        self._on_select_all()
        return "break"

    def _on_delete_key(self, event=None):
        if self._typing() or not self.selected:
            return
        self._sel_remove()
        return "break"

    def _clear_search(self):
        self.search_entry.delete(0, "end")
        self._sync_rows()

    def _save_folder(self):
        self.cfg.set("folder", self.folder_entry.get().strip())

    def _pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if d:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, d)
            self._save_folder()

    def _paste(self):
        try:
            text = self.clipboard_get().strip()
        except Exception:
            return
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, text)

    def _import_file(self):
        """Add every link of a .txt file (one per line, or any text that contains links), or a .torrent file."""
        path = filedialog.askopenfilename(title="Linklerin olduğu dosya ya da torrent",
                                          filetypes=[("Linkler ve torrentler", "*.txt *.csv *.url *.list *.torrent"),
                                                     ("Torrent dosyaları", "*.torrent"), ("Tüm dosyalar", "*.*")])
        if path:
            self._add_from_paths([path])

    def _settings(self) -> Settings:
        return Settings(
            kind=KIND_LABELS.get(self.kind_menu.get(), "auto"),
            quality=self.quality_menu.get(),
            bitrate=self.bitrate_menu.get(),
            connections=int(self.conn_menu.get()),
            folder=self.folder_entry.get().strip() or default_download_dir(),
            playlist=bool(self.playlist_var.get()),
            cookies=self.cookie_menu.get(),
            subs=self.subs_menu.get(),
            cover=bool(self.cover_var.get()),
            sort_folders=bool(self.folders_var.get()),
        )

    def settings_from_config(self) -> Settings:
        """The same choices read from the saved settings, not from the widgets: safe to call
        from another thread (the browser bridge). Playlists are not expanded."""
        c = self.cfg
        return Settings(
            kind=KIND_LABELS.get(c.get("kind"), "auto"), quality=c.get("quality"), bitrate=c.get("bitrate"),
            connections=int(c.get("connections")), folder=c.get("folder") or default_download_dir(),
            playlist=False, cookies=c.get("cookies"), subs=c.get("subs"), cover=bool(c.get("cover")),
            sort_folders=bool(c.get("sort_folders")))

    def notice(self, text, seconds=6):
        self._notice, self._notice_until = text, time.time() + seconds

    # ------------------------------------------------------------------ 🔧 is the file whole?
    def check_file(self, item):
        """🔧 Look whether a finished download is whole; offer to finish or download again what is not."""
        if getattr(item, "_checking", False):
            return
        item._checking = True
        self.notice(f"🔧 “{item.display_name}” kontrol ediliyor…", 30)
        url = item.url if item.kind == "file" else ""          # a video page says nothing about the file's size

        def work():
            try:
                verdict = repair.check(item.final_path, url, item.request_headers())
            except Exception as e:  # noqa: BLE001 - said to the user
                verdict = repair.Verdict(repair.UNKNOWN, str(e))
            self._ui_calls.put(lambda: self._file_checked(item, verdict))
        threading.Thread(target=work, daemon=True, name="check-file").start()

    def _file_checked(self, item, v):
        item._checking = False
        name = item.display_name
        if v.status == repair.OK:
            self.notice(f"✓ “{name}” sağlam, eksiği yok", 10)
        elif v.status == repair.UNKNOWN:
            self.notice(f"“{name}” kontrol edilemedi: {v.detail}", 10)
        elif v.status == repair.SHORT and v.resumable:
            if messagebox.askyesno("DISO", f"{name}\n\nDosyanın sonu eksik ({human_size(v.missing)} eksik).\n"
                                           "Yalnız eksik kısmı indirip dosyayı tamamlayayım mı?", parent=self):
                self._complete_file(item)
        else:
            if v.status in (repair.MISSING, repair.EMPTY):
                why = "Dosya yerinde yok." if v.status == repair.MISSING else "Dosya boş."
                text = f"{name}\n\n{why}\nBozuk dosyayı silip baştan indireyim mi?"
            elif v.status == repair.SHORT:
                text = f"{name}\n\nDosyanın sonu eksik ({human_size(v.missing)} eksik).\nBozuk dosyayı silip baştan indireyim mi?"
            else:
                text = f"{name}\n\nDosya bozuk görünüyor ({v.detail}).\nBozuk dosyayı silip baştan indireyim mi?"
            if messagebox.askyesno("DISO", text, parent=self):
                if item.final_path and os.path.isfile(item.final_path):
                    try:
                        os.remove(item.final_path)
                    except OSError as e:
                        self.notice(f"Dosya silinemedi: {e}", 10)
                        return
                self.manager.redownload(item)

    def _complete_file(self, item):
        """Download the missing end of a finished file (the part that is there stays)."""
        item._checking = True
        path = item.final_path

        def work():
            try:
                added = repair.complete_tail(path, item.url, item.request_headers(),
                                             progress=lambda n: setattr(item, "message", f"🔧 Eksik kısım: {human_size(n)}"))
                problem = repair.read_through(path)
                result = (added, problem)
            except Exception as e:  # noqa: BLE001 - said to the user
                result = (None, str(e))
            self._ui_calls.put(lambda: self._file_completed(item, *result))
        threading.Thread(target=work, daemon=True, name="complete-file").start()

    def _file_completed(self, item, added, problem):
        item._checking = False
        item.message = ""
        if added is None:
            self.notice(f"Tamamlanamadı: {problem}. “Baştan indir” ile yeniden indirebilirsin.", 12)
        elif problem:
            self.notice(f"Eksik kısım eklendi ama dosya hâlâ bozuk ({problem}). “Baştan indir”i dene.", 12)
        else:
            self.notice(f"✓ “{item.display_name}” tamamlandı ({human_size(added)} eklendi)", 10)
        self.manager.save()

    def add_urls(self, urls, kind=None):
        """Add links; returns how many were accepted. Links already in the list are skipped
        (unless that is switched off in the settings). With 'Oynatma listesi' ticked the link is
        opened as a playlist first (see _playlist_ready). `kind` ("video", "audio" ...) overrides
        what is chosen in the window."""
        s = self._settings()
        if kind:
            s.kind = kind
        skip = bool(self.cfg.get("block_duplicates"))
        good = [normalize_url(u) for u in urls if is_url(u)]
        added = duplicates = 0
        for u in good:
            if skip and self.manager.find_duplicate(u):
                duplicates += 1
            elif s.playlist and s.kind in ("auto", "video", "audio"):
                self._expand_async(u, s)
                added += 1
            elif self.manager.add_url(u, s, skip_duplicates=False):
                added += 1
        bad = len(urls) - len(good)
        if added and duplicates:
            self.notice(f"{added} bağlantı eklendi, {duplicates} tanesi zaten listedeydi")
        elif duplicates:
            self.notice(f"{duplicates} link zaten listedeydi, atladım")
        elif bad:
            self.notice(f"{bad} geçersiz linki atladım (http ya da https ile başlamalı)")
        elif added > 1:
            self.notice(f"{added} bağlantı eklendi")
        return added

    def add_from_entry(self):
        urls = [u for u in re.split(r"\s+", self.url_entry.get().strip()) if u]
        if not urls:
            self.notice("Önce bir link yapıştır bakalım.")
            return
        if self.add_urls(urls):
            self.url_entry.delete(0, "end")

    # ---------------------------------------------------------------------- playlists
    def _expand_async(self, url, s):
        """Read the playlist on another thread, then continue on this one."""
        self.notice("Oynatma listesi okunuyor…", 30)

        def work():
            try:
                entries = ve.expand_playlist(url, s.cookies)
            except Exception as e:  # noqa: BLE001
                self.notice(f"Listeyi okuyamadım: {ve.pretty_error(e)}", 10)
                entries = [(url, "", 0)]
            self._ui_calls.put(lambda: self._playlist_ready(entries, s))

        threading.Thread(target=work, daemon=True).start()

    def _playlist_ready(self, entries, s):
        if len(entries) > 1 and self.cfg.get("playlist_ask"):
            PlaylistDialog(self, entries, s)
        else:
            self.add_playlist_selection(entries, s)

    def add_playlist_selection(self, entries, s):
        added, skipped = self.manager.add_entries(entries, s, True, bool(self.cfg.get("block_duplicates")))
        text = f"{added} video listeye eklendi" if len(entries) > 1 else "Bağlantı eklendi"
        if skipped:
            text += f" ({skipped} tanesi zaten listedeydi)"
        self.notice(text)

    # ------------------------------------------------------------------------- info
    def _show_info(self):
        urls = extract_urls(self.url_entry.get())
        if not urls:
            self.notice("Önce bir link yapıştır, sonra bakarım.")
            return
        InfoDialog(self, urls[0])

    def download_quality(self, url, quality, kind, clip=None):
        """A button of the info window: download this link with that quality (None: keep the
        quality of the option bar); with `clip` ([start, end] s) only that part of it."""
        s = dataclasses.replace(self._settings(), kind=kind, playlist=False)
        if quality:
            s = dataclasses.replace(s, quality=quality)
        if not clip and self.cfg.get("block_duplicates") and self.manager.find_duplicate(url):
            self.notice("Bu link zaten listede, ikinciyi eklemedim")      # a part of it is something else
        else:
            self.manager.add_url(url, s, extra={"clip": clip} if clip else None)
            self.notice("Eklendi: " + (f"{quality}" if quality else "MP3") + (f" ✂ {clip_text(clip)}" if clip else ""))

    # ----------------------------------------------------------------- text files
    def _add_from_paths(self, paths):
        """Links from text files (the 📄 button); a .torrent file is downloaded as a torrent (🧲)."""
        urls = []
        for p in paths:
            if p.lower().endswith(".torrent"):
                urls.append(pathlib.Path(os.path.abspath(p)).as_uri())
            else:
                urls += urls_from_file(p)
        if not urls:
            self.notice("O dosyada tek bir link bile bulamadım")
            return 0
        return self.add_urls(urls)

    # ------------------------------------------------------ list: filter / sort / select
    def _on_filter(self, value):
        self.cfg.set("filter", value)
        self._sync_rows()

    def _on_sort(self, value):
        self.cfg.set("sort", value)
        self._sync_rows()

    def _visible_items(self):
        text = self.search_entry.get().strip().lower()
        if self.nostalgia:                       # the category tree and the table's headings choose
            category = self.category
            keep = lambda it: classic_ui.in_category(category, it)    # noqa: E731
            sort = self.cfg.get("sort")
        else:
            states = FILTER_STATES.get(self.filter_menu.get())
            keep = lambda it: states is None or it.state in states    # noqa: E731
            sort = self.sort_menu.get()
        items = [it for it in list(self.manager.items)
                 if keep(it) and (not text or text in it.display_name.lower() or text in it.url.lower())]
        items.sort(key=SORT_KEYS.get(sort, SORT_KEYS["Yeni üstte"]))
        return items

    def set_selected(self, item_id, flag):
        if flag:
            self.selected.add(item_id)
        else:
            self.selected.discard(item_id)
        self._update_selection_ui()

    def _on_select_all(self):
        ids = {it.id for it in self._visible_items()}
        if self.select_all_var.get():
            self.selected |= ids
        else:
            self.selected -= ids
        self._sync_rows()

    def _selected_items(self):
        return [it for it in list(self.manager.items) if it.id in self.selected]

    def _sel_resume(self):
        for it in self._selected_items():
            self.manager.resume(it)

    def _sel_pause(self):
        for it in self._selected_items():
            self.manager.pause(it)

    def _sel_remove(self):
        sel = self._selected_items()
        if len(sel) > 1 and not messagebox.askyesno(
                "DISO", f"{len(sel)} indirme listeden silinsin mi?\n"
                                  "(Yarım kalan geçici dosyalar da silinir.)"):
            return
        for it in sel:
            self.manager.remove(it)
        self.selected.clear()
        self._sync_rows()

    def _update_selection_ui(self):
        n = len(self.selected)
        set_if_changed(self.sel_label, text=f"{n} seçili" if n else "")
        state = "normal" if n else "disabled"
        for b in self.sel_buttons:
            set_if_changed(b, state=state)
        visible = set(self._order or [])
        all_selected = bool(visible) and visible <= self.selected
        if bool(self.select_all_var.get()) != all_selected:
            self.select_all_var.set(all_selected)

    def _sync_rows(self):
        if self.nostalgia:
            self._n_sync()
            return
        items = list(self.manager.items)
        ids = {i.id for i in items}
        for iid in [k for k in self.rows if k not in ids]:
            self.rows.pop(iid).destroy()
        self.selected &= ids
        visible = self._visible_items()
        for it in visible:
            if it.id not in self.rows:
                self.rows[it.id] = DownloadRow(self.list_frame, it, self)
        order = [it.id for it in visible]
        if order != self._order:  # new item, filter, sort or state change: pack again in order
            for row in self.rows.values():
                row.pack_forget()
            self.empty_label.pack_forget()
            for iid in order:
                self.rows[iid].pack(fill="x", padx=4, pady=4)
            if not order:
                self.empty_label.configure(
                    text="Burası şimdilik bomboş. Bir link yapıştır, gerisini bana bırak." if not items
                    else "Aramana uyan bir şey çıkmadı.")
                self.empty_label.pack(pady=40)
            self._order = order
        for iid in order:
            self.rows[iid].refresh()
        self._update_selection_ui()

    # ------------------------------------------------------------------ settings window
    def open_about(self):
        try:
            if self.about_dialog is not None and self.about_dialog.winfo_exists():
                self._bring_to_front(self.about_dialog)
                return
        except TclError:
            pass
        self.about_dialog = AboutDialog(self)

    def _announce_version(self):
        """Said once per version: welcome the first time, a short note after an update."""
        label = brand.VERSION_LABEL
        last = self.cfg.get("last_version")
        if last == label:
            return
        self.cfg.set("last_version", label)
        self.notice(f"{brand.NAME}'ya hoş geldin! Linki yapıştır, gerisini bana bırak." if not last
                    else f"{brand.NAME} {label} sürümüne güncellendi 🎉", 9)

    def _open_settings(self, tab=None):
        """The settings window; `tab`: the group to show ("Zamanlayıcı" ...)."""
        try:
            if self.settings_panel is not None and self.settings_panel.winfo_exists():
                self._bring_to_front(self.settings_panel)
                if tab:
                    self.settings_panel.show_tab(tab)
                return
        except TclError:
            pass
        self.settings_panel = SettingsPanel(self)
        if tab:
            self.settings_panel.show_tab(tab)

    def _on_language_switch(self, short):
        name = LANGUAGE_SHORT.get(short)
        if not name or name == self.cfg.get("language"):
            return
        self.apply_setting("language", name)

    def _show_language(self):
        """The TR | EN switch and the settings' language menu show the chosen language."""
        name = self.cfg.get("language")
        try:
            if self.language_switch.get() != LANGUAGE_NAMES.get(name):
                self.language_switch.set(LANGUAGE_NAMES.get(name))
            panel = self.settings_panel
            if panel is not None and panel.winfo_exists() and panel.language_menu.get() != name:
                panel.language_menu.set(name)
        except (TclError, AttributeError):
            pass
        if self.nostalgia:
            self._n_show_choices()

    def apply_setting(self, key, value):
        """Settings window changed something: save it and apply it at once."""
        if key == "start_with_windows":
            if not startup.set_enabled(bool(value)):
                self.notice("Windows açılışına ekleyemedim", 8)
                return
        self.cfg.set(key, value)
        if key == "max_parallel":
            self.manager.set_max_parallel(int(value))
        elif key == "auto_retry":
            self.manager.set_max_retries(int(value))
        elif key == "speed_limit":
            LIMITER.set_rate(SPEED_LIMITS[value] * 1024)
            self.notice("Hız sınırı kalktı, tam gaz" if SPEED_LIMITS[value] == 0 else f"Hız sınırı: {value}")
        elif key == "theme" and self.nostalgia:
            self.after(150, self._offer_restart)          # its grey is chosen when it starts
        elif key == "theme":
            # Not inside the dropdown's own callback: on Windows that still runs inside the native
            # menu loop, and re-coloring every widget there can leave the buttons without clicks.
            self.after(80, self._apply_theme, value)
        elif key == "look":
            self.after(150, self._offer_restart)
        elif key == "language":
            self._show_language()
            self.after(150, lambda: self._offer_restart(
                "Dil programı yeniden açınca değişir.\n\nŞimdi yeniden açılsın mı?",
                "Tamam, dil bir sonraki açılışta değişecek"))
        elif key == "tray_on_close" and value:
            self._ensure_tray()

    @staticmethod
    def _bring_to_front(win):
        """Bring a window to the front, also when it is hidden or minimized."""
        if win.state() in ("withdrawn", "iconic"):
            win.deiconify()
        win.lift()
        win.focus_force()

    # ------------------------------------------------------------------ history, shortcuts, backup
    def _single(self, attr, make):
        win = getattr(self, attr)
        try:
            if win is not None and win.winfo_exists():
                self._bring_to_front(win)
                return win
        except TclError:
            pass
        win = make()
        setattr(self, attr, win)
        return win

    def open_history(self):
        win = self._single("history_window", lambda: HistoryWindow(self, self.history))
        win.refresh()
        return win

    def open_shortcuts(self):
        return self._single("shortcuts_window", lambda: ShortcutsWindow(self))

    # ---------------------------------------------------------------------- 📺 followed channels
    def open_channels(self):
        return self._single("channels_window", lambda: ChannelsWindow(
            self, self.channel_store, self.channel_watcher, self.download_channel_videos))

    def download_channel_videos(self, videos, kind) -> int:
        """The videos picked in the channel window into the download list (MP4 / MP3, the rest as chosen above)."""
        s = dataclasses.replace(self._settings(), kind=kind, playlist=False)
        skip = bool(self.cfg.get("block_duplicates"))
        added = sum(1 for v in videos if self.manager.add_url(v["url"], s, skip_duplicates=skip))
        if added:
            self.notice(f"📺 {added} video indirme listesine eklendi")
        return added

    def _drain_channels(self):
        """New videos of followed channels: a notification and a count on the button. Nothing is downloaded."""
        news = self.channel_watcher.drain()
        if news:
            new = [n for n in news if n[0] == "new"]
            if new:
                title, body = channels.announcement(new)
                notify.toast(title, body)
                self.notice(f"{title}: {body}", 12)
            win = self.channels_window
            if win is not None and win.alive():
                win.take(news)
        count = len(self.channel_store.new)
        if self.nostalgia:
            set_if_changed(self.channels_btn, text=f"Kanallar ({count})" if count else "Kanallar")
        else:
            set_if_changed(self.channels_btn, text=f"📺 {count}" if count else "📺")

    def _dialog_parent(self):
        panel = self.settings_panel
        return panel if panel is not None and panel.winfo_exists() else self

    def make_backup(self, target=None):
        """'💾 Yedek al': one .disoyedek file with the settings, lists and history."""
        self._store().save()                     # the settings are written as they change; these are saved now
        self.manager.save()
        target = target or filedialog.asksaveasfilename(
            parent=self._dialog_parent(), title="Yedeği nereye kaydedeyim?", initialfile=backup.default_name(),
            defaultextension=backup.EXTENSION, filetypes=[("DISO yedeği", "*" + backup.EXTENSION)])
        if not target:
            return None
        try:
            saved = backup.make_backup(target)
        except (OSError, backup.BackupError) as e:
            messagebox.showerror("DISO", f"Yedeği alamadım:\n{e}", parent=self._dialog_parent())
            return None
        self.notice(f"💾 Yedek hazır: {os.path.basename(target)} ({len(saved)} dosya)", 10)
        return target

    def restore_backup(self, path=None, ask=True):
        """'📂 Yedeği yükle': checked now, put in place at the next start (DISO restarts if the user wants)."""
        path = path or filedialog.askopenfilename(
            parent=self._dialog_parent(), title="Hangi yedeği yükleyeyim?",
            filetypes=[("DISO yedeği", "*" + backup.EXTENSION), ("Hepsi", "*.*")])
        if not path:
            return False
        try:
            content = backup.prepare_restore(path)
        except backup.BackupError as e:
            messagebox.showerror("DISO", str(e), parent=self._dialog_parent())
            return False
        when = time.strftime("%d.%m.%Y %H:%M", time.localtime(content["made"])) if content.get("made") else "?"
        text = (f"Yedek hazır ({when}, DISO {content['version'] or '?'}).\n\nŞu anki ayarların, çalma listelerin "
                "ve geçmişin bu yedektekilerle değişecek. Bunun için DISO yeniden açılmalı.\n\nŞimdi yeniden açılsın mı?")
        if not ask or messagebox.askyesno("DISO", text, parent=self._dialog_parent()):
            self.restart_requested = True
            self._on_close()
        else:
            self.notice("Tamam, yedek DISO'yu bir dahaki açışında yüklenecek", 10)
        return True

    def _offer_restart(self, text=None, later="Tamam, yeni görünüm bir sonraki açılışta gelecek"):
        """The look and the language are chosen when the program starts, so a change needs a new start."""
        if self._closing:
            return
        parent = self.settings_panel if self.settings_panel is not None and self.settings_panel.winfo_exists() else self
        text = text or ("Yeni görünüm programı yeniden açınca uygulanır.\n\nŞimdi yeniden açılsın mı?\n"
                        "(İndirmeler duraklatılır ve açılışta kaldığı yerden devam eder; çalan müzik durur.)")
        if messagebox.askyesno("DISO", text, parent=parent):
            self._remember_view()
            self.restart_requested = True
            self._on_close()
        else:
            self.notice(later, 8)

    def _remember_view(self):
        """Before "restart now": the size and place of the window, the mode, an open settings window and
        whether a song plays. The new start puts them back (_restore_view): only the look changes."""
        view = {"mode": self.mode}
        try:
            view["geometry"] = self._geometry_of(self)
            view["zoomed"] = self.state() == "zoomed"
            panel = self.settings_panel
            if panel is not None and panel.winfo_exists():
                view["settings"] = panel.current_tab() or "Sistem"     # where the look and the language are
            music = self.music
            if music is not None:
                view["music_geometry"] = self._geometry_of(music)
                view["music_zoomed"] = music.state() == "zoomed"
                view["playing"] = music.controller.state == "playing"
        except (TclError, AttributeError):
            pass
        self.cfg.set("restart_view", view)

    @staticmethod
    def _geometry_of(win):
        """'WxH+X+Y' of a window, also of one that is hidden now (customtkinter keeps the size it was given;
        Tk tells a never shown window's size wrong)."""
        place = re.search(r"([+-]-?\d+[+-]-?\d+)$", win.wm_geometry())
        return f"{win._current_width}x{win._current_height}" + (place.group(1) if place else "")

    def _restore_view(self):
        view, self._view = self._view, {}
        try:
            if view.get("mode") == MODE_MUSIC:
                self._switch_mode(MODE_MUSIC)
                if self.music is None:
                    self.deiconify()
                else:
                    if view.get("music_geometry"):
                        self.music.geometry(view["music_geometry"])
                    if view.get("music_zoomed"):
                        self.music.state("zoomed")
            elif view.get("zoomed"):
                self.state("zoomed")
            if view.get("playing") and self._ensure_music():
                self.music.go_on()
            if "settings" in view:
                self._open_settings(view["settings"] or None)
        except TclError:
            pass

    def _apply_theme(self, value):
        if self._closing:
            return
        try:
            # customtkinter hides a window for a moment to recolor its title bar, and a window that
            # is open then (the settings panel) can stay hidden: remember them and show them again.
            open_windows = [w for w in self.winfo_children()
                            if isinstance(w, ctk.CTkToplevel) and w.state() == "normal"]
            ctk.set_appearance_mode(THEMES.get(value, "dark"))
            if self.music is not None:
                self.music.recolor()
            self.update_idletasks()
            self.after(400, self._restore_windows, open_windows)
        except TclError:
            pass

    def _restore_windows(self, windows):
        for w in windows:
            try:
                if w.winfo_exists() and w.state() != "normal":
                    w.deiconify()
            except TclError:
                pass

    def apply_proxy(self, text) -> bool:
        """Validate and apply the proxy address; '' = the system's own settings."""
        try:
            set_proxy(text)
        except ValueError as e:
            self.notice(str(e), 10)
            return False
        self.cfg.set("proxy", (text or "").strip())
        self.notice("Proxy: " + (text.strip() if (text or "").strip() else "sistem ayarı kullanılıyor"))
        return True

    def apply_schedule(self, key, text) -> bool:
        """key is schedule_start or schedule_stop. The stop time may be empty."""
        text = (text or "").strip()
        if key == "schedule_stop" and not text:
            self.cfg.set(key, "")
            return True
        if schedule.parse_hhmm(text) is None:
            self.notice("Saati 24 saatlik yaz, mesela 02:00", 8)
            return False
        self.cfg.set(key, schedule.format_hhmm(schedule.parse_hhmm(text)))
        return True

    def apply_bridge_port(self, text) -> bool:
        try:
            port = int(str(text).strip())
        except ValueError:
            port = 0
        if not 1024 <= port <= 65535:
            self.notice("Port 1024 ile 65535 arasında bir sayı olsun", 8)
            return False
        if port != self.cfg.get("bridge_port"):
            self.cfg.set("bridge_port", port)
            self.restart_bridge()
        return True

    def set_after_all(self, label):
        self.after_all = label
        action = AFTER_ALL.get(label, "none")
        if action != "none":
            self.notice(f"Tüm indirmeler bitince: {label.lower()}", 8)

    def test_notification(self):
        self._notify("done", "Bildirim geldiyse çalışıyor demektir ✔")

    def open_log(self):
        path = setup_logging()
        if not os.path.exists(path):
            open(path, "a").close()
        open_file(path)

    def open_extension_folder(self):
        try:
            folder = extension_setup.extension_folder()
        except OSError:
            folder = ""
        if os.path.isdir(folder):
            open_in_file_manager(folder)
        else:
            self.notice("Eklenti klasörünü bulamadım", 8)

    def should_offer_extension(self, now=None) -> bool:
        """Offer the browser extension? Not once it has talked to us, not after "don't ask again", not before
        "remind me later" is over, not with the bridge off, and not on a PC without a supported browser."""
        cfg = self.cfg
        if not cfg.get("extension_ask") or cfg.get("extension_seen") or not cfg.get("bridge_on"):
            return False
        if (time.time() if now is None else now) < cfg.get("extension_ask_after"):
            return False
        return bool(extension_setup.find_browsers())

    def _maybe_offer_extension(self):
        try:
            if (self._closing or getattr(self, "_started_hidden", False) or self.state() == "withdrawn"
                    or not self.should_offer_extension()):
                return
            self.extension_offer = extension_setup.ExtensionOffer(
                self, on_add=self.open_extension_guide,
                on_later=lambda: self.cfg.set("extension_ask_after", int(time.time()) + EXTENSION_LATER),
                on_never=lambda: self.cfg.set("extension_ask", False))
        except Exception:  # noqa: BLE001 - only a suggestion: never in the way
            log.exception("extension offer")

    def open_extension_guide(self):
        """'Add DISO to your browser' (one window at a time)."""
        win = getattr(self, "extension_guide", None)
        try:
            if win is not None and win.winfo_exists():
                win.lift()
                return
        except TclError:
            pass
        try:
            self.extension_guide = extension_setup.ExtensionGuide(self._dialog_parent())
        except OSError as e:
            log.exception("extension guide")
            self.notice(f"Eklenti klasörünü hazırlayamadım: {e}", 10)

    # ------------------------------------------------------------------ notifications
    def _notify(self, kind, text):
        if self.cfg.get("notify_sound"):
            notify.play_sound(kind)
        if self.cfg.get("notify_toast"):
            notify.toast("İndirme tamamlandı" if kind == "done" else "İndirme başarısız", text)

    def _drain_events(self):
        dones, errors = [], []
        while True:
            try:
                kind, item = self.manager.events.get_nowait()
            except queue.Empty:
                break
            (dones if kind == "done" else errors).append(item)
        self._phase_done += len(dones)
        if dones:
            try:
                self.history.record(dones)
            except Exception:  # noqa: BLE001 - the history must never stop the downloads
                log.exception("could not write the download history")
            self._music_collect(dones)
            self._notify("done", dones[0].display_name if len(dones) == 1
                         else f"{len(dones)} indirme tamamlandı")
        if errors:
            self._notify("error", errors[0].display_name if len(errors) == 1
                         else f"{len(errors)} indirme başarısız")

    def _check_after_all(self):
        """When the last download of a run is finished, do what the user asked (once)."""
        items = list(self.manager.items)
        if any(i.state in ACTIVE_STATES for i in items):
            self._had_work = True
            return
        if not self._had_work:
            return
        self._had_work = False
        done, self._phase_done = self._phase_done, 0
        action = AFTER_ALL.get(self.after_all, "none")
        # a paused download means "not finished": never shut down because of a pause-all
        if action == "none" or not done or any(i.state == PAUSED for i in items):
            return
        self.after_all = NO_END_ACTION
        text, seconds = {"close": ("DISO kapanacak", 10),
                         "sleep": ("Bilgisayar uykuya geçecek", 30),
                         "shutdown": ("Bilgisayar kapanacak", 30)}[action]
        notify.play_sound("done")
        CountdownDialog(self, f"Tüm indirmeler bitti 🎉\n{text}", seconds, lambda: self._do_power(action))

    def _do_power(self, action):
        if action == "close":
            self._on_close()
        else:
            notify.power_action(action)

    # ----------------------------------------------------------------------- scheduler
    def _check_schedule(self):
        """Open or close the queue's gate according to the scheduler settings."""
        cfg = self.cfg
        start = schedule.parse_hhmm(cfg.get("schedule_start"))
        stop_text = (cfg.get("schedule_stop") or "").strip()
        stop = schedule.parse_hhmm(stop_text) if stop_text else None
        now = self._now()
        want_open = True
        if cfg.get("schedule_on") and start is not None:
            want_open = schedule.gate_should_be_open(now.hour * 60 + now.minute, start, stop)
        if want_open != self.manager.gate_open:
            self.manager.set_gate(want_open)
            if want_open:
                resumed = [it for it in self._sched_paused if it.state == PAUSED]
                self._sched_paused = []
                for it in resumed:
                    self.manager.resume(it)
                self.notice("Zamanlayıcı: indirmeler başladı")
            elif stop is not None:
                # the stop time came: running downloads pause and continue at the next start
                for it in list(self.manager.items):
                    if it.state in (RESOLVING, DOWNLOADING, WAITING):
                        self._sched_paused.append(it)
                        self.manager.pause(it)
                self.notice("Zamanlayıcı: bitiş saati geldi, indirmeler duraklatıldı")
            else:
                self.notice("Zamanlayıcı: yeni indirmeler başlama saatini bekleyecek")
        self.queue_note = "" if want_open else f"⏰ Zamanlayıcı: {schedule.format_hhmm(start)}'de başlayacak"

    # ------------------------------------------------------------------ tray / window
    def _ensure_tray(self):
        if self.tray is None and tray.AVAILABLE:
            try:
                self.tray = tray.TrayIcon("DISO",
                                          lambda name: self._ui_calls.put(lambda: self._tray_event(name)))
                self.tray.start()
            except Exception:
                log.exception("tray icon could not start")
                self.tray = None

    def _tray_event(self, name):
        if name == "show":
            self._show_window()
        elif name == "pause_all":
            self.manager.pause_all()
        elif name == "resume_all":
            self.manager.resume_all()
        elif name == "quit":
            self._on_close()

    def _hide_to_tray(self):
        self._ensure_tray()
        if self.tray is not None:
            self.withdraw()
            if self.music is not None:
                self.music.withdraw()
        elif self.mode == MODE_MUSIC and self.music is not None:
            self.music.iconify()
        else:
            self.iconify()

    def _show_window(self):
        """Bring up the window of the mode we are in (tray icon, second launch)."""
        win = self.music if self.mode == MODE_MUSIC and self.music is not None else self
        try:
            win.deiconify()
            win.lift()
            win.attributes("-topmost", True)
            win.after(300, lambda: win.attributes("-topmost", False))
            win.focus_force()
        except TclError:
            pass

    # ------------------------------------------------------------------ music player mode
    def _store(self):
        if self.playlist_store is None:
            self.playlist_store = playlists.PlaylistStore()
        return self.playlist_store

    def playlist_names(self):
        return self._store().user_names()

    def new_music_list(self, name) -> str:
        name = self._store().create(name)
        if self.music is not None:
            self.music.reload()
        return name

    def add_to_music_list(self, item, name) -> bool:
        """The row menu: put a finished song into a playlist (a chosen one, so any audio file goes)."""
        path = item.final_path
        if not (path and player.is_audio(path) and os.path.isfile(path)):
            self.notice("Dosyayı bulamadım, müzik listesine ekleyemedim", 8)
            return False
        store = self._store()
        name = store.ensure(name)
        if store.has_path(name, path):
            self.notice(f"Bu parça “{name}” listesinde zaten var")
            return False
        store.add(name, [path])
        if self.music is not None:
            self.music.reload()
        self.notice(f"“{name}” çalma listesine eklendi")
        return True

    def _music_collect(self, items):
        """Finished music downloads go into a playlist by themselves: the playlist they were taken
        from (named like it), else 'İndirilenler'. Switched off in the settings. Songs found in the
        music player are not put anywhere by themselves: the user is asked which list they go to."""
        found = [it for it in items if getattr(it, "origin", "") == "music"]
        if found:
            self.ask_song_list(found)
            self._find_song_lyrics(found)
        listed = [it for it in items if getattr(it, "origin", "") == "music-list"]
        if listed:
            self._songs_into_their_list(listed)
        items = [it for it in items if it not in found and it not in listed]
        if not self.cfg.get("auto_music"):
            return
        added = {}
        store = None
        for it in sorted(items, key=lambda i: i.added):
            path = it.final_path
            if not (path and player.is_music(path) and os.path.isfile(path)):
                continue
            store = store or self._store()
            name = store.ensure(it.group)
            if store.add_download(name, path, it.added):
                added[name] = added.get(name, 0) + 1
        if not added:
            return
        if self.music is not None:
            self.music.reload()
        total, names = sum(added.values()), list(added)
        self.notice(f"{total} müzik “{names[0]}” çalma listesine eklendi" if len(names) == 1
                    else f"{total} müzik çalma listelerine eklendi")

    # ------------------------------------------------------------------ songs found in the music player
    def song_items(self):
        """The downloads that were started from '🔍 Şarkı bul'."""
        return [it for it in list(self.manager.items)
                if getattr(it, "origin", "").startswith("music") and not it.removed]

    def song_settings(self) -> Settings:
        """A found song: always MP3 (the chosen bitrate) with its cover, into %LOCALAPPDATA%/DISO/Müzik."""
        c = self.cfg
        return Settings(kind="audio", bitrate=c.get("bitrate"), connections=int(c.get("connections")),
                        folder=music_search.music_dir(), playlist=False, cookies=c.get("cookies"),
                        subs="Yok", cover=True, sort_folders=False)

    def download_song(self, result) -> str:
        """'⬇ İndir' in the music window. Returns "added", "running" (already downloading),
        "restarted" (a stopped / failed one goes on) or "done" (it is here already: ask for a list)."""
        old = self.manager.find_duplicate(result["url"])
        if old is not None and old.origin == "music":
            if old.state in ACTIVE_STATES:
                return "running"
            if old.state == DONE and old.final_path and os.path.isfile(old.final_path):
                self.ask_song_list([old])
                return "done"
            if old.state != DONE:
                self.manager.start(old)
                return "restarted"
        self.manager.add_song(result["url"], result.get("title", ""), self.song_settings())
        return "added"

    def _songs_into_their_list(self, items):
        """Songs of a playlist downloaded with '⬇ Hepsini indir' go into that list by themselves, in order."""
        store = self._store()
        added = {}
        for it in sorted(items, key=lambda i: i.added):
            if it.final_path and player.is_audio(it.final_path) and os.path.isfile(it.final_path):
                name = store.ensure(it.group)
                if store.add_download(name, it.final_path, it.added):
                    added[name] = added.get(name, 0) + 1
        self._find_song_lyrics(items)
        if added and self.music is not None:
            self.music.reload()
            name, n = next(iter(added.items()))
            self.music.note(f"✓ {n} şarkı “{name}” listesine girdi")

    def video_id_for(self, path) -> str:
        """The YouTube video a song file was downloaded from (download list, then history), or ""."""
        target = os.path.normcase(os.path.abspath(path))
        sources = [(it.final_path, it.url) for it in list(self.manager.items)]
        sources += [(e["path"], e["url"]) for e in self.history.entries]
        for file, url in sources:
            if file and os.path.normcase(os.path.abspath(file)) == target:
                video = lyrics.video_id_of(url)
                if video:
                    return video
        return ""

    def _find_song_lyrics(self, items):
        """A found song brings its lyrics along: looked up on the internet, kept as '<song>.lrc'."""
        for it in items:
            path = it.final_path
            if path and os.path.isfile(path) and not lyrics.has_lyrics(path):
                artist, title = player.artist_and_title({"title": it.title or os.path.splitext(os.path.basename(path))[0]})
                self.lyrics_fetcher.find(path, artist, title, video_id=lyrics.video_id_of(it.url))

    def download_playlist(self, results, title):
        """'⬇ Hepsini indir' in the music window: every song of a (YouTube Music) playlist or album, as MP3,
        into a playlist with its name, in its order. Songs already there or downloading are skipped.
        Returns (how many started, the list's name)."""
        store = self._store()
        name = store.ensure(title)
        if self.music is not None:
            self.music.reload()
        settings = self.song_settings()
        base = time.time()
        added = 0
        for i, r in enumerate(results):
            old = self.manager.find_duplicate(r["url"])
            if old is not None and getattr(old, "origin", "").startswith("music"):
                if old.state == DONE and old.final_path and os.path.isfile(old.final_path):
                    store.add_download(name, old.final_path, base + i / 1000)
                elif old.state not in ACTIVE_STATES:
                    old.origin, old.group, old.added = "music-list", name, base + i / 1000
                    self.manager.start(old)
                continue
            it = self.manager.add_song(r["url"], r.get("title", ""), settings, origin="music-list")
            it.group, it.added = name, base + i / 1000            # the list keeps the playlist's order
            added += 1
        self.manager.save()
        if self.music is not None:
            self.music.reload()
        return added, name

    def ask_song_list(self, items):
        """'🎉 İndi! Hangi listeye ekleyeyim?' (one question for songs that finish together)."""
        songs = [(it.display_name, it.final_path) for it in items
                 if it.final_path and player.is_audio(it.final_path) and os.path.isfile(it.final_path)]
        if not songs:
            return
        if self.song_dialog is not None:
            try:
                if self.song_dialog.winfo_exists():
                    self.song_dialog.add(songs)
                    return
            except TclError:
                pass
        store = self._store()
        default = store.state.get("ask_list") or (self.music.viewed if self.music is not None else "")
        parent = self.music if (self.mode == MODE_MUSIC and self.music is not None) else self
        self.song_dialog = SongListDialog(parent, store.user_names(), default, songs, self.songs_to_list)

    def songs_to_list(self, paths, name):
        """The answer: name = a list, ("new", wanted name), or None (not now)."""
        self.song_dialog = None
        if name is None:
            if self.music is not None:
                self.music.note("Tamam, eklemedim. Şarkılar “📂 İnenler” klasöründe duruyor.")
            return 0
        store = self._store()
        name = store.create(name[1]) if isinstance(name, tuple) else store.ensure(name)
        added = sum(1 for p in paths if not store.has_path(name, p) and store.add(name, [p]))
        store.set_state(ask_list=name)
        if self.music is not None:
            self.music.show_list(name)
            self.music.note(f"✓ {added} şarkı “{name}” listesine eklendi" if added
                            else f"Bu şarkılar “{name}” listesinde zaten var")
        self.notice(f"{added} şarkı “{name}” çalma listesine eklendi" if added
                    else f"Bu şarkılar “{name}” listesinde zaten var")
        return added

    def _ensure_music(self):
        if self.music is not None:
            return True
        try:
            backend = player.equalizable()
        except (OSError, AttributeError) as e:
            log.error("music player unavailable: %s", e)
            self.notice("Müzik çaları bu bilgisayarda başlatamadım", 8)
            return False
        try:
            spare = player.equalizable(alias="hizli_music_b")     # the second voice of a cross-fade
        except (OSError, AttributeError):
            spare = None
        prepare = playable.Preparer() if player.needs_playable_copies() else None
        self.music = MusicWindow(self, self._store(), player.Controller(backend, spare=spare, prepare=prepare),
                                 on_close=self._on_window_x, on_mode=self._switch_mode)
        self.music.withdraw()
        return True

    def _switch_mode(self, mode):
        """Download window <-> music player window. Downloads and music both keep going."""
        if mode == MODE_MUSIC:
            if not self._ensure_music():
                self.mode_bar.set(MODE_DOWNLOAD)
                return
            self.mode = MODE_MUSIC
            self.withdraw()
            self.music.mode_bar.set(MODE_MUSIC)
            self.music.deiconify()
            self.music.lift()
        else:
            self.mode = MODE_DOWNLOAD
            if self.music is not None:
                self.music.withdraw()
            self.mode_bar.set(MODE_DOWNLOAD)
            self.deiconify()
            self.lift()

    def _on_window_x(self):
        """The window's own close button: go to the tray if the user wants that, else quit."""
        if self.cfg.get("tray_on_close") and MAC and not self._closing:      # no tray there: into the Dock
            (self.music if self.mode == MODE_MUSIC and self.music is not None else self).iconify()
            return
        if self.cfg.get("tray_on_close") and tray.AVAILABLE and not self._closing:
            self._hide_to_tray()
            if self.tray is not None and not self._hidden_hint_shown and self.cfg.get("notify_toast"):
                self._hidden_hint_shown = True
                notify.toast("DISO", "DISO arka planda çalışmaya devam ediyor. Geri çağırmak için simgesine tıkla.")
        else:
            self._on_close()

    # ------------------------------------------------------------------ browser bridge
    def _start_bridge(self):
        self.bridge = bridge_module.Bridge(BridgeApi(self), port=self.cfg.get("bridge_port"))
        if not self.bridge.start():
            self.bridge = None
            self.notice("Tarayıcı eklentisiyle konuşamıyorum: port başka bir programda kullanımda. Ayarlardan değiştirebilirsin.", 10)

    def restart_bridge(self):
        old, self.bridge = self.bridge, None
        if old is not None:
            old.stop()
        self._start_bridge()

    def bridge_add(self, urls, extra, kind):
        """Links from the browser extension. Runs on the bridge's thread: no widgets here."""
        s = self.settings_from_config()
        if kind:
            s = dataclasses.replace(s, kind=kind)
        skip = bool(self.cfg.get("block_duplicates"))
        added = duplicates = 0
        for u in urls:
            if self.manager.add_url(normalize_url(u), s, skip_duplicates=skip, extra=extra):
                added += 1
            else:
                duplicates += 1
        if added:
            self.notice(f"Tarayıcıdan {added} bağlantı eklendi")
        return {"added": added, "duplicates": duplicates}

    def bridge_status(self):
        items = list(self.manager.items)
        return {"active": sum(i.state in (RESOLVING, DOWNLOADING, PROCESSING) for i in items),
                "queued": sum(i.state in (QUEUED, WAITING) for i in items),
                "speed": int(sum(i.speed for i in items if i.state == DOWNLOADING)),
                "total": len(items)}

    # ---------------------------------------------------------------------- updates
    def _open_updates(self):
        try:
            if self.update_panel is not None and self.update_panel.winfo_exists():
                self.update_panel.lift()
                return
        except TclError:  # the old panel was destroyed
            pass
        self.update_panel = UpdatePanel(self)

    def check_updates(self, install):
        threading.Thread(target=self.updates.run, kwargs={"install": install}, daemon=True).start()
        threading.Thread(target=self.app_update.check, daemon=True).start()     # DISO itself: only looks

    def update_card(self, key):
        """Button on a card: install FFmpeg when it is missing, otherwise update."""
        if key == "diso":
            self.update_app()
        elif key == "ffmpeg" and self.updates.components["ffmpeg"].status == "missing":
            threading.Thread(target=self.updates.install_ffmpeg, daemon=True).start()
        else:
            self.check_updates(install=True)

    def update_app(self):
        """"Güncelle" on the DISO card: download the new setup, let Windows ask, then make room for it."""
        def work():
            result = self.app_update.update()
            self._ui_calls.put(lambda: self._app_update_done(result))
        threading.Thread(target=work, daemon=True, name="app-update-install").start()

    def _app_update_done(self, result):
        rel = self.app_update.release or {}
        if result == "page":
            webbrowser.open(rel.get("page") or brand.HOME_URL + "/releases/latest")
        elif result == "started":
            self.notice("DISO güncelleniyor… birazdan yeni sürümle açılacak", 30)
            self.after(800, self._on_close)          # the setup needs DISO's files: close (it starts DISO again)

    def _announce_app_update(self):
        """A new DISO was found: told once per version (a notification and the status line), never installed."""
        found = self.app_update.announce
        if not found or self.cfg.get("update_announced") == found[0]:
            return
        self.cfg.set("update_announced", found[0])
        title = f"🎉 DISO {found[0]} çıktı"
        notify.toast(title, "Kurmak için ⟳ Güncellemeler → DISO → Güncelle")
        self.notice(f"{title}: ⟳ Güncellemeler → Güncelle", 20)

    def _update_update_widgets(self):
        comps = list(self.updates.components.values())
        working = next((c for c in comps if c.status == "working"), None)
        if working is not None:
            self.update_label.configure(text=f"{working.title}: {working.message}")
            self.update_progress.set(working.progress)
            self.update_progress.grid()
            self.update_bar.grid()
        elif self.updates.running:
            self.update_label.configure(text="Parçalara bakıyorum…")
            self.update_progress.grid_remove()
            self.update_bar.grid()
        else:
            self.update_bar.grid_remove()

        if self.updates.running:
            text = "⟳ Kontrol ediliyor…"
        else:
            n = sum(c.status == "available" for c in comps + [self.app_update.comp])
            text = f"⟳ Güncellemeler ({n})" if n else "⟳ Güncellemeler"
        if self.nostalgia:                        # under a picture: no symbol in front
            text = text[2:]
        if text != self._btn_text:
            self._btn_text = text
            self.updates_btn.configure(text=text)

    # ------------------------------------------------------------------ close / loop
    def _on_close(self):
        """Really quit: pause what runs, remember the list, close."""
        if self._closing:
            return
        self._closing = True
        self._hide_all()         # the windows go at once; what is left to save happens out of sight
        self._save_folder()
        self.manager.shutdown()  # asks running downloads to pause; returns at once
        self.channel_watcher.stop()
        self.app_update.stop()
        if self.music is not None:
            self.music.shutdown()
        self._finish_close(time.time() + CLOSE_WAIT)

    def _hide_all(self):
        for win in [self, *self.winfo_children()]:
            try:
                if isinstance(win, tk.Toplevel) or win is self:
                    win.withdraw()
            except TclError:
                pass
        try:
            self.update_idletasks()
        except TclError:
            pass

    def _finish_close(self, deadline):
        """Wait, without freezing the window, until downloads have saved their state."""
        if (self.manager.busy() or self.updates.writing) and time.time() < deadline:
            self.status.configure(text="Kapanıyorum… indirmeleri kaydediyorum")
            self.after(100, lambda: self._finish_close(deadline))
            return
        self.manager.save()
        if self.tray is not None:
            self.tray.stop()
        if self.bridge is not None:
            threading.Thread(target=self.bridge.stop, daemon=True).start()
        gc.collect()          # finalizers of Tk objects must run while the window still exists
        self.destroy()
        gc.enable()

    def _drain_notices(self):
        for q in (self.manager.notices, self.updates.notices):
            while True:
                try:
                    text = q.get_nowait()
                except queue.Empty:
                    break
                self.notice(text)

    def _drain_ui_calls(self):
        while True:
            try:
                fn = self._ui_calls.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                log.exception("a call from another thread failed")

    def report_callback_exception(self, exc, val, tb):
        """A button / timer callback crashed: write it to the log, keep the window alive."""
        log.error("callback failed", exc_info=(exc, val, tb))
        self.notice("Hoppala, beklenmedik bir şey oldu. Ayrıntısı günlükte: Ayarlar → Günlüğü aç", 10)

    def _tick(self):
        self._tick_no += 1
        try:
            self._drain_ui_calls()
            self._sync_rows()
            self._watch_clipboard()
            self._drain_notices()
            self._drain_events()
            self._check_after_all()
            self._check_schedule()
            self._drain_channels()
            self._announce_app_update()
            if self._tick_no % 10 == 0:
                self._ffmpeg_ok = bool(find_ffmpeg())
                self._update_tray_tooltip()
            if self._tick_no % 20 == 0:
                gc.collect()  # here, on the window's thread: see __init__
            self._update_update_widgets()
            self._update_status()
        finally:
            if not self._closing:
                self.after(300, self._tick)

    def _update_tray_tooltip(self):
        if self.tray is not None:
            items = self.manager.items
            active = sum(i.state in (DOWNLOADING, PROCESSING, RESOLVING) for i in items)
            speed = sum(i.speed for i in items if i.state == DOWNLOADING)
            self.tray.set_title(f"DISO • {active} aktif • {human_size(speed)}/s")

    def _update_status(self):
        items = self.manager.items
        active = [i for i in items if i.state in (DOWNLOADING, PROCESSING, RESOLVING)]
        queued = sum(1 for i in items if i.state in (QUEUED, WAITING))
        speed = sum(i.speed for i in items if i.state == DOWNLOADING)
        parts = [f"Aktif: {len(active)}/{self.manager.max_parallel}", f"Sırada: {queued}",
                 f"Hız: {human_size(speed)}/s"]
        limit = self.cfg.get("speed_limit")
        if SPEED_LIMITS.get(limit):
            parts.append(f"Sınır: {limit}")
        parts.append("FFmpeg: hazır" if self._ffmpeg_ok else "FFmpeg: yok (lazım olunca kendim indiririm)")
        text = "  •  ".join(parts)
        if self.queue_note:
            text += f"  •  {self.queue_note}"
        if self.after_all != NO_END_ACTION:
            text += f"  •  Bitince: {self.after_all.lower()}"
        if self._notice and time.time() < self._notice_until:
            text = f"{self._notice}    |    {text}"
        self.status.configure(text=text)
