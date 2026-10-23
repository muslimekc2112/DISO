"""The round after 1.2: the song's wave as its progress bar, the sleep timer fading the music out, the next song
waiting ready so there is no gap between songs."""
import pytest
from music_support import FakeBackend, FakeReader, make_wav

from app import player, tags
from app.player import Controller
from app.waveform import WaveBar, peaks


# ------------------------------------------------------------------------------ 〰 the wave
def test_the_wave_is_the_loudest_moment_of_each_part():
    levels = [0] * 30 + [255] * 30 + [64] * 40
    hs = peaks(levels, 10)
    assert len(hs) == 10 and hs[0] == pytest.approx(0.12) and max(hs) == pytest.approx(1.0)
    assert hs[3] > hs[8] > hs[0]                                       # loud, quieter, silent
    assert peaks([], 10) == [] and peaks([5], 0) == []
    assert len(peaks([1, 2, 3], 50)) == 50                             # more bars than moments: still fills it


@pytest.fixture
def music_app(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app.manager.set_gate(False)
    app._ensure_music()
    return app, app.music


class Ready:
    def __init__(self, levels):
        import numpy as np
        self.result = None if levels is None else (np.zeros((len(levels), 64), dtype=np.uint8),
                                                   np.array(levels, dtype=np.uint8))

    def want(self, path):
        pass

    def get(self, path):
        return self.result

    def busy(self, path):
        return False


@pytest.mark.gui
def test_the_progress_bar_shows_the_songs_wave_and_a_click_goes_there(music_app, tmp_path):
    _, music = music_app
    assert isinstance(music.seek, WaveBar)
    music.analyzer = Ready(None)                                       # the song is not analysed yet
    song = make_wav(tmp_path / "Dalga.wav")
    music._pick_files = lambda: [song]
    music._add_files()
    music.tree.selection_set("0")
    music._play_selected()
    backend = music.controller.backend.active
    backend.length = 100000
    music.deiconify()
    music.update()
    assert not music.seek._bars                                        # not analysed yet: a plain line
    music.analyzer = Ready([10, 200, 255, 30] * 50)
    backend.position = 25000
    music._update_status()
    music.update()
    bars = music.seek._bars
    assert len(bars) > 20 and music.seek.length_ms == 100000
    played, rest, _ = music.seek._colours()
    colour = lambda i: music.seek.canvas.itemcget(bars[i], "fill")     # noqa: E731
    assert colour(0) == played and colour(len(bars) - 1) == rest
    quarter = len(bars) // 4
    assert colour(quarter - 2) == played and colour(quarter + 2) == rest
    w = music.seek.canvas.winfo_width()
    seen = []
    music.seek._press(type("E", (), {"x": w * 3 // 4, "y": 5})())     # press and drag …
    music.seek._drag(type("E", (), {"x": w * 3 // 4, "y": 5})())
    seen.append(music.pos_label.cget("text"))
    music.seek._release(type("E", (), {"x": w * 3 // 4, "y": 5})())   # … let go: the song goes there
    assert abs(backend.position - 75000) < 2500 and not music._dragging
    assert seen[0].startswith("1:1")                                   # the time while dragging (≈ 1:15)
    music.seek._move(type("E", (), {"x": w // 2, "y": 5})())           # hovering tells the time there
    assert music.seek.canvas.itemcget(music.seek._hover_items[1], "text") == "0:50"
    music.player_box.configure(fg_color=("#203040", "#203040"))       # the block's colour changes …
    music.update()
    assert music.seek.canvas.cget("bg") == "#203040"                   # … the wave's background follows
    music._stop()
    music._update_status()
    assert not music.seek._bars and music.seek.get() == 0


# ------------------------------------------------------------------------------ 😴 the sleep timer fades out
@pytest.mark.gui
def test_the_sleep_timer_fades_the_music_out_and_gives_the_volume_back(music_app, tmp_path):
    _, music = music_app
    song = make_wav(tmp_path / "Uyku.wav")
    music._pick_files = lambda: [song]
    music._add_files()
    music.tree.selection_set("0")
    music._play_selected()
    music.set_volume(80)
    music._set_sleep("15 dk")
    assert music._sleep_fade == 120
    at = music.sleep_at
    c = music.controller
    music._check_sleep(now=at - 300)                                   # 5 minutes left: as loud as before
    assert c.volume == 80
    volumes = []
    for left in (110, 90, 60, 30, 10, 2):
        music._check_sleep(now=at - left)
        volumes.append(c.volume)
    assert volumes == sorted(volumes, reverse=True) and volumes[0] < 80 and volumes[-1] <= 1
    assert int(music.volume.get()) == 80                               # the user's volume is not touched
    music._check_sleep(now=at + 1)
    assert c.state == "stopped" and c.volume == 80                     # stopped, the volume is the user's again
    music._play_selected()
    music._set_sleep("30 dk")
    music._check_sleep(now=music.sleep_at - 30)
    assert c.volume < 80
    music._set_sleep("😴 Uyku: kapalı")                                 # called off while fading: loud again
    assert c.volume == 80


@pytest.mark.gui
def test_after_the_song_the_last_seconds_fade(music_app, tmp_path):
    _, music = music_app
    song = make_wav(tmp_path / "Son.wav")
    music._pick_files = lambda: [song]
    music._add_files()
    music.tree.selection_set("0")
    music._play_selected()
    backend = music.controller.backend.active
    backend.length = 60000
    music.set_volume(70)
    music._set_sleep("Parça bitince")
    backend.position = 40000
    music._check_sleep()
    assert music.controller.volume == 70
    backend.position = 55000                                           # 5 s left of 10
    music._check_sleep()
    assert 10 < music.controller.volume < 30


# ------------------------------------------------------------------------------ ⏭ no gap between songs
@pytest.fixture
def songs(tmp_path):
    return [{"path": make_wav(tmp_path / f"{n}.wav"), "title": n} for n in ("a", "b", "c")]


def gapless(songs):
    c = Controller(FakeBackend(), spare=FakeBackend())
    c.set_tracks(songs)
    c.backend.length = c.spare.length = 60000
    return c


def test_the_next_song_waits_ready_and_starts_the_moment_this_one_ends(songs):
    c = gapless(songs)
    c.play_index(0)
    first, second = c.backend, c.spare
    first.position = 50000
    c.tick()
    assert c.ready_next() is None and second.loaded is None            # 10 s left: not yet
    first.position = 58000
    c.tick()                                                           # 2 s left: opened, waiting
    assert c.ready_next()[1] == 1 and second.loaded == songs[1]["path"] and not second.playing
    assert c.current_title() == "a" and first.playing
    first.position = 60000 - 20                                        # the last moment
    c.tick()
    assert c.current_title() == "b" and c.backend is second and second.playing
    assert first.loaded is None and c.spare is first                   # the old one is closed, ready for the next


def test_a_change_meanwhile_lets_the_waiting_song_go(songs):
    c = gapless(songs)
    c.play_index(0)
    c.backend.position = 58000
    c.tick()
    waiting = c.spare
    assert c.ready_next() is not None
    c.seek_fraction(0.1)                                               # sought back: not the end any more
    assert c.ready_next() is None and waiting.loaded is None
    c.backend.position = 58000
    c.tick()
    c.play_next([songs[2]])                                            # "play next": another song comes next
    assert c.ready_next() is None
    c.backend.position = 58000
    c.tick()
    assert c.ready_next()[0] == "queue"
    c.backend.position = 59990
    c.tick()
    assert c.current_title() == "c"


def test_repeat_one_waits_with_the_same_song_and_cross_fade_is_left_alone(songs):
    c = gapless(songs)
    c.repeat = "Tek"
    c.play_index(1)
    c.backend.position = 58000
    c.tick()
    assert c.ready_next()[1] == 1
    c.repeat = "Kapalı"                                                 # changed meanwhile: the waiting one is wrong
    c.backend.position = 59990
    c.tick()
    assert c.ready_next() is None
    c2 = gapless(songs)
    c2.fade_ms = 3000                                                  # with a cross-fade the fade does it
    c2.play_index(0)
    c2.backend.position = 58500
    c2.tick()
    assert c2.ready_next() is None and c2.fading


def test_the_end_of_the_list_and_short_songs_have_nothing_waiting(songs):
    c = gapless(songs)
    c.play_index(2)                                                     # last, repeat off
    c.backend.position = 59000
    c.tick()
    assert c.ready_next() is None
    c2 = gapless(songs)
    c2.backend.length = 3000                                            # a very short song: plays normally
    c2.play_index(0)
    c2.backend.position = 2500
    c2.tick()
    assert c2.ready_next() is None


# ------------------------------------------------------------------------------ 📺 series mode
from test_extension import app as bridge_app, needs_node, run  # noqa: E402,F401 - the bridge fixture


@needs_node
def test_series_mode_opens_each_episode_catches_its_video_and_sends_it_named(bridge_app):  # noqa: F811
    api, b = bridge_app
    data = run(b.port, "series")
    answer, log = data["answer"], data["log"]
    assert [e["episode"] for e in answer["list"]["episodes"]] == [1, 2, 3]        # in order, only this site's
    assert answer["list"]["series"] == "Kuruluş Osman"
    assert answer["start"]["ok"] and not answer["again"]["ok"]                    # one series at a time
    status = answer["status"]
    assert not status["running"] and status["sent"] == 3 and status["missed"] == 1
    assert "1" in status["text"]                                                   # "… (1 without a video)"
    win = log["windows"][0]
    assert win["type"] == "popup" and win["focused"] is False and log["closed"] == [500]
    assert {"muted": True} in log["tabUpdates"] and log["poked"] >= 1           # muted; the players were started
    titles = [a["extra"].get("title") for a in api.added]
    assert titles == ["Kuruluş Osman - S03 Bölüm 01", "Kuruluş Osman - S03 Bölüm 02", "Kuruluş Osman - S03 Bölüm 03"]
    assert all(a["extra"].get("subdir") == "Kuruluş Osman" for a in api.added)    # a folder of its own
    first, second = api.added[0], api.added[1]
    assert first["urls"] == ["http://cdn.example/kurulus-osman/3-sezon-1-bolum/master.m3u8"]
    assert first["extra"]["referer"] == PLAYER and first["extra"]["quality"] == "720p"
    assert second["urls"] == ["http://dizi.example/kurulus-osman/3-sezon-2-bolum"]  # no video came: its page
    assert first["kind"] == second["kind"] == "video"


@needs_node
def test_series_mode_can_be_stopped(bridge_app):  # noqa: F811
    api, b = bridge_app
    status = run(b.port, "series-stop")["answer"]["status"]
    assert not status["running"] and status["sent"] < 3 and "Durduruldu" in status["text"]


PLAYER = "http://player.example/embed/77"


def test_an_episode_goes_into_the_series_folder(tmp_path):
    from app.manager import DownloadManager
    from app.models import Settings
    item = DownloadManager._make_item("http://x/1", Settings(), str(tmp_path), extra={"subdir": "Kuruluş: Osman?"})
    assert item.folder.startswith(str(tmp_path)) and "Kuruluş" in item.folder and "?" not in item.folder


# ------------------------------------------------------------------------------ 🎞 a playlist behind another name
@needs_node
def test_a_playlist_with_another_name_is_found_by_what_it_starts_with(bridge_app):  # noqa: F811
    api, b = bridge_app
    answer = run(b.port, "hidden")["answer"]
    assert answer["before"]["media"] == []                                        # ".txt", "text/plain": not by its name
    assert answer["told"]["ok"] and not answer["fake"]["ok"]
    m = answer["after"]["media"]
    assert len(m) == 1 and m[0]["kind"] == "hls" and m[0]["url"] == "http://cdn.example/v/list.txt?t=1"
    assert m[0]["referer"] == PLAYER and m[0]["origin"] == "http://player.example" and m[0]["cookies"] == "pl=1"


@needs_node
def test_the_page_script_and_the_new_helpers_pass_their_node_tests():
    import os
    import subprocess
    from test_extension import JS, NODE
    for name in ("sniff.test.js", "lib.test.js"):
        r = subprocess.run([NODE, "--test", os.path.join(JS, name)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0 and "fail 0" in r.stdout, r.stdout + r.stderr


def test_the_page_script_runs_in_the_page_itself_in_both_browsers():
    import json
    import os
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "browser_extension")
    for name in ("manifest.json", "manifest.firefox.json"):
        m = json.load(open(os.path.join(root, name), encoding="utf-8"))
        scripts = {tuple(c["js"]): c for c in m["content_scripts"]}
        sniff = scripts[("sniff.js",)]
        assert sniff["world"] == "MAIN" and sniff["all_frames"] and sniff["run_at"] == "document_start"
    firefox = json.load(open(os.path.join(root, "manifest.firefox.json"), encoding="utf-8"))
    assert firefox["browser_specific_settings"]["gecko"]["strict_min_version"] == "128.0"   # (the page's own world)
