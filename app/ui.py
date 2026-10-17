"""Main window (customtkinter): link bar, options, the live download list, the settings
window and the update panel."""
import gc
import os
import queue
import re
import threading
import time
from tkinter import TclError, filedialog, messagebox

import customtkinter as ctk

from . import notify, updater
from . import video_engine as ve
from .config import (AFTER_ALL, FILTERS, MAX_PARALLEL_CHOICES, SORTS, SPEED_LIMITS, Config)
from .manager import DownloadManager
from .models import (ACTIVE_STATES, CANCELLED, DONE, DOWNLOADING, ERROR, PAUSED, PROCESSING,
                     QUEUED, RESOLVING, Settings)
from .segmented_downloader import LIMITER
from .utils import (default_download_dir, extract_urls, find_ffmpeg, human_eta, human_size, is_url,
                    normalize_url, open_in_file_manager, urls_from_file)

try:  # drag & drop of links / .txt files needs the optional tkinterdnd2 package
    from tkinterdnd2 import DND_FILES, DND_TEXT, TkinterDnD
    _BASES = (ctk.CTk, TkinterDnD.DnDWrapper)
    HAS_DND = True
except Exception:  # not installed: everything else still works
    _BASES = (ctk.CTk,)
    HAS_DND = False

KIND_LABELS = {
    "Otomatik (dosya / video)": "auto",
    "Video (MP4)": "video",
    "Ses (MP3)": "audio",
    "Dosya (rar, zip, exe, iso…)": "file",
}
CONNECTIONS = ["8", "16", "32"]
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
    "manual": ("Kendi kurulumun", "gray"),
}

# list filter -> states it shows (None = everything)
FILTER_STATES = {
    "Hepsi": None,
    "Aktif": (RESOLVING, DOWNLOADING, PROCESSING),
    "Sırada": (QUEUED,),
    "Duraklatılmış": (PAUSED,),
    "Tamamlanan": (DONE,),
    "Hatalı": (ERROR,),
}
_STATE_RANK = {DOWNLOADING: 0, PROCESSING: 0, RESOLVING: 0, QUEUED: 1, PAUSED: 2,
               ERROR: 3, DONE: 4, CANCELLED: 5}
SORT_KEYS = {
    "Yeni üstte": lambda it: -it.added,
    "Eski üstte": lambda it: it.added,
    "Ad (A→Z)": lambda it: it.display_name.lower(),
    "Boyut (büyük üstte)": lambda it: -(it.total or it.done),
    "Duruma göre": lambda it: (_STATE_RANK.get(it.state, 9), -it.added),
}


class DownloadRow(ctk.CTkFrame):
    """One line of the list: checkbox, name, progress bar, status text and buttons."""

    def __init__(self, master, item, app):
        super().__init__(master, corner_radius=10)
        self.item, self.app = item, app
        self._cache = {}
        self.columnconfigure(1, weight=1)

        self.sel_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="", width=24, checkbox_width=20, checkbox_height=20,
                        variable=self.sel_var, command=self._on_select).grid(
            row=0, column=0, rowspan=3, padx=(12, 0))
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

    # ---- buttons
    def _on_select(self):
        self.app.set_selected(self.item.id, bool(self.sel_var.get()))

    def _toggle(self):
        it, m = self.item, self.app.manager
        if it.state in ACTIVE_STATES:
            m.pause(it)
        else:
            m.resume(it)

    def _open(self):
        it = self.item
        open_in_file_manager(it.final_path or it.dest or it.folder)

    def _remove(self):
        self.app.manager.remove(self.item)

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
            text = "Sırada bekliyor…"
        elif st == RESOLVING:
            text = it.message or "Bağlanılıyor…"
        elif st == DOWNLOADING:
            text = f"{pct}{sizes} • {human_size(it.speed)}/s • Kalan {human_eta(it.eta)}"
            if it.conns:
                text += f" • {it.conns} bağlantı"
            if it.message:
                text += f"\n{it.message}"
        elif st == PROCESSING:
            text = it.message or "İşleniyor…"
        elif st == DONE:
            text = "✅ Tamamlandı" + (f" • {human_size(it.total or it.done)}" if (it.total or it.done) else "")
            if it.message:
                text += f"\n{it.message}"
        elif st == PAUSED:
            text = f"⏸ Duraklatıldı • {pct}"
        elif st == ERROR:
            text = f"❌ {it.error}"
        elif st == CANCELLED:
            text = "İptal edildi"
        else:
            text = st
        self._set("info", text, lambda v: self.info.configure(text=v))

        icon = "⏸" if st in (QUEUED, RESOLVING, DOWNLOADING) else "▶"
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
        self.app = app
        self.title("Güncellemeler")
        self.geometry("620x640")
        self.minsize(560, 480)
        self.transient(app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 6))
        ctk.CTkLabel(head, text="⟳ Güncellemeler", font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(head, text="Uygulama her açılışta bu bileşenleri kontrol eder. Yeni sürüm varsa "
                                "otomatik indirilir ve SHA-256 ile doğrulanır.",
                     text_color="gray", wraplength=560, justify="left").pack(anchor="w", pady=(2, 0))

        self.cards_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.cards_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=6)
        self.cards = {}
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
                card.refresh(busy)
            state = "disabled" if busy else "normal"
            self.check_btn.configure(state=state, text="Kontrol ediliyor…" if busy else "🔍 Kontrol et")
            self.all_btn.configure(state=state)
            last = self.app.updates.last_check
            self.last_label.configure(text=f"Son kontrol: {time.strftime('%H:%M:%S', time.localtime(last))}"
                                      if last else "Henüz kontrol edilmedi")
            self.after(300, self._refresh)
        except TclError:  # the window was closed
            return


