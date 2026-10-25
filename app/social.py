"""👥 Friends: requests by user name, messages, songs recommended to a friend, a friend's likes, what a friend is
listening to now. Everything goes through Cloud Firestore (no server of our own):

* public/<uid>: what every signed-in user may see of an account: its user name, its name, when it was last seen
  and (if it wants) the song it plays now. The e-mail address is never there.
* users/<uid>/friends/<friend uid>: the friends of an account (only its owner reads or writes them).
* users/<uid>/outgoing/<uid>: the requests it sent that are not answered yet.
* users/<uid>/inbox/<id>: what others send it. The rules let anyone (signed in, e-mail confirmed) leave a
  "request" there, a friend anything, and someone who was asked an "accepted" / "declined"; only the owner reads
  and deletes it. DISO looks into its inbox every POLL_EVERY while it runs, takes what came into social.json
  (which travels with the account like the playlists) and empties it.

Firestore on the free plan cannot push anything: a message arrives at the next look (seconds)."""
import json
import os
import threading
import time
import uuid

from . import account, safefile
from .logs import log
from .utils import app_data_dir

POLL_EVERY = 20 * 1000          # ms: how often DISO looks for what friends sent
SEEN_EVERY = 120                # s: how often "I am here" (last seen) is written
ONLINE_FOR = 180                # s: seen this recently = online
MAX_TEXT = 1000                 # characters of one message
MAX_NOTES = 200                 # notifications kept
MAX_CHAT = 500                  # messages kept per friend
KINDS = ("request", "accepted", "declined", "message", "recommend", "like", "feedback", "removed", "gone")
_lock = threading.RLock()
_seen_at = 0.0                  # when "I am here" was last written


class SocialError(account.AccountError):
    pass


def _url(path) -> str:
    return f"{account.STORE_URL}/{path}"


def _session():
    return account._session_or_fail()


def _fields(values) -> dict:
    out = {}
    for k, v in values.items():
        if isinstance(v, bool):
            out[k] = {"booleanValue": v}
        elif isinstance(v, int):
            out[k] = {"integerValue": str(v)}
        elif isinstance(v, float):
            out[k] = {"doubleValue": v}
        else:
            out[k] = {"stringValue": "" if v is None else str(v)}
    return out


def _values(fields) -> dict:
    out = {}
    for k, v in (fields or {}).items():
        if "integerValue" in v:
            out[k] = int(v["integerValue"])
        elif "doubleValue" in v:
            out[k] = float(v["doubleValue"])
        elif "booleanValue" in v:
            out[k] = bool(v["booleanValue"])
        else:
            out[k] = v.get("stringValue", "")
    return out


def _get(session, path, **params):
    return account._call("GET", _url(path), headers=account._headers(session), params=params or None)


def _patch(session, path, values, mask=None):
    params = [("updateMask.fieldPaths", k) for k in values] if mask else None
    return account._call("PATCH", _url(path), headers=account._headers(session), params=params,
                         json={"fields": _fields(values)})


def _delete(session, path):
    try:
        account._call("DELETE", _url(path), headers=account._headers(session))
    except account.AccountError as e:
        if e.code != "NOT_FOUND":
            raise


def _list(session, path) -> list:
    """[(document id, values)] of a collection."""
    data = _get(session, path, pageSize=300)
    return [(d.get("name", "").rsplit("/", 1)[-1], _values(d.get("fields"))) for d in data.get("documents", [])]


def me(session=None) -> dict:
    session = session or _session()
    p = session.get("profile") or {}
    return {"uid": session["uid"], "username": p.get("username", ""), "name": account.display_name(session)}


# ------------------------------------------------------------------------------ what is kept here
def path() -> str:
    return os.path.join(app_data_dir(), "social.json")


def load() -> dict:
    try:
        data = safefile.read_json(path())
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    for key, empty in (("friends", {}), ("requests", {}), ("outgoing", {}), ("chats", {}), ("notes", []),
                       ("unread", {})):
        if not isinstance(data.get(key), type(empty)):
            data[key] = empty
    return data


def save(data):
    with _lock:
        safefile.write_json(path(), data, indent=1)


def unread_count(data=None) -> int:
    """Notifications and messages not looked at yet (the number on the account button)."""
    data = data or load()
    return sum(1 for n in data["notes"] if not n.get("seen")) + sum(data["unread"].values()) + len(data["requests"])


