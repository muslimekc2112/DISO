"""The built .exe (dist/DISO.exe, made by build.bat). Skipped when it has not been built.

Build it first:  python tools/build_exe.py --no-ffmpeg
These tests start the real program in a private home folder and check what a user would see:
the bundled libraries load, a newer downloaded yt-dlp beats the bundled one inside the exe,
the window opens, the browser bridge works, a second launch wakes the first, closing is clean.
"""
import ctypes
import json
import os
import socket
import subprocess
import sys
import time

import pytest
import requests

from conftest import wait_for

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.environ.get("DISO_TEST_EXE") or os.path.join(ROOT, "dist", "DISO.exe")     # another build can be tested too
WINDOWS = sys.platform.startswith("win")
pytestmark = [pytest.mark.exe,
              pytest.mark.skipif(not (WINDOWS and os.path.exists(EXE)), reason="dist/DISO.exe not built")]

NO_PROXY = {"http": None, "https": None}
TITLE = "DISO"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def home(tmp_path):
    """A private home with settings that keep the test quiet and the port known."""
    h = tmp_path / "home"
    d = h / "AppData" / "Local" / "DISO"
    d.mkdir(parents=True)
    (d / "settings.json").write_text(json.dumps({
        "bridge_port": free_port(), "folder": str(tmp_path / "dl"), "notify_sound": False,
        "notify_toast": False}), encoding="utf-8")
    return h


def port_of(home):
    return json.loads((home / "AppData" / "Local" / "DISO" / "settings.json").read_text(encoding="utf-8"))["bridge_port"]


def env_for(home):
    return {**os.environ, "USERPROFILE": str(home), "HOME": str(home), "LOCALAPPDATA": str(home / "AppData" / "Local"),
            "HIZLI_NO_UPDATE": "1", "DISO_NO_NATIVE_HOST": "1"}


def selftest(home, tmp_path):
    out = tmp_path / "selftest.json"
    r = subprocess.run([EXE, "--selftest", str(out)], env=env_for(home), timeout=120, capture_output=True)
    assert r.returncode == 0 and out.exists(), r.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def find_window():
    return ctypes.windll.user32.FindWindowW(None, TITLE)


def visible(hwnd):
    return bool(ctypes.windll.user32.IsWindowVisible(hwnd))


@pytest.fixture
def running(home):
    """Launch the program; yields a function start(*args) -> process. Everything is stopped after."""
    procs = []

    def start(*args):
        p = subprocess.Popen([EXE, *args], env=env_for(home), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)
        return p

    yield start
    for p in procs:
        if p.poll() is None:
            p.kill()
            p.wait(10)


def wait_until_up(home, timeout=60):
    port = port_of(home)
    ping = lambda: requests.get(f"http://127.0.0.1:{port}/ping", timeout=2, proxies=NO_PROXY).json()  # noqa: E731

    def up():
        try:
            return ping()
        except Exception:  # noqa: BLE001
            return None

    assert wait_for(up, timeout, interval=0.3), "the program did not start"
    return port


def close_window(proc):
    hwnd = find_window()
    assert hwnd, "no window to close"
    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)       # WM_CLOSE: the X button
    assert wait_for(lambda: proc.poll() is not None, 30), "the program did not quit after the window was closed"
    return proc.returncode


# --------------------------------------------------------------------------- selftest
def test_the_exe_carries_everything_it_needs(home, tmp_path):
    info = selftest(home, tmp_path)
    assert info["frozen"] is True and info["version"]
    for part in ("customtkinter", "pystray", "PIL", "socks", "requests"):
        assert info[part] is True, (part, info[part])
    assert info["tray_icon"] is True
    assert info["music_player"] is True                                       # the music player starts
    assert info["music_ui"] is True                                           # its table, pictures, tag reader load
    assert info["tag_tools"] is True                                          # ffprobe + ffmpeg are found inside
    assert info["playable"] is True                                           # a song MCI refuses still plays
    assert "yt_dlp_error" not in info and info["yt_dlp_version"]
    assert "_MEI" in info["yt_dlp_file"] or "Temp" in info["yt_dlp_file"]     # the copy inside the exe
    assert info["overrides"] == {}


def test_a_newer_downloaded_yt_dlp_beats_the_bundled_one_inside_the_exe(home, tmp_path):
    pk = home / "AppData" / "Local" / "DISO" / "packages"
    (pk / "yt_dlp").mkdir(parents=True)
    (pk / "yt_dlp" / "__init__.py").write_text(
        "MARK = 'downloaded copy'\nclass YoutubeDL:\n    def __init__(self, *a, **k): pass\n"
        "    def close(self): pass\nclass version:\n    __version__ = '2099.1.1'\n", encoding="utf-8")
    (pk / "manifest.json").write_text(json.dumps({"yt-dlp": "2099.1.1"}), encoding="utf-8")
    info = selftest(home, tmp_path)
    assert info["yt_dlp_mark"] == "downloaded copy" and info["yt_dlp_file"].startswith(str(pk))
    assert info["overrides"] == {"yt-dlp": "2099.1.1"}


