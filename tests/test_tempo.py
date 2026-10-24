"""⏩ Playing speed and pitch: the ffmpeg filter, the real ffmpeg + SDL player at another speed, and MCI handing
over to it (and back for the next song)."""
import time

import pytest
from music_support import FakeBackend
from test_eq_friendly import _sdl_or_skip, long_song  # noqa: F401 - the fixture

from app import equalizer, player, sdl_player


def test_the_filter_for_each_speed_and_pitch():
    assert sdl_player.tempo_filter(1, 0) == ""
    assert sdl_player.tempo_filter(1.5) == "atempo=1.500000"
    assert sdl_player.tempo_filter(4) == "atempo=2.0,atempo=2.0"                  # older builds: 0.5–2 per step
    assert sdl_player.tempo_filter(0.25) == "atempo=0.5,atempo=0.5"
    higher = sdl_player.tempo_filter(1, 12)                                       # an octave up, same speed
    assert "asetrate=88200.000" in higher and higher.endswith("atempo=0.5")
    assert sdl_player.clean_tempo(9, 40) == (4.0, 12)
    assert sdl_player.clean_tempo(0.01, -40) == (0.25, -12)
    assert sdl_player.clean_tempo("x", None) == (1.0, 0)
    assert sdl_player.clean_tempo(float("nan"), 0) == (1.0, 0)


def _wait_until(backend, ms, limit=6):
    end = time.monotonic() + limit
    while backend.position_ms() < ms and time.monotonic() < end:
        time.sleep(0.02)


def test_twice_as_fast_goes_twice_as_far_and_the_position_stays_the_songs(long_song):  # noqa: F811
    sdl = _sdl_or_skip()
    backend = sdl.SdlBackend("tempo_test")
    try:
        assert backend.load(long_song)
        backend.play()
        _wait_until(backend, 300)
        at = backend.position_ms()
        backend.set_tempo(2.0)
        assert backend.is_playing()
        assert abs(backend.position_ms() - at) < 300                              # it goes on from there
        start, t0 = backend.position_ms(), time.monotonic()
        time.sleep(1.0)
        went = backend.position_ms() - start
        took = (time.monotonic() - t0) * 1000
        assert 1.6 * took < went < 2.4 * took
        backend.set_filter(equalizer.ffmpeg_filter([5] * 8))                     # the equalizer on top of it
        seen = []
        for _ in range(15):
            seen.append(backend.position_ms())
            time.sleep(0.03)
        assert seen == sorted(seen) and backend.is_playing()
        backend.set_tempo(4.0, 3)                                                 # faster and higher: plays to the end
        end = time.monotonic() + 8
        while not backend.finished() and time.monotonic() < end:
            time.sleep(0.05)
        assert backend.finished()
    finally:
        backend.close()


def test_slower_while_paused_starts_slow_and_where_it_was(long_song):  # noqa: F811
    sdl = _sdl_or_skip()
    backend = sdl.SdlBackend("tempo_pause")
    try:
        assert backend.load(long_song)
        backend.play()
        _wait_until(backend, 400)
        backend.pause()
        at = backend.position_ms()
        backend.set_tempo(0.5)
        assert abs(backend.position_ms() - at) < 50
        backend.resume()
        _wait_until(backend, at + 50)
        start, t0 = backend.position_ms(), time.monotonic()
        time.sleep(0.8)
        went = backend.position_ms() - start
        took = (time.monotonic() - t0) * 1000
        assert 0.3 * took < went < 0.7 * took
    finally:
        backend.close()


def test_mci_hands_over_for_another_speed_and_the_next_song_is_on_mci_again(long_song, monkeypatch):  # noqa: F811
    sdl = _sdl_or_skip()

    class Plain(FakeBackend):
        pass

    plain = Plain()
    b = player.SwitchingBackend(plain, lambda: sdl.SdlBackend("tempo_hand"))
    try:
        assert b.load(long_song.replace(".opus", ".opus"))
        # an Opus file never plays on MCI; a pretend MP3 shows the switch
        monkeypatch.setattr(player, "needs_ffmpeg", lambda path: False)
        b._use(plain)
        assert b.load(long_song) and b.active is plain
        b.play()
        assert b.set_tempo(1.5, 0)
        assert b.active is b.eq and b.eq._speed == 1.5
        assert b.set_tempo(1.0, 0)                       # back to normal mid-song: stays on ffmpeg (no jump)
        assert b.active is b.eq
        assert b.load(long_song) and b.active is plain   # the next song is MCI's again
        assert b.set_tempo(2.0, 2)
        b.close()
        assert b.load(long_song) and b.active is b.eq    # at another speed the next song stays on ffmpeg
        assert b.eq._speed == 2.0 and b.eq._pitch == 2
    finally:
        b.active.close()
        if b.eq is not None:
            b.eq.close()


def test_without_the_ffmpeg_player_the_speed_cannot_change():
    def broken():
        raise OSError("no sound device")
    b = player.SwitchingBackend(FakeBackend(), broken)
    assert not b.set_tempo(2.0)
    assert b.tempo == (1.0, 0)
