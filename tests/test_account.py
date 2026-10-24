"""👤 The DISO account: signing in and the files that travel between computers. A pretend Firebase stands in
for the real one (no test needs the internet)."""
import json
import os
import time

import pytest

from app import account, backup


class FakeFirebase:
    """Auth + Firestore as far as DISO uses them; the rules: only the owner reaches users/<uid>/..."""

    def __init__(self):
        self.users = {}          # e-mail -> (password, uid)
        self.docs = {}           # uid -> {doc id: fields}
        self.mails = []
        self.refreshes = 0
        self.refused_refresh = None
        self.offline = False

    @staticmethod
    def _refuse(code, status=400):
        raise account.AccountError(*account._message({"error": {"message": code, "status": code}}, status))

    def _session(self, address, uid):
        return {"localId": uid, "email": address, "idToken": "tok-" + uid, "refreshToken": "ref-" + uid,
                "expiresIn": "3600"}

    def __call__(self, method, url, timeout=None, json=None, data=None, headers=None, params=None):
        if self.offline:
            raise account.AccountError("İnternete ulaşamadım. Bağlantını kontrol edip tekrar dene.", "OFFLINE")
        if "accounts:signUp" in url:
            if json["email"] in self.users:
                self._refuse("EMAIL_EXISTS")
            uid = f"u{len(self.users) + 1}"
            self.users[json["email"]] = (json["password"], uid)
            return self._session(json["email"], uid)
        if "accounts:signInWithPassword" in url:
            password, uid = self.users.get(json["email"], (None, None))
            if password != json["password"]:
                self._refuse("INVALID_LOGIN_CREDENTIALS")
            return self._session(json["email"], uid)
        if "accounts:sendOobCode" in url:
            self.mails.append(json["email"])
            return {}
        if url.startswith(account.TOKEN_URL):
            if self.refused_refresh:
                self._refuse(self.refused_refresh)
            self.refreshes += 1
            uid = data["refresh_token"][len("ref-"):]
            return {"id_token": "tok-" + uid, "refresh_token": data["refresh_token"], "expires_in": "3600"}
        assert url.startswith(account.STORE_URL)
        path = url[len(account.STORE_URL):].strip("/").split("/")       # users, uid, files[, doc]
        if headers.get("Authorization") != "Bearer tok-" + path[1]:
            self._refuse("PERMISSION_DENIED", 403)
        files = self.docs.setdefault(path[1], {})
        if method == "GET":
            return {"documents": [{"name": f"projects/p/databases/(default)/documents/users/{path[1]}/files/{d}",
                                   "fields": f} for d, f in files.items()]} if files else {}
        assert method == "PATCH"
        files[path[3]] = json["fields"]
        return {}

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


# ------------------------------------------------------------------------------ signing in
def test_an_account_is_made_kept_encrypted_and_forgotten(cloud):
    assert not account.signed_in()
    account.sign_up("ali@ornek.com", "gizli123")
    assert account.signed_in() and account.email() == "ali@ornek.com"
    with open(account.store_path(), "rb") as f:
        assert b"ref-u1" not in f.read()                       # DPAPI: not readable as it is
    account.sign_out()
    assert not account.signed_in()
    account.sign_in("ali@ornek.com", "gizli123")
    assert account.load()["uid"] == "u1"


@pytest.mark.parametrize("address, password, why", [
    ("ali", "gizli123", "Bu bir e-posta adresine benzemiyor."),
    ("ali@ornek.com", "123", "Şifre en az 6 karakter olmalı."),
])
def test_a_bad_address_or_short_password_is_refused_before_asking(cloud, address, password, why):
    with pytest.raises(account.AccountError, match=why):
        account.sign_up(address, password)
    assert cloud.users == {}


