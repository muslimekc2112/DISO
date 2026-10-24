"""📊 Listening statistics of the music player: this month, this year or all the time — how long, the most
played songs and artists, the hours of the day and the longest run of days (PlaylistStore.summary)."""
import datetime
import time
import tkinter as tk

import customtkinter as ctk

from .ui_common import fit_geometry, set_if_changed, set_window_icon

PERIODS = ["Bu ay", "Bu yıl", "Tüm zamanlar"]
TOP_SONGS = 10
TOP_ARTISTS = 5


def period_start(name, now=None) -> float:
    now = datetime.datetime.fromtimestamp(now or time.time())
    if name == "Bu ay":
        return datetime.datetime(now.year, now.month, 1).timestamp()
    if name == "Bu yıl":
        return datetime.datetime(now.year, 1, 1).timestamp()
    return 0.0


def duration_text(ms) -> str:
    minutes = int(ms // 60000)
    if minutes >= 60:
        return f"{minutes // 60} sa {minutes % 60} dk"
    return f"{minutes} dk"


def _themed(color):
    """One colour of a (light, dark) customtkinter pair, for the current appearance."""
    if isinstance(color, (list, tuple)):
        return color[0] if ctk.get_appearance_mode() == "Light" else color[1]
    return color if color != "transparent" else "gray20"


def _accent():
    return _themed(ctk.ThemeManager.theme["CTkButton"]["fg_color"])


class StatsWindow(ctk.CTkToplevel):
    def __init__(self, music, store):
        super().__init__(music)
        set_window_icon(self)
        self.music, self.store = music, store
        self.title("DISO • Dinleme istatistiklerim")
        fit_geometry(self, 620, 720)
        self.minsize(520, 520)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        head.columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="📊 Dinleme istatistiklerim", font=ctk.CTkFont(size=22, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="w")
        self.period = ctk.CTkSegmentedButton(head, values=PERIODS, command=lambda v: self.show())
        self.period.set(PERIODS[0])
        self.period.grid(row=0, column=1, sticky="e")
        self.cards = ctk.CTkFrame(self, fg_color="transparent")
        self.cards.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 4))
        self.big = {}
        for i, key in enumerate(("time", "plays", "artists", "streak")):
            self.cards.columnconfigure(i, weight=1)
            card = ctk.CTkFrame(self.cards, corner_radius=12)
            card.grid(row=0, column=i, sticky="ew", padx=4)
            value = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=20, weight="bold"))
            value.pack(padx=8, pady=(10, 0))
            label = ctk.CTkLabel(card, text="", text_color="gray", font=ctk.CTkFont(size=11))
            label.pack(padx=8, pady=(0, 10))
            self.big[key] = (value, label)
        self.body = ctk.CTkScrollableFrame(self)
        self.body.grid(row=2, column=0, sticky="nsew", padx=16, pady=(6, 14))
        self.body.columnconfigure(0, weight=1)
        self.bind("<Escape>", lambda e: self.destroy())
        self.data = None
        self.show()

    # ------------------------------------------------------------------ filling
    def show(self):
        since = period_start(self.period.get())
        self.data = d = self.store.summary(since)
        texts = {"time": (duration_text(d["ms"]), "dinledin"), "plays": (str(d["plays"]), "dinleme"),
                 "artists": (str(len(d["artists"])), "sanatçı"), "streak": (f"{d['streak']} gün", "üst üste")}
        for key, (value, label) in self.big.items():
            set_if_changed(value, text=texts[key][0])
            set_if_changed(label, text=texts[key][1])
        for w in self.body.winfo_children():
            w.destroy()
        if not d["plays"]:
            ctk.CTkLabel(self.body, text="🎧\n\nBu dönemde henüz dinleme yok.\nBiraz müzik dinle, burası dolsun.",
                         text_color="gray", justify="center").grid(row=0, column=0, pady=60)
            return
        row = self._section(0, "🎵 En çok dinlediğin şarkılar")
        top = d["songs"][:TOP_SONGS]
        most = top[0][2] if top else 1
        for i, (title, artist, n) in enumerate(top, start=1):
            row = self._bar_row(row, f"{i}.  {title}", artist, n, most, f"{n} kez")
        if d["artists"]:
            row = self._section(row, "🎤 En sevdiğin sanatçılar")
            arts = d["artists"][:TOP_ARTISTS]
            most = arts[0][1]
            for i, (artist, n, ms) in enumerate(arts, start=1):
                row = self._bar_row(row, f"{i}.  {artist}", duration_text(ms) if ms else "", n, most, f"{n} kez")
        if any(d["hours"]):
            row = self._section(row, "🕒 Günün hangi saatinde dinliyorsun")
            peak = max(range(24), key=lambda h: d["hours"][h])
            ctk.CTkLabel(self.body, text=f"En çok {peak:02d}:00 ile {(peak + 1) % 24:02d}:00 arası", anchor="w",
                         text_color="gray").grid(row=row, column=0, sticky="ew", padx=8)
            self.hours_canvas = self._hours(row + 1, d["hours"], peak)

    def _section(self, row, title):
        ctk.CTkLabel(self.body, text=title, font=ctk.CTkFont(size=15, weight="bold"), anchor="w").grid(
            row=row, column=0, sticky="ew", padx=8, pady=(14, 4))
        return row + 1

    def _bar_row(self, row, name, sub, n, most, count):
        line = ctk.CTkFrame(self.body, fg_color="transparent")
        line.grid(row=row, column=0, sticky="ew", padx=8, pady=3)
        line.columnconfigure(0, weight=1)
        ctk.CTkLabel(line, text=name, anchor="w", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(line, text=count, text_color="gray").grid(row=0, column=1, sticky="e")
        if sub:
            ctk.CTkLabel(line, text=sub, anchor="w", text_color="gray", font=ctk.CTkFont(size=11)).grid(
                row=1, column=0, sticky="ew")
        bar = ctk.CTkProgressBar(line, height=8)
        bar.set(n / most if most else 0)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        return row + 1

    def _hours(self, row, hours, peak):
        width, height = 540, 110
        canvas = tk.Canvas(self.body, width=width, height=height, highlightthickness=0,
                           bg=_themed(self.body.cget("fg_color")))
        canvas.grid(row=row, column=0, sticky="ew", padx=8, pady=(4, 8))
        most = max(hours) or 1
        step = width / 24
        accent = _accent()
        for h, n in enumerate(hours):
            bar = (height - 22) * n / most
            x0 = h * step + 2
            canvas.create_rectangle(x0, height - 18 - bar, x0 + step - 4, height - 18,
                                    fill=accent if h == peak else "#8a7a96", outline="")
            if h % 3 == 0:
                canvas.create_text(x0 + (step - 4) / 2, height - 8, text=f"{h:02d}", fill="gray", font=("Segoe UI", 8))
        return canvas
