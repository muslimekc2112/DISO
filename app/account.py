"""👤 The DISO account: a name, a user name, an e-mail and a password (Supabase Authentication) that keep the
settings, the playlists, the followed channels and the download history the same on every computer signed in to it.
They are kept in the database (table user_files); its rules (row level security, supabase/schema.sql) let only the
owner read or write them. User names are unique (table profiles).

Making an account: the name, the user name, the e-mail and the password are asked; Supabase mails a 6 digit code and
the account counts only after the code was typed ("Doğrula"). Until then it is "waiting" (waiting()).

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
from datetime import datetime, timezone

import requests

from . import backup, brand, safefile
from .google_account import _dpapi
from .logs import log
from .utils import app_data_dir

# Supabase: the project's address and its publishable key (public by design: the rules in the database guard)
SUPABASE = "https://jllnyvngelhukntlunck.supabase.co"
API_KEY = "sb_publishable_W-m-tCPyOKMOSqOjN-gJug_e1xTUXxS"
AUTH_URL = SUPABASE + "/auth/v1"
REST_URL = SUPABASE + "/rest/v1"
STORAGE_URL = SUPABASE + "/storage/v1"
BACKEND = 2                    # which kind of account a saved session belongs to (1 was Firebase)
TIMEOUT = (5, 15)              # connect, read (seconds)
START_TIMEOUT = (2, 4)         # at start DISO's window waits for this: short
CLOSE_TIMEOUT = (3, 5)
SYNC_EVERY = 10 * 60 * 1000    # ms: what changed here goes up this often while DISO runs
MAX_BYTES = 4_000_000          # one synced file (the history of years is a few hundred KB)
MIN_PASSWORD = 6
CODE = re.compile(r"^\d{6,8}$")
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
    "ALREADY_EXISTS": "Bu kullanıcı adı alınmış, başka birini dene.",
    "BAD_USERNAME": "Kullanıcı adı 3–20 karakter olmalı: küçük harf, rakam, nokta ya da alt çizgi.",
    "MISSING_NAME": "Adını ve soyadını yaz.",
    "BAD_CODE": "Kod yanlış ya da süresi dolmuş. Yeni bir kod isteyebilirsin.",
    "MISSING_CODE": "E-postana gelen 6 haneli kodu yaz.",
    "REMOVED": "Bu bilgisayar, hesabından başka bir bilgisayardan çıkarıldı. İstersen yeniden giriş yapabilirsin.",
    "NOT_VERIFIED": "E-posta adresin henüz doğrulanmadı. Gmail'ine gelen 6 haneli kodu yaz.",
}
# what the server calls a problem -> our code
CODES = {
    "user_already_exists": "EMAIL_EXISTS", "email_exists": "EMAIL_EXISTS", "invalid_credentials": "INVALID_LOGIN_CREDENTIALS",
    "email_not_confirmed": "EMAIL_NOT_CONFIRMED", "weak_password": "WEAK_PASSWORD", "validation_failed": "INVALID_EMAIL",
    "over_email_send_rate_limit": "TOO_MANY_ATTEMPTS_TRY_LATER", "over_request_rate_limit": "TOO_MANY_ATTEMPTS_TRY_LATER",
    "otp_expired": "BAD_CODE", "otp_disabled": "BAD_CODE", "user_banned": "USER_DISABLED",
    "refresh_token_not_found": "TOKEN_EXPIRED", "refresh_token_already_used": "TOKEN_EXPIRED",
    "session_not_found": "TOKEN_EXPIRED", "session_expired": "TOKEN_EXPIRED", "user_not_found": "USER_NOT_FOUND",
    "42501": "PERMISSION_DENIED", "23505": "ALREADY_EXISTS", "PGRST116": "NOT_FOUND", "PGRST301": "TOKEN_EXPIRED",
    "PGRST303": "TOKEN_EXPIRED", "PGRST202": "NOT_FOUND",
}


class AccountError(Exception):
    def __init__(self, text, code=""):
        super().__init__(text)
        self.code = code


def _message(data, status) -> tuple:
    """(what to tell the person, our code) for what the server answered."""
    raw = ""
    if isinstance(data, dict):
        raw = str(data.get("error_code") or "")
        if not raw and data.get("error_description"):          # the token door: {"error": "invalid_grant", ...}
            text = str(data["error_description"]).lower()
            raw = ("invalid_credentials" if "invalid login" in text else
                   "email_not_confirmed" if "not confirmed" in text else
                   "refresh_token_not_found" if "refresh token" in text else str(data.get("error") or ""))
        if not raw:                                              # the database
            message = str(data.get("message") or data.get("msg") or "")
            if re.fullmatch(r"[A-Z_]{4,}", message):             # our own RAISE EXCEPTION 'NOT_FRIENDS' ...
                raw = message
            elif str(data.get("code") or "") in CODES:
                raw = str(data["code"])
        if not raw and status in (401, 404):
            raw = "TOKEN_EXPIRED" if status == 401 else "NOT_FOUND"
    code = CODES.get(raw, raw)
    if code in SESSION_GONE:
        return "Oturumun süresi doldu. Hesabına yeniden giriş yap.", code
    return MESSAGES.get(code, f"Hesap sunucusu bir hata verdi ({code or status})."), code


def _call(method, url, timeout=TIMEOUT, **kw):
    """The one door to the internet (tests put a pretend Supabase here)."""
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


def _raw(method, url, timeout=TIMEOUT, **kw) -> bytes:
    """The same door for what is not JSON (a file that is downloaded)."""
    try:
        r = requests.request(method, url, timeout=timeout, **kw)
    except requests.RequestException as e:
        raise AccountError("İnternete ulaşamadım. Bağlantını kontrol edip tekrar dene.", "OFFLINE") from e
    if r.status_code >= 400:
        try:
            data = r.json()
        except ValueError:
            data = {}
        raise AccountError(*_message(data, r.status_code))
    return r.content


def _anon() -> dict:
    return {"apikey": API_KEY}


def _auth(path, body, timeout=TIMEOUT, method="POST", params=None, session=None) -> dict:
    """Supabase Authentication (the mails it sends have the language of its templates)."""
    headers = _headers(session, timeout) if session else _anon()
    return _call(method, f"{AUTH_URL}/{path}", timeout=timeout, json=body, headers=headers, params=params)


def rest(method, table, session=None, params=None, json=None, prefer=None, timeout=TIMEOUT, anon=False):
    """The database: GET / POST / PATCH / DELETE on a table (or POST on "rpc/<function>"). The rows come back as a
    list (or what the function returns); params are the filters ("id": "eq.5", "select": "a,b", "order": "x.desc")."""
    headers = _anon() if anon else _headers(session, timeout)
    if prefer:
        headers["Prefer"] = prefer
    return _call(method, f"{REST_URL}/{table}", timeout=timeout, headers=headers, params=params, json=json)


def iso(seconds=None) -> str:
    return datetime.fromtimestamp(time.time() if seconds is None else seconds, timezone.utc).isoformat()


def from_iso(text) -> float:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# ------------------------------------------------------------------------------ the session
def store_path() -> str:
    return os.path.join(app_data_dir(), "account.bin")


def state_path(folder=None) -> str:
    return os.path.join(folder or app_data_dir(), "account-sync.json")


def pending_path() -> str:
    return os.path.join(app_data_dir(), "account-pending.json")


def load():
    """The session ({uid, email, refresh, token, expires, verified, profile}), or None."""
    try:
        with open(store_path(), "rb") as f:
            data = json.loads(_dpapi(f.read(), False).decode("utf-8"))
        ok = isinstance(data, dict) and data.get("uid") and data.get("refresh") and data.get("backend") == BACKEND
        return data if ok else None                          # (a session of the old Firebase accounts is no session)
    except (OSError, ValueError):
        return None


def _save(session):
    path = store_path()
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(_dpapi(json.dumps({**session, "backend": BACKEND}).encode("utf-8"), True))
    os.replace(tmp, path)


def pending():
    """{email, profile} of an account whose e-mail waits for its code, or None."""
    try:
        with open(pending_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and data.get("email") else None
    except (OSError, ValueError):
        return None


def _set_pending(address, profile=None):
    with open(pending_path(), "w", encoding="utf-8") as f:
        json.dump({"email": address, "profile": profile or {}}, f)


def _clear_pending():
    try:
        os.remove(pending_path())
    except OSError:
        pass


def signed_in() -> bool:
    """Signed in with a confirmed e-mail: the account works."""
    session = load()
    return bool(session and session.get("verified"))


def waiting() -> bool:
    """An account was made (or signed in to) whose e-mail is not confirmed yet."""
    return not signed_in() and pending() is not None


def email() -> str:
    return (load() or pending() or {}).get("email", "")


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


def clean_code(text) -> str:
    code = re.sub(r"\s+", "", text or "")
    if not code:
        raise AccountError(MESSAGES["MISSING_CODE"], "MISSING_CODE")
    if not CODE.match(code):
        raise AccountError(MESSAGES["BAD_CODE"], "BAD_CODE")
    return code


def _signed(data, address="", verified=True) -> dict:
    """The session Supabase gave ({access_token, refresh_token, expires_in, user}), saved."""
    user = data.get("user") or {}
    session = {"uid": user.get("id", ""), "email": user.get("email") or address, "refresh": data["refresh_token"],
               "token": data["access_token"], "expires": time.time() + int(data.get("expires_in", 3600)) - 60,
               "verified": verified}
    _save(session)
    return session


def _headers(session, timeout=TIMEOUT) -> dict:
    return {"apikey": API_KEY, "Authorization": "Bearer " + token(session, timeout)}


def username_free(name) -> bool:
    return bool(rest("POST", "rpc/username_free", anon=True, json={"name": name}))


def sign_up(first, last, username, address, password) -> dict:
    """A new account: Supabase mails a 6 digit code; the account works once it is typed (verify_code)."""
    first, last = " ".join((first or "").split()), " ".join((last or "").split())
    if not first or not last:
        raise AccountError(MESSAGES["MISSING_NAME"], "MISSING_NAME")
    username = clean_username(username)
    address = _check(address, password)
    if not username_free(username):
        raise AccountError(MESSAGES["ALREADY_EXISTS"], "ALREADY_EXISTS")
    try:
        data = _auth("signup", {"email": address, "password": password,
                                "data": {"username": username, "first_name": first, "last_name": last}})
    except AccountError as e:
        if e.code in ("EMAIL_EXISTS", "WEAK_PASSWORD", "INVALID_EMAIL", "TOO_MANY_ATTEMPTS_TRY_LATER", "OFFLINE"):
            raise
        if not username_free(username):                           # taken between the question and the sign-up
            raise AccountError(MESSAGES["ALREADY_EXISTS"], "ALREADY_EXISTS") from e
        raise
    if isinstance(data, dict) and data.get("identities") == []:   # an address that has an account already
        raise AccountError(MESSAGES["EMAIL_EXISTS"], "EMAIL_EXISTS")
    if isinstance(data, dict) and data.get("access_token"):       # (the project asks for no code: signed in at once)
        session = _signed(data, address)
        session["profile"] = {"first": first, "last": last, "username": username, "email": address}
        _save(session)
        _say_here(session)
        return session
    _set_pending(address, {"first": first, "last": last, "username": username, "email": address})
    return {"uid": (data or {}).get("id", ""), "email": address, "verified": False}


def send_verification(address=None):
    """(Again) the mail with the code that confirms the e-mail address."""
    address = address or (pending() or {}).get("email")
    if not address:
        raise AccountError("Hesaba giriş yapılmamış.")
    _auth("resend", {"type": "signup", "email": address})


def verify_code(code) -> dict:
    """"Doğrula": the code from the mail makes the account work; the session comes with it."""
    wait = pending()
    if wait is None:
        raise AccountError("Hesaba giriş yapılmamış.")
    code = clean_code(code)
    data = _auth("verify", {"type": "signup", "email": wait["email"], "token": code})
    session = _signed(data, wait["email"])
    session["profile"] = wait.get("profile") or {}
    _with_profile(session)
    _save(session)
    _clear_pending()
    _say_here(session)
    return session


def _say_here(session):
    try:
        _here(session, fresh=True)
    except AccountError as e:
        log.info("account: this computer is not listed yet: %s", e)


def _with_profile(session):
    """The name and the user name kept in the account (what another computer or the sign-up gave)."""
    try:
        rows = rest("GET", "profiles", session, params={"id": "eq." + session["uid"],
                                                       "select": "username,first_name,last_name"})
    except AccountError as e:
        log.info("account: no profile: %s", e)
        return
    if rows:
        r = rows[0]
        session["profile"] = {"first": r.get("first_name", ""), "last": r.get("last_name", ""),
                              "username": r.get("username", ""), "email": session.get("email", "")}


# ------------------------------------------------------------------------------ 💻 the computers of the account
def device_id() -> str:
    """This computer's own id (kept even when it signs out: signing in again is the same computer)."""
    path = os.path.join(app_data_dir(), "account-device.json")
    try:
        with open(path, encoding="utf-8") as f:
            found = json.load(f).get("id", "")
        if found:
            return found
    except (OSError, ValueError, AttributeError):
        pass
    import uuid
    new = uuid.uuid4().hex
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"id": new}, f)
    except OSError:
        pass
    return new


