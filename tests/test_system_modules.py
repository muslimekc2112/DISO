"""Scheduler maths, start-with-Windows, tray icon, browser bridge and the connection test."""
import json
import sys
import uuid

import pytest
import requests

from app import __version__, bridge, schedule, startup, tray
from app.segmented_downloader import check_connection

# ------------------------------------------------------------------------------ schedule


@pytest.mark.parametrize("text,expected", [
    ("00:00", 0), ("07:30", 450), ("7:30", 450), (" 23:59 ", 1439), ("12:00", 720),
    ("24:00", None), ("12:60", None), ("7", None), ("", None), (None, None), ("ab:cd", None),
    ("07:3", None), ("-1:00", None),
])
def test_parse_hhmm(text, expected):
    assert schedule.parse_hhmm(text) == expected


def test_format_hhmm():
    assert schedule.format_hhmm(0) == "00:00" and schedule.format_hhmm(450) == "07:30"
    assert schedule.format_hhmm(1439) == "23:59"


def hm(text):
    return schedule.parse_hhmm(text)


@pytest.mark.parametrize("now,start,stop,expected", [
    # no start time: never blocks
    ("03:00", None, None, True), ("03:00", None, "07:00", True),
    # start only: open from the start time on
    ("01:59", "02:00", None, False), ("02:00", "02:00", None, True), ("23:59", "02:00", None, True),
    ("00:00", "02:00", None, False),
    # window inside one day
    ("01:59", "02:00", "07:00", False), ("02:00", "02:00", "07:00", True),
    ("06:59", "02:00", "07:00", True), ("07:00", "02:00", "07:00", False), ("15:00", "02:00", "07:00", False),
    # overnight window
    ("22:59", "23:00", "06:00", False), ("23:00", "23:00", "06:00", True), ("03:00", "23:00", "06:00", True),
    ("05:59", "23:00", "06:00", True), ("06:00", "23:00", "06:00", False), ("12:00", "23:00", "06:00", False),
    # start == stop counts as "no stop"
    ("01:00", "02:00", "02:00", False), ("03:00", "02:00", "02:00", True),
])
def test_when_the_gate_is_open(now, start, stop, expected):
    assert schedule.gate_should_be_open(hm(now), hm(start), hm(stop)) is expected


def test_describe():
    assert schedule.describe(hm("02:00"), hm("07:00")) == "02:00–07:00"
    assert schedule.describe(hm("02:00"), None) == "02:00"
    assert schedule.describe(hm("02:00"), hm("02:00")) == "02:00"
    assert schedule.describe(None, None) == ""


# ------------------------------------------------------------------------------- startup
def test_the_startup_command_for_a_source_install_and_an_exe(monkeypatch):
    cmd = startup.command()
    assert cmd.endswith('main.py" --minimized') and cmd.startswith('"')
    assert startup.command(minimized=False).endswith('main.py"')
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\DISO.exe")
    assert startup.command() == r'"C:\Apps\DISO.exe" --minimized'


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows registry")
def test_start_with_windows_writes_and_removes_the_registry_value():
    name = f"DISOTest_{uuid.uuid4().hex[:8]}"
    try:
        assert startup.is_enabled(name) is False
        assert startup.set_enabled(True, name) is True
        assert startup.is_enabled(name) is True
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, startup.RUN_KEY) as key:
            assert winreg.QueryValueEx(key, name)[0] == startup.command()
        assert startup.set_enabled(False, name) is True
        assert startup.is_enabled(name) is False
        assert startup.set_enabled(False, name) is True        # removing twice is fine
    finally:
        startup.set_enabled(False, name)


# ---------------------------------------------------------------------------------- tray
@pytest.mark.gui
@pytest.mark.skipif(not tray.AVAILABLE, reason="pystray is not installed")
def test_tray_icon_starts_changes_its_tooltip_and_stops():
    events = []
    icon = tray.TrayIcon("DISO", events.append)
    try:
        icon.start()
        assert icon.running
        icon.set_title("x" * 300)                      # longer than Windows allows: must not raise
        icon._fire("show")
        icon._fire("quit")
        assert events == ["show", "quit"]
    finally:
        icon.stop()
    assert not icon.running


