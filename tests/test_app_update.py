"""DISO updating itself: a new version is only announced; "Güncelle" downloads the setup, checks its
SHA-256 and starts it (--update) — Windows asks; a no keeps DISO running."""
import pytest

from app import app_update, brand

LATEST = app_update.latest_release          # the real one (the window tests swap it for one without internet)
SHA = "cc3ef0d84fa9c58f782e7d0e76a8f5c6c0ba53efbf1621f7b099dedfd4e666ef"


class Answer:
    def __init__(self, status=200, data=None, text="", headers=None):
        self.status_code, self._data, self.text, self.headers = status, data, text, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


API = {"tag_name": "v9.1.0", "html_url": "https://github.com/muslimekc2112/DISO/releases/tag/v9.1.0",
       "body": "## 9.1.0\n- yeni şeyler", "assets": [
           {"name": "DISO-9.1-linux-x86_64.deb", "browser_download_url": "https://x/deb", "size": 5, "digest": "sha256:" + "a" * 64},
           {"name": "DISO-Setup-9.1.exe", "browser_download_url": "https://x/setup.exe", "size": 200, "digest": "sha256:" + SHA}]}

PAGE = ('<a href="/muslimekc2112/DISO/releases/download/v9.1.0/DISO-9.1-linux-x86_64.deb">deb</a> sha256:' + "a" * 64 +
        ' sha256:' + "a" * 64 + '<a href="/muslimekc2112/DISO/releases/download/v9.1.0/DISO-Setup-9.1.exe">exe</a>'
        '<span>sha256:' + SHA + '</span><a href="/muslimekc2112/DISO/releases/download/v9.1.0/DISO-browser-extension-9.1.zip">zip</a>')


def github(api_status=200):
    asked = []

    def get(url, **kw):
        asked.append(url)
        if url == app_update.API_URL:
            return Answer(api_status, API if api_status == 200 else {"message": "API rate limit exceeded"})
        if url == app_update.LATEST_URL:
            assert kw.get("allow_redirects") is False
            return Answer(302, headers={"Location": "https://github.com/muslimekc2112/DISO/releases/tag/v9.1.0"})
        if url == app_update.ASSETS_URL.format(tag="v9.1.0"):
            return Answer(text=PAGE)
        raise AssertionError(url)
    get.asked = asked
    return get


# ------------------------------------------------------------------------------ what GitHub says
@pytest.mark.parametrize("tag, version", [("v1.0.2", "1.0.2"), ("1.0", "1.0"), ("v0.11.5-beta", "0.11.5"),
                                          ("nightly", ""), ("", "")])
def test_the_version_of_a_tag(tag, version):
    assert app_update.tag_version(tag) == version


def test_newer_is_compared_as_numbers():
    assert app_update.is_newer("1.0.10", "1.0.9") and app_update.is_newer("2.0", "1.9.9")
    assert not app_update.is_newer("1.0.1", "1.0.1") and not app_update.is_newer("", "1.0")
    assert not app_update.is_newer("1.0", brand.VERSION)


def test_the_api_gives_the_setup_with_its_sha256():
    rel = LATEST(github())
    assert rel["version"] == "9.1.0" and rel["notes"].startswith("## 9.1.0")
    assert app_update.setup_asset(rel["assets"]) == {"name": "DISO-Setup-9.1.exe", "url": "https://x/setup.exe",
                                                     "size": 200, "sha256": SHA}


def test_when_the_api_says_no_the_release_page_tells_the_same():
    get = github(api_status=403)                       # "API rate limit exceeded": 60 an hour per address
    rel = LATEST(get)
    assert get.asked == [app_update.API_URL, app_update.LATEST_URL, app_update.ASSETS_URL.format(tag="v9.1.0")]
    assert rel["version"] == "9.1.0" and rel["page"].endswith("/releases/tag/v9.1.0")
    setup = app_update.setup_asset(rel["assets"])
    assert setup["sha256"] == SHA                     # the SHA-256 right after its own link, not the one before
    assert setup["url"] == "https://github.com/muslimekc2112/DISO/releases/download/v9.1.0/DISO-Setup-9.1.exe"
    zip_file = [a for a in rel["assets"] if a["name"].endswith(".zip")][0]
    assert zip_file["sha256"] == ""                    # none written after it: none


def test_only_the_installed_diso_updates_itself():
    assert app_update.installed_here(frozen=False) is False


# ------------------------------------------------------------------------------ the card
def found(can_install=True, **kw):
    return app_update.AppUpdate(release=lambda: LATEST(github()), can_install=can_install, **kw)


