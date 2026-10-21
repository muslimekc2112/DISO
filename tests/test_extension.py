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
def manifest(name="manifest.json"):
    with open(os.path.join(EXT, name), encoding="utf-8") as f:
        return json.load(f)


def firefox_manifest():
    return manifest("manifest.firefox.json")


def test_the_manifest_is_a_valid_manifest_v3_for_chrome_and_firefox():
    m = manifest()
    assert m["manifest_version"] == 3 and m["name"] == "DISO"
    assert m["version"] == __version__                       # extension and app move together
    assert set(m["permissions"]) == {"contextMenus", "downloads", "storage", "cookies", "activeTab", "scripting",
                                      "nativeMessaging"}
    assert "http://127.0.0.1/*" in m["host_permissions"]
    assert m["background"] == {"service_worker": "sw.js"}                       # Chrome
    assert firefox_manifest()["background"] == {"scripts": ["lib.js", "background.js"]}   # Firefox
    assert firefox_manifest()["browser_specific_settings"]["gecko"]["id"]


# Chrome warns about every key of a manifest it does not know ("background.scripts requires manifest
# version 2 or lower" ...): the Chrome manifest holds only what Chrome understands, Firefox has its own.
CHROME_KEYS = {"manifest_version", "name", "version", "version_name", "description", "default_locale", "key",
               "permissions", "host_permissions", "background", "action", "options_ui", "icons", "content_scripts"}


def test_chrome_gets_no_key_it_would_warn_about_and_firefox_gets_no_chrome_key():
    assert set(manifest()) <= CHROME_KEYS
    assert "key" not in firefox_manifest() and "service_worker" not in firefox_manifest()["background"]


def test_the_two_manifests_say_the_same_about_everything_else():
    chrome, firefox = manifest(), firefox_manifest()
    for k in set(chrome) | set(firefox):
        if k not in ("key", "background", "browser_specific_settings"):
            assert chrome.get(k) == firefox.get(k), k


def test_every_file_the_manifest_and_pages_mention_exists():
    m = manifest()
    files = [m["background"]["service_worker"], *firefox_manifest()["background"]["scripts"], m["action"]["default_popup"],
             m["options_ui"]["page"], *m["icons"].values(), *m["action"]["default_icon"].values(),
             *[js for c in m["content_scripts"] for js in c["js"]]]
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
        self.lang = "tr"

    def language(self):
        return self.lang

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


def run(port, scenario, live=None):
    args = [NODE, os.path.join(JS, "harness.js"), str(port), scenario] + ([str(live)] if live else [])
    r = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert "error" not in data, data
    return data


SESSION = "http://shop.example/files/report.zip"
PAGE = "http://shop.example/page"


@needs_node
def test_the_context_menu_entries_are_created(app):
    api, b = app
    assert run(b.port, "menus")["log"]["menus"] == ["hi-link", "hi-media", "hi-page-video", "hi-page-audio",
                                                    "hi-all-links", "hi-torrents", "hi-selection"]


@needs_node
def test_a_link_goes_to_the_app_with_the_browsers_session(app):
    api, b = app
    out = run(b.port, "link")
    assert out["answer"]["ok"] is True and out["answer"]["text"] == "1 bağlantı eklendi"
    assert api.added == [{"urls": [SESSION], "kind": "file",                   # report.zip: a file, as it is
                          "extra": {"referer": PAGE, "user_agent": "TestBrowser/1.0", "cookie": "sid=1; theme=dark"}}]
    assert out["log"]["cookiesAsked"] == [SESSION] and out["log"]["badge"] == ["✓"]


@needs_node
def test_a_media_element_is_sent_with_the_page_as_referer(app):
    api, b = app
    run(b.port, "media")
    assert api.added[0]["urls"] == ["http://shop.example/v.mp4"] and api.added[0]["extra"]["referer"] == PAGE
    assert api.added[0]["extra"]["cookie"] == ""


@needs_node
def test_the_page_entries_ask_for_the_video_as_mp4_or_mp3(app):
    api, b = app
    run(b.port, "page")
    assert api.added[0]["urls"] == ["http://video.example/watch?v=1"] and api.added[0]["kind"] == "video"
    assert api.added[0]["extra"]["referer"] == ""
    run(b.port, "page-audio")
    assert api.added[1]["urls"] == ["http://video.example/watch?v=1"] and api.added[1]["kind"] == "audio"


