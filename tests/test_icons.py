"""The icon pipeline: a picture with a white background and a soft shadow becomes clean transparent icons."""
import os
import sys

import pytest
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import make_icons as mi  # noqa: E402


def sample(size=600, tile=(120, 70, 380, 380), with_shadow=True):
    """White page, a soft grey shadow, a purple rounded tile with a white 'note' inside."""
    img = Image.new("RGB", (size, size), (255, 255, 255))
    if with_shadow:
        shadow = Image.new("L", (size, size), 0)
        ImageDraw.Draw(shadow).rounded_rectangle((tile[0] - 6, tile[1] + 8, tile[0] + tile[2] + 6, tile[1] + tile[3] + 14),
                                                 radius=50, fill=70)
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        img = Image.composite(Image.new("RGB", (size, size), (190, 190, 195)), img, shadow)
    d = ImageDraw.Draw(img)
    x, y, w, h = tile
    d.rounded_rectangle((x, y, x + w, y + h), radius=60, fill=(150, 50, 150))
    d.rectangle((x + 120, y + 70, x + 160, y + 250), fill=(255, 255, 255))                     # the white note, inside
    d.ellipse((x + 70, y + 210, x + 150, y + 270), fill=(255, 255, 255))
    return img


def alpha(img, xy):
    return img.getpixel(xy)[3]


# ------------------------------------------------------------------------------ what counts as background
@pytest.mark.parametrize("pixel,expected", [((255, 255, 255), True), ((235, 235, 238), True), ((200, 200, 205), True),
                                            ((150, 50, 150), False), ((250, 220, 250), False), ((120, 120, 120), False),
                                            ((255, 240, 200), False)])
def test_only_plain_light_colours_are_background(pixel, expected):
    assert mi.is_background(*pixel) is expected


# ------------------------------------------------------------------------------ the cut-out
def test_the_background_and_the_shadow_go_and_the_tile_stays():
    out = mi.cut_out(sample())
    assert out.mode == "RGBA" and out.width == out.height
    assert alpha(out, (0, 0)) == 0 and alpha(out, (out.width - 1, out.height - 1)) == 0       # corners: nothing
    assert alpha(out, (out.width // 2, out.height // 2)) == 255                                # the middle: the tile
    r, g, b, a = out.getpixel((out.width // 2, out.height // 2 - 90))
    assert a == 255 and (r, g, b) != (255, 255, 255)                                           # tile colour, not white


def test_white_inside_the_tile_is_kept_opaque():
    img = sample()
    out = mi.cut_out(img)
    # find a pure white opaque pixel: the note
    px = out.load()
    whites = sum(1 for x in range(0, out.width, 6) for y in range(0, out.height, 6) if px[x, y][3] == 255 and px[x, y][:3] == (255, 255, 255))
    assert whites > 20


def test_the_shadow_halo_is_not_left_as_a_grey_rim():
    out = mi.cut_out(sample())
    px = out.load()
    grey_rim = [(x, y) for x in range(out.width) for y in range(out.height)
                if 0 < px[x, y][3] < 255 and max(px[x, y][:3]) - min(px[x, y][:3]) < 25 and min(px[x, y][:3]) > 150]
    assert len(grey_rim) < 40                                                                  # essentially none


def test_the_result_is_square_with_a_small_margin_and_a_fixed_working_size():
    out = mi.cut_out(sample(size=900, tile=(100, 150, 600, 600)))
    assert out.width == out.height
    box = out.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    assert 0 < box[0] <= out.width * 0.05 and 0 < box[1] <= out.height * 0.05                  # a thin transparent margin
    assert mi.render(out, 48).size == (48, 48)


def test_a_tile_that_is_not_square_is_centred_not_stretched():
    out = mi.cut_out(sample(size=900, tile=(100, 150, 600, 400)))
    box = out.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    assert out.width == out.height and box[3] - box[1] < box[2] - box[0]                       # still wider than tall
    assert abs(box[1] - (out.height - box[3])) <= 3                                             # and centred


def test_a_picture_of_only_background_is_refused():
    with pytest.raises(ValueError):
        mi.cut_out(Image.new("RGB", (300, 300), (255, 255, 255)))


def test_a_picture_with_a_transparent_png_mode_or_a_palette_still_works(tmp_path):
    path = tmp_path / "p.png"
    sample().convert("P").save(path)
    assert mi.cut_out(Image.open(path)).width > 100
    rgba = sample().convert("RGBA")
    assert mi.cut_out(rgba).width > 100


# ------------------------------------------------------------------------------ the files
def test_every_file_is_written_with_the_right_sizes(tmp_path):
    src = tmp_path / "icon.png"
    sample().save(src)
    root = tmp_path / "proje"
    assets, ext = mi.write_all(str(src), str(root))
    big = Image.open(os.path.join(assets, "icon.png"))
    assert big.size == (512, 512) and big.mode == "RGBA" and alpha(big, (0, 0)) == 0
    ico = Image.open(os.path.join(assets, "icon.ico"))
    assert sorted(ico.info["sizes"]) == sorted((s, s) for s in mi.ICO_SIZES)
    for s in (16, 48, 128):
        assert Image.open(os.path.join(ext, f"icon{s}.png")).size == (s, s)


def test_a_missing_source_says_where_to_put_it(tmp_path):
    with pytest.raises(SystemExit) as e:
        mi.main(["--source", str(tmp_path / "yok.png")])
    assert "not found" in str(e.value)


# ------------------------------------------------------------------------------ the icons the program ships with
def test_the_shipped_icons_are_clean_and_complete():
    big = Image.open(os.path.join(ROOT, "assets", "icon.png"))
    assert big.size == (512, 512) and big.mode == "RGBA" and alpha(big, (0, 0)) == 0 and alpha(big, (256, 256)) == 255
    assert alpha(big, (511, 511)) == 0 and alpha(big, (511, 0)) == 0
    ico = Image.open(os.path.join(ROOT, "assets", "icon.ico"))
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(ico.info["sizes"])
    for s in (16, 48, 128):
        im = Image.open(os.path.join(ROOT, "browser_extension", "icons", f"icon{s}.png"))
        assert im.size == (s, s) and im.mode == "RGBA"
