"""1.2 in the music window: ← / → once (5 s) and twice (the song before / after), the ⏪ 5 / 5 ⏩ buttons, the
playing speed, ordering a list (and getting one's own order back), the window taking the cover's colour, and
the visualizer's controls and round cover."""
import os
import time

import pytest
from music_support import FakeBackend, FakeReader, make_wav

from app import ambient, hotkeys, player, playlists, tags, visualizer
from app.music_ui import ORDER_NAMES, SEEK_STEP

pytestmark = pytest.mark.gui


@pytest.fixture
def music_app(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app.manager.set_gate(False)
    app._ensure_music()
    return app, app.music


@pytest.fixture
def songs(tmp_path):
    return [make_wav(tmp_path / f"{n}.wav") for n in ("Sabah", "Öğle", "Akşam", "Çay")]


def add(music, paths):
    music._pick_files = lambda: paths
    music._add_files()


def playing(music, index=0):
    music.tree.selection_set(str(index))
    music._play_selected()
    backend = music.controller.backend.active
    backend.length = 200000
    return backend


class Key:
    def __init__(self, widget, keysym):
        self.widget, self.keysym = widget, keysym


# ------------------------------------------------------------------------------ ← / →
def test_the_arrows_are_the_default_keys_for_five_seconds():
    assert hotkeys.DEFAULT_KEYS["seek_forward"] == "Right" and hotkeys.DEFAULT_KEYS["seek_back"] == "Left"
    assert hotkeys.needs_quiet_typing("Right")                      # typing in a box keeps its arrows


def test_right_once_is_five_seconds_twice_is_the_next_song(music_app, songs):
    _, music = music_app
    add(music, songs)
    backend = playing(music, 1)
    backend.position = 60000
    assert music.tap("seek_forward", "Right", now=100.0) == "seek"
    assert backend.position == 60000 + SEEK_STEP
    music._on_key_release(Key(music, "Right"))
    assert music.tap("seek_forward", "Right", now=100.3) == "song"
    assert music.controller.current_title() == "Akşam"
    music._on_key_release(Key(music, "Right"))
    backend = music.controller.backend.active
    backend.length = 200000
    assert music.tap("seek_forward", "Right", now=105.0) == "seek"     # long after: just 5 s again
    assert music.controller.current_title() == "Akşam" and backend.position == SEEK_STEP


def test_left_once_is_five_seconds_back_twice_is_the_song_before(music_app, songs):
    _, music = music_app
    add(music, songs)
    backend = playing(music, 2)
    backend.position = 50000
    music.tap("seek_back", "Left", now=10.0)
    assert backend.position == 50000 - SEEK_STEP
    music._on_key_release(Key(music, "Left"))
    music.tap("seek_back", "Left", now=10.2)
    assert music.controller.current_title() == "Öğle"           # not the start of "Akşam": the one before


def test_holding_the_key_keeps_seeking_and_is_no_double_press(music_app, songs):
    _, music = music_app
    add(music, songs)
    backend = playing(music, 0)
    backend.position = 10000
    for k in range(4):                                           # the key's own repeats, no release between
        assert music.tap("seek_forward", "Right", now=1.0 + k * 0.03) == "seek"
    assert backend.position == 10000 + 4 * SEEK_STEP and music.controller.current_title() == "Sabah"


def test_the_key_goes_through_the_shortcut_binding_but_not_while_typing(music_app, songs):
    _, music = music_app
    add(music, songs)
    backend = playing(music, 0)
    backend.position = 20000
    assert music._on_shortcut(Key(music.tree, "Right"), "seek_forward", True) == "break"
    assert backend.position == 20000 + SEEK_STEP
    entry = music.filter_entry._entry
    assert music._on_shortcut(Key(entry, "Right"), "seek_forward", True) is None
    assert backend.position == 20000 + SEEK_STEP


def test_the_buttons_and_the_end_of_the_song(music_app, songs):
    _, music = music_app
    add(music, songs)
    backend = playing(music, 0)
    backend.position = 3000
    music.back_btn.invoke()
    assert backend.position == 0                                 # not before the start
    music.forward_btn.invoke()
    assert backend.position == SEEK_STEP
    backend.position = backend.length - 2000
    music.forward_btn.invoke()                                   # past the end: the next song
    assert music.controller.current_title() == "Öğle"
    music._stop()
    assert music.seek_by(SEEK_STEP) is False                     # nothing plays: nothing to move


# ------------------------------------------------------------------------------ ⏩ speed
def test_the_speed_menu_plays_faster_and_remembers_it(music_app, songs):
    _, music = music_app
    add(music, songs)
    playing(music, 0)
    items = {e[0].strip("● ").strip(): e[1] for e in music.speed_menu_items() if e}
    items["2x"]()
    switching = music.controller.backend
    assert switching.tempo == (2.0, 0) and switching.active is switching.eq
    assert music.speed_btn.cget("text") == "2x" and music.store.state["speed"] == 2.0
    pitches = {e[0].strip("● ").strip(): e[1] for e in dict((e[0], e[1]) for e in music.speed_menu_items() if e)[
        "🎵 Perde (ses inceliği)"]}
    pitches["+2 yarım ses"]()
    assert switching.tempo == (2.0, 2) and music.speed_btn.cget("text") == "2x +2"
    assert music.set_tempo(9, -40) and switching.tempo == (4.0, -12)        # kept inside what can play
    items["↺ Normale döndür"]() if "↺ Normale döndür" in items else music.set_tempo(1.0, 0)
    assert switching.tempo == (1.0, 0) and music.speed_btn.cget("text") == "1x"


def test_a_saved_speed_is_used_when_the_player_opens(app, monkeypatch, tmp_path):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    store = playlists.PlaylistStore()
    store.set_state(speed=1.5, pitch=0)
    app._ensure_music()
    assert app.music.controller.backend.tempo == (1.5, 0)
    assert app.music.speed_btn.cget("text") == "1.5x"


# ------------------------------------------------------------------------------ ⇅ order
def test_ordering_a_list_and_getting_ones_own_order_back(music_app, songs, monkeypatch):
    _, music = music_app
    add(music, songs)
    titles = lambda: [t["title"] for t in music.store.tracks(music.viewed)]     # noqa: E731
    own = titles()
    assert music.order_menu.get() == "Kendi sıram"
    music._choose_order("A → Z")
    assert titles() == ["Akşam", "Çay", "Öğle", "Sabah"]                       # the Turkish alphabet
    music._choose_order("Z → A")
    assert titles() == ["Sabah", "Öğle", "Çay", "Akşam"]
    store = music.store
    for k, (path, when) in enumerate(zip(songs, (400, 100, 300, 200))):
        store.stats[playlists.file_key(path)]["first"] = float(when)
    music._choose_order("Son eklenen en başta")
    assert titles() == ["Sabah", "Akşam", "Çay", "Öğle"]
    music._choose_order("Son eklenen en sonda")
    assert titles() == ["Öğle", "Çay", "Akşam", "Sabah"]
    store.count_play(songs[3])
    store.count_play(songs[3])
    store.count_play(songs[1])
    music._choose_order("En popüler en başta")
    assert titles()[:2] == ["Çay", "Öğle"]
    assert music.order_menu.get() == "En popüler en başta"
    music._choose_order("Kendi sıram")
    assert titles() == own and music.order_menu.get() == "Kendi sıram"


def test_a_sorted_list_keeps_its_order_for_new_songs_and_a_move_makes_it_ones_own(music_app, songs, tmp_path):
    _, music = music_app
    add(music, songs[:3])
    music._choose_order("A → Z")
    add(music, [make_wav(tmp_path / "Bahar.wav")])
    titles = [t["title"] for t in music.store.tracks(music.viewed)]
    assert titles == ["Akşam", "Bahar", "Öğle", "Sabah"]
    music.tree.selection_set("3")
    music._move(-1)                                                            # by hand: this order is the own one
    assert music.store.order_of(music.viewed) == playlists.ORDER_OWN
    assert music.order_menu.get() == "Kendi sıram"
    music._choose_order("Kendi sıram")
    assert [t["title"] for t in music.store.tracks(music.viewed)] == ["Akşam", "Bahar", "Sabah", "Öğle"]


def test_the_order_is_kept_on_disk_and_follows_a_renamed_list(songs, tmp_path):
    store = playlists.PlaylistStore()
    store.add(playlists.DEFAULT_NAME, songs)
    store.order(playlists.DEFAULT_NAME, playlists.ORDER_ZA)
    name = store.rename(playlists.DEFAULT_NAME, "Benim")
    again = playlists.PlaylistStore()
    assert again.order_of(name) == playlists.ORDER_ZA
    assert again.order(name, playlists.ORDER_OWN)
    assert [t["title"] for t in again.tracks(name)] == ["Sabah", "Öğle", "Akşam", "Çay"]
    assert not again.order(playlists.SMART_NEW, playlists.ORDER_AZ)            # a smart list cannot
    assert not again.order(name, "nonsense")


def test_every_order_has_a_name():
    assert set(ORDER_NAMES) == set(playlists.ORDERS)


# ------------------------------------------------------------------------------ 🎨 the cover's colour
def _cover(tmp_path, colour):
    from PIL import Image
    path = str(tmp_path / f"cover_{colour}.jpg")
    img = Image.new("RGB", (100, 100), (20, 20, 20))
    img.paste(Image.new("RGB", (70, 70), colour), (15, 15))
    img.save(path)
    return path


def test_the_main_colour_of_a_cover_is_the_lively_one(tmp_path):
    red = ambient.main_colour(_cover(tmp_path, "#d02030"))
    r, g, b = ambient._hex(red)
    assert r > 150 and g < 80 and b < 90
    assert ambient.main_colour(str(tmp_path / "none.jpg")) is None
    light, dark = ambient.background(red, ("#f0f0f0", "#202020"))
    assert light != "#f0f0f0" and dark != "#202020"
    assert ambient._hex(dark)[0] > ambient._hex(dark)[2]                     # a hint of red in the dark one
    assert ambient.background(None, ("#f0f0f0", "#202020")) == ("#f0f0f0", "#202020")
    pal = ambient.palette([red, "#ffcc00"])
    assert len(pal) == 5 and all(p.startswith("#") and len(p) == 7 for p in pal)


def test_the_window_takes_the_covers_colour_and_gives_it_back(music_app, songs, tmp_path):
    _, music = music_app
    add(music, songs)
    playing(music, 0)
    plain = music._ambient_target(None)
    music._covers[music.controller.current_path()] = jpg = _cover(tmp_path, "#2050e0")
    music._set_cover(jpg)
    for _ in range(20):
        music.update()
        time.sleep(0.03)
    tinted = music._ambient_now
    assert tinted is not None and tinted != plain
    assert music.cget("fg_color") == (tinted[0], tinted[1])
    music.set_ambient(False)
    for _ in range(20):
        music.update()
        time.sleep(0.03)
    assert music._ambient_now == plain
    music.set_ambient(True)
    music._set_cover(None)                                                    # a song without a cover: plain
    for _ in range(20):
        music.update()
        time.sleep(0.03)
    assert music._ambient_now == plain


# ------------------------------------------------------------------------------ 🌌 the visualizer
class ReadyAnalyzer:
    def __init__(self, result):
        self.result = result

    def want(self, path):
        pass

    def get(self, path):
        return self.result

    def busy(self, path):
        return False


def test_the_visualizer_has_controls_and_the_cover_in_the_ring(music_app, songs, tmp_path, monkeypatch):
    import numpy as np
    _, music = music_app
    add(music, songs)
    backend = playing(music, 1)
    backend.position = 30000
    music._covers[music.controller.current_path()] = _cover(tmp_path, "#20b060")
    t = np.arange(visualizer.RATE * 3) / visualizer.RATE
    win = music.open_visualizer()
    win.analyzer = ReadyAnalyzer(visualizer.analyse_samples((0.5 * np.sin(2 * np.pi * 800 * t)).astype(np.float32)))
    win.geometry("900x600")
    win.set_style("Halka")
    win.update()
    for _ in range(10):
        win.step()
    assert win._cover_palette is not None and win.palette == win._cover_palette
    assert win.items.get("cover") is not None and len(win._pictures["cover"]) > 1
    assert win.palette_menu.get() == "🎨 Kapaktan"
    win.forward_btn.invoke()
    assert backend.position == 30000 + SEEK_STEP
    win.back_btn.invoke()
    win.back_btn.invoke()
    assert backend.position == 30000 - SEEK_STEP
    win.next_btn.invoke()
    assert music.controller.current_title() == "Akşam"
    win.prev_btn.invoke()
    win.play_btn.invoke()
    assert music.controller.state == "paused"
    for _ in range(8):
        win.step()
    assert win.play_btn.cget("text") == "▶"
    win.set_palette("Neon")
    assert win.palette == visualizer.PALETTES["Neon"]
    shown = []
    monkeypatch.setattr(win, "attributes", lambda *a: shown.append(a))
    win.toggle_full()
    assert not win.controls.winfo_ismapped()
    win._show_controls_for_a_while()
    win.update()
    assert win.controls.winfo_ismapped()
    win._hide_controls()
    win.update()
    assert not win.controls.winfo_ismapped()
    win.toggle_full()
    win.destroy()


def test_the_new_icon_and_the_round_picture(tmp_path):
    from app import visualizer_ui
    icon = visualizer_ui.icon_image(20)
    assert icon is not None and icon.cget("size") == (20, 20)
    pic = visualizer_ui.round_picture(_cover(tmp_path, "#ff8800"), 120)
    assert pic.size == (120, 120) and pic.getpixel((0, 0))[3] == 0 and pic.getpixel((60, 60))[3] == 255
    assert visualizer_ui.round_picture(str(tmp_path / "missing.jpg"), 50) is None
    glow = visualizer_ui.glow_picture(300, 200, visualizer.PALETTES["Mor"], 0.5)
    assert glow.size == (300, 200)
    assert sum(glow.getpixel((150, 100))) > sum(glow.getpixel((0, 0)))     # bright in the middle
