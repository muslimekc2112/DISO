"""👤 The Google account for YouTube Music: the session taken from DISO's own browser profile, kept
encrypted, the library's lists and their songs, and the window that downloads them (no network here)."""
import os
import time

import pytest

from app import google_account as g


class FakeApi:
    def __init__(self, refuse=0):
        self.refuse = refuse

    def _maybe_refuse(self):
        if self.refuse:
            self.refuse -= 1
            raise Exception("Server returned HTTP 401: Unauthorized")

    def get_account_info(self):
        return {"accountName": "Tuğra", "channelHandle": "@tugra", "accountPhotoUrl": ""}

    def get_library_playlists(self, limit=None):
        self._maybe_refuse()
        return [{"playlistId": "LM", "title": "Liked"}, {"playlistId": "PL1", "title": "Yol", "count": "12"},
                {"playlistId": "PL2", "title": "Spor", "count": None}, {"title": "no id"}]

    def get_playlist(self, playlist_id, limit=None):
        return {"tracks": [{"videoId": "a1", "title": "Gülpembe", "artists": [{"name": "Barış Manço"}]},
                           {"videoId": None, "title": "gone"},
                           {"videoId": "b2", "title": "Dönence", "artists": [{"name": "Barış Manço"}]}]}


# ------------------------------------------------------------------------------ the session
def test_only_youtube_cookies_go_into_the_header():
    cookies = [{"domain": ".youtube.com", "name": "SID", "value": "1"},
               {"domain": "music.youtube.com", "name": g.NEEDED, "value": "x"},
               {"domain": ".google.com", "name": "SID", "value": "other"},
               {"domain": ".youtube.com", "name": "SID", "value": "again"},
               {"domain": "evil-youtube.com", "name": "X", "value": "no"}]
    assert g.cookie_header(cookies) == f"SID=1; {g.NEEDED}=x"


def test_the_session_is_kept_encrypted_and_sign_out_forgets_it():
    data = {"cookie": f"{g.NEEDED}=abc", "agent": "UA", "name": "Tuğra"}
    g.save(data)
    raw = open(g.store_path(), "rb").read()
    assert b"abc" not in raw and "Tuğra".encode() not in raw                  # not readable as it is
    assert g.load() == data and g.signed_in()
    os.makedirs(g.profile_dir(), exist_ok=True)
    g.sign_out()
    assert g.load() is None and not os.path.exists(g.profile_dir())


def test_the_headers_make_ytmusicapi_use_the_signed_in_website():
    from requests.structures import CaseInsensitiveDict
    from ytmusicapi.auth.auth_parse import determine_auth_type
    from ytmusicapi.auth.types import AuthType
    h = g.headers({"cookie": f"{g.NEEDED}=abc", "agent": "UA/1"})
    assert determine_auth_type(CaseInsensitiveDict(h)) == AuthType.BROWSER
    assert h["origin"] == g.ORIGIN and h["user-agent"] == "UA/1"


def test_the_default_browser_is_used_when_it_can_be(monkeypatch):
    found = {"chrome": "chrome.exe", "edge": "edge.exe", "firefox": "firefox.exe"}
    monkeypatch.setattr("app.extension_setup.find_browsers", lambda: found)
    monkeypatch.setattr(g, "default_browser_id", lambda: "chrome")
    assert list(g.usable_browsers()) == ["chrome", "edge"] and g.find_browser() == ("chrome", "chrome.exe")
    assert g.find_browser("edge") == ("edge", "edge.exe")                 # chosen by hand
    monkeypatch.setattr(g, "default_browser_id", lambda: "firefox")         # its cookies cannot be asked for
    assert g.find_browser() == ("chrome", "chrome.exe")
    assert g.profile_dir("chrome") != g.profile_dir("edge")                # each browser its own profile


def test_the_default_browser_is_read_from_windows():
    assert g.default_browser_id() in ("", "chrome", "edge", "firefox", "brave", "vivaldi", "opera")


# ------------------------------------------------------------------------------ the library
def test_the_lists_liked_songs_first_and_their_songs():
    lists = g.playlists(FakeApi())
    assert lists == [{"id": "LM", "title": "Beğendiğim şarkılar", "count": None},
                     {"id": "PL1", "title": "Yol", "count": 12}, {"id": "PL2", "title": "Spor", "count": None}]
    songs = g.tracks(FakeApi(), "PL1")
    assert [s["title"] for s in songs] == ["Gülpembe", "Dönence"] and songs[0]["channel"] == "Barış Manço"
    assert songs[0]["url"].endswith("watch?v=a1")


