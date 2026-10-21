"""The pictures of the "Nostalji" look: the big toolbar icons and the small ones of the category tree and of
the download list. They are drawn here (four times larger, then scaled down: smooth edges), so no picture
file has to travel with the program and nothing is borrowed from another program."""
from PIL import Image, ImageDraw, ImageEnhance

S = 128                       # drawing size; every shape below is in this square

GREEN = (40, 165, 60)
RED = (215, 50, 45)
BLUE = (30, 115, 210)
ORANGE = (240, 145, 25)
PURPLE = (125, 70, 190)
GREY = (120, 125, 132)
YELLOW = (245, 200, 75)
WHITE = (255, 255, 255)
INK = (40, 40, 40)

_photos = {}


def _darker(c, f=0.7):
    return tuple(int(v * f) for v in c[:3])


def _lighter(c, f=0.45):
    return tuple(int(v + (255 - v) * f) for v in c[:3])


def _canvas():
    return Image.new("RGBA", (S, S), (0, 0, 0, 0))


def _ball(img, box, colour):
    """A glossy round button: darker rim, body, a light shine on the upper half."""
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.ellipse(box, fill=_darker(colour, 0.62))
    d.ellipse((x0 + 4, y0 + 4, x1 - 4, y1 - 4), fill=colour)
    shine = Image.new("RGBA", img.size, (0, 0, 0, 0))
    w = x1 - x0
    ImageDraw.Draw(shine).ellipse((x0 + w * 0.16, y0 + w * 0.08, x1 - w * 0.16, y0 + w * 0.52),
                                  fill=(255, 255, 255, 95))
    img.alpha_composite(shine)


def _page(img, box, fold=22, fill=WHITE):
    """A sheet of paper with a folded corner."""
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.polygon([(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)], fill=(110, 110, 110))
    d.polygon([(x0 + 3, y0 + 3), (x1 - fold - 1, y0 + 3), (x1 - 3, y0 + fold + 1), (x1 - 3, y1 - 3),
               (x0 + 3, y1 - 3)], fill=fill)
    d.polygon([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)], fill=(205, 205, 205))


def _lines(img, box, n=4, colour=(150, 160, 175)):
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    step = (y1 - y0) / max(1, n)
    for i in range(n):
        y = y0 + i * step
        d.rectangle((x0, y, x1 - (18 if i == n - 1 else 0), y + 5), fill=colour)


def _plus(img, cx, cy, r, colour=GREEN):
    _ball(img, (cx - r, cy - r, cx + r, cy + r), colour)
    d = ImageDraw.Draw(img)
    a, t = r * 0.55, r * 0.17
    d.rectangle((cx - a, cy - t, cx + a, cy + t), fill=WHITE)
    d.rectangle((cx - t, cy - a, cx + t, cy + a), fill=WHITE)


def _play(d, cx, cy, r, colour=WHITE):
    d.polygon([(cx - r * 0.55, cy - r), (cx - r * 0.55, cy + r), (cx + r * 0.95, cy)], fill=colour)


def _square(d, cx, cy, r, colour=WHITE):
    d.rectangle((cx - r, cy - r, cx + r, cy + r), fill=colour)


def _cross(img, cx, cy, r, colour=RED, width=22):
    d = ImageDraw.Draw(img)
    for w, c in ((width + 8, _darker(colour, 0.6)), (width, colour)):
        d.line((cx - r, cy - r, cx + r, cy + r), fill=c, width=w)
        d.line((cx - r, cy + r, cx + r, cy - r), fill=c, width=w)


def _check(img, cx, cy, r, colour=GREEN, width=20):
    d = ImageDraw.Draw(img)
    pts = [(cx - r, cy), (cx - r * 0.3, cy + r * 0.7), (cx + r, cy - r * 0.8)]
    d.line(pts, fill=_darker(colour, 0.6), width=width + 8, joint="curve")
    d.line(pts, fill=colour, width=width, joint="curve")


def _gear(img, cx, cy, r, colour=GREY):
    import math
    d = ImageDraw.Draw(img)
    teeth = 8
    pts = []
    for i in range(teeth * 2):
        a = math.pi * i / teeth
        rr = r if i % 2 == 0 else r * 0.78
        for da in (-0.17, 0.17):
            pts.append((cx + rr * math.cos(a + da), cy + rr * math.sin(a + da)))
    d.polygon(pts, fill=_darker(colour, 0.75))
    d.ellipse((cx - r * 0.7, cy - r * 0.7, cx + r * 0.7, cy + r * 0.7), fill=colour)
    d.ellipse((cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3), fill=(235, 235, 235))


def _clock(img, cx, cy, r):
    _ball(img, (cx - r, cy - r, cx + r, cy + r), BLUE)
    d = ImageDraw.Draw(img)
    d.ellipse((cx - r * 0.78, cy - r * 0.78, cx + r * 0.78, cy + r * 0.78), fill=WHITE)
    d.line((cx, cy, cx, cy - r * 0.55), fill=INK, width=9)
    d.line((cx, cy, cx + r * 0.42, cy + r * 0.12), fill=INK, width=9)
    d.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill=RED)


