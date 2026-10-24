"""🌈 The visualizer: the analysis (spectrum and loudness per 1/30 s) and the window's three pictures."""
import time

import numpy as np
import pytest
from music_support import FakeBackend, make_wav

from app import player, visualizer


def _tone(hz, seconds=2.0, loud=0.5):
    t = np.arange(int(visualizer.RATE * seconds)) / visualizer.RATE
    return (loud * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def _band_of(hz):
    edges = visualizer.band_edges() * visualizer.RATE / visualizer.WINDOW
    return int(np.searchsorted(edges, hz, side="right") - 1)


def test_a_tone_lights_its_own_band():
    for hz in (100, 1000, 5000):
        frames, level = visualizer.analyse_samples(_tone(hz))
        assert frames.shape[1] == visualizer.BANDS and len(frames) == len(level)
        assert abs(int(np.argmax(frames[20])) - _band_of(hz)) <= 1, hz


def test_frames_follow_the_time_and_loudness_follows_the_sound():
    quiet_then_loud = np.concatenate([_tone(440, 1.0, 0.02), _tone(440, 1.0, 0.8)])
    frames, level = visualizer.analyse_samples(quiet_then_loud)
    assert len(frames) == pytest.approx(2 * visualizer.FPS, abs=2)
    _, early = visualizer.frame_at((frames, level), 300)
    _, late = visualizer.frame_at((frames, level), 1700)
    assert late > early * 3
    assert visualizer.frame_at((frames, level), 10 ** 9)[0] is not None    # after the end: the last frame


def test_colours_along_a_palette():
    p = ["#000000", "#ffffff"]
    assert visualizer.blend(p, 0) == "#000000" and visualizer.blend(p, 1) == "#ffffff"
    assert visualizer.blend(p, 0.5) == "#7f7f7f" and visualizer.blend(p, 7) == "#ffffff"
    assert all(len(v) == 5 for v in visualizer.PALETTES.values())


def test_the_analyzer_works_once_per_song_in_the_background():
    calls = []
    a = visualizer.Analyzer(decode_fn=lambda path: calls.append(path) or _tone(440, 1.0))
    a.want("x.mp3")
    a.want("x.mp3")
    end = time.time() + 5
    while a.get("x.mp3") is None and time.time() < end:
        time.sleep(0.02)
    assert a.get("x.mp3") is not None and calls == ["x.mp3"] and not a.busy("x.mp3")
    bad = visualizer.Analyzer(decode_fn=lambda path: (_ for _ in ()).throw(OSError("broken")))
    bad.want("y.mp3")
    end = time.time() + 5
    while bad.busy("y.mp3") and time.time() < end:
        time.sleep(0.02)
    assert bad.get("y.mp3") is None


def test_a_real_file_is_decoded():
    from app.utils import find_ffmpeg
    if not find_ffmpeg():
        pytest.skip("needs ffmpeg")
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = make_wav(d + "/a.wav")
        samples = visualizer.decode(path)
        assert len(samples) > 0 and samples.dtype == np.float32


class ReadyAnalyzer:
    def __init__(self, result):
        self.result = result

    def want(self, path):
        pass

    def get(self, path):
        return self.result

    def busy(self, path):
        return False


@pytest.mark.gui
def test_the_window_draws_every_style(app, monkeypatch, tmp_path):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    music = app.music
    song = make_wav(tmp_path / "Barış Manço - Gülpembe.wav")
    music._pick_files = lambda: [song]
    music._add_files()
    music.tree.selection_set("0")
    music._play_selected()
    assert music.controller.state == "playing"
    result = visualizer.analyse_samples(_tone(1000, 3.0))
    win = music.open_visualizer()
    win.analyzer = ReadyAnalyzer(result)
    win.geometry("800x500")
    win.update()
    monkeypatch.setattr(music.controller, "position_ms", lambda: 1000)
    for style in ("Çubuklar", "Dalga", "Halka"):
        win.set_style(style)
        win.update()
        for _ in range(3):
            win.step()
        assert max(win.levels) > 0.5, style
    band = _band_of(1000)
    win.set_style("Çubuklar")
    win.update()
    win.step()
    x0, top, x1, base = win.canvas.coords(win.items["bars"][band])
    assert base - top > 100                                        # the 1 kHz bar stands tall
    assert music.store.state["vis_style"] == "Çubuklar"
    win.set_palette("Neon")
    assert music.store.state["vis_palette"] == "Neon"
    shown = []
    monkeypatch.setattr(win, "attributes", lambda *a: shown.append(a))
    win.toggle_full()
    assert shown == [("-fullscreen", True)] and not win.bar.winfo_ismapped()
    win.toggle_full()
    win.destroy()


@pytest.mark.gui
def test_the_lyrics_flow_over_the_picture_and_can_be_hidden(app, monkeypatch, tmp_path):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    music = app.music
    song = make_wav(tmp_path / "Barış Manço - Gülpembe.wav")
    (tmp_path / "Barış Manço - Gülpembe.lrc").write_text("[00:01.00]Sen gülünce\n[00:04.00]güller açar\n"
                                                        "[00:07.00]gül pembe", encoding="utf-8")
    music._pick_files = lambda: [song]
    music._add_files()
    music.tree.selection_set("0")
    music._play_selected()
    win = music.open_visualizer(lyrics_on=True)
    win.analyzer = ReadyAnalyzer(visualizer.analyse_samples(_tone(440, 10.0)))
    win.update()
    now = {"ms": 4500}
    monkeypatch.setattr(music.controller, "position_ms", lambda: now["ms"])
    win.step()
    text = lambda key: win.canvas.itemcget(win.items[key], "text")     # noqa: E731
    assert (text("lyr_prev"), text("lyr_now"), text("lyr_next")) == ("Sen gülünce", "güller açar", "gül pembe")
    now["ms"] = 7600
    win.step()
    assert text("lyr_now") == "gül pembe" and text("lyr_next") == ""
    win.set_style("Halka")                                          # every picture keeps the lyrics
    win.step()
    assert text("lyr_now") == "gül pembe"
    win.lyrics_btn.invoke()
    win.step()
    assert text("lyr_now") == "" and music.store.state["vis_lyrics"] is False
    assert music.open_visualizer(lyrics_on=True) is win and win.show_lyrics
    win.destroy()


@pytest.mark.gui
def test_with_nothing_playing_it_says_so_and_rests(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    win = app.music.open_visualizer()
    win.levels = [1.0] * visualizer.BANDS
    for _ in range(40):
        win.step()
    assert max(win.levels) < 0.01 and win.canvas.itemcget(win.items["text"], "text") == "Bir şarkı çal 🎵"
    win.destroy()
