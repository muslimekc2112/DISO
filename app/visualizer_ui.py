"""🌈 The visualizer window: the playing song as moving bars, a wave or a ring, in a colour theme, with a
background that glows with the beat and peaks that fall slowly. F11 / double click: full screen.

It draws ~30 times a second from the analysis (visualizer.Analyzer) at the player's position, reusing its
canvas items (only their coordinates and colours change), so it stays light."""
import math
import os
import tkinter as tk

import customtkinter as ctk

from . import lyrics, tooltip, visualizer
from .player import artist_and_title
from .ui_common import fit_geometry, set_if_changed, set_window_icon

STYLES = ["Çubuklar", "Dalga", "Halka"]
FRAME_MS = 33
FALL = 0.80                 # how fast a band falls back (attack is at once)
PEAK_FALL = 0.012           # the falling peak line, per frame


class VisualizerWindow(ctk.CTkToplevel):
    def __init__(self, music, analyzer=None):
        super().__init__(music)
        set_window_icon(self)
        self.music = music
        self.analyzer = analyzer or visualizer.Analyzer()
        self.title("DISO • Görselleştirici")
        fit_geometry(self, 900, 560)
        self.minsize(480, 320)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        state = music.store.state
        self.style = state.get("vis_style") if state.get("vis_style") in STYLES else STYLES[0]
        self.palette_name = state.get("vis_palette") if state.get("vis_palette") in visualizer.PALETTES else "Mor"
        self.show_lyrics = bool(state.get("vis_lyrics", True))
        self._lyrics_for = (None, None)              # (path, file time) of the lyrics in self._lyrics
        self._lyrics = None

        self.bar = ctk.CTkFrame(self, fg_color="transparent")
        self.bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        self.bar.columnconfigure(0, weight=1)
        self.song_label = ctk.CTkLabel(self.bar, text="", anchor="w", font=ctk.CTkFont(size=15, weight="bold"))
        self.song_label.grid(row=0, column=0, sticky="ew")
        self.style_switch = ctk.CTkSegmentedButton(self.bar, values=STYLES, command=self.set_style)
        self.style_switch.set(self.style)
        self.style_switch.grid(row=0, column=1, padx=6)
        self.palette_menu = ctk.CTkOptionMenu(self.bar, values=list(visualizer.PALETTES), width=130,
                                              command=self.set_palette)
        self.palette_menu.set(self.palette_name)
        self.palette_menu.grid(row=0, column=2, padx=6)
        self.lyrics_btn = ctk.CTkButton(self.bar, text="🎤", width=36, command=lambda: self.set_lyrics(not self.show_lyrics))
        tooltip.set(self.lyrics_btn, "Şarkıyla akan sözleri göster / gizle")
        self.lyrics_btn.grid(row=0, column=3, padx=(0, 6))
        self.full_btn = ctk.CTkButton(self.bar, text="⛶", width=36, command=self.toggle_full)
        self.full_btn.grid(row=0, column=4)

        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#0b0710")
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda e: self._rebuild())
        self.canvas.bind("<Double-Button-1>", lambda e: self.toggle_full())
        self.bind("<F11>", lambda e: self.toggle_full())
        self.bind("<Escape>", lambda e: self.toggle_full() if self.full else self.destroy())

        self.levels = [0.0] * visualizer.BANDS
        self.peaks = [0.0] * visualizer.BANDS
        self.glow = 0.0
        self.full = False
        self.items = {}
        self.path = None
        self._job = None
        self._rebuild()
        self.set_lyrics(self.show_lyrics)
        self._frame()

    # ------------------------------------------------------------------ choices
    @property
    def palette(self):
        return visualizer.PALETTES[self.palette_name]

    def set_style(self, style):
        self.style = style if style in STYLES else STYLES[0]
        self.style_switch.set(self.style)
        self.music.store.set_state(vis_style=self.style)
        self._rebuild()

    def set_palette(self, name):
        self.palette_name = name if name in visualizer.PALETTES else "Mor"
        self.palette_menu.set(self.palette_name)
        self.music.store.set_state(vis_palette=self.palette_name)
        self._rebuild()

    def set_lyrics(self, on):
        """🎤 The song's lyrics flowing with it, over the picture."""
        self.show_lyrics = bool(on)
        self.music.store.set_state(vis_lyrics=self.show_lyrics)
        self.lyrics_btn.configure(fg_color=self.full_btn.cget("fg_color") if self.show_lyrics else "transparent",
                                  border_width=0 if self.show_lyrics else 1)
        if not self.show_lyrics:
            for key in ("lyr_prev", "lyr_now", "lyr_next", "lyr_shadow"):
                self.canvas.itemconfigure(self.items[key], text="")

    def _lines(self, path):
        """The synced lyrics of the song (read again when its .lrc changes: written by hand, found)."""
        try:
            stamp = os.path.getmtime(lyrics.lyrics_path(path))
        except OSError:
            stamp = None
        if self._lyrics_for != (path, stamp):
            self._lyrics_for = (path, stamp)
            data = lyrics.load(path) if stamp is not None else None
            self._lyrics = data["synced"] if data and data["synced"] else None
            if stamp is None and path:                      # no lyrics yet: the player looks them up
                track = self.music.controller.current_track()
                finder = getattr(self.music, "find_lyrics", None)
                if track and finder and path not in getattr(self.music, "_lyrics_asked", set()):
                    try:
                        finder(track)
                    except Exception:  # noqa: BLE001 - only a wish
                        pass
        return self._lyrics

    def _draw_lyrics(self):
        c = self.canvas
        keys = ("lyr_prev", "lyr_now", "lyr_next", "lyr_shadow")
        lines = self._lines(self.path) if self.show_lyrics and self.path else None
        if not lines:
            for key in keys:
                c.itemconfigure(self.items[key], text="")
            return
        ms = self.music.controller.position_ms()
        i = lyrics.line_at(lines, ms + 250)                  # a little early: easier to sing along
        now = lines[i][1] if i >= 0 else ""
        before = lines[i - 1][1] if i >= 1 else ""
        after = lines[i + 1][1] if i + 1 < len(lines) else (lines[0][1] if i < 0 else "")
        w, h = self._size()
        size = max(14, min(34, int(h / 15)))
        y = h - size * 2.6
        width = w * 0.9
        c.coords(self.items["lyr_now"], w / 2, y)
        c.coords(self.items["lyr_shadow"], w / 2 + 2, y + 2)
        c.coords(self.items["lyr_prev"], w / 2, y - size * 1.7)
        c.coords(self.items["lyr_next"], w / 2, y + size * 1.6)
        c.itemconfigure(self.items["lyr_now"], text=now or "♪", font=("Segoe UI", size, "bold"), width=width)
        c.itemconfigure(self.items["lyr_shadow"], text=now or "♪", font=("Segoe UI", size, "bold"), width=width)
        c.itemconfigure(self.items["lyr_prev"], text=before, font=("Segoe UI", int(size * 0.6)), width=width)
        c.itemconfigure(self.items["lyr_next"], text=after, font=("Segoe UI", int(size * 0.6)), width=width)

    def toggle_full(self):
        self.full = not self.full
        try:
            self.attributes("-fullscreen", self.full)
        except tk.TclError:
            self.full = False
        if self.full:
            self.bar.grid_remove()
        else:
            self.bar.grid()

    # ------------------------------------------------------------------ the picture
    def _size(self):
        return max(10, self.canvas.winfo_width()), max(10, self.canvas.winfo_height())

    def _rebuild(self):
        c = self.canvas
        c.delete("all")
        w, h = self._size()
        p = self.palette
        n = visualizer.BANDS
        self.items = {"text": c.create_text(w / 2, h / 2, text="", fill="#bbbbbb", font=("Segoe UI", 14))}
        if self.style == "Çubuklar":
            self.items["bars"] = [c.create_rectangle(0, 0, 0, 0, outline="", fill=p[2]) for _ in range(n)]
            self.items["shadows"] = [c.create_rectangle(0, 0, 0, 0, outline="", fill=p[1], stipple="gray25")
                                     for _ in range(n)]
            self.items["peaks"] = [c.create_rectangle(0, 0, 0, 0, outline="", fill=p[4]) for _ in range(n)]
        elif self.style == "Dalga":
            flat = [0, h / 2, w, h / 2, w, h / 2, 0, h / 2]
            self.items["outer"] = c.create_polygon(*flat, smooth=True, fill=p[1], outline=p[3], width=2)
            self.items["inner"] = c.create_polygon(*flat, smooth=True, fill=p[2], outline=p[4], width=1)
            self.items["line"] = c.create_line(0, h / 2, w, h / 2, fill=p[4], width=1)
        else:
            self.items["rays"] = [c.create_line(0, 0, 0, 0, fill=p[2], width=3, capstyle="round")
                                  for _ in range(n * 2)]
            self.items["core"] = c.create_oval(0, 0, 0, 0, outline=p[3], width=3, fill=p[0])
            self.items["title"] = c.create_text(w / 2, h / 2, text="", fill="#ffffff", font=("Segoe UI", 12, "bold"),
                                                width=10)
        self.items["lyr_prev"] = c.create_text(0, 0, text="", fill="#9a8aa6", justify="center")
        self.items["lyr_next"] = c.create_text(0, 0, text="", fill="#9a8aa6", justify="center")
        self.items["lyr_shadow"] = c.create_text(0, 0, text="", fill="#000000", justify="center")
        self.items["lyr_now"] = c.create_text(0, 0, text="", fill="#ffffff", justify="center")
        c.tag_raise(self.items["text"])

    def _target(self):
        """What the bands should show now: the playing song's frame, nothing while paused / stopped."""
        ctl = self.music.controller
        path = ctl.current_path() if ctl.state != "stopped" else None
        if path != self.path:
            self.path = path
            track = ctl.current_track() or {}
            artist, title = artist_and_title(track) if track else ("", "")
            set_if_changed(self.song_label, text=(f"{artist} — {title}" if artist else title) or "")
            self._song = title or ""
        if not path:
            return None, "Bir şarkı çal 🎵"
        self.analyzer.want(path)
        result = self.analyzer.get(path)
        if result is None:
            return None, "Şarkı çözümleniyor…" if self.analyzer.busy(path) else ""
        if ctl.state != "playing":
            return None, ""
        return visualizer.frame_at(result, ctl.position_ms()), ""

    def step(self):
        """One frame: move the levels towards the target and draw (tests call it directly)."""
        target, message = self._target()
        bands, loud = target if target else ([0.0] * visualizer.BANDS, 0.0)
        for i, v in enumerate(bands):
            self.levels[i] = v if v > self.levels[i] else self.levels[i] * FALL
            self.peaks[i] = max(self.levels[i], self.peaks[i] - PEAK_FALL)
        self.glow = max(loud, self.glow * 0.9)
        self.canvas.itemconfigure(self.items["text"], text=message)
        self.canvas.configure(bg=visualizer.blend(["#0b0710", self.palette[0], self.palette[1]], self.glow * 0.55))
        getattr(self, "_draw_" + {"Çubuklar": "bars", "Dalga": "wave", "Halka": "ring"}[self.style])()
        self._draw_lyrics()

    def _draw_bars(self):
        c, p = self.canvas, self.palette
        w, h = self._size()
        n = len(self.levels)
        gap = 2
        width = (w - gap * (n + 1)) / n
        base = h * 0.78
        for i, v in enumerate(self.levels):
            x0 = gap + i * (width + gap)
            top = base - v * base * 0.92
            c.coords(self.items["bars"][i], x0, top, x0 + width, base)
            c.itemconfigure(self.items["bars"][i], fill=visualizer.blend(p, 0.25 + 0.75 * v))
            c.coords(self.items["shadows"][i], x0, base + 2, x0 + width, base + 2 + (base - top) * 0.25)
            peak = base - self.peaks[i] * base * 0.92
            c.coords(self.items["peaks"][i], x0, peak - 3, x0 + width, peak)

    def _draw_wave(self):
        c = self.canvas
        w, h = self._size()
        mid = h / 2
        n = len(self.levels)
        xs = [w * i / (n - 1) for i in range(n)]
        top = [(x, mid - v * mid * 0.85) for x, v in zip(xs, self.levels)]
        inner_top = [(x, mid - v * mid * 0.5) for x, v in zip(xs, self.levels)]

        def shape(points):
            flat = [0, mid]
            for x, y in points:
                flat += [x, y]
            flat += [w, mid]
            for x, y in reversed(points):
                flat += [x, 2 * mid - y]
            return flat
        c.coords(self.items["outer"], *shape(top))
        c.coords(self.items["inner"], *shape(inner_top))
        c.coords(self.items["line"], 0, mid, w, mid)

    def _draw_ring(self):
        c, p = self.canvas, self.palette
        w, h = self._size()
        cx, cy = w / 2, h / 2
        size = min(w, h)
        core = size * 0.18 * (1 + 0.18 * self.glow)
        n = len(self.levels)
        for k in range(n * 2):                              # the right half, then the left mirrored
            i = k if k < n else 2 * n - 1 - k
            angle = math.pi * k / n - math.pi / 2
            v = self.levels[i]
            r1, r2 = core + 4, core + 4 + v * size * 0.3
            c.coords(self.items["rays"][k], cx + r1 * math.cos(angle), cy + r1 * math.sin(angle),
                     cx + r2 * math.cos(angle), cy + r2 * math.sin(angle))
            c.itemconfigure(self.items["rays"][k], fill=visualizer.blend(p, 0.3 + 0.7 * v))
        c.coords(self.items["core"], cx - core, cy - core, cx + core, cy + core)
        c.coords(self.items["title"], cx, cy)
        c.itemconfigure(self.items["title"], text=getattr(self, "_song", ""), width=max(10, core * 1.7))

    def _frame(self):
        try:
            if not self.winfo_exists():
                return
            self.step()
        except tk.TclError:
            return
        self._job = self.after(FRAME_MS, self._frame)

    def destroy(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
        super().destroy()
