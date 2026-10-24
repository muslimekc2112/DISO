"""🧲 Which files of a torrent to download: its folders as a tree with tick boxes, quick choices (all, none,
videos, music, pictures, documents), a search, the size of what is chosen and the room left on the disk."""
import os
import shutil
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from . import look
from .i18n import tr
from .music_ui import style_table
from .ui_common import fit_geometry, set_window_icon
from .utils import category_for, human_size

ON, OFF, SOME = "☑", "☐", "◩"
KINDS = (("video", "🎬 Videolar", "Video"), ("music", "🎵 Müzik", "Müzik"), ("pictures", "🖼 Resimler", "Resim"),
         ("documents", "📄 Belgeler", "Belge"), ("archives", "🗜 Arşivler", "Arşiv"))

STYLE = "Torrent.Treeview"


def kind_of(path) -> str:
    """Video / Müzik / Resim / Belge / Arşiv / Program / Diğer (as the "by type" folders)."""
    return category_for(os.path.basename(path))


def free_space(folder) -> int:
    probe = os.path.abspath(folder)
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return -1


class TorrentFilesDialog(ctk.CTkToplevel):
    """files: [{"index", "path", "size", "done"}]. on_done(indexes) with the chosen ones, or on_done(None) when
    closed without a choice. `first`: asked before the download starts ("Vazgeç" then cancels the torrent)."""

    def __init__(self, parent, name, files, folder, on_done, chosen=None, first=True):
        super().__init__(parent)
        set_window_icon(self)
        self.files = list(files)
        self.folder = folder
        self._on_done = on_done
        self._answered = False
        self.first = first
        self.ticked = set(chosen) if chosen else {f["index"] for f in self.files}
        self.title("DISO • 🧲 Torrent dosyaları")
        fit_geometry(self, 720, 580)
        self.minsize(560, 420)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        total = sum(f["size"] for f in self.files)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 2))
        head.columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text=f"🧲 {name}" if name else "🧲 Torrent", anchor="w", justify="left", wraplength=640,
                     font=ctk.CTkFont(size=17, weight="bold")).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(head, text=f"{len(self.files)} dosya • toplam {human_size(total)}", anchor="w",
                     text_color=look.grey_text()).grid(row=1, column=0, sticky="w")

        quick = ctk.CTkFrame(self, fg_color="transparent")
        quick.grid(row=1, column=0, sticky="ew", padx=18, pady=(10, 4))
        ctk.CTkLabel(quick, text="Seç:", text_color=look.grey_text()).pack(side="left", padx=(0, 6))
        self.quick = {}
        for key, text in (("all", "Hepsi"), ("none", "Hiçbiri")):
            b = ctk.CTkButton(quick, text=text, width=70, height=28, command=lambda k=key: self.pick(k))
            b.pack(side="left", padx=(0, 6))
            self.quick[key] = b
        kinds = {kind_of(f["path"]) for f in self.files}
        for key, text, category in KINDS:
            if category in kinds:
                b = ctk.CTkButton(quick, text=text, width=96, height=28, fg_color="transparent", border_width=1,
                                  text_color=("gray20", "gray85"), command=lambda k=key: self.pick(k))
                b.pack(side="left", padx=(0, 6))
                self.quick[key] = b

        find = ctk.CTkFrame(self, fg_color="transparent")
        find.grid(row=2, column=0, sticky="ew", padx=18, pady=(2, 6))
        find.columnconfigure(0, weight=1)
        self.search = ctk.CTkEntry(find, placeholder_text="🔎 Dosya ara (yalnız gösterilenleri süzer)")
        self.search.grid(row=0, column=0, sticky="ew")
        self.search.bind("<KeyRelease>", lambda e: self._fill())
        self.expand_btn = ctk.CTkButton(find, text="⊞ Hepsini aç", width=110, height=28, fg_color="transparent",
                                        border_width=1, text_color=("gray20", "gray85"), command=self._toggle_open)
        self.expand_btn.grid(row=0, column=1, padx=(8, 0))
        self._open_all = True

        box = ctk.CTkFrame(self, fg_color="transparent")
        box.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 6))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        style_table(self, STYLE)
        self.tree = ttk.Treeview(box, columns=("size", "kind"), style=STYLE, selectmode="extended")
        self.tree.heading("#0", text=tr("Dosya"), anchor="w")
        self.tree.heading("size", text=tr("Boyut"), anchor="e")
        self.tree.heading("kind", text=tr("Dosya türü"), anchor="w")
        self.tree.column("#0", width=400, stretch=True)
        self.tree.column("size", width=150, anchor="e", stretch=False)
        self.tree.column("kind", width=90, stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview) if look.is_nostalgia() \
            else ctk.CTkScrollbar(box, command=self.tree.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<space>", lambda e: self._toggle_selected() or "break")
        self.tree.bind("<Double-1>", lambda e: "break")

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=4, column=0, sticky="ew", padx=18, pady=(4, 6))
        foot.columnconfigure(0, weight=1)
        self.summary = ctk.CTkLabel(foot, text="", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.summary.grid(row=0, column=0, sticky="w")
        self.room = ctk.CTkLabel(foot, text="", anchor="w", text_color=look.grey_text())
        self.room.grid(row=1, column=0, sticky="w")
        self.remember = None
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=5, column=0, sticky="ew", padx=18, pady=(2, 16))
        buttons.columnconfigure(0, weight=1)
        if first:
            self.remember = ctk.CTkCheckBox(buttons, text="Bir daha sorma, hep hepsini indir")
            self.remember.grid(row=0, column=0, sticky="w")
        self.ok_btn = ctk.CTkButton(buttons, text="⬇ İndir" if first else "✓ Uygula", width=120, command=self.accept)
        self.ok_btn.grid(row=0, column=1, padx=(8, 8))
        ctk.CTkButton(buttons, text="Torrenti iptal et" if first else "Vazgeç", width=120, fg_color="transparent",
                      border_width=1, text_color=("gray20", "gray85"), command=self.cancel).grid(row=0, column=2)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())
        self.bind("<Return>", lambda e: self.accept())
        self._nodes = {}            # tree id -> set of file indexes under it
        self._fill()
        try:
            self.transient(parent)
        except tk.TclError:
            pass
        self.lift()
        self.after(80, self.focus_force)

    # ------------------------------------------------------------------ the tree
    def _visible(self):
        words = self.search.get().casefold().split()
        return [f for f in self.files if all(w in f["path"].casefold() for w in words)]

    def _fill(self):
        self.tree.delete(*self.tree.get_children())
        self._nodes = {}
        folders = {}
        for f in sorted(self._visible(), key=lambda f: [p.casefold() for p in f["path"].split("/")]):
            parts = f["path"].split("/")
            parent = ""
            for depth in range(len(parts) - 1):
                key = "/".join(parts[:depth + 1])
                if key not in folders:
                    folders[key] = self.tree.insert(parent, "end", text="", open=self._open_all,
                                                    values=("", tr("Klasör")))
                    self._nodes[folders[key]] = set()
                parent = folders[key]
                self._nodes[parent].add(f["index"])
            leaf = self.tree.insert(parent, "end", text="", values=(human_size(f["size"]), tr(kind_of(f["path"]))))
            self._nodes[leaf] = {f["index"]}
            self.tree.item(leaf, tags=(f"file{f['index']}",))
        self._names = {}
        for node in self._nodes:
            self._names[node] = None
        for key, node in folders.items():
            self._names[node] = "📁 " + key.split("/")[-1]
        for f in self.files:
            for node in self.tree.tag_has(f"file{f['index']}"):
                self._names[node] = os.path.basename(f["path"])
        self._paint()

    def _paint(self):
        sizes = {f["index"]: f["size"] for f in self.files}
        for node, indexes in self._nodes.items():
            on = len(indexes & self.ticked)
            mark = ON if on == len(indexes) else OFF if on == 0 else SOME
            text = f"{mark}  {self._names.get(node) or ''}"
            if self.tree.item(node, "text") != text:
                self.tree.item(node, text=text)
            if self.tree.get_children(node):
                chosen = sum(sizes[i] for i in indexes & self.ticked)
                total = sum(sizes[i] for i in indexes)
                self.tree.set(node, "size", human_size(total) if chosen in (0, total)
                              else f"{human_size(chosen)} / {human_size(total)}")
        count = len(self.ticked)
        size = sum(f["size"] for f in self.files if f["index"] in self.ticked)
        self.summary.configure(text=f"Seçilen: {count} / {len(self.files)} dosya • {human_size(size)}")
        free = free_space(self.folder)
        if free >= 0:
            short = size > free
            self.room.configure(text=(f"⚠ Diskte yer yetmiyor: {human_size(free)} boş" if short
                                      else f"Diskte boş yer: {human_size(free)} • {self.folder}"),
                                text_color=("#C62828", "#FF7070") if short else look.grey_text())
        self.ok_btn.configure(state="normal" if count else "disabled")

    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) not in ("tree", "cell"):
            return None
        node = self.tree.identify_row(event.y)
        if not node:
            return None
        element = self.tree.identify_element(event.x, event.y)
        if "indicator" in str(element):                 # the folder's ▸: open / close, no tick
            return None
        self.toggle(node)
        return "break"

    def toggle(self, node):
        indexes = self._nodes.get(node, set())
        if indexes <= self.ticked:
            self.ticked -= indexes
        else:
            self.ticked |= indexes
        self._paint()

    def _toggle_selected(self):
        for node in self.tree.selection():
            self.toggle(node)

    def _toggle_open(self):
        self._open_all = not self._open_all
        for node in self._nodes:
            if self.tree.get_children(node):
                self.tree.item(node, open=self._open_all)
        self.expand_btn.configure(text="⊞ Hepsini aç" if not self._open_all else "⊟ Hepsini kapat")

    def pick(self, what):
        """The quick choices: all, none, or only one kind of file (videos, music ...)."""
        if what == "all":
            self.ticked = {f["index"] for f in self.files}
        elif what == "none":
            self.ticked = set()
        else:
            category = next(c for k, _, c in KINDS if k == what)
            self.ticked = {f["index"] for f in self.files if kind_of(f["path"]) == category}
        self._paint()

    # ------------------------------------------------------------------ the answer
    def accept(self):
        if not self.ticked:
            return
        self._answer(sorted(self.ticked))

    def cancel(self):
        self._answer(None)

    def _answer(self, value):
        if self._answered:
            return
        self._answered = True
        remember = bool(self.remember is not None and self.remember.get())
        self.remember_choice = remember and value is not None
        try:
            self.destroy()
        finally:
            self._on_done(value, self.remember_choice)
