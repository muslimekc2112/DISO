"""🏷 The tag editor of the music player: a song's name, artist, album, year, genre and cover picture,
written into the file itself (tags.write_tags), so every player and phone shows them too."""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import tags
from .ui_common import fit_geometry, set_window_icon

LABELS = (("title", "Şarkının adı"), ("artist", "Sanatçı"), ("album", "Albüm"), ("date", "Yıl"), ("genre", "Tür"))
PREVIEW = 120


class TagEditor(ctk.CTkToplevel):
    """before(path) is called on the window's thread just before writing (its answer goes to done), then
    write(path, fields, cover) on a worker thread, then done(path, fields, error, before's answer)."""

    def __init__(self, parent, path, write, done, before=None):
        super().__init__(parent)
        set_window_icon(self)
        self.path, self._write, self._done, self._before = path, write, done, before
        self._place = None
        self.cover = tags.KEEP
        self._image = None
        self._result = None
        self.title("DISO • Şarkı bilgileri")
        fit_geometry(self, 520, 400)
        self.minsize(460, 360)
        self.columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text=os.path.basename(path), anchor="w", text_color="gray",
                     wraplength=480).grid(row=0, column=0, columnspan=3, sticky="ew", padx=18, pady=(14, 8))
        now = tags.read_fields(path)
        self.entries = {}
        for row, (key, label) in enumerate(LABELS, start=1):
            ctk.CTkLabel(self, text=label, anchor="w").grid(row=row, column=0, sticky="w", padx=(18, 10), pady=4)
            entry = ctk.CTkEntry(self)
            entry.insert(0, now.get(key, ""))
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            self.entries[key] = entry

        side = ctk.CTkFrame(self, fg_color="transparent")
        side.grid(row=1, column=2, rowspan=5, sticky="n", padx=(14, 18))
        self.picture = ctk.CTkLabel(side, text="Kapak yok", width=PREVIEW, height=PREVIEW, corner_radius=8,
                                    fg_color=("gray85", "gray25"))
        self.picture.pack()
        can_cover = os.path.splitext(path)[1].lower() in tags.COVER_FORMATS
        state = "normal" if can_cover else "disabled"
        self.pick_btn = ctk.CTkButton(side, text="🖼 Resim seç…", width=PREVIEW, command=self.pick_cover, state=state)
        self.pick_btn.pack(pady=(8, 4))
        self.drop_btn = ctk.CTkButton(side, text="Kapağı kaldır", width=PREVIEW, fg_color="transparent", border_width=1,
                                      text_color=("gray20", "gray85"), command=self.drop_cover, state=state)
        self.drop_btn.pack()
        if not can_cover:
            ctk.CTkLabel(side, text="Bu dosya türü\nkapak taşımaz", text_color="gray").pack(pady=(6, 0))
        self._show_picture(tags.extract_cover(path))

        self.hint = ctk.CTkLabel(self, text="Bilgiler dosyanın içine yazılır; şarkı değişmez.", text_color="gray",
                                 anchor="w", justify="left", wraplength=480)
        self.hint.grid(row=6, column=0, columnspan=3, sticky="ew", padx=18, pady=(12, 0))
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=7, column=0, columnspan=3, sticky="ew", padx=18, pady=(8, 16))
        foot.columnconfigure(0, weight=1)
        self.save_btn = ctk.CTkButton(foot, text="💾 Kaydet", width=100, command=self.save)
        self.save_btn.grid(row=0, column=1, padx=(8, 8))
        ctk.CTkButton(foot, text="Vazgeç", width=90, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.destroy).grid(row=0, column=2)
        self.bind("<Return>", lambda e: self.save())
        self.bind("<Escape>", lambda e: self.destroy())
        try:
            self.transient(parent)
        except tk.TclError:
            pass
        self.after(50, lambda: self.entries["title"].focus_set())

    # ------------------------------------------------------------------ the cover
    def _show_picture(self, picture):
        if not picture:
            self.picture.configure(image=None, text="Kapak yok")
            self._image = None
            return
        try:
            from PIL import Image
            with Image.open(picture) as im:
                img = im.convert("RGB")
                img.thumbnail((PREVIEW, PREVIEW))
        except Exception:  # noqa: BLE001 - not a picture: shown as none
            self.picture.configure(image=None, text="Kapak yok")
            self._image = None
            return
        self._image = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        self.picture.configure(image=self._image, text="")

    def _ask_picture(self):
        return filedialog.askopenfilename(parent=self, title="Kapak resmi seç",
                                          filetypes=[("Resim", "*.jpg *.jpeg *.png *.webp *.bmp"), ("Hepsi", "*.*")])

    def pick_cover(self):
        picture = self._ask_picture()
        if picture:
            self.cover = picture
            self._show_picture(picture)

    def drop_cover(self):
        self.cover = tags.REMOVE
        self._show_picture(None)

    # ------------------------------------------------------------------ saving
    def fields(self) -> dict:
        return {key: entry.get().strip() for key, entry in self.entries.items()}

    def save(self):
        if str(self.save_btn.cget("state")) == "disabled":
            return
        fields, cover = self.fields(), self.cover
        self.save_btn.configure(state="disabled", text="Yazıyorum…")
        self._place = self._before(self.path) if self._before else None

        def work():
            try:
                self._write(self.path, fields, cover)
                self._result = (fields, "")
            except Exception as e:  # noqa: BLE001 - said in the window
                self._result = (fields, str(e) or type(e).__name__)
        threading.Thread(target=work, daemon=True, name="tag-writer").start()
        self.after(50, self._wait)

    def _wait(self):
        if self._result is None:
            self.after(50, self._wait)
            return
        fields, error = self._result
        self._done(self.path, fields, error, self._place)
        self._place = None
        if error:
            self.save_btn.configure(state="normal", text="💾 Kaydet")
            messagebox.showerror("DISO", f"Bilgiler yazılamadı: {error}", parent=self)
            return
        self.destroy()
