"""The browser extension: its package, its pure logic (node --test) and its background script
run against a mock browser but talking real HTTP to the app's bridge."""
import json
import os
import re
import shutil
import subprocess

import pytest

from app import __version__, bridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "browser_extension")
JS = os.path.join(ROOT, "tests", "js")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


# ----------------------------------------------------------------------------- package
def manifest():
    with open(os.path.join(EXT, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def test_the_manifest_is_a_valid_manifest_v3_for_chrome_and_firefox():
    m = manifest()
    assert m["manifest_version"] == 3 and m["name"] == "DISO"
    assert m["version"] == __version__                       # extension and app move together
    assert set(m["permissions"]) == {"contextMenus", "downloads", "storage", "cookies", "activeTab"}
    assert "http://127.0.0.1/*" in m["host_permissions"]
    assert m["background"]["service_worker"] == "sw.js"      # Chrome
    assert m["background"]["scripts"] == ["lib.js", "background.js"]   # Firefox
    assert m["browser_specific_settings"]["gecko"]["id"]


def test_every_file_the_manifest_and_pages_mention_exists():
    m = manifest()
    files = [m["background"]["service_worker"], *m["background"]["scripts"], m["action"]["default_popup"],
             m["options_ui"]["page"], *m["icons"].values(), *m["action"]["default_icon"].values()]
    for name in files:
        assert os.path.isfile(os.path.join(EXT, name)), name
    for page in ("popup.html", "options.html"):
        html = open(os.path.join(EXT, page), encoding="utf-8").read()
        for src in re.findall(r'<script src="([^"]+)"', html):
            assert os.path.isfile(os.path.join(EXT, src)), (page, src)
            assert not src.startswith(("http:", "https:", "//")), "no remote code allowed"
    sw = open(os.path.join(EXT, "sw.js"), encoding="utf-8").read()
    assert 'importScripts("lib.js", "background.js")' in sw


def test_the_extension_speaks_turkish_and_english():
    assert manifest()["default_locale"] == "en" and manifest()["description"] == "__MSG_description__"
    for lang in ("en", "tr"):
        with open(os.path.join(EXT, "_locales", lang, "messages.json"), encoding="utf-8") as f:
            assert json.load(f)["description"]["message"]
    lib = open(os.path.join(EXT, "lib.js"), encoding="utf-8").read()
    for page in ("popup.html", "options.html"):
        html = open(os.path.join(EXT, page), encoding="utf-8").read()
        for key in re.findall(r'data-i18n="(\w+)"', html):
            assert lib.count(f"{key}: ") >= 2, (page, key)                                     # in both languages
    for name in ("background.js", "popup.js", "options.js"):
        code = open(os.path.join(EXT, name), encoding="utf-8").read()
        strings = re.findall(r'"([^"\n]*)"', code)
        assert not [s for s in strings if re.search("[çğıöşüÇĞİÖŞÜ]", s)], name    # every text comes from lib.js


def test_the_icons_are_real_pngs_of_the_declared_sizes():
    from PIL import Image
    for size, name in manifest()["icons"].items():
        with Image.open(os.path.join(EXT, name)) as img:
            assert img.format == "PNG" and img.size == (int(size), int(size))


def test_no_page_loads_scripts_from_the_internet_or_uses_eval():
    for name in os.listdir(EXT):
        if name.endswith((".js", ".html")):
            text = open(os.path.join(EXT, name), encoding="utf-8").read()
            assert "eval(" not in text and "new Function(" not in text, name
            assert not re.search(r'<script[^>]+src="https?:', text), name


def test_the_extension_only_talks_to_the_local_app():
    for name in ("background.js", "popup.js", "options.js", "lib.js"):
        text = open(os.path.join(EXT, name), encoding="utf-8").read()
        for url in re.findall(r"https?://[^\s\"'`)]+", text):
            assert "127.0.0.1" in url or "localhost" in url or url.startswith(("http://a.", "https://a.")), (name, url)


def test_the_readme_explains_installation_for_both_browsers():
    text = open(os.path.join(EXT, "README.txt"), encoding="utf-8").read()
    assert "chrome://extensions" in text and "about:debugging" in text and "17653" in text


# --------------------------------------------------------------------------- pure logic
@needs_node
def test_the_pure_logic_passes_its_node_tests():
    r = subprocess.run([NODE, "--test", os.path.join(JS, "lib.test.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "fail 0" in r.stdout


# ----------------------------------------------------------------- background script
class Api:
    def __init__(self):
        self.add_enabled, self.added, self.shown, self.fail = True, [], 0, False

    def add(self, urls, extra, kind):
        if self.fail:
            raise RuntimeError("the app crashed while adding")
        self.added.append({"urls": urls, "extra": extra, "kind": kind})
        return {"added": len(urls), "duplicates": 0}

    def status(self):
        return {"active": 0, "queued": 0, "speed": 0, "total": 0}

    def show(self):
        self.shown += 1


@pytest.fixture
def app():
    api = Api()
    b = bridge.Bridge(api, port=0)
    assert b.start()
    yield api, b
    b.stop()


def run(port, scenario):
    r = subprocess.run([NODE, os.path.join(JS, "harness.js"), str(port), scenario], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert "error" not in data, data
    return data


SESSION = "http://shop.example/files/report.zip"
PAGE = "http://shop.example/page"


@needs_node
def test_the_context_menu_entries_are_created(app):
    api, b = app
    assert run(b.port, "menus")["log"]["menus"] == ["hi-link", "hi-media", "hi-page", "hi-selection"]


@needs_node
def test_a_link_goes_to_the_app_with_the_browsers_session(app):
    api, b = app
    out = run(b.port, "link")
    assert out["answer"]["ok"] is True and out["answer"]["text"] == "1 bağlantı eklendi"
    assert api.added == [{"urls": [SESSION], "kind": None,
                          "extra": {"referer": PAGE, "user_agent": "TestBrowser/1.0", "cookie": "sid=1; theme=dark"}}]
    assert out["log"]["cookiesAsked"] == [SESSION] and out["log"]["badge"] == ["✓"]


@needs_node
def test_a_media_element_is_sent_with_the_page_as_referer(app):
    api, b = app
    run(b.port, "media")
    assert api.added[0]["urls"] == ["http://shop.example/v.mp4"] and api.added[0]["extra"]["referer"] == PAGE
    assert api.added[0]["extra"]["cookie"] == ""


@needs_node
def test_the_page_entry_asks_for_a_video_download_of_the_page(app):
    api, b = app
    run(b.port, "page")
    assert api.added[0]["urls"] == ["http://video.example/watch?v=1"] and api.added[0]["kind"] == "video"
    assert api.added[0]["extra"]["referer"] == ""


@needs_node
def test_selected_text_sends_every_link_once_and_no_cookies(app):
    api, b = app
    run(b.port, "selection")
    assert api.added[0]["urls"] == ["http://a.com/1", "https://b.org/2"]
    assert api.added[0]["extra"]["cookie"] == "" and api.added[0]["extra"]["referer"] == PAGE


@needs_node
def test_a_selection_without_links_sends_nothing(app):
    api, b = app
    out = run(b.port, "empty-selection")
    assert api.added == [] and out["log"]["badge"] == ["?"]


@needs_node
def test_taking_over_a_browser_download(app):
    api, b = app
    out = run(b.port, "intercept")
    assert out["log"]["cancelled"] == [7] and out["log"]["erased"] == [7]      # the browser lets go of it
    assert api.added[0]["urls"] == [SESSION]
    assert api.added[0]["extra"] == {"referer": PAGE, "user_agent": "TestBrowser/1.0", "cookie": "sid=1; theme=dark"}
    assert out["log"]["badge"] == ["✓"] and out["log"]["downloaded"] == []


@needs_node
@pytest.mark.parametrize("scenario", ["intercept-off", "intercept-small", "intercept-blob"])
def test_downloads_that_are_not_ours_stay_with_the_browser(app, scenario):
    api, b = app
    out = run(b.port, scenario)
    assert api.added == [] and out["log"]["cancelled"] == [] and out["log"]["downloaded"] == []


@needs_node
def test_with_the_app_closed_the_browser_keeps_the_download(app):
    api, b = app
    port = b.port
    b.stop()
    out = run(port, "intercept")
    assert out["log"]["cancelled"] == [] and out["log"]["erased"] == [] and out["log"]["downloaded"] == []


@needs_node
def test_with_adding_switched_off_in_the_app_the_browser_keeps_the_download(app):
    api, b = app
    api.add_enabled = False
    out = run(b.port, "intercept")
    assert out["log"]["cancelled"] == [] and api.added == []


@needs_node
def test_a_download_the_app_could_not_take_is_given_back_to_the_browser_once(app):
    api, b = app
    api.fail = True                                   # the app answers /ping but breaks on /add
    out = run(b.port, "intercept")
    assert out["log"]["cancelled"] == [7]             # cancelled once ...
    assert out["log"]["downloaded"] == [SESSION]      # ... then restarted in the browser
    assert out["log"]["badge"] == ["!"]               # and NOT taken over again in a loop


@needs_node
def test_the_popup_can_send_links_through_the_background_script(app):
    api, b = app
    out = run(b.port, "send")
    assert out["answer"]["ok"] and api.added[0]["kind"] == "audio"
    assert api.added[0]["urls"] == ["http://a.com/1", "http://a.com/2"] and api.added[0]["extra"]["cookie"] == ""


@needs_node
def test_the_popup_can_ask_whether_the_app_runs(app):
    api, b = app
    out = run(b.port, "status")
    assert out["answer"]["app"]["app"] == "DISO" and out["answer"]["app"]["version"] == __version__
    assert out["answer"]["port"] == b.port and out["answer"]["intercept"] is False


@needs_node
def test_the_popup_sees_a_closed_app_and_reports_it_when_sending(app):
    api, b = app
    port = b.port
    b.stop()
    assert run(port, "status")["answer"]["app"] is None
    sent = run(port, "send")["answer"]
    assert sent["ok"] is False and "açık mı" in sent["text"]


@needs_node
def test_a_switched_off_bridge_says_so_to_the_user(app):
    api, b = app
    api.add_enabled = False
    sent = run(b.port, "send")["answer"]
    assert sent["ok"] is False and "kapalı" in sent["text"]


@needs_node
def test_an_unknown_message_is_ignored(app):
    api, b = app
    assert run(b.port, "unknown-message")["answer"] is None
