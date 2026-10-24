"""👤 The DISO account: a name, a user name, an e-mail and a password (Firebase Authentication) that keep the settings,
the playlists, the followed channels and the download history the same on every computer signed in to it. They are
kept in Cloud Firestore under users/<uid>/files/<name>; its rules let only the owner read or write them, and only
once the e-mail address is confirmed. User names are claimed in usernames/<name> (one owner each).

Making an account: the name, the user name, the e-mail and the password are asked; Firebase mails a link and the
account counts only after the link was opened ("Doğruladım"). Until then it is "waiting" (waiting()).

The songs and videos themselves never travel, only DISO's own small files do. A song of a list that lives in
DISO's own music folder travels as "%DISO_MUSIC%\\<file>", so on another computer it points into that computer's
music folder; a song whose file is not there is marked "away" (the player then keeps it instead of dropping it as
deleted) until it is downloaded again (App.download_away_songs) or its file turns up.

How the files travel:
* at start, before anything reads them (sync("start") from main.py): what changed in the account since this
  computer last saw it comes in. When this computer changed the same file too, the account wins and the
  local file is kept as "<file>.before-sync".
* while DISO runs (every few minutes) and when it closes (sync("up")): what changed here goes up. A file that
  changed in the account meanwhile is left alone; it comes in at the next start.
* "🔄 Şimdi eşitle" and the first sign-in (sync("now")): both ways. What comes in waits in backup's
  "restore-pending" folder and is put in place at the next start (DISO is running and would write over it).
Settings that belong to this computer (folders, the USB stick, the port, starting with Windows ...) never travel.
The session (its refresh token) is kept encrypted for this Windows user (DPAPI), like the YouTube Music one."""
import hashlib
import json
import os
import re
import socket
import threading
import time

import requests

from . import backup, brand, i18n, safefile
from .google_account import _dpapi
from .logs import log
from .utils import app_data_dir

API_KEY = "AIzaSyBvKGtY0NW3j40TdxqpFksvj51MN5FCvSQ"      # a Firebase web key: public by design (the rules guard)
PROJECT = "diso-2112"
AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts:"
TOKEN_URL = "https://securetoken.googleapis.com/v1/token"
STORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"
TIMEOUT = (5, 15)              # connect, read (seconds)
START_TIMEOUT = (2, 4)         # at start DISO's window waits for this: short
CLOSE_TIMEOUT = (3, 5)
SYNC_EVERY = 10 * 60 * 1000    # ms: what changed here goes up this often while DISO runs
MAX_BYTES = 900_000            # a Firestore document holds 1 MiB at most
MIN_PASSWORD = 6
USERNAME = re.compile(r"^[a-z0-9._]{3,20}$")
FILES = ("settings.json", "playlists.json", "channels.json", "history.json")
MUSIC_DIR_NAME = "Müzik"       # (music_search.MUSIC_DIR_NAME: not imported, it pulls in the whole downloader)
MUSIC_MARK = "%DISO_MUSIC%"
REDOWNLOAD_MARK = "account-redownload"     # a file in the data folder: download the "away" songs at the next start
# settings of this computer only: they stay as they are on each one
LOCAL_SETTINGS = frozenset({
    "folder", "watch_folder", "usb_copy", "cookies", "proxy", "bridge_on", "bridge_port", "start_with_windows",
    "associate", "tray_on_close", "last_version", "update_announced", "extension_seen", "extension_ask",
    "extension_ask_after", "restart_view", "account_ask",
})
SESSION_GONE = {"TOKEN_EXPIRED", "USER_DISABLED", "USER_NOT_FOUND", "INVALID_REFRESH_TOKEN",
                "INVALID_GRANT_TYPE", "MISSING_REFRESH_TOKEN", "UNAUTHENTICATED"}
