"""👥 Friends, chats and groups. Everything lives in the Supabase database (supabase/schema.sql; its row level
security says who sees what), nothing on a server of our own:

* profiles: what every signed-in user may see of an account: its user name, its name, when it was last seen,
  the song it plays now (if it wants) and a status. The e-mail address is never there.
* friend_requests / friendships: asking by user name, saying yes (accept_request makes both sides at once).
* conversations / members / messages / reactions: a chat of two (made by direct_chat) and groups (made by
  create_group, run by their admins) are the same thing: a conversation with members and messages.
  A message is text, a song, a whole playlist, a picture or a file (stored in the "files" bucket).
* notifications: a friend liked / answered a song, a friend deleted the account.

DISO looks for what is new (poll) when the live connection says so (Live, Supabase Realtime) and now and then
anyway; what it finds is kept as notifications and shown (a toast, the number on the account button). The chats
themselves are read from the server when a chat is opened.

What is kept on this computer (social.json): the notifications, the last message already looked at, a copy of the
friends and requests (to see what changed) and the chats' numbers of unread messages."""
import json
import os
import threading
import time
import uuid

from . import account, safefile
from .logs import log
from .utils import app_data_dir

POLL_EVERY = 30 * 1000          # ms: how often DISO looks for what is new while the live connection is not there
LIVE_POLL_EVERY = 120 * 1000    # ms: ... and while it is there (a safety net)
CHAT_POLL_EVERY = 4 * 1000      # ms: ... while a chat is open and the live connection is not there
SEEN_EVERY = 120                # s: how often "I am here" (last seen) is written
ONLINE_FOR = 180                # s: seen this recently = online
MAX_TEXT = 4000                 # characters of one message
MAX_NOTES = 200                 # notifications kept
PAGE = 60                       # messages read at a time
MAX_GROUP = 50
MAX_FILE = 50 * 1024 * 1024     # bytes: the bucket's limit
_lock = threading.RLock()
_seen_at = 0.0                  # when "I am here" was last written
NOTE_LIMIT = 12                 # events handled in one poll (a long absence does not flood the screen)


class SocialError(account.AccountError):
    pass


def _session():
    return account._session_or_fail()


def _in(uids) -> str:
    return "in.(" + ",".join(sorted(uids)) + ")"


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
    for key, empty in (("friends", {}), ("requests", {}), ("outgoing", {}), ("notes", []), ("unread", {}),
                       ("direct", {}), ("muted", []), ("groups", [])):
        if not isinstance(data.get(key), type(empty)):
            data[key] = empty
    if not isinstance(data.get("last_msg"), int):
        data["last_msg"] = 0
    return data


def save(data):
    with _lock:
        safefile.write_json(path(), data, indent=1)


def unread_count(data=None) -> int:
    """Notifications and messages not looked at yet (the number on the account button)."""
    data = data or load()
    muted = set(data["muted"])
    return (sum(1 for n in data["notes"] if not n.get("seen")) + sum(v for k, v in data["unread"].items()
                                                                       if k not in muted) + len(data["requests"]))


def mark_seen():
    """The notifications were looked at."""
    with _lock:
        data = load()
        for n in data["notes"]:
            n["seen"] = True
        save(data)


def _note(data, kind, who, text, song=None, value=0, msg=None, conv=None):
    note = {"id": uuid.uuid4().hex[:12], "kind": kind, "from": who.get("uid", ""), "name": who.get("name", ""),
            "username": who.get("username", ""), "text": text, "song": song or None, "value": value,
            "msg": msg, "conv": conv, "at": time.time(), "seen": False}
    data["notes"].insert(0, note)
    del data["notes"][MAX_NOTES:]
    return note


# ------------------------------------------------------------------------------ profiles
def _name(p) -> str:
    return (" ".join(x for x in (p.get("first_name", ""), p.get("last_name", "")) if x).strip()
            or p.get("username", "") or "?")


def _card(r) -> dict:
    return {"uid": r["id"], "username": r.get("username", ""), "name": _name(r), "seen": account.from_iso(r.get("seen")),
            "now": r.get("now_playing", ""), "status": r.get("status", "online"), "photo": r.get("photo")}


PROFILE_COLUMNS = "id,username,first_name,last_name,seen,now_playing,status,photo"


def profiles(uids, session=None) -> dict:
    """{uid: card} for these accounts."""
    uids = [u for u in set(uids) if u]
    if not uids:
        return {}
    session = session or _session()
    rows = account.rest("GET", "profiles", session, params={"id": _in(uids), "select": PROFILE_COLUMNS})
    return {r["id"]: _card(r) for r in rows}


