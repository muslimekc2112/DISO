"""Where the lyrics come from: YouTube Music first (the video's own lyrics), LRCLIB only to add the line
times when it is the same text, and never another song that only has the same name."""
import time
import types

import pytest
from music_support import make_wav

from app import lyrics

GULPEMBE = "Sen gülünce güller açar, gülpembe\nBülbüller seni söyler, biz dinlerdik, gülpembe\nSen gelince bahar gelir"
GULPEMBE_LRC = ("[00:10.00]Sen gülünce güller açar, gülpembe\n[00:16.00]Bülbüller seni söyler, biz dinlerdik, gülpembe\n"
                "[00:22.00]Sen gelince bahar gelir")
OTHER_LRC = "[00:05.00]Bambaşka bir şarkının\n[00:09.00]bambaşka sözleri burada\n[00:12.00]hiç benzemiyor"


class FakeYTM:
    """The few calls of ytmusicapi.YTMusic DISO makes."""

    def __init__(self, text=GULPEMBE, timed=None, songs=None, browse="MPLYt_x"):
        self.text, self.timed, self.songs, self.browse = text, timed, songs or [], browse
        self.asked = []

    def search(self, query, filter=None, limit=None):
        self.asked.append(("search", query, filter))
        return self.songs

    def get_watch_playlist(self, videoId=None):
        self.asked.append(("watch", videoId))
        return {"lyrics": self.browse}

    def get_lyrics(self, browse, timestamps=False):
        self.asked.append(("lyrics", browse, timestamps))
        if self.timed:
            return {"lyrics": self.timed, "hasTimestamps": True}
        return {"lyrics": self.text, "hasTimestamps": False}


def lrclib(answer):
    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return answer

    return lambda url, params=None, **k: R()


def rec(name, synced="", plain="", artist="Barış Manço", duration=312):
    return {"trackName": name, "artistName": artist, "duration": duration, "syncedLyrics": synced, "plainLyrics": plain}


# ------------------------------------------------------------------------------ the video id
@pytest.mark.parametrize("url, vid", [
    ("https://www.youtube.com/watch?v=zd8IFDgQCUc", "zd8IFDgQCUc"),
    ("https://music.youtube.com/watch?v=zd8IFDgQCUc&list=OLAK", "zd8IFDgQCUc"),
    ("https://youtu.be/zd8IFDgQCUc?t=3", "zd8IFDgQCUc"), ("https://www.youtube.com/shorts/zd8IFDgQCUc", "zd8IFDgQCUc"),
    ("https://example.com/file.mp3", ""), ("", "")])
def test_the_video_id_of_a_link(url, vid):
    assert lyrics.video_id_of(url) == vid


# ------------------------------------------------------------------------------ YouTube Music
def test_a_found_song_gets_its_own_videos_lyrics():
    api = FakeYTM()
    assert lyrics.ytmusic_lyrics("zd8IFDgQCUc", api=api) == (GULPEMBE, False)
    assert api.asked[0] == ("watch", "zd8IFDgQCUc") and not [a for a in api.asked if a[0] == "search"]


def test_timed_lyrics_of_youtube_music_become_lrc():
    lines = [types.SimpleNamespace(text="Sen gülünce", start_time=10500), types.SimpleNamespace(text="güller açar", start_time=65020)]
    text, timed = lyrics.ytmusic_lyrics("zd8IFDgQCUc", api=FakeYTM(timed=lines))
    assert timed and lyrics.parse(text)["synced"] == [(10500, "Sen gülünce"), (65020, "güller açar")]


def test_without_a_video_the_song_is_searched_by_name_and_artist():
    songs = [{"videoId": "AAAAAAAAAAA", "title": "Gülpembe", "artists": [{"name": "Başka Biri"}]},
             {"videoId": "BBBBBBBBBBB", "title": "Gülpembe (Remastered)", "artists": [{"name": "Barış Manço"}]}]
    api = FakeYTM(songs=songs)
    assert lyrics.ytmusic_lyrics("", "Barış Manço", "Gülpembe", api=api) == (GULPEMBE, False)
    assert ("watch", "BBBBBBBBBBB") in api.asked                         # the one with the right artist


def test_no_matching_song_or_no_lyrics_is_none():
    assert lyrics.ytmusic_lyrics("", "Barış Manço", "Gülpembe", api=FakeYTM(songs=[
        {"videoId": "CCCCCCCCCCC", "title": "Dönence", "artists": [{"name": "Barış Manço"}]}])) is None
    assert lyrics.ytmusic_lyrics("zd8IFDgQCUc", api=FakeYTM(browse=None)) is None


# ------------------------------------------------------------------------------ the two sources together
def test_youtube_music_text_with_lrclib_times_when_they_are_the_same_song():
    text = lyrics.fetch("Barış Manço", "Gülpembe", 312, get=lrclib([rec("Gülpembe", synced=GULPEMBE_LRC)]),
                        video_id="zd8IFDgQCUc", ytm=FakeYTM())
    assert lyrics.parse(text)["synced"][0] == (10000, "Sen gülünce güller açar, gülpembe")
    assert text.startswith("[re:YouTube Music + LRCLIB]")