MESSAGES = {
    "EMAIL_EXISTS": "Bu e-postayla zaten bir hesap var. “Giriş yap”ı dene.",
    "EMAIL_NOT_FOUND": "E-posta ya da şifre yanlış.",
    "INVALID_PASSWORD": "E-posta ya da şifre yanlış.",
    "INVALID_LOGIN_CREDENTIALS": "E-posta ya da şifre yanlış.",
    "INVALID_EMAIL": "Bu bir e-posta adresine benzemiyor.",
    "MISSING_PASSWORD": "Şifreyi yazmadın.",
    "WEAK_PASSWORD": f"Şifre en az {MIN_PASSWORD} karakter olmalı.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Çok fazla deneme oldu. Biraz bekleyip tekrar dene.",
    "USER_DISABLED": "Bu hesap kapatılmış.",
    "PERMISSION_DENIED": "Hesap sunucusu bu işleme izin vermedi.",
    "OPERATION_NOT_ALLOWED": "Hesap sunucusunda e-postayla giriş kapalı. DISO'nun Firebase ayarında "
                             "Email/Password açılmalı.",
    "PASSWORD_LOGIN_DISABLED": "Hesap sunucusunda e-postayla giriş kapalı. DISO'nun Firebase ayarında "
                               "Email/Password açılmalı.",
    "ALREADY_EXISTS": "Bu kullanıcı adı alınmış, başka birini dene.",
    "BAD_USERNAME": "Kullanıcı adı 3–20 karakter olmalı: küçük harf, rakam, nokta ya da alt çizgi.",
    "MISSING_NAME": "Adını ve soyadını yaz.",
    "NOT_VERIFIED": "E-posta adresin henüz doğrulanmadı. Gmail'ine gelen bağlantıya tıkla, sonra “Doğruladım” de.",
}


class AccountError(Exception):
    def __init__(self, text, code=""):
        super().__init__(text)
        self.code = code


def _message(data, status) -> tuple:
    err = data.get("error") if isinstance(data, dict) else None
    raw = ""
    if isinstance(err, dict):
        # Auth names the problem in "message" (EMAIL_EXISTS ...); Firestore writes a sentence there and names
        # it in "status" (PERMISSION_DENIED, ALREADY_EXISTS ...)
        message = str(err.get("message") or "")
        word = message.split(" ")[0].split(":")[0].strip()
        raw = word if re.fullmatch(r"[A-Z_]+", word or "") else str(err.get("status") or message)
    elif isinstance(err, str):
        raw = err.upper()               # the token door answers {"error": "invalid_grant"}
    code = raw.split(" ")[0].split(":")[0].strip()
    if code in SESSION_GONE:
        return "Oturumun süresi doldu. Hesabına yeniden giriş yap.", code
    return MESSAGES.get(code, f"Hesap sunucusu bir hata verdi ({code or status})."), code


def _call(method, url, timeout=TIMEOUT, **kw) -> dict:
    """The one door to the internet (tests put a pretend Firebase here)."""
    try:
        r = requests.request(method, url, timeout=timeout, **kw)
    except requests.RequestException as e:
        raise AccountError("İnternete ulaşamadım. Bağlantını kontrol edip tekrar dene.", "OFFLINE") from e
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        raise AccountError(*_message(data, r.status_code))
    return data


def _auth(path, body, timeout=TIMEOUT) -> dict:
    """Firebase Authentication; the mails it sends (the link) are in DISO's language."""
    return _call("POST", AUTH_URL + path + "?key=" + API_KEY, timeout=timeout, json=body,
                 headers={"X-Firebase-Locale": "tr" if i18n.current == "tr" else "en"})


# ------------------------------------------------------------------------------ the session
def store_path() -> str:
    return os.path.join(app_data_dir(), "account.bin")


def state_path(folder=None) -> str:
    return os.path.join(folder or app_data_dir(), "account-sync.json")


def load():
    """The session ({uid, email, refresh, token, expires, verified, profile}), or None."""
    try:
        with open(store_path(), "rb") as f:
            data = json.loads(_dpapi(f.read(), False).decode("utf-8"))
        return data if isinstance(data, dict) and data.get("uid") and data.get("refresh") else None
    except (OSError, ValueError):
        return None


def _save(session):
    path = store_path()
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(_dpapi(json.dumps(session).encode("utf-8"), True))
    os.replace(tmp, path)


def signed_in() -> bool:
    """Signed in with a confirmed e-mail: the account works."""
    session = load()
    return bool(session and session.get("verified"))


def waiting() -> bool:
    """An account was made (or signed in to) whose e-mail is not confirmed yet."""
    session = load()
    return bool(session and not session.get("verified"))


