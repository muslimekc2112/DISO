"""🎨 The colours of a song's cover: the music window's background takes on a little of them (like YouTube's
ambient mode) and the visualizer can paint with them ("Kapaktan" palette).

Everything here is plain colour arithmetic on a small copy of the picture, so it is quick enough to run when
the song changes."""
import colorsys

LIGHT_BASE, DARK_BASE = "#EBEBEB", "#242424"     # customtkinter's window colours (gray92 / gray14)
LIGHT_SHARE, DARK_SHARE = 0.16, 0.22             # how much of the cover's colour the background takes
STEPS = 10                                       # a new colour comes in over this many small steps


def _hex(colour):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def mix(a, b, share) -> str:
    """`share` of colour b over colour a (both "#rrggbb")."""
    share = max(0.0, min(1.0, float(share)))
    ra, rb = _hex(a), _hex(b)
    return to_hex(ra[k] + (rb[k] - ra[k]) * share for k in range(3))


def cover_colours(path, count=3):
    """The cover's main colours, the most striking first (a lively, often seen colour beats a big grey
    background); [] when the picture cannot be read."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            small = im.convert("RGB").resize((48, 48))
    except Exception:  # noqa: BLE001 - no picture, no colours
        return []
    quantised = small.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    palette = quantised.getpalette() or []
    found = []
    for amount, index in sorted(quantised.getcolors() or [], reverse=True):
        rgb = tuple(palette[index * 3:index * 3 + 3])
        if len(rgb) < 3:
            continue
        h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
        lively = s * (1 - abs(2 * l - 1))                         # saturated and neither black nor white
        found.append((amount / (48 * 48) * (0.25 + lively * 2), rgb))
    found.sort(reverse=True)
    return [to_hex(rgb) for _, rgb in found[:count]]


def main_colour(path):
    colours = cover_colours(path, 1)
    return colours[0] if colours else None


def _with(colour, lightness=None, saturation=None) -> str:
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in _hex(colour)))
    l = l if lightness is None else lightness
    s = s if saturation is None else saturation
    return to_hex(v * 255 for v in colorsys.hls_to_rgb(h, l, s))


def background(colour, base=(LIGHT_BASE, DARK_BASE)):
    """(light, dark) colours of `base` (a window / panel colour pair) with a hint of this colour; `base`
    itself without one."""
    light, dark = base
    if not colour:
        return light, dark
    s = max(0.45, colorsys.rgb_to_hls(*(v / 255 for v in _hex(colour)))[2])
    return (mix(light, _with(colour, lightness=0.62, saturation=s), LIGHT_SHARE),
            mix(dark, _with(colour, lightness=0.40, saturation=s), DARK_SHARE))


def palette(colours):
    """A five-stop visualizer palette (dark → bright) made from the cover's colours."""
    if not colours:
        return None
    first = colours[0]
    second = colours[1] if len(colours) > 1 else _with(first, lightness=0.7)
    h, _l, s = colorsys.rgb_to_hls(*(v / 255 for v in _hex(first)))
    s = max(0.45, s)
    return [_with(first, lightness=0.12, saturation=s), _with(first, lightness=0.32, saturation=s),
            _with(first, lightness=0.52, saturation=s), _with(second, lightness=0.66, saturation=max(0.5, s)),
            _with(second, lightness=0.88, saturation=0.6)]


def steps(old, new, count=STEPS):
    """The colours in between, for a soft change (the last one is `new`)."""
    return [mix(old, new, (i + 1) / count) for i in range(count)]