@pytest.mark.skipif(not tray.AVAILABLE, reason="pystray is not installed")
def test_tray_menu_entries_call_back_with_their_names():
    events = []
    icon = tray.TrayIcon("t", events.append)
    items = [i for i in icon._icon.menu.items if i.text and i.text != "- - - -"]  # no separator
    assert [i.text for i in items] == ["Göster", "Hepsini duraklat", "Hepsini başlat", "Çıkış"]
    for item in items:
        item(icon._icon)
    assert events == ["show", "pause_all", "resume_all", "quit"]


@pytest.mark.skipif(not tray.AVAILABLE, reason="pystray is not installed")
def test_tray_image_falls_back_to_a_plain_square(tmp_path):
    assert tray.load_image(str(tmp_path / "missing.png")).size == (64, 64)
    assert tray.load_image().size[0] >= 64                    # the real icon


def test_a_failing_menu_callback_does_not_break_the_tray():
    if not tray.AVAILABLE:
        pytest.skip("pystray is not installed")

    def boom(name):
        raise RuntimeError("window is gone")

    tray.TrayIcon("t", boom)._fire("show")


# --------------------------------------------------------------------------------- bridge
class FakeApi:
    def __init__(self):
        self.add_enabled = True
        self.added, self.shown = [], 0

    def add(self, urls, extra, kind):
        self.added.append((urls, extra, kind))
        return {"added": len(urls), "duplicates": 0}

    def status(self):
        return {"active": 1, "queued": 2, "speed": 1234}

    def show(self):
        self.shown += 1


@pytest.fixture
def running():
    api = FakeApi()
    b = bridge.Bridge(api, port=0)
    assert b.start()
    base = f"http://127.0.0.1:{b.port}"
    yield api, b, base
    b.stop()


EXT = {"Origin": "chrome-extension://abcdefghijklmnop"}


def post(base, path, body, headers=None, raw=None):
    data = raw if raw is not None else json.dumps(body).encode()
    h = {"Content-Type": "application/json", **(headers or {})}
    return requests.post(base + path, data=data, headers=h, proxies={"http": None, "https": None})


def get(base, path, headers=None):
    return requests.get(base + path, headers=headers or {}, proxies={"http": None, "https": None})


def test_the_bridge_notices_that_the_extension_is_in_a_browser(running):
    api, b, base = running
    seen = []
    api.extension_seen = lambda: seen.append(1)
    get(base, "/ping")                                                    # a local program: not the extension
    get(base, "/ping", headers={"Origin": "https://evil.example"})        # a web page: refused, not the extension
    assert seen == []
    get(base, "/ping", headers=EXT)
    get(base, "/status", headers={"Origin": "moz-extension://1234"})
    assert seen == [1, 1]

def test_ping_identifies_the_app(running):
    api, b, base = running
    data = get(base, "/ping").json()
    assert data == {"app": "DISO", "version": __version__, "add": True}
    assert get(base, "/status").json() == {"active": 1, "queued": 2, "speed": 1234}
    assert get(base, "/nothing").status_code == 404


def test_links_from_the_extension_are_added_with_the_session(running):
    api, b, base = running
    r = post(base, "/add", {"urls": ["http://a.com/x.zip", "https://b.org/y"], "referer": "http://a.com/page",
                            "userAgent": "UA/1", "cookies": "sid=1", "kind": "video"}, EXT)
    assert r.status_code == 200 and r.json() == {"added": 2, "duplicates": 0}
    assert r.headers["Access-Control-Allow-Origin"] == EXT["Origin"]
    urls, extra, kind = api.added[0]
    assert urls == ["http://a.com/x.zip", "https://b.org/y"] and kind == "video"
    assert extra == {"referer": "http://a.com/page", "user_agent": "UA/1", "cookie": "sid=1"}


