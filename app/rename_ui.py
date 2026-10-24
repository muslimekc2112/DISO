"""✏ The window that renames many songs' files at once: a pattern, a preview of every new name (and what is in
the way), then rename, and undo."""
import os
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from . import look, renamer
from .i18n import tr
from .music_ui import style_table
from .ui_common import fit_geometry, set_window_icon

STYLE = "Rename.Treeview"
MARKS = {renamer.OK: "✓", renamer.SAME: "= aynı", renamer.CLASH: "⚠ bu ad dolu", renamer.EMPTY: "⚠ ad çıkmadı"}


class RenameDialog(ctk.CTkToplevel):
    """rename(steps) -> (done, failed) does the work (the music window: it lets go of the song that plays
    and moves the lists along); undo(done) puts the names back. `pattern` is the one used last time."""

    def __init__(self, parent, tracks, rename, undo, pattern=renamer.PRESETS[0], on_pattern=None):
        super().__init__(parent)
        set_window_icon(self)
        self.tracks = list(tracks)
        self._rename, self._undo, self._on_pattern = rename, undo, on_pattern
        self.done = []
        self.steps = []
        self.title("DISO • ✏ Dosya adları")
        fit_geometry(self, 860, 560)
        self.minsize(640, 420)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        ctk.CTkLabel(head, text="✏ Dosya adlarını düzenle", font=ctk.CTkFont(size=17, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text=f"   {len(self.tracks)} şarkı", text_color=look.grey_text()).pack(side="left")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=18, pady=(6, 2))
        row.columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text="Ad kalıbı:").grid(row=0, column=0, padx=(0, 8))
        self.pattern = ctk.CTkComboBox(row, values=renamer.PRESETS, command=lambda v: self.refresh())
        self.pattern.set(pattern)
        self.pattern.grid(row=0, column=1, sticky="ew")
        self.pattern.bind("<KeyRelease>", lambda e: self.refresh())
        ctk.CTkLabel(row, text="Kullanılabilir: {sanatçı}  {şarkı}  {albüm}  {no}", text_color=look.grey_text(),
                     anchor="w").grid(row=1, column=1, sticky="w", pady=(2, 0))

        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=2, column=0, sticky="ew", padx=18, pady=(6, 6))
        self.capitals = ctk.CTkCheckBox(opts, text="Baş Harfleri Büyük Yap", command=self.refresh)
        self.capitals.pack(side="left", padx=(0, 18))
        self.plain = ctk.CTkCheckBox(opts, text="Türkçe harfleri sadeleştir (ş→s, ı→i…)", command=self.refresh)
        self.plain.pack(side="left")

        box = ctk.CTkFrame(self, fg_color="transparent")
        box.grid(row=3, column=0, sticky="nsew", padx=18)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        style_table(self, STYLE)
        self.tree = ttk.Treeview(box, columns=("old", "new", "state"), show="headings", style=STYLE,
                                 selectmode="none")
        for key, text, width in (("old", "Şimdiki ad", 300), ("new", "Yeni ad", 320), ("state", "", 110)):
            self.tree.heading(key, text=tr(text), anchor="w")
            self.tree.column(key, width=width, stretch=key != "state")
        self.tree.tag_configure("same", foreground="gray55")
        self.tree.tag_configure("bad", foreground="#D9534F")
        self.tree.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview) if look.is_nostalgia() \
            else ctk.CTkScrollbar(box, command=self.tree.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=bar.set)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=4, column=0, sticky="ew", padx=18, pady=(10, 16))
        foot.columnconfigure(0, weight=1)
        self.summary = ctk.CTkLabel(foot, text="", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.summary.grid(row=0, column=0, sticky="w")
        self.undo_btn = ctk.CTkButton(foot, text="↶ Geri al", width=100, fg_color="transparent", border_width=1,
                                      text_color=("gray20", "gray85"), command=self.take_back, state="disabled")
        self.undo_btn.grid(row=0, column=1, padx=(8, 0))
        self.ok_btn = ctk.CTkButton(foot, text="✏ Yeniden adlandır", width=150, command=self.go)
        self.ok_btn.grid(row=0, column=2, padx=8)
        ctk.CTkButton(foot, text="Kapat", width=90, command=self.destroy).grid(row=0, column=3)
        self.bind("<Escape>", lambda e: self.destroy())
        try:
            self.transient(parent)
        except tk.TclError:
            pass
        self.refresh()

    def refresh(self):
        """The preview follows the pattern and the tick boxes."""
        self.steps = renamer.plan(self.tracks, self.pattern.get(), plain=bool(self.plain.get()),
                                  capitals=bool(self.capitals.get()))
        self.tree.delete(*self.tree.get_children())
        for t, new, state in self.steps:
            tag = "same" if state == renamer.SAME else "bad" if state in (renamer.CLASH, renamer.EMPTY) else ""
            self.tree.insert("", "end", values=(os.path.basename(t["path"]), os.path.basename(new) if state != renamer.EMPTY
                                                else "", tr(MARKS[state])), tags=(tag,))
        changes = sum(1 for *_, s in self.steps if s == renamer.OK)
        problems = sum(1 for *_, s in self.steps if s in (renamer.CLASH, renamer.EMPTY))
        text = f"{changes} dosyanın adı değişecek" if changes else "Değişecek ad yok"
        if problems:
            text += f" • {problems} dosya atlanacak"
        self.summary.configure(text=text, text_color=look.grey_text() if not changes else
                               ctk.ThemeManager.theme["CTkLabel"]["text_color"])
        self.ok_btn.configure(state="normal" if changes else "disabled")

    def go(self):
        if not any(s == renamer.OK for *_, s in self.steps):
            return
        if self._on_pattern:
            self._on_pattern(self.pattern.get())
        done, failed = self._rename(self.steps)
        self.done = done
        self.refresh()                            # the tracks are the lists' own: they have their new paths now
        text = f"✓ {len(done)} dosyanın adı değişti"
        if failed:
            text += f" • {len(failed)} değişemedi ({failed[0][0]}: {failed[0][1]})"
        self.summary.configure(text=text)
        self.undo_btn.configure(state="normal" if done else "disabled")

    def take_back(self):
        if not self.done:
            return
        back = self._undo(self.done)
        self.done = []
        self.refresh()
        self.summary.configure(text=f"↶ {len(back)} dosya eski adına döndü")
        self.undo_btn.configure(state="disabled")
