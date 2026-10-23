"""⌨ Keyboard shortcuts of the music player that the user sets: one key for each action inside DISO's
window, and (if wanted) one that works everywhere, also when another program is in front.

Keys are kept as Tk sequences without the brackets ("space", "Control-Right", "Control-Alt-p"); shown as
"Ctrl + →"; the global ones become (modifiers, virtual key) for RegisterHotKey (see mediakeys)."""

ACTIONS = [
    ("toggle", "Çal / duraklat"), ("next", "Sonraki şarkı"), ("previous", "Önceki şarkı"), ("stop", "Durdur"),
    ("seek_forward", "5 saniye ileri (iki kez: sonraki şarkı)"), ("seek_back", "5 saniye geri (iki kez: önceki şarkı)"),
    ("volume_up", "Sesi aç"),
    ("volume_down", "Sesi kıs"), ("mute", "Sesi kapat / aç"), ("shuffle", "Karışık çal"),
    ("repeat", "Tekrar modu"), ("mini", "Mini oynatıcı"), ("lyrics", "Şarkı sözleri"), ("search", "Şarkı ara"),
]
NAMES = dict(ACTIONS)

DEFAULT_KEYS = {"toggle": "space", "next": "Control-Right", "previous": "Control-Left", "stop": "",
                "seek_forward": "Right", "seek_back": "Left", "volume_up": "Shift-Up",
                "volume_down": "Shift-Down", "mute": "Control-m", "shuffle": "Control-r", "repeat": "Control-t",
                "mini": "Control-i", "lyrics": "Control-l", "search": "Control-k"}
DEFAULT_GLOBAL = {name: "" for name, _ in ACTIONS}

MODIFIERS = ("Control", "Alt", "Shift", "Win")
_SHOWN_MODS = {"Control": "Ctrl", "Alt": "Alt", "Shift": "Shift", "Win": "Win"}
_SHOWN_KEYS = {"space": "Boşluk", "Right": "→", "Left": "←", "Up": "↑", "Down": "↓", "Return": "Enter",
               "Prior": "Page Up", "Next": "Page Down", "Escape": "Esc", "plus": "+", "minus": "-",
               "comma": ",", "period": "."}
# Tk keysym -> Windows virtual key (for the keys that work everywhere)
_VK = {"space": 0x20, "Right": 0x27, "Left": 0x25, "Up": 0x26, "Down": 0x28, "Return": 0x0D, "Prior": 0x21,
       "Next": 0x22, "Home": 0x24, "End": 0x23, "Insert": 0x2D, "Delete": 0x2E, "plus": 0xBB, "minus": 0xBD,
       "comma": 0xBC, "period": 0xBE}
_VK_MOD = {"Alt": 0x1, "Control": 0x2, "Shift": 0x4, "Win": 0x8}
_TK_MOD_STATE = {"Shift": 0x1, "Control": 0x4, "Alt": 0x20000}      # event.state bits on Windows
_ALONE = {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Win_L", "Win_R", "Caps_Lock"}


def clean(saved, defaults) -> dict:
    """Every action with a key ("" = none), what was saved where it makes sense."""
    out = dict(defaults)
    for name, seq in (saved.items() if isinstance(saved, dict) else ()):
        if name in out and isinstance(seq, str) and (seq == "" or parse(seq) is not None):
            out[name] = seq
    return out


def parse(seq):
    """("Control", "Alt"), "p" from "Control-Alt-p"; None when it is no key."""
    if not seq:
        return None
    parts = seq.split("-")
    key, mods = parts[-1], tuple(parts[:-1])
    if not key or any(m not in MODIFIERS for m in mods):
        return None
    return mods, key


def shown(seq) -> str:
    """"Ctrl + →" for "Control-Right" ("—" when there is no key)."""
    got = parse(seq)
    if got is None:
        return "—"
    mods, key = got
    key = _SHOWN_KEYS.get(key, key.upper() if len(key) == 1 else key)
    return " + ".join([_SHOWN_MODS[m] for m in mods] + [key])


def from_event(event) -> str:
    """The sequence of a pressed key ("" while only a modifier is down)."""
    if event.keysym in _ALONE:
        return ""
    mods = [m for m in ("Control", "Alt", "Shift") if event.state & _TK_MOD_STATE[m]]
    key = event.keysym
    if len(key) == 1:
        key = key.lower()
        if "Shift" in mods and not key.isalnum():
            mods.remove("Shift")                      # "+" is typed with Shift: the character says it all
    return "-".join(mods + [key])


def needs_quiet_typing(seq) -> bool:
    """A key without Ctrl / Alt (space, a letter, an arrow …) must not act while typing in a box."""
    got = parse(seq)
    return got is not None and not ({"Control", "Alt", "Win"} & set(got[0]))


def tk_sequence(seq) -> str:
    """"<Control-Key-r>" — "Key-" so a digit is a key, not a mouse button."""
    mods, key = parse(seq)
    return "<" + "-".join(list(mods) + ["Key", key]) + ">"


def win32(seq):
    """(modifiers, virtual key) for RegisterHotKey, or None when this key cannot work everywhere."""
    got = parse(seq)
    if got is None:
        return None
    mods, key = got
    if not mods:                                      # a key alone everywhere would take it from every program
        return None
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key in _VK:
        vk = _VK[key]
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    else:
        return None
    flags = 0
    for m in mods:
        flags |= _VK_MOD[m]
    return flags, vk


def conflicts(keys: dict, name, seq):
    """The other action that already has this key (or None)."""
    return next((n for n, s in keys.items() if s and s == seq and n != name), None)