def _note(img, colour=PURPLE):
    d = ImageDraw.Draw(img)
    d.rectangle((70, 18, 82, 92), fill=colour)
    d.polygon([(70, 18), (112, 30), (112, 52), (82, 42)], fill=colour)
    d.ellipse((34, 76, 82, 112), fill=colour)
    d.ellipse((44, 82, 62, 94), fill=_lighter(colour, 0.5))


def _folder(img, colour=YELLOW, box=(10, 26, 118, 108)):
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.polygon([(x0, y0 + 6), (x0 + 6, y0), (x0 + 40, y0), (x0 + 48, y0 + 10), (x1, y0 + 10), (x1, y1),
               (x0, y1)], fill=_darker(colour, 0.8))
    d.polygon([(x0 + 2, y0 + 26), (x1 - 2, y0 + 26), (x1 - 2, y1 - 2), (x0 + 2, y1 - 2)], fill=colour)
    d.rectangle((x0 + 2, y0 + 26, x1 - 2, y0 + 34), fill=_lighter(colour, 0.5))


def _film(img):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((12, 22, 116, 106), 10, fill=(55, 60, 75))
    for x in range(20, 112, 18):
        d.rectangle((x, 28, x + 9, 38), fill=WHITE)
        d.rectangle((x, 90, x + 9, 100), fill=WHITE)
    d.rectangle((22, 44, 106, 84), fill=(90, 160, 230))
    d.polygon([(54, 50), (54, 78), (80, 64)], fill=WHITE)


def _box(img):
    """A packed archive: a box with a zip down the middle."""
    d = ImageDraw.Draw(img)
    d.rectangle((14, 30, 114, 110), fill=(190, 140, 70))
    d.polygon([(14, 30), (34, 12), (94, 12), (114, 30)], fill=(220, 175, 105))
    d.rectangle((56, 12, 72, 110), fill=(120, 120, 130))
    for y in range(18, 106, 10):
        d.rectangle((60, y, 68, y + 4), fill=(225, 225, 230))


def _window(img):
    d = ImageDraw.Draw(img)
    d.rectangle((10, 18, 118, 110), fill=(80, 80, 90))
    d.rectangle((14, 22, 114, 40), fill=BLUE)
    d.rectangle((14, 40, 114, 106), fill=WHITE)
    d.rectangle((98, 26, 108, 36), fill=RED)
    d.rectangle((24, 54, 70, 60), fill=(150, 160, 175))
    d.rectangle((24, 70, 90, 76), fill=(150, 160, 175))
    d.rectangle((24, 86, 60, 92), fill=(150, 160, 175))


def _tv(img):
    d = ImageDraw.Draw(img)
    d.line((44, 8, 64, 28), fill=INK, width=6)
    d.line((84, 8, 64, 28), fill=INK, width=6)
    d.rounded_rectangle((8, 26, 120, 108), 12, fill=(70, 70, 80))
    d.rounded_rectangle((18, 36, 98, 98), 8, fill=(95, 165, 235))
    d.polygon([(46, 50), (46, 84), (76, 67)], fill=WHITE)
    d.ellipse((102, 44, 114, 56), fill=ORANGE)
    d.ellipse((102, 64, 114, 76), fill=ORANGE)


def _bars(img):
    d = ImageDraw.Draw(img)
    d.rectangle((10, 112, 118, 118), fill=INK)
    for x, h, c in ((16, 46, BLUE), (44, 82, GREEN), (72, 62, ORANGE), (100, 96, RED)):
        d.rectangle((x, 112 - h, x + 20, 112), fill=_darker(c, 0.75))
        d.rectangle((x + 3, 115 - h, x + 17, 112), fill=c)


def _arrows(img):
    """Two arrows going round: update."""
    d = ImageDraw.Draw(img)
    d.arc((14, 14, 114, 114), 200, 340, fill=GREEN, width=20)
    d.polygon([(104, 32), (124, 62), (88, 62)], fill=GREEN)
    d.arc((14, 14, 114, 114), 20, 160, fill=BLUE, width=20)
    d.polygon([(24, 96), (4, 66), (40, 66)], fill=BLUE)


def _down(img, colour=GREEN):
    d = ImageDraw.Draw(img)
    d.rectangle((48, 12, 80, 66), fill=_darker(colour, 0.7))
    d.rectangle((52, 14, 76, 66), fill=colour)
    d.polygon([(20, 62), (108, 62), (64, 112)], fill=_darker(colour, 0.7))
    d.polygon([(28, 66), (100, 66), (64, 106)], fill=colour)


def _bang(img):
    _ball(img, (8, 8, 120, 120), RED)
    d = ImageDraw.Draw(img)
    d.rectangle((56, 28, 72, 76), fill=WHITE)
    d.rectangle((56, 86, 72, 100), fill=WHITE)


