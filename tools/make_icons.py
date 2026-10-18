"""Draws the app icon (a lightning bolt on a blue tile) with Pillow.

Run:  python tools/make_icons.py
Writes assets/icon.ico, assets/icon.png and the browser extension icons.
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOLT = [(152, 18), (66, 142), (118, 142), (98, 238), (192, 106), (138, 106)]  # on a 256 x 256 grid


def draw(size: int = 256) -> Image.Image:
    scale = 4  # draw big, shrink: smooth edges
    big = size * scale
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    # vertical gradient inside a rounded square
    gradient = Image.linear_gradient("L").resize((big, big))
    top, bottom = Image.new("RGBA", (big, big), (52, 132, 232, 255)), Image.new("RGBA", (big, big), (24, 76, 168, 255))
    body = Image.composite(bottom, top, gradient)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.21), fill=255)
    tile.paste(body, (0, 0), mask)
    k = big / 256
    ImageDraw.Draw(tile).polygon([(x * k, y * k) for x, y in BOLT], fill=(255, 255, 255, 255))
    return tile.resize((size, size), Image.LANCZOS)


def main():
    assets = os.path.join(ROOT, "assets")
    ext = os.path.join(ROOT, "browser_extension", "icons")
    os.makedirs(assets, exist_ok=True)
    os.makedirs(ext, exist_ok=True)
    master = draw(256)
    master.save(os.path.join(assets, "icon.png"))
    master.save(os.path.join(assets, "icon.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    for s in (16, 48, 128):
        draw(s).save(os.path.join(ext, f"icon{s}.png"))
    print("icons written to", assets, "and", ext)


if __name__ == "__main__":
    main()