def _device_filter(session, device=None) -> dict:
    out = {"user_id": "eq." + session["uid"]}
    if device:
        out["device_id"] = "eq." + device
    return out


def _here(session, timeout=TIMEOUT, fresh=False):
    """This computer tells the account it is here (its name, when, DISO's version). fresh: it has just signed in,
    so an old "signed out from elsewhere" mark of it goes too."""
    row = {"user_id": session["uid"], "device_id": device_id(), "name": socket.gethostname(), "seen": iso(),
           "version": brand.VERSION_LABEL}
    if fresh:
        row["signed_out"] = False                        # (without it the mark a sign-out left stays as it is)
    rest("POST", "devices", session, params={"on_conflict": "user_id,device_id"}, json=row,
         prefer="resolution=merge-duplicates", timeout=timeout)


def _still_signed_in(session, timeout):
    """Was this computer signed out from another one? Then it forgets the account now."""
    rows = rest("GET", "devices", session, params={**_device_filter(session, device_id()), "select": "signed_out"},
                timeout=timeout)
    if rows and rows[0].get("signed_out"):
        sign_out()
        _mark_removed()
        raise AccountError(MESSAGES["REMOVED"], "REMOVED")
    return True


def devices(session=None) -> list:
    """The computers signed in to the account: [{"id", "name", "seen", "version", "this"}], newest first."""
    session = session or _session_or_fail()
    rows = rest("GET", "devices", session, params={**_device_filter(session), "signed_out": "eq.false",
                                                   "select": "device_id,name,seen,version"})
    mine = device_id()
    found = [{"id": r["device_id"], "name": r.get("name") or "?", "seen": from_iso(r.get("seen")),
              "version": r.get("version", ""), "this": r["device_id"] == mine} for r in rows]
    return sorted(found, key=lambda d: (not d["this"], -d["seen"]))