def card(uid, session=None) -> dict:
    """Someone's public card ({} when there is none: the account is gone)."""
    return profiles([uid], session).get(uid, {})


def online(c) -> bool:
    return (bool(c.get("seen")) and time.time() - float(c["seen"]) < ONLINE_FOR
            and c.get("status", "online") != "invisible")


def publish_me(session=None, now_playing=None, seen=True, status=None):
    """My card: when I was last seen, the song playing now ("" = nothing / not shown), my status."""
    session = session or _session()
    values = {}
    if seen:
        values["seen"] = account.iso()
    if now_playing is not None:
        values["now_playing"] = now_playing
    if status is not None:
        values["status"] = status
    if values:
        account.rest("PATCH", "profiles", session, params={"id": "eq." + session["uid"]}, json=values)


# ------------------------------------------------------------------------------ friends
def find(username, session=None) -> str:
    """The uid behind a user name (SocialError when there is no such user)."""
    session = session or _session()
    name = (username or "").strip().lstrip("@").lower()
    rows = account.rest("GET", "profiles", session, params={"username": "eq." + name, "select": "id"})
    if not rows:
        raise SocialError(f"“{name}” adında bir kullanıcı yok.", "NO_USER")
    return rows[0]["id"]


def request(username):
    """Ask someone to be friends (by their user name)."""
    session = _session()
    username = (username or "").strip().lstrip("@").lower()
    uid = find(username, session)
    if uid == session["uid"]:
        raise SocialError("Kendine istek gönderemezsin 🙂", "SELF")
    data = load()
    if account.rest("GET", "friendships", session, params={"user_id": "eq." + session["uid"],
                                                          "friend_id": "eq." + uid, "select": "friend_id"}):
        raise SocialError("Zaten arkadaşsınız.", "ALREADY")           # (asked of the server: the copy here may be old)
    asked_me = account.rest("GET", "friend_requests", session, params={"from_id": "eq." + uid,
                                                                      "to_id": "eq." + session["uid"],
                                                                      "select": "from_id"})
    if uid in data["requests"] or asked_me:           # they asked first: this is a yes
        return accept(uid)
    try:
        account.rest("POST", "friend_requests", session, json={"to_id": uid, "from_id": session["uid"]},
                     prefer="return=minimal")
    except account.AccountError as e:
        if e.code == "ALREADY_EXISTS":
            raise SocialError("Bu kullanıcıya zaten bir istek gönderdin.", "ALREADY") from e
        if e.code == "PERMISSION_DENIED":
            raise SocialError("Bu kullanıcıya istek gönderemezsin.", "DENIED") from e
        raise
    c = card(uid, session)
    with _lock:
        data = load()
        data["outgoing"][uid] = {"username": c.get("username", username), "name": c.get("name", ""), "at": time.time()}
        save(data)
    return uid


def accept(uid):
    session = _session()
    account.rest("POST", "rpc/accept_request", session, json={"from_user": uid})
    c = card(uid, session)
    with _lock:
        data = load()
        data["friends"][uid] = {"username": c.get("username", ""), "name": c.get("name", "")}
        data["requests"].pop(uid, None)
        data["outgoing"].pop(uid, None)
        save(data)
    return uid


def decline(uid):
    session = _session()
    account.rest("DELETE", "friend_requests", session, params={"from_id": "eq." + uid, "to_id": "eq." + session["uid"]})
    with _lock:
        data = load()
        data["requests"].pop(uid, None)
        save(data)


def cancel(uid):
    """Take back a request that was not answered."""
    session = _session()
    account.rest("DELETE", "friend_requests", session, params={"from_id": "eq." + session["uid"], "to_id": "eq." + uid})
    with _lock:
        data = load()
        data["outgoing"].pop(uid, None)
        save(data)


def unfriend(uid):
    session = _session()
    account.rest("POST", "rpc/unfriend", session, json={"other": uid})
    with _lock:
        data = load()
        data["friends"].pop(uid, None)
        data["direct"].pop(uid, None)
        save(data)


def block(uid):
    session = _session()
    account.rest("POST", "rpc/block_user", session, json={"other": uid})
    with _lock:
        data = load()
        for k in ("friends", "requests", "outgoing", "direct"):
            data[k].pop(uid, None)
        save(data)


def unblock(uid):
    account.rest("POST", "rpc/unblock_user", _session(), json={"other": uid})


def blocked() -> dict:
    """{uid: card} of the people I blocked."""
    session = _session()
    rows = account.rest("GET", "blocks", session, params={"user_id": "eq." + session["uid"], "select": "blocked_id"})
    return profiles([r["blocked_id"] for r in rows], session)


