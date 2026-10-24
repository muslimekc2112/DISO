"""👤 The DISO account: an e-mail and a password (Firebase Authentication) that keep the settings, the playlists,
the followed channels and the download history the same on every computer signed in to it. They are kept in
Cloud Firestore under users/<uid>/files/<name>; its rules let only the owner read or write them. The songs and
videos themselves never travel: only DISO's own small files do.

An account is never needed: without one nothing here runs.

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
import socket
import threading
import time

import requests

from . import backup, brand, safefile
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
FILES = ("settings.json", "playlists.json", "channels.json", "history.json")
# settings of this computer only: they stay as they are on each one
LOCAL_SETTINGS = frozenset({
    "folder", "watch_folder", "usb_copy", "cookies", "proxy", "bridge_on", "bridge_port", "start_with_windows",
    "associate", "tray_on_close", "last_version", "update_announced", "extension_seen", "extension_ask",
    "extension_ask_after", "restart_view",
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
}


class AccountError(Exception):
    def __init__(self, text, code=""):
        super().__init__(text)
        self.code = code


def _message(data, status) -> tuple:
    err = data.get("error") if isinstance(data, dict) else None
    raw = ""
    if isinstance(err, dict):
        # Firestore names the refusal in "status" (its message is a sentence); Auth in "message"
        raw = str(err.get("status") if status in (401, 403) and err.get("status")
                  else err.get("message") or err.get("status") or "")
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


# ------------------------------------------------------------------------------ the session
def store_path() -> str:
    return os.path.join(app_data_dir(), "account.bin")


def state_path(folder=None) -> str:
    return os.path.join(folder or app_data_dir(), "account-sync.json")


def load():
    """The signed-in session ({uid, email, refresh, token, expires}), or None."""
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
    return load() is not None


def email() -> str:
    return (load() or {}).get("email", "")


def _check(address, password=None):
    address = (address or "").strip()
    if "@" not in address or "." not in address.split("@")[-1] or " " in address:
        raise AccountError(MESSAGES["INVALID_EMAIL"], "INVALID_EMAIL")
    if password is not None and len(password) < MIN_PASSWORD:
        raise AccountError(MESSAGES["WEAK_PASSWORD"], "WEAK_PASSWORD")
    return address


def _signed(data) -> dict:
    session = {"uid": data["localId"], "email": data.get("email", ""), "refresh": data["refreshToken"],
               "token": data["idToken"], "expires": time.time() + int(data.get("expiresIn", 3600)) - 60}
    _save(session)
    return session


def sign_up(address, password) -> dict:
    """A new account; it is signed in at once."""
    address = _check(address, password)
    return _signed(_call("POST", AUTH_URL + "signUp?key=" + API_KEY,
                         json={"email": address, "password": password, "returnSecureToken": True}))


def sign_in(address, password) -> dict:
    address = _check(address)
    if not password:
        raise AccountError(MESSAGES["MISSING_PASSWORD"], "MISSING_PASSWORD")
    return _signed(_call("POST", AUTH_URL + "signInWithPassword?key=" + API_KEY,
                         json={"email": address, "password": password, "returnSecureToken": True}))


def reset_password(address):
    """Firebase mails a link for a new password."""
    address = _check(address)
    _call("POST", AUTH_URL + "sendOobCode?key=" + API_KEY, json={"requestType": "PASSWORD_RESET", "email": address})


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
    data = _call("GET", _doc_url(session["uid"]), timeout=timeout,
                 headers={"Authorization": "Bearer " + token(session, timeout)}, params={"pageSize": 50})
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
    _call("PATCH", _doc_url(session["uid"], name), timeout=timeout,
          headers={"Authorization": "Bearer " + token(session, timeout)},
          json={"fields": {"data": {"stringValue": text}, "updated": {"doubleValue": updated},
                           "device": {"stringValue": socket.gethostname()},
                           "version": {"stringValue": brand.VERSION_LABEL}}})
    return updated


# ------------------------------------------------------------------------------ the files here
def _canon(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(text) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


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
    return _canon(data)


def _write(folder, name, text, local_folder, keep=False):
    """Put the account's file in folder; settings keep this computer's own values (from local_folder)."""
    data = json.loads(text)
    path = os.path.join(folder, name)
    if name == "settings.json":
        try:
            here = safefile.read_json(os.path.join(local_folder, name))
        except (OSError, ValueError):
            here = {}
        here = here if isinstance(here, dict) else {}
        data = {**{k: v for k, v in data.items() if k not in LOCAL_SETTINGS},
                **{k: v for k, v in here.items() if k in LOCAL_SETTINGS}}
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


def peek(timeout=TIMEOUT, folder=None) -> dict:
    """Before the first sync of a computer: what the account holds and which of its files differ from
    the ones here ({"files", "differ", "device", "updated"})."""
    session = load()
    if session is None:
        raise AccountError("Hesaba giriş yapılmamış.")
    folder = folder or app_data_dir()
    cloud = cloud_files(session, timeout)
    differ = [n for n, c in cloud.items() if local_text(folder, n) not in (None, c["text"])]
    newest = max(cloud.values(), key=lambda c: c["updated"]) if cloud else {}
    return {"files": sorted(cloud), "differ": differ, "device": newest.get("device", ""),
            "updated": newest.get("updated", 0)}


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
    if session is None:
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
            if mode == "start":
                _write(folder, name, came["text"], folder, keep=action == "conflict")
                done["down"].append(name)
            else:
                _write(pending, name, came["text"], folder)
                done["waiting"].append(name)
            st["files"][name] = {"hash": _hash(local_text(pending if mode != "start" else folder, name) or ""),
                                 "updated": came["updated"]}
    st["last"] = time.time()
    _save_state(folder, st)
    if done["up"] or done["down"] or done["waiting"]:
        log.info("account sync (%s): %s", mode, done)
    return done