@needs_node
def test_a_page_link_is_left_for_diso_to_look_at(app):
    api, b = app
    run(b.port, "page-link")
    assert api.added[0]["urls"] == ["http://video.example/watch?v=2"] and api.added[0]["kind"] == "auto"


@needs_node
def test_mixed_links_go_with_what_each_one_is(app):
    api, b = app
    out = run(b.port, "mixed-selection")
    assert out["answer"]["text"] == "3 bağlantı eklendi"
    assert [(a["kind"], a["urls"]) for a in api.added] == [
        ("file", ["http://a.com/setup.exe", "http://a.com/b.rar"]), ("auto", ["http://a.com/watch?v=1"])]


@needs_node
def test_selected_text_sends_every_link_once_and_no_cookies(app):
    api, b = app
    run(b.port, "selection")
    assert api.added[0]["urls"] == ["http://a.com/1", "https://b.org/2"] and api.added[0]["kind"] == "auto"
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
    assert api.added[0]["urls"] == [SESSION] and api.added[0]["kind"] == "file"     # never turned into MP4 / MP3
    assert api.added[0]["extra"] == {"referer": PAGE, "user_agent": "TestBrowser/1.0", "cookie": "sid=1; theme=dark"}
    assert out["log"]["badge"] == ["✓"] and out["log"]["downloaded"] == []


@needs_node
@pytest.mark.parametrize("scenario", ["intercept-off", "intercept-small", "intercept-blob", "intercept-history",
                                      "intercept-finished", "intercept-before-ready"])
def test_downloads_that_are_not_ours_stay_with_the_browser(app, scenario):
    api, b = app
    out = run(b.port, scenario)
    assert api.added == [] and out["log"]["cancelled"] == [] and out["log"]["downloaded"] == []
    assert out["log"]["erased"] == [] and out["log"]["paused"] == []      # the browser's history is left alone


@needs_node
def test_with_the_app_closed_the_browser_keeps_the_download(app):
    api, b = app
    port = b.port
    b.stop()
    out = run(port, "intercept")
    assert out["log"]["cancelled"] == [] and out["log"]["erased"] == [] and out["log"]["downloaded"] == []
    assert out["log"]["paused"] == [7] and out["log"]["resumed"] == [7]      # held while DISO could not be started


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
    out = run(port, "send")
    sent = out["answer"]
    assert sent["ok"] is False and "açık mı" in sent["text"]
    assert [n["message"]["type"] for n in out["log"]["native"]] == ["launch"]       # it tried to start DISO first


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


def free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_the_extension_id_is_the_one_the_native_host_allows():
    import base64
    import hashlib

    from app import native_host
    digest = hashlib.sha256(base64.b64decode(manifest()["key"])).hexdigest()[:32]
    assert "".join(chr(ord("a") + int(c, 16)) for c in digest) == native_host.EXTENSION_ID
    assert firefox_manifest()["browser_specific_settings"]["gecko"]["id"] == native_host.FIREFOX_ID
    lib = open(os.path.join(EXT, "lib.js"), encoding="utf-8").read()
    assert f'const HOST = "{native_host.HOST_NAME}"' in lib


@needs_node
def test_a_closed_diso_is_started_and_then_gets_the_link(app):
    api, b = app
    dead = free_port()
    out = run(dead, "link", live=b.port)
    assert out["log"]["native"] == [{"host": "com.iso.diso", "message": {"type": "launch", "port": dead}}]
    assert out["answer"]["ok"] is True and api.added[0]["urls"] == [SESSION]


@needs_node
def test_a_running_diso_is_not_started_again(app):
    api, b = app
    out = run(b.port, "link", live=b.port)
    assert out["log"]["native"] == [] and api.added


@needs_node
def test_without_permission_to_start_diso_the_native_host_is_left_alone(app):
    api, b = app
    out = run(free_port(), "launch-off", live=b.port)
    assert out["log"]["native"] == [] and out["answer"]["ok"] is False and api.added == []


@needs_node
def test_a_browser_download_waits_while_diso_starts_then_moves_over(app):
    api, b = app
    out = run(free_port(), "intercept", live=b.port)
    assert out["log"]["paused"] == [7] and out["log"]["cancelled"] == [7] and out["log"]["resumed"] == []
    assert api.added[0]["urls"] == [SESSION]