def mark_seen(friend=None):
    """The notifications (or a friend's messages) were looked at."""
    with _lock:
        data = load()
        if friend:
            data["unread"].pop(friend, None)
        else:
            for n in data["notes"]:
                n["seen"] = True
        save(data)


def _note(data, kind, who, text, song=None, value=0):
    data["notes"].insert(0, {"id": uuid.uuid4().hex[:12], "kind": kind, "from": who.get("uid", ""),
                             "name": who.get("name", ""), "username": who.get("username", ""), "text": text,
                             "song": song or None, "value": value, "at": time.time(), "seen": False})
    del data["notes"][MAX_NOTES:]


def _chat(data, uid, mine, text, at=None):
    chat = data["chats"].setdefault(uid, [])
    chat.append({"me": mine, "text": text, "at": at or time.time()})
    del chat[:-MAX_CHAT]


# ------------------------------------------------------------------------------ my public card
def publish_me(session=None, now_playing=None, seen=True):
    """public/<uid>: user name, name, last seen, (the song playing now: "" = nothing / not shown)."""
    session = session or _session()
    who = me(session)
    values = {"username": who["username"], "name": who["name"]}
    if seen:
        values["seen"] = time.time()
    if now_playing is not None:
        values["now"] = now_playing
        values["now_at"] = time.time()
    _patch(session, f"public/{session['uid']}", values, mask=True)


def card(uid, session=None) -> dict:
    """Someone's public card ({} when there is none: the account is gone)."""
    session = session or _session()
    try:
        return _values(_get(session, f"public/{uid}").get("fields"))
    except account.AccountError as e:
        if e.code == "NOT_FOUND":
            return {}
        raise


def online(c) -> bool:
    return bool(c.get("seen")) and time.time() - float(c["seen"]) < ONLINE_FOR


# ------------------------------------------------------------------------------ friends
def find(username, session=None) -> str:
    """The uid behind a user name (SocialError when there is no such user)."""
    session = session or _session()
    name = (username or "").strip().lstrip("@").lower()
    try:
        doc = _get(session, f"usernames/{name}")
    except account.AccountError as e:
        if e.code == "NOT_FOUND":
            raise SocialError(f"“{name}” adında bir kullanıcı yok.", "NO_USER") from e
        raise
    return _values(doc.get("fields")).get("uid", "")


def _send(session, to, kind, **values):
    who = me(session)
    doc = {"from": session["uid"], "from_username": who["username"], "from_name": who["name"], "type": kind,
           "at": time.time(), **values}
    account._call("POST", _url(f"users/{to}/inbox"), headers=account._headers(session),
                  json={"fields": _fields(doc)})


def request(username):
    """Ask someone to be friends (by their user name)."""
    session = _session()
    username = (username or "").strip().lstrip("@").lower()
    uid = find(username, session)
    who = me(session)
    if uid == session["uid"]:
        raise SocialError("Kendine istek gönderemezsin 🙂", "SELF")
    data = load()
    if uid in data["friends"]:
        raise SocialError("Zaten arkadaşsınız.", "ALREADY")
    if uid in data["requests"]:                       # they asked first: this is a yes
        return accept(uid)
    c = card(uid, session)
    _patch(session, f"users/{session['uid']}/outgoing/{uid}", {"username": c.get("username", username),
                                                               "name": c.get("name", ""), "at": time.time()})
    _send(session, uid, "request")
    with _lock:
        data = load()
        data["outgoing"][uid] = {"username": c.get("username", username), "name": c.get("name", ""),
                                 "at": time.time()}
        save(data)
    log.info("friend request sent to %s (from %s)", uid, who["username"])
    return uid


def _add_friend(session, data, uid, info):
    _patch(session, f"users/{session['uid']}/friends/{uid}",
           {"username": info.get("username", ""), "name": info.get("name", ""), "since": time.time()})
    data["friends"][uid] = {"username": info.get("username", ""), "name": info.get("name", ""), "since": time.time()}
    data["requests"].pop(uid, None)
    if data["outgoing"].pop(uid, None) is not None:
        _delete(session, f"users/{session['uid']}/outgoing/{uid}")


def _befriend(session, uid, info):
    with _lock:
        data = load()
        _add_friend(session, data, uid, info)
        save(data)


