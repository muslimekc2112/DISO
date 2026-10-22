"""📻 Songs like this one: YouTube Music's radio of a song, shown with the search's results."""
import time

import pytest
from music_support import FakeBackend, make_wav

from app import music_search, player


class FakeApi:
    def __init__(self):
        self.asked = []

    def search(self, words, filter=None, limit=None):
        self.asked.append(("search", words))
        return [{"title": "x"}, {"videoId": "seed", "title": "Gülpembe"}]

    def get_watch_playlist(self, videoId=None, radio=False, limit=None):
        self.asked.append(("radio", videoId, radio))
        return {"tracks": [{"videoId": videoId, "title": "Gülpembe", "artists": [{"name": "Barış Manço"}]},
                           {"videoId": "r1", "title": "Dönence", "artists": [{"name": "Barış Manço"}]},
                           {"videoId": "r2", "title": "Sarı Çizmeli Mehmet Ağa", "artists": [{"name": "Barış Manço"}]}]}


def test_the_radio_of_a_song_leaves_the_song_itself_out():
    api = FakeApi()
    found = music_search.radio("seed", "Barış Manço", "Gülpembe", api=api)
    assert [r["title"] for r in found] == ["Dönence", "Sarı Çizmeli Mehmet Ağa"]
    assert found.title == "📻 Barış Manço - Gülpembe radyosu" and api.asked == [("radio", "seed", True)]


def test_without_its_video_the_song_is_looked_up_by_name():
    api = FakeApi()
    found = music_search.radio("", "Barış Manço", "Gülpembe", api=api)
    assert api.asked[0] == ("search", "Barış Manço Gülpembe") and api.asked[1] == ("radio", "seed", True)
    assert len(found) == 2
    assert music_search.radio("", "", "", api=api) == []


@pytest.mark.gui
def test_the_radio_shows_with_the_results_and_can_go_into_a_list(app, monkeypatch, tmp_path):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    music = app.music
    song = make_wav(tmp_path / "Barış Manço - Gülpembe.wav")
    music._pick_files = lambda: [song]
    music._add_files()
    music.tree.selection_set("0")
    asked = []
    real = music_search.radio
    monkeypatch.setattr(music_search, "radio", lambda v, a, t: asked.append((a, t)) or real("seed", a, t, api=FakeApi()))
    entry = dict((e[0], e[1]) for e in music.track_menu_items() if e)
    entry["📻 Bu şarkıdan radyo"]()
    end = time.time() + 5
    while not music.results and time.time() < end:
        music._take_answer()
        music.update()
        time.sleep(0.02)
    assert asked == [("Barış Manço", "Gülpembe")]
    assert [r["title"] for r in music.results] == ["Dönence", "Sarı Çizmeli Mehmet Ağa"]
    assert music.results_title.startswith("📻") and music.import_btn.winfo_manager() == "grid"


@pytest.mark.gui
def test_with_nothing_to_go_by_the_radio_says_so(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    assert app.music.start_radio() is False