def _hourglass(img):
    d = ImageDraw.Draw(img)
    d.rectangle((24, 10, 104, 20), fill=(120, 80, 40))
    d.rectangle((24, 108, 104, 118), fill=(120, 80, 40))
    d.polygon([(32, 20), (96, 20), (64, 64), (96, 108), (32, 108), (64, 64)], fill=(205, 225, 245))
    d.polygon([(44, 30), (84, 30), (64, 58)], fill=(230, 185, 80))
    d.polygon([(64, 74), (88, 104), (40, 104)], fill=(230, 185, 80))


# name -> drawing; the toolbar's and the small ones share them
def _draw(name):
    img = _canvas()
    d = ImageDraw.Draw(img)
    if name == "add":
        _page(img, (16, 6, 92, 104))
        _lines(img, (28, 34, 78, 84), 4)
        _plus(img, 88, 88, 34)
    elif name == "resume":
        _ball(img, (8, 8, 120, 120), GREEN)
        _play(d, 66, 64, 34)
    elif name == "pause":
        _ball(img, (8, 8, 120, 120), RED)
        _square(d, 64, 64, 24)
    elif name == "pause_all":
        _ball(img, (4, 4, 84, 84), RED)
        _square(ImageDraw.Draw(img), 44, 44, 15)
        _ball(img, (44, 44, 124, 124), RED)
        _square(ImageDraw.Draw(img), 84, 84, 17)
    elif name == "start_all":
        _ball(img, (8, 8, 120, 120), GREEN)
        _play(d, 50, 64, 26)
        _play(d, 82, 64, 26)
    elif name == "delete":
        _cross(img, 64, 64, 40)
    elif name == "delete_done":
        _page(img, (14, 6, 90, 106))
        _check(img, 50, 54, 24, width=14)
        _cross(img, 94, 94, 22, width=14)
    elif name == "options":
        _gear(img, 64, 64, 56)
    elif name == "scheduler":
        _clock(img, 64, 64, 56)
    elif name == "update":
        _arrows(img)
    elif name == "music":
        _note(img)
    elif name == "channels":
        _tv(img)
    elif name == "history":
        _bars(img)
    elif name == "download":
        _down(img)
    elif name == "info":
        _ball(img, (8, 8, 120, 120), BLUE)
        d.ellipse((56, 26, 72, 42), fill=WHITE)
        d.rectangle((56, 50, 72, 100), fill=WHITE)
    elif name == "paste":
        d.rounded_rectangle((18, 16, 110, 120), 8, fill=(150, 105, 60))
        d.rectangle((40, 6, 88, 28), fill=(170, 170, 175))
        _page(img, (32, 34, 100, 114), fold=16)
    elif name == "file_links":
        _page(img, (18, 6, 104, 120))
        _lines(img, (32, 34, 92, 104), 5, colour=BLUE)
    elif name == "folder":
        _folder(img)
    elif name == "folder_open":
        _folder(img)
        _down(img.crop((0, 0, S, S)), GREEN)
    elif name == "video":
        _film(img)
    elif name == "audio":
        _note(img)
    elif name == "archive":
        _box(img)
    elif name == "document":
        _page(img, (20, 6, 108, 120))
        _lines(img, (34, 36, 94, 108), 5)
    elif name == "program":
        _window(img)
    elif name == "other":
        _page(img, (22, 6, 106, 120))
    elif name == "unfinished":
        _folder(img)
        _down(img)
    elif name == "finished":
        _folder(img)
        _check(img, 66, 74, 30)
    elif name == "error":
        _bang(img)
    elif name == "queue":
        _hourglass(img)
    else:
        raise KeyError(name)
    return img


def image(name, size, disabled=False):
    """The picture as a PIL image of `size` pixels; `disabled`: grey and faded (a button that cannot be used)."""
    img = _draw(name).resize((size, size), Image.LANCZOS)
    if disabled:
        alpha = img.getchannel("A")
        grey = ImageEnhance.Color(img).enhance(0.0)
        grey = ImageEnhance.Brightness(grey).enhance(1.15)
        grey.putalpha(alpha.point(lambda a: a * 0.45))
        img = grey
    return img


def photo(master, name, size, disabled=False):
    """The picture as a Tk image (kept here: a Tk image nobody holds disappears from the screen)."""
    key = (id(master.tk), name, size, disabled)           # per Tk interpreter (the image holds it: no id reuse)
    found = _photos.get(key)
    if found is None:
        from PIL import ImageTk
        found = _photos[key] = ImageTk.PhotoImage(image(name, size, disabled), master=master)
    return found


NAMES = ("add", "resume", "pause", "pause_all", "start_all", "delete", "delete_done", "options", "scheduler",
         "update", "music", "channels", "history", "download", "info", "paste", "file_links", "folder",
         "video", "audio", "archive", "document", "program", "other", "unfinished", "finished", "error", "queue")
