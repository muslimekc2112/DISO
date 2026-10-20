"""🎛 The equalizer window of the music player: a ready-made setting, or eight sliders of your own."""
from tkinter import TclError

import customtkinter as ctk

from . import equalizer
from .ui_common import fit_geometry, set_if_changed, set_window_icon

APPLY_AFTER = 250           # ms after the last slider move: every change restarts the sound for a moment


class EqualizerWindow(ctk.CTkToplevel):
    def __init__(self, music):
        """`music` is the MusicWindow: its apply_eq(gains) puts a setting on the sound (False: not possible)."""
        super().__init__(music)
        set_window_icon(self)
        self.music = music
        self.title("DISO • Ekolayzır")
        fit_geometry(self, 620, 430)
        self.minsize(560, 400)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))
        head.columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="🎛 Ekolayzır", font=ctk.CTkFont(size=22, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="w")
        self.preset_menu = ctk.CTkOptionMenu(head, values=list(equalizer.PRESETS), width=170, command=self._preset)
        self.preset_menu.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(self, text="Hazır bir ayar seç ya da kaydırıcılarla kendin ayarla. Düz bırakırsan ses hiç "
                                "değişmez.", text_color="gray", anchor="w", justify="left", wraplength=560).grid(
            row=1, column=0, sticky="ew", padx=20)

        bands = ctk.CTkFrame(self)
        bands.grid(row=2, column=0, sticky="nsew", padx=16, pady=10)
        self.sliders, self.values = [], []
        for i, label in enumerate(equalizer.LABELS):
            bands.columnconfigure(i, weight=1)
            value = ctk.CTkLabel(bands, text="0", width=40, font=ctk.CTkFont(weight="bold"))
            value.grid(row=0, column=i, pady=(10, 0))
            slider = ctk.CTkSlider(bands, orientation="vertical", from_=-equalizer.LIMIT, to=equalizer.LIMIT,
                                   number_of_steps=equalizer.LIMIT * 2, height=180,
                                   command=lambda v, i=i: self._moved(i, v))
            slider.grid(row=1, column=i, pady=6)
            ctk.CTkLabel(bands, text=label, text_color="gray").grid(row=2, column=i, pady=(0, 10))
            self.sliders.append(slider)
            self.values.append(value)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 14))
        foot.columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(foot, text="", text_color="gray", anchor="w", justify="left", wraplength=380)
        self.status.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(foot, text="Sıfırla", width=90, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=lambda: self._preset(equalizer.FLAT)).grid(
            row=0, column=1, padx=6)
        ctk.CTkButton(foot, text="Kapat", width=90, command=self.destroy).grid(row=0, column=2)
        self.bind("<Escape>", lambda e: self.destroy())
        self._pending = None
        self.gains = equalizer.clean(music.store.state.get("eq"))
        self._show(self.gains)

    # ------------------------------------------------------------------ showing
    def _show(self, gains):
        for slider, value, g in zip(self.sliders, self.values, gains):
            slider.set(g)
            set_if_changed(value, text=f"{g:+d}" if g else "0")
        name = equalizer.preset_of(gains)
        if name == equalizer.CUSTOM:
            self.preset_menu.configure(values=list(equalizer.PRESETS) + [equalizer.CUSTOM])
        self.preset_menu.set(name)
        set_if_changed(self.status, text="Ses olduğu gibi çalıyor" if equalizer.is_flat(gains)
                       else "Ekolayzır açık")

    # ------------------------------------------------------------------ changing
    def _preset(self, name):
        self.preset_menu.configure(values=list(equalizer.PRESETS))
        self.gains = list(equalizer.PRESETS.get(name, equalizer.PRESETS[equalizer.FLAT]))
        self._show(self.gains)
        self.apply()

    def _moved(self, i, value):
        self.gains[i] = int(round(value))
        self._show(self.gains)
        if self._pending is not None:
            self.after_cancel(self._pending)
        self._pending = self.after(APPLY_AFTER, self.apply)

    def apply(self):
        self._pending = None
        try:
            if not self.music.apply_eq(self.gains):
                set_if_changed(self.status, text="Ekolayzır bu bilgisayarda çalışmıyor: ses çıkışı açılamadı")
        except TclError:
            pass