def friends(refresh=False) -> dict:
    """{uid: {"username", "name", (refresh: "seen", "now", "online", "status", "photo")}}."""
    data = load()
    if not refresh:
        return data["friends"]
    session = _session()
    rows = account.rest("GET", "friendships", session, params={"user_id": "eq." + session["uid"],
                                                               "select": "friend_id,since"})
    cards = profiles([r["friend_id"] for r in rows], session)
    found = {}
    for r in rows:
        c = cards.get(r["friend_id"])
        found[r["friend_id"]] = ({"username": c["username"], "name": c["name"], "seen": c["seen"], "now": c["now"],
                                  "online": online(c), "status": c["status"], "photo": c["photo"]} if c
                                 else {"username": "", "name": "?", "gone": True})
    with _lock:
        data = load()
        data["friends"] = {uid: {"username": f["username"], "name": f["name"]} for uid, f in found.items()}
        save(data)
    return found


def requests_in() -> dict:
    """{uid: card} of the people who asked to be my friend."""
    session = _session()
    rows = account.rest("GET", "friend_requests", session, params={"to_id": "eq." + session["uid"],
                                                                  "select": "from_id,at"})
    return profiles([r["from_id"] for r in rows], session)


# ------------------------------------------------------------------------------ conversations
def direct(uid) -> str:
    """The id of my chat with a friend (made the first time)."""
    data = load()
    if uid in data["direct"]:
        return data["direct"][uid]
    conv = account.rest("POST", "rpc/direct_chat", _session(), json={"other": uid})
    with _lock:
        data = load()
        data["direct"][uid] = conv
        save(data)
    return conv


def conversations() -> list:
    """My chats and groups: [{"id", "kind", "name", "emoji", "about", "photo", "only_admins", "role", "muted",
    "peer", "unread"}], the ones with news first."""
    session = _session()
    mine = account.rest("GET", "members", session, params={"user_id": "eq." + session["uid"],
                                                          "select": "conversation_id,role,muted"})
    if not mine:
        return []
    ids = [m["conversation_id"] for m in mine]
    convs = {c["id"]: c for c in account.rest("GET", "conversations", session,
                                              params={"id": _in(ids), "select": "*"})}
    directs = [c for c in convs if convs[c]["kind"] == "direct"]
    peers = {}
    if directs:
        for r in account.rest("GET", "members", session, params={"conversation_id": _in(directs),
                                                                "user_id": "neq." + session["uid"],
                                                                "select": "conversation_id,user_id"}):
            peers[r["conversation_id"]] = r["user_id"]
    cards = profiles(peers.values(), session)
    unread = {r["conversation_id"]: r["n"] for r in account.rest("POST", "rpc/unread_counts", session, json={})}
    out = []
    for m in mine:
        c = convs.get(m["conversation_id"])
        if c is None:
            continue
        peer = peers.get(c["id"])
        who = cards.get(peer, {})
        out.append({"id": c["id"], "kind": c["kind"], "name": c["name"] if c["kind"] == "group" else who.get("name", "?"),
                    "emoji": c.get("emoji", "👥"), "about": c.get("about", ""),
                    "photo": c.get("photo") if c["kind"] == "group" else who.get("photo"),
                    "only_admins": bool(c.get("only_admins")), "role": m["role"], "muted": bool(m["muted"]),
                    "peer": peer, "unread": unread.get(c["id"], 0)})
    with _lock:
        data = load()
        data["groups"] = [{"id": c["id"], "name": c["name"], "emoji": c["emoji"], "only_admins": c["only_admins"],
                           "role": c["role"]} for c in out if c["kind"] == "group"]
        data["unread"] = {c["id"]: c["unread"] for c in out if c["unread"]}
        data["muted"] = [c["id"] for c in out if c["muted"]]
        data["direct"].update({c["peer"]: c["id"] for c in out if c["kind"] == "direct" and c["peer"]})
        save(data)
    return sorted(out, key=lambda c: (-c["unread"], c["name"].lower()))


def _message(r, reactions=None) -> dict:
    return {"id": r["id"], "conv": r["conversation_id"], "sender": r.get("sender_id"), "kind": r["kind"],
            "body": r.get("body", ""), "payload": r.get("payload"), "reply_to": r.get("reply_to"),
            "deleted": bool(r.get("deleted")), "at": account.from_iso(r.get("created_at")),
            "reactions": (reactions or {}).get(r["id"], {})}


def messages(conv, before=None, limit=PAGE) -> list:
    """The last `limit` messages of a chat (older than message `before` when given), oldest first."""
    session = _session()
    params = {"conversation_id": "eq." + conv, "order": "id.desc", "limit": str(limit), "select": "*"}
    if before:
        params["id"] = f"lt.{before}"
    rows = list(reversed(account.rest("GET", "messages", session, params=params)))
    reactions = {}
    if rows:
        for r in account.rest("GET", "reactions", session, params={"message_id": _in(str(x["id"]) for x in rows),
                                                                  "select": "message_id,user_id,emoji"}):
            reactions.setdefault(r["message_id"], {}).setdefault(r["emoji"], []).append(r["user_id"])
    return [_message(r, reactions) for r in rows]