class SettingsPanel(ctk.CTkToplevel):
    """Global switches: parallel downloads, speed limit, notifications, what to do at the end."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Ayarlar")
        self.geometry("520x550")
        self.resizable(False, False)
        self.transient(app)
        self.columnconfigure(0, weight=1)
        cfg = app.cfg

        ctk.CTkLabel(self, text="⚙ Ayarlar", font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=24, pady=(14, 4))

        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=1, column=0, sticky="ew", padx=20, pady=4)
        card.columnconfigure(0, weight=1)
        self._row = 0

        self.parallel_menu = ctk.CTkOptionMenu(
            card, values=MAX_PARALLEL_CHOICES, width=150,
            command=lambda v: app.apply_setting("max_parallel", int(v)))
        self.parallel_menu.set(str(cfg.get("max_parallel")))
        self._add(card, "Aynı anda indirme", "Fazlası sırada bekler", self.parallel_menu)

        self.speed_menu = ctk.CTkOptionMenu(
            card, values=list(SPEED_LIMITS), width=150,
            command=lambda v: app.apply_setting("speed_limit", v))
        self.speed_menu.set(cfg.get("speed_limit"))
        self._add(card, "Hız sınırı", "Tüm indirmelerin toplamı", self.speed_menu)

        self.sound_switch = ctk.CTkSwitch(card, text="", command=lambda: app.apply_setting(
            "notify_sound", bool(self.sound_switch.get())))
        self.sound_switch.select() if cfg.get("notify_sound") else self.sound_switch.deselect()
        self._add(card, "Bildirim sesi", "İndirme bitince veya hata verince", self.sound_switch)

        self.toast_switch = ctk.CTkSwitch(card, text="", command=lambda: app.apply_setting(
            "notify_toast", bool(self.toast_switch.get())))
        self.toast_switch.select() if cfg.get("notify_toast") else self.toast_switch.deselect()
        self._add(card, "Windows bildirimi", "Sağ alttaki bildirim balonu", self.toast_switch)

        self.dup_switch = ctk.CTkSwitch(card, text="", command=lambda: app.apply_setting(
            "block_duplicates", bool(self.dup_switch.get())))
        self.dup_switch.select() if cfg.get("block_duplicates") else self.dup_switch.deselect()
        self._add(card, "Aynı linki tekrar ekleme", "Listede olan link atlanır", self.dup_switch)

        self.after_menu = ctk.CTkOptionMenu(card, values=list(AFTER_ALL), width=150,
                                            command=app.set_after_all)
        self.after_menu.set(app.after_all)
        self._add(card, "Tüm indirmeler bitince", "Bir kez uygulanır, kaydedilmez", self.after_menu)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=24, pady=(10, 14))
        foot.columnconfigure(0, weight=1)
        ctk.CTkButton(foot, text="🔔 Bildirimi dene", width=150, command=app.test_notification).grid(
            row=0, column=0, sticky="w")
        ctk.CTkButton(foot, text="Kapat", width=110, command=self.destroy).grid(row=0, column=1)

        self.after(500, self._sync)

    def _add(self, card, title, hint, widget):
        ctk.CTkLabel(card, text=title, anchor="w", font=ctk.CTkFont(weight="bold")).grid(
            row=self._row, column=0, sticky="w", padx=16, pady=(8, 0))
        ctk.CTkLabel(card, text=hint, anchor="w", text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=self._row + 1, column=0, sticky="w", padx=16, pady=(0, 6))
        widget.grid(row=self._row, column=1, rowspan=2, padx=16, sticky="e")
        self._row += 2

    def _sync(self):
        """The end action is one-shot: when it fires the menu goes back to 'do nothing'."""
        try:
            if self.after_menu.get() != self.app.after_all:
                self.after_menu.set(self.app.after_all)
            self.after(500, self._sync)
        except TclError:
            return


class CountdownDialog(ctk.CTkToplevel):
    """'The computer will shut down in N seconds' with a cancel button."""

    def __init__(self, app, text, seconds, on_done):
        super().__init__(app)
        self.title("Hızlı İndirici")
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


class App(*_BASES):
    def __init__(self):
        super().__init__()
        # Garbage collection must run on this (the window's) thread only. Collected Tk objects
        # (fonts ...) call into Tcl from their finalizer; on a download thread that call waits for
        # this thread, and if the download thread holds a lock this thread needs, both freeze.
        # So automatic collection is off and _tick() collects every few seconds instead.
        gc.disable()
        if HAS_DND:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
            except Exception:
                pass
        self.title("Hızlı İndirici")
        self.geometry("1000x760")
        self.minsize(900, 620)

        self.cfg = Config()
        self.cfg.sanitize({
            "kind": list(KIND_LABELS), "quality": ve.QUALITIES, "bitrate": ve.BITRATES,
            "connections": CONNECTIONS, "cookies": ve.BROWSERS, "speed_limit": list(SPEED_LIMITS),
            "sort": SORTS, "filter": FILTERS,
        })
        if not 1 <= self.cfg.get("max_parallel") <= 8:
            self.cfg.data["max_parallel"] = 3
        self.manager = DownloadManager(max_parallel=self.cfg.get("max_parallel"))
        LIMITER.set_rate(SPEED_LIMITS[self.cfg.get("speed_limit")] * 1024)
        self.updates = updater.Updater()
        self.updates.ffmpeg_busy = lambda: any(i.state == PROCESSING for i in self.manager.items)
        self.update_panel = None
        self.settings_panel = None
        self.rows = {}
        self.selected = set()
        self.after_all = "Hiçbir şey yapma"   # one-shot, not saved
        self._order = None   # None: the list was never laid out yet
        self._had_work = False
        self._phase_done = 0
        self._last_clip = ""
        self._notice = ""
        self._notice_until = 0
        self._tick_no = 0
        self._ffmpeg_ok = bool(find_ffmpeg())
        self._closing = False
        self._btn_text = ""

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
        self.status.grid(row=7, column=0, sticky="ew", padx=20, pady=(0, 10))

        self._on_kind(self.kind_menu.get())
        self.clip_var.set(bool(self.cfg.get("clip_watch")))
        self._last_clip = self._clipboard_text()  # what is in the clipboard now is not "new"
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if HAS_DND:
            try:
                self.drop_target_register(DND_TEXT, DND_FILES)
                self.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass
        self.after(300, self._tick)
        self.updates.start()  # checks and updates yt-dlp / FFmpeg in the background

    # ------------------------------------------------------------------------ layout
    def _build_top(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        head.columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="⚡ Hızlı İndirici", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, sticky="w")
        ctk.CTkLabel(head, text="Dosya (IDM gibi parçalı) • YouTube/Instagram/TikTok/X… videoları • MP3",
                     text_color="gray").grid(row=1, column=0, sticky="w")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 0))
        row.columnconfigure(0, weight=1)
        hint = "Bağlantıyı yapıştır (birden fazla link boşlukla ayrılabilir)…"
        if HAS_DND:
            hint = "Bağlantıyı yapıştır veya sürükle-bırak (birden fazla link olabilir)…"
        self.url_entry = ctk.CTkEntry(row, height=44, placeholder_text=hint)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.url_entry.bind("<Return>", lambda e: self.add_from_entry())
        ctk.CTkButton(row, text="📋", width=48, height=44, command=self._paste).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(row, text="📄", width=48, height=44, command=self._import_file).grid(
            row=0, column=2, padx=(0, 8))
        ctk.CTkButton(row, text="⬇  İndir", height=44, width=130, font=ctk.CTkFont(size=16, weight="bold"),
                      command=self.add_from_entry).grid(row=0, column=3)

    def _build_options(self):
        opt = ctk.CTkFrame(self)
        opt.grid(row=2, column=0, sticky="ew", padx=16, pady=10)
        for c in range(6):
            opt.columnconfigure(c, weight=1)
        cfg = self.cfg

        def label(text, col):
            ctk.CTkLabel(opt, text=text).grid(row=0, column=col, padx=10, pady=(8, 0), sticky="w")

        label("Ne indirilecek", 0)
        self.kind_menu = ctk.CTkOptionMenu(opt, values=list(KIND_LABELS), command=self._on_kind)
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

        self.playlist_var = ctk.BooleanVar(value=bool(cfg.get("playlist")))
        ctk.CTkCheckBox(opt, text="Oynatma listesi", variable=self.playlist_var,
                        command=lambda: cfg.set("playlist", bool(self.playlist_var.get()))).grid(
            row=1, column=5, padx=10, pady=(0, 6), sticky="w")

        folder = ctk.CTkFrame(opt, fg_color="transparent")
        folder.grid(row=2, column=0, columnspan=6, sticky="ew", padx=10, pady=(0, 10))
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
        self.updates_btn = ctk.CTkButton(bar, text="⟳ Güncellemeler", width=160, height=30,
                                         command=self._open_updates)
        self.updates_btn.pack(side="right", padx=3)
        self.clip_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(bar, text="Panoyu izle", variable=self.clip_var,
                        command=self._on_clip_toggle).pack(side="right", padx=12)

    def _build_filter_bar(self):
        """Search, filter, sort and the actions for the ticked rows."""
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 6))
        bar.columnconfigure(0, weight=1)
        # no textvariable here: customtkinter hides the placeholder when one is used
        self.search_entry = ctk.CTkEntry(bar, height=30, placeholder_text="🔍 Listede ara…")
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.search_entry.bind("<KeyRelease>", lambda e: self._sync_rows())
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

    # ----------------------------------------------------------------------- actions
    def _on_kind(self, label):
        kind = KIND_LABELS.get(label, "auto")
        self.cfg.set("kind", label)
        self.quality_menu.configure(state="normal" if kind in ("auto", "video") else "disabled")
        self.bitrate_menu.configure(state="normal" if kind == "audio" else "disabled")

    def _clipboard_text(self):
        try:
            return self.clipboard_get().strip()
        except Exception:
            return ""

    def _on_clip_toggle(self):
        # links that are already in the clipboard are NOT added, only new ones
        self._last_clip = self._clipboard_text()
        self.cfg.set("clip_watch", bool(self.clip_var.get()))
        self.notice("Pano izleme açık: kopyaladığın her yeni link otomatik eklenir"
                    if self.clip_var.get() else "Pano izleme kapalı")

    def _watch_clipboard(self):
        if not self.clip_var.get():
            return
        text = self._clipboard_text()
        if text and text != self._last_clip:
            self._last_clip = text
            urls = [u for u in re.split(r"\s+", text) if is_url(u)]
            if urls and len(urls) == len(text.split()):
                self.add_urls(urls)
                self.notice(f"Panodan eklendi: {urls[0][:60]}")

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
        """Add every link of a .txt file (one per line, or any text that contains links)."""
        path = filedialog.askopenfilename(title="Linklerin olduğu dosya",
                                          filetypes=[("Metin dosyaları", "*.txt *.csv *.url *.list"),
                                                     ("Tüm dosyalar", "*.*")])
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
        )

    def notice(self, text, seconds=6):
        self._notice, self._notice_until = text, time.time() + seconds

    def add_urls(self, urls):
        """Add links; returns how many were added. Links already in the list are skipped
        (unless that is switched off in the settings)."""
        s = self._settings()
        skip = bool(self.cfg.get("block_duplicates"))
        good = [normalize_url(u) for u in urls if is_url(u)]
        added = duplicates = 0
        for u in good:
            if self.manager.add_url(u, s, skip_duplicates=skip):
                added += 1
            else:
                duplicates += 1
        bad = len(urls) - len(good)
        if added and duplicates:
            self.notice(f"{added} bağlantı eklendi, {duplicates} tanesi zaten listedeydi")
        elif duplicates:
            self.notice(f"{duplicates} link zaten listede, atlandı")
        elif bad:
            self.notice(f"{bad} geçersiz bağlantı atlandı (http/https ile başlamalı)")
        elif added > 1:
            self.notice(f"{added} bağlantı eklendi")
        return added

    def add_from_entry(self):
        urls = [u for u in re.split(r"\s+", self.url_entry.get().strip()) if u]
        if not urls:
            self.notice("Lütfen bir bağlantı yapıştır.")
            return
        if self.add_urls(urls):
            self.url_entry.delete(0, "end")

    # ----------------------------------------------------------------- drag and drop
    def _add_from_paths(self, paths):
        """Links from text files (the 📄 button and dropped files)."""
        urls = []
        for p in paths:
            urls += urls_from_file(p)
        if not urls:
            self.notice("Dosyada bağlantı bulunamadı")
            return 0
        return self.add_urls(urls)

    def _on_drop(self, event):
        """A link (text) or text files with links were dropped on the window."""
        urls = []
        for part in self.tk.splitlist(event.data):
            urls += urls_from_file(part) if os.path.isfile(part) else extract_urls(part)
        if urls:
            self.add_urls(urls)
        else:
            self.notice("Bırakılan şeyde bağlantı bulunamadı")
        return getattr(event, "action", None)

    # ------------------------------------------------------ list: filter / sort / select
    def _on_filter(self, value):
        self.cfg.set("filter", value)
        self._sync_rows()

    def _on_sort(self, value):
        self.cfg.set("sort", value)
        self._sync_rows()

    def _visible_items(self):
        text = self.search_entry.get().strip().lower()
        states = FILTER_STATES.get(self.filter_menu.get())
        items = [it for it in list(self.manager.items)
                 if (states is None or it.state in states)
                 and (not text or text in it.display_name.lower() or text in it.url.lower())]
        items.sort(key=SORT_KEYS.get(self.sort_menu.get(), SORT_KEYS["Yeni üstte"]))
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
                "Hızlı İndirici", f"{len(sel)} indirme listeden silinsin mi?\n"
                                  "(Yarım kalan geçici dosyalar da silinir.)"):
            return
        for it in sel:
            self.manager.remove(it)
        self.selected.clear()
        self._sync_rows()

    def _update_selection_ui(self):
        n = len(self.selected)
        self.sel_label.configure(text=f"{n} seçili" if n else "")
        state = "normal" if n else "disabled"
        for b in self.sel_buttons:
            b.configure(state=state)
        visible = set(self._order or [])
        self.select_all_var.set(bool(visible) and visible <= self.selected)

    def _sync_rows(self):
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
                    text="Henüz indirme yok. Bir link yapıştır veya buraya sürükle." if not items
                    else "Aramaya / filtreye uyan indirme yok.")
                self.empty_label.pack(pady=40)
            self._order = order
        for iid in order:
            self.rows[iid].refresh()
        self._update_selection_ui()

    # ------------------------------------------------------------------ settings window
    def _open_settings(self):
        try:
            if self.settings_panel is not None and self.settings_panel.winfo_exists():
                self.settings_panel.lift()
                return
        except TclError:
            pass
        self.settings_panel = SettingsPanel(self)

    def apply_setting(self, key, value):
        """Settings window changed something: save it and apply it at once."""
        self.cfg.set(key, value)
        if key == "max_parallel":
            self.manager.set_max_parallel(int(value))
        elif key == "speed_limit":
            LIMITER.set_rate(SPEED_LIMITS[value] * 1024)
            self.notice("Hız sınırı kaldırıldı" if SPEED_LIMITS[value] == 0 else f"Hız sınırı: {value}")

    def set_after_all(self, label):
        self.after_all = label
        action = AFTER_ALL.get(label, "none")
        if action != "none":
            self.notice(f"Tüm indirmeler bitince: {label.lower()}", 8)

    def test_notification(self):
        self._notify("done", "Bildirimler çalışıyor ✔")

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
        self.after_all = "Hiçbir şey yapma"
        text, seconds = {"close": ("Uygulama kapanacak", 10),
                         "sleep": ("Bilgisayar uykuya geçecek", 30),
                         "shutdown": ("Bilgisayar kapanacak", 30)}[action]
        notify.play_sound("done")
        CountdownDialog(self, f"Tüm indirmeler bitti.\n{text}", seconds, lambda: self._do_power(action))

    def _do_power(self, action):
        if action == "close":
            self._on_close()
        else:
            notify.power_action(action)

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

    def update_card(self, key):
        """Button on a card: install FFmpeg when it is missing, otherwise update."""
        if key == "ffmpeg" and self.updates.components["ffmpeg"].status == "missing":
            threading.Thread(target=self.updates.install_ffmpeg, daemon=True).start()
        else:
            self.check_updates(install=True)

    def _update_update_widgets(self):
        comps = list(self.updates.components.values())
        working = next((c for c in comps if c.status == "working"), None)
        if working is not None:
            self.update_label.configure(text=f"{working.title}: {working.message}")
            self.update_progress.set(working.progress)
            self.update_progress.grid()
            self.update_bar.grid()
        elif self.updates.running:
            self.update_label.configure(text="Bileşenler kontrol ediliyor…")
            self.update_progress.grid_remove()
            self.update_bar.grid()
        else:
            self.update_bar.grid_remove()

        if self.updates.running:
            text = "⟳ Kontrol ediliyor…"
        else:
            n = sum(c.status == "available" for c in comps)
            text = f"⟳ Güncellemeler ({n})" if n else "⟳ Güncellemeler"
        if text != self._btn_text:
            self._btn_text = text
            self.updates_btn.configure(text=text)

    # ------------------------------------------------------------------ close / loop
    def _on_close(self):
        if self._closing:
            return
        self._closing = True
        self._save_folder()
        self.manager.shutdown()  # asks running downloads to pause; returns at once
        self._finish_close(time.time() + 15)

    def _finish_close(self, deadline):
        """Wait, without freezing the window, until downloads have saved their state."""
        if (self.manager.busy() or self.updates.writing) and time.time() < deadline:
            self.status.configure(text="Kapatılıyor… indirmeler kaydediliyor")
            self.after(100, lambda: self._finish_close(deadline))
            return
        self.manager.save()
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

    def _tick(self):
        self._tick_no += 1
        try:
            self._sync_rows()
            self._watch_clipboard()
            self._drain_notices()
            self._drain_events()
            self._check_after_all()
            if self._tick_no % 10 == 0:
                self._ffmpeg_ok = bool(find_ffmpeg())
            if self._tick_no % 20 == 0:
                gc.collect()  # here, on the window's thread: see __init__
            self._update_update_widgets()
            self._update_status()
        finally:
            if not self._closing:
                self.after(300, self._tick)

    def _update_status(self):
        items = self.manager.items
        active = [i for i in items if i.state in (DOWNLOADING, PROCESSING, RESOLVING)]
        queued = sum(1 for i in items if i.state == QUEUED)
        speed = sum(i.speed for i in items if i.state == DOWNLOADING)
        parts = [f"Aktif: {len(active)}/{self.manager.max_parallel}", f"Sırada: {queued}",
                 f"Hız: {human_size(speed)}/s"]
        limit = self.cfg.get("speed_limit")
        if SPEED_LIMITS.get(limit):
            parts.append(f"Sınır: {limit}")
        parts.append("FFmpeg: hazır" if self._ffmpeg_ok else "FFmpeg: yok (gerekince otomatik indirilir)")
        text = "  •  ".join(parts)
        if self.after_all != "Hiçbir şey yapma":
            text += f"  •  Bitince: {self.after_all.lower()}"
        if self._notice and time.time() < self._notice_until:
            text = f"{self._notice}    |    {text}"
        self.status.configure(text=text)
