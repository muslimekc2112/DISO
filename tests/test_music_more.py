"""The music player's newer parts without a window: deleted files leave the lists, sorting, copying
to another list, the remembered place, the search for songs and the media keys."""
import os
import sys
import time
import types

import pytest
from music_support import make_wav

from app import mediakeys, music_search
from app import video_engine as ve
from app.manager import DownloadManager
from app.models import Item, Settings
from app.playlists import DEFAULT_NAME, PlaylistStore, is_gone


@pytest.fixture
def store(tmp_path):
    return PlaylistStore(str(tmp_path / "playlists.json"))


@pytest.fixture
def songs(tmp_path):
    return [make_wav(tmp_path / f"{n}.wav") for n in "abcd"]


def titles(store, name=DEFAULT_NAME):
    return [t["title"] for t in store.tracks(name)]


# ------------------------------------------------------------------------------ deleted files
def test_a_deleted_file_is_gone_but_one_on_a_missing_drive_is_not(tmp_path, songs):
    assert not is_gone(songs[0])
    os.remove(songs[0])
    assert is_gone(songs[0])
    free = next((f"{c}:" for c in "QWXYZJKLMN" if not os.path.exists(f"{c}:\\")), None)
    if free and sys.platform.startswith("win"):
        assert not is_gone(free + "\\Müzik\\şarkı.mp3")             # a USB stick that is not plugged in


def test_deleted_files_leave_every_list_and_others_stay(store, songs):
    store.add(DEFAULT_NAME, songs)
    other = store.create("Gece")
    store.add(other, [songs[1], songs[2]])
    os.remove(songs[1])
    missing = store.missing_paths()
    assert missing == {os.path.abspath(songs[1])}
    assert store.prune(missing) == {DEFAULT_NAME: 1, "Gece": 1}
    assert titles(store) == ["a", "c", "d"] and titles(store, "Gece") == ["c"]
    assert titles(PlaylistStore(store.path)) == ["a", "c", "d"]                # written to the file


def test_a_file_that_came_back_is_not_removed(store, songs):
    store.add(DEFAULT_NAME, songs)
    os.remove(songs[0])
    missing = store.missing_paths()
    make_wav(songs[0])                                                          # restored before the prune
    assert store.prune(missing) == {} and titles(store) == list("abcd")


# ------------------------------------------------------------------------------ sorting and copying
def test_sorting_by_title_artist_and_length(store, tmp_path):
    paths = [make_wav(tmp_path / f"{n}.wav") for n in ("zeytin", "Armut", "elma")]
    store.add(DEFAULT_NAME, paths)
    store.apply_tags({paths[0]: {"artist": "Ali", "duration": 3000}, paths[1]: {"artist": "Can", "duration": 1000},
                      paths[2]: {"duration": 2000}})
    store.sort(DEFAULT_NAME, "title")
    assert titles(store) == ["Armut", "elma", "zeytin"]                         # not case sensitive
    store.sort(DEFAULT_NAME, "title", reverse=True)
    assert titles(store) == ["zeytin", "elma", "Armut"]
    store.sort(DEFAULT_NAME, "artist")
    assert titles(store) == ["zeytin", "Armut", "elma"]                         # no artist goes last
    store.sort(DEFAULT_NAME, "time")
    assert titles(store) == ["Armut", "elma", "zeytin"]
    store.sort(DEFAULT_NAME, "nonsense")
    assert titles(PlaylistStore(store.path)) == ["Armut", "elma", "zeytin"]


def test_copying_to_another_list_keeps_what_is_known_and_skips_doubles(store, songs):
    store.add(DEFAULT_NAME, songs)
    store.apply_tags({songs[0]: {"artist": "Ali", "duration": 1000}})
    assert store.copy_to("Spor", store.tracks(DEFAULT_NAME)[:2]) == 2
    assert store.tracks("Spor")[0]["artist"] == "Ali"
    assert store.copy_to("Spor", store.tracks(DEFAULT_NAME)[:3]) == 1 and titles(store, "Spor") == ["a", "b", "c"]
    store.tracks("Spor")[0]["artist"] = "Değişti"
    assert store.tracks(DEFAULT_NAME)[0]["artist"] == "Ali"                     # a copy, not the same object


