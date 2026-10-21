"""The features of the second round of 1.1: .m3u lists, lyrics and tags by hand, the dark "Nostalji",
the clipboard question, FLAC / Ogg / Opus on the ffmpeg player, even volume, and checking / finishing a
downloaded file."""
import os
import subprocess
import time
import zipfile

import pytest
from media_support import FFMPEG, FFPROBE
from music_support import FakeBackend, FakeEqBackend, FakeReader, make_wav

from app import loudness, lyrics, player, playlists, repair, tags


# ------------------------------------------------------------------------------ 📤 .m3u lists
def test_a_list_is_written_as_m3u_and_read_back(tmp_path):
    music = tmp_path / "Müzik"
    (music / "alt").mkdir(parents=True)
    a = make_wav(music / "Barış Manço - Gülpembe.wav")
    b = make_wav(music / "alt" / "b.wav")
    elsewhere = make_wav(tmp_path / "c.wav")
    tracks = [{"path": a, "title": "Barış Manço - Gülpembe", "duration": 312000},
              {"path": b, "title": "b", "artist": "Sezen Aksu", "tag_title": "Gülümse"},
              {"path": elsewhere, "title": "c"}]
    target = music / "liste.m3u8"
    assert playlists.write_m3u(tracks, str(target)) == 3
    text = target.read_text(encoding="utf-8")
    assert text.splitlines()[:3] == ["#EXTM3U", "#EXTINF:312,Barış Manço - Gülpembe", "Barış Manço - Gülpembe.wav"]
    assert os.path.join("alt", "b.wav") in text and "#EXTINF:-1,Sezen Aksu - Gülümse" in text
    assert os.path.abspath(elsewhere) in text                      # outside the list's folder: the full path
    assert playlists.read_m3u(str(target)) == [os.path.abspath(p) for p in (a, b, elsewhere)]


def test_m3u_of_other_players_file_addresses_pls_and_old_code_pages(tmp_path):
    song = make_wav(tmp_path / "Şarkı.wav")
    (tmp_path / "eski.m3u").write_bytes(("#EXTM3U\r\nŞarkı.wav\r\nyok.wav\r\nhttp://radyo.example/yayin\r\n"
                                         "notes.txt\r\n").encode("cp1254"))
    assert playlists.read_m3u(str(tmp_path / "eski.m3u")) == [song]
    uri = "file:///" + song.replace("\\", "/").replace(" ", "%20")
    (tmp_path / "uri.m3u").write_text(uri + "\n", encoding="utf-8")
    assert playlists.read_m3u(str(tmp_path / "uri.m3u")) == [os.path.normpath(song)]
    (tmp_path / "a.pls").write_text(f"[playlist]\nFile1={song}\nTitle1=Şarkı\nNumberOfEntries=1\n", encoding="utf-8")
    assert playlists.read_m3u(str(tmp_path / "a.pls")) == [song]


# ------------------------------------------------------------------------------ ✎ lyrics by hand
def test_lyrics_written_by_hand_are_kept_and_empty_text_deletes_them(tmp_path):
    song = make_wav(tmp_path / "a.wav")
    assert lyrics.raw(song) == ""
    assert lyrics.write_by_hand(song, "[00:01.00]Bir\n[00:03.50]İki\n") is True
    assert lyrics.load(song)["synced"] == [(1000, "Bir"), (3500, "İki")]
    assert lyrics.raw(song).startswith("[00:01.00]Bir")
    assert lyrics.write_by_hand(song, "   \n") is False and not lyrics.has_lyrics(song)


# ------------------------------------------------------------------------------ 🏷 tags
def test_the_tag_command_copies_the_sound_and_sets_the_names(tmp_path):
    args = tags.write_args("a.mp3", "o.mp3", {"title": "Ad", "artist": ""}, tags.KEEP)
    assert args[args.index("-map") + 1] == "0" and "-c" in args and args[args.index("-c") + 1] == "copy"
    assert "title=Ad" in args and "artist=" in args and "album=" not in " ".join(args)
    assert args[-3:] == ["-id3v2_version", "3", "o.mp3"]
    new = tags.write_args("a.m4a", "o.m4a", {}, "c.jpg", "c.jpg")
    assert new[new.index("-i", 6) + 1] == "c.jpg" and "1:0" in new and "attached_pic" in new
    gone = tags.write_args("a.flac", "o.flac", {}, tags.REMOVE)
    assert "0:a" in gone and "1:0" not in gone
    ogg = tags.write_args("a.opus", "o.opus", {"title": "x"}, tags.KEEP)
    assert ogg[ogg.index("title=x") - 1] == "-metadata:s:a:0"          # Ogg keeps tags on the sound


