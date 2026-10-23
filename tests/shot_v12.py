"""Screenshots of the 1.2 music window and visualizer (not a test: run by hand, writes PNGs to SHOT_DIR)."""
import os
import subprocess
import time

import pytest
from music_support import FakeBackend

from app import player, utils

OUT = os.environ.get("SHOT_DIR", ".")


class ClockBackend(FakeBackend):
    def __init__(self, alias=""):
        super().__init__(alias)
        self.length = 60000
        self._t = None

    def play(self):
        self.playing, self._t = True, time.monotonic()

    def resume(self):
        self.play()

    def pause(self):
        self.position = self.position_ms()
        self.playing = False

    def seek(self, ms):
        self.position, self._t = ms, time.monotonic()

    def position_ms(self):
        if self.playing and self._t is not None:
            return self.position + int((time.monotonic() - self._t) * 1000)
        return self.position


def _song(folder, name, colour):
    from PIL import Image, ImageDraw
    cover = os.path.join(folder, name + ".png")
    img = Image.new("RGB", (500, 500), colour)
    d = ImageDraw.Draw(img)
    for k in range(12):
        d.ellipse((40 + k * 15, 40 + k * 15, 460 - k * 15, 460 - k * 15), outline=(255, 220 - k * 12, 120), width=6)
    img.save(cover)
    path = os.path.join(folder, name + ".mp3")
    subprocess.run([utils.find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=330:duration=60", "-f", "lavfi", "-i", "anoisesrc=d=60:a=0.15",
                    "-i", cover, "-filter_complex", "[0:a][1:a]amix=inputs=2,volume=2[a]", "-map", "[a]",
                    "-map", "2:v", "-c:v", "mjpeg", "-disposition:v", "attached_pic", "-c:a", "libmp3lame",
                    "-metadata", "artist=Barış Manço", "-metadata", "title=" + name, path], check=True,
                   **utils.subprocess_flags())
    return path


def _grab(win, name):
    from PIL import ImageGrab
    win.attributes("-topmost", True)
    win.deiconify()
    win.lift()
    end = time.time() + 1.2
    while time.time() < end:
        win.update()
        time.sleep(0.02)
    x, y = win.winfo_rootx(), win.winfo_rooty()
    w, h = win.winfo_width(), win.winfo_height()
    ImageGrab.grab((x, y, x + w, y + h), all_screens=True).save(os.path.join(OUT, name + ".png"))
    win.attributes("-topmost", False)


@pytest.mark.gui
def test_shots(app, monkeypatch, tmp_path):
    monkeypatch.setattr(player, "new_backend", ClockBackend)
    assert app._ensure_music()
    music = app.music
    songs = [_song(str(tmp_path), "Gülpembe", (150, 40, 60)), _song(str(tmp_path), "Dönence", (20, 90, 160))]
    music._pick_files = lambda: songs
    music._add_files()
    music.tree.selection_set("0")
    music._play_selected()
    end = time.time() + 6
    while time.time() < end and not music._covers.get(songs[0]):
        music.update()
        time.sleep(0.05)
    _grab(music, "music")
    win = music.open_visualizer()
    win.geometry("960x620")
    end = time.time() + 8
    while time.time() < end and win.analyzer.get(songs[0]) is None:
        win.update()
        time.sleep(0.05)
    for style in ("Halka", "Çubuklar", "Dalga"):
        win.set_style(style)
        _grab(win, "vis_" + style)
    win.destroy()
