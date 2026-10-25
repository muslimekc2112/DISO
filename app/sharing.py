"""🔗 A playlist sent to a friend. The songs of a list (their titles, artists and YouTube links) are kept in the
database (table shared_lists) under a short code (e.g. "K7P2-QM4X"); whoever has the code (or the link
"diso:liste?K7P2-QM4X") opens it in their DISO: the list is made there and its songs are downloaded as MP3.
Sending needs an account (the shared list belongs to it, and goes with it when the account is deleted); opening
does not.

The code is 8 letters and digits that cannot be mistaken for one another (no 0/O, 1/I): about a trillion of them,
and the database gives out one list for one exact code only (get_shared), so they cannot be listed or guessed
one by one."""
import random
import re
import time

from . import account

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LENGTH = 8
LINK = "diso:liste?"
MAX_SONGS = 500
_CODE = re.compile(r"([A-Za-z2-9]{4})-?([A-Za-z2-9]{4})")


def new_code(rng=random.SystemRandom()) -> str:
    return "".join(rng.choice(ALPHABET) for _ in range(LENGTH))


def pretty(code) -> str:
    return f"{code[:4]}-{code[4:]}"


def link(code) -> str:
    return LINK + pretty(code)


def is_link(text) -> bool:
    return isinstance(text, str) and text.strip().strip('"').lower().startswith(LINK)


def clean_code(text):
    """The code in what was typed or clicked ("k7p2 qm4x", "K7P2-QM4X", "diso:liste?K7P2-QM4X"), or None."""
    text = (text or "").strip().strip('"')
    if text.lower().startswith(LINK):
        text = text[len(LINK):]
    m = _CODE.fullmatch(text.replace(" ", "").upper().rstrip("/"))
    if not m:
        return None
    code = m.group(1) + m.group(2)
    return code if all(c in ALPHABET for c in code) else None


def share(name, songs, tries=4) -> str:
    """Keep the list ([{"title", "artist", "url"}]) in the account under a new code; returns the code."""
    session = account._session_or_fail()
    songs = [{"title": s.get("title", ""), "artist": s.get("artist", ""), "url": s["url"]}
             for s in songs if s.get("url")][:MAX_SONGS]
    if not songs:
        raise account.AccountError("Bu listedeki şarkıların hiçbirini internette bulamadım.", "NO_SONGS")
    row = {"name": name, "by_name": account.display_name(session), "songs": songs, "owner": session["uid"]}
    for attempt in range(tries):
        code = new_code()
        try:
            account.rest("POST", "shared_lists", session, json={**row, "code": code}, prefer="return=minimal")
            return code
        except account.AccountError as e:
            if e.code != "ALREADY_EXISTS" or attempt == tries - 1:     # (a code taken already: another one)
                raise
    raise account.AccountError("Paylaşamadım.", "")


def fetch(code) -> dict:
    """The shared list behind a code: {"name", "by", "made", "songs": [{"title", "artist", "url"}]}."""
    rows = account.rest("POST", "rpc/get_shared", anon=True, json={"list_code": code})
    if not rows:
        raise account.AccountError("Bu kodla paylaşılmış bir liste yok. Kodu kontrol et.", "NOT_FOUND")
    r = rows[0]
    songs = [s for s in (r.get("songs") or []) if isinstance(s, dict) and isinstance(s.get("url"), str)
             and s["url"].startswith("http")]
    return {"name": r.get("name") or "Paylaşılan liste", "by": r.get("by_name", ""),
            "made": account.from_iso(r.get("made")) or time.time(), "songs": songs}