@pytest.mark.ffmpeg
@pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not found")
@pytest.mark.parametrize("ext,codec", [(".mp3", "libmp3lame"), (".m4a", "aac"), (".flac", "flac"),
                                       (".opus", "libopus")])
def test_tags_and_cover_are_written_into_real_files(tmp_path, ext, codec):
    from PIL import Image
    tmp_path = tmp_path / "songs"
    tmp_path.mkdir()
    song = str(tmp_path / f"Şarkı{ext}")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=2", "-metadata", "title=Eski",
                    "-c:a", codec, song], check=True)
    picture = str(tmp_path / "kapak.png")
    Image.new("RGB", (900, 900), (200, 30, 30)).save(picture)
    tags.write_tags(song, {"title": "Yeni Ad", "artist": "Sanatçı", "album": "Albüm", "date": "1999", "genre": "Pop"},
                    cover=picture)
    assert tags.read_fields(song) == {"title": "Yeni Ad", "artist": "Sanatçı", "album": "Albüm", "date": "1999",
                                      "genre": "Pop"}
    assert tags.probe(song)["cover"] is (ext in tags.COVER_FORMATS)
    tags.write_tags(song, {"artist": ""}, cover=tags.REMOVE)
    assert tags.read_fields(song)["artist"] == "" and tags.read_fields(song)["title"] == "Yeni Ad"
    assert not tags.probe(song)["cover"]
    assert sorted(os.listdir(tmp_path)) == sorted([os.path.basename(song), "kapak.png"])     # nothing left over


def test_a_failed_tag_write_leaves_the_song_as_it_was(tmp_path, monkeypatch):
    song = make_wav(tmp_path / "a.wav")
    before = open(song, "rb").read()
    monkeypatch.setattr(tags, "_tool", lambda name: None)
    with pytest.raises(OSError):
        tags.write_tags(song, {"title": "x"})
    assert open(song, "rb").read() == before


def test_the_song_that_plays_is_let_go_while_its_tags_are_written(tmp_path):
    songs = [make_wav(tmp_path / f"{n}.wav") for n in "ab"]
    c = player.Controller(FakeBackend())
    c.set_tracks([{"path": p, "title": os.path.basename(p)} for p in songs])
    c.play_index(0)
    c.backend.position = 2500
    assert c.let_go(songs[1]) is None                       # another song: nothing to let go
    place = c.let_go(songs[0])
    assert place == (2500, "playing") and c.backend.loaded is None
    c.take_back(place)
    assert c.backend.loaded == songs[0] and c.backend.position == 2500 and c.backend.playing and c.state == "playing"
    c.toggle()
    place = c.let_go(songs[0])
    c.take_back(place)
    assert c.state == "paused" and not c.backend.playing


# ------------------------------------------------------------------------------ 🎵 FLAC / Ogg / Opus
def test_flac_ogg_and_opus_are_music_and_go_to_the_ffmpeg_player():
    for name in ("a.flac", "a.OGG", "a.opus", "a.oga", "a.aiff"):
        assert player.is_audio(name) and player.is_music(name) and player.needs_ffmpeg(name)
    assert not player.needs_ffmpeg("a.mp3") and not player.needs_ffmpeg(None)
    plain, eq = FakeBackend(), FakeEqBackend()
    b = player.SwitchingBackend(plain, lambda: eq)
    b.set_volume(40)
    assert b.load("x.flac") and b.active is eq and eq.loaded == "x.flac" and eq.volume == 40
    assert b.set_filter("") and b.active is eq                 # a flat equalizer cannot take a FLAC to MCI
    assert b.load("y.mp3") and b.active is plain and plain.loaded == "y.mp3" and eq.loaded is None
    b.set_filter("equalizer=f=60")
    assert b.active is eq
    assert b.load("z.mp3") and b.active is eq and eq.filter == "equalizer=f=60"     # the equalizer stays on