def email() -> str:
    return (load() or {}).get("email", "")


def profile() -> dict:
    return (load() or {}).get("profile") or {}


def display_name(session=None) -> str:
    """'Ad Soyad', else the user name, else the e-mail's first part."""
    session = session or load() or {}
    p = session.get("profile") or {}
    name = " ".join(x for x in (p.get("first", ""), p.get("last", "")) if x).strip()
    return name or p.get("username", "") or session.get("email", "").split("@")[0]


def _check(address, password=None):
    address = (address or "").strip()
    if "@" not in address or "." not in address.split("@")[-1] or " " in address:
        raise AccountError(MESSAGES["INVALID_EMAIL"], "INVALID_EMAIL")
    if password is not None and len(password) < MIN_PASSWORD:
        raise AccountError(MESSAGES["WEAK_PASSWORD"], "WEAK_PASSWORD")
    return address


def clean_username(name) -> str:
    name = (name or "").strip().lstrip("@").lower()
    if not USERNAME.match(name):
        raise AccountError(MESSAGES["BAD_USERNAME"], "BAD_USERNAME")
    return name


def _signed(data, **extra) -> dict:
    session = {"uid": data["localId"], "email": data.get("email", ""), "refresh": data["refreshToken"],
               "token": data["idToken"], "expires": time.time() + int(data.get("expiresIn", 3600)) - 60,
               "verified": False, **extra}
    _save(session)
    return session


def _headers(session, timeout=TIMEOUT) -> dict:
    return {"Authorization": "Bearer " + token(session, timeout)}


def sign_up(first, last, username, address, password) -> dict:
    """A new account. Its user name is claimed and a link to confirm the e-mail is mailed; the account works
    once the link was opened (check_verified)."""
    first, last = " ".join((first or "").split()), " ".join((last or "").split())
    if not first or not last:
        raise AccountError(MESSAGES["MISSING_NAME"], "MISSING_NAME")
    username = clean_username(username)
    address = _check(address, password)
    data = _auth("signUp", {"email": address, "password": password, "returnSecureToken": True})
    session = _signed(data, profile={"first": first, "last": last, "username": username, "email": address})
    try:
        _call("POST", f"{STORE_URL}/usernames", params={"documentId": username}, headers=_headers(session),
              json={"fields": {"uid": {"stringValue": session["uid"]}, "made": {"doubleValue": time.time()}}})
    except AccountError:
        try:                   # the name is taken (or could not be claimed): the half-made account goes again
            _auth("delete", {"idToken": session["token"]})
        except AccountError:
            log.warning("account: could not take back the account %s", session["uid"])
        sign_out()
        raise
    try:
        _auth("update", {"idToken": session["token"], "displayName": f"{first} {last}", "returnSecureToken": False})
    except AccountError as e:
        log.info("account: no display name: %s", e)
    send_verification(session)
    return session


def send_verification(session=None):
    """(Again) the mail with the link that confirms the e-mail address."""
    session = session or load()
    if session is None:
        raise AccountError("Hesaba giriş yapılmamış.")
    _auth("sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": token(session)})


def check_verified(session=None) -> bool:
    """"Doğruladım": was the link opened? Then the account works (a new token carries the news to the rules)
    and the name given at sign-up is kept in the account."""
    session = session or load()
    if session is None:
        raise AccountError("Hesaba giriş yapılmamış.")
    users = _auth("lookup", {"idToken": token(session)}).get("users") or [{}]
    if not users[0].get("emailVerified"):
        return False
    session["verified"], session["expires"] = True, 0
    token(session)                                        # the new token says email_verified=true
    _with_profile(session)
    _save(session)
    return True


def _profile_url(uid) -> str:
    return f"{STORE_URL}/users/{uid}/info/profile"


def _with_profile(session):
    """The name: the one kept in the account (another computer), or the one given at sign-up goes there."""
    try:
        doc = _call("GET", _profile_url(session["uid"]), headers=_headers(session))
        fields = doc.get("fields", {})
        session["profile"] = {k: fields[k].get("stringValue", "") for k in ("first", "last", "username", "email")
                              if k in fields}
    except AccountError as e:
        if e.code != "NOT_FOUND":
            log.info("account: no profile: %s", e)
            return
        p = session.get("profile") or {}
        if p:
            _call("PATCH", _profile_url(session["uid"]), headers=_headers(session),
                  json={"fields": {k: {"stringValue": str(v)} for k, v in p.items()}})


