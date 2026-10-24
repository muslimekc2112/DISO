"""🌌 The visualizer window: the playing song as moving bars, a wave or a ring, in a colour theme (or in the
colours of the song's cover), over a soft glowing background that breathes with the beat. In the ring, the
cover itself sits in the middle, round, and swells a little on every beat. Below the picture: ⏮ ⏪ ⏯ ⏩ ⏭ and
where the song is. F11 / double click: full screen (the controls come back when the mouse moves).

It draws ~30 times a second from the analysis (visualizer.Analyzer) at the player's position, reusing its
canvas items (only their coordinates and colours change) and pictures made in advance, so it stays light."""
import math
import os
import tkinter as tk

import customtkinter as ctk

from . import ambient, lyrics, tooltip, visualizer
from .player import artist_and_title
from .ui_common import fill_monitor, fit_geometry, set_if_changed, set_window_icon

STYLES = ["Çubuklar", "Dalga", "Halka"]
AUTO = "🎨 Kapaktan"                 # the palette made from the playing song's cover
FRAME_MS = 33
FALL = 0.80                 # how fast a band falls back (attack is at once)
PEAK_FALL = 0.012           # the falling peak line, per frame
GLOWS = 3                   # background pictures from calm to bright: the beat picks one
SWELLS = 7                  # sizes of the cover in the ring, from rest to the loudest beat
SWELL = 0.12                # ... the biggest is this much larger
SPIN = 0.0025               # the ring turns slowly (radians per frame)
HIDE_AFTER = 2500           # ms: in full screen the controls go away when the mouse rests
SEEK_STEP = 5000