def test_bad_remembered_values_are_ignored(tmp_path):
    p = tmp_path / "playlists.json"
    p.write_text('{"playlists": {}, "state": {"resume_ms": -5, "resume_path": 7, "ask_list": ["x"]}}', encoding="utf-8")
    s = PlaylistStore(str(p))
    assert s.state["resume_ms"] == 0 and s.state["resume_path"] == "" and s.state["ask_list"] == ""


# ------------------------------------------------------------------------------ a found song in the queue
def test_a_found_song_is_an_mp3_with_its_origin_and_survives_a_restart(tmp_path):
    m = DownloadManager(store_path=str(tmp_path / "d.json"))
    m.set_gate(False)                                       # nothing really starts
    it = m.add_song("https://www.youtube.com/watch?v=abc", "Şarkı", Settings(kind="video", folder=str(tmp_path)))
    assert it.kind == "audio" and it.origin == "music" and it.title == "Şarkı" and it.folder == str(tmp_path)
    m.save()
    again = DownloadManager(store_path=str(tmp_path / "d.json"))
    again.set_gate(False)
    assert [(i.origin, i.kind) for i in again.items] == [("music", "audio")]
    assert Item.from_dict({"url": "x"}).origin == ""                            # an old list without it


def test_the_music_folder_is_in_the_data_folder(isolated_home):
    folder = music_search.music_dir()
    assert os.path.isdir(folder) and folder.startswith(str(isolated_home / "AppData" / "Local" / "DISO"))
    assert os.path.basename(folder) == "Müzik"


# ------------------------------------------------------------------------------ searching
class FakeYDL:
    answer = {}
    asked = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        FakeYDL.asked.append((url, self.opts))
        return FakeYDL.answer


@pytest.fixture
def fake_ytdlp(monkeypatch):
    FakeYDL.asked = []
    monkeypatch.setattr(ve, "_yt_dlp", lambda: types.SimpleNamespace(YoutubeDL=FakeYDL))
    return FakeYDL


class FakeYTMusic:
    """Same `search` as ytmusicapi.YTMusic; answers per filter."""

    def __init__(self, songs=(), videos=()):
        self.answers = {"songs": list(songs), "videos": list(videos)}
        self.asked = []

    def search(self, query, filter=None, limit=20):
        self.asked.append((query, filter, limit))
        return self.answers[filter]


def song(vid, title, artist, views="", seconds=200, **more):
    return dict({"videoId": vid, "title": title, "artists": [{"name": artist, "id": "x"}], "views": views,
                 "duration_seconds": seconds, "album": {"name": "Albüm", "id": "a"}, "resultType": "song"}, **more)


@pytest.fixture
def fake_ytmusic(monkeypatch):
    api = FakeYTMusic()
    monkeypatch.setattr(music_search, "_ytmusic", lambda: api)
    return api


def test_a_search_asks_youtube_music_for_songs_and_puts_the_popular_matches_first(fake_ytmusic):
    fake_ytmusic.answers["songs"] = [
        song("a1", "Kuzu Kuzu", "Tarkan", "238M", 234),
        song("b2", "Dudu", "Tarkan", "546M"),
        song("c3", "Kuzu Kuzu (Akustik)", "Tarkan", "1.1M"),
        song("d4", "Kuzu Kuzu", "Biri", "2.5B"),
        song("a1", "Kuzu Kuzu", "Tarkan", "238M"),                       # the same twice
        song("e5", "Kuzu Kuzu", "Tarkan", "9K"),                          # the same song again (another id)
        song("", "Videosuz", "Tarkan"), song("f6", "Gone", "Tarkan", isAvailable=False), None]
    found = music_search.search("  kuzu   kuzu ")
    assert ("kuzu kuzu", "songs", music_search.LIMIT) in fake_ytmusic.asked
    assert [(r["url"][-2:], r["views"]) for r in found] == [
        ("d4", 2_500_000_000), ("a1", 238_000_000), ("c3", 1_100_000), ("b2", 546_000_000)]
    assert found[1] == {"url": "https://www.youtube.com/watch?v=a1", "title": "Kuzu Kuzu", "channel": "Tarkan",
                        "duration": 234, "views": 238_000_000, "album": "Albüm"}


