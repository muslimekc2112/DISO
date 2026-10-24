"""📊 Listening statistics: every listening is logged with its name and length; the summary of a period
(songs, artists, hours, days in a row) and the window that shows it."""
import datetime

import pytest
from music_support import FakeBackend, make_wav

from app import player, playlists, stats_ui


def _at(y, m, d, h=12):
    return datetime.datetime(y, m, d, h).timestamp()


def test_listenings_are_logged_and_summed_up(tmp_path):
    store = playlists.PlaylistStore(str(tmp_path / "p.json"))
    a = make_wav(tmp_path / "Barış Manço - Gülpembe.wav")
    b = make_wav(tmp_path / "Sezen Aksu - Gülümse.wav")
    store.add("Liste", [a, b])
    ta, tb = store.tracks("Liste")
    ta["duration"], tb["duration"] = 240000, 180000
    for when in (_at(2026, 10, 1, 22), _at(2026, 10, 2, 22), _at(2026, 10, 3, 9)):
        store.count_play(a, when=when, track=ta)
    store.count_play(b, when=_at(2026, 10, 5, 22), track=tb)
    store.count_play(b, when=_at(2025, 12, 31, 23), track=tb)              # last year
    s = store.summary(_at(2026, 10, 1, 0))
    assert s["plays"] == 4 and s["ms"] == 3 * 240000 + 180000
    assert s["songs"][0] == ("Gülpembe", "Barış Manço", 3) and s["songs"][1] == ("Gülümse", "Sezen Aksu", 1)
    assert s["artists"][0] == ("Barış Manço", 3, 720000)
    assert s["hours"][22] == 3 and s["hours"][9] == 1
    assert s["days"] == 4 and s["streak"] == 3                             # 1, 2, 3 October in a row
    again = playlists.PlaylistStore(str(tmp_path / "p.json"))              # kept in the file
    assert len(again.log) == 5 and again.summary(0)["plays"] == 5


def test_all_time_counts_the_plays_from_before_the_log(tmp_path):
    store = playlists.PlaylistStore(str(tmp_path / "p.json"))
    a = make_wav(tmp_path / "Barış Manço - Dönence.wav")
    store.add("Liste", [a])
    store.stats[playlists.file_key(a)] = {"plays": 7, "last": 1.0, "first": 1.0}   # an older DISO counted these
    s = store.summary(0)
    assert s["plays"] == 7 and s["songs"] == [("Dönence", "Barış Manço", 7)]
    assert store.summary(_at(2026, 1, 1))["plays"] == 0


def test_the_log_is_cleaned_and_kept_short():
    assert playlists._clean_log([{"t": 1, "title": "a"}, {"t": "x", "title": "b"}, "junk",
                                 {"t": 2, "title": "c", "ms": -5}]) == [
        {"t": 1.0, "k": "", "title": "a", "artist": "", "ms": 0}, {"t": 2.0, "k": "", "title": "c", "artist": "", "ms": 0}]
    assert len(playlists._clean_log([{"t": i, "title": "x"} for i in range(playlists.MAX_LOG + 10)])) == playlists.MAX_LOG


def test_periods_start_at_the_month_and_the_year():
    now = _at(2026, 10, 22, 15)
    assert stats_ui.period_start("Bu ay", now) == _at(2026, 10, 1, 0)
    assert stats_ui.period_start("Bu yıl", now) == _at(2026, 1, 1, 0)
    assert stats_ui.period_start("Tüm zamanlar", now) == 0
    assert stats_ui.duration_text(3 * 3600000 + 5 * 60000) == "3 sa 5 dk" and stats_ui.duration_text(59000) == "0 dk"


@pytest.mark.gui
def test_the_window_shows_the_period(app, monkeypatch, tmp_path):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    music = app.music
    song = make_wav(tmp_path / "Barış Manço - Gülpembe.wav")
    music._pick_files = lambda: [song]
    music._add_files()
    import time
    music.store.count_play(song, when=time.time(), track={"title": "Barış Manço - Gülpembe", "duration": 200000})
    win = music.open_stats()
    win.update()
    assert win.big["plays"][0].cget("text") == "1" and win.big["artists"][0].cget("text") == "1"
    import customtkinter as ctk
    texts = [w.cget("text") for w in win.body.winfo_children() if isinstance(w, ctk.CTkLabel)]
    assert "🎵 En çok dinlediğin şarkılar" in texts
    win.period.set("Tüm zamanlar")
    win.show()
    assert win.big["plays"][0].cget("text") == "1"
    assert music.open_stats() is win
    win.destroy()