def sign_out_device(device, session=None):
    """That computer forgets the account the next time it talks to it (at its start, or within minutes)."""
    session = session or _session_or_fail()
    rest("PATCH", "devices", session, params=_device_filter(session, device), json={"signed_out": True})


def leave():
    """"Çıkış yap": the account forgets this computer (best it can), then this computer forgets the account."""
    session = load()
    if session is not None and session.get("verified"):
        try:
            rest("DELETE", "devices", session, params=_device_filter(session, device_id()), timeout=CLOSE_TIMEOUT)
        except AccountError as e:
            log.info("account: this computer stays listed: %s", e)
    sign_out()


def _removed_path():
    return os.path.join(app_data_dir(), "account-removed")


def _mark_removed():
    try:
        with open(_removed_path(), "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def take_removed() -> bool:
    """This computer was signed out from another one since DISO last asked (said once)."""
    try:
        os.remove(_removed_path())
        return True
    except OSError:
        return False


def sign_in(address, password) -> dict:
    """Signing in. An address whose e-mail was never confirmed gets a new code and is "waiting" (verified False)."""
    address = _check(address)
    if not password:
        raise AccountError(MESSAGES["MISSING_PASSWORD"], "MISSING_PASSWORD")
    try:
        data = _auth("token", {"email": address, "password": password}, params={"grant_type": "password"})
    except AccountError as e:
        if e.code != "EMAIL_NOT_CONFIRMED":
            raise
        _set_pending(address, (pending() or {}).get("profile") if (pending() or {}).get("email") == address else {})
        try:
            send_verification(address)
        except AccountError as again:
            log.info("account: no new code: %s", again)
        return {"uid": "", "email": address, "verified": False}
    session = _signed(data, address)
    _with_profile(session)
    _save(session)
    _clear_pending()
    _say_here(session)
    return session


def delete_account(password):
    """🗑 The account goes for good: the password is asked again, friends are told, everything it kept (files,
    lists, shared lists, user name, devices, friendships, messages it wrote stay without a name) is deleted."""
    session = load()
    if session is None:
        raise AccountError("Hesaba giriş yapılmamış.")
    try:
        fresh = sign_in(session.get("email", ""), password)
    except AccountError as e:
        if e.code in ("INVALID_LOGIN_CREDENTIALS", "INVALID_PASSWORD", "MISSING_PASSWORD"):
            raise AccountError("Şifre yanlış.", e.code) from e
        raise
    if not fresh.get("verified"):
        raise AccountError(MESSAGES["NOT_VERIFIED"], "NOT_VERIFIED")
    from . import social
    social.forget_everything(fresh)
    rest("POST", "rpc/delete_me", fresh, json={})
    sign_out()


def reset_password(address):
    """Supabase mails a 6 digit code for a new password (finish_reset)."""
    address = _check(address)
    _auth("recover", {"email": address})


def finish_reset(address, code, new_password):
    """The new password, with the code from the mail. Nothing is kept signed in: the person signs in next."""
    address = _check(address, new_password)
    data = _auth("verify", {"type": "recovery", "email": address, "token": clean_code(code)})
    _auth("user", {"password": new_password}, method="PUT", session={"uid": "", "token": data["access_token"],
                                                                     "expires": time.time() + 600, "refresh": "x"})


def sign_out():
    """This computer forgets the account. Its own files stay as they are."""
    for path in (store_path(), store_path() + ".tmp", state_path(), pending_path()):
        try:
            os.remove(path)
        except OSError:
            pass


def token(session, timeout=TIMEOUT) -> str:
    """A valid access token: the saved one, or a new one for the refresh token (they live an hour)."""
    if session.get("token") and session.get("expires", 0) > time.time():
        return session["token"]
    try:
        data = _call("POST", f"{AUTH_URL}/token", timeout=timeout, headers=_anon(),
                     params={"grant_type": "refresh_token"}, json={"refresh_token": session["refresh"]})
    except AccountError as e:
        if e.code in SESSION_GONE:
            sign_out()
        raise
    session.update(token=data["access_token"], refresh=data.get("refresh_token", session["refresh"]),
                   expires=time.time() + int(data.get("expires_in", 3600)) - 60)
    if session.get("uid"):
        _save(session)
    return session["token"]


# ------------------------------------------------------------------------------ the files in the account
def cloud_files(session, timeout=TIMEOUT) -> dict:
    """{name: {"text", "updated", "device"}} of what the account holds."""
    rows = rest("GET", "user_files", session, params={"user_id": "eq." + session["uid"],
                                                      "select": "name,data,updated,device"}, timeout=timeout)
    return {r["name"]: {"text": r["data"], "updated": float(r.get("updated") or 0), "device": r.get("device", "")}
            for r in rows if r.get("name") in FILES}


def put_file(session, name, text, timeout=TIMEOUT) -> float:
    updated = time.time()
    rest("POST", "user_files", session, params={"on_conflict": "user_id,name"}, prefer="resolution=merge-duplicates",
         json={"user_id": session["uid"], "name": name, "data": text, "updated": updated,
               "device": socket.gethostname(), "version": brand.VERSION_LABEL}, timeout=timeout)
    return updated


# ------------------------------------------------------------------------------ the files here
def _canon(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(text) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _paths(data, change):
    """Every text inside data, through change()."""
    if isinstance(data, dict):              # (keys too: the play counts are kept by the song's path)
        return {(change(k) if isinstance(k, str) else k): _paths(v, change) for k, v in data.items()}
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
        if pending() is not None:                          # made, the code not typed yet
            raise AccountError(MESSAGES["NOT_VERIFIED"], "NOT_VERIFIED")
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
    _still_signed_in(session, timeout)
    try:
        _here(session, timeout)
    except AccountError as e:
        log.info("account: could not say this computer is here: %s", e)
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