def sign_in(address, password) -> dict:
    address = _check(address)
    if not password:
        raise AccountError(MESSAGES["MISSING_PASSWORD"], "MISSING_PASSWORD")
    data = _auth("signInWithPassword", {"email": address, "password": password, "returnSecureToken": True})
    session = _signed(data)
    users = _auth("lookup", {"idToken": session["token"]}).get("users") or [{}]
    if users[0].get("emailVerified"):
        session["verified"] = True
        _with_profile(session)
        _save(session)
    return session


def reset_password(address):
    """Firebase mails a link for a new password."""
    address = _check(address)
    _auth("sendOobCode", {"requestType": "PASSWORD_RESET", "email": address})


def sign_out():
    """This computer forgets the account. Its own files stay as they are."""
    for path in (store_path(), store_path() + ".tmp", state_path()):
        try:
            os.remove(path)
        except OSError:
            pass


def token(session, timeout=TIMEOUT) -> str:
    """A valid ID token: the saved one, or a new one for the refresh token (they live an hour)."""
    if session.get("token") and session.get("expires", 0) > time.time():
        return session["token"]
    try:
        data = _call("POST", TOKEN_URL + "?key=" + API_KEY, timeout=timeout,
                     data={"grant_type": "refresh_token", "refresh_token": session["refresh"]})
    except AccountError as e:
        if e.code in SESSION_GONE:
            sign_out()
        raise
    session.update(token=data["id_token"], refresh=data.get("refresh_token", session["refresh"]),
                   expires=time.time() + int(data.get("expires_in", 3600)) - 60)
    _save(session)
    return session["token"]


# ------------------------------------------------------------------------------ the files in the account
def _doc_url(uid, name="") -> str:
    return f"{STORE_URL}/users/{uid}/files" + (f"/{name[:-len('.json')]}" if name else "")


def cloud_files(session, timeout=TIMEOUT) -> dict:
    """{name: {"text", "updated", "device"}} of what the account holds."""
    data = _call("GET", _doc_url(session["uid"]), timeout=timeout, headers=_headers(session, timeout),
                 params={"pageSize": 50})
    found = {}
    for doc in data.get("documents", []):
        name = doc.get("name", "").rsplit("/", 1)[-1] + ".json"
        fields = doc.get("fields", {})
        if name in FILES and "stringValue" in fields.get("data", {}):
            found[name] = {"text": fields["data"]["stringValue"],
                           "updated": float(fields.get("updated", {}).get("doubleValue", 0)),
                           "device": fields.get("device", {}).get("stringValue", "")}
    return found


def put_file(session, name, text, timeout=TIMEOUT) -> float:
    updated = time.time()
    _call("PATCH", _doc_url(session["uid"], name), timeout=timeout, headers=_headers(session, timeout),
          json={"fields": {"data": {"stringValue": text}, "updated": {"doubleValue": updated},
                           "device": {"stringValue": socket.gethostname()},
                           "version": {"stringValue": brand.VERSION_LABEL}}})
    return updated