def test_a_local_program_without_an_origin_may_add_links_too(running):
    api, b, base = running
    r = post(base, "/add", {"urls": ["http://a.com/x"]})
    assert r.status_code == 200 and "Access-Control-Allow-Origin" not in r.headers


@pytest.mark.parametrize("origin", ["https://evil.example", "http://localhost:3000", "null",
                                    "file://", "chrome://settings"])
def test_a_web_page_can_never_add_downloads(running, origin):
    api, b, base = running
    for path, method in (("/add", post), ("/show", post)):
        r = method(base, path, {"urls": ["http://a.com/x"]}, {"Origin": origin})
        assert r.status_code == 403
    assert get(base, "/ping", {"Origin": origin}).status_code == 403
    assert api.added == [] and api.shown == 0


def test_dns_rebinding_is_refused_by_the_host_check(running):
    api, b, base = running
    assert get(base, "/ping", {"Host": "evil.example"}).status_code == 403
    assert post(base, "/add", {"urls": ["http://a.com/x"]}, {"Host": "evil.example:80"}).status_code == 403
    assert get(base, "/ping", {"Host": f"localhost:{b.port}"}).status_code == 200
    assert api.added == []


def test_the_preflight_request_is_answered_only_for_extensions(running):
    api, b, base = running
    r = requests.options(base + "/add", headers={**EXT, "Access-Control-Request-Method": "POST"},
                         proxies={"http": None, "https": None})
    assert r.status_code == 204
    assert r.headers["Access-Control-Allow-Origin"] == EXT["Origin"]
    assert "POST" in r.headers["Access-Control-Allow-Methods"]
    assert r.headers["Access-Control-Allow-Private-Network"] == "true"
    evil = requests.options(base + "/add", headers={"Origin": "https://evil.example"},
                            proxies={"http": None, "https": None})
    assert evil.status_code == 403
    assert requests.options(base + "/add", proxies={"http": None, "https": None}).status_code == 403


@pytest.mark.parametrize("body", [
    {}, {"urls": "http://a.com"}, {"urls": []}, {"urls": ["not a link", "ftp://x/y", 5, None]},
])
def test_bad_add_requests_are_refused(running, body):
    api, b, base = running
    assert post(base, "/add", body, EXT).status_code == 400
    assert api.added == []


def test_broken_or_oversized_bodies_are_refused(running):
    api, b, base = running
    assert post(base, "/add", None, EXT, raw=b"{not json").status_code == 400
    assert post(base, "/add", None, EXT, raw=b"[1,2]").status_code == 400
    assert post(base, "/add", None, EXT, raw=b"").status_code == 400
    assert post(base, "/add", None, EXT, raw=b"x" * (bridge.MAX_BODY + 1)).status_code == 400
    assert api.added == []


def test_invalid_links_are_dropped_but_valid_ones_are_kept(running):
    api, b, base = running
    post(base, "/add", {"urls": ["not a link", "http://ok.com/a", 7]}, EXT)
    assert api.added[0][0] == ["http://ok.com/a"]


def test_the_number_and_size_of_the_fields_are_limited(running):
    api, b, base = running
    post(base, "/add", {"urls": [f"http://a.com/{i}" for i in range(bridge.MAX_URLS + 50)],
                        "referer": "r" * 10000, "userAgent": ["x"], "cookies": "c" * 20000, "kind": "evil"}, EXT)
    urls, extra, kind = api.added[0]
    assert len(urls) == bridge.MAX_URLS
    assert len(extra["referer"]) == 2000 and extra["user_agent"] == "" and len(extra["cookie"]) == 8000
    assert kind is None                                      # unknown kinds are ignored


