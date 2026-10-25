"""🔗 A playlist sent to a friend. The songs of a list (their titles, artists and YouTube links) are kept in the account
under a short code (shared/<code>, e.g. "K7P2-QM4X"); whoever has the code (or the link "diso:liste?K7P2-QM4X")
opens it in their DISO: the list is made there and its songs are downloaded as MP3. Sending needs an account (the
shared list belongs to it); opening does not.

The code is 8 letters and digits that cannot be mistaken for one another (no 0/O, 1/I): about a trillion of them,
so they cannot be guessed one by one."""
import json
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


def _url(code="") -> str:
    return f"{account.STORE_URL}/shared" + (f"/{code}" if code else "")


def share(name, songs, tries=4) -> str:
    """Keep the list ([{"title", "artist", "url"}]) in the account under a new code; returns the code."""
    session = account._session_or_fail()
    songs = [{"title": s.get("title", ""), "artist": s.get("artist", ""), "url": s["url"]}
             for s in songs if s.get("url")][:MAX_SONGS]
    if not songs:
        raise account.AccountError("Bu listedeki şarkıların hiçbirini internette bulamadım.", "NO_SONGS")
    fields = {"name": {"stringValue": name}, "owner": {"stringValue": session["uid"]},
              "by": {"stringValue": account.display_name(session)}, "made": {"doubleValue": time.time()},
              "count": {"integerValue": str(len(songs))},
              "songs": {"stringValue": json.dumps(songs, ensure_ascii=False)}}
    for attempt in range(tries):
        code = new_code()
        try:
            account._call("POST", _url(), params={"documentId": code}, headers=account._headers(session),
                          json={"fields": fields})
            try:                                     # (kept with the account: deleting it deletes these too)
                account._call("PATCH", f"{account.STORE_URL}/users/{session['uid']}/shares/{code}",
                              headers=account._headers(session), json={"fields": {"name": {"stringValue": name}}})
            except account.AccountError as e:
                account.log.info("shared list not noted: %s", e)
            return code
        except account.AccountError as e:
            if e.code != "ALREADY_EXISTS" or attempt == tries - 1:     # (a code taken already: another one)
                raise
    raise account.AccountError("Paylaşamadım.", "")


def fetch(code) -> dict:
    """The shared list behind a code: {"name", "by", "made", "songs": [{"title", "artist", "url"}]}."""
    try:
        doc = account._call("GET", _url(code))
    except account.AccountError as e:
        if e.code == "NOT_FOUND":
            raise account.AccountError("Bu kodla paylaşılmış bir liste yok. Kodu kontrol et.", "NOT_FOUND") from e
        raise
    f = doc.get("fields", {})
    try:
        songs = json.loads(f.get("songs", {}).get("stringValue", "[]"))
    except ValueError:
        songs = []
    songs = [s for s in songs if isinstance(s, dict) and isinstance(s.get("url"), str) and s["url"].startswith("http")]
    return {"name": f.get("name", {}).get("stringValue", "") or "Paylaşılan liste",
            "by": f.get("by", {}).get("stringValue", ""), "made": float(f.get("made", {}).get("doubleValue", 0)),
            "songs": songs}
