"""📈 A small live graph of the download speed: the last minute, one point a second, the area under the line
filled. In the "Nostalji" look it is the green-on-black graph of the programs of those days (with its grid
moving along); in the others it takes the colours of the theme. `Sampler` keeps the numbers: the total and
the speed of each download, for the progress window."""
import collections
import time
import tkinter as tk

import customtkinter as ctk

from . import look
from .i18n import tr
from .utils import human_size

POINTS = 60                    # one minute, one point a second


class Sampler:
    """Once a second: the total speed and each download's speed (kept for POINTS seconds)."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.total = collections.deque([0.0] * POINTS, maxlen=POINTS)
        self.each = {}
        self._last = 0.0

    def take(self, items, downloading) -> bool:
        """Note the speeds when a second has passed (True then). `downloading`: the state that counts."""
        now = self.clock()
        if now - self._last < 1.0:
            return False
        self._last = now
        total = 0.0
        alive = set()
        for it in items:
            speed = float(it.speed) if it.state == downloading else 0.0
            total += speed
            alive.add(it.id)
            row = self.each.get(it.id)
            if row is None:
                if not speed:
                    continue
                row = self.each[it.id] = collections.deque([0.0] * POINTS, maxlen=POINTS)
            row.append(speed)
        for gone in set(self.each) - alive:
            del self.each[gone]
        self.total.append(total)
        return True

    def of(self, item_id):
        return self.each.get(item_id) or collections.deque([0.0] * POINTS, maxlen=POINTS)


def _colour(value):
    if isinstance(value, (list, tuple)):
        return value[1] if ctk.get_appearance_mode() == "Dark" else value[0]
    return value


def palette():
    """(background, grid, line, fill, text) of the current look."""
    if look.is_nostalgia():
        return "#000000", "#0B4F1D", "#3CFF5A", "#0E7A24", "#3CFF5A"
    t = ctk.ThemeManager.theme
    accent = _colour(t["CTkButton"]["fg_color"])
    bg = _colour(t["CTkFrame"]["fg_color"])
    dark = ctk.get_appearance_mode() == "Dark"
    grid = "#3A3A3A" if dark else "#DADADA"
    fill = _blend(accent, bg, 0.35)
    return bg, grid, accent, fill, _colour(t["CTkLabel"]["text_color"])


def _rgb(colour):
    colour = colour.lstrip("#")
    if len(colour) != 6:
        return (128, 128, 128)
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def _blend(a, b, part):
    """`part` of colour a over colour b (only "#rrggbb" colours; anything else gives a)."""
    if not (str(a).startswith("#") and str(b).startswith("#")):
        return a
    x, y = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(p * part + q * (1 - part)) for p, q in zip(x, y))


class SpeedGraph(tk.Canvas):
    """show(values) draws the speeds (bytes/s, oldest first). The top of the graph follows the highest one."""

    def __init__(self, master, width=160, height=28, label=True, **kw):
        bg = palette()[0]
        super().__init__(master, width=width, height=height, highlightthickness=0, bd=0, bg=bg, **kw)
        self.label = label
        self.values = [0.0] * POINTS
        self._shift = 0                  # the grid moves along with the time, like the old graphs did
        self.bind("<Configure>", lambda e: self.redraw())

    def show(self, values):
        self.values = list(values)[-POINTS:]
        self._shift = (self._shift + 1) % 10
        self.redraw()

    def redraw(self):
        try:
            w, h = max(10, self.winfo_width()), max(8, self.winfo_height())
        except tk.TclError:
            return
        bg, grid, line, fill, text = palette()
        self.delete("all")
        self.configure(bg=bg)
        step = w / (POINTS - 1)
        for i in range(-1, POINTS // 10 + 1):                 # upright grid lines every 10 seconds
            x = (i * 10 - self._shift) * step
            if 0 <= x <= w:
                self.create_line(x, 0, x, h, fill=grid)
        for k in (1, 2, 3):
            y = h * k / 4
            self.create_line(0, y, w, y, fill=grid)
        top = max(self.values) if self.values else 0
        if top <= 0:
            if self.label and h >= 24:
                self.create_text(4, 2, anchor="nw", text="0 B/s", fill=text, font=("Segoe UI", 8))
            return
        scale = (h - 3) / (top * 1.15)
        points = [(i * step, h - 1 - v * scale) for i, v in enumerate(self.values)]
        self.create_polygon([(0, h)] + points + [(w, h)], fill=fill, outline="")
        self.create_line(*[c for p in points for c in p], fill=line, width=1.6 if h >= 40 else 1.2, smooth=False)
        if self.label and h >= 24:
            now = self.values[-1]
            self.create_text(4, 2, anchor="nw", text=f"{human_size(now)}/s", fill=text, font=("Segoe UI", 8, "bold"))
            if h >= 44:
                self.create_text(w - 4, 2, anchor="ne", text=f"{tr('en çok')} {human_size(top)}/s", fill=text,
                                 font=("Segoe UI", 8))