def messages_after(conv, last, limit=200) -> list:
    """What came into an open chat after message `last`."""
    session = _session()
    rows = account.rest("GET", "messages", session, params={"conversation_id": "eq." + conv, "id": f"gt.{last}",
                                                           "order": "id.asc", "limit": str(limit), "select": "*"})
    return [_message(r) for r in rows]


def search(conv, text, limit=50) -> list:
    """Messages of a chat that hold a text."""
    rows = account.rest("GET", "messages", _session(), params={"conversation_id": "eq." + conv, "deleted": "eq.false",
                                                              "body": "ilike.*" + text.replace("*", "") + "*",
                                                              "order": "id.desc", "limit": str(limit), "select": "*"})
    return [_message(r) for r in reversed(rows)]


def send(conv, body="", kind="text", payload=None, reply_to=None) -> dict:
    body = (body or "")[:MAX_TEXT]
    if kind == "text" and not body.strip():
        raise SocialError("Boş mesaj gönderilmez.", "EMPTY")
    row = {"conversation_id": conv, "kind": kind, "body": body}
    if payload is not None:
        row["payload"] = payload
    if reply_to:
        row["reply_to"] = reply_to
    try:
        made = account.rest("POST", "messages", _session(), json=row, prefer="return=representation")
    except account.AccountError as e:
        if e.code == "PERMISSION_DENIED":
            raise SocialError("Bu sohbete yazamazsın: yalnız yöneticiler yazabilir ya da artık arkadaş değilsiniz.",
                              "DENIED") from e
        raise
    return _message(made[0]) if made else {}


def message(uid, text):
    """A message to a friend."""
    return send(direct(uid), text)


def recommend(uid, song, text=""):
    """A song to a friend: {"title", "artist", "url"}."""
    return send(direct(uid), text or song_name(song), "song", song)


def recommend_conv(conv, song, text=""):
    return send(conv, text or song_name(song), "song", song)


def send_playlist(conv, name, songs):
    return send(conv, name, "playlist", {"name": name, "songs": songs[:500]})


def react(msg_id, emoji):
    session = _session()
    account.rest("POST", "reactions", session, params={"on_conflict": "message_id,user_id"},
                 prefer="resolution=merge-duplicates",
                 json={"message_id": msg_id, "user_id": session["uid"], "emoji": emoji})


def unreact(msg_id):
    session = _session()
    account.rest("DELETE", "reactions", session, params={"message_id": f"eq.{msg_id}", "user_id": "eq." + session["uid"]})


def delete_message(msg_id):
    account.rest("PATCH", "messages", _session(), params={"id": f"eq.{msg_id}"},
                 json={"deleted": True, "body": "", "payload": None})


def read(conv):
    """The chat was looked at: its unread messages count no more."""
    session = _session()
    account.rest("PATCH", "members", session, params={"conversation_id": "eq." + conv,
                                                      "user_id": "eq." + session["uid"]}, json={"last_read": account.iso()})
    with _lock:
        data = load()
        data["unread"].pop(conv, None)
        save(data)


def mute(conv, on=True):
    session = _session()
    account.rest("PATCH", "members", session, params={"conversation_id": "eq." + conv,
                                                      "user_id": "eq." + session["uid"]}, json={"muted": bool(on)})
    with _lock:
        data = load()
        muted = set(data["muted"])
        (muted.add if on else muted.discard)(conv)
        data["muted"] = sorted(muted)
        save(data)


def read_marks(conv) -> dict:
    """{uid: when} each member last looked at this chat (for the ✓✓ under my messages)."""
    rows = account.rest("GET", "members", _session(), params={"conversation_id": "eq." + conv,
                                                             "select": "user_id,last_read"})
    return {r["user_id"]: account.from_iso(r["last_read"]) for r in rows}


def feedback_song(uid, song, value):
    """Tell the one who recommended a song (a message in a chat) whether it was liked."""
    session = _session()
    account.rest("POST", "notifications", session,
                 json={"user_id": uid, "from_id": session["uid"], "kind": "feedback", "body": me(session)["name"],
                       "payload": {"song": song or {}, "value": int(value)}}, prefer="return=minimal")


