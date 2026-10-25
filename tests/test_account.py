"""👤 The DISO account: making one (name, user name, a confirmed e-mail), signing in, the files that travel between
computers and the lists' songs that come after them. A pretend Firebase stands in for the real one (no test needs
the internet); it keeps the real rules: users/<uid> only for its owner with a confirmed e-mail, one owner per user
name."""
import json
import os
import time

import pytest

from app import account, backup, playlists


class FakeFirebase:
    def __init__(self):
        self.users = {}          # e-mail -> {"password", "uid", "verified", "name"}
        self.tokens = {}         # id token -> (uid, verified when it was made)
        self.docs = {}           # uid -> {doc id: fields}
        self.profiles = {}       # uid -> fields
        self.usernames = {}      # name -> uid
        self.devices = {}        # uid -> {device id: fields}
        self.shared = {}         # code -> fields
        self.store = {}          # path -> fields (public cards, friends, requests, inboxes)
        self.sent = []           # (to, kind) of every inbox item
        self.mails = []          # (kind, e-mail)
        self.refused_refresh = None
        self.offline = False
        self.disabled = False

    @staticmethod
    def _refuse(code, status=400, sentence=False):
        err = {"message": f"Some sentence about {code}." if sentence else code, "status": code}
        raise account.AccountError(*account._message({"error": err}, status))

    def _user(self, uid):
        return next(u for u in self.users.values() if u["uid"] == uid)

    def _token(self, uid):
        tok = f"tok-{uid}-{len(self.tokens)}"
        self.tokens[tok] = (uid, self._user(uid)["verified"])
        return tok

    def _session(self, address, uid):
        return {"localId": uid, "email": address, "idToken": self._token(uid), "refreshToken": "ref-" + uid,
                "expiresIn": "3600"}

    def confirm(self, address):          # the user clicked the link in the mail
        self.users[address]["verified"] = True

    def __call__(self, method, url, timeout=None, json=None, data=None, headers=None, params=None):
        if self.offline:
            raise account.AccountError("İnternete ulaşamadım. Bağlantını kontrol edip tekrar dene.", "OFFLINE")
        if url.startswith(account.AUTH_URL):
            what = url[len(account.AUTH_URL):].split("?")[0]
            assert headers["X-Firebase-Locale"] in ("tr", "en")
            if self.disabled and what in ("signUp", "signInWithPassword"):
                self._refuse("PASSWORD_LOGIN_DISABLED")
            if what == "signUp":
                if json["email"] in self.users:
                    self._refuse("EMAIL_EXISTS")
                uid = f"u{len(self.users) + 1}"
                self.users[json["email"]] = {"password": json["password"], "uid": uid, "verified": False, "name": ""}
                return self._session(json["email"], uid)
            if what == "signInWithPassword":
                user = self.users.get(json["email"])
                if not user or user["password"] != json["password"]:
                    self._refuse("INVALID_LOGIN_CREDENTIALS")
                return self._session(json["email"], user["uid"])
            uid = self.tokens[json["idToken"]][0] if "idToken" in json else None
            if what == "lookup":
                return {"users": [{"localId": uid, "emailVerified": self._user(uid)["verified"]}]}
            if what == "update":
                self._user(uid)["name"] = json["displayName"]
                return {}
            if what == "delete":
                address = next(a for a, u in self.users.items() if u["uid"] == uid)
                del self.users[address]
                return {}
            if what == "sendOobCode":
                if json["requestType"] == "VERIFY_EMAIL":
                    self.mails.append(("verify", next(a for a, u in self.users.items() if u["uid"] == uid)))
                else:
                    self.mails.append(("reset", json["email"]))
                return {}
            raise AssertionError(what)
        if url.startswith(account.TOKEN_URL):
            if self.refused_refresh:
                self._refuse(self.refused_refresh)
            uid = data["refresh_token"][len("ref-"):]
            return {"id_token": self._token(uid), "refresh_token": data["refresh_token"], "expires_in": "3600"}
        assert url.startswith(account.STORE_URL)
        path = url[len(account.STORE_URL):].strip("/").split("/")
        uid, verified = self.tokens.get((headers or {}).get("Authorization", "")[len("Bearer "):], (None, False))
        if path[0] == "shared":                                    # 🔗 shared lists: anyone reads, the owner makes
            if method == "DELETE":
                return self._social(method, path, uid, verified, json, params)
            if method == "GET":
                if path[1] not in self.shared:
                    self._refuse("NOT_FOUND", 404, sentence=True)
                return {"fields": self.shared[path[1]]}
            if not verified or json["fields"]["owner"]["stringValue"] != uid:
                self._refuse("PERMISSION_DENIED", 403, sentence=True)
            if params["documentId"] in self.shared:
                self._refuse("ALREADY_EXISTS", 409, sentence=True)
            self.shared[params["documentId"]] = json["fields"]
            return {}
        if path == ["usernames"]:                                  # create usernames/<documentId>
            if uid is None or json["fields"]["uid"]["stringValue"] != uid:
                self._refuse("PERMISSION_DENIED", 403, sentence=True)
            if params["documentId"] in self.usernames:
                self._refuse("ALREADY_EXISTS", 409, sentence=True)
            self.usernames[params["documentId"]] = uid
            return {}
        social = self._social(method, path, uid, verified, json, params)
        if social is not None:
            return social
        if path[1] != uid or not verified:                         # the rules
            self._refuse("PERMISSION_DENIED", 403, sentence=True)
        if path[2] == "devices":
            devices = self.devices.setdefault(uid, {})
            if len(path) == 3:
                return {"documents": [{"name": f"users/{uid}/devices/{d}", "fields": f}
                                      for d, f in devices.items()]} if devices else {}
            if method == "GET":
                if path[3] not in devices:
                    self._refuse("NOT_FOUND", 404, sentence=True)
                return {"fields": devices[path[3]]}
            if method == "DELETE":
                devices.pop(path[3], None)
                return {}
            mask = [v for k, v in (params or []) if k == "updateMask.fieldPaths"]
            doc = devices.setdefault(path[3], {}) if mask else {}
            doc.update({k: v for k, v in json["fields"].items() if not mask or k in mask})
            devices[path[3]] = doc
            return {}
        if path[2] == "info":
            if method == "DELETE":
                self.profiles.pop(uid, None)
                return {}
            if method == "GET":
                if uid not in self.profiles:
                    self._refuse("NOT_FOUND", 404, sentence=True)
                return {"fields": self.profiles[uid]}
            self.profiles[uid] = json["fields"]
            return {}
        files = self.docs.setdefault(uid, {})
        if method == "GET":
            return {"documents": [{"name": f"projects/p/databases/(default)/documents/users/{uid}/files/{d}",
                                   "fields": f} for d, f in files.items()]} if files else {}
        if method == "DELETE":
            files.pop(path[3], None)
            return {}
        assert method == "PATCH"
        files[path[3]] = json["fields"]
        return {}

    # ---- 👥 public cards, user names, friends, requests, the inbox (with the rules of the real database)
    def _doc(self, path, method, json, params, auto=False):
        key = "/".join(path)
        if method == "GET":
            if key in self.store:
                return {"fields": self.store[key]}
            children = {k: v for k, v in self.store.items() if k.startswith(key + "/") and k.count("/") == key.count("/") + 1}
            if len(path) % 2 == 1:                                 # a collection
                return {"documents": [{"name": k, "fields": v} for k, v in children.items()]} if children else {}
            self._refuse("NOT_FOUND", 404, sentence=True)
        if method == "DELETE":
            self.store.pop(key, None)
            return {}
        if method == "POST":
            doc_id = (dict(params or {}).get("documentId") if isinstance(params, (dict, list)) else None) or                 f"auto{len(self.store)}"
            self.store[f"{key}/{doc_id}"] = json["fields"]
            return {}
        mask = [v for k, v in (params or []) if k == "updateMask.fieldPaths"] if isinstance(params, list) else []
        doc = dict(self.store.get(key, {})) if mask else {}
        doc.update({k: v for k, v in json["fields"].items() if not mask or k in mask})
        self.store[key] = doc
        return {}

    def _social(self, method, path, uid, verified, json, params):
        deny = lambda: self._refuse("PERMISSION_DENIED", 403, sentence=True)   # noqa: E731
        if path[0] == "public":
            if uid is None or (method != "GET" and path[1] != uid):
                deny()
            return self._doc(path, method, json, params)
        if path[0] == "usernames" and len(path) == 2:
            if uid is None or (method == "DELETE" and self.usernames.get(path[1]) != uid):
                deny()
            if method == "DELETE":
                self.usernames.pop(path[1], None)
                return {}
            if path[1] not in self.usernames:
                self._refuse("NOT_FOUND", 404, sentence=True)
            return {"fields": {"uid": {"stringValue": self.usernames[path[1]]}}}
        if path[0] == "shared" and method == "DELETE":
            if self.shared.get(path[1], {}).get("owner", {}).get("stringValue") != uid:
                deny()
            self.shared.pop(path[1], None)
            return {}
        if path[0] == "users" and len(path) >= 3 and path[2] in ("friends", "outgoing", "inbox", "shares"):
            owner = path[1]
            if path[2] == "inbox" and method == "POST" and owner != uid:
                f = json["fields"]
                kind, sender = f["type"]["stringValue"], f["from"]["stringValue"]
                ok = verified and sender == uid and (
                    kind == "request" or f"users/{owner}/friends/{uid}" in self.store
                    or f"users/{owner}/outgoing/{uid}" in self.store)   # (they asked me: I may answer, then talk)
                if not ok:
                    deny()
                self.sent.append((owner, kind))
                return self._doc(path, method, json, params)
            if owner != uid or not verified:
                deny()
            return self._doc(path, method, json, params)
        return None

    def text(self, uid, name):
        return self.docs[uid][name[:-len(".json")]]["data"]["stringValue"]


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeFirebase()
    monkeypatch.setattr(account, "_call", fake)
    return fake


