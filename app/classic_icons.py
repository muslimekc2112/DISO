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


def _person(img, colour=BLUE):
    d = ImageDraw.Draw(img)
    d.ellipse((38, 8, 90, 60), fill=_darker(colour, 0.7))
    d.ellipse((42, 12, 86, 56), fill=_lighter(colour, 0.25))
    d.pieslice((12, 62, 116, 166), 180, 360, fill=_darker(colour, 0.7))
    d.pieslice((16, 66, 112, 162), 180, 360, fill=colour)


def _magnifier(img):
    d = ImageDraw.Draw(img)
    d.line((76, 76, 116, 116), fill=(120, 80, 40), width=22)
    d.ellipse((8, 8, 88, 88), fill=(70, 70, 80))
    d.ellipse((18, 18, 78, 78), fill=(185, 220, 250))
    d.ellipse((28, 26, 52, 44), fill=(235, 245, 255))


def _magnet(img):
    d = ImageDraw.Draw(img)
    d.arc((14, 10, 114, 110), 180, 360, fill=RED, width=30)
    d.rectangle((14, 58, 44, 92), fill=RED)
    d.rectangle((84, 58, 114, 92), fill=RED)
    d.rectangle((14, 92, 44, 118), fill=(205, 205, 210))
    d.rectangle((84, 92, 114, 118), fill=(205, 205, 210))


def _phone(img):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((32, 4, 96, 124), 12, fill=(45, 45, 55))
    d.rectangle((38, 18, 90, 104), fill=(95, 165, 235))
    d.ellipse((58, 108, 70, 120), fill=(150, 150, 160))
    d.rectangle((54, 9, 74, 13), fill=(120, 120, 130))


def _disk(img):
    d = ImageDraw.Draw(img)
    d.polygon([(10, 10), (104, 10), (118, 24), (118, 118), (10, 118)], fill=BLUE)
    d.rectangle((30, 10, 92, 46), fill=(225, 230, 240))
    d.rectangle((72, 16, 84, 40), fill=(60, 70, 90))
    d.rectangle((26, 66, 102, 118), fill=WHITE)
    _lines(img, (34, 78, 94, 112), 3)


def _key(img):
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 64, 64), fill=_darker(YELLOW, 0.7))
    d.ellipse((14, 14, 58, 58), fill=YELLOW)
    d.ellipse((26, 26, 46, 46), fill=(0, 0, 0, 0))
    d.line((52, 52, 116, 116), fill=_darker(YELLOW, 0.7), width=18)
    d.line((52, 52, 116, 116), fill=YELLOW, width=10)
    d.line((92, 92, 104, 80), fill=YELLOW, width=12)
    d.line((106, 106, 118, 94), fill=YELLOW, width=12)


def _pencil(img):
    d = ImageDraw.Draw(img)
    d.polygon([(90, 10), (118, 38), (44, 112), (16, 84)], fill=ORANGE)
    d.polygon([(90, 10), (118, 38), (106, 50), (78, 22)], fill=(235, 120, 140))
    d.polygon([(16, 84), (44, 112), (8, 120)], fill=(240, 215, 170))
    d.polygon([(8, 120), (14, 104), (24, 114)], fill=INK)


def _trash(img):
    d = ImageDraw.Draw(img)
    d.rectangle((14, 20, 114, 32), fill=(110, 115, 125))
    d.rectangle((48, 8, 80, 20), fill=(110, 115, 125))
    d.polygon([(24, 36), (104, 36), (96, 122), (32, 122)], fill=(150, 155, 165))
    for x in (44, 62, 80):
        d.rectangle((x, 48, x + 6, 110), fill=(105, 110, 120))


def _bell(img):
    d = ImageDraw.Draw(img)
    d.pieslice((22, 14, 106, 98), 180, 360, fill=_darker(YELLOW, 0.75))
    d.rectangle((22, 56, 106, 92), fill=_darker(YELLOW, 0.75))
    d.pieslice((26, 18, 102, 94), 180, 360, fill=YELLOW)
    d.rectangle((26, 56, 102, 92), fill=YELLOW)
    d.rounded_rectangle((10, 88, 118, 104), 6, fill=_darker(YELLOW, 0.75))
    d.ellipse((54, 100, 74, 120), fill=(150, 100, 40))


def _globe(img):
    d = ImageDraw.Draw(img)
    _ball(img, (8, 8, 120, 120), BLUE)
    d.ellipse((30, 26, 70, 62), fill=GREEN)
    d.ellipse((62, 66, 100, 100), fill=GREEN)
    d.ellipse((76, 30, 96, 48), fill=GREEN)


def _star(img, colour=YELLOW):
    import math
    d = ImageDraw.Draw(img)
    pts = [(64 + (58 if i % 2 == 0 else 24) * math.sin(math.pi * i / 5),
            68 - (58 if i % 2 == 0 else 24) * math.cos(math.pi * i / 5)) for i in range(10)]
    d.polygon(pts, fill=_darker(colour, 0.75))
    d.polygon([(64 + (x - 64) * 0.86, 68 + (y - 68) * 0.86) for x, y in pts], fill=colour)


def _keyboard(img):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 30, 122, 104), 10, fill=(70, 72, 82))
    for row, y in enumerate((40, 60)):
        for x in range(16 - row * 4, 110, 18):
            d.rounded_rectangle((x, y, x + 13, y + 13), 3, fill=(225, 228, 235))
    d.rounded_rectangle((32, 82, 96, 94), 3, fill=(225, 228, 235))