@needs_node
def test_all_file_links_of_a_page_go_to_diso_once_each(app):
    api, b = app
    out = run(b.port, "all-links")
    assert out["log"]["scripted"] == [5]
    assert api.added[0]["urls"] == ["http://shop.example/a.zip", "http://shop.example/b.mp4"]
    assert api.added[0]["kind"] == "file"


@needs_node
def test_the_popup_opens_diso_and_brings_it_forward(app):
    api, b = app
    out = run(free_port(), "open", live=b.port)
    assert out["answer"]["ok"] is True and api.shown == 1 and len(out["log"]["native"]) == 1


@needs_node
def test_the_popup_says_when_diso_cannot_be_opened(app):
    api, b = app
    out = run(free_port(), "open")
    assert out["answer"]["ok"] is False and "bir kez" in out["answer"]["text"]

# ------------------------------------------------------------------------ 🧲 torrents and the language
def test_magnet_clicks_are_caught_by_a_content_script_in_every_page():
    for m in (manifest(), firefox_manifest()):
        assert m["content_scripts"] == [{"matches": ["<all_urls>"], "js": ["catch.js"], "run_at": "document_start",
                                         "all_frames": True}]
    code = open(os.path.join(EXT, "catch.js"), encoding="utf-8").read()
    assert '"magnet"' in code and "preventDefault" in code and "a.click()" in code     # given back if DISO cannot


@needs_node
def test_the_torrents_of_a_page_go_to_diso_once_each(app):
    api, b = app
    out = run(b.port, "torrents")
    assert out["log"]["scripted"] == [5] and out["answer"]["ok"] is True
    assert sorted(u for a in api.added for u in a["urls"]) == ["http://shop.example/two.torrent",
                                                               "magnet:?xt=urn:btih:AAA&dn=one"]


@needs_node
def test_the_popup_finds_the_torrents_of_the_page(app):
    api, b = app
    assert run(b.port, "page-torrents")["answer"] == ["magnet:?xt=urn:btih:AAA&dn=one", "http://shop.example/two.torrent"]
    assert api.added == []


@needs_node
def test_a_clicked_magnet_goes_to_diso_unless_torrents_are_switched_off(app):
    api, b = app
    out = run(b.port, "magnet")
    assert out["answer"]["ok"] is True
    assert api.added == [{"urls": ["magnet:?xt=urn:btih:AAA&dn=one"], "kind": "auto",
                          "extra": {"referer": PAGE, "user_agent": "TestBrowser/1.0", "cookie": ""}}]
    out = run(b.port, "magnet-off")
    assert out["answer"] == {"ok": False} and len(api.added) == 1        # the browser opens it as usual


@needs_node
def test_a_clicked_magnet_is_given_back_when_diso_is_closed(app):
    out = run(free_port(), "magnet")
    assert out["answer"]["ok"] is False


@needs_node
def test_a_torrent_file_download_moves_to_diso_even_without_intercept(app):
    api, b = app
    out = run(b.port, "intercept-torrent")
    assert out["log"]["cancelled"] == [8] and api.added[0]["urls"] == ["http://shop.example/get?id=2"]
    assert api.added[0]["kind"] == "file"


@needs_node
def test_the_extension_speaks_the_language_diso_speaks(app):
    api, b = app
    out = run(b.port, "language")
    assert out["answer"]["lang"] == "tr" and out["log"]["titles"][0] == "DISO ile indir"
    api.lang = "en"
    out = run(b.port, "language")
    assert out["answer"]["lang"] == "en" and out["store"]["appLang"] == "en"
    assert out["log"]["titles"][0] == "Download with DISO" and "🧲 Download the torrents on this page with DISO" in out["log"]["titles"]
    out = run(b.port, "language-fixed")                  # chosen by hand in the extension: stays
    assert out["answer"]["lang"] == "tr"


def test_the_popup_shows_downloads_torrents_and_a_paste_box():
    html = open(os.path.join(EXT, "popup.html"), encoding="utf-8").read()
    for element in ('id="list"', 'id="torrents"', 'id="paste"', 'id="pasteGo"', 'id="lang-tr"', 'id="lang-en"'):
        assert element in html, element
    options = open(os.path.join(EXT, "options.html"), encoding="utf-8").read()
    assert 'id="lang"' in options and 'id="torrents"' in options
