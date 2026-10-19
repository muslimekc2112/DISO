"""Putting the extension into the user's browsers: finding them, the extension's folder, the guide window."""
import os

import pytest

from app import extension_setup as es

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_browsers_are_found_through_app_paths_or_where_they_usually_are():
    places = {r"C:\PF\Google\Chrome\Application\chrome.exe", r"C:\Local\BraveSoftware\Brave-Browser\Application\brave.exe",
              r"D:\Firefox\firefox.exe"}
    app_paths = {"firefox.exe": r"D:\Firefox\firefox.exe", "msedge.exe": r"C:\gone\msedge.exe"}
    found = es.find_browsers(app_path=app_paths.get, exists=places.__contains__,
                             environ={"ProgramFiles": r"C:\PF", "ProgramFiles(x86)": r"C:\PF86", "LOCALAPPDATA": r"C:\Local"})
    assert found == {"chrome": r"C:\PF\Google\Chrome\Application\chrome.exe",
                     "brave": r"C:\Local\BraveSoftware\Brave-Browser\Application\brave.exe",
                     "firefox": r"D:\Firefox\firefox.exe"}                  # Edge's App Paths entry leads nowhere
    assert list(found) == [b for b in ("chrome", "brave", "firefox")]        # in the order of the list


def test_every_browser_has_a_name_a_button_and_an_extensions_page():
    for bid, name, exe, page in es.BROWSERS:
        assert name and exe.endswith(".exe") and es.ADD_TO[bid].endswith("ekle")
        assert page.endswith(("extensions/", "extensions", "this-firefox"))


def test_an_installed_diso_uses_the_extension_next_to_it(tmp_path):
    beside = tmp_path / "DISO" / "browser_extension"
    beside.mkdir(parents=True)
    (beside / "manifest.json").write_text("{}")
    assert es.extension_folder(frozen=True, executable=str(tmp_path / "DISO" / "DISO.exe")) == str(beside)


def test_from_source_the_projects_own_folder_is_used():
    assert os.path.samefile(es.extension_folder(frozen=False), os.path.join(ROOT, "browser_extension"))


def test_a_portable_exe_copies_its_extension_somewhere_that_stays_and_keeps_it_current(tmp_path):
    bundled = tmp_path / "MEI" / "browser_extension"
    bundled.mkdir(parents=True)
    (bundled / "manifest.json").write_text('{"version": "1"}')
    (bundled / "lib.js").write_text("one")
    data = tmp_path / "data"
    got = es.extension_folder(data_dir=str(data), frozen=True, executable=str(tmp_path / "x" / "DISO.exe"),
                              bundled=str(bundled))
    assert got == str(data / "browser_extension") and (data / "browser_extension" / "lib.js").read_text() == "one"
    (bundled / "manifest.json").write_text('{"version": "2"}')                  # a newer DISO.exe brings a newer one
    (bundled / "lib.js").write_text("two")
    es.extension_folder(data_dir=str(data), frozen=True, executable=str(tmp_path / "x" / "DISO.exe"), bundled=str(bundled))
    assert (data / "browser_extension" / "lib.js").read_text() == "two"


def test_opening_a_browser_opens_its_extensions_page_and_the_folder():
    calls = []
    assert es.open_for("edge", r"C:\e\msedge.exe", r"C:\ext", start=lambda exe, args: calls.append((exe, args)))
    assert calls == [(r"C:\e\msedge.exe", ["edge://extensions/"]), ("explorer.exe", [r"C:\ext"])]
    assert es.open_for("chrome", "c.exe", r"C:\ext", start=lambda exe, args: False) is False


@pytest.mark.gui
def test_the_guide_has_a_button_per_browser_and_copies_the_folder(app, tmp_path):
    calls = []
    guide = es.ExtensionGuide(app, browsers={"chrome": r"C:\c\chrome.exe", "firefox": r"C:\f\firefox.exe"},
                              folder=str(tmp_path), start=lambda exe, args: calls.append((exe, args)))
    guide.withdraw()
    try:
        assert set(guide.buttons) == {"chrome", "firefox"}
        assert guide.buttons["chrome"].cget("text") == "🧩 Chrome'a ekle"
        guide.buttons["chrome"].invoke()
        assert calls[0] == (r"C:\c\chrome.exe", ["chrome://extensions/"]) and app.clipboard_get() == str(tmp_path)
        assert "panoya kopyalandı" in guide.status.cget("text")
        texts = " ".join(str(w.cget("text")) for w in guide.winfo_children() if isinstance(w, es.ctk.CTkLabel))
        assert "Geliştirici modu" in texts and "about:debugging" in texts                   # Firefox has its own note
    finally:
        guide.destroy()