def tell_like(song, value):
    """👍 / 👎 told to every friend (they see "X liked this song")."""
    session = _session()
    who = me(session)
    rows = [{"user_id": uid, "from_id": session["uid"], "kind": "like", "body": who["name"],
             "payload": {"song": song, "value": int(value)}} for uid in load()["friends"]]
    if rows:
        account.rest("POST", "notifications", session, json=rows, prefer="return=minimal")


def feedback(note_id, value):
    """The answer to a recommended song: 👍 / 👎 goes back to whoever sent it."""
    session = _session()
    data = load()
    note = next((n for n in data["notes"] if n["id"] == note_id), None)
    if note is None or not note.get("from"):
        return
    account.rest("POST", "notifications", session,
                 json={"user_id": note["from"], "from_id": session["uid"], "kind": "feedback",
                       "body": me(session)["name"], "payload": {"song": note.get("song") or {}, "value": int(value)}},
                 prefer="return=minimal")
    with _lock:
        data = load()
        for n in data["notes"]:
            if n["id"] == note_id:
                n["answered"] = int(value)
        save(data)


# ------------------------------------------------------------------------------ groups
def create_group(name, about="", emoji="👥", people=()):
    session = _session()
    conv = account.rest("POST", "rpc/create_group", session, json={
        "group_name": name, "group_about": about, "group_emoji": emoji, "people": list(people)})
    return conv


def group_members(conv) -> list:
    """[{"uid", "role", "name", "username"}], the admins first."""
    session = _session()
    rows = account.rest("GET", "members", session, params={"conversation_id": "eq." + conv,
                                                          "select": "user_id,role,joined_at"})
    cards = profiles([r["user_id"] for r in rows], session)
    out = [{"uid": r["user_id"], "role": r["role"], "name": cards.get(r["user_id"], {}).get("name", "?"),
            "username": cards.get(r["user_id"], {}).get("username", ""), "joined": account.from_iso(r["joined_at"])}
           for r in rows]
    return sorted(out, key=lambda m: (m["role"] != "admin", m["joined"]))


def group_add(conv, uid):
    account.rest("POST", "rpc/group_add", _session(), json={"conv": conv, "person": uid})


def group_remove(conv, uid):
    account.rest("POST", "rpc/group_remove", _session(), json={"conv": conv, "person": uid})


def group_role(conv, uid, admin):
    account.rest("POST", "rpc/group_role", _session(), json={"conv": conv, "person": uid,
                                                            "new_role": "admin" if admin else "member"})


def group_leave(conv):
    account.rest("POST", "rpc/group_leave", _session(), json={"conv": conv})


def group_delete(conv):
    account.rest("POST", "rpc/group_delete", _session(), json={"conv": conv})


def group_update(conv, **fields):
    """name, about, emoji, only_admins, photo."""
    allowed = {k: v for k, v in fields.items() if k in ("name", "about", "emoji", "only_admins", "photo")}
    if allowed:
        account.rest("PATCH", "conversations", _session(), params={"id": "eq." + conv}, json=allowed)


def system_text(body, names) -> str:
    """What a system message of a group says ("added:<uid>" ...), with the names of the people in it."""
    kind, _, who = (body or "").partition(":")
    name = names.get(who, "?")
    return {"created": "Grup oluşturuldu", "left": "Bir üye gruptan çıktı", "added": f"{name} gruba eklendi",
            "removed": f"{name} gruptan çıkarıldı", "admin": f"{name} yönetici yapıldı",
            "member": f"{name} yöneticilikten alındı"}.get(kind, "")


# ------------------------------------------------------------------------------ what came in
def poll() -> list:
    """Look for what is new: requests, new friends, messages, notifications. Returns the events
    ([{"kind", "name", "text", ...}]) and keeps them as notifications; the groups list changing is the kind "groups"."""
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
    with _lock:
        data = load()
        events = []
        events += _poll_friends(session, data)            # (before the requests: an accepted one is gone from them)
        events += _poll_requests(session, data)
        events += _poll_messages(session, data)
        events += _poll_notifications(session, data)
        try:
            data["unread"] = {r["conversation_id"]: r["n"] for r in
                              account.rest("POST", "rpc/unread_counts", session, json={})}
        except account.AccountError as e:
            log.info("unread numbers: %s", e)
        save(data)
    return events[:NOTE_LIMIT] if len(events) > NOTE_LIMIT else events