def _wait(account, what, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        for answer in account.drain():
            if answer[0] == what:
                return answer
        time.sleep(0.02)
    raise AssertionError(f"no answer: {what}")


def test_connecting_waits_for_the_sign_in_window_then_takes_the_session(monkeypatch):
    class Window:
        def __init__(self):
            self.open = True

        def poll(self):
            return None if self.open else 0

        def terminate(self):
            self.open = False

    window = Window()
    monkeypatch.setattr(g, "open_login", lambda exe, *a: window)
    monkeypatch.setattr(g, "read_session", lambda exe, visit=True, **k: {"cookie": f"{g.NEEDED}=s", "agent": "UA"})
    monkeypatch.setattr(g, "client", lambda data=None: FakeApi())
    real_sleep = time.sleep
    monkeypatch.setattr(g.time, "sleep", lambda s: real_sleep(min(s, 0.02)))
    account = g.Account(browser="edge.exe")
    account.connect()
    time.sleep(0.2)
    assert not account.drain() and not account.connected                   # still signing in
    window.open = False                                                     # the user closed the window
    what, info, error = _wait(account, "connected")
    assert error is None and info["name"] == "Tuğra" and account.connected
    assert g.load()["cookie"] == f"{g.NEEDED}=s" and g.load()["handle"] == "@tugra"


def test_a_window_closed_without_signing_in_or_cancelled_is_reported(monkeypatch):
    class Closed:
        def poll(self):
            return 0
    monkeypatch.setattr(g, "open_login", lambda exe, *a: Closed())
    monkeypatch.setattr(g, "read_session", lambda exe, visit=True, **k: {"cookie": "", "agent": "UA"})
    monkeypatch.setattr(g.time, "sleep", lambda s: None)
    account = g.Account(browser="edge.exe")
    account.connect()
    assert isinstance(_wait(account, "connected")[2], PermissionError) and not account.connected


def test_old_cookies_are_renewed_from_the_profile_once(monkeypatch):
    g.save({"cookie": f"{g.NEEDED}=old", "agent": "UA"})
    apis = [FakeApi(refuse=1), FakeApi()]
    used = []
    monkeypatch.setattr(g, "client", lambda data=None: (used.append(data["cookie"]), apis.pop(0))[1])
    monkeypatch.setattr(g, "read_session", lambda exe, visit=True, **k: {"cookie": f"{g.NEEDED}=new", "agent": "UA"})
    account = g.Account(browser="edge.exe")
    account.library()
    what, lists, error = _wait(account, "library")
    assert error is None and len(lists) == 3 and used == [f"{g.NEEDED}=old", f"{g.NEEDED}=new"]
    assert g.load()["cookie"] == f"{g.NEEDED}=new"


def test_a_session_that_cannot_be_renewed_says_signed_out(monkeypatch):
    g.save({"cookie": f"{g.NEEDED}=old", "agent": "UA"})
    monkeypatch.setattr(g, "client", lambda data=None: FakeApi(refuse=5))
    monkeypatch.setattr(g, "read_session", lambda exe, visit=True, **k: {"cookie": "", "agent": "UA"})
    account = g.Account(browser="edge.exe")
    account.library()
    assert isinstance(_wait(account, "library")[2], PermissionError)


# ------------------------------------------------------------------------------ the window
@pytest.fixture
def music(app, monkeypatch):
    from music_support import FakeBackend

    from app import player
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    return app.music


def _pump(win, cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end and not cond():
        win.update()
        time.sleep(0.02)
    return cond()


@pytest.mark.gui
def test_the_window_offers_to_connect_then_lists_and_downloads(music, monkeypatch):
    from app import google_ui
    monkeypatch.setattr(g, "client", lambda data=None: FakeApi())
    account = g.Account(browser="edge.exe")
    win = google_ui.GoogleWindow(music, account=account)
    win.update()
    assert win.connect_btn.winfo_ismapped() and "Şifreni DISO'ya yazmazsın" in win.info.cget("text")
    account.data = {"cookie": f"{g.NEEDED}=s", "name": "Tuğra", "handle": "@tugra"}  # as after signing in
    win._answer("connected", {"name": "Tuğra"}, None)
    assert _pump(win, lambda: len(win.lists) == 3)
    assert win.name_label.cget("text") == "Tuğra" and win.picked_btn.cget("state") == "disabled"
    started = []
    monkeypatch.setattr(music.app, "download_playlist", lambda songs, title: (started.append((title, len(songs))), (len(songs), title))[1])
    win.checks["PL1"].set(True)
    win._update_buttons()
    assert win.picked_btn.cget("text") == "⬇ Seçilenleri indir (1)"
    win.download_picked()
    assert _pump(win, lambda: started)
    assert started == [("Yol", 2)] and "2 şarkı iniyor" in win.info.cget("text")
    started.clear()
    win.download_all()
    assert _pump(win, lambda: len(started) == 3)
    assert [t for t, _ in started] == ["Beğendiğim şarkılar", "Yol", "Spor"]
    monkeypatch.setattr(google_ui.messagebox, "askyesno", lambda *a, **k: True)
    win.sign_out()
    win.update()
    assert not account.connected and win.connect_btn.winfo_ismapped()
    win.destroy()


@pytest.mark.gui
def test_the_music_window_has_the_youtube_music_button(music, monkeypatch):
    from app import google_ui
    real = g.Account
    monkeypatch.setattr(google_ui.google_account, "Account", lambda: real(browser="edge.exe"))
    assert music.google_btn.cget("text") == "👤 YT Music"
    win = music.open_google()
    assert music.open_google() is win
    win.destroy()