def accept(uid):
    session = _session()
    info = load()["requests"].get(uid) or card(uid, session)
    _befriend(session, uid, info)
    _send(session, uid, "accepted")
    return uid


def decline(uid):
    session = _session()
    with _lock:
        data = load()
        data["requests"].pop(uid, None)
        save(data)
    try:
        _send(session, uid, "declined")
    except account.AccountError as e:
        log.info("could not say no to %s: %s", uid, e)


def cancel(uid):
    """Take back a request that was not answered."""
    session = _session()
    _delete(session, f"users/{session['uid']}/outgoing/{uid}")
    with _lock:
        data = load()
        data["outgoing"].pop(uid, None)
        save(data)


def unfriend(uid, kind="removed"):
    session = _session()
    try:
        _send(session, uid, kind)                    # (while they still have me: their list follows)
    except account.AccountError as e:
        log.info("could not tell %s: %s", uid, e)
    _delete(session, f"users/{session['uid']}/friends/{uid}")
    with _lock:
        data = load()
        data["friends"].pop(uid, None)
        data["chats"].pop(uid, None)
        data["unread"].pop(uid, None)
        save(data)


def friends(refresh=False) -> dict:
    """{uid: {"username", "name", (refresh: "seen", "now", "online")}}."""
    data = load()
    if not refresh:
        return data["friends"]
    session = _session()
    found = {uid: {"username": v.get("username", ""), "name": v.get("name", "")}
             for uid, v in _list(session, f"users/{session['uid']}/friends")}
    for uid, f in found.items():
        c = card(uid, session)
        if c:
            f.update(username=c.get("username", f["username"]), name=c.get("name", f["name"]),
                     seen=c.get("seen", 0), now=c.get("now", ""), online=online(c))
        else:
            f.update(gone=True)
    with _lock:
        data = load()
        data["friends"] = {uid: {k: f[k] for k in ("username", "name")} for uid, f in found.items()}
        save(data)
    return found


# ------------------------------------------------------------------------------ talking
def message(uid, text):
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        return
    _send(_session(), uid, "message", text=text)
    with _lock:
        data = load()
        _chat(data, uid, True, text)
        save(data)


def recommend(uid, song, text=""):
    """A song to a friend: {"title", "artist", "url"}."""
    _send(_session(), uid, "recommend", song=json.dumps(song, ensure_ascii=False), text=(text or "")[:MAX_TEXT])


def tell_like(song, value):
    """👍 / 👎 told to every friend (they see "X liked this song")."""
    session = _session()
    for uid in list(load()["friends"]):
        try:
            _send(session, uid, "like", song=json.dumps(song, ensure_ascii=False), value=int(value))
        except account.AccountError as e:
            log.info("like not told to %s: %s", uid, e)


def feedback(note_id, value):
    """The answer to a recommended song: 👍 / 👎 goes back to whoever sent it."""
    data = load()
    note = next((n for n in data["notes"] if n["id"] == note_id), None)
    if note is None or not note.get("from"):
        return
    _send(_session(), note["from"], "feedback", song=json.dumps(note.get("song") or {}, ensure_ascii=False),
          value=int(value))
    with _lock:
        data = load()
        for n in data["notes"]:
            if n["id"] == note_id:
                n["answered"] = int(value)
        save(data)


# ------------------------------------------------------------------------------ what came in
def poll() -> list:
    """Take what others sent (and empty the inbox); returns the new notifications ([{kind, name, text, ...}])."""
    global _seen_at
    session = account.load()
    if session is None or not session.get("verified"):
        return []
    if time.time() - _seen_at > SEEN_EVERY:            # "I am here" for the friends' lists
        try:
            publish_me(session)
            _seen_at = time.time()
        except account.AccountError as e:
            log.info("not marked as here: %s", e)
    items = _list(session, f"users/{session['uid']}/inbox")
    fresh = []
    with _lock:
        data = load()
        for doc_id, v in sorted(items, key=lambda i: i[1].get("at", 0)):
            try:
                fresh += _take(session, data, v)
            except Exception:  # noqa: BLE001 - one odd item never stops the others
                log.exception("inbox item")
            try:
                _delete(session, f"users/{session['uid']}/inbox/{doc_id}")
            except account.AccountError as e:
                log.info("inbox item stays: %s", e)
        save(data)
    return fresh