def test_a_broken_downloaded_yt_dlp_is_rolled_back_inside_the_exe(home, tmp_path):
    pk = home / "AppData" / "Local" / "DISO" / "packages"
    (pk / "yt_dlp").mkdir(parents=True)
    (pk / "yt_dlp" / "__init__.py").write_text("raise ImportError('broken update')\n", encoding="utf-8")
    (pk / "manifest.json").write_text(json.dumps({"yt-dlp": "2099.1.1"}), encoding="utf-8")
    info = selftest(home, tmp_path)
    assert "yt_dlp_error" not in info and info["yt_dlp_version"] != "2099.1.1"
    assert info["overrides"] == {}                              # back on the bundled copy
    manifest = json.loads((pk / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["_bad"] == {"yt-dlp": "2099.1.1"} and "yt-dlp" not in manifest
    assert not (pk / "yt_dlp").exists()


# ------------------------------------------------------------------------------ window
def test_the_window_opens_downloads_through_the_bridge_and_closes_cleanly(home, running, server, tmp_path):
    proc = running()
    port = wait_until_up(home)
    assert wait_for(lambda: find_window() and visible(find_window()), 30)       # the real window is on screen
    name, data = server.file(300_000, ".zip")
    r = requests.post(f"http://127.0.0.1:{port}/add", proxies=NO_PROXY,
                      headers={"Origin": "chrome-extension://abcdefghijklmnop"},
                      json={"urls": [server.url("f", name)], "kind": "file"})
    assert r.json() == {"added": 1, "duplicates": 0}
    saved = tmp_path / "dl" / name
    assert wait_for(lambda: saved.exists() and saved.read_bytes() == data, 30)
    assert requests.get(f"http://127.0.0.1:{port}/status", proxies=NO_PROXY).json()["total"] == 1
    assert close_window(proc) == 0
    listing = json.loads((home / "AppData" / "Local" / "DISO" / "downloads.json").read_text(encoding="utf-8"))
    assert [i["state"] for i in listing["items"]] == ["done"]
    assert (home / "AppData" / "Local" / "DISO" / "diso.log").exists()


def test_a_second_launch_wakes_the_first_window_and_exits(home, running):
    first = running()
    wait_until_up(home)
    hwnd = None

    def got_window():
        nonlocal hwnd
        hwnd = find_window()
        return hwnd

    assert wait_for(got_window, 30)
    ctypes.windll.user32.ShowWindow(hwnd, 6)                    # minimise it
    second = running()
    assert wait_for(lambda: second.poll() is not None, 30)      # it leaves at once ...
    assert second.returncode == 0
    assert first.poll() is None                                 # ... the first one keeps running
    assert close_window(first) == 0


def test_starting_minimized_keeps_the_window_hidden_until_asked(home, running):
    proc = running("--minimized")
    port = wait_until_up(home)
    time.sleep(1.5)
    hwnd = find_window()
    assert not hwnd or not visible(hwnd)                        # nothing on screen (the tray icon only)
    assert requests.post(f"http://127.0.0.1:{port}/show", proxies=NO_PROXY).status_code == 200
    assert wait_for(lambda: find_window() and visible(find_window()), 20)
    assert close_window(proc) == 0


def test_the_exe_refuses_web_pages_like_the_source_version_does(home, running):
    proc = running()
    port = wait_until_up(home)
    r = requests.post(f"http://127.0.0.1:{port}/add", proxies=NO_PROXY, headers={"Origin": "https://evil.example"},
                      json={"urls": ["http://a.com/x"]})
    assert r.status_code == 403
    assert wait_for(lambda: find_window(), 30)
    assert close_window(proc) == 0

# ------------------------------------------------------------------ started by the browser extension
ORIGIN = "chrome-extension://adkiobcdpklfjnbajjiocmlifmbhdnei/"


def talk(home, *messages, timeout=120):
    data = b"".join(len(b := json.dumps(m).encode()).to_bytes(4, "little") + b for m in messages)
    r = subprocess.run([EXE, ORIGIN, "--parent-window=0"], input=data, capture_output=True, env=env_for(home),
                       timeout=timeout)
    out, answers = r.stdout, []
    while len(out) >= 4:
        n = int.from_bytes(out[:4], "little")
        answers.append(json.loads(out[4:4 + n]))
        out = out[4 + n:]
    return r.returncode, answers


def test_the_windowed_exe_talks_to_the_browser_through_its_pipes(home):
    code, answers = talk(home, {"type": "ping", "port": port_of(home)})
    assert code == 0 and answers and answers[0]["ok"] is True and answers[0]["running"] is False


def test_the_native_host_starts_a_closed_diso_and_waits_for_it(home):
    started = time.time()
    try:
        code, answers = talk(home, {"type": "launch", "port": port_of(home)})
        assert code == 0 and answers == [{"ok": True, "started": True}]
        assert wait_until_up(home)                                   # DISO runs on its own, the host has ended
        code, answers = talk(home, {"type": "launch", "port": port_of(home)})
        assert answers == [{"ok": True, "started": False}]           # a running DISO is not started twice
    finally:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq '" + EXE + "' -and "
                        "$_.CreationDate -gt (Get-Date).AddSeconds(-" + str(int(time.time() - started) + 5) + ") } | "
                        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"], capture_output=True, timeout=60)
