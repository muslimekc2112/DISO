"""Makes every icon of the program from ONE picture: IKON/icon.png.

    python tools/make_icons.py                  # uses IKON/icon.png
    python tools/make_icons.py --source my.png

The picture may have a plain white (or light grey) background and a soft shadow around the tile, as
pictures made by image tools usually do. The background is found from the picture's border inwards, so
white that is INSIDE the tile (the note) is kept. Writes:
    assets/icon.png         512 x 512, transparent corners (tray, windows)
    assets/icon.ico         16 .. 256 px in one file (the exe, the shortcuts, the installer)
    browser_extension/icons icon16 / icon48 / icon128 for the browser extension
"""
import argparse
import os
from collections import deque

from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "IKON", "icon.png")
WORK = 1024                    # the background is searched at this size (fast enough, sharp enough)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def is_background(r, g, b, light=196, spread=22):
    """Plain white / light grey: bright and without colour. The tile's own edge is saturated, so the
    soft grey halo around it counts as background but the tile does not."""
    return min(r, g, b) >= light and max(r, g, b) - min(r, g, b) <= spread


def background_mask(img: Image.Image) -> Image.Image:
    """'L' picture: 255 for the tile, 0 for the background that is connected to the border."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    data = rgb.tobytes()
    seen = bytearray(w * h)
    queue = deque()

    def bg(i):
        j = i * 3
        return is_background(data[j], data[j + 1], data[j + 2])

    for x in range(w):
        for y in (0, h - 1):
            i = y * w + x
            if not seen[i] and bg(i):
                seen[i] = 1
                queue.append(i)
    for y in range(h):
        for x in (0, w - 1):
            i = y * w + x
            if not seen[i] and bg(i):
                seen[i] = 1
                queue.append(i)
    while queue:
        i = queue.popleft()
        x, y = i % w, i // w
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h:
                j = ny * w + nx
                if not seen[j] and bg(j):
                    seen[j] = 1
                    queue.append(j)
    mask = Image.frombytes("L", (w, h), bytes(0 if v else 255 for v in seen))
    # eat the last pixel of grey fringe, then soften the edge so that it is smooth when scaled down
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.1))
    return mask.point(lambda v: 0 if v < 40 else (255 if v > 215 else int((v - 40) * 255 / 175)))


def cut_out(img: Image.Image, margin=0.02) -> Image.Image:
    """The tile alone, on a transparent square, scaled to WORK pixels."""
    img = img.convert("RGB")
    longest = max(img.size)
    if longest != WORK:
        scale = WORK / longest
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    rgba = img.convert("RGBA")
    rgba.putalpha(background_mask(img))
    box = rgba.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if not box:
        raise ValueError("the picture has nothing but background")
    rgba = rgba.crop(box)
    side = max(rgba.size)
    pad = round(side * margin)
    square = Image.new("RGBA", (side + 2 * pad, side + 2 * pad), (0, 0, 0, 0))
    square.paste(rgba, ((square.width - rgba.width) // 2, (square.height - rgba.height) // 2), rgba)
    return square


def render(master: Image.Image, size: int) -> Image.Image:
    return master.resize((size, size), Image.LANCZOS)


def write_all(source=SOURCE, root=ROOT):
    master = cut_out(Image.open(source))
    assets = os.path.join(root, "assets")
    ext = os.path.join(root, "browser_extension", "icons")
    os.makedirs(assets, exist_ok=True)
    os.makedirs(ext, exist_ok=True)
    big = render(master, 512)
    big.save(os.path.join(assets, "icon.png"))
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(assets, "icon.ico"), sizes=[(s, s) for s in ICO_SIZES])
    for s in (16, 48, 128):
        render(master, s).save(os.path.join(ext, f"icon{s}.png"))
    return assets, ext


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=SOURCE)
    args = ap.parse_args(argv)
    if not os.path.isfile(args.source):
        raise SystemExit(f"{args.source} not found: put the icon picture there (a square png)")
    assets, ext = write_all(args.source)
    print("icons written to", assets, "and", ext)


if __name__ == "__main__":
    main()
