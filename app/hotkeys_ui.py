"""⌨ The window where the music player's shortcuts are set: press the button of an action, then the key.
Esc leaves it as it was, Delete / Backspace takes the key away. A key another action had moves over."""
import tkinter as tk

import customtkinter as ctk

from . import hotkeys
from .ui_common import fit_geometry, set_if_changed, set_window_icon


class KeysWindow(ctk.CTkToplevel):
    def __init__(self, music):
        super().__init__(music)
        set_window_icon(self)
        self.music = music
        self.title("DISO • Kısayolları ayarla")
        fit_geometry(self, 620, 680)
        self.minsize(520, 460)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ctk.CTkLabel(self, text="⌨ Kısayolları ayarla", font=ctk.CTkFont(size=22, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(16, 2))
        ctk.CTkLabel(self, text="Bir düğmeye bas, sonra istediğin tuşa. Esc: vazgeç, Delete: tuşu kaldır. \"Her "
                                "yerde\" tuşları DISO arkadayken de çalışır (Ctrl, Alt ya da Shift ile birlikte).",
                     text_color="gray", anchor="w", justify="left", wraplength=560).grid(row=1, column=0, sticky="ew",
                                                                                         padx=20)
        body = ctk.CTkScrollableFrame(self)
        body.grid(row=2, column=0, sticky="nsew", padx=16, pady=10)
        body.columnconfigure(0, weight=1)
        ctk.CTkLabel(body, text="Pencerede", text_color="gray").grid(row=0, column=1, padx=6)
        ctk.CTkLabel(body, text="Her yerde", text_color="gray").grid(row=0, column=2, padx=6)
        self.keys, self.global_keys = music.shortcut_keys()
        self.buttons = {}
        for row, (name, label) in enumerate(hotkeys.ACTIONS, start=1):
            ctk.CTkLabel(body, text=label, anchor="w").grid(row=row, column=0, sticky="ew", padx=8, pady=3)
            for col, where in ((1, "window"), (2, "global")):
                b = ctk.CTkButton(body, text="", width=150, fg_color="transparent", border_width=1,
                                  text_color=("gray20", "gray85"), command=lambda n=name, w=where: self.listen(n, w))
                b.grid(row=row, column=col, padx=6, pady=3)
                self.buttons[(name, where)] = b
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 14))
        foot.columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(foot, text="", text_color="gray", anchor="w", justify="left", wraplength=330)
        self.status.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(foot, text="Varsayılana dön", width=130, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.reset).grid(row=0, column=1, padx=6)
        ctk.CTkButton(foot, text="Kapat", width=90, command=self.destroy).grid(row=0, column=2)
        self.waiting = None
        self.bind("<KeyPress>", self._on_key)
        self.show()

    def show(self):
        for (name, where), b in self.buttons.items():
            seq = (self.keys if where == "window" else self.global_keys).get(name, "")
            waiting = self.waiting == (name, where)
            b.configure(text="Bir tuşa bas…" if waiting else hotkeys.shown(seq),
                        border_color=("#B35EC9", "#B35EC9") if waiting else ("gray60", "gray40"))

    def listen(self, name, where):
        self.waiting = (name, where)
        set_if_changed(self.status, text=f"“{hotkeys.NAMES[name]}” için bir tuşa bas")
        self.show()
        self.focus_force()

    def _on_key(self, event):
        if self.waiting is None:
            if event.keysym == "Escape":
                self.destroy()
            return None
        seq = hotkeys.from_event(event)
        if not seq:
            return "break"                                  # only Ctrl / Alt / Shift so far
        self.press(seq)
        return "break"

    def press(self, seq):
        """The key pressed while an action waits for one (tests call this directly)."""
        name, where = self.waiting
        self.waiting = None
        keys = self.keys if where == "window" else self.global_keys
        if seq == "Escape":
            set_if_changed(self.status, text="")
        elif seq in ("Delete", "BackSpace"):
            keys[name] = ""
            set_if_changed(self.status, text=f"“{hotkeys.NAMES[name]}” tuşsuz kaldı")
        elif where == "global" and hotkeys.win32(seq) is None:
            set_if_changed(self.status, text="Her yerde çalışacak tuş Ctrl, Alt ya da Shift ile birlikte olmalı "
                                             "(örn. Ctrl + Alt + P)")
        else:
            other = hotkeys.conflicts(keys, name, seq)
            if other:
                keys[other] = ""
            keys[name] = seq
            set_if_changed(self.status, text=(f"{hotkeys.shown(seq)}: “{hotkeys.NAMES[name]}”" +
                                              (f" (“{hotkeys.NAMES[other]}” tuşsuz kaldı)" if other else "")))
            self.music.set_shortcuts(self.keys, self.global_keys)
        if seq in ("Delete", "BackSpace"):
            self.music.set_shortcuts(self.keys, self.global_keys)
        try:
            self.show()
        except tk.TclError:
            pass

    def reset(self):
        self.keys, self.global_keys = dict(hotkeys.DEFAULT_KEYS), dict(hotkeys.DEFAULT_GLOBAL)
        self.waiting = None
        self.music.set_shortcuts(self.keys, self.global_keys)
        set_if_changed(self.status, text="Kısayollar varsayılana döndü")
        self.show()
