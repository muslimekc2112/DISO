"""The last round of 1.1: renaming many songs' files from a pattern, covers from the internet, and the
speed graph."""
import collections
import os
import time

import pytest
from music_support import FakeBackend, FakeEqBackend, FakeReader, make_wav

from app import covers, player, playlists, renamer, tags
from app.speed_graph import POINTS, Sampler


# ------------------------------------------------------------------------------ ✏ file names
def track(path, **kw):
    return dict({"path": str(path), "title": os.path.splitext(os.path.basename(str(path)))[0]}, **kw)


def test_names_come_from_the_pattern_in_turkish_or_english():
    t = track("C:/m/x.mp3", artist="barış manço", tag_title="GÜLPEMBE", album="Sahibinden İhtiyaç")
    assert renamer.make_name("{sanatçı} - {şarkı}", t, 3) == "barış manço - GÜLPEMBE"
    assert renamer.make_name("{no}. {artist} - {title}", t, 3) == "03. barış manço - GÜLPEMBE"
    assert renamer.make_name("{sanatçı} - {albüm} - {şarkı}", t, 1, capitals=True) == \
        "Barış Manço - Sahibinden İhtiyaç - Gülpembe"
    assert renamer.make_name("{sanatçı} - {şarkı}", t, 1, plain=True) == "baris manco - GULPEMBE"
    alone = track("C:/m/Şımarık.mp3")
    assert renamer.make_name("{sanatçı} - {şarkı}", alone, 1) == "Şımarık"        # no artist: no "- "
    assert renamer.make_name("{sanatçı}", alone, 1) == ""
    assert renamer.make_name('{şarkı}: "canlı"?', alone, 1) == "Şımarık_ _canlı__"   # what Windows refuses goes
    assert renamer.title_case("istanbul'da SONBAHAR ılık") == "İstanbul'da Sonbahar Ilık"


def test_the_plan_shows_what_would_happen_and_rename_moves_the_lyrics_too(tmp_path):
    a = make_wav(tmp_path / "01.wav")
    b = make_wav(tmp_path / "02.wav")
    c = make_wav(tmp_path / "Gece.wav")
    taken = make_wav(tmp_path / "Teoman - Gece.wav")
    (tmp_path / "01.lrc").write_text("[00:01.00]söz", encoding="utf-8")
    tracks = [track(a, artist="Teoman", tag_title="Sabah"), track(b, artist="Teoman", tag_title="Sabah"),
              track(c, artist="Teoman", tag_title="Gece"), track(make_wav(tmp_path / "x.wav"))]
    steps = renamer.plan(tracks, "{sanatçı} - {şarkı}")
    assert [s for *_, s in steps] == [renamer.OK, renamer.CLASH, renamer.CLASH, renamer.SAME]   # x has no artist
    same = renamer.plan([track(taken, artist="Teoman", tag_title="Gece")], "{sanatçı} - {şarkı}")
    assert same[0][2] == renamer.SAME
    done, failed = renamer.apply(steps)
    assert [os.path.basename(n) for _, n in done] == ["Teoman - Sabah.wav"]
    assert (tmp_path / "Teoman - Sabah.lrc").read_text(encoding="utf-8") == "[00:01.00]söz"
    assert not (tmp_path / "01.wav").exists() and failed == []
    back = renamer.undo(done)
    assert (tmp_path / "01.wav").exists() and (tmp_path / "01.lrc").exists() and len(back) == len(done)


def test_only_the_letter_case_can_change_too(tmp_path):
    tmp_path = tmp_path / "m"
    tmp_path.mkdir()
    a = make_wav(tmp_path / "gülpembe.wav")
    steps = renamer.plan([track(a)], "{şarkı}", capitals=True)
    assert steps[0][2] == renamer.OK and os.path.basename(steps[0][1]) == "Gülpembe.wav"
    renamer.apply(steps)
    assert os.listdir(tmp_path) == ["Gülpembe.wav"]