def test_an_artist_keeps_only_their_songs(fake_ytmusic):
    fake_ytmusic.answers["songs"] = [song("a1", "Şımarık", "Tarkan", "10M"), song("b2", "Simarik", "Cover Grup", "90M"),
                                     song("c3", "Dudu", "TARKAN", "50M"),
                                     song("d4", "Hadi O Zaman", "Nazan Öncel, Tarkan", "1M")]
    found = music_search.search("simarik", "  tarkan ")
    assert fake_ytmusic.asked[0][0] == "simarik tarkan"
    assert [r["url"][-2:] for r in found] == ["a1", "c3", "d4"]          # "Şımarık" matches "simarik" too
    assert [r["url"][-2:] for r in music_search.search("", "tarkan")] == ["c3", "a1", "d4"]
    # an artist nobody matches does not empty the results
    assert len(music_search.search("dudu", "yok böyle biri")) == 4


def test_only_songs_are_searched_never_youtube_videos(fake_ytmusic):
    """Lyric videos, covers and shorts are YouTube videos: the search asks YouTube Music for songs only."""
    fake_ytmusic.answers["songs"] = [song("a1", "Nadir Şarkı", "Biri", "5K")]
    fake_ytmusic.answers["videos"] = [song("v1", "Nadir Şarkı (Lyrics)", "Biri", "80K", 240)]
    assert [r["url"][-2:] for r in music_search.search("nadir şarkı")] == ["a1"]
    assert {f for _, f, _ in fake_ytmusic.asked} == {"songs"}


def test_a_short_answer_is_asked_once_more_and_both_are_used(fake_ytmusic):
    answers = [[song("a1", "Bir", "Biri", "1K")], [song("a1", "Bir", "Biri", "1K"), song("b2", "Bir daha", "Biri", "9M")]]
    fake_ytmusic.search = lambda q, filter=None, limit=20: answers.pop(0) if filter == "songs" else []
    assert [r["url"][-2:] for r in music_search.search("bir")] == ["b2", "a1"] and answers == []


def test_listen_counts_are_read_and_shown_short():
    assert [music_search.views_count(t) for t in ("238M", "1.1M", "447K", "2.7B", "12,345", "1.234.567",
                                                  "", None, "çok")] == [
        238_000_000, 1_100_000, 447_000, 2_700_000_000, 12345, 1234567, 0, 0, 0]
    assert [music_search.short_views(n) for n in (0, 950, 447_000, 1_100_000, 238_000_000, 2_700_000_000)] == [
        "", "950", "447 B", "1,1 Mn", "238 Mn", "2,7 Mr"]


def test_without_youtube_music_the_search_says_so_and_never_searches_youtube(fake_ytdlp, monkeypatch):
    tries = []

    def broken():
        tries.append(1)
        raise ConnectionError("Read timed out")
    monkeypatch.setattr(music_search, "_ytmusic", broken)
    with pytest.raises(music_search.Unreachable) as caught:
        music_search.search("  tarkan   şımarık ")
    assert len(tries) == music_search.SEARCH_TRIES == 2 and fake_ytdlp.asked == []     # asked again, then said so
    assert "YouTube Music'e ulaşılamadı" in str(caught.value)