@pytest.mark.gui
def test_the_settings_button_opens_one_guide(app, monkeypatch, tmp_path):
    monkeypatch.setattr(es, "find_browsers", lambda: {"edge": r"C:\e\msedge.exe"})
    monkeypatch.setattr(es, "extension_folder", lambda: str(tmp_path))
    app.open_extension_guide()
    first = app.extension_guide
    first.withdraw()
    app.open_extension_guide()
    try:
        assert app.extension_guide is first and list(first.buttons) == ["edge"]
    finally:
        first.destroy()

# ------------------------------------------------------------------------------ "shall we add DISO to your browser?"
@pytest.fixture
def asking(app, monkeypatch):
    """The app as on a real PC: a browser is there, and the question is still open."""
    monkeypatch.setattr(es, "find_browsers", lambda: {"chrome": r"C:\c\chrome.exe"})
    app.cfg.set("extension_ask", True)
    monkeypatch.setattr(app, "state", lambda *a: "normal")                # the test window is hidden; a real one is not
    return app


@pytest.mark.gui
def test_the_question_is_asked_only_while_it_makes_sense(asking, monkeypatch):
    import time
    app = asking
    assert app.should_offer_extension()
    app.cfg.set("extension_ask_after", int(time.time()) + 60)              # "remind me later" is not over
    assert not app.should_offer_extension() and app.should_offer_extension(now=time.time() + 120)
    app.cfg.set("extension_ask_after", 0)
    app.cfg.set("bridge_on", False)                                        # links from the browser are switched off
    assert not app.should_offer_extension()
    app.cfg.set("bridge_on", True)
    monkeypatch.setattr(es, "find_browsers", lambda: {})                   # no supported browser on this PC
    assert not app.should_offer_extension()


@pytest.mark.gui
def test_once_the_extension_talks_to_diso_it_is_never_asked_again(asking):
    from app import ui
    ui.BridgeApi(asking).extension_seen()
    assert asking.cfg.get("extension_seen") is True and not asking.should_offer_extension()


@pytest.mark.gui
def test_add_opens_the_guide(asking, monkeypatch):
    opened = []
    monkeypatch.setattr(asking, "open_extension_guide", lambda: opened.append(1))
    asking._maybe_offer_extension()
    offer = asking.extension_offer
    offer.withdraw()
    texts = " ".join(str(w.cget("text")) for w in offer.winfo_children() if isinstance(w, es.ctk.CTkLabel))
    assert "ekleyelim mi?" in texts and "IDM" not in texts
    offer.add_btn.invoke()
    assert opened == [1] and offer.answer == "add" and asking.cfg.get("extension_ask") is True


@pytest.mark.gui
def test_later_asks_again_in_three_days_and_never_means_never(asking):
    import time
    from app import ui
    asking._maybe_offer_extension()
    asking.extension_offer.withdraw()
    asking.extension_offer.later_btn.invoke()
    after = asking.cfg.get("extension_ask_after")
    assert abs(after - (time.time() + ui.EXTENSION_LATER)) < 60 and not asking.should_offer_extension()
    asking.cfg.set("extension_ask_after", 0)
    asking._maybe_offer_extension()
    asking.extension_offer.withdraw()
    asking.extension_offer.never_btn.invoke()
    assert asking.cfg.get("extension_ask") is False and not asking.should_offer_extension()


@pytest.mark.gui
def test_closing_the_question_with_x_means_later(asking):
    asking._maybe_offer_extension()
    offer = asking.extension_offer
    offer.withdraw()
    offer.tk.call(offer.protocol("WM_DELETE_WINDOW"))                     # what the X calls
    assert offer.answer == "later" and asking.cfg.get("extension_ask_after") > 0


@pytest.mark.gui
def test_a_window_started_as_a_tray_icon_is_not_asked(make_app, monkeypatch):
    from app import config
    monkeypatch.setitem(config.DEFAULTS, "extension_ask", True)
    monkeypatch.setattr(es, "find_browsers", lambda: {"chrome": "c.exe"})
    app = make_app(minimized=True)
    app._maybe_offer_extension()                                           # hidden in the tray: it waits for a real start
    assert getattr(app, "extension_offer", None) is None