def icon_image(px=20):
    """The visualizer's own little picture (for its button): five rounded bars in the program's colours on a
    soft round glow. A CTkImage, None without Pillow."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    scale = 8
    size = px * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    colours = ["#7B3FA0", "#B35EC9", "#F2545B", "#F9A03F", "#FFD166"]
    heights = (0.42, 0.72, 0.95, 0.64, 0.36)
    width = size / 7.2
    gap = (size - 5 * width) / 6
    for i, (h, colour) in enumerate(zip(heights, colours)):
        x0 = gap + i * (width + gap)
        top = size / 2 - h * size / 2
        draw.rounded_rectangle((x0, top, x0 + width, size - top), radius=width / 2, fill=colour)
    small = img.resize((px * 2, px * 2), Image.LANCZOS)
    return ctk.CTkImage(light_image=small, dark_image=small, size=(px, px))


def round_picture(path, side):
    """The picture cut to a circle of `side` px (transparent around it), with a thin light rim; None if it
    cannot be read."""
    try:
        from PIL import Image, ImageDraw
        with Image.open(path) as im:
            im = im.convert("RGB")
            square = min(im.size)
            left, top = (im.width - square) // 2, (im.height - square) // 2
            big = side * 3
            im = im.crop((left, top, left + square, top + square)).resize((big, big), Image.LANCZOS)
    except Exception:  # noqa: BLE001 - no picture: the ring has its plain core
        return None
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask)
    rim = ImageDraw.Draw(out)
    rim.ellipse((2, 2, big - 3, big - 3), outline=(255, 255, 255, 90), width=max(3, big // 90))
    return out.resize((side, side), Image.LANCZOS)


def glow_picture(width, height, palette, strength):
    """The background: dark at the edges, the palette's colour glowing from the middle (brighter with
    `strength` 0..1). Made small and stretched: smooth, and quick to make."""
    import numpy as np
    from PIL import Image
    w, h = max(8, width // 6), max(8, height // 6)
    ys, xs = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xs - w / 2) / (w / 2)) ** 2 + ((ys - h / 2) / (h / 2)) ** 2) / 1.42
    d = np.clip(d, 0, 1)
    edge = np.array(ambient._hex(ambient.mix("#000000", palette[0], 0.55)), dtype=np.float32)
    mid = np.array(ambient._hex(ambient.mix(palette[0], palette[2], 0.25 + 0.5 * strength)), dtype=np.float32)
    share = (1 - d) ** 1.6
    pixels = edge + (mid - edge) * share[..., None]
    img = Image.fromarray(pixels.astype(np.uint8), "RGB")
    return img.resize((max(1, width), max(1, height)), Image.BILINEAR)


class VisualizerWindow(ctk.CTkToplevel):
    def __init__(self, music, analyzer=None):
        super().__init__(music)
        set_window_icon(self)
        self.music = music
        self.analyzer = analyzer or getattr(music, "analyzer", None) or visualizer.Analyzer()
        if getattr(music, "analyzer", None) is None and analyzer is None:
            music.analyzer = self.analyzer                   # one analysis of a song for the window and the player
        self.title("DISO • Görselleştirici")
        fit_geometry(self, 960, 620)
        self.minsize(520, 380)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        state = music.store.state
        if not state.get("vis_auto_once"):                   # 1.2: the cover's colours are the new default
            music.store.set_state(vis_palette=AUTO, vis_auto_once=True)
        self.style = state.get("vis_style") if state.get("vis_style") in STYLES else STYLES[0]
        names = [AUTO] + list(visualizer.PALETTES)
        self.palette_name = state.get("vis_palette") if state.get("vis_palette") in names else AUTO
        self.show_lyrics = bool(state.get("vis_lyrics", True))
        self._lyrics_for = (None, None)              # (path, file time) of the lyrics in self._lyrics
        self._lyrics = None
        self._cover_jpg = None                       # the cover the pictures were made from
        self._cover_palette = None                   # its colours as a palette (AUTO)
        self._pictures = {}                          # what was made for the current size / colours
        self._made_for = None
        self._spin = 0.0
        self._hide_job = None
        self._tick = 0

        self.bar = ctk.CTkFrame(self, fg_color="transparent")
        self.bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 6))
        self.bar.columnconfigure(1, weight=1)
        self._icon = icon_image(26)
        ctk.CTkLabel(self.bar, text="", image=self._icon, width=30).grid(row=0, column=0, rowspan=2, padx=(0, 10))
        self.song_label = ctk.CTkLabel(self.bar, text="", anchor="w", font=ctk.CTkFont(size=16, weight="bold"))
        self.song_label.grid(row=0, column=1, sticky="ew")
        self.artist_label = ctk.CTkLabel(self.bar, text="", anchor="w", text_color="gray", height=18)
        self.artist_label.grid(row=1, column=1, sticky="ew")
        self.style_switch = ctk.CTkSegmentedButton(self.bar, values=STYLES, command=self.set_style)
        self.style_switch.set(self.style)
        self.style_switch.grid(row=0, column=2, rowspan=2, padx=6)
        self.palette_menu = ctk.CTkOptionMenu(self.bar, values=names, width=140, command=self.set_palette)
        self.palette_menu.set(self.palette_name)
        self.palette_menu.grid(row=0, column=3, rowspan=2, padx=6)
        self.lyrics_btn = ctk.CTkButton(self.bar, text="🎤", width=36, command=lambda: self.set_lyrics(not self.show_lyrics))
        tooltip.set(self.lyrics_btn, "Şarkıyla akan sözleri göster / gizle")
        self.lyrics_btn.grid(row=0, column=4, rowspan=2, padx=(0, 6))
        self.full_btn = ctk.CTkButton(self.bar, text="⛶", width=36, command=self.toggle_full)
        tooltip.set(self.full_btn, "Tam ekran (F11)")
        self.full_btn.grid(row=0, column=5, rowspan=2)

        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#0b0710")
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda e: self._rebuild())
        self.canvas.bind("<Double-Button-1>", lambda e: self.toggle_full())
        self.canvas.bind("<Motion>", lambda e: self._show_controls_for_a_while())
        self.bind("<F11>", lambda e: self.toggle_full())
        self.bind("<Escape>", lambda e: self.toggle_full() if self.full else self.destroy())
        self.bind("<space>", lambda e: self.music._toggle() or "break")
        for key, action in (("Right", "seek_forward"), ("Left", "seek_back"), ("Up", "volume_up"), ("Down", "volume_down")):
            self.bind(f"<{key}>", lambda e, k=key, a=action: self.music.tap(a, k) and "break")
        self.bind("<KeyRelease>", lambda e: self.music._on_key_release(e), add="+")

        self._build_controls()
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

    # ------------------------------------------------------------------ ⏮ ⏪ ⏯ ⏩ ⏭
    def _build_controls(self):
        box = self.controls = ctk.CTkFrame(self, fg_color="transparent")
        box.grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 10))
        box.columnconfigure(1, weight=1)
        self.pos_label = ctk.CTkLabel(box, text="0:00", width=44, text_color="gray")
        self.pos_label.grid(row=0, column=0)
        self.seek = ctk.CTkSlider(box, from_=0, to=1000, command=self._on_seek_drag)
        self.seek.set(0)
        self.seek.grid(row=0, column=1, sticky="ew", padx=6)
        self.seek.bind("<ButtonPress-1>", lambda e: setattr(self, "_dragging", True), add="+")
        self.seek.bind("<ButtonRelease-1>", self._on_seek_release, add="+")
        self._dragging = False
        self.len_label = ctk.CTkLabel(box, text="0:00", width=44, text_color="gray")
        self.len_label.grid(row=0, column=2)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.grid(row=1, column=0, columnspan=3, pady=(4, 0))
        m = self.music
        self.prev_btn = ctk.CTkButton(row, text="⏮", width=46, height=34, command=m._previous)
        self.back_btn = ctk.CTkButton(row, text="⏪ 5", width=56, height=34, command=lambda: m.seek_by(-SEEK_STEP))
        self.play_btn = ctk.CTkButton(row, text="▶", width=64, height=40, font=ctk.CTkFont(size=20),
                                      corner_radius=20, command=m._toggle)
        self.forward_btn = ctk.CTkButton(row, text="5 ⏩", width=56, height=34, command=lambda: m.seek_by(SEEK_STEP))
        self.next_btn = ctk.CTkButton(row, text="⏭", width=46, height=34, command=m._next)
        tooltip.set(self.prev_btn, "Önceki şarkı")
        tooltip.set(self.back_btn, "5 saniye geri  (←)")
        tooltip.set(self.play_btn, "Çal / duraklat  (Boşluk)")
        tooltip.set(self.forward_btn, "5 saniye ileri  (→)")
        tooltip.set(self.next_btn, "Sonraki şarkı")
        for col, b in enumerate((self.prev_btn, self.back_btn, self.play_btn, self.forward_btn, self.next_btn)):
            b.grid(row=0, column=col, padx=5)

    def _on_seek_drag(self, value):
        if self._dragging:
            from .music_ui import fmt_time
            set_if_changed(self.pos_label, text=fmt_time(self.music.controller.length_ms() * value / 1000))

    def _on_seek_release(self, event=None):
        self._dragging = False
        c = self.music.controller
        if c.state != "stopped" and c.length_ms():
            self.music._seek_ms(int(c.length_ms() * self.seek.get() / 1000))

    def _update_controls(self):
        from .music_ui import fmt_time
        c = self.music.controller
        set_if_changed(self.play_btn, text="⏸" if c.state == "playing" else "▶")
        if self._dragging:
            return
        length, at = c.length_ms(), c.position_ms()
        set_if_changed(self.pos_label, text=fmt_time(at))
        set_if_changed(self.len_label, text=fmt_time(length))
        value = int(at * 1000 / length) if length else 0
        if abs(self.seek.get() - value) >= 1:
            self.seek.set(value)

    def _show_controls_for_a_while(self):
        if not self.full:
            return
        if not self.controls.winfo_ismapped():
            self.controls.grid()
        if self._hide_job is not None:
            self.after_cancel(self._hide_job)
        self._hide_job = self.after(HIDE_AFTER, self._hide_controls)

    def _hide_controls(self):
        self._hide_job = None
        if self.full and not self._dragging:
            self.controls.grid_remove()

    # ------------------------------------------------------------------ choices
    @property
    def palette(self):
        if self.palette_name == AUTO:
            return self._cover_palette or visualizer.PALETTES["Mor"]
        return visualizer.PALETTES[self.palette_name]

    def set_style(self, style):
        self.style = style if style in STYLES else STYLES[0]
        self.style_switch.set(self.style)
        self.music.store.set_state(vis_style=self.style)
        self._rebuild()

    def set_palette(self, name):
        self.palette_name = name if name == AUTO or name in visualizer.PALETTES else AUTO
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
        if self.full:
            try:
                self._windowed = (self.state(), self.geometry())        # (to come back to exactly this)
            except tk.TclError:
                self._windowed = None
        try:
            self.attributes("-fullscreen", self.full)
        except tk.TclError:
            self.full = False
        if self.full:
            self.bar.grid_remove()
            self.controls.grid_remove()
            self.update_idletasks()
            fill_monitor(self)                                  # the whole monitor, not Tk's scaled idea of it
            self.after(80, lambda: self.full and fill_monitor(self))
        else:
            self.bar.grid()
            self.controls.grid()
            before = getattr(self, "_windowed", None)
            if before:
                try:
                    if before[0] == "zoomed":
                        self.state("zoomed")
                    else:
                        self.geometry(before[1])
                except tk.TclError:
                    pass

    # ------------------------------------------------------------------ the pictures made in advance
    def _size(self):
        return max(10, self.canvas.winfo_width()), max(10, self.canvas.winfo_height())

    def _core_radius(self):
        w, h = self._size()
        return min(w, h) * 0.2

    def _make_pictures(self):
        """The glowing backgrounds and the round cover in its sizes, for this size and these colours."""
        w, h = self._size()
        key = (w, h, tuple(self.palette), self._cover_jpg, self.style)
        if key == self._made_for:
            return
        self._made_for = key
        from PIL import ImageTk
        pictures = {"glow": []}
        try:
            for k in range(GLOWS):
                pictures["glow"].append(ImageTk.PhotoImage(glow_picture(w, h, self.palette, k / (GLOWS - 1)),
                                                           master=self.canvas))
        except Exception:  # noqa: BLE001 - without numpy / Pillow: the plain background colour
            pictures["glow"] = []
        pictures["cover"] = []
        if self.style == "Halka" and self._cover_jpg:
            base = int(self._core_radius() * 2)
            first = round_picture(self._cover_jpg, int(base * (1 + SWELL)))
            if first is not None:
                from PIL import Image
                for k in range(SWELLS):
                    side = max(8, int(base * (1 + SWELL * k / (SWELLS - 1))))
                    pictures["cover"].append(ImageTk.PhotoImage(first.resize((side, side), Image.LANCZOS),
                                                                master=self.canvas))
        self._pictures = pictures

    def _follow_cover(self):
        """The playing song's cover (as the music window has read it): the ring's middle and the AUTO colours."""
        covers = getattr(self.music, "_covers", {})
        jpg = covers.get(self.path) if self.path else None
        if jpg != self._cover_jpg:
            self._cover_jpg = jpg
            self._cover_palette = ambient.palette(ambient.cover_colours(jpg)) if jpg else None
            self._rebuild()

    # ------------------------------------------------------------------ the picture
    def _rebuild(self):
        c = self.canvas
        c.delete("all")
        self._made_for = None
        self._make_pictures()
        w, h = self._size()
        p = self.palette
        n = visualizer.BANDS
        glows = self._pictures.get("glow") or []
        self.items = {"bg": c.create_image(0, 0, anchor="nw", image=glows[0]) if glows else None}
        self.items["text"] = c.create_text(w / 2, h / 2, text="", fill="#d9d0e0", font=("Segoe UI", 15))
        if self.style == "Çubuklar":
            self.items["shadows"] = [c.create_line(0, 0, 0, 0, fill=p[1], width=4, capstyle="round",
                                                   stipple="gray25") for _ in range(n)]
            self.items["bars"] = [c.create_line(0, 0, 0, 0, fill=p[2], width=4, capstyle="round") for _ in range(n)]
            self.items["peaks"] = [c.create_line(0, 0, 0, 0, fill=p[4], width=3, capstyle="round") for _ in range(n)]
        elif self.style == "Dalga":
            flat = [0, h / 2, w, h / 2, w, h / 2, 0, h / 2]
            self.items["outer"] = c.create_polygon(*flat, smooth=True, fill=p[1], outline=p[3], width=2)
            self.items["inner"] = c.create_polygon(*flat, smooth=True, fill=p[2], outline=p[4], width=1)
            self.items["line"] = c.create_line(0, h / 2, w, h / 2, fill=p[4], width=1)
        else:
            self.items["halo"] = [c.create_oval(0, 0, 0, 0, outline=p[k], width=2) for k in (1, 2)]
            self.items["rays"] = [c.create_line(0, 0, 0, 0, fill=p[2], width=3, capstyle="round")
                                  for _ in range(n * 2)]
            self.items["core"] = c.create_oval(0, 0, 0, 0, outline=p[3], width=3, fill=p[0])
            covers = self._pictures.get("cover") or []
            self.items["cover"] = c.create_image(w / 2, h / 2, image=covers[0]) if covers else None
            self.items["title"] = c.create_text(w / 2, h / 2, text="", fill="#ffffff", font=("Segoe UI", 12, "bold"),
                                                width=10)
        self.items["lyr_prev"] = c.create_text(0, 0, text="", fill="#b5a8c0", justify="center")
        self.items["lyr_next"] = c.create_text(0, 0, text="", fill="#b5a8c0", justify="center")
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
            set_if_changed(self.song_label, text=title or "Görselleştirici")
            set_if_changed(self.artist_label, text=" • ".join(x for x in (artist, track.get("album")) if x) or " ")
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
        self._follow_cover()
        bands, loud = target if target else ([0.0] * visualizer.BANDS, 0.0)
        for i, v in enumerate(bands):
            self.levels[i] = v if v > self.levels[i] else self.levels[i] * FALL
            self.peaks[i] = max(self.levels[i], self.peaks[i] - PEAK_FALL)
        self.glow = max(loud, self.glow * 0.9)
        self.canvas.itemconfigure(self.items["text"], text=message)
        glows = self._pictures.get("glow") or []
        if glows and self.items.get("bg") is not None:
            which = min(len(glows) - 1, int(self.glow * len(glows)))
            if which != self.items.get("bg_shown"):
                self.items["bg_shown"] = which
                self.canvas.itemconfigure(self.items["bg"], image=glows[which])
        else:
            self.canvas.configure(bg=visualizer.blend(["#0b0710", self.palette[0], self.palette[1]], self.glow * 0.55))
        getattr(self, "_draw_" + {"Çubuklar": "bars", "Dalga": "wave", "Halka": "ring"}[self.style])()
        self._draw_lyrics()
        self._tick += 1
        if self._tick % 8 == 0:                                   # the controls: a few times a second is enough
            self._update_controls()

    def _draw_bars(self):
        c, p = self.canvas, self.palette
        w, h = self._size()
        n = len(self.levels)
        step = w / n
        width = max(2, step * 0.62)
        base = h * 0.74
        for i, v in enumerate(self.levels):
            x = step * (i + 0.5)
            top = base - max(v, 0.012) * base * 0.88
            c.coords(self.items["bars"][i], x, top, x, base)
            c.itemconfigure(self.items["bars"][i], fill=visualizer.blend(p, 0.25 + 0.75 * v), width=width)
            c.coords(self.items["shadows"][i], x, base + width, x, base + width + (base - top) * 0.3)
            c.itemconfigure(self.items["shadows"][i], width=width)
            peak = base - self.peaks[i] * base * 0.88 - width
            c.coords(self.items["peaks"][i], x, peak, x, peak - 1)
            c.itemconfigure(self.items["peaks"][i], width=max(2, width * 0.8))

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
        swell = min(1.0, self.glow)
        core = self._core_radius() * (1 + SWELL * swell)
        self._spin = (self._spin + SPIN * (1 + 2 * swell)) % (2 * math.pi)
        n = len(self.levels)
        for k in range(n * 2):                              # the right half, then the left mirrored
            i = k if k < n else 2 * n - 1 - k
            angle = math.pi * k / n - math.pi / 2 + self._spin
            v = self.levels[i]
            r1, r2 = core + 8, core + 8 + v * size * 0.26
            c.coords(self.items["rays"][k], cx + r1 * math.cos(angle), cy + r1 * math.sin(angle),
                     cx + r2 * math.cos(angle), cy + r2 * math.sin(angle))
            c.itemconfigure(self.items["rays"][k], fill=visualizer.blend(p, 0.3 + 0.7 * v))
        for k, item in enumerate(self.items["halo"]):          # rings that open up with the beat
            r = core + 4 + (k + 1) * size * 0.05 * (0.4 + swell)
            c.coords(item, cx - r, cy - r, cx + r, cy + r)
            c.itemconfigure(item, outline=visualizer.blend(p, 0.2 + 0.6 * swell * (1 - k * 0.4)))
        covers = self._pictures.get("cover") or []
        if covers and self.items.get("cover") is not None:
            c.coords(self.items["cover"], cx, cy)
            c.itemconfigure(self.items["cover"], image=covers[min(SWELLS - 1, int(swell * SWELLS))])
            c.coords(self.items["core"], cx - core - 2, cy - core - 2, cx + core + 2, cy + core + 2)
            c.itemconfigure(self.items["core"], fill="", outline=visualizer.blend(p, 0.6 + 0.4 * swell))
            c.itemconfigure(self.items["title"], text="")
            return
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
        for job in (self._job, self._hide_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        super().destroy()
