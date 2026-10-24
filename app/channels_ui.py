"""📺 The channel window: follow channels, see their new videos, download the ones you want."""
import time
import webbrowser
from tkinter import TclError, ttk

import customtkinter as ctk

from . import channels
from .extra_ui import _when
from .i18n import tr
from .music_ui import style_table
from .ui_common import fit_geometry, set_window_icon
from .utils import human_duration


class ChannelsWindow(ctk.CTkToplevel):
    def __init__(self, parent, store, watcher, download):
        """`download(videos, kind)` puts videos into the download list ("video": MP4, "audio": MP3)."""
        super().__init__(parent)
        set_window_icon(self)
        self.store, self.watcher, self._download = store, watcher, download
        self.title("DISO • Kanal takibi")
        fit_geometry(self, 940, 700)
        self.minsize(680, 520)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)
        ctk.CTkLabel(self, text="📺 Kanal takibi", font=ctk.CTkFont(size=22, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(16, 0))
        ctk.CTkLabel(self, text="Takip ettiğin kanallara yeni video gelince haber veririm. Hiçbir şeyi kendiliğimden "
                                "indirmem: ne indireceğini sen seçersin.",
                     text_color="gray", anchor="w", justify="left", wraplength=860).grid(
            row=1, column=0, sticky="ew", padx=20, pady=(2, 8))

        add = ctk.CTkFrame(self, fg_color="transparent")
        add.grid(row=2, column=0, sticky="ew", padx=16)
        add.columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(add, height=34, placeholder_text="Kanal linki, @kanaladı ya da kanalın bir videosu")
        self.entry.grid(row=0, column=0, sticky="ew", padx=(4, 8))
        self.entry.bind("<Return>", lambda e: self.follow())
        self.follow_btn = ctk.CTkButton(add, text="＋ Takip et", width=120, height=34, command=self.follow)
        self.follow_btn.grid(row=0, column=1, padx=(0, 4))

        style_table(self)
        top = ctk.CTkFrame(self)
        top.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 4))
        top.columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Takip ettiklerin", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=10, pady=(6, 0))
        self.unfollow_btn = ctk.CTkButton(top, text="✖ Takibi bırak", width=130, height=28, fg_color="transparent",
                                          border_width=1, text_color=("gray20", "gray85"), command=self.unfollow)
        self.unfollow_btn.grid(row=0, column=1, sticky="e", padx=8, pady=(6, 0))
        self.channel_tree = ttk.Treeview(top, columns=("name", "checked", "state"), show="headings", height=4,
                                         selectmode="browse", style="Music.Treeview")
        for name, text, width, stretch in (("name", "Kanal", 300, True), ("checked", "Son bakış", 130, False),
                                           ("state", "Durum", 260, True)):
            self.channel_tree.heading(name, text=text, anchor="w")
            self.channel_tree.column(name, width=width, minwidth=80, stretch=stretch)
        self.channel_tree.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        self.channel_tree.bind("<Double-Button-1>", lambda e: self._open_channel())

        box = ctk.CTkFrame(self)
        box.grid(row=4, column=0, sticky="nsew", padx=16, pady=4)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        self.new_label = ctk.CTkLabel(box, text="Yeni videolar", font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
        self.new_label.grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 0))
        self.tree = ttk.Treeview(box, columns=("title", "channel", "length", "found"), show="headings",
                                 selectmode="extended", style="Music.Treeview")
        for name, text, width, anchor, stretch in (("title", "Video", 380, "w", True), ("channel", "Kanal", 170, "w", False),
                                                   ("length", "Süre", 70, "e", False), ("found", "Geldi", 120, "w", False)):
            self.tree.heading(name, text=text, anchor=anchor)
            self.tree.column(name, width=width, minwidth=50, anchor=anchor, stretch=stretch)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=8)
        bar = ctk.CTkScrollbar(box, command=self.tree.yview)
        bar.grid(row=1, column=1, sticky="ns", pady=8, padx=(0, 4))
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.bind("<Double-Button-1>", lambda e: self._open_video())
        self.empty = ctk.CTkLabel(box, text="", text_color="gray")

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=5, column=0, sticky="ew", padx=16, pady=(4, 2))
        ctk.CTkButton(foot, text="🎬 MP4 indir", width=120, command=lambda: self.download("video")).pack(side="left", padx=4)
        ctk.CTkButton(foot, text="🎵 MP3 indir", width=120, command=lambda: self.download("audio")).pack(side="left", padx=4)
        ctk.CTkButton(foot, text="✓ Gördüm", width=100, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.dismiss).pack(side="left", padx=4)
        ctk.CTkButton(foot, text="Hepsini temizle", width=120, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.dismiss_all).pack(side="left", padx=4)

        end = ctk.CTkFrame(self, fg_color="transparent")
        end.grid(row=6, column=0, sticky="ew", padx=16, pady=(4, 14))
        end.columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(end, text="", text_color="gray", anchor="w", justify="left", wraplength=420)
        self.status.grid(row=0, column=0, sticky="ew", padx=4)
        ctk.CTkLabel(end, text="Bakma sıklığı:").grid(row=0, column=1, padx=(8, 4))
        self.every_menu = ctk.CTkOptionMenu(end, values=list(channels.EVERY), width=150, command=self.store.set_every)
        self.every_menu.set(self.store.every)
        self.every_menu.grid(row=0, column=2, padx=4)
        self.check_btn = ctk.CTkButton(end, text="⟳ Şimdi bak", width=120, command=self.check_now)
        self.check_btn.grid(row=0, column=3, padx=4)
        ctk.CTkButton(end, text="Kapat", width=90, command=self.destroy).grid(row=0, column=4, padx=(4, 0))
        self.bind("<Escape>", lambda e: self.destroy())
        self.shown = []
        self._asked = False
        self.refresh()

    # ------------------------------------------------------------------ showing
    def refresh(self):
        self.channel_tree.delete(*self.channel_tree.get_children())
        for i, c in enumerate(self.store.channels):
            state = ("⚠ " + c["error"]) if c.get("error") else "✓"
            self.channel_tree.insert("", "end", iid=str(i), values=(
                c["name"], tr(_when(c["checked"])) if c.get("checked") else "—", tr(state)))
        picked = {self.shown[int(i)]["url"] for i in self.tree.selection() if int(i) < len(self.shown)}
        self.tree.delete(*self.tree.get_children())
        self.shown = list(self.store.new)
        for i, v in enumerate(self.shown):
            self.tree.insert("", "end", iid=str(i), values=(
                v["title"], v.get("channel", ""), human_duration(v.get("duration")),
                tr(_when(v["found"])) if v.get("found") else ""))
            if v["url"] in picked:
                self.tree.selection_add(str(i))
        self.new_label.configure(text=f"Yeni videolar ({len(self.shown)})" if self.shown else "Yeni videolar")
        if self.shown:
            self.empty.place_forget()
        else:
            self.empty.configure(text="Yeni video yok." if self.store.channels
                                 else "Henüz bir kanal takip etmiyorsun. Yukarıya bir kanalın linkini yapıştır.")
            self.empty.place(relx=0.5, rely=0.55, anchor="center")
        self.check_btn.configure(state="disabled" if self.watcher.busy else "normal")

    def note(self, text):
        self.status.configure(text=text)

    def take(self, news):
        """The watcher's news (the app hands them over)."""
        for kind, what, error in news:
            if kind == "followed":
                self.follow_btn.configure(state="normal")
                if what:
                    self.entry.delete(0, "end")
                    self.note(f"✓ “{what['name']}” takip ediliyor; yeni video gelince haber veririm")
                else:
                    self.note(f"Takip edemedim: {error}")
            elif kind == "checked" and self._asked:          # only when "Look now" was pressed
                self._asked = False
                self.note(f"Kanallara baktım ({time.strftime('%H:%M')})")
        self.refresh()

    # ------------------------------------------------------------------ actions
    def follow(self):
        text = self.entry.get().strip()
        if not text:
            self.note("Önce bir kanal linki yapıştır")
            return
        if not channels.channel_link(text):
            self.note("Bu bir kanal linki değil")
            return
        self.follow_btn.configure(state="disabled")
        self.note("Kanala bakıyorum…")
        self.watcher.follow(text)

    def selected_channel(self):
        sel = self.channel_tree.selection()
        return self.store.channels[int(sel[0])] if sel and int(sel[0]) < len(self.store.channels) else None

    def unfollow(self):
        from tkinter import messagebox
        c = self.selected_channel()
        if c is None:
            self.note("Önce listeden bir kanal seç")
            return
        if messagebox.askyesno("DISO", f"“{c['name']}” kanalının takibi bırakılsın mı?", parent=self):
            self.store.unfollow(c["url"])
            self.refresh()

    def selected(self):
        return [self.shown[int(i)] for i in self.tree.selection() if int(i) < len(self.shown)]

    def download(self, kind):
        videos = self.selected()
        if not videos:
            self.note("Önce indirmek istediğin videoları seç")
            return
        added = self._download(videos, kind)
        self.store.dismiss(v["url"] for v in videos)
        self.refresh()
        self.note(f"⬇ {added} video indirme listesine eklendi")

    def dismiss(self):
        videos = self.selected()
        if videos:
            self.store.dismiss(v["url"] for v in videos)
            self.refresh()

    def dismiss_all(self):
        self.store.dismiss(v["url"] for v in list(self.store.new))
        self.refresh()

    def check_now(self):
        if not self.store.channels:
            self.note("Önce bir kanal takip et")
            return
        self._asked = True
        self.watcher.check_now()
        self.check_btn.configure(state="disabled")
        self.note("Kanallara bakıyorum…")

    def _open_video(self):
        videos = self.selected()
        if videos:
            webbrowser.open(videos[0]["url"])

    def _open_channel(self):
        c = self.selected_channel()
        if c:
            webbrowser.open(c["url"])

    def alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except TclError:
            return False