def _poll_requests(session, data) -> list:
    rows = account.rest("GET", "friend_requests", session, params={"to_id": "eq." + session["uid"],
                                                                  "select": "from_id,at"})
    ids = [r["from_id"] for r in rows]
    new = [u for u in ids if u not in data["requests"]]
    cards = profiles(new, session) if new else {}
    events = []
    data["requests"] = {u: data["requests"].get(u) or {"username": cards.get(u, {}).get("username", ""),
                                                         "name": cards.get(u, {}).get("name", ""), "at": time.time()}
                        for u in ids}
    for u in new:
        c = cards.get(u, {})
        events.append({"kind": "request", "uid": u, "name": c.get("name", "?"),
                       "text": f"{c.get('name', '?')} sana arkadaşlık isteği gönderdi"})
    out = account.rest("GET", "friend_requests", session, params={"from_id": "eq." + session["uid"],
                                                                 "select": "to_id,at"})
    data["outgoing"] = {r["to_id"]: data["outgoing"].get(r["to_id"]) or {"username": "", "name": "", "at": time.time()}
                        for r in out}
    return events


def _poll_friends(session, data) -> list:
    rows = account.rest("GET", "friendships", session, params={"user_id": "eq." + session["uid"],
                                                              "select": "friend_id"})
    now = {r["friend_id"] for r in rows}
    old = set(data["friends"])
    events, joined = [], now - old
    cards = profiles(joined, session) if joined else {}
    for u in joined:
        c = cards.get(u, {})
        data["friends"][u] = {"username": c.get("username", ""), "name": c.get("name", "")}
        if u in data["outgoing"]:                     # I asked, they said yes
            who = {"uid": u, "name": c.get("name", ""), "username": c.get("username", "")}
            text = f"{c.get('name', '?')} arkadaşlık isteğini kabul etti 🎉"
            _note(data, "accepted", who, text)
            events.append({"kind": "accepted", "uid": u, "name": c.get("name", "?"), "text": text})
        data["outgoing"].pop(u, None)
        data["requests"].pop(u, None)
    for u in old - now:                               # not friends any more (they unfriended or blocked me)
        data["friends"].pop(u, None)
        data["direct"].pop(u, None)
    return events


def _poll_messages(session, data) -> list:
    last = data["last_msg"]
    if not last:                                      # the first look: what was there before is not "new"
        newest = account.rest("GET", "messages", session, params={"order": "id.desc", "limit": "1", "select": "id"})
        data["last_msg"] = newest[0]["id"] if newest else 1
        return []
    rows = account.rest("GET", "messages", session, params={"id": f"gt.{last}", "order": "id.asc", "limit": "200",
                                                           "select": "*"})
    if not rows:
        return []
    data["last_msg"] = max(r["id"] for r in rows)
    mine = session["uid"]
    from_others = [r for r in rows if r.get("sender_id") != mine]
    system = any(r["kind"] == "system" for r in rows)
    people = profiles({r["sender_id"] for r in from_others if r.get("sender_id")} |
                      {r["body"].partition(":")[2] for r in rows if r["kind"] == "system"}, session)
    convs = {c["id"]: c for c in account.rest("GET", "conversations", session, params={
        "id": _in({r["conversation_id"] for r in from_others}), "select": "id,kind,name"})} if from_others else {}
    muted = set(data["muted"])
    events = []
    if system:
        events.append({"kind": "groups", "text": ""})
    for r in from_others:
        if r["kind"] == "system" or r["id"] <= last:
            continue
        who = people.get(r.get("sender_id"), {"name": "?", "username": ""})
        who = {"uid": r.get("sender_id"), "name": who.get("name", "?"), "username": who.get("username", "")}
        conv = convs.get(r["conversation_id"], {})
        place = f"{conv.get('name', '')} · " if conv.get("kind") == "group" else ""
        song = r.get("payload") if r["kind"] == "song" else None
        if r["kind"] == "song" and isinstance(song, dict):
            text = f"🎵 {who['name']} sana bir şarkı öneriyor: {song_name(song)}"
            _note(data, "recommend", who, text, song, msg=r["id"], conv=r["conversation_id"])
            events.append({"kind": "recommend", "uid": who["uid"], "conv": r["conversation_id"], "name": who["name"],
                           "text": text})
            continue
        if r["kind"] == "playlist":
            text = f"📋 {who['name']} bir çalma listesi gönderdi: {r.get('body', '')}"
            _note(data, "playlist", who, text, msg=r["id"], conv=r["conversation_id"])
            events.append({"kind": "playlist", "uid": who["uid"], "conv": r["conversation_id"], "name": who["name"],
                           "text": text})
            continue
        body = r.get("body", "")
        if r["kind"] in ("image", "file"):
            body = "📎 " + ((r.get("payload") or {}).get("name") or "dosya")
        text = f"💬 {place}{who['name']}: {body}"
        mention = mine in ((r.get("payload") or {}).get("mentions") or []) if isinstance(r.get("payload"), dict) else False
        if mention:
            _note(data, "mention", who, f"@ {who['name']} seni {conv.get('name', 'sohbette')} grubunda andı: {body}",
                  msg=r["id"], conv=r["conversation_id"])
        if r["conversation_id"] in muted and not mention:
            continue
        events.append({"kind": "message", "uid": who["uid"], "conv": r["conversation_id"], "name": who["name"],
                       "text": text, "mention": mention})
    return events