def test_the_lists_follow_renamed_files(tmp_path):
    store = playlists.PlaylistStore(str(tmp_path / "p.json"))
    a = make_wav(tmp_path / "a.wav")
    store.add(store.user_names()[0], [a])
    store.create("Gece")
    store.add("Gece", [a])
    store.count_play(a)
    store.set_state(resume_path=os.path.abspath(a))
    new = str(tmp_path / "Yeni ad.wav")
    os.rename(a, new)
    assert store.rename_paths([(a, new)]) == 2
    again = playlists.PlaylistStore(str(tmp_path / "p.json"))
    assert [t["path"] for t in again.tracks("Gece")] == [os.path.abspath(new)]
    assert again.tracks("Gece")[0]["title"] == "Yeni ad" and again.plays(new) == 1
    assert again.state["resume_path"] == os.path.abspath(new)


# ------------------------------------------------------------------------------ 🖼 covers
def test_the_cover_link_asks_for_the_big_picture():
    assert covers.big("https://yt3.googleusercontent.com/abc=w60-h60-l90-rj").endswith("=w544-h544-l90-rj")
    assert covers.big("https://i.ytimg.com/vi/x/hqdefault.jpg") == "https://i.ytimg.com/vi/x/hqdefault.jpg"


class FakeYTM:
    def __init__(self, songs, watch=None):
        self.songs, self.watch = songs, watch or {}

    def search(self, query, filter=None, limit=None):
        return self.songs

    def get_watch_playlist(self, videoId=None):
        return {"tracks": self.watch.get(videoId, [])}


def thumbs(name):
    return [{"url": f"https://yt3.example/{name}=w60-h60", "width": 60},
            {"url": f"https://yt3.example/{name}=w120-h120", "width": 120}]


def test_only_the_same_song_gives_its_cover():
    songs = [{"videoId": "o1", "title": "Başka Şarkı", "artists": [{"name": "Barış Manço"}], "thumbnails": thumbs("other")},
             {"videoId": "g1", "title": "Gül Pembe", "artists": [{"name": "Barış Manço"}], "thumbnails": thumbs("gul")}]
    api = FakeYTM(songs)
    assert covers.picture_url("Barış Manço", "Gülpembe (Official Video)", api=api) == "https://yt3.example/gul=w544-h544"
    assert covers.picture_url("Sezen Aksu", "Gülpembe", api=api) == ""                # another artist: none
    api = FakeYTM([], watch={"v1": [{"videoId": "v1", "thumbnail": thumbs("own")}]})
    assert covers.picture_url(video_id="v1", api=api) == "https://yt3.example/own=w544-h544"


def _wait(finder, timeout=10):
    end, got = time.time() + timeout, []
    while time.time() < end and finder.pending():
        time.sleep(0.02)
    got += finder.drain()
    return got


def test_the_finder_writes_skips_and_leaves_the_playing_song_to_the_window(tmp_path, monkeypatch):
    written = []
    monkeypatch.setattr(tags, "write_tags", lambda path, fields, cover: written.append((path, cover)))
    monkeypatch.setattr(tags, "probe", lambda path: {"cover": "has" in path})
    picture = tmp_path / "p.jpg"

    def find(artist, title, seconds, video_id):
        picture.write_bytes(b"jpg")
        return str(picture) if title != "yok" else None
    f = covers.Finder(find=find, busy=lambda path: "playing" in path)
    paths = {k: make_wav(tmp_path / f"{k}.mp3") for k in ("new", "has", "none", "playing")}
    for key, path in paths.items():
        f.find(path, "A", "yok" if key == "none" else key)
    f.find(make_wav(tmp_path / "x.wav"), "A", "x")
    got = {os.path.basename(p): r for p, r, d in _wait(f)}
    assert got == {"new.mp3": "done", "has.mp3": "has", "none.mp3": "none", "playing.mp3": "later", "x.wav": "cant"}
    assert written == [(paths["new"], str(picture))]
    f.find(paths["has"], "A", "has", force=True)                                  # "find again": it is replaced
    assert _wait(f)[0][1] == "done"


