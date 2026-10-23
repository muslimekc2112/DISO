"""〰 The song's wave as its progress bar: a bar for each moment, tall where it is loud. What has played is in
the accent colour, the rest is grey; hovering shows the time there, a click (or a drag) jumps there.

The wave comes from the visualizer's analysis (the loudness of every 1/30 s), so it costs nothing more than
reading it once. Until it is known a thin line is shown, like an ordinary slider. It has the slider's set() /
get() (0..1000) and calls `command(value)` while it is dragged and `on_release()` when the mouse lets go."""
import tkinter as tk

import customtkinter as ctk

BAR_PX = 4                  # the width of a bar and the room after it, in screen pixels (before scaling)
HEIGHT = 40


def peaks(levels, count):
    """`count` heights (0..1) from the loudness of every frame: the loudest of each part, a little lifted so
    quiet parts still show."""
    n = len(levels)
    if not n or count <= 0:
        return []
    top = max(1, max(int(v) for v in levels))
    out = []
    for i in range(count):
        a, b = i * n // count, max(i * n // count + 1, (i + 1) * n // count)
        part = levels[a:b]
        v = max(int(x) for x in part) / top if len(part) else 0.0
        out.append(0.12 + 0.88 * v ** 0.75)
    return out


def _themed(pair):
    if isinstance(pair, (tuple, list)):
        return pair[0] if ctk.get_appearance_mode() == "Light" else pair[1]
    return pair


class WaveBar(ctk.CTkFrame):
    def __init__(self, master, command=None, on_release=None, height=HEIGHT, **kw):
        super().__init__(master, fg_color="transparent", height=height, **kw)
        self.command, self.on_release = command, on_release
        self._value = 0.0                     # 0..1000
        self._levels = None                   # the song's loudness per frame (None: not known yet)
        self._heights = []
        self._bars = []
        self._played = -1                     # bars up to this one are drawn as played
        self._hover = None
        self.dragging = False
        self.length_ms = 0                    # for the time shown while hovering
        self.canvas = tk.Canvas(self, height=self._apply_widget_scaling(height), highlightthickness=0, bd=0,
                                cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._rebuild())
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Motion>", self._move)
        self.canvas.bind("<Leave>", lambda e: self._leave())
        self._paint_background()

    # ------------------------------------------------------------------ the slider's API
    def set(self, value):
        self._value = max(0.0, min(1000.0, float(value)))
        self._show_progress()

    def get(self):
        return self._value

    def set_levels(self, levels):
        """The song's loudness per frame (None / [] for a song not analysed yet: a plain line)."""
        levels = None if levels is None or len(levels) == 0 else levels
        if levels is self._levels:
            return
        self._levels = levels
        self._rebuild()

    # ------------------------------------------------------------------ colours
    def _colours(self):
        theme = ctk.ThemeManager.theme
        slider = theme.get("CTkSlider", {})
        played = _themed(slider.get("progress_color") or theme["CTkButton"]["fg_color"])
        rest = _themed(slider.get("fg_color") or "gray50")
        if not (isinstance(played, str) and played) or played == "transparent":
            played = _themed(theme["CTkButton"]["fg_color"])
        return played, rest, _themed(slider.get("button_hover_color") or played)

    def _paint_background(self):
        bg = self._apply_appearance_mode(self._bg_color) if self._fg_color == "transparent" \
            else self._apply_appearance_mode(self._fg_color)
        try:
            self.canvas.configure(bg=bg)
        except tk.TclError:
            pass

    def _draw(self, no_color_updates=False):
        """customtkinter calls this when the colour behind it changes (the player's block glowing with the
        music, a theme switch): the canvas follows."""
        super()._draw(no_color_updates)
        if hasattr(self, "canvas"):
            self._paint_background()
            self._show_progress(force=True)

    # ------------------------------------------------------------------ the picture
    def _size(self):
        return max(10, self.canvas.winfo_width()), max(10, self.canvas.winfo_height())

    def _rebuild(self):
        c = self.canvas
        c.delete("all")
        self._bars, self._played = [], -1
        w, h = self._size()
        step = max(3, int(self._apply_widget_scaling(BAR_PX)))
        mid = h / 2
        if self._levels is None:                                    # not known yet: a slider's line
            self._heights = []
            self._line = (c.create_line(4, mid, w - 4, mid, width=4, capstyle="round"),
                          c.create_line(4, mid, 4, mid, width=4, capstyle="round"))
        else:
            count = max(10, (w - 4) // step)
            self._heights = peaks(self._levels, count)
            width = max(2, step - max(1, step // 3))
            for i, v in enumerate(self._heights):
                x = 2 + i * step + width / 2
                half = max(1.5, v * (h / 2 - 3))
                self._bars.append(c.create_line(x, mid - half, x, mid + half, width=width, capstyle="round"))
        self._hover_items = (c.create_line(0, 0, 0, 0, width=1, dash=(2, 2)),
                             c.create_text(0, 0, text="", anchor="s", font=("Segoe UI", 8)))
        self._show_progress(force=True)

    def _show_progress(self, force=False):
        c = self.canvas
        played, rest, hover = self._colours()
        w, h = self._size()
        if not self._bars:
            line = getattr(self, "_line", None)
            if line:
                x = 4 + (w - 8) * self._value / 1000
                c.coords(line[1], 4, h / 2, max(4, x), h / 2)
                c.itemconfigure(line[0], fill=rest)
                c.itemconfigure(line[1], fill=played)
            return
        upto = int(len(self._bars) * self._value / 1000) - 1
        if upto == self._played and not force:
            return
        lo, hi = (0, len(self._bars) - 1) if force else (min(upto, self._played) + 1, max(upto, self._played))
        for i in range(max(0, lo), min(len(self._bars) - 1, hi) + 1):
            c.itemconfigure(self._bars[i], fill=played if i <= upto else rest)
        self._played = upto

    # ------------------------------------------------------------------ the mouse
    def _value_at(self, x):
        w, _ = self._size()
        return max(0.0, min(1000.0, 1000.0 * (x - 2) / max(1, w - 4)))

    def _press(self, event):
        self.dragging = True
        self._drag(event)

    def _drag(self, event):
        self.set(self._value_at(event.x))
        self._move(event)
        if self.command:
            self.command(self._value)

    def _release(self, event):
        if not self.dragging:
            return
        self.dragging = False
        self.set(self._value_at(event.x))
        if self.on_release:
            self.on_release()

    def _move(self, event):
        from .music_ui import fmt_time
        if not self.length_ms:
            self._leave()
            return
        w, h = self._size()
        x = max(2, min(w - 2, event.x))
        line, text = self._hover_items
        _played, _rest, hover = self._colours()
        self.canvas.coords(line, x, 2, x, h - 2)
        self.canvas.itemconfigure(line, fill=hover)
        self.canvas.coords(text, min(max(x, 16), w - 16), h / 2 - 2)
        self.canvas.itemconfigure(text, text=fmt_time(self.length_ms * self._value_at(x) / 1000), fill=hover)
        self.canvas.tag_raise(line)
        self.canvas.tag_raise(text)

    def _leave(self):
        line, text = self._hover_items
        self.canvas.coords(line, 0, 0, 0, 0)
        self.canvas.itemconfigure(text, text="")