# ------------------------------------------------------------------------------ 🔊 even volume
def test_loud_songs_get_less_of_the_volume_quiet_ones_all_of_it():
    assert loudness.factor(None) == 1.0 and loudness.factor(-20) == 1.0 and loudness.factor(-14) == 1.0
    assert loudness.factor(-8) == pytest.approx(0.501, abs=0.002)        # 6 dB too loud: half
    assert loudness.factor(5) == pytest.approx(0.251, abs=0.002)         # never more than 12 dB softer


def test_the_leveler_measures_once_and_remembers(tmp_path):
    song = make_wav(tmp_path / "a.wav")
    asked = []
    lev = loudness.Leveler(str(tmp_path / "loud.json"), measure_fn=lambda p: asked.append(p) or -8.0)
    assert lev.gain(song) == 1.0
    lev.request(song)
    end = time.time() + 5
    while time.time() < end and not lev.drain():
        time.sleep(0.02)
    assert lev.gain(song) == pytest.approx(0.501, abs=0.002)
    lev.request(song)
    again = loudness.Leveler(str(tmp_path / "loud.json"), measure_fn=lambda p: asked.append(p))
    assert again.known(song) and again.gain(song) == lev.gain(song) and asked == [song]
    with open(song, "ab") as f:                                          # the file changed: measured again
        f.write(b"\0\0")
    assert not again.known(song) and again.gain(song) == 1.0


def test_the_player_plays_each_song_at_its_level_also_in_a_cross_fade(tmp_path):
    songs = [make_wav(tmp_path / f"{n}.wav") for n in ("yuksek", "sessiz")]
    clock = [0.0]
    c = player.Controller(FakeBackend(), spare=FakeBackend(), clock=lambda: clock[0])
    c.set_tracks([{"path": p, "title": os.path.basename(p)} for p in songs])
    c.set_volume(80)
    c.gain = lambda p: 0.5 if "yuksek" in p else 1.0
    c.play_index(0)
    assert c.backend.volume == 40
    c.set_volume(60)
    assert c.backend.volume == 30
    c.fade_ms = 1000
    c.backend.length, c.backend.position = 10000, 9500
    c.tick()                                                              # the fade starts
    old, new = c.spare, c.backend
    clock[0] = 0.5
    c.tick()
    assert old.volume == 15 and new.volume == 30                          # half of each one's own level
    clock[0] = 2
    c.tick()
    assert new.volume == 60 and not c.fading
    c.gain = None
    c.relevel()
    assert c.backend.volume == 60


# ------------------------------------------------------------------------------ 🔧 is the file whole?
def test_a_file_whose_end_is_missing_is_finished_from_the_server(server, tmp_path):
    name, data = server.file(300_000, ".zip")
    path = str(tmp_path / "a.zip")
    open(path, "wb").write(data[:200_000])
    v = repair.check(path, server.url("f", name))
    assert v.status == repair.SHORT and v.missing == 100_000 and v.resumable
    seen = []
    assert repair.complete_tail(path, server.url("f", name), progress=seen.append) == 100_000
    assert open(path, "rb").read() == data and seen[-1] == 100_000
    open(path, "wb").write(data[:200_000])
    with pytest.raises(OSError):                                          # the server sends all or nothing
        repair.complete_tail(path, server.url("norange", name))
    assert open(path, "rb").read() == data[:200_000]


def test_broken_archives_pictures_and_pdfs_are_found(tmp_path):
    good = tmp_path / "iyi.zip"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("a.txt", "merhaba " * 1000)
    assert repair.check(str(good)).status == repair.OK
    broken = tmp_path / "bozuk.zip"
    broken.write_bytes(good.read_bytes()[:-40])
    assert repair.check(str(broken)).status == repair.BROKEN
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4\n...")
    assert repair.check(str(tmp_path / "a.pdf")).detail == "sonu eksik"
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4\n...\n%%EOF\n")
    assert repair.check(str(tmp_path / "b.pdf")).status == repair.OK
    from PIL import Image
    Image.new("RGB", (64, 64)).save(tmp_path / "r.png")
    (tmp_path / "half.png").write_bytes((tmp_path / "r.png").read_bytes()[:60])
    assert repair.check(str(tmp_path / "r.png")).status == repair.OK
    assert repair.check(str(tmp_path / "half.png")).status == repair.BROKEN
    (tmp_path / "bos.bin").write_bytes(b"")
    assert repair.check(str(tmp_path / "bos.bin")).status == repair.EMPTY
    assert repair.check(str(tmp_path / "yok.bin")).status == repair.MISSING
    (tmp_path / "x.exe").write_bytes(b"MZ" + b"\0" * 100)                 # nothing to read through: fine
    assert repair.check(str(tmp_path / "x.exe")).status == repair.OK