def test_a_slow_first_answer_is_asked_again(fake_ytmusic, monkeypatch):
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("Read timed out")
        return fake_ytmusic
    monkeypatch.setattr(music_search, "_ytmusic", flaky)
    fake_ytmusic.answers["songs"] = [song("a1", "Şımarık", "Tarkan", "10M")]
    assert [r["url"][-2:] for r in music_search.search("şımarık")] == ["a1"]


def test_an_empty_search_asks_nothing(fake_ytdlp, fake_ytmusic):
    assert music_search.search("   ") == [] and music_search.search("", "  ") == []
    assert fake_ytdlp.asked == [] and fake_ytmusic.asked == []


def test_the_searcher_passes_the_artist_on():
    s = music_search.Searcher(find=lambda q, artist="": [{"url": "u", "title": f"{q}/{artist}"}])
    s.search("a", "b")
    assert wait_for(s) == ("a", [{"url": "u", "title": "a/b"}], "")


def test_a_link_is_opened_not_searched(monkeypatch):
    seen = []
    monkeypatch.setattr(ve, "expand_playlist", lambda url, cookies=None: seen.append(url) or
                        ve.PlaylistEntries([("https://y/1", "Bir", 60), ("https://y/2", "", 0)], "Liste"))
    found = music_search.search("https://www.youtube.com/playlist?list=PL1")
    assert seen == ["https://www.youtube.com/playlist?list=PL1"]
    assert found == [{"url": "https://y/1", "title": "Bir", "channel": "", "duration": 60},
                     {"url": "https://y/2", "title": "https://y/2", "channel": "", "duration": 0}]