def _poll_notifications(session, data) -> list:
    rows = account.rest("GET", "notifications", session, params={"user_id": "eq." + session["uid"],
                                                                "seen": "eq.false", "order": "id.asc", "select": "*"})
    events = []
    for r in rows:
        payload = r.get("payload") or {}
        song = payload.get("song") if isinstance(payload, dict) else None
        value = int(payload.get("value", 0)) if isinstance(payload, dict) else 0
        who = {"uid": r.get("from_id") or "", "name": r.get("body") or "?", "username": ""}
        name = who["name"]
        if r["kind"] == "like":
            text = (f"👍 {name} bu şarkıyı beğendi: {song_name(song)}" if value > 0
                    else f"👎 {name} bu şarkıyı beğenmedi: {song_name(song)}")
        elif r["kind"] == "feedback":
            text = (f"👍 {name} önerdiğin şarkıyı beğendi: {song_name(song)}" if value > 0
                    else f"👎 {name} önerdiğin şarkıyı beğenmedi: {song_name(song)}")
        else:
            text = f"{name} DISO hesabını sildi"
        _note(data, r["kind"], who, text, song, value)
        events.append({"kind": r["kind"], "name": name, "text": text})
    if rows:
        account.rest("PATCH", "notifications", session, params={"user_id": "eq." + session["uid"], "seen": "eq.false"},
                     json={"seen": True})
    return events


def song_name(song) -> str:
    title, artist = (song or {}).get("title", ""), (song or {}).get("artist", "")
    return f"{artist} - {title}" if artist and title else title or artist or "?"


# ------------------------------------------------------------------------------ files in chats
BUCKET = "files"


def upload(conv, file_path, kind=None):
    """Send a file or a picture into a chat (up to MAX_FILE bytes): it goes into the bucket, then a message tells."""
    size = os.path.getsize(file_path)
    if size > MAX_FILE:
        raise SocialError(f"Dosya çok büyük (en fazla {MAX_FILE // (1024 * 1024)} MB).", "TOO_BIG")
    session = _session()
    name = os.path.basename(file_path)
    key = f"{conv}/{session['uid']}-{uuid.uuid4().hex[:10]}-{_safe(name)}"
    with open(file_path, "rb") as f:
        account._call("POST", f"{account.STORAGE_URL}/object/{BUCKET}/{key}", timeout=(10, 300),
                      headers={**account._headers(session), "x-upsert": "false",
                               "Content-Type": "application/octet-stream"}, data=f)
    is_picture = name.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp", "bmp")
    return send(conv, name, kind or ("image" if is_picture else "file"), {"path": key, "name": name, "size": size})


def _safe(name) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:80] or "dosya"


def download(payload, dest_folder) -> str:
    """Save a file from a chat into a folder; returns the path."""
    session = _session()
    key = payload["path"]
    blob = account._raw("GET", f"{account.STORAGE_URL}/object/authenticated/{BUCKET}/{key}", headers=account._headers(session),
                        timeout=(10, 300))
    os.makedirs(dest_folder, exist_ok=True)
    target = os.path.join(dest_folder, _safe(payload.get("name") or "dosya"))
    base, ext = os.path.splitext(target)
    n = 1
    while os.path.exists(target):
        n += 1
        target = f"{base} ({n}){ext}"
    with open(target, "wb") as f:
        f.write(blob)
    return target


# ------------------------------------------------------------------------------ the live connection
REALTIME = "wss://" + account.SUPABASE.split("//", 1)[1] + "/realtime/v1/websocket?apikey=" + account.API_KEY + "&vsn=1.0.0"
LIVE_TABLES = ("messages", "members", "conversations", "friend_requests", "friendships", "notifications", "reactions")
LIVE_RETRY = 20                 # s: no connection: tried again after this (polling goes on)
LIVE_RENEW = 50 * 60            # s: the access token lives an hour: the connection is made again with a new one
HEARTBEAT = 25                  # s