def test_a_dropped_connection_is_asked_once_more(tmp_path, monkeypatch):
    monkeypatch.setattr(covers, "RETRY_WAIT", 0)
    monkeypatch.setattr(tags, "probe", lambda path: {})
    calls = []

    def find(*a):
        calls.append(a)
        if len(calls) == 1:
            raise ConnectionResetError(10054, "reset")
        return None
    f = covers.Finder(find=find)
    f.find(make_wav(tmp_path / "a.mp3"), "A", "B")
    assert _wait(f)[0][1] == "none" and len(calls) == 2


# ------------------------------------------------------------------------------ 📈 the speed graph
class It:
    def __init__(self, id, speed, state="downloading"):
        self.id, self.speed, self.state = id, speed, state


def test_the_sampler_keeps_a_minute_of_each_download_and_the_total():
    now = [100.0]
    s = Sampler(clock=lambda: now[0])
    items = [It("a", 1000), It("b", 500), It("c", 900, "paused")]
    assert s.take(items, "downloading") and list(s.total)[-1] == 1500 and len(s.total) == POINTS
    assert not s.take(items, "downloading")                                        # not a second yet
    now[0] += 1
    items[0].speed = 3000
    s.take(items, "downloading")
    assert list(s.of("a"))[-2:] == [1000, 3000] and "c" not in s.each
    now[0] += 1
    s.take(items[1:], "downloading")                                               # "a" was removed
    assert "a" not in s.each and list(s.of("a")) == [0.0] * POINTS


@pytest.mark.gui
@pytest.mark.parametrize("style", ["Yeni", "Nostalji"])
def test_the_graph_is_drawn_in_every_look(make_app, style):
    from app import look
    look.apply(style, "Koyu" if style == "Yeni" else "Açık")
    try:
        app = make_app()
        graph = app.speed_graph
        assert graph is not None
        values = collections.deque([float(v * 1000) for v in range(POINTS)], maxlen=POINTS)
        app.speeds.total = values
        app.speeds.take = lambda *a: True
        app.deiconify()
        app.update()
        app._update_graphs()
        app.update()
        kinds = {graph.type(i) for i in graph.find_all()}
        assert {"polygon", "line"} <= kinds
        if style == "Nostalji":
            assert graph.cget("bg") == "#000000"                                   # green on black
            assert "text" not in kinds                                             # too small for words
        else:
            assert "text" in kinds
        app.withdraw()
    finally:
        look.apply("Klasik")


@pytest.mark.gui
def test_the_progress_window_shows_the_speed_of_its_download(make_app):
    from app import look
    from app.models import DOWNLOADING
    from ui_support import add_item
    look.apply("Nostalji")
    try:
        app = make_app()
        it = add_item(app, "Ubuntu.iso", DOWNLOADING, speed=2_000_000, total=10, done=1)
        win = app.open_progress(it)
        app.speeds.each[it.id] = collections.deque([2e6] * POINTS, maxlen=POINTS)
        app.speeds.take = lambda *a: True
        app._update_graphs()
        assert win.graph.values[-1] == 2e6
        win.destroy()
    finally:
        look.apply("Klasik")