def write(folder, name, data):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        json.dump(data, f)


def read(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8") as f:
        return json.load(f)


def ready(cloud, address="ali@gmail.com", username="ali"):
    """An account made and confirmed."""
    account.sign_up("Ali", "Yılmaz", username, address, "gizli123")
    cloud.confirm(address)
    assert account.check_verified()
    return account.load()


# ------------------------------------------------------------------------------ making an account
def test_an_account_counts_only_after_its_e_mail_is_confirmed(cloud):
    account.sign_up("Ali", "Yılmaz", "Ali", "ali@gmail.com", "gizli123")
    assert cloud.mails == [("verify", "ali@gmail.com")] and cloud.usernames == {"ali": "u1"}
    assert cloud.users["ali@gmail.com"]["name"] == "Ali Yılmaz"
    assert account.waiting() and not account.signed_in()
    assert account.sync("up") == {"up": [], "down": [], "waiting": []}              # nothing travels yet
    with pytest.raises(account.AccountError, match="henüz doğrulanmadı"):
        account.peek()
    assert account.check_verified() is False                                       # not clicked yet
    account.send_verification()
    assert cloud.mails[-1] == ("verify", "ali@gmail.com")
    cloud.confirm("ali@gmail.com")
    assert account.check_verified() and account.signed_in() and not account.waiting()
    assert account.display_name() == "Ali Yılmaz" and account.profile()["username"] == "ali"
    assert cloud.profiles["u1"]["username"] == {"stringValue": "ali"}               # kept in the account
    with open(account.store_path(), "rb") as f:
        assert b"ref-u1" not in f.read()                                           # DPAPI


def test_a_taken_user_name_takes_the_half_made_account_back(cloud):
    ready(cloud)
    account.sign_out()
    with pytest.raises(account.AccountError, match="kullanıcı adı alınmış"):
        account.sign_up("Veli", "Kaya", "ali", "veli@gmail.com", "gizli123")
    assert "veli@gmail.com" not in cloud.users and not account.waiting() and not account.signed_in()


@pytest.mark.parametrize("fields, why", [
    (("", "Kaya", "veli", "veli@gmail.com", "gizli123"), "Adını ve soyadını yaz."),
    (("Veli", "Kaya", "v", "veli@gmail.com", "gizli123"), "Kullanıcı adı 3–20 karakter"),
    (("Veli", "Kaya", "veli kaya", "veli@gmail.com", "gizli123"), "Kullanıcı adı 3–20 karakter"),
    (("Veli", "Kaya", "veli", "veli", "gizli123"), "e-posta adresine benzemiyor"),
    (("Veli", "Kaya", "veli", "veli@gmail.com", "123"), "en az 6 karakter"),
])
def test_wrong_details_are_refused_before_asking(cloud, fields, why):
    with pytest.raises(account.AccountError, match=why):
        account.sign_up(*fields)
    assert cloud.users == {}


def test_signing_in_elsewhere_brings_the_name_and_a_closed_door_is_said_plainly(cloud):
    ready(cloud)
    account.sign_out()
    with pytest.raises(account.AccountError, match="E-posta ya da şifre yanlış"):
        account.sign_in("ali@gmail.com", "yanlis99")
    account.sign_in("ali@gmail.com", "gizli123")
    assert account.signed_in() and account.display_name() == "Ali Yılmaz"
    account.reset_password("ali@gmail.com")
    assert cloud.mails[-1] == ("reset", "ali@gmail.com")
    account.sign_out()
    cloud.disabled = True
    with pytest.raises(account.AccountError, match="e-postayla giriş kapalı"):
        account.sign_in("ali@gmail.com", "gizli123")


def test_an_unconfirmed_account_signs_in_as_waiting(cloud):
    account.sign_up("Ali", "Yılmaz", "ali", "ali@gmail.com", "gizli123")
    account.sign_out()
    account.sign_in("ali@gmail.com", "gizli123")
    assert account.waiting() and not account.signed_in()


def test_an_old_token_is_renewed_and_a_dead_session_signs_out(cloud):
    session = ready(cloud)
    session["expires"] = time.time() - 1
    assert account.token(session).startswith("tok-u1")
    session["expires"] = time.time() - 1
    cloud.refused_refresh = "TOKEN_EXPIRED"
    with pytest.raises(account.AccountError, match="Oturumun süresi doldu") as e:
        account.token(session)
    assert e.value.code in account.SESSION_GONE and not account.signed_in()


def test_firestores_sentences_are_read_by_their_status():
    assert account._message({"error": {"message": "Document already exists: x", "status": "ALREADY_EXISTS"}},
                            409)[1] == "ALREADY_EXISTS"
    assert account._message({"error": {"message": "INVALID_LOGIN_CREDENTIALS", "status": "INVALID_ARGUMENT"}},
                            400)[1] == "INVALID_LOGIN_CREDENTIALS"


# ------------------------------------------------------------------------------ what goes where
def test_the_plan_for_each_file():
    seen = {n: {"hash": "a", "updated": 1.0} for n in account.FILES}
    local = {"settings.json": "b", "playlists.json": "a", "channels.json": "b", "history.json": "c"}
    cloud = {"settings.json": {"hash": "a", "updated": 1.0}, "playlists.json": {"hash": "b", "updated": 2.0},
             "channels.json": {"hash": "c", "updated": 2.0}, "history.json": {"hash": "c", "updated": 3.0}}
    assert account.plan(local, cloud, seen) == {"settings.json": "up", "playlists.json": "down",
                                                "channels.json": "conflict", "history.json": "same",
                                                "social.json": None}


def test_two_computers_share_lists_but_each_keeps_its_own_folders(cloud, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    write(a, "settings.json", {"theme": "Açık", "quality": "720p", "folder": "C:\\A", "bridge_port": 1})
    write(a, "channels.json", {"channels": [{"url": "https://youtube.com/@k"}]})
    write(b, "settings.json", {"theme": "Koyu", "folder": "D:\\B", "bridge_port": 2})
    ready(cloud)
    assert sorted(account.sync("up", folder=a)["up"]) == ["channels.json", "settings.json"]
    assert "folder" not in cloud.text("u1", "settings.json")
    done = account.sync("start", folder=b)
    assert sorted(done["down"]) == ["channels.json", "settings.json"]
    assert read(b, "settings.json") == {"theme": "Açık", "quality": "720p", "folder": "D:\\B", "bridge_port": 2}
    assert read(b, "settings.json.before-sync") == {"theme": "Koyu", "folder": "D:\\B", "bridge_port": 2}
    assert account.sync("start", folder=b) == {"up": [], "down": [], "waiting": []}
    assert account.sync("up", folder=b)["up"] == []


def test_songs_point_into_each_computers_music_folder_and_wait_there_until_they_come(cloud, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    song_a = os.path.join(a, account.MUSIC_DIR_NAME, "Tarkan - Kuzu Kuzu.mp3")
    os.makedirs(os.path.dirname(song_a))
    open(song_a, "wb").close()
    elsewhere = "E:\\Arşiv\\eski.mp3"
    write(a, "playlists.json", {"playlists": {"Gece": [{"path": song_a, "title": "Kuzu Kuzu"},
                                                       {"path": elsewhere, "title": "eski"}]},
                                "state": {"resume_path": song_a}})
    ready(cloud)
    account.sync("up", folder=a)
    sent = json.loads(cloud.text("u1", "playlists.json"))
    assert sent["playlists"]["Gece"][0]["path"] == account.MUSIC_MARK + os.sep + "Tarkan - Kuzu Kuzu.mp3"
    assert sent["state"]["resume_path"].startswith(account.MUSIC_MARK)
    account.sync("start", folder=b)
    came = read(b, "playlists.json")["playlists"]["Gece"]
    assert came[0]["path"] == os.path.join(b, account.MUSIC_DIR_NAME, "Tarkan - Kuzu Kuzu.mp3")
    assert came[0]["away"] is True and came[1] == {"path": elsewhere, "title": "eski", "away": True}
    store = playlists.PlaylistStore(os.path.join(b, "playlists.json"))
    assert store.missing_paths() == set()                       # waiting songs are not "deleted"
    assert account.sync("up", folder=b)["up"] == []             # and the mark never travels back
    new = os.path.join(b, account.MUSIC_DIR_NAME, "Kuzu Kuzu (Official).mp3")
    os.makedirs(os.path.dirname(new), exist_ok=True)
    open(new, "wb").close()
    assert store.rename_paths([(came[0]["path"], new)]) == 1    # downloaded again: in its place
    assert store.tracks("Gece")[0]["path"] == new and "away" not in store.tracks("Gece")[0]


def test_sync_now_puts_what_came_in_aside_for_the_next_start(cloud, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    write(a, "channels.json", {"channels": [{"url": "k"}]})
    ready(cloud)
    account.sync("up", folder=a)
    write(b, "channels.json", {"channels": []})
    write(b, "history.json", {"entries": [1]})
    assert account.first_time(b)
    done = account.sync("now", folder=b, prefer="account")
    assert done == {"up": ["history.json"], "down": [], "waiting": ["channels.json"]} and not account.first_time(b)
    assert read(b, "channels.json") == {"channels": []}
    assert account.sync("up", folder=b)["up"] == []
    assert backup.apply_pending(b) == ["channels.json"]
    assert read(b, "channels.json") == {"channels": [{"url": "k"}]}
    assert account.sync("start", folder=b)["down"] == [] and account.sync("up", folder=b)["up"] == []


def test_the_first_sign_in_can_keep_this_computers_data(cloud, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    write(a, "settings.json", {"theme": "Açık"})
    write(a, "playlists.json", {"playlists": {"Gece": [{"path": "x.mp3", "title": "x"}]}})
    ready(cloud)
    account.sync("up", folder=a)
    write(b, "settings.json", {"theme": "Koyu"})
    look = account.peek(folder=b)
    assert look["differ"] == ["settings.json"] and look["songs"] == 1
    assert account.sync("now", folder=b, prefer="here")["up"] == ["settings.json"]
    assert json.loads(cloud.text("u1", "settings.json")) == {"theme": "Koyu"}


def test_the_songs_are_asked_for_once_after_the_restart(tmp_path):
    assert not account.take_redownload(str(tmp_path))
    account.ask_redownload(str(tmp_path))
    assert account.take_redownload(str(tmp_path)) and not account.take_redownload(str(tmp_path))


def test_without_the_internet_nothing_changes(cloud, tmp_path):
    a = str(tmp_path / "a")
    write(a, "settings.json", {"theme": "Açık"})
    ready(cloud)
    cloud.offline = True
    with pytest.raises(account.AccountError, match="İnternete ulaşamadım"):
        account.sync("start", folder=a)
    assert read(a, "settings.json") == {"theme": "Açık"}


def test_another_users_files_are_out_of_reach(cloud):
    session = ready(cloud)
    with pytest.raises(account.AccountError, match="izin vermedi"):
        account.cloud_files({**session, "uid": "u9"})


# ------------------------------------------------------------------------------ the windows
def run_until(app, done, seconds=10):
    deadline = time.time() + seconds
    while not done() and time.time() < deadline:
        app._drain_ui_calls()
        app.update()
        time.sleep(0.02)
    assert done()


def test_making_an_account_in_the_window_then_confirming_it(app, cloud):
    assert app.account_btn.cget("text") == "👤 Giriş yap"
    win = app.open_account("signup")
    assert win.page == "signup"
    for entry, text in [(win.first_entry, "Ali"), (win.last_entry, "Yılmaz"), (win.username_entry, "ali"),
                        (win.email_entry, "ali@gmail.com"), (win.password_entry, "gizli123"),
                        (win.password2_entry, "gizli124")]:
        entry.insert(0, text)
    win.sign_up()
    assert "aynı değil" in win.status.cget("text") and cloud.users == {}
    win.password2_entry.delete(0, "end")
    win.password2_entry.insert(0, "gizli123")
    win.sign_up()
    run_until(app, lambda: win.page == "verify" and not win.busy)
    assert app.account_btn.cget("text") == "👤 Doğrula"
    win.verified()
    run_until(app, lambda: not win.busy)
    assert win.page == "verify" and "henüz doğrulanmadı" in win.status.cget("text")
    cloud.confirm("ali@gmail.com")
    win.verified()
    run_until(app, lambda: win.page == "account" and not win.busy)
    assert app.account_btn.cget("text") == "👤 Ali Yılmaz"
    win.destroy()


def test_the_first_sign_in_on_a_new_computer_brings_the_data_and_the_songs(app, cloud, monkeypatch):
    from app import account_ui
    other = ready(cloud)
    song = account.MUSIC_MARK + os.sep + "Sezen Aksu - Firuze.mp3"
    account.put_file(other, "playlists.json", json.dumps({"playlists": {"Eski": [{"path": song, "title": "Firuze"}]}}))
    account.sign_out()
    monkeypatch.setattr(app, "restart_for_account", lambda: restarts.append(1))
    monkeypatch.setattr(account_ui.messagebox, "askyesno", lambda *a, **k: True)
    restarts = []
    win = app.open_account()
    assert win.page == "signin"
    win.email_entry.insert(0, "ali@gmail.com")
    win.password_entry.insert(0, "gizli123")
    win.sign_in()
    run_until(app, lambda: win.page == "first" and not win.busy)
    assert win.songs_var.get() is True and win.choice.get() == "account"
    win.first_go()
    run_until(app, lambda: restarts)
    assert account.take_redownload()                                # the songs come after the restart
    assert backup.apply_pending() == ["playlists.json"]
    win.destroy()


def test_away_songs_are_looked_up_and_take_their_old_place(app, monkeypatch, tmp_path):
    from app import music_search, utils
    data = utils.app_data_dir()
    away = os.path.join(data, account.MUSIC_DIR_NAME, "Sezen Aksu - Firuze.mp3")
    write(data, "playlists.json", {"playlists": {"Eski": [{"path": away, "title": "Sezen Aksu - Firuze",
                                                          "away": True}]}})
    app.playlist_store = None
    assert [p for p, _ in app.away_songs()] == [away]
    monkeypatch.setattr(music_search, "search", lambda title, artist="", limit=0: [{"url": "https://y/1"}])
    added = []
    monkeypatch.setattr(app.manager, "add_song", lambda url, title, s, origin="music": added.append(
        type("It", (), {"url": url, "origin": origin, "group": ""})()) or added[-1])
    assert app.download_away_songs() == 1
    run_until(app, lambda: added)
    assert added[0].url == "https://y/1" and added[0].origin == "music-restore" and added[0].group == away
    new = tmp_path / "Firuze.mp3"
    new.write_bytes(b"x")
    done = type("It", (), {"group": away, "final_path": str(new), "url": "https://y/1", "title": "Firuze"})()
    monkeypatch.setattr(app, "_find_song_lyrics", lambda items: None)          # (no lyrics from the internet)
    app._songs_back_in_place([done])
    assert app._store().tracks("Eski")[0]["path"] == str(new) and not app.away_songs()


def test_the_offer_at_start_until_dont_show_again(app):
    from app import account_ui
    app.cfg.set("account_ask", True)
    app.deiconify()
    app._maybe_offer_account()
    offer = app.account_offer
    assert isinstance(offer, account_ui.AccountOffer)
    offer.never_btn.invoke()
    assert app.cfg.get("account_ask") is False and not offer.winfo_exists()
    app.account_offer = None
    app._maybe_offer_account()
    assert app.account_offer is None
    app.withdraw()


# ------------------------------------------------------------------------------ 💻 the computers of the account
def test_each_computer_is_listed_and_can_be_signed_out_from_another(cloud, monkeypatch, tmp_path):
    ready(cloud)
    me = account.device_id()
    assert account.device_id() == me                                    # the same computer stays the same
    assert [d["this"] for d in account.devices()] == [True]
    other = "laptop-123"                                                # another computer of the account
    cloud.devices["u1"][other] = {"name": {"stringValue": "LAPTOP"}, "seen": {"doubleValue": 1.0}}
    found = account.devices()
    assert [d["name"] for d in found][1:] == ["LAPTOP"] and found[0]["this"]
    account.sign_out_device(other)
    assert [d["id"] for d in account.devices()] == [me]                  # signed out: not listed any more
    # and this computer, signed out from elsewhere, forgets the account at its next sync
    cloud.devices["u1"][me]["signed_out"] = {"booleanValue": True}
    with pytest.raises(account.AccountError, match="başka bir bilgisayardan çıkarıldı") as e:
        account.sync("up", folder=str(tmp_path))
    assert e.value.code == "REMOVED" and not account.signed_in() and account.take_removed()
    assert not account.take_removed()                                   # said once
    account.sign_in("ali@gmail.com", "gizli123")                         # signing in again: listed again
    assert account.signed_in() and [d["id"] for d in account.devices()] == [me]
    assert account.sync("up", folder=str(tmp_path)) is not None          # a sync keeps the mark as it is


def test_signing_out_here_takes_this_computer_off_the_list(cloud):
    ready(cloud)
    assert account.device_id() in cloud.devices["u1"]
    account.leave()
    assert not account.signed_in() and cloud.devices["u1"] == {}


# ------------------------------------------------------------------------------ 🔗 a playlist sent to a friend
def test_a_code_is_read_however_it_is_written():
    from app import sharing
    assert sharing.clean_code("k7p2-qm4x") == sharing.clean_code(" K7P2 QM4X ") == "K7P2QM4X"
    assert sharing.clean_code("diso:liste?K7P2-QM4X") == "K7P2QM4X" and sharing.is_link("diso:liste?K7P2-QM4X")
    assert sharing.clean_code("K7P2-QM40") is None                       # 0 is never in a code (O / 0)
    assert sharing.clean_code("abc") is None and sharing.clean_code("") is None
    code = sharing.new_code()
    assert len(code) == 8 and sharing.clean_code(sharing.link(code)) == code


def test_a_list_is_shared_by_its_owner_and_opened_by_anyone(cloud, monkeypatch):
    from app import sharing
    songs = [{"title": "Firuze", "artist": "Sezen Aksu", "url": "https://youtube.com/watch?v=1"},
             {"title": "bulunamadı", "artist": "", "url": ""}]
    with pytest.raises(account.AccountError, match="giriş yapılmamış"):
        sharing.share("Gece", songs)                                     # sending needs an account
    ready(cloud)
    codes = iter(["AAAA2222", "AAAA2222", "BBBB3333"])
    monkeypatch.setattr(sharing, "new_code", lambda: next(codes))
    assert sharing.share("Gece", songs) == "AAAA2222"
    assert sharing.share("Sabah", songs) == "BBBB3333"                   # a taken code: another one
    account.sign_out()                                                   # opening needs no account
    got = sharing.fetch("AAAA2222")
    assert got["name"] == "Gece" and got["by"] == "Ali Yılmaz" and [s["title"] for s in got["songs"]] == ["Firuze"]
    with pytest.raises(account.AccountError, match="Bu kodla paylaşılmış bir liste yok"):
        sharing.fetch("ZZZZ9999")


def test_a_shared_link_opens_the_list_window_and_its_songs_come(app, cloud, monkeypatch):
    from app import associations, sharing
    assert associations.links_from_argv(["diso:liste?AAAA-2222"]) == ["diso:liste?AAAA-2222"]
    cloud.shared["AAAA2222"] = {"name": {"stringValue": "Gece"}, "by": {"stringValue": "Ali"},
                                "songs": {"stringValue": json.dumps([{"title": "Firuze", "url": "https://y/1"}])}}
    taken = []
    monkeypatch.setattr(app, "download_playlist", lambda results, title: taken.append((results, title)) or (1, title))
    monkeypatch.setattr(app, "_switch_mode", lambda mode: None)
    app.add_urls(["diso:liste?AAAA-2222"])                               # (as a click on the link brings it)
    win = app.open_shared_window
    run_until(app, lambda: win.shared is not None)
    assert "Gece" in win.info.cget("text") and win.take_btn.cget("state") == "normal"
    win.take()
    assert taken == [([{"url": "https://y/1", "title": "Firuze"}], "Gece")] and not win.winfo_exists()


def test_sending_a_list_finds_its_songs_links(app, cloud, monkeypatch, tmp_path):
    from app import music_search
    ready(cloud)
    song = tmp_path / "Sezen Aksu - Firuze.mp3"
    song.write_bytes(b"x")
    other = tmp_path / "Tarkan - Kuzu Kuzu.mp3"
    other.write_bytes(b"x")
    app.history.entries.append({"path": str(song), "url": "https://youtube.com/watch?v=firuze"})
    monkeypatch.setattr(music_search, "search", lambda title, artist="", limit=0: [{"url": "https://y/kuzu"}])
    name = app.new_music_list("Gece")
    app._store().add(name, [str(song), str(other)])
    win = app.share_list(name)
    run_until(app, lambda: win.code is not None)
    shared = list(cloud.shared.values())[0]
    urls = [s["url"] for s in json.loads(shared["songs"]["stringValue"])]
    assert urls == ["https://youtube.com/watch?v=firuze", "https://y/kuzu"]
    assert win.code_label.cget("text") == win.code[:4] + "-" + win.code[4:]
    win.destroy()