class Live(threading.Thread):
    """Supabase Realtime: while DISO runs it listens to the tables of friends and chats; when something changes (a
    message came, a request, a new friend ...) on_change() is called at once, and DISO looks (poll) instead of
    waiting for its next look. Also "X is typing" travels here (a broadcast, nothing is stored): on_typing(conv, uid).
    The database says who may hear what (the same row level security as for reading)."""

    def __init__(self, on_change, on_typing=None, connect=None):
        super().__init__(daemon=True, name="friends-live")
        self.on_change, self.on_typing = on_change, on_typing
        self.connect = connect               # (tests: a pretend connection)
        self.stopped = threading.Event()
        self.connected = False
        self._ws = None
        self._ref = 0
        self._send_lock = threading.Lock()

    def stop(self):
        self.stopped.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def _say(self, ws, topic, event, payload):
        self._ref += 1
        with self._send_lock:
            ws.send(json.dumps({"topic": topic, "event": event, "payload": payload, "ref": str(self._ref)}))

    def typing(self, conv):
        """I am typing in this chat (the others see it for a few seconds)."""
        ws = self._ws
        if ws is None or not self.connected:
            return
        try:
            self._say(ws, "realtime:diso", "broadcast", {"type": "broadcast", "event": "typing",
                                                          "payload": {"conv": conv, "uid": (account.load() or {}).get("uid")}})
        except Exception as e:  # noqa: BLE001
            log.info("typing not sent: %s", e)

    def run(self):
        while not self.stopped.is_set():
            session = account.load()
            if session is None or not session.get("verified"):
                self.stopped.wait(30)
                continue
            try:
                self._connection(session)
            except Exception as e:  # noqa: BLE001 - no live connection for a while: polling goes on
                log.info("friends live: %s", e)
            self.connected = False
            self._ws = None
            self.stopped.wait(LIVE_RETRY)

    def _connection(self, session):
        if self.connect is not None:
            self._on(self.connect(REALTIME), session)
            return
        from websockets.sync.client import connect
        with connect(REALTIME, open_timeout=10, max_size=2 ** 22) as ws:
            self._on(ws, session)

    def _on(self, ws, session):
        self._ws = ws
        try:
            self._say(ws, "realtime:diso", "phx_join", {
                "config": {"broadcast": {"self": False}, "presence": {"key": ""},
                           "postgres_changes": [{"event": "*", "schema": "public", "table": t} for t in LIVE_TABLES]},
                "access_token": account.token(session)})
            began, beat = time.time(), time.time()
            while not self.stopped.is_set() and time.time() - began < LIVE_RENEW:
                if time.time() - beat > HEARTBEAT:
                    self._say(ws, "phoenix", "heartbeat", {})
                    beat = time.time()
                try:
                    raw = ws.recv(timeout=HEARTBEAT)
                except TimeoutError:
                    continue
                self._handle(json.loads(raw))
        finally:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def _handle(self, message):
        event, payload = message.get("event"), message.get("payload") or {}
        if event == "phx_reply" and message.get("topic") == "realtime:diso":
            self.connected = payload.get("status") == "ok"
            if self.connected:
                self.on_change()                       # (what came while there was no connection)
        elif event == "postgres_changes":
            self.on_change()
        elif event == "broadcast" and payload.get("event") == "typing" and self.on_typing:
            data = payload.get("payload") or {}
            if data.get("uid") != (account.load() or {}).get("uid"):
                self.on_typing(data.get("conv"), data.get("uid"))
        elif event in ("phx_error", "phx_close"):
            raise OSError("live connection closed")


# ------------------------------------------------------------------------------ the account goes
def forget_everything(session):
    """Before the account is deleted: friends are told, the files it sent are deleted (the database deletes the
    rest with the account: its files, lists, friendships, memberships; its messages stay without a name)."""
    who = me(session)
    rows = [{"user_id": uid, "from_id": session["uid"], "kind": "gone", "body": who["name"]}
            for uid in friends().keys()]
    try:
        for f in account.rest("GET", "friendships", session, params={"user_id": "eq." + session["uid"],
                                                                   "select": "friend_id"}):
            if f["friend_id"] not in {r["user_id"] for r in rows}:
                rows.append({"user_id": f["friend_id"], "from_id": session["uid"], "kind": "gone", "body": who["name"]})
        if rows:
            account.rest("POST", "notifications", session, json=rows, prefer="return=minimal")
    except account.AccountError as e:
        log.info("friends not told: %s", e)
    try:
        for m in account.rest("GET", "members", session, params={"user_id": "eq." + session["uid"],
                                                                "select": "conversation_id"}):
            listing = account._call("POST", f"{account.STORAGE_URL}/object/list/{BUCKET}", headers=account._headers(session),
                                    json={"prefix": m["conversation_id"], "limit": 1000})
            mine = [f"{m['conversation_id']}/{o['name']}" for o in listing if o["name"].startswith(session["uid"])]
            if mine:
                account._call("DELETE", f"{account.STORAGE_URL}/object/{BUCKET}", headers=account._headers(session),
                              json={"prefixes": mine})
    except account.AccountError as e:
        log.info("files not deleted: %s", e)
    try:
        os.remove(path())
    except OSError:
        pass
