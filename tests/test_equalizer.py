"""🎛 The equalizer: settings, the ffmpeg filter they make, and the backend that switches to ffmpeg + SDL
while the equalizer is on (Windows' MCI stays for a flat one), going on from the same moment."""
import os
import re
import subprocess
import time

import pytest
from music_support import FakeBackend, FakeEqBackend

from app import equalizer, player, playlists
from app.utils import subprocess_flags


# ------------------------------------------------------------------------------ settings
def test_settings_are_cleaned_and_named():
    assert equalizer.clean([3.4, -20, 20, 0, 0, 0, 0, 0]) == [3, -12, 12, 0, 0, 0, 0, 0]
    assert equalizer.clean([1, 2]) == [0] * 8 and equalizer.clean(None) == [0] * 8 and equalizer.clean("x") == [0] * 8
    assert equalizer.is_flat([0] * 8) and not equalizer.is_flat(equalizer.PRESETS["Rock"])
    assert equalizer.preset_of(equalizer.PRESETS["Vokal"]) == "Vokal"
    assert equalizer.preset_of([1, 0, 0, 0, 0, 0, 0, 0]) == equalizer.CUSTOM
    assert all(len(v) == len(equalizer.BANDS) for v in equalizer.PRESETS.values())


def test_the_filter():
    assert equalizer.ffmpeg_filter([0] * 8) == ""                   # flat: the sound is not touched
    f = equalizer.ffmpeg_filter([6, 0, 0, 0, 0, 0, 0, -3])
    assert f == "volume=-3.6dB,equalizer=f=60:t=o:w=1.2:g=6,equalizer=f=15000:t=o:w=1.2:g=-3,alimiter=limit=0.97:level=0"
    assert not equalizer.ffmpeg_filter([-4] * 8).startswith("volume")  # only cut: no headroom needed


def ffmpeg():
    from app.tags import _tool
    found = _tool("ffmpeg")
    if not found:
        here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ffmpeg", "ffmpeg.exe")
        found = here if os.path.isfile(here) else None
    return found


def loudness(tone_hz, af):
    """Mean volume (dB) of a pure tone after the filter."""
    args = [ffmpeg(), "-hide_banner", "-f", "lavfi", "-i", f"sine=frequency={tone_hz}:duration=1:sample_rate=44100"]
    args += (["-af", af + ",volumedetect"] if af else ["-af", "volumedetect"]) + ["-f", "null", "-"]
    out = subprocess.run(args, capture_output=True, text=True, timeout=60, **subprocess_flags()).stderr
    return float(re.search(r"mean_volume: (-?[\d.]+) dB", out).group(1))


@pytest.mark.skipif(ffmpeg() is None, reason="no ffmpeg")
def test_ffmpeg_really_changes_the_sound_as_asked():
    bass = equalizer.ffmpeg_filter(equalizer.PRESETS["Bas güçlü"])
    low_before, low_after = loudness(60, ""), loudness(60, bass)
    high_before, high_after = loudness(8000, ""), loudness(8000, bass)
    assert low_after - low_before > 2.5                                   # the bass is louder ...
    assert high_after < high_before                                       # ... the rest a little quieter (headroom)
    treble = equalizer.ffmpeg_filter(equalizer.PRESETS["Tiz güçlü"])
    assert loudness(12000, treble) - loudness(12000, "") > 2


# ------------------------------------------------------------------------------ the switching backend
def switching():
    made = []

    def make_eq():
        made.append(FakeEqBackend("eq"))
        return made[-1]
    return player.SwitchingBackend(FakeBackend("mci"), make_eq), made


def test_flat_plays_on_the_plain_backend_and_the_eq_one_is_not_even_made():
    b, made = switching()
    assert b.load("a.mp3") and b.active is b.plain and made == []
    assert b.set_filter("") and b.active is b.plain and made == []