# ------------------------------------------------------------------------------ in the music window
@pytest.fixture
def music_app(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(player, "new_eq_backend", FakeEqBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app._ensure_music()
    return app, app.music


def _items(entries):
    return {e[0]: e[1] for e in entries if e}


@pytest.mark.gui
def test_renaming_from_the_menu_keeps_the_song_playing_and_can_be_undone(music_app, tmp_path):
    app, music = music_app
    folder = tmp_path / "m"
    folder.mkdir()
    songs = [make_wav(folder / f"{n}.wav") for n in ("track01", "track02")]
    music._pick_files = lambda: songs
    music._add_files()
    for t, (artist, title) in zip(music.store.tracks(music.viewed), [("Teoman", "Gemi"), ("Teoman", "Paramparça")]):
        t["artist"], t["tag_title"] = artist, title
    music.tree.selection_set("0", "1")
    music._play_selected()
    music.controller.backend.active.position = 4200
    win = _items(music.track_menu_items())["✏ Dosya adlarını düzenle…"]()
    win.pattern.set("{no}. {sanatçı} - {şarkı}")
    win.refresh()
    assert [win.tree.set(i, "new") for i in win.tree.get_children()] == ["01. Teoman - Gemi.wav",
                                                                         "02. Teoman - Paramparça.wav"]
    win.go()
    assert sorted(os.listdir(folder)) == ["01. Teoman - Gemi.wav", "02. Teoman - Paramparça.wav"]
    c = music.controller
    assert c.current_path() == str(folder / "01. Teoman - Gemi.wav") and c.backend.active.position == 4200
    assert c.state == "playing" and music.store.state["rename_pattern"] == "{no}. {sanatçı} - {şarkı}"
    assert str(win.undo_btn.cget("state")) == "normal"
    win.take_back()
    assert sorted(os.listdir(folder)) == ["track01.wav", "track02.wav"]
    assert [t["path"] for t in music.store.tracks(music.viewed)] == [str(folder / "track01.wav"), str(folder / "track02.wav")]
    win.destroy()


@pytest.mark.gui
def test_covers_are_looked_for_from_the_menus_and_counted(music_app, tmp_path, monkeypatch):
    app, music = music_app
    songs = [make_wav(tmp_path / f"{n}.mp3") for n in ("a", "b")]
    music._pick_files = lambda: songs
    music._add_files()
    results = iter([("done", ""), ("none", "")])

    class Finder:
        def __init__(self):
            self.asked, self.out = [], []

        def find(self, path, artist, title, seconds=0, video_id="", force=False):
            self.asked.append((os.path.basename(path), force))
            self.out.append((path,) + next(results))
            return True

        def pending(self):
            return 0

        def drain(self):
            out, self.out = self.out, []
            return out
    music.cover_finder = Finder()
    _items(music.player_menu_items())["🖼 Kapağı olmayanlara kapak bul"]()
    assert music.cover_finder.asked == [("a.mp3", False), ("b.mp3", False)]
    music._take_covers()
    assert "1 şarkıya kapak kondu" in music.note_label.cget("text") and "1 şarkının kapağı bulunamadı" in \
        music.note_label.cget("text")
    music.tree.selection_set("0")
    results = iter([("done", "")])
    _items(music.track_menu_items())["🖼 Kapağı internetten bul"]()
    assert music.cover_finder.asked[-1] == ("a.mp3", True)                      # chosen by hand: also a wrong one


@pytest.mark.gui
def test_the_tag_editor_finds_a_cover_on_the_internet(music_app, tmp_path, monkeypatch):
    from PIL import Image
    app, music = music_app
    song = make_wav(tmp_path / "a.mp3")
    music._pick_files = lambda: [song]
    music._add_files()
    monkeypatch.setattr(tags, "read_fields", lambda path: {"title": "Gülpembe", "artist": "Barış Manço", "album": "",
                                                            "date": "", "genre": ""})
    picture = tmp_path / "c.jpg"
    Image.new("RGB", (64, 64), (200, 0, 0)).save(picture)
    from app import covers as cv
    asked = []
    monkeypatch.setattr(cv, "fetch_picture", lambda *a: asked.append(a[:2]) or str(picture))
    editor = music.edit_tags(music.store.tracks(music.viewed)[0])
    editor.find_cover()
    end = time.time() + 5
    while time.time() < end and editor.cover == tags.KEEP:
        app.update()
        time.sleep(0.02)
    assert asked == [("Barış Manço", "Gülpembe")] and editor.cover == str(picture)
    assert editor._image is not None and "Kaydet" in editor.hint.cget("text")
    editor.destroy()