def _heart(img, colour=RED):
    d = ImageDraw.Draw(img)
    for grow, c in ((0, _darker(colour, 0.7)), (5, colour)):
        d.ellipse((10 + grow, 18 + grow, 66 - grow, 74 - grow), fill=c)
        d.ellipse((62 + grow, 18 + grow, 118 - grow, 74 - grow), fill=c)
        d.polygon([(14 + grow, 56), (114 - grow, 56), (64, 116 - grow)], fill=c)


def _rocket(img):
    d = ImageDraw.Draw(img)
    d.polygon([(30, 74), (12, 96), (40, 90)], fill=RED)
    d.polygon([(54, 98), (32, 116), (38, 88)], fill=RED)
    d.polygon([(116, 12), (66, 30), (30, 74), (54, 98), (98, 62)], fill=(215, 220, 230))
    d.ellipse((70, 38, 92, 60), fill=BLUE)
    d.polygon([(30, 98), (18, 112), (26, 104)], fill=ORANGE)
    d.polygon([(34, 92), (14, 120), (40, 100)], fill=ORANGE)


def _mail(img):
    d = ImageDraw.Draw(img)
    d.rectangle((8, 26, 120, 104), fill=(110, 110, 120))
    d.rectangle((12, 30, 116, 100), fill=WHITE)
    d.polygon([(12, 30), (116, 30), (64, 72)], fill=(225, 230, 240))
    d.line((12, 30, 64, 72, 116, 30), fill=(140, 140, 150), width=4)


def _puzzle(img, colour=GREEN):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((14, 34, 104, 118), 8, fill=_darker(colour, 0.72))
    d.rounded_rectangle((18, 38, 100, 114), 6, fill=colour)
    d.ellipse((46, 10, 76, 40), fill=colour)
    d.ellipse((92, 60, 122, 90), fill=colour)


def _bug(img):
    d = ImageDraw.Draw(img)
    for y in (52, 74, 96):
        d.line((14, y - 10, 114, y + 10), fill=INK, width=6)
        d.line((14, y + 10, 114, y - 10), fill=INK, width=6)
    d.ellipse((30, 34, 98, 120), fill=RED)
    d.line((64, 40, 64, 118), fill=INK, width=5)
    d.ellipse((44, 12, 84, 46), fill=INK)
    d.ellipse((48, 62, 58, 72), fill=INK)
    d.ellipse((72, 84, 82, 94), fill=INK)


def _mic(img):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((42, 6, 86, 78), 22, fill=(90, 95, 110))
    d.rounded_rectangle((46, 10, 82, 74), 18, fill=(160, 165, 180))
    d.arc((26, 30, 102, 94), 0, 180, fill=INK, width=7)
    d.line((64, 94, 64, 116), fill=INK, width=7)
    d.line((42, 118, 86, 118), fill=INK, width=8)


def _sliders(img):
    d = ImageDraw.Draw(img)
    for x, y, c in ((26, 40, BLUE), (64, 84, GREEN), (102, 56, ORANGE)):
        d.line((x, 12, x, 116), fill=(90, 95, 110), width=8)
        d.rounded_rectangle((x - 16, y - 10, x + 16, y + 10), 5, fill=_darker(c, 0.7))
        d.rounded_rectangle((x - 13, y - 7, x + 13, y + 7), 4, fill=c)


def _headphones(img):
    d = ImageDraw.Draw(img)
    d.arc((14, 10, 114, 110), 180, 360, fill=(70, 72, 82), width=12)
    d.rounded_rectangle((8, 62, 40, 116), 10, fill=PURPLE)
    d.rounded_rectangle((88, 62, 120, 116), 10, fill=PURPLE)


def _picture(img):
    d = ImageDraw.Draw(img)
    d.rectangle((8, 18, 120, 110), fill=(120, 90, 60))
    d.rectangle((14, 24, 114, 104), fill=(160, 210, 245))
    d.polygon([(14, 104), (52, 56), (82, 92), (96, 76), (114, 104)], fill=GREEN)
    d.ellipse((84, 32, 104, 52), fill=YELLOW)


def _plus_only(img):
    _plus(img, 64, 64, 56)


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
    elif name in DRAWINGS:                     # the "Standart" look's pictures
        DRAWINGS[name](img)
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


DRAWINGS = {
    "person": _person, "search": _magnifier, "magnet": _magnet, "phone": _phone, "disk": _disk, "key": _key,
    "pencil": _pencil, "trash": _trash, "bell": _bell, "globe": _globe, "star": _star, "keyboard": _keyboard,
    "heart": _heart, "rocket": _rocket, "mail": _mail, "puzzle": _puzzle, "bug": _bug, "mic": _mic,
    "sliders": _sliders, "headphones": _headphones, "picture": _picture, "plus": _plus_only,
    "check": lambda img: _check(img, 64, 64, 48, width=22),
}
NAMES = ("add", "resume", "pause", "pause_all", "start_all", "delete", "delete_done", "options", "scheduler",
         "update", "music", "channels", "history", "download", "info", "paste", "file_links", "folder",
         "video", "audio", "archive", "document", "program", "other", "unfinished", "finished", "error", "queue",
         *DRAWINGS)
