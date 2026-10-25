"""👤 The DISO account: making one (name, user name, a confirmed e-mail by a 6 digit code), signing in, a new password,
the files that travel between computers, the lists' songs that come after them, the computers of the account, a
playlist sent with a code. A pretend Supabase stands in for the real one (tests/fake_supabase.py: no test needs the
internet; it keeps the real database's rules)."""
import json
import os
import time

import pytest
from supabase_support import cloud, read, ready, write  # noqa: F401 - the fixture

from app import account, backup, playlists, sharing


# ------------------------------------------------------------------------------ making an account
def test_an_account_counts_only_after_its_code_is_typed(cloud):
    account.sign_up("Ali", "Yılmaz", "Ali", "ali@gmail.com", "gizli123")
    assert cloud.mails[0][:2] == ("signup", "ali@gmail.com") and cloud.uid_of("ali")
    assert account.waiting() and not account.signed_in() and account.email() == "ali@gmail.com"
    assert account.sync("up") == {"up": [], "down": [], "waiting": []}              # nothing travels yet
    with pytest.raises(account.AccountError, match="henüz doğrulanmadı"):
        account.peek()
    with pytest.raises(account.AccountError, match="Kod yanlış"):
        account.verify_code("000000")
    with pytest.raises(account.AccountError, match="6 haneli kodu yaz"):
        account.verify_code("  ")
    account.send_verification()                                                    # a new code
    assert len(cloud.mails) == 2
    session = account.verify_code(" " + cloud.last_code("ali@gmail.com") + " ")
    assert session["verified"] and account.signed_in() and not account.waiting()
    assert account.display_name() == "Ali Yılmaz" and account.profile()["username"] == "ali"
    with open(account.store_path(), "rb") as f:
        assert session["refresh"].encode() not in f.read()                         # DPAPI: not readable as it is
    assert [d["this"] for d in account.devices()] == [True]                        # this computer is listed


def test_a_taken_user_name_or_e_mail_is_said_before_the_mail(cloud):
    ready(cloud)
    account.sign_out()
    with pytest.raises(account.AccountError, match="kullanıcı adı alınmış"):
        account.sign_up("Veli", "Kaya", "ALI", "veli@gmail.com", "gizli123")
    with pytest.raises(account.AccountError, match="zaten bir hesap var"):
        account.sign_up("Veli", "Kaya", "veli", "ali@gmail.com", "gizli123")
    assert len(cloud.mails) == 1 and not account.waiting()


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


def test_signing_in_elsewhere_brings_the_name_and_an_unconfirmed_account_gets_a_new_code(cloud):
    ready(cloud)
    account.sign_out()
    with pytest.raises(account.AccountError, match="E-posta ya da şifre yanlış"):
        account.sign_in("ali@gmail.com", "yanlis99")
    account.sign_in("ali@gmail.com", "gizli123")
    assert account.signed_in() and account.display_name() == "Ali Yılmaz"
    account.sign_out()
    account.sign_up("Veli", "Kaya", "veli", "veli@gmail.com", "gizli123")
    account.sign_out()                                                             # (the code never typed)
    before = len(cloud.mails)
    assert account.sign_in("veli@gmail.com", "gizli123")["verified"] is False
    assert account.waiting() and len(cloud.mails) == before + 1                    # a new code came
    assert account.verify_code(cloud.last_code("veli@gmail.com"))["verified"] and account.signed_in()


def test_a_new_password_with_the_code_from_the_mail(cloud):
    ready(cloud)
    account.sign_out()
    account.reset_password("ali@gmail.com")
    kind, address, code = cloud.mails[-1]
    assert (kind, address) == ("recovery", "ali@gmail.com")
    with pytest.raises(account.AccountError, match="Kod yanlış"):
        account.finish_reset("ali@gmail.com", "999999", "yeni1234")
    with pytest.raises(account.AccountError, match="en az 6 karakter"):
        account.finish_reset("ali@gmail.com", code, "123")
    account.finish_reset("ali@gmail.com", code, "yeni1234")
    assert not account.signed_in()                                                 # (nothing is kept signed in)
    with pytest.raises(account.AccountError, match="E-posta ya da şifre yanlış"):
        account.sign_in("ali@gmail.com", "gizli123")
    assert account.sign_in("ali@gmail.com", "yeni1234")["verified"]


def test_an_old_token_is_renewed_and_a_dead_session_signs_out(cloud):
    session = ready(cloud)
    cloud.expire(session["uid"])
    session["expires"] = time.time() - 1
    assert account.token(session).startswith("tok-")                               # a new one, from the refresh token
    cloud.refresh.clear()
    session["expires"] = time.time() - 1
    with pytest.raises(account.AccountError, match="Oturumun süresi doldu") as e:
        account.token(session)
    assert e.value.code in account.SESSION_GONE and not account.signed_in()


