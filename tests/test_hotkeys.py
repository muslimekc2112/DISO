"""⌨ Shortcuts the user sets: how keys are read, shown and turned into global ones, and the window that
sets them (inside the music window and everywhere)."""
from types import SimpleNamespace

import pytest
from music_support import FakeBackend

from app import hotkeys, player


def test_keys_are_shown_and_checked():
    assert hotkeys.shown("Control-Right") == "Ctrl + →" and hotkeys.shown("space") == "Boşluk"
    assert hotkeys.shown("Control-Alt-p") == "Ctrl + Alt + P" and hotkeys.shown("") == "—"
    assert hotkeys.parse("Hyper-x") is None and hotkeys.parse("Control-") is None
    assert hotkeys.tk_sequence("Control-Shift-1") == "<Control-Shift-Key-1>"
    assert hotkeys.needs_quiet_typing("space") and hotkeys.needs_quiet_typing("Shift-Right")
    assert not hotkeys.needs_quiet_typing("Control-m")


def test_global_keys_need_a_modifier():
    assert hotkeys.win32("Control-Alt-p") == (0x2 | 0x1, ord("P"))
    assert hotkeys.win32("Shift-F5") == (0x4, 0x74)
    assert hotkeys.win32("Control-Right") == (0x2, 0x27)
    assert hotkeys.win32("p") is None and hotkeys.win32("") is None


def test_a_pressed_key_becomes_a_sequence():
    def ev(keysym, state=0):
        return SimpleNamespace(keysym=keysym, state=state)
    assert hotkeys.from_event(ev("Control_L", 0x4)) == ""
    assert hotkeys.from_event(ev("P", 0x4 | 0x20000)) == "Control-Alt-p"
    assert hotkeys.from_event(ev("Right", 0x1)) == "Shift-Right"
    assert hotkeys.from_event(ev("plus", 0x1)) == "Shift-plus"
    assert hotkeys.from_event(ev("+", 0x1)) == "+"                         # the character says it all


def test_saved_keys_are_cleaned():
    keys = hotkeys.clean({"toggle": "Control-p", "next": "Hyper-x", "nope": "a", "stop": 5}, hotkeys.DEFAULT_KEYS)
    assert keys["toggle"] == "Control-p" and keys["next"] == hotkeys.DEFAULT_KEYS["next"] and "nope" not in keys
    assert hotkeys.conflicts(keys, "next", "Control-p") == "toggle"


@pytest.fixture
def music(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    return app.music


@pytest.mark.gui
def test_the_shortcuts_act_and_can_be_changed(music, monkeypatch):
    done = []
    monkeypatch.setattr(music, "key_actions", lambda: {n: (lambda n=n: done.append(n)) for n, _ in hotkeys.ACTIONS})
    music.apply_keys()
    assert music.bind("<Control-Key-l>") and music.tree.bind("<Control-Key-l>")      # lyrics' default key
    music._on_shortcut(SimpleNamespace(widget=music.tree), "lyrics", False)
    assert done == ["lyrics"]
    win = music.open_keys()
    win.listen("lyrics", "window")
    assert win.buttons[("lyrics", "window")].cget("text") == "Bir tuşa bas…"
    win.press("Control-r")                                   # was shuffle's: shuffle loses it
    assert win.keys["lyrics"] == "Control-r" and win.keys["shuffle"] == "" and "tuşsuz kaldı" in win.status.cget("text")
    assert music.store.state["keys"]["lyrics"] == "Control-r"
    assert not music.bind("<Control-Key-l>") and music.bind("<Control-Key-r>")       # the old key is let go
    win.listen("toggle", "global")
    win.press("p")                                           # everywhere: only with a modifier
    assert win.global_keys["toggle"] == "" and "Ctrl, Alt ya da Shift" in win.status.cget("text")
    win.listen("toggle", "global")
    win.press("Control-Alt-p")
    assert music.keys.extra == {"toggle": (0x3, ord("P"))}
    win.listen("next", "window")
    win.press("Delete")
    assert win.keys["next"] == "" and music.store.state["keys"]["next"] == ""
    win.reset()
    assert music.shortcut_keys()[0] == hotkeys.DEFAULT_KEYS and music.keys.extra == {}
    win.destroy()


@pytest.mark.gui
def test_typing_in_a_box_is_not_a_shortcut(music, monkeypatch):
    done = []
    monkeypatch.setattr(music, "key_actions", lambda: {n: (lambda n=n: done.append(n)) for n, _ in hotkeys.ACTIONS})
    entry = SimpleNamespace(widget=music.search_entry._entry)
    assert music._on_shortcut(entry, "toggle", True) is None and done == []     # space typed into the search box
    assert music._on_shortcut(entry, "lyrics", False) == "break" and done == ["lyrics"]