def test_adding_can_be_switched_off(running):
    api, b, base = running
    api.add_enabled = False
    r = post(base, "/add", {"urls": ["http://a.com/x"]}, EXT)
    assert r.status_code == 403 and r.json() == {"error": "disabled"}
    assert get(base, "/ping").json()["add"] is False
    assert post(base, "/show", {}).status_code == 200        # the window can still be shown


def test_show_is_post_only(running):
    api, b, base = running
    assert get(base, "/show").status_code == 404
    assert post(base, "/show", {}).status_code == 200 and api.shown == 1


def test_a_second_bridge_on_the_same_port_fails_which_is_how_we_know_a_copy_runs(running):
    api, b, base = running
    assert bridge.Bridge(FakeApi(), port=b.port).start() is False


def test_finding_and_waking_a_running_copy(running):
    api, b, base = running
    assert bridge.ping_existing(b.port) is True
    assert bridge.show_existing(b.port) is True and api.shown == 1
    b.stop()
    assert bridge.ping_existing(b.port) is False
    assert bridge.show_existing(b.port) is False


def test_something_else_on_the_port_is_not_mistaken_for_the_app(server):
    port = int(server.base.rsplit(":", 1)[1])
    assert bridge.ping_existing(port) is False


def test_origin_and_host_helpers():
    assert bridge.origin_allowed(None) and bridge.origin_allowed("")
    assert bridge.origin_allowed("moz-extension://x") and bridge.origin_allowed("safari-web-extension://x")
    assert not bridge.origin_allowed("https://example.com")
    assert bridge.host_allowed("127.0.0.1:5", 5) and bridge.host_allowed("localhost", 5)
    assert not bridge.host_allowed("127.0.0.1:6", 5) and not bridge.host_allowed(None, 5)


# ---------------------------------------------------------------------- connection test
def test_connection_test_reports_status_and_time(server):
    name, _ = server.file(100)
    ok, text = check_connection(server.url("f", name))
    assert ok and text.startswith("HTTP 200") and "ms" in text


def test_connection_test_fails_for_errors(server):
    assert check_connection(server.url("f", "missing"))[0] is False
    ok, text = check_connection("http://127.0.0.1:9/x", timeout=2)
    assert ok is False and text


def test_connection_test_goes_through_the_given_proxy(server, proxy):
    name, _ = server.file(100)
    ok, text = check_connection(server.url("f", name), proxy=proxy.url)
    assert ok and proxy.hits
    assert check_connection(server.url("f", name), proxy="not a proxy")[0] is False
    assert check_connection(server.url("f", name), proxy="http://127.0.0.1:9", timeout=2)[0] is False


# -------------------------------------------------------- the tray must never keep the app alive
def _child(code, timeout=30):
    """Run code in a fresh Python; raises subprocess.TimeoutExpired if the process does not end."""
    import os
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prelude = f"import sys; sys.path.insert(0, {root!r})\nfrom app import tray\n"
    return subprocess.run([sys.executable, "-c", prelude + code], timeout=timeout, capture_output=True, text=True)


@pytest.mark.gui
@pytest.mark.skipif(not tray.AVAILABLE or not sys.platform.startswith("win"), reason="needs pystray on Windows")
@pytest.mark.parametrize("code", [
    "i = tray.TrayIcon('t', print); i.start(); i.stop()",                    # normal use
    "i = tray.TrayIcon('t', print); i.start(); i.set_title('x' * 500); i.stop()",
    "i = tray.TrayIcon('t', print); i.start()",                              # never stopped
    "i = tray.TrayIcon('t', print); i.stop()",                               # never started
    "i = tray.TrayIcon('t', print); i.start(); i.stop(); i.stop()",          # stopped twice
], ids=["start-stop", "tooltip", "never-stopped", "never-started", "stop-twice"])
def test_the_tray_icon_never_keeps_the_process_alive(code):
    for _ in range(4):                      # the old bug was a race: try several times
        result = _child(code)
        assert result.returncode == 0, result.stderr