# ------------------------------------------------------------------------------ the files here
def _canon(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(text) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _paths(data, change):
    """Every text inside data, through change()."""
    if isinstance(data, dict):
        return {k: _paths(v, change) for k, v in data.items()}
    if isinstance(data, list):
        return [_paths(v, change) for v in data]
    return change(data) if isinstance(data, str) else data


def _portable(data, folder):
    """Songs in DISO's own music folder travel as "%DISO_MUSIC%\\<file>": each computer has its own folder."""
    root = os.path.normcase(os.path.join(folder, MUSIC_DIR_NAME)) + os.sep

    def change(text):
        return MUSIC_MARK + os.sep + text[len(root):] if os.path.normcase(text).startswith(root) else text
    return _paths(data, change)


def _local_paths(data, folder):
    root = os.path.join(folder, MUSIC_DIR_NAME)

    def change(text):
        return root + text[len(MUSIC_MARK):] if text.startswith(MUSIC_MARK + "\\") or \
            text.startswith(MUSIC_MARK + "/") else text
    return _paths(data, change)


def _mark_away(data):
    """A list's song whose file is not on this computer waits for it ("away") instead of counting as deleted."""
    lists = data.get("playlists") if isinstance(data, dict) else None
    if isinstance(lists, dict):
        for tracks in lists.values():
            for t in tracks if isinstance(tracks, list) else ():
                if isinstance(t, dict) and isinstance(t.get("path"), str):
                    if os.path.isfile(t["path"]):
                        t.pop("away", None)
                    else:
                        t["away"] = True
    return data


def _strip_away(data):
    lists = data.get("playlists") if isinstance(data, dict) else None
    if isinstance(lists, dict):
        for tracks in lists.values():
            for t in tracks if isinstance(tracks, list) else ():
                if isinstance(t, dict):
                    t.pop("away", None)
    return data


def local_text(folder, name):
    """What of the file travels, as text (None: there is no such file, or it does not read)."""
    try:
        data = safefile.read_json(os.path.join(folder, name))
    except (OSError, ValueError):
        return None
    if name == "settings.json":
        if not isinstance(data, dict):
            return None
        data = {k: v for k, v in data.items() if k not in LOCAL_SETTINGS}
    data = _portable(data, folder)
    if name == "playlists.json":
        data = _strip_away(data)
    return _canon(data)


def _write(folder, name, text, local_folder, keep=False):
    """Put the account's file in folder; settings keep this computer's own values (from local_folder), songs
    point into this computer's music folder."""
    data = _local_paths(json.loads(text), local_folder)
    path = os.path.join(folder, name)
    if name == "settings.json":
        try:
            here = safefile.read_json(os.path.join(local_folder, name))
        except (OSError, ValueError):
            here = {}
        here = here if isinstance(here, dict) else {}
        data = {**{k: v for k, v in data.items() if k not in LOCAL_SETTINGS},
                **{k: v for k, v in here.items() if k in LOCAL_SETTINGS}}
    if name == "playlists.json":
        data = _mark_away(data)
    if keep and os.path.isfile(path):
        try:
            os.replace(path, path + ".before-sync")
        except OSError:
            pass
    os.makedirs(folder, exist_ok=True)
    safefile.write_json(path, data, indent=2)


def _state(folder, uid) -> dict:
    try:
        with open(state_path(folder), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    if not isinstance(st, dict) or st.get("uid") != uid:        # another account: nothing was seen yet
        st = {"uid": uid, "files": {}}
    st.setdefault("files", {})
    return st


def _save_state(folder, st):
    tmp = state_path(folder) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f)
    os.replace(tmp, state_path(folder))


def last_sync(folder=None) -> float:
    try:
        with open(state_path(folder), encoding="utf-8") as f:
            return float(json.load(f).get("last", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0.0


def first_time(folder=None) -> bool:
    """This computer has not synced with this account yet."""
    session = load()
    if session is None:
        return False
    try:
        with open(state_path(folder), encoding="utf-8") as f:
            return json.load(f).get("uid") != session["uid"]
    except (OSError, ValueError, AttributeError):
        return True


def ask_redownload(folder=None):
    """The songs of the lists are to be downloaded here at the next start (after what came in is in place)."""
    with open(os.path.join(folder or app_data_dir(), REDOWNLOAD_MARK), "w", encoding="utf-8") as f:
        f.write(str(time.time()))


def take_redownload(folder=None) -> bool:
    path = os.path.join(folder or app_data_dir(), REDOWNLOAD_MARK)
    if not os.path.isfile(path):
        return False
    try:
        os.remove(path)
    except OSError:
        pass
    return True


# ------------------------------------------------------------------------------ syncing
def plan(local, cloud, seen) -> dict:
    """What to do with each file: "up", "down", "conflict" (changed here and there), "same" or None.
    local: {name: hash or None}, cloud: {name: {"hash", "updated"}}, seen: {name: {"hash", "updated"}} as
    they were after the last sync on this computer."""
    todo = {}
    for name in FILES:
        mine, theirs, before = local.get(name), cloud.get(name), seen.get(name) or {}
        if theirs is None:
            todo[name] = "up" if mine else None
        elif mine is None:
            todo[name] = "down"
        elif mine == theirs["hash"]:
            todo[name] = "same"
        else:
            here, there = mine != before.get("hash"), theirs["updated"] != before.get("updated")
            todo[name] = "up" if here and not there else "down" if there and not here else "conflict"
    return todo


def _session_or_fail():
    session = load()
    if session is None:
        raise AccountError("Hesaba giriş yapılmamış.")
    if not session.get("verified"):
        raise AccountError(MESSAGES["NOT_VERIFIED"], "NOT_VERIFIED")
    return session


def peek(timeout=TIMEOUT, folder=None) -> dict:
    """Before the first sync of a computer: what the account holds and which of its files differ from the ones
    here ({"files", "differ", "device", "updated", "songs"}; songs: how many songs the account's lists hold)."""
    session = _session_or_fail()
    folder = folder or app_data_dir()
    cloud = cloud_files(session, timeout)
    differ = [n for n, c in cloud.items() if local_text(folder, n) not in (None, c["text"])]
    newest = max(cloud.values(), key=lambda c: c["updated"]) if cloud else {}
    songs = 0
    if "playlists.json" in cloud:
        try:
            lists = json.loads(cloud["playlists.json"]["text"]).get("playlists", {})
            songs = len({t.get("path") for tracks in lists.values() for t in tracks if isinstance(t, dict)})
        except (ValueError, AttributeError, TypeError):
            pass
    return {"files": sorted(cloud), "differ": differ, "device": newest.get("device", ""),
            "updated": newest.get("updated", 0), "songs": songs}


def sync(mode, timeout=TIMEOUT, folder=None, prefer=None) -> dict:
    """mode "start": what changed in the account is written now (DISO is opening, nothing has read the files).
    "up": only what changed here goes up. "now": both ways; what comes in waits for the next start.
    prefer "account" / "here" settles every file that differs (the first sign-in of a computer with data).
    Returns {"up": [...], "down": [...], "waiting": [...]}: the names that went up, came in, wait."""
    with _lock:              # the timer's sync and the closing one never run side by side
        return _sync(mode, timeout, folder, prefer)


_lock = threading.Lock()


def _sync(mode, timeout, folder, prefer):
    done = {"up": [], "down": [], "waiting": []}
    session = load()
    if session is None or not session.get("verified"):
        return done
    folder = folder or app_data_dir()
    pending = os.path.join(folder, backup.PENDING)
    if mode != "start" and os.path.isdir(pending):
        return done          # files wait for the next start: this computer's copies are already old
    cloud = cloud_files(session, timeout)
    st = _state(folder, session["uid"])
    texts = {n: local_text(folder, n) for n in FILES}
    todo = plan({n: t and _hash(t) for n, t in texts.items()},
                {n: {"hash": _hash(c["text"]), "updated": c["updated"]} for n, c in cloud.items()}, st["files"])
    for name, action in todo.items():
        if prefer and action in ("up", "down", "conflict"):
            action = "up" if prefer == "here" and texts[name] else "down" if name in cloud else action
        text = texts[name]
        if action == "same":
            st["files"][name] = {"hash": _hash(text), "updated": cloud[name]["updated"]}
        elif action == "up" and mode != "start":
            if len(text.encode("utf-8")) > MAX_BYTES:
                log.warning("account: %s is too big to sync (%d bytes)", name, len(text))
                continue
            st["files"][name] = {"hash": _hash(text), "updated": put_file(session, name, text, timeout)}
            done["up"].append(name)
        elif action in ("down", "conflict") and mode != "up":
            came = cloud[name]
            where = folder if mode == "start" else pending
            _write(where, name, came["text"], folder, keep=mode == "start" and action == "conflict")
            done["down" if mode == "start" else "waiting"].append(name)
            st["files"][name] = {"hash": _hash(came["text"]), "updated": came["updated"]}
    st["last"] = time.time()
    _save_state(folder, st)
    if done["up"] or done["down"] or done["waiting"]:
        log.info("account sync (%s): %s", mode, done)
    return done