def test_the_servers_answers_are_said_in_plain_words(cloud):
    account.sign_up("ali@ornek.com", "gizli123")
    with pytest.raises(account.AccountError, match="zaten bir hesap var"):
        account.sign_up("ali@ornek.com", "baska123")
    with pytest.raises(account.AccountError, match="E-posta ya da şifre yanlış"):
        account.sign_in("ali@ornek.com", "yanlis99")
    account.reset_password("ali@ornek.com")
    assert cloud.mails == ["ali@ornek.com"]
    assert account._message({"error": {"code": 401, "message": "Request had invalid authentication credentials.",
                                       "status": "UNAUTHENTICATED"}}, 401)[1] == "UNAUTHENTICATED"


def test_an_old_token_is_renewed_and_a_dead_session_signs_out(cloud):
    session = account.sign_up("ali@ornek.com", "gizli123")
    session["expires"] = time.time() - 1
    assert account.token(session) == "tok-u1" and cloud.refreshes == 1
    assert account.load()["expires"] > time.time()
    session["expires"] = time.time() - 1
    cloud.refused_refresh = "TOKEN_EXPIRED"
    with pytest.raises(account.AccountError, match="Oturumun süresi doldu") as e:
        account.token(session)
    assert e.value.code in account.SESSION_GONE and not account.signed_in()


# ------------------------------------------------------------------------------ what goes where
def test_the_plan_for_each_file():
    seen = {"settings.json": {"hash": "a", "updated": 1.0}, "playlists.json": {"hash": "a", "updated": 1.0},
            "channels.json": {"hash": "a", "updated": 1.0}, "history.json": {"hash": "a", "updated": 1.0}}
    local = {"settings.json": "b", "playlists.json": "a", "channels.json": "b", "history.json": "c"}
    cloud = {"settings.json": {"hash": "a", "updated": 1.0}, "playlists.json": {"hash": "b", "updated": 2.0},
             "channels.json": {"hash": "c", "updated": 2.0}, "history.json": {"hash": "c", "updated": 3.0}}
    assert account.plan(local, cloud, seen) == {"settings.json": "up", "playlists.json": "down",
                                                "channels.json": "conflict", "history.json": "same"}
    assert account.plan({"settings.json": "x"}, {"playlists.json": {"hash": "y", "updated": 1.0}}, {}) == \
        {"settings.json": "up", "playlists.json": "down", "channels.json": None, "history.json": None}


