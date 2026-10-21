"""🎛 The equalizer window of the music player: a ready-made setting, three plain controls (Bas, Orta, Tiz)
or, under "Gelişmiş", the eight bands themselves."""
from tkinter import TclError

import customtkinter as ctk

from . import equalizer
from .ui_common import fit_geometry, set_if_changed, set_window_icon

APPLY_AFTER = 250           # ms after the last slider move: dragging changes the sound once, not at every step
SIZES = {False: (560, 420), True: (640, 640)}      # simple / with "Gelişmiş"


def _db(value) -> str:
    return f"{value:+d} dB" if value else "0 dB"


class EqualizerWindow(ctk.CTkToplevel):
    def __init__(self, music):
        """`music` is the MusicWindow: its apply_eq(gains) puts a setting on the sound (False: not possible)."""
        super().__init__(music)
        set_window_icon(self)
        self.music = music
        self.title("DISO • Ekolayzır")
        self.advanced = bool(music.store.state.get("eq_advanced"))
        fit_geometry(self, *SIZES[self.advanced])
        self.minsize(520, 400)
        self.columnconfigure(0, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))
        head.columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="🎛 Ekolayzır", font=ctk.CTkFont(size=22, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="w")
        self.preset_menu = ctk.CTkOptionMenu(head, values=list(equalizer.PRESETS), width=170, command=self._preset)
        self.preset_menu.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(self, text="Hazır bir ayar seç ya da kaydırıcılarla kendin ayarla. Düz bırakırsan ses hiç "
                                "değişmez.", text_color="gray", anchor="w", justify="left", wraplength=500).grid(
            row=1, column=0, sticky="ew", padx=20)

        # the simple view: Bas, Orta, Tiz, each with what it changes
        simple = ctk.CTkFrame(self)
        simple.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 4))
        simple.columnconfigure(1, weight=1)
        self.simple_sliders, self.simple_values = [], []
        for i, (name, hint, _) in enumerate(equalizer.SIMPLE):
            words = ctk.CTkFrame(simple, fg_color="transparent")
            words.grid(row=i, column=0, sticky="w", padx=(14, 10), pady=8)
            ctk.CTkLabel(words, text=name, font=ctk.CTkFont(size=15, weight="bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(words, text=hint, text_color="gray", anchor="w", font=ctk.CTkFont(size=11)).pack(anchor="w")
            slider = ctk.CTkSlider(simple, from_=-equalizer.LIMIT, to=equalizer.LIMIT,
                                   number_of_steps=equalizer.LIMIT * 2, command=lambda v, i=i: self._moved_simple(i, v))
            slider.grid(row=i, column=1, sticky="ew", padx=6)
            value = ctk.CTkLabel(simple, text="0 dB", width=56, font=ctk.CTkFont(weight="bold"))
            value.grid(row=i, column=2, padx=(4, 14))
            self.simple_sliders.append(slider)
            self.simple_values.append(value)

        self.advanced_var = ctk.BooleanVar(value=self.advanced)
        ctk.CTkSwitch(self, text="Gelişmiş: frekans bantlarını tek tek ayarla", variable=self.advanced_var,
                      command=self._toggle_advanced).grid(row=3, column=0, sticky="w", padx=22, pady=(6, 0))

        # "Gelişmiş": the eight bands
        self.bands = ctk.CTkFrame(self)
        self.sliders, self.values = [], []
        for i, label in enumerate(equalizer.LABELS):
            self.bands.columnconfigure(i, weight=1)
            value = ctk.CTkLabel(self.bands, text="0", width=40, font=ctk.CTkFont(weight="bold"))
            value.grid(row=0, column=i, pady=(10, 0))
            slider = ctk.CTkSlider(self.bands, orientation="vertical", from_=-equalizer.LIMIT, to=equalizer.LIMIT,
                                   number_of_steps=equalizer.LIMIT * 2, height=160,
                                   command=lambda v, i=i: self._moved(i, v))
            slider.grid(row=1, column=i, pady=6)
            ctk.CTkLabel(self.bands, text=label, text_color="gray").grid(row=2, column=i, pady=(0, 10))
            self.sliders.append(slider)
            self.values.append(value)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=5, column=0, sticky="ew", padx=20, pady=(8, 14))
        foot.columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(foot, text="", text_color="gray", anchor="w", justify="left", wraplength=340)
        self.status.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(foot, text="Sıfırla", width=90, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=lambda: self._preset(equalizer.FLAT)).grid(
            row=0, column=1, padx=6)
        ctk.CTkButton(foot, text="Kapat", width=90, command=self.destroy).grid(row=0, column=2)
        self.bind("<Escape>", lambda e: self.destroy())
        self._pending = None
        self.gains = equalizer.clean(music.store.state.get("eq"))
        self._place_bands()
        self._show(self.gains)

    # ------------------------------------------------------------------ showing
    def _place_bands(self):
        if self.advanced:
            self.bands.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 0))
        else:
            self.bands.grid_remove()

    def _toggle_advanced(self):
        self.advanced = bool(self.advanced_var.get())
        self.music.store.state["eq_advanced"] = self.advanced
        self._place_bands()
        try:
            w, h = SIZES[self.advanced]
            self.geometry(f"{max(w, self.winfo_width())}x{h}")
        except TclError:
            pass

    def _show(self, gains):
        for slider, value, g in zip(self.sliders, self.values, gains):
            slider.set(g)
            set_if_changed(value, text=f"{g:+d}" if g else "0")
        for slider, value, g in zip(self.simple_sliders, self.simple_values, equalizer.simple_values(gains)):
            slider.set(g)
            set_if_changed(value, text=_db(g))
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
        self._changed()

    def _moved_simple(self, which, value):
        self.gains = equalizer.set_simple(self.gains, which, int(round(value)))
        self._changed()

    def _changed(self):
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