def test_lrclib_with_another_text_is_not_used():
    """The bug: LRCLIB had another song of the same name. YouTube Music's text wins."""
    text = lyrics.fetch("Barış Manço", "Gülpembe", 312, get=lrclib([rec("Gülpembe", synced=OTHER_LRC)]),
                        video_id="zd8IFDgQCUc", ytm=FakeYTM())
    assert lyrics.parse(text)["synced"] == [] and "Bülbüller seni söyler" in text and "Bambaşka" not in text


def test_timed_youtube_music_lyrics_need_nothing_else():
    lines = [types.SimpleNamespace(text="Sen gülünce", start_time=1000)]
    asked = []
    text = lyrics.fetch("Barış Manço", "Gülpembe", 312, get=lambda *a, **k: asked.append(a),
                        video_id="zd8IFDgQCUc", ytm=FakeYTM(timed=lines))
    assert lyrics.parse(text)["synced"] == [(1000, "Sen gülünce")] and asked == []


def test_without_youtube_music_lrclib_must_name_the_same_artist():
    get = lrclib([rec("Gülpembe", synced=OTHER_LRC, artist="Başka Sanatçı")])
    assert lyrics.fetch("Barış Manço", "Gülpembe", 312, get=get, ytm=FakeYTM(songs=[])) is None
    get = lrclib([rec("Gülpembe", synced=GULPEMBE_LRC)])
    assert "[re:LRCLIB]" in lyrics.fetch("Barış Manço", "Gülpembe", 312, get=get, ytm=FakeYTM(songs=[]))


def test_one_source_failing_is_not_the_end():
    class Broken(FakeYTM):
        def get_watch_playlist(self, videoId=None):
            raise OSError("YouTube Music unreachable")

    text = lyrics.fetch("Barış Manço", "Gülpembe", 312, get=lrclib([rec("Gülpembe", synced=GULPEMBE_LRC)]),
                        video_id="zd8IFDgQCUc", ytm=Broken())
    assert lyrics.parse(text)["synced"]

    def no_net(*a, **k):
        raise OSError("no internet")

    with pytest.raises(OSError):
        lyrics.fetch("Barış Manço", "Gülpembe", 312, get=no_net, video_id="zd8IFDgQCUc", ytm=Broken())


def test_the_same_song_test():
    assert lyrics.similar(GULPEMBE, GULPEMBE_LRC) and not lyrics.similar(GULPEMBE, OTHER_LRC)
    assert not lyrics.similar("", GULPEMBE)


def test_the_fetcher_hands_over_the_video(tmp_path):
    song = make_wav(tmp_path / "a.mp3")
    seen = []
    f = lyrics.Fetcher(find=lambda artist, title, seconds, video_id="": seen.append(video_id) or "söz")
    f.find(song, "Barış Manço", "Gülpembe", 10, video_id="zd8IFDgQCUc")
    end = time.time() + 5
    got = []
    while time.time() < end and not got:
        got = f.drain()
        time.sleep(0.02)
    assert seen == ["zd8IFDgQCUc"] and got == [(song, True, "")]


# ------------------------------------------------------------------------------ in the window
@pytest.mark.gui
def test_wrong_lyrics_can_be_looked_up_again_with_the_songs_own_video(app, monkeypatch, tmp_path):
    from music_support import FakeBackend, FakeReader

    from app import player, tags
    from app.models import DONE, Item
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app._ensure_music()
    music = app.music
    song = make_wav(tmp_path / "Gülpembe.mp3")
    it = Item("https://www.youtube.com/watch?v=zd8IFDgQCUc", kind="audio", title="Gülpembe")
    it.state, it.final_path = DONE, song
    app.manager.items.append(it)
    lyrics.save(song, OTHER_LRC)                                         # the wrong lyrics from before
    music._pick_files = lambda: [song]
    music._add_files()
    asked = []
    monkeypatch.setattr(lyrics, "fetch", lambda artist, title, seconds=0, video_id="": asked.append(video_id) or GULPEMBE)
    music.tree.selection_set("0")
    items = {e[0]: e[1] for e in music.track_menu_items() if e}
    items["🔄 Sözler yanlış, yeniden bul"]()
    end = time.time() + 5
    while time.time() < end and "Bambaşka" in open(lyrics.lyrics_path(song), encoding="utf-8").read():
        time.sleep(0.02)
    assert asked == ["zd8IFDgQCUc"] and "Bülbüller" in open(lyrics.lyrics_path(song), encoding="utf-8").read()
    assert app.video_id_for(song) == "zd8IFDgQCUc" and app.video_id_for(str(tmp_path / "yok.mp3")) == ""