def test_two_computers_share_lists_but_each_keeps_its_own_folders(cloud, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    write(a, "settings.json", {"theme": "Açık", "quality": "720p", "folder": "C:\\A", "bridge_port": 1})
    write(a, "playlists.json", {"playlists": {"Gece": ["x.mp3"]}})
    write(a, "channels.json", {"channels": [{"url": "https://youtube.com/@k"}]})
    write(b, "settings.json", {"theme": "Koyu", "folder": "D:\\B", "bridge_port": 2})
    account.sign_up("ali@ornek.com", "gizli123")
    assert sorted(account.sync("up", folder=a)["up"]) == ["channels.json", "playlists.json", "settings.json"]
    assert "folder" not in cloud.text("u1", "settings.json")                    # this computer's own: stays here

    done = account.sync("start", folder=b)
    assert sorted(done["down"]) == ["channels.json", "playlists.json", "settings.json"]
    assert read(b, "settings.json") == {"theme": "Açık", "quality": "720p", "folder": "D:\\B", "bridge_port": 2}
    assert read(b, "playlists.json") == {"playlists": {"Gece": ["x.mp3"]}}
    assert read(b, "settings.json.before-sync") == {"theme": "Koyu", "folder": "D:\\B", "bridge_port": 2}
    assert account.sync("start", folder=b) == {"up": [], "down": [], "waiting": []}      # nothing new
    assert account.sync("up", folder=b)["up"] == []                     # what came in is not sent back


def test_a_change_here_goes_up_and_one_from_elsewhere_waits_for_the_start(cloud, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    write(a, "playlists.json", {"playlists": {"Gece": []}})
    account.sign_up("ali@ornek.com", "gizli123")
    account.sync("up", folder=a)
    account.sync("start", folder=b)
    write(b, "playlists.json", {"playlists": {"Gece": [], "Sabah": []}})
    assert account.sync("up", folder=b)["up"] == ["playlists.json"]
    assert account.sync("up", folder=a)["up"] == []                     # a has nothing new; b's change waits
    assert read(a, "playlists.json") == {"playlists": {"Gece": []}}
    assert account.sync("start", folder=a)["down"] == ["playlists.json"]
    assert read(a, "playlists.json") == {"playlists": {"Gece": [], "Sabah": []}}


def test_sync_now_puts_what_came_in_aside_for_the_next_start(cloud, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    write(a, "channels.json", {"channels": [{"url": "k"}]})
    account.sign_up("ali@ornek.com", "gizli123")
    account.sync("up", folder=a)
    write(b, "channels.json", {"channels": []})
    write(b, "history.json", {"entries": [1]})
    done = account.sync("now", folder=b, prefer="account")
    assert done == {"up": ["history.json"], "down": [], "waiting": ["channels.json"]}
    assert read(b, "channels.json") == {"channels": []}                 # not yet: DISO runs
    assert account.sync("up", folder=b)["up"] == []                     # waiting: nothing old goes up meanwhile
    assert backup.apply_pending(b) == ["channels.json"]
    assert read(b, "channels.json") == {"channels": [{"url": "k"}]}
    assert account.sync("start", folder=b)["down"] == [] and account.sync("up", folder=b)["up"] == []


def test_the_first_sign_in_asks_and_here_can_win(cloud, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    write(a, "settings.json", {"theme": "Açık"})
    account.sign_up("ali@ornek.com", "gizli123")
    account.sync("up", folder=a)
    os.remove(account.state_path(a))
    write(b, "settings.json", {"theme": "Koyu"})
    look = account.peek(folder=b)
    assert look["files"] == ["settings.json"] and look["differ"] == ["settings.json"]
    assert account.sync("now", folder=b, prefer="here")["up"] == ["settings.json"]
    assert json.loads(cloud.text("u1", "settings.json")) == {"theme": "Koyu"}


def test_without_an_account_or_the_internet_nothing_happens(cloud, tmp_path):
    a = str(tmp_path / "a")
    write(a, "settings.json", {"theme": "Açık"})
    assert account.sync("up", folder=a) == {"up": [], "down": [], "waiting": []}
    assert cloud.docs == {}
    account.sign_up("ali@ornek.com", "gizli123")
    cloud.offline = True
    with pytest.raises(account.AccountError, match="İnternete ulaşamadım"):
        account.sync("start", folder=a)
    assert read(a, "settings.json") == {"theme": "Açık"}


def test_another_users_files_are_out_of_reach(cloud):
    account.sign_up("ali@ornek.com", "gizli123")
    session = account.load()
    with pytest.raises(account.AccountError, match="izin vermedi"):
        account.cloud_files({**session, "uid": "u9"})


# ------------------------------------------------------------------------------ the window
def test_the_settings_have_an_account_line_and_the_window_signs_in(app, cloud, monkeypatch):
    from tkinter import messagebox
    app._open_settings()
    panel = app.settings_panel
    assert panel.account_hint.cget("text").startswith("Giriş yap")
    win = app.open_account()
    win.email_entry.insert(0, "ali@ornek.com")
    win.password_entry.insert(0, "gizli123")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: pytest.fail("nothing to ask: the account is empty"))
    win.sign_in(new=True)
    deadline = time.time() + 10
    while (win.busy or not hasattr(win, "sync_btn")) and time.time() < deadline:
        app._drain_ui_calls()
        app.update()
        time.sleep(0.02)
    assert account.signed_in() and not win.busy
    assert panel.account_hint.cget("text").startswith("ali@ornek.com ile giriş yapıldı")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    win.sign_out()
    assert not account.signed_in() and win.sign_in_btn in win.buttons and win.sign_in_btn.winfo_exists()
    win.destroy()
