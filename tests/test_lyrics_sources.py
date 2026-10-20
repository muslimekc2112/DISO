"""Where the lyrics come from: only YouTube Music (the video's own lyrics, else YouTube Music's song of
the same name and artist), and never another song that only has the same name."""
import time
import types

import pytest
from music_support import make_wav

from app import lyrics

GULPEMBE = "Sen gülünce güller açar, gülpembe\nBülbüller seni söyler, biz dinlerdik, gülpembe\nSen gelince bahar gelir"
OTHER_LRC = "[00:05.00]Bambaşka bir şarkının\n[00:09.00]bambaşka sözleri burada\n[00:12.00]hiç benzemiyor"


class FakeYTM:
    """The few calls of ytmusicapi.YTMusic DISO makes. `browse` maps a video to its lyrics (None: none)."""

    def __init__(self, text=GULPEMBE, timed=None, songs=None, browse="MPLYt_x"):
        self.text, self.timed, self.songs, self.browse = text, timed, songs or [], browse
        self.asked = []

    def search(self, query, filter=None, limit=None):
        self.asked.append(("search", query, filter))
        return self.songs

    def get_watch_playlist(self, videoId=None):
        self.asked.append(("watch", videoId))
        return {"lyrics": self.browse.get(videoId) if isinstance(self.browse, dict) else self.browse}

    def get_lyrics(self, browse, timestamps=False):
        self.asked.append(("lyrics", browse, timestamps))
        if self.timed:
            return {"lyrics": self.timed, "hasTimestamps": True}
        return {"lyrics": self.text, "hasTimestamps": False}


def song(vid, title, artist="Barış Manço", seconds=312):
    return {"videoId": vid, "title": title, "artists": [{"name": artist}], "duration_seconds": seconds}


def watched(api):
    return [a[1] for a in api.asked if a[0] == "watch"]


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
    api = FakeYTM(songs=[song("AAAAAAAAAAA", "Gülpembe", "Başka Biri"), song("BBBBBBBBBBB", "Gülpembe (Remastered)")])
    assert lyrics.ytmusic_lyrics("", "Barış Manço", "Gülpembe", api=api) == (GULPEMBE, False)
    assert watched(api) == ["BBBBBBBBBBB"]                                  # the one with the right artist


def test_a_video_without_lyrics_gets_youtube_musics_own_song():
    """A lyrics video uploaded by someone has no lyrics on YouTube Music; the real song has."""
    api = FakeYTM(songs=[song("SONGSONGSON", "On & On (feat. Daniel Levi)", "Cartoon, Jéja, Daniel Levi", 208)],
                  browse={"LYRICVIDEO1": None, "SONGSONGSON": "MPLYt_x"})
    assert lyrics.ytmusic_lyrics("LYRICVIDEO1", "Cartoon, Jéja", "On & On (Lyrics) feat. Daniel Levi", 208,
                                 api=api) == (GULPEMBE, False)
    assert watched(api) == ["LYRICVIDEO1", "SONGSONGSON"]


def test_the_recording_closest_in_length_is_taken():
    api = FakeYTM(songs=[song("LIVELIVELIV", "Gülpembe", seconds=402), song("STUDIOSTUDI", "Gülpembe", seconds=311)])
    lyrics.ytmusic_lyrics("", "Barış Manço", "Gülpembe", 312, api=api)
    assert watched(api) == ["STUDIOSTUDI"]


def test_no_matching_song_or_no_lyrics_is_none():
    assert lyrics.ytmusic_lyrics("", "Barış Manço", "Gülpembe", api=FakeYTM(songs=[song("CCCCCCCCCCC", "Dönence")])) is None
    assert lyrics.ytmusic_lyrics("zd8IFDgQCUc", api=FakeYTM(browse=None)) is None


def test_without_an_artist_only_exactly_the_same_name_counts():
    api = FakeYTM(songs=[song("AAAAAAAAAAA", "Love Me Again"), song("BBBBBBBBBBB", "Love (Live)")])
    assert lyrics.ytmusic_lyrics("", "", "Love", api=api) == (GULPEMBE, False)
    assert watched(api) == ["BBBBBBBBBBB"]
    assert lyrics.ytmusic_lyrics("", "", "Love", api=FakeYTM(songs=[song("AAAAAAAAAAA", "Love Me Again")])) is None


# ------------------------------------------------------------------------------ fetch: YouTube Music only
def test_lyrics_come_only_from_youtube_music(monkeypatch):
    import requests

    def no_other_site(*a, **k):
        raise AssertionError("asked another lyrics site")
    monkeypatch.setattr(requests, "get", no_other_site)
    text = lyrics.fetch("Barış Manço", "Gülpembe", 312, video_id="zd8IFDgQCUc", ytm=FakeYTM())
    assert text.startswith("[re:YouTube Music]\n") and "Bülbüller seni söyler" in text
    assert lyrics.fetch("Barış Manço", "Gülpembe", 312, ytm=FakeYTM(songs=[])) is None      # none: no lyrics


def test_timed_youtube_music_lyrics_are_kept_with_their_times():
    lines = [types.SimpleNamespace(text="Sen gülünce", start_time=1000)]
    text = lyrics.fetch("Barış Manço", "Gülpembe", 312, video_id="zd8IFDgQCUc", ytm=FakeYTM(timed=lines))
    assert lyrics.parse(text)["synced"] == [(1000, "Sen gülünce")]


def test_youtube_music_unreachable_is_an_error_not_other_lyrics():
    class Broken(FakeYTM):
        def get_watch_playlist(self, videoId=None):
            raise OSError("YouTube Music unreachable")

    with pytest.raises(OSError):
        lyrics.fetch("Barış Manço", "Gülpembe", 312, video_id="zd8IFDgQCUc", ytm=Broken())


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
    assert lyrics.clean_title("Never Gonna Give You Up (4K Remaster)") == "Never Gonna Give You Up"
    assert lyrics.clean_title("Love (Live)") == "Love (Live)"                    # a real part of the name stays
    assert lyrics.clean_title("(Official Video)") == "(Official Video)"         # never cleaned to nothing