def test_a_session_of_the_old_firebase_accounts_is_no_session(cloud):
    session = ready(cloud)
    assert account.signed_in()
    with open(account.store_path(), "wb") as f:                          # (as the Firebase version saved it)
        f.write(account._dpapi(json.dumps({**session, "backend": 1}).encode("utf-8"), True))
    assert account.load() is None and not account.signed_in()          # (it asks for a new sign-in, nothing crashes)


def test_the_servers_answers_are_said_in_plain_words():
    for body, status, code in [({"error_code": "user_already_exists"}, 422, "EMAIL_EXISTS"),
                               ({"error": "invalid_grant", "error_description": "Invalid login credentials"}, 400,
                                "INVALID_LOGIN_CREDENTIALS"),
                               ({"code": "P0001", "message": "NOT_FRIENDS"}, 400, "NOT_FRIENDS"),
                               ({"code": "42501", "message": "denied"}, 403, "PERMISSION_DENIED"),
                               ({"code": "23505", "message": "dup"}, 409, "ALREADY_EXISTS"),
                               ({"code": "PGRST303", "message": "JWT expired"}, 401, "TOKEN_EXPIRED"),
                               ({"error_code": "otp_expired"}, 403, "BAD_CODE"), ({}, 404, "NOT_FOUND")]:
        assert account._message(body, status)[1] == code


# ------------------------------------------------------------------------------ what goes where
def test_the_plan_for_each_file():
    seen = {n: {"hash": "a", "updated": 1.0} for n in account.FILES}
    local = {"settings.json": "b", "playlists.json": "a", "channels.json": "b", "history.json": "c"}
    there = {"settings.json": {"hash": "a", "updated": 1.0}, "playlists.json": {"hash": "b", "updated": 2.0},
             "channels.json": {"hash": "c", "updated": 2.0}, "history.json": {"hash": "c", "updated": 3.0}}
    assert account.plan(local, there, seen) == {"settings.json": "up", "playlists.json": "down",
                                                "channels.json": "conflict", "history.json": "same"}


