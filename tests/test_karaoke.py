"""🎤 Karaoke: the song's voice taken away (the middle of the stereo sound, the bass kept) and its lyrics on the
visualizer. Not kept: a new start sings again."""
import os
import subprocess

import pytest
from music_support import FakeEqBackend
from test_equalizer import music  # noqa: F401 - the fixture

from app import equalizer, utils


def test_the_karaoke_comes_before_the_equalizer():
    assert equalizer.sound_filter([0] * 8) == ""
    assert equalizer.sound_filter([0] * 8, karaoke=True) == equalizer.KARAOKE
    rock = equalizer.PRESETS["Rock"]
    assert equalizer.sound_filter(rock, True) == equalizer.KARAOKE + "," + equalizer.ffmpeg_filter(rock)


@pytest.mark.gui
def test_karaoke_takes_the_voice_away_and_shows_the_lyrics(music, monkeypatch):
    shown = []
    monkeypatch.setattr(music, "open_visualizer", lambda lyrics_on=None: shown.append(lyrics_on))
    assert music.set_karaoke(True) and music.karaoke and shown == [True]
    c = music.controller
    for backend in (c.backend, c.spare):                                  # both voices of a cross-fade
        assert isinstance(backend.active, FakeEqBackend) and backend.active.filter == equalizer.KARAOKE
    music.apply_eq(equalizer.PRESETS["Rock"])                            # the equalizer keeps working with it
    assert c.backend.active.filter.startswith(equalizer.KARAOKE + ",equalizer") or \
        c.backend.active.filter.startswith(equalizer.KARAOKE + ",volume")
    assert music.store.state.get("karaoke") is None                     # not kept for the next start
    assert any("Karaoke" in (label or "") for label, _ in filter(None, music.player_menu_items()))
    music.apply_eq(equalizer.FLAT)
    assert music.set_karaoke(False) and not music.karaoke
    assert not isinstance(c.backend.active, FakeEqBackend)                # back on the plain player


def test_the_filter_really_takes_the_middle_away(tmp_path):
    ff = utils.find_ffmpeg() or os.path.join(os.environ.get("LOCALAPPDATA", ""), "DISO", "tools", "ffmpeg.EXE")
    if not os.path.isfile(ff):
        pytest.skip("needs ffmpeg")
    src, out = str(tmp_path / "in.wav"), str(tmp_path / "out.wav")
    run = lambda *a: subprocess.run([ff, "-v", "error", "-y", *a], check=True, **utils.subprocess_flags())  # noqa: E731
    # a "voice" at 1 kHz in the middle, an "instrument" at 2 kHz on one side only
    run("-f", "lavfi", "-i", "sine=f=1000:d=2", "-f", "lavfi", "-i", "sine=f=2000:d=2", "-filter_complex",
        "[0][1]amerge=inputs=2,pan=stereo|c0=c0+c1|c1=c0", src)
    run("-i", src, "-af", equalizer.KARAOKE, out)

    def level(path, freq):                                               # (the left speaker, as it is heard)
        r = subprocess.run([ff, "-v", "info", "-i", path, "-af", f"bandpass=f={freq}:w=50,pan=mono|c0=c0,"
                            "astats=measure_overall=RMS_level:measure_perchannel=none", "-f", "null", "-"],
                           capture_output=True, text=True, **utils.subprocess_flags())
        return float(next(line.split()[-1] for line in r.stderr.splitlines() if "RMS level" in line))
    assert level(out, 1000) < level(src, 1000) - 15                      # the voice: far quieter
    assert level(out, 2000) > level(src, 2000) - 6                       # the instrument: still there