def test_turning_it_on_goes_on_from_the_same_moment_and_back():
    b, made = switching()
    b.set_volume(35)
    b.load("a.mp3")
    b.play()
    b.plain.position = 2500
    assert b.set_filter("equalizer=f=60:t=o:w=1:g=5")
    eq = made[0]
    assert b.active is eq and eq.filter.startswith("equalizer") and eq.loaded == "a.mp3"
    assert eq.position == 2500 and eq.playing and eq.volume == 35
    assert b.plain.loaded is None                                         # the old one let go of the file
    b.set_filter("equalizer=f=60:t=o:w=1:g=8")                            # another setting: same backend
    assert b.active is eq and eq.filter.endswith("g=8") and len(made) == 1
    eq.position = 4000
    b.set_filter("")                                    # flat in the middle of the song: no switch to be heard
    assert b.active is eq and eq.filter == "" and eq.playing and eq.position == 4000
    b.load("b.mp3")                                     # the next song is on MCI again
    assert b.active is b.plain and b.plain.loaded == "b.mp3"


def test_switching_while_paused_stays_paused_and_resume_starts_the_new_one():
    b, made = switching()
    b.load("a.mp3")
    b.play()
    b.plain.position = 1200
    b.pause()
    b.set_filter("equalizer=f=60:t=o:w=1:g=5")
    eq = made[0]
    assert not eq.playing and eq.position == 1200
    b.resume()
    assert eq.playing                                                     # "resume" of a fresh backend = play


def test_reading_what_only_the_backend_under_it_has():
    b, _ = switching()
    assert b.alias == "mci" and b.last_error == ""


def test_without_a_sound_output_for_it_the_equalizer_says_no_and_music_goes_on():
    def broken():
        raise OSError("no sound output: no pygame")
    b = player.SwitchingBackend(FakeBackend("mci"), broken)
    b.load("a.mp3")
    b.play()
    assert b.set_filter("equalizer=f=60:t=o:w=1:g=5") is False
    assert b.active is b.plain and b.plain.playing


def test_where_ffmpeg_plays_anyway_the_filter_goes_straight_to_it():
    own = FakeEqBackend("sdl")
    b = player.SwitchingBackend(None, lambda: own)
    assert b.active is own
    b.load("a.mp3")
    b.set_filter("x")
    assert b.active is own and own.filter == "x" and own.loaded == "a.mp3"


def test_the_setting_is_kept_with_the_playlists(tmp_path):
    path = str(tmp_path / "p.json")
    store = playlists.PlaylistStore(path)
    assert store.state["eq"] == [0] * 8
    store.set_state(eq=equalizer.PRESETS["Rock"])
    again = playlists.PlaylistStore(path)
    assert again.state["eq"] == equalizer.PRESETS["Rock"]


# ------------------------------------------------------------------------------ in the music window
@pytest.fixture
def music(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    return app.music


@pytest.mark.gui
def test_a_preset_puts_the_filter_on_both_voices_and_is_remembered(music):
    win = music.open_eq()
    assert music.open_eq() is win
    win._preset("Rock")
    c = music.controller
    for backend in (c.backend, c.spare):
        assert isinstance(backend.active, FakeEqBackend) and backend.active.filter == equalizer.ffmpeg_filter(equalizer.PRESETS["Rock"])
    assert music.store.state["eq"] == equalizer.PRESETS["Rock"] and win.status.cget("text") == "Ekolayzır açık"
    win._preset(equalizer.FLAT)
    assert not isinstance(c.backend.active, FakeEqBackend) and music.store.state["eq"] == [0] * 8


@pytest.mark.gui
def test_moving_a_slider_makes_it_custom_and_applies_a_moment_later(music):
    win = music.open_eq()
    win._moved(0, 4.2)
    assert win.preset_menu.get() == equalizer.CUSTOM and win.values[0].cget("text") == "+4"
    assert music.store.state["eq"] == [0] * 8                             # not yet: more moves may follow
    end = time.time() + 3
    while time.time() < end and music.store.state["eq"][0] != 4:
        music.update()
        time.sleep(0.02)
    assert music.store.state["eq"] == [4, 0, 0, 0, 0, 0, 0, 0]


@pytest.mark.gui
def test_a_saved_setting_is_on_from_the_start(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    app._store().set_state(eq=equalizer.PRESETS["Vokal"])
    assert app._ensure_music()
    assert app.music.controller.backend.active.filter == equalizer.ffmpeg_filter(equalizer.PRESETS["Vokal"])
    assert "🎛 Ekolayzır…" in [e[0] for e in app.music.player_menu_items() if e]
