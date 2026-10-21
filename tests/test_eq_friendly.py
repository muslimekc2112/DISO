"""🎛 The friendlier equalizer: Bas / Orta / Tiz on top of the eight bands ("Gelişmiş"), one change of the
sound per drag, and a new setting that does not stop the music (ffmpeg + SDL change over without a gap)."""
import os
import subprocess
import time

import pytest
from music_support import FakeBackend
from test_equalizer import music  # noqa: F401 - the fixture

from app import equalizer, player, utils


# ------------------------------------------------------------------------------ Bas / Orta / Tiz
def test_the_simple_controls_move_their_bands_and_keep_an_experts_shape():
    gains = [0] * 8
    gains = equalizer.set_simple(gains, 0, 6)                             # Bas
    assert gains == [6, 6, 0, 0, 0, 0, 0, 0] and equalizer.simple_values(gains) == [6, 0, 0]
    shaped = [0, 0, 2, 4, 6, 0, 0, 0]                                     # Orta, shaped by hand in "Gelişmiş"
    assert equalizer.simple_values(shaped)[1] == 4
    moved = equalizer.set_simple(shaped, 1, 6)
    assert moved[2:5] == [4, 6, 8] and moved[:2] == [0, 0] and moved[5:] == [0, 0, 0]
    assert equalizer.set_simple([0] * 8, 2, 40)[5:] == [12, 12, 12]       # within the limits
    names = [name for name, _, _ in equalizer.SIMPLE]
    assert names == ["Bas", "Orta", "Tiz"]
    covered = sorted(i for _, _, bands in equalizer.SIMPLE for i in bands)
    assert covered == list(range(len(equalizer.BANDS)))                   # every band belongs to one control


@pytest.mark.gui
def test_the_window_shows_bas_orta_tiz_and_the_bands_only_in_advanced(music):  # noqa: F811
    music.store.state["eq_advanced"] = False
    win = music.open_eq()
    win.update()
    assert not win.bands.winfo_ismapped()
    win._moved_simple(2, 5)                                               # Tiz +5
    assert win.gains[5:] == [5, 5, 5] and win.simple_values[2].cget("text") == "+5 dB"
    assert [s.get() for s in win.sliders][5:] == [5, 5, 5]                 # the bands follow, hidden or not
    win.advanced_var.set(True)
    win._toggle_advanced()
    win.update()
    assert win.bands.winfo_ismapped() and music.store.state["eq_advanced"] is True
    win._moved(0, 7)                                                      # 60 Hz by hand: Bas shows the middle
    assert win.simple_values[0].cget("text") == "+4 dB"
    win.destroy()


@pytest.mark.gui
def test_dragging_changes_the_sound_once(music, monkeypatch):  # noqa: F811
    applied = []
    monkeypatch.setattr(music, "apply_eq", lambda gains, remember=True: applied.append(list(gains)) or True)
    win = music.open_eq()
    for v in range(1, 9):                                                 # a drag: many small moves
        win._moved_simple(0, v)
    end = time.time() + 3
    while time.time() < end and not applied:
        music.update()
        time.sleep(0.02)
    music.update()
    assert applied == [[8, 8, 0, 0, 0, 0, 0, 0]]
    win.destroy()


# ------------------------------------------------------------------------------ the real ffmpeg + SDL player
def _sdl_or_skip():
    pytest.importorskip("pygame")
    if not utils.find_ffmpeg():
        pytest.skip("needs ffmpeg")
    os.environ["SDL_AUDIODRIVER"] = "dummy"          # no sound comes out of the tests
    from app import sdl_player
    return sdl_player


@pytest.fixture(scope="module")
def long_song(tmp_path_factory):
    if not utils.find_ffmpeg():
        pytest.skip("needs ffmpeg")
    path = str(tmp_path_factory.mktemp("eq") / "song.opus")
    subprocess.run([utils.find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=duration=8",
                    "-c:a", "libopus", path], check=True, **utils.subprocess_flags())
    return path


def test_a_new_setting_does_not_stop_or_move_the_music(long_song):
    sdl = _sdl_or_skip()
    backend = sdl.SdlBackend("eq_test")
    try:
        assert backend.load(long_song)
        backend.play()
        end = time.monotonic() + 6
        while backend.position_ms() < 500 and time.monotonic() < end:
            time.sleep(0.02)
        seen = []
        for g in (3, 6, 9, -3, 0, 5):                                     # one setting after another
            backend.set_filter(equalizer.ffmpeg_filter([g] * 8))
            for _ in range(10):
                seen.append(backend.position_ms())
                assert backend.is_playing()
                time.sleep(0.03)
        assert seen == sorted(seen)                                       # never back, never a restart
        assert seen[-1] - seen[0] > 1000                                  # and it went on all the time
        assert backend._next_proc is None or backend._next_proc.poll() is None
    finally:
        backend.close()


def test_turning_it_on_mid_song_hands_over_at_the_same_moment(long_song, monkeypatch):
    sdl = _sdl_or_skip()
    clock = {"t": 0}

    class Plain(FakeBackend):                                             # stands in for MCI, its clock runs
        def position_ms(self):
            return self.position + int((time.monotonic() - clock["t"]) * 1000) if self.playing else self.position

    plain = Plain()
    b = player.SwitchingBackend(plain, lambda: sdl.SdlBackend("eq_hand"))
    try:
        assert b.load(long_song)
        clock["t"] = time.monotonic()
        b.play()
        plain.position = 0
        time.sleep(0.4)
        before = plain.position_ms()
        assert b.set_filter(equalizer.ffmpeg_filter([4] * 8))
        assert b.active is not plain and b.active.is_playing()
        assert before <= b.active.position_ms() <= before + 1200          # it goes on, about where it was
    finally:
        b.close() if hasattr(b, "close") else None
        b.active.close()
