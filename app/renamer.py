"""✏ Many songs' file names at once, from a pattern: "{sanatçı} - {şarkı}", "{no}. {şarkı}" … The lyrics
beside a song (.lrc) move with it; the lists follow the new names (PlaylistStore.rename_paths). Nothing here
touches the window: plan() says what would happen, apply() does it and gives back what undo() needs."""
import os
import re
import unicodedata

from .player import artist_and_title
from .utils import sanitize_filename

# the names a pattern may use, in Turkish and in English
FIELDS = {"sanatçı": "artist", "artist": "artist", "şarkı": "title", "title": "title", "albüm": "album",
          "album": "album", "no": "no"}
PRESETS = ["{sanatçı} - {şarkı}", "{şarkı}", "{no}. {sanatçı} - {şarkı}", "{no}. {şarkı}", "{sanatçı} - {albüm} - {şarkı}"]
_FIELD = re.compile(r"\{([^{}]+)\}")
SIDE_FILES = (".lrc",)                         # files beside a song that belong to it

OK, SAME, CLASH, EMPTY = "ok", "same", "clash", "empty"


def ascii_text(text: str) -> str:
    """'Şımarık Çiçek' -> 'Simarik Cicek' (for players and cars that cannot show Turkish letters)."""
    text = text.translate(str.maketrans("ıİşŞğĞçÇöÖüÜ", "iIsSgGcCoOuU"))
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def title_case(text: str) -> str:
    """'barış manço - GÜLPEMBE' -> 'Barış Manço - Gülpembe' (Turkish i / ı kept right)."""
    def word(w):
        if not w:
            return w
        first, rest = w[0], w[1:]
        first = "İ" if first == "i" else first.upper()
        rest = rest.replace("I", "ı").replace("İ", "i").lower()
        return first + rest
    return " ".join(word(w) for w in text.split(" "))


def make_name(pattern: str, track: dict, number: int, width: int = 2, plain=False, capitals=False) -> str:
    """The new file name (without the extension) of a track; "" when the pattern gives nothing."""
    artist, title = artist_and_title(track)
    values = {"artist": artist, "title": title, "album": track.get("album") or "", "no": str(number).zfill(width)}

    def fill(m):
        return values.get(FIELDS.get(m.group(1).strip().casefold(), ""), m.group(0))
    name = _FIELD.sub(fill, pattern)
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"^[\s\-–—.]+|[\s\-–—]+$", "", name)                  # "- Şarkı" when there is no artist
    name = re.sub(r"\s*-\s*-\s*", " - ", name)
    name = re.sub(r"\.\s*-\s*", ". ", name)                             # "04. - Şarkı" when there is no artist
    if capitals:
        name = title_case(name)
    if plain:
        name = ascii_text(name)
    return sanitize_filename(name) if name.strip() else ""


def plan(tracks, pattern, plain=False, capitals=False):
    """[(track, new path, state)] for these tracks: OK, SAME (already so named), CLASH (another file has that
    name, or two of them would) or EMPTY (the pattern gives no name)."""
    width = max(2, len(str(len(tracks))))
    out, taken = [], {}
    for n, t in enumerate(tracks, start=1):
        old = t["path"]
        stem = make_name(pattern, t, n, width, plain, capitals)
        if not stem:
            out.append((t, old, EMPTY))
            continue
        new = os.path.join(os.path.dirname(old), stem + os.path.splitext(old)[1])
        key = os.path.normcase(os.path.abspath(new))
        if key == os.path.normcase(os.path.abspath(old)) and os.path.basename(new) == os.path.basename(old):
            state = SAME
        elif key in taken or (os.path.exists(new) and key != os.path.normcase(os.path.abspath(old))):
            state = CLASH
        else:
            state = OK
        taken[key] = True
        out.append((t, new, state))
    return out


def _move(old, new):
    if os.path.normcase(os.path.abspath(old)) == os.path.normcase(os.path.abspath(new)):
        tmp = new + ".diso-rename"                    # only the case changes: Windows needs a step between
        os.rename(old, tmp)
        os.rename(tmp, new)
    else:
        os.rename(old, new)


def apply(steps):
    """Rename the OK ones of plan(): [(old, new)] of what was done, and [(name, why)] of what could not be."""
    done, failed = [], []
    for t, new, state in steps:
        if state != OK:
            continue
        old = t["path"]
        try:
            _move(old, new)
        except OSError as e:
            failed.append((os.path.basename(old), e.strerror or str(e)))
            continue
        done.append((old, new))
        for side in SIDE_FILES:
            a, b = os.path.splitext(old)[0] + side, os.path.splitext(new)[0] + side
            if os.path.isfile(a) and not os.path.exists(b):
                try:
                    _move(a, b)
                except OSError:
                    pass
    return done, failed


def undo(done):
    """Put the names back (the last renamed first). Returns [(new, old)] of what went back."""
    back = []
    for old, new in reversed(done):
        try:
            _move(new, old)
        except OSError:
            continue
        back.append((new, old))
        for side in SIDE_FILES:
            a, b = os.path.splitext(new)[0] + side, os.path.splitext(old)[0] + side
            if os.path.isfile(a) and not os.path.exists(b):
                try:
                    _move(a, b)
                except OSError:
                    pass
    return back
