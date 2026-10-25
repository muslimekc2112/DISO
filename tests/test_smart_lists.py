"""✨ Smart lists: most played, recently added, never played — made from the other lists, filled by
themselves, never changed by hand. A song counts as listened to after 30 s (a short one: half of it)."""
import os

import pytest
from music_support import FakeBackend, make_wav

from app import player
from app.playlists import (SMART, SMART_MOST, SMART_NEVER, SMART_NEW, PlaylistStore, file_key)


def titles(store, name):
    return [t["title"] for t in store.tracks(name)]


@pytest.fixture
def songs(tmp_path):
    return [make_wav(tmp_path / f"{name}.mp3") for name in ("Bir", "İki", "Üç", "Dört")]


@pytest.fixture
def store(tmp_path):
    return PlaylistStore(str(tmp_path / "playlists.json"))


def test_the_smart_lists_are_always_there_and_last(store):
    assert store.names()[-len(SMART):] == list(SMART) and store.user_names() == ["Çalma listem"]
    store.create("Spor")
    assert store.names() == ["Çalma listem", "Spor", *SMART]


def test_most_played_counts_and_orders(store, songs):
    store.add("Çalma listem", songs)
    for path, times in zip(songs, (1, 3, 0, 2)):
        for i in range(times):
            store.count_play(path, when=100 + i)
    store.refresh_smart()
    assert titles(store, SMART_MOST) == ["İki", "Dört", "Bir"]           # never played ones are not in it
    assert titles(store, SMART_NEVER) == ["Üç"]
    assert store.plays(songs[1]) == 3 and store.plays(os.path.join(os.path.dirname(songs[1]), ".", "İki.mp3")) == 3


def test_recently_added_is_newest_first_and_each_song_once(store, songs):
    store.create("Spor")
    store._seen([songs[0]], 10)
    store.add("Çalma listem", songs[:2])
    store._seen([songs[2]], 30)
    store.add("Spor", [songs[2], songs[1]])                               # İki is in two lists: once
    store.stats[file_key(songs[1])]["first"] = 20
    store.refresh_smart()
    assert titles(store, SMART_NEW) == ["Üç", "İki", "Bir"]


def test_a_song_from_before_the_counting_uses_its_files_time(store, songs):
    store.lists["Çalma listem"] = [{"path": p, "title": os.path.splitext(os.path.basename(p))[0]} for p in songs[:2]]
    os.utime(songs[0], (5000, 5000))
    os.utime(songs[1], (9000, 9000))
    store.refresh_smart()
    assert titles(store, SMART_NEW) == ["İki", "Bir"]


def test_a_deleted_file_is_left_out(store, songs):
    store.add("Çalma listem", songs[:2])
    os.remove(songs[0])
    store.refresh_smart()
    assert titles(store, SMART_NEW) == ["İki"]


def test_smart_lists_cannot_be_changed_by_hand(store, songs):
    store.add("Çalma listem", songs)
    store.refresh_smart()
    before = list(store.tracks(SMART_NEW))
    assert store.add(SMART_NEW, songs) == 0 and store.copy_to(SMART_NEW, before) == 0
    store.remove(SMART_NEW, [0])
    store.clear(SMART_NEW)
    store.move(SMART_NEW, [1], -1)
    assert store.tracks(SMART_NEW) == before
    assert store.rename(SMART_NEW, "Başka") == SMART_NEW and store.delete(SMART_NEW) == SMART_NEW
    assert SMART_NEW in store.names()
    assert store.ensure(SMART_MOST) != SMART_MOST                          # a download never lands in one
    assert store.add_download(SMART_MOST, songs[0], 1.0) and store.tracks(SMART_MOST) == []


def test_counts_survive_a_restart(store, songs, tmp_path):
    store.add("Çalma listem", songs)
    store.count_play(songs[2])
    again = PlaylistStore(str(tmp_path / "playlists.json"))
    assert titles(again, SMART_MOST) == ["Üç"] and again.plays(songs[2]) == 1


def test_a_broken_stats_part_of_the_file_is_no_problem(tmp_path):
    path = tmp_path / "playlists.json"
    path.write_text('{"playlists": {"A": []}, "stats": {"x": {"plays": "çok"}, "y": 5, "z": {"plays": 2, "last": 1}}}',
                    encoding="utf-8")
    assert PlaylistStore(str(path)).stats == {"z": {"plays": 2, "last": 1.0}}


# ------------------------------------------------------------------------------ in the music window
@pytest.fixture
def music(app, monkeypatch, songs):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    m = app.music
    m.store.add(m.viewed, songs)
    m._refresh_lists()
    return m


def play_for(music, ms, length=200000):
    b = music.controller.backend.active
    b.length = length
    b.position = ms
    music._count_listening()


@pytest.mark.gui
def test_a_song_counts_after_30_seconds_and_once(music, songs):
    music.tree.selection_set("1")
    music._play_selected()
    play_for(music, 10000)
    assert music.store.plays(songs[1]) == 0                               # skipped after 10 s: not counted
    play_for(music, 31000)
    play_for(music, 60000)
    assert music.store.plays(songs[1]) == 1
    play_for(music, 500)                                                  # from the start again (repeat)
    play_for(music, 30500)
    assert music.store.plays(songs[1]) == 2


@pytest.mark.gui
def test_a_short_song_counts_after_half(music, songs):
    music.tree.selection_set("0")
    music._play_selected()
    play_for(music, 9000, length=20000)
    assert music.store.plays(songs[0]) == 0
    play_for(music, 10500, length=20000)
    assert music.store.plays(songs[0]) == 1


@pytest.mark.gui
def test_opening_a_smart_list_fills_it_and_locks_the_editing_buttons(music, songs):
    music.store.count_play(songs[3])
    music._select_list(SMART_MOST)
    assert [music.tree.item(i, "values")[1] for i in music.tree.get_children()] == ["Dört"]
    assert all(b.cget("state") == "disabled" for b in music.edit_buttons)
    assert music.count_label.cget("text").startswith("✨ Kendiliğinden dolar")
    music.tree.selection_set("0")
    labels = [e[0] for e in music.track_menu_items() if e]
    assert "✖ Listeden çıkar" not in labels
    other = dict((e[0], e[1]) for e in music.track_menu_items() if e)["➕ Başka listeye ekle"]
    assert not any(label in SMART for label, _ in other)
    music._select_list("Çalma listem")
    assert all(b.cget("state") == "normal" for b in music.edit_buttons)


@pytest.mark.gui
def test_an_empty_smart_list_says_how_it_fills(music):
    music._select_list(SMART_MOST)
    assert "30 saniye" in music.empty_hint.cget("text")


@pytest.mark.gui
def test_a_song_is_never_offered_a_smart_list(app):
    assert not any(n in SMART for n in app.playlist_names())
