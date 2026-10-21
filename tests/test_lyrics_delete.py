"""Lyrics edited by hand keep following the music, and 🗑 deleting a song's file from the right-click menu."""
import os

import pytest
from music_support import FakeBackend, FakeEqBackend, FakeReader, make_wav

from app import lyrics, player, tags

SYNCED = "\n".join(f"[00:{2 * i + 2:02d}.00]satır {i + 1}" for i in range(20))        # line i at (2i + 2) s


@pytest.fixture
def music_app(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(player, "new_eq_backend", FakeEqBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app._ensure_music()
    return app, app.music


def _add(music, paths):
    music._pick_files = lambda: list(paths)
    music._add_files()


def _items(entries):
    return {e[0]: e[1] for e in entries if e}


def _playing(music, tmp_path, name="Gülpembe", text=SYNCED, seconds=1.0):
    """A song with lyrics that plays, and the 🎤 window open for it."""
    song = make_wav(tmp_path / f"{name}.wav", seconds)
    lyrics.save(song, text)
    _add(music, [song])
    music.tree.selection_set(str(len(music.store.tracks(music.viewed)) - 1))
    music._play_selected()
    music.open_lyrics(music.controller.current_track())
    return song, music.lyrics_window


def _at(music, ms):
    """The player is at `ms`: one round of the window's clock follows it."""
    music.controller.backend.seek(ms)
    music._follow_lyrics()
    return music.lyrics_window


def _now(win):
    """(index of the marked line, its words) as the text shows them."""
    ranges = win.text.tag_ranges("now")
    if not ranges:
        return -1, ""
    return int(str(ranges[0]).split(".")[0]) - 1, win.text.get(ranges[0], ranges[1]).strip()


def _edit(win, change):
    win.edit()
    text = win.text.get("1.0", "end-1c")
    win.text.delete("1.0", "end")
    win.text.insert("1.0", change(text))
    win.save_edit()


@pytest.mark.gui
def test_following_goes_on_after_one_word_is_changed(music_app, tmp_path):
    app, music = music_app
    song, win = _playing(music, tmp_path)
    assert _now(_at(music, 6000)) == (2, "satır 3")
    _edit(win, lambda t: t.replace("satır 5", "gül 5"))
    assert not win.editing and win.synced and str(win.text.cget("state")) == "disabled"
    assert win.text.tag_ranges("edit") == () and str(win.text.cget("cursor")) == "hand2"
    assert win.close_btn.cget("text") == "Kapat" and win.save_btn is None
    assert _now(_at(music, 10000)) == (4, "gül 5")                        # right away, no restart needed
    assert _now(_at(music, 30000)) == (14, "satır 15") and win.text.yview()[0] > 0     # and it scrolls
    assert _now(_at(music, 4000)) == (1, "satır 2")


@pytest.mark.gui
def test_the_letter_size_or_theme_while_editing_does_not_lose_the_time_marks(music_app, tmp_path):
    app, music = music_app
    song, win = _playing(music, tmp_path)
    win.edit()
    win._resize(+2)                                                       # A+ while editing
    music.recolor()                                                       # the theme changes
    assert win.editing and str(win.text.cget("state")) == "normal"
    assert win.text.get("1.0", "end").strip() == SYNCED
    win.save_edit()
    assert lyrics.load(song)["synced"][3] == (8000, "satır 4")
    assert _now(_at(music, 8000)) == (3, "satır 4")


@pytest.mark.gui
def test_lines_added_without_a_time_mark_are_kept_and_followed(music_app, tmp_path):
    app, music = music_app
    song, win = _playing(music, tmp_path)
    _edit(win, lambda t: t.replace("[00:06.00]satır 3", "[00:06.00]satır 3\nyeni satır"))
    assert win.lines()[2:5] == ["satır 3", "yeni satır", "satır 4"]
    assert _now(_at(music, 7000)) == (3, "yeni satır")                   # between 6 s and 8 s
    assert _now(_at(music, 8000)) == (4, "satır 4")
    _edit(win, lambda t: "\n".join(line for line in t.splitlines() if "satır 4" not in line))   # a line goes
    assert "satır 4" not in win.lines() and _now(_at(music, 8000))[1] == "yeni satır"
    assert _now(_at(music, 10000))[1] == "satır 5"


@pytest.mark.gui
def test_plain_lyrics_pasted_over_synced_ones_keep_their_times(music_app, tmp_path):
    app, music = music_app
    song, win = _playing(music, tmp_path)
    _edit(win, lambda t: "\n".join(f"söz {i + 1}" for i in range(20)))   # the same song, without time marks
    assert win.synced and lyrics.load(song)["synced"][4] == (10000, "söz 5")
    assert _now(_at(music, 10000)) == (4, "söz 5")
    music.controller.backend.active.length = 80000
    _edit(win, lambda t: "\n".join(f"başka {i + 1}" for i in range(8)))  # quite other lyrics: spread over the song
    assert win.synced and len(win.lines()) == 8
    first = _now(_at(music, 1000))[0]
    last = _now(_at(music, 79000))[0]
    assert first <= 1 and last >= 6


@pytest.mark.gui
def test_plain_lyrics_without_old_times_and_unknown_length_stay_plain(music_app, tmp_path):
    app, music = music_app
    song, win = _playing(music, tmp_path, text="düz bir satır\nbir daha")
    assert not win.synced
    _edit(win, lambda t: t.rstrip() + "\nüçüncü")
    assert not win.synced and win.lines() == ["düz bir satır", "bir daha", "üçüncü"]
    _at(music, 1000)                                                      # nothing breaks
    assert _now(win) == (-1, "")


@pytest.mark.gui
def test_editing_another_song_than_the_one_that_plays(music_app, tmp_path):
    app, music = music_app
    playing, win = _playing(music, tmp_path)
    other = make_wav(tmp_path / "Diğer.wav")
    lyrics.save(other, "[00:01.00]bir\n[00:03.00]iki")
    _add(music, [other])
    music.edit_lyrics(music.store.tracks(music.viewed)[1])
    assert win.editing and win.path == other
    _at(music, 6000)                                                      # the player does not disturb the typing
    assert win.editing and win.path == other
    win.text.delete("1.0", "end")
    win.text.insert("1.0", "[00:01.00]bir\n[00:03.00]üç")
    win.save_edit()
    assert lyrics.load(other)["synced"][1] == (3000, "üç")
    assert _now(_at(music, 6000)) == (2, "satır 3") and win.path == playing  # back to the song that plays
    win.edit()
    win._cancel_edit()                                                    # Vazgeç
    assert not win.editing and _now(_at(music, 8000)) == (3, "satır 4")


@pytest.mark.gui
def test_lyrics_found_on_the_internet_while_editing_do_not_throw_the_typing_away(music_app, tmp_path):
    app, music = music_app
    song, win = _playing(music, tmp_path)
    win.edit()
    win.text.insert("1.0", "[00:00.50]benim satırım\n")
    music.lyrics_fetcher._done.put((song, True, ""))
    music._take_lyrics()
    assert win.editing and "benim satırım" in win.text.get("1.0", "end")
    win.save_edit()
    assert _now(_at(music, 600)) == (0, "benim satırım")


# ------------------------------------------------------------------------------ the times, without a window
def test_untimed_lines_among_timed_ones_get_a_time_between_their_neighbours():
    data = lyrics.parse("[ar:Barış Manço]\nbaşlık\n[00:10.00]bir\nara\nara 2\n[00:16.00]iki\n\n[00:20.00]üç\nson")
    assert data["synced"] == [(5000, "başlık"), (10000, "bir"), (12000, "ara"), (14000, "ara 2"),
                              (16000, "iki"), (20000, "üç"), (20000 + lyrics.LINE_GAP, "son")]
    assert lyrics.parse("düz\nsöz")["synced"] == []                       # no time marks at all: plain
    chorus = lyrics.parse("[00:10.00][00:30.00]nakarat\nek")["synced"]    # a line with two marks
    assert [w for _, w in chorus] == ["nakarat", "ek", "nakarat"]


def test_keep_times_carries_or_stretches_the_old_times():
    old = lyrics.parse("[00:01.00]a\n[00:02.00]b\n[00:03.00]\n[00:04.00]c")   # an empty timed line: a pause
    assert lyrics.keep_times("x\ny\n\nz", old) == "[00:01.00]x\n[00:02.00]y\n\n[00:04.00]z"
    stretched = lyrics.parse(lyrics.keep_times("1\n2\n3\n4", old))["synced"]   # one line more
    assert [ms for ms, _ in stretched] == [1000, 1660, 2660, 4000]
    assert lyrics.keep_times("[00:05.00]kendi", old) == "[00:05.00]kendi"     # its own marks win
    assert lyrics.keep_times("düz", None) == "düz"                            # nothing to go by
    many = lyrics.parse(lyrics.keep_times("\n".join("abcdefghij"), old, length_ms=21000))["synced"]
    assert many[0][0] == 1000 and many[-1][0] == 19000                       # spread to the song's end


# ------------------------------------------------------------------------------ 🗑 delete the file
@pytest.mark.gui
def test_delete_is_red_in_the_menu_and_asks_first(music_app, tmp_path):
    app, music = music_app
    song = make_wav(tmp_path / "Sabah.wav")
    _add(music, [song])
    music.tree.selection_set("0")
    entry = next(e for e in music.track_menu_items() if e and e[0] == "🗑 Dosyayı sil")
    assert entry[2] == {"foreground": "#D32F2F"}
    import tkinter as tk
    menu = tk.Menu(music, tearoff=0)
    music._fill_menu(menu, music.track_menu_items())
    last = menu.index("end")
    assert menu.entrycget(last, "label") == "🗑 Dosyayı sil" and str(menu.entrycget(last, "foreground")) == "#D32F2F"
    menu.destroy()
    asked = []
    music._confirm = lambda text: asked.append(text) or False                # "Hayır"
    entry[1]()
    assert asked == ["“Sabah” dosyası bilgisayardan tamamen silinsin mi? Bu geri alınamaz."]
    assert os.path.isfile(song) and len(music.store.tracks(music.viewed)) == 1


@pytest.mark.gui
def test_deleting_the_song_that_plays_moves_on_and_takes_it_out_everywhere(music_app, tmp_path):
    app, music = music_app
    songs = [make_wav(tmp_path / f"{n}.wav") for n in ("Sabah", "Ogle", "Aksam", "Gece")]
    for s in songs[:2]:
        lyrics.save(s, "[00:01.00]söz")
    _add(music, songs)
    music.store.create("Spor")
    music.store.add("Spor", [songs[0], songs[3]])
    music.tree.selection_set("0")
    music._play_selected()
    music.open_lyrics(music.controller.current_track())
    music.controller.add_to_queue([music.store.tracks(music.viewed)[1]])
    asked = []
    music._confirm = lambda text: asked.append(text) or True
    music.tree.selection_set(("0", "1"))
    _items(music.track_menu_items())["🗑 Dosyayı sil"]()
    assert asked == ["2 dosya bilgisayardan tamamen silinsin mi? Bu geri alınamaz."]
    assert not any(os.path.exists(p) for p in songs[:2])
    assert not any(os.path.exists(lyrics.lyrics_path(p)) for p in songs[:2])         # the lyrics go too
    assert [os.path.basename(t["path"]) for t in music.store.tracks(music.viewed)] == ["Aksam.wav", "Gece.wav"]
    assert [os.path.basename(t["path"]) for t in music.store.tracks("Spor")] == ["Gece.wav"]
    c = music.controller
    assert c.queue == [] and c.state == "playing" and os.path.basename(c.current_path()) == "Aksam.wav"
    assert music.lyrics_window is None                                   # its song is no more
    assert "2 dosya silindi" in music.note_label.cget("text")


@pytest.mark.gui
def test_deleting_the_last_song_that_plays_stops_and_a_paused_one_does_not_go_on(music_app, tmp_path):
    app, music = music_app
    songs = [make_wav(tmp_path / f"{n}.wav") for n in ("Bir", "İki")]
    _add(music, songs)
    music._confirm = lambda text: True
    music.tree.selection_set("1")
    music._play_selected()
    music.controller.toggle()                                            # paused
    music.delete_files()
    c = music.controller
    assert not os.path.exists(songs[1]) and c.state == "stopped"
    music.tree.selection_set("0")
    music._play_selected()
    music.delete_files()
    assert not os.path.exists(songs[0]) and c.state == "stopped" and music.store.tracks(music.viewed) == []


@pytest.mark.gui
def test_a_file_that_cannot_be_deleted_keeps_playing(music_app, tmp_path, monkeypatch):
    app, music = music_app
    songs = [make_wav(tmp_path / f"{n}.wav") for n in ("Bir", "İki")]
    _add(music, songs)
    music._confirm = lambda text: True
    music.tree.selection_set("0")
    music._play_selected()
    music.controller.backend.seek(700)
    real = os.remove

    def locked(path):
        if path == songs[0]:
            raise PermissionError("in use")
        real(path)
    monkeypatch.setattr(os, "remove", locked)
    assert music.delete_files() == 0
    c = music.controller
    assert os.path.isfile(songs[0]) and c.state == "playing" and c.current_path() == songs[0]
    assert c.position_ms() == 700 and len(music.store.tracks(music.viewed)) == 2
    assert "silinemedi" in music.note_label.cget("text")