def _take(session, data, v) -> list:
    kind, uid = v.get("type"), v.get("from", "")
    who = {"uid": uid, "name": v.get("from_name", ""), "username": v.get("from_username", "")}
    name = who["name"] or who["username"] or "?"
    try:
        song = json.loads(v.get("song") or "null")
    except ValueError:
        song = None
    if kind == "request":
        if uid in data["friends"]:
            return []
        if uid in data["outgoing"]:                 # both asked: that is a yes from both
            _add_friend(session, data, uid, who)
            _send(session, uid, "accepted")
            _note(data, "accepted", who, f"{name} ile artık arkadaşsınız 🎉")
            return [{"kind": "accepted", "name": name, "text": data["notes"][0]["text"]}]
        data["requests"][uid] = {"username": who["username"], "name": who["name"], "at": v.get("at", time.time())}
        return [{"kind": kind, "name": name, "text": f"{name} sana arkadaşlık isteği gönderdi"}]
    if kind == "accepted" and uid in data["outgoing"]:
        _add_friend(session, data, uid, who)
        _note(data, kind, who, f"{name} arkadaşlık isteğini kabul etti 🎉")
        return [{"kind": kind, "name": name, "text": data["notes"][0]["text"]}]
    if kind == "declined":
        data["outgoing"].pop(uid, None)
        try:
            _delete(session, f"users/{session['uid']}/outgoing/{uid}")
        except account.AccountError:
            pass
        return []
    if uid not in data["friends"]:                 # (not a friend any more: nothing of theirs comes in)
        return []
    if kind == "message":
        text = (v.get("text") or "")[:MAX_TEXT]
        _chat(data, uid, False, text, v.get("at"))
        data["unread"][uid] = data["unread"].get(uid, 0) + 1
        return [{"kind": kind, "name": name, "uid": uid, "text": f"💬 {name}: {text}"}]
    if kind == "recommend" and song:
        _note(data, kind, who, f"🎵 {name} sana bir şarkı öneriyor: {song_name(song)}", song)
        return [{"kind": kind, "name": name, "text": data["notes"][0]["text"]}]
    if kind == "like" and song:
        value = int(v.get("value", 0))
        text = (f"👍 {name} bu şarkıyı beğendi: {song_name(song)}" if value > 0
                else f"👎 {name} bu şarkıyı beğenmedi: {song_name(song)}")
        _note(data, kind, who, text, song, value)
        return [{"kind": kind, "name": name, "text": text}]
    if kind == "feedback" and song:
        value = int(v.get("value", 0))
        text = (f"👍 {name} önerdiğin şarkıyı beğendi: {song_name(song)}" if value > 0
                else f"👎 {name} önerdiğin şarkıyı beğenmedi: {song_name(song)}")
        _note(data, kind, who, text, song, value)
        return [{"kind": kind, "name": name, "text": text}]
    if kind in ("removed", "gone"):
        data["friends"].pop(uid, None)
        data["chats"].pop(uid, None)
        data["unread"].pop(uid, None)
        try:
            _delete(session, f"users/{session['uid']}/friends/{uid}")
        except account.AccountError:
            pass
        if kind == "gone":
            _note(data, kind, who, f"{name} DISO hesabını sildi")
            return [{"kind": kind, "name": name, "text": data["notes"][0]["text"]}]
    return []


def song_name(song) -> str:
    title, artist = (song or {}).get("title", ""), (song or {}).get("artist", "")
    return f"{artist} - {title}" if artist and title else title or artist or "?"


# ------------------------------------------------------------------------------ the account goes
def forget_everything(session):
    """Before the account is deleted: friends are told, every trace of it in Firestore goes."""
    uid = session["uid"]
    for fid, _v in _list(session, f"users/{uid}/friends"):
        try:
            _send(session, fid, "gone")
        except account.AccountError as e:
            log.info("could not tell %s: %s", fid, e)
    for sub in ("friends", "outgoing", "inbox", "files", "devices", "shares"):
        for doc_id, _v in _list(session, f"users/{uid}/{sub}"):
            if sub == "shares":
                _delete(session, f"shared/{doc_id}")
            _delete(session, f"users/{uid}/{sub}/{doc_id}")
    _delete(session, f"users/{uid}/info/profile")
    _delete(session, f"public/{uid}")
    name = (session.get("profile") or {}).get("username")
    if name:
        _delete(session, f"usernames/{name}")
    try:
        os.remove(path())
    except OSError:
        pass