@pytest.mark.ffmpeg
@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not found")
def test_a_cut_off_video_is_found(tmp_path):
    video = str(tmp_path / "v.mp4")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=d=2:s=160x120", "-f", "lavfi",
                    "-i", "sine=d=2", "-shortest", "-c:v", "libx264", "-c:a", "aac", video], check=True)
    assert repair.check(video).status == repair.OK
    data = open(video, "rb").read()
    cut = str(tmp_path / "kesik.mp4")
    open(cut, "wb").write(data[: len(data) // 2])
    assert repair.check(cut).status == repair.BROKEN


# ------------------------------------------------------------------------------ the dark "Nostalji"
def test_nostalgia_takes_dark_grey_from_the_theme_and_the_others_do_not():
    from app import look
    try:
        look.apply("Nostalji", "Koyu")
        assert look.is_dark_nostalgia() and look.N_FACE == look.N_DARK["N_FACE"] and look.appearance("light") == "dark"
        look.apply("Nostalji", "Açık")
        assert not look.is_dark_nostalgia() and look.N_FACE == "#F0F0F0" and look.appearance("dark") == "light"
        look.apply("Yeni", "Koyu")
        assert not look.is_dark_nostalgia() and look.N_FACE == "#F0F0F0" and look.appearance("dark") == "dark"
        assert look.wants_dark("Koyu") and not look.wants_dark("Açık")
    finally:
        look.apply("Klasik")


# ------------------------------------------------------------------------------ in the windows
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
def test_a_list_goes_out_as_m3u_and_comes_back_as_a_new_list(music_app, tmp_path):
    app, music = music_app
    songs = [make_wav(tmp_path / f"{n}.wav") for n in ("Sabah", "Gece")]
    music._pick_files = lambda: songs
    music._add_files()
    target = str(tmp_path / "out" / "Benim liste.m3u8")
    os.makedirs(os.path.dirname(target))
    music._pick_m3u_target = lambda name: target
    menu = _items(music.player_menu_items())
    menu["📤 Bu listeyi dışa aktar (.m3u)…"]()
    assert playlists.read_m3u(target) == [os.path.abspath(p) for p in songs]
    music._pick_m3u_source = lambda: target
    menu["📥 Liste içe aktar (.m3u)…"]()
    assert music.viewed == "Benim liste" and [t["path"] for t in music.store.tracks("Benim liste")] == \
        [os.path.abspath(p) for p in songs]


@pytest.mark.gui
def test_lyrics_are_written_by_hand_in_the_lyrics_window(music_app, tmp_path):
    app, music = music_app
    song = make_wav(tmp_path / "Gülpembe.wav")
    music._pick_files = lambda: [song]
    music._add_files()
    music.tree.selection_set("0")
    _items(music.track_menu_items())["✎ Sözleri elle yaz / düzenle"]()
    win = music.lyrics_window
    assert win.editing and win.text.get("1.0", "end").strip() == ""
    win.text.insert("1.0", "[00:02.00]Sen gülünce\n[00:05.00]güller açar")
    win.follow(music.store.tracks(music.viewed)[0], 3000)                 # the player does not disturb the typing
    win.save_edit()
    assert not win.editing and win.synced and win.lines() == ["Sen gülünce", "güller açar"]
    assert lyrics.load(song)["synced"][0] == (2000, "Sen gülünce")
    win.edit()
    win.text.delete("1.0", "end")
    win._cancel_edit()                                                    # "Vazgeç": nothing changes
    assert lyrics.has_lyrics(song) and win.close_btn.cget("text") == "Kapat"
    win.destroy()


@pytest.mark.gui
def test_the_tag_editor_writes_and_the_lists_show_the_new_names(music_app, tmp_path, monkeypatch):
    app, music = music_app
    song = make_wav(tmp_path / "a.wav")
    music._pick_files = lambda: [song]
    music._add_files()
    music.tree.selection_set("0")
    monkeypatch.setattr(tags, "read_fields", lambda path: {"title": "Eski", "artist": "", "album": "", "date": "",
                                                            "genre": ""})
    written = []
    editor = _items(music.track_menu_items())["🏷 Bilgileri düzenle (ad, sanatçı, kapak)…"]()
    assert editor.entries["title"].get() == "Eski" and str(editor.pick_btn.cget("state")) == "disabled"   # a wav
    editor._write = lambda path, fields, cover: written.append((path, fields, cover))
    editor.entries["title"].delete(0, "end")
    editor.entries["title"].insert(0, "Gülpembe")
    editor.entries["artist"].insert(0, "Barış Manço")
    editor.save()
    end = time.time() + 5
    while time.time() < end and editor.winfo_exists():
        app.update()
        time.sleep(0.02)
    assert written[0][0] == song and written[0][1]["title"] == "Gülpembe" and written[0][2] == tags.KEEP
    track = music.store.tracks(music.viewed)[0]
    assert track["tag_title"] == "Gülpembe" and track["artist"] == "Barış Manço"
    assert music.tree.item("0", "values")[1:3] == ("Gülpembe", "Barış Manço")


@pytest.mark.gui
def test_even_volume_is_switched_in_the_menu_and_kept(music_app, tmp_path):
    app, music = music_app
    assert music.controller.gain is None
    label = next(e[0] for e in music.player_menu_items() if e and "Ses seviyesini" in e[0])
    _items(music.player_menu_items())[label]()
    assert music.store.state["level"] and music.controller.gain == music.leveler.gain
    label = next(e[0] for e in music.player_menu_items() if e and "Ses seviyesini" in e[0])
    assert label.startswith("✓")
    _items(music.player_menu_items())[label]()
    assert not music.store.state["level"] and music.controller.gain is None


@pytest.mark.gui
def test_a_copied_link_asks_first_and_goes_with_the_answer(app, monkeypatch):
    added = []
    monkeypatch.setattr(app, "add_urls", lambda urls, kind=None: added.append((urls, kind)) or len(urls))
    monkeypatch.setattr(app, "_clipboard_text", lambda: "https://www.youtube.com/watch?v=abc")
    app.clip_var.set(True)
    app._last_clip = ""
    app._watch_clipboard()
    prompt = app.clip_prompt
    assert prompt.winfo_exists() and prompt.urls == ["https://www.youtube.com/watch?v=abc"] and added == []
    prompt.buttons["audio"].invoke()
    assert added == [(["https://www.youtube.com/watch?v=abc"], "audio")]
    app._watch_clipboard()                                                # the same text: not asked again
    assert added == [(["https://www.youtube.com/watch?v=abc"], "audio")]
    app.ask_clip(["https://a.example/x.zip"]).choose(None)                # "Hayır" / it went by itself
    assert len(added) == 1
    app.cfg.set("clip_ask", False)
    monkeypatch.setattr(app, "_clipboard_text", lambda: "https://a.example/y.zip")
    app._watch_clipboard()
    assert added[-1] == (["https://a.example/y.zip"], None)


@pytest.mark.gui
def test_checking_a_finished_download_offers_to_finish_it(app, server, tmp_path, monkeypatch):
    from tkinter import messagebox
    from ui_support import add_item

    from app.models import DONE
    real = tmp_path / "real.zip"
    with zipfile.ZipFile(real, "w") as z:                                 # a real archive: it is read through too
        z.writestr("a.bin", os.urandom(150_000))
    data = real.read_bytes()
    name = server.add(data, ".zip")
    path = str(tmp_path / "a.zip")
    open(path, "wb").write(data[:100_000])
    it = add_item(app, "a.zip", DONE, url=server.url("f", name), final_path=path, folder=str(tmp_path))
    asked = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a[1]) or True)
    menu = dict(app_menu(app, it))
    menu["🔧 Dosyayı kontrol et / onar"]()
    end = time.time() + 10
    while time.time() < end and open(path, "rb").read() != data:
        app.update()
        time.sleep(0.02)
    assert open(path, "rb").read() == data and "sonu eksik" in asked[0]
    while time.time() < end and getattr(it, "_checking", False):
        app.update()
        time.sleep(0.02)
    app.check_file(it)
    while time.time() < end and getattr(it, "_checking", False):
        app.update()
        time.sleep(0.02)
    assert len(asked) == 1                                                # whole now: nothing to ask


def app_menu(app, item):
    from app.ui import ItemMenu
    return ItemMenu(item, app).menu_commands()