def test_two_computers_share_lists_but_each_keeps_its_own_folders(cloud, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    write(a, "settings.json", {"theme": "Açık", "quality": "720p", "folder": "C:\\A", "bridge_port": 1})
    write(a, "channels.json", {"channels": [{"url": "https://youtube.com/@k"}]})
    write(b, "settings.json", {"theme": "Koyu", "folder": "D:\\B", "bridge_port": 2})
    ready(cloud)
    assert sorted(account.sync("up", folder=a)["up"]) == ["channels.json", "settings.json"]
    assert "folder" not in cloud.t["user_files"][0]["data"]
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
    sent = json.loads(cloud.t["user_files"][0]["data"])
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
    assert json.loads(next(r for r in cloud.t["user_files"] if r["name"] == "settings.json")["data"]) == {"theme": "Koyu"}


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


def test_another_persons_files_are_out_of_reach(cloud):
    ready(cloud)
    other = account.load()
    account.sign_out()
    ready(cloud, "veli", "Veli", "Kaya")
    assert account.cloud_files({**account.load(), "uid": other["uid"]}) == {}      # (the rules show nothing)
    with pytest.raises(account.AccountError, match="izin vermedi"):
        account.put_file({**account.load(), "uid": other["uid"]}, "settings.json", "{}")


# ------------------------------------------------------------------------------ 💻 the computers of the account
def test_each_computer_is_listed_and_can_be_signed_out_from_another(cloud, tmp_path):
    ready(cloud)
    me = account.device_id()
    assert account.device_id() == me                                    # the same computer stays the same
    other = "laptop-123"                                                # another computer of the account
    uid = account.load()["uid"]
    cloud.t["devices"].append({"user_id": uid, "device_id": other, "name": "LAPTOP", "seen": account.iso(1.0),
                               "version": "1.6", "signed_out": False})
    found = account.devices()
    assert [d["name"] for d in found][1:] == ["LAPTOP"] and found[0]["this"]
    account.sign_out_device(other)
    assert [d["id"] for d in account.devices()] == [me]                 # signed out: not listed any more
    # and this computer, signed out from elsewhere, forgets the account at its next sync
    next(d for d in cloud.t["devices"] if d["device_id"] == me)["signed_out"] = True
    with pytest.raises(account.AccountError, match="başka bir bilgisayardan çıkarıldı") as e:
        account.sync("up", folder=str(tmp_path))
    assert e.value.code == "REMOVED" and not account.signed_in() and account.take_removed()
    assert not account.take_removed()                                   # said once
    account.sign_in("ali@gmail.com", "gizli123")                         # signing in again: listed again
    assert account.signed_in() and [d["id"] for d in account.devices()] == [me]
    account.sync("up", folder=str(tmp_path))                             # a sync keeps the mark as it is
    assert account.signed_in()


def test_signing_out_here_takes_this_computer_off_the_list(cloud):
    ready(cloud)
    assert account.device_id() in [d["device_id"] for d in cloud.t["devices"]]
    account.leave()
    assert not account.signed_in() and cloud.t["devices"] == []


# ------------------------------------------------------------------------------ 🔗 a playlist sent to a friend
def test_a_code_is_read_however_it_is_written():
    assert sharing.clean_code("k7p2-qm4x") == sharing.clean_code(" K7P2 QM4X ") == "K7P2QM4X"
    assert sharing.clean_code("diso:liste?K7P2-QM4X") == "K7P2QM4X" and sharing.is_link("diso:liste?K7P2-QM4X")
    assert sharing.clean_code("K7P2-QM40") is None                       # 0 is never in a code (O / 0)
    assert sharing.clean_code("abc") is None and sharing.clean_code("") is None
    code = sharing.new_code()
    assert len(code) == 8 and sharing.clean_code(sharing.link(code)) == code


def test_a_list_is_shared_by_its_owner_and_opened_by_anyone(cloud, monkeypatch):
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


# ------------------------------------------------------------------------------ 🗑 deleting the account
def test_deleting_the_account_takes_everything_and_frees_the_name(cloud, tmp_path):
    ready(cloud)
    write(str(tmp_path), "settings.json", {"theme": "Açık"})
    account.sync("up", folder=str(tmp_path))
    sharing.share("Gece", [{"title": "x", "url": "https://y/x"}])
    with pytest.raises(account.AccountError, match="Şifre yanlış"):
        account.delete_account("yanlis99")
    assert account.signed_in()
    account.delete_account("gizli123")
    assert not account.signed_in() and "ali@gmail.com" not in cloud.users
    assert all(rows == [] for rows in cloud.t.values())                  # nothing of it is left
    account.sign_up("Ali", "Yeni", "ali", "ali@gmail.com", "gizli456")   # the name and e-mail are free again


# ------------------------------------------------------------------------------ the windows
def run_until(app, done, seconds=10):
    deadline = time.time() + seconds
    while not done() and time.time() < deadline:
        app._drain_ui_calls()
        app.update()
        time.sleep(0.02)
    assert done()


def test_making_an_account_in_the_window_then_typing_the_code(app, cloud):
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
    win.code_entry.insert(0, "000000")
    win.verified()
    run_until(app, lambda: not win.busy)
    assert win.page == "verify" and "Kod yanlış" in win.status.cget("text")
    win.code_entry.delete(0, "end")
    win.code_entry.insert(0, cloud.last_code("ali@gmail.com"))
    win.verified()
    run_until(app, lambda: win.page == "account" and not win.busy)
    assert app.account_btn.cget("text") == "👤 Ali Yılmaz"
    win.destroy()


def test_a_new_password_in_the_window(app, cloud):
    ready(cloud)
    account.sign_out()
    win = app.open_account("signin")
    win.show("reset")
    assert win.page == "reset"
    win.email_entry.delete(0, "end")
    win.email_entry.insert(0, "ali@gmail.com")
    win.send_reset_code()
    run_until(app, lambda: cloud.mails[-1][0] == "recovery" and not win.busy)
    win.code_entry.insert(0, cloud.mails[-1][2])
    win.password_entry.insert(0, "yeni1234")
    win.finish_reset()
    run_until(app, lambda: win.page == "signin" and not win.busy)
    assert "Şifren değişti" in win.status.cget("text") and account.sign_in("ali@gmail.com", "yeni1234")["verified"]
    win.destroy()


def test_the_first_sign_in_on_a_new_computer_brings_the_data_and_the_songs(app, cloud, monkeypatch):
    from app import account_ui
    other = ready(cloud)
    song = account.MUSIC_MARK + os.sep + "Sezen Aksu - Firuze.mp3"
    account.put_file(other, "playlists.json", json.dumps({"playlists": {"Eski": [{"path": song, "title": "Firuze"}]}}))
    account.sign_out()
    restarts = []
    monkeypatch.setattr(app, "restart_for_account", lambda: restarts.append(1))
    monkeypatch.setattr(account_ui.messagebox, "askyesno", lambda *a, **k: True)
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


def test_a_shared_link_opens_the_list_window_and_its_songs_come(app, cloud, monkeypatch):
    from app import associations
    ready(cloud)
    code = sharing.share("Gece", [{"title": "Firuze", "artist": "", "url": "https://y/1"}])
    account.sign_out()
    assert associations.links_from_argv(["diso:liste?AAAA-2222"]) == ["diso:liste?AAAA-2222"]
    taken = []
    monkeypatch.setattr(app, "download_playlist", lambda results, title: taken.append((results, title)) or (1, title))
    monkeypatch.setattr(app, "_switch_mode", lambda mode: None)
    app.add_urls([sharing.link(code)])                                   # (as a click on the link brings it)
    win = app.open_shared_window
    run_until(app, lambda: win.shared is not None)
    assert "Gece" in win.info.cget("text") and win.take_btn.cget("state") == "normal"
    win.take()
    assert taken == [([{"url": "https://y/1", "title": "Firuze"}], "Gece")] and not win.winfo_exists()