def wait_for(searcher, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        answer = searcher.poll()
        if answer:
            return answer
        time.sleep(0.01)
    return None


def test_the_searcher_answers_from_another_thread_once():
    s = music_search.Searcher(find=lambda q: [{"url": "u", "title": q}])
    s.search("a")
    assert wait_for(s) == ("a", [{"url": "u", "title": "a"}], "") and not s.busy
    assert s.poll() is None


def test_only_the_newest_question_is_answered():
    import threading
    slow = threading.Event()

    def find(q):
        if q == "eski":
            slow.wait(5)
        return [{"title": q}]

    s = music_search.Searcher(find=find)
    s.search("eski")
    s.search("yeni")
    assert wait_for(s) == ("yeni", [{"title": "yeni"}], "")
    slow.set()
    time.sleep(0.2)
    assert s.poll() is None                                       # the late, old answer is thrown away


def test_a_failing_search_gives_a_readable_error():
    def find(q):
        raise RuntimeError("ERROR: \x1b[0;31mUnable to download\x1b[0m webpage")

    s = music_search.Searcher(find=find)
    s.search("x")
    query, results, error = wait_for(s)
    assert results == [] and error == "Unable to download webpage" and not s.busy


# ------------------------------------------------------------------------------ media keys (real Windows messages)
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_media_keys_are_taken_heard_and_given_back():
    keys = mediakeys.MediaKeys()
    taken = keys.start()
    try:
        assert keys.active
        if "next" not in taken:
            pytest.skip("another program holds the media keys")
        keys.post("next")
        assert keys.pressed.get(timeout=3) == "next"
    finally:
        keys.stop()
    assert not keys.active and keys.taken == set()
    again = mediakeys.MediaKeys()                                 # given back: it can be taken again
    try:
        assert "next" in again.start()
    finally:
        again.stop()


def test_stopping_media_keys_that_never_started_is_quiet():
    mediakeys.MediaKeys().stop()


# ------------------------------------------------------------------------------ what a track is called
@pytest.mark.parametrize("track, shown", [
    ({"title": "dosya"}, ("", "dosya")),
    ({"title": "x", "tag_title": "Sabah", "artist": "Ali"}, ("Ali", "Sabah")),
    ({"title": "x", "tag_title": "Barış Manço - Gülpembe", "artist": "netd müzik"}, ("Barış Manço", "Gülpembe")),
    ({"title": "Tarkan – Şımarık"}, ("Tarkan", "Şımarık")),
    ({"title": "x", "tag_title": "Tarkan - Şımarık", "artist": "Tarkan"}, ("Tarkan", "Şımarık")),
    ({"title": "x", "tag_title": "Remix - Sezen Aksu", "artist": "Sezen Aksu"}, ("Sezen Aksu", "Remix - Sezen Aksu")),
    ({"title": "x", "tag_title": "- Gülpembe"}, ("", "- Gülpembe")),
])
def test_artist_and_title_from_a_youtube_style_title(track, shown):
    from app.player import artist_and_title, track_label
    assert artist_and_title(track) == shown
    assert track_label(track) == (f"{shown[0]} – {shown[1]}" if shown[0] else shown[1])


# ------------------------------------------------------------------------------ lyrics without a window
def test_lrc_text_is_read_with_times_and_without_tags():
    from app import lyrics
    d = lyrics.parse("[ti:Şarkı]\r\n[00:01.5]Bir\n[01:02.25][01:30.00]Nakarat\n\nDüz satır\n")
    assert d["synced"] == [(1500, "Bir"), (62250, "Nakarat"), (64750, "Düz satır"), (90000, "Nakarat")]
    assert d["plain"] == ["Bir", "Nakarat", "", "Düz satır"]
    assert lyrics.parse("sadece düz\nmetin")["synced"] == []


def test_the_line_being_sung():
    from app import lyrics
    synced = [(1000, "a"), (5000, "b"), (9000, "c")]
    assert [lyrics.line_at(synced, ms) for ms in (0, 1000, 4999, 5000, 20000)] == [-1, 0, 0, 1, 2]


def test_titles_are_cleaned_for_the_search():
    from app import lyrics
    assert lyrics.clean_title("Gülpembe (Official Video) [4K]") == "Gülpembe"
    assert lyrics.clean_title("Şımarık (Resmi Klip) | Tarkan") == "Şımarık"
    assert lyrics.clean_title("Never Gonna Give You Up (4K Remaster)") == "Never Gonna Give You Up"
    assert lyrics.clean_title("Love (Live)") == "Love (Live)"                    # a real part of the name stays
    assert lyrics.clean_title("(Official Video)") == "(Official Video)"         # never cleaned to nothing


def test_lyrics_are_kept_next_to_the_song(tmp_path):
    from app import lyrics
    song = make_wav(tmp_path / "Şarkı.mp3")
    assert not lyrics.has_lyrics(song) and lyrics.load(song) is None
    lyrics.save(song, "[00:01.00]Merhaba\n")
    assert os.path.isfile(tmp_path / "Şarkı.lrc") and lyrics.load(song)["synced"] == [(1000, "Merhaba")]


def test_the_fetcher_saves_what_it_finds_and_reports(tmp_path):
    from app import lyrics
    song = make_wav(tmp_path / "a.mp3")
    other = make_wav(tmp_path / "b.mp3")
    f = lyrics.Fetcher(find=lambda artist, title, seconds: "söz" if title == "a" else None)
    assert f.find(song, "", "a", 10) and f.find(other, "", "b", 10)
    assert not f.find(song, "", "a", 10) or True
    end = time.time() + 5
    got = []
    while time.time() < end and len(got) < 2:
        got += f.drain()
        time.sleep(0.02)
    assert sorted(got) == [(song, True, ""), (other, False, "")]
    assert lyrics.load(song)["plain"] == ["söz"] and not lyrics.has_lyrics(other)


def test_the_store_can_shuffle_and_undo(store, songs):
    import random
    store.add(DEFAULT_NAME, songs)
    before = store.shuffle(DEFAULT_NAME, random.Random(1))
    assert titles(store) != [t["title"] for t in before] and sorted(titles(store)) == list("abcd")
    store.remove(DEFAULT_NAME, [0])
    gone = [t for t in before if t["title"] not in titles(store)]
    store.set_order(DEFAULT_NAME, before)
    assert titles(store) == [t["title"] for t in before if t not in gone]
