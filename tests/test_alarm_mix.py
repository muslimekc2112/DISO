"""⏰ The music alarm (when it rings, how the volume rises, the window) and ✨ today's mix."""
import datetime
import time

import pytest
from music_support import FakeBackend, make_wav

from app import alarm, music_search, player

MON_0729 = datetime.datetime(2026, 10, 19, 7, 29)                 # a Monday


def test_the_alarm_rings_once_on_its_days_at_its_time():
    a = alarm.clean({"on": True, "time": "07:30", "days": [0, 1, 2, 3, 4]})
    assert not alarm.due(a, MON_0729)
    assert alarm.due(a, MON_0729 + datetime.timedelta(minutes=1, seconds=20))
    assert not alarm.due(a, MON_0729 + datetime.timedelta(minutes=4))              # missed by far: not later
    assert not alarm.due(dict(a, last="2026-10-19"), MON_0729 + datetime.timedelta(minutes=1))   # once a day
    assert not alarm.due(a, datetime.datetime(2026, 10, 24, 7, 30))                 # Saturday
    assert not alarm.due(dict(a, on=False), MON_0729 + datetime.timedelta(minutes=1))


def test_the_next_ring_and_its_words():
    a = alarm.clean({"on": True, "time": "07:30", "days": [0, 1, 2, 3, 4]})
    assert alarm.next_ring(a, MON_0729) == datetime.datetime(2026, 10, 19, 7, 30)
    fri_eve = datetime.datetime(2026, 10, 23, 20, 0)
    assert alarm.next_ring(a, fri_eve) == datetime.datetime(2026, 10, 26, 7, 30)       # over the weekend
    assert alarm.when_text(datetime.datetime(2026, 10, 20, 7, 30), MON_0729) == "yarın 07:30"
    assert alarm.when_text(datetime.datetime(2026, 10, 19, 7, 30), MON_0729) == "bugün 07:30"
    assert alarm.next_ring(dict(a, on=False), MON_0729) is None


def test_the_volume_rises_slowly():
    assert alarm.volume_at(0, 60, 80) == alarm.START_VOLUME
    assert alarm.volume_at(30, 60, 80) == 42
    assert alarm.volume_at(90, 60, 80) == 80 and alarm.volume_at(0, 0, 80) == 80


def test_bad_settings_are_cleaned():
    a = alarm.clean({"on": "yes", "time": "25:00", "days": [9], "fade": 7, "list": 3})
    assert a == alarm.DEFAULT


@pytest.fixture
def music(app, monkeypatch, tmp_path):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    m = app.music
    songs = [make_wav(tmp_path / f"Barış Manço - {n}.wav") for n in ("Gülpembe", "Dönence")]
    m._pick_files = lambda: songs
    m._add_files()
    return m


@pytest.mark.gui
def test_ringing_plays_the_list_with_the_volume_rising(music, monkeypatch):
    music.set_volume(70)
    music.ring_alarm(alarm.clean({"on": True, "time": "07:30", "days": [0], "list": music.viewed, "fade": 60}))
    assert music.controller.state == "playing" and int(music.volume.get()) == alarm.START_VOLUME
    assert music.store.state["alarm"]["last"] == datetime.date.today().isoformat()
    started, fade, target = music._alarm_ramp
    music._alarm_ramp = (started - 30, fade, target)                      # half a minute later
    music._ramp_alarm()
    assert int(music.volume.get()) == alarm.volume_at(30, 60, 70)
    music._alarm_ramp = (started - 61, fade, target)
    music._ramp_alarm()
    assert int(music.volume.get()) == 70 and music._alarm_ramp is None


@pytest.mark.gui
def test_the_app_rings_even_without_the_music_window(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    rang = []
    app._store().set_state(alarm={"on": True, "time": "07:30", "days": [0, 1, 2, 3, 4, 5, 6]})
    monkeypatch.setattr(alarm, "due", lambda setting: True)
    monkeypatch.setattr("app.music_ui.MusicWindow.ring_alarm", lambda self, s: rang.append(s["time"]))
    app._check_alarm()
    assert app.music is not None and rang == ["07:30"]


@pytest.mark.gui
def test_the_alarm_window_saves_what_is_chosen(music):
    win = music.open_alarm()
    win.on.select()
    win.hour.set("06")
    win.minute.set("45")
    win.days[5].select()
    win._changed()
    saved = alarm.clean(music.store.state["alarm"])
    assert saved["on"] and saved["time"] == "06:45" and 5 in saved["days"]
    assert win.next_label.cget("text").startswith("Sonraki alarm:")
    win.destroy()


class MixApi:
    def search(self, words, filter=None, limit=None):
        return [{"videoId": "seed-" + words, "title": words}]

    def get_watch_playlist(self, videoId=None, radio=False, limit=None):
        n = videoId[-3:]
        return {"tracks": [{"videoId": videoId}] + [
            {"videoId": f"{n}{i}", "title": f"Şarkı {n} {i}", "artists": [{"name": "Sanatçı"}]} for i in range(5)] +
            [{"videoId": "dup", "title": "Gülpembe", "artists": [{"name": "Barış Manço"}]}]}


def test_todays_mix_leaves_out_known_songs_and_keeps_its_order_all_day():
    seeds = [("Barış Manço", "Gülpembe"), ("Sezen Aksu", "Gülümse")]
    have = [("Barış Manço", "Gülpembe")]
    day = datetime.date(2026, 10, 22)
    a = music_search.daily_mix(seeds, have, api=MixApi(), day=day, per=3)
    b = music_search.daily_mix(seeds, have, api=MixApi(), day=day, per=3)
    other = music_search.daily_mix(seeds, have, api=MixApi(), day=day + datetime.timedelta(days=1), per=3)
    assert [r["url"] for r in a] == [r["url"] for r in b] and len(a) == 6
    assert sorted(r["url"] for r in other) == sorted(r["url"] for r in a)
    assert all(r["title"] != "Gülpembe" for r in a) and a.title == "✨ Günün karışığı (22.10)"


@pytest.mark.gui
def test_the_mix_shows_with_the_results(music, monkeypatch):
    real = music_search.daily_mix
    monkeypatch.setattr(music_search, "daily_mix", lambda seeds, have: real(seeds, have, api=MixApi(), per=2))
    assert music.daily_mix()
    end = time.time() + 5
    while not music.results and time.time() < end:
        music._take_answer()
        music.update()
        time.sleep(0.02)
    assert music.results and music.results_title.startswith("✨")