def test_a_new_version_is_announced_and_nothing_is_downloaded():
    downloads = []
    u = found(download=lambda *a: downloads.append(a))
    assert u.check()
    assert u.comp.status == "available" and u.comp.latest == "9.1.0" and "Güncelle" in u.comp.message
    assert u.announce == ("9.1.0", "https://github.com/muslimekc2112/DISO/releases/tag/v9.1.0")
    assert downloads == []


def test_the_same_version_is_current_and_github_unreachable_is_said():
    u = app_update.AppUpdate(release=lambda: {"version": brand.VERSION, "page": "", "notes": "", "assets": []},
                             can_install=True)
    u.check()
    assert u.comp.status == "current" and u.announce is None

    def down():
        raise ConnectionError("ağ yok")
    u = app_update.AppUpdate(release=down, can_install=True)
    u.check()
    assert u.comp.status == "error" and "GitHub'a ulaşamadım" in u.comp.message


def test_update_downloads_checks_and_starts_the_setup(tmp_path):
    got, started = [], []

    def download(url, sha, dest, progress):
        progress(50, 100)
        got.append((url, sha, dest))
        open(dest, "wb").write(b"setup")

    u = found(download=download, start_setup=lambda exe, args: started.append((exe, args)) or True)
    u.check()
    assert u.update() == "started" and u.ready_to_quit
    assert got[0][:2] == ("https://x/setup.exe", SHA) and got[0][2].endswith("DISO-Setup-9.1.exe")
    assert started == [(got[0][2], "--update --launch")]            # silent, shortcuts kept, DISO started again


def test_saying_no_to_windows_keeps_diso_running():
    u = found(download=lambda url, sha, dest, p: open(dest, "wb").close(), start_setup=lambda exe, args: False)
    u.check()
    assert u.update() == "cancelled" and not u.ready_to_quit
    assert u.comp.status == "available" and "izin verilmedi" in u.comp.message


def test_a_failed_download_is_said_and_nothing_starts():
    def broken(*a):
        raise RuntimeError("SHA-256 eşleşmedi, dosya kullanılmadı")
    started = []
    u = found(download=broken, start_setup=lambda *a: started.append(a) or True)
    u.check()
    assert u.update() == "error" and started == [] and "SHA-256" in u.comp.message


def test_a_setup_without_sha256_is_never_run():
    rel = LATEST(github())
    for a in rel["assets"]:
        a["sha256"] = ""
    started = []
    u = app_update.AppUpdate(release=lambda: rel, can_install=True, start_setup=lambda *a: started.append(a) or True,
                             download=lambda *a: None)
    u.check()
    assert u.update() == "page" and started == [] and u.comp.status == "error"


def test_where_diso_cannot_install_itself_the_page_is_opened():
    started = []
    u = found(can_install=False, start_setup=lambda *a: started.append(a) or True)
    u.check()
    assert "sayfasını açar" in u.comp.message and u.update() == "page" and started == []


# ------------------------------------------------------------------------------ in the program
@pytest.mark.gui
def test_the_update_window_has_a_diso_card_first(app):
    app._open_updates()
    panel = app.update_panel
    assert list(panel.cards)[0] == "diso" and panel.cards["diso"].comp is app.app_update.comp


@pytest.mark.gui
def test_a_new_diso_is_told_once_per_version(app, monkeypatch):
    from app import notify
    toasts = []
    monkeypatch.setattr(notify, "toast", lambda title, body: toasts.append(title))
    app.app_update = found()
    app.app_update.check()
    app._announce_app_update()
    app._announce_app_update()
    assert toasts == ["🎉 DISO 9.1.0 çıktı"] and app.cfg.get("update_announced") == "9.1.0"
    app._update_update_widgets()
    assert app.updates_btn.cget("text") == "⟳ Güncellemeler (1)"


@pytest.mark.gui
def test_the_buttons_result_opens_the_page_or_closes_diso(app, monkeypatch):
    import webbrowser
    opened, closed = [], []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(app, "_on_close", lambda: closed.append(True))
    monkeypatch.setattr(app, "after", lambda ms, fn=None: fn() if fn else None)
    app.app_update = found()
    app.app_update.check()
    app._app_update_done("page")
    assert opened == ["https://github.com/muslimekc2112/DISO/releases/tag/v9.1.0"] and closed == []
    app._app_update_done("cancelled")
    assert closed == []
    app._app_update_done("started")
    assert closed == [True]
