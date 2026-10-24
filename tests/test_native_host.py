"""The native host: how the browser extension starts DISO when it is closed (app/native_host.py)."""
import io
import json
import os
import struct
import subprocess
import sys
import uuid

import pytest

from app import __version__, native_host

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGIN = f"chrome-extension://{native_host.EXTENSION_ID}/"
winreg = pytest.importorskip("winreg")


def packed(*messages):
    out = b""
    for m in messages:
        data = json.dumps(m).encode("utf-8")
        out += struct.pack("<I", len(data)) + data
    return out


def unpacked(data):
    stream, out = io.BytesIO(data), []
    while True:
        m = native_host.read_message(stream)
        if m is None:
            return out
        out.append(m)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s


# ----------------------------------------------------------------------------- protocol
def test_messages_go_both_ways_with_their_length_in_front():
    buf = io.BytesIO()
    native_host.write_message(buf, {"type": "ping", "ünicode": "ğ"})
    raw = buf.getvalue()
    assert struct.unpack("<I", raw[:4])[0] == len(raw) - 4
    assert unpacked(raw) == [{"type": "ping", "ünicode": "ğ"}]


def test_a_closed_pipe_ends_the_conversation_and_a_huge_message_is_refused():
    assert native_host.read_message(io.BytesIO(b"")) is None
    assert native_host.read_message(io.BytesIO(b"\x05\x00\x00\x00ab")) is None          # cut short
    with pytest.raises(ValueError):
        native_host.read_message(io.BytesIO(struct.pack("<I", native_host.MAX_MESSAGE + 1)))


def test_the_browser_calls_are_recognised():
    assert native_host.is_host_call([ORIGIN])
    assert native_host.is_host_call([ORIGIN, "--parent-window=123"])
    assert native_host.is_host_call([r"C:\x\native_host_firefox.json", native_host.FIREFOX_ID])
    assert not native_host.is_host_call(["--minimized"]) and not native_host.is_host_call([])


# ----------------------------------------------------------------------------- answers
def test_a_running_diso_is_not_started_again():
    launched = []
    r = native_host.answer({"type": "launch", "port": 20000}, ping=lambda p: True, launch=lambda: launched.append(1))
    assert r == {"ok": True, "started": False} and launched == []


def test_a_closed_diso_is_started_and_the_host_waits_until_it_answers():
    clock, pings = Clock(), []

    def ping(port):
        pings.append(port)
        return clock.now >= 3                      # its bridge is up after 3 seconds
    r = native_host.answer({"type": "launch", "port": 20001}, ping=ping, launch=lambda: True, sleep=clock.sleep, clock=clock)
    assert r == {"ok": True, "started": True} and set(pings) == {20001}


def test_a_diso_that_does_not_come_up_is_reported():
    clock = Clock()
    r = native_host.answer({"type": "launch", "port": 20002}, ping=lambda p: False, launch=lambda: True,
                           wait=5, sleep=clock.sleep, clock=clock)
    assert r == {"ok": False, "error": "timeout"} and clock.now >= 5
    r = native_host.answer({"type": "launch", "port": 20002}, ping=lambda p: False, launch=lambda: False)
    assert r == {"ok": False, "error": "launch failed"}


def test_ping_unknown_and_broken_messages():
    r = native_host.answer({"type": "ping", "port": 20003}, ping=lambda p: False, launch=None)
    assert r == {"ok": True, "app": "DISO", "version": __version__, "running": False}
    assert native_host.answer({"type": "format c:"}, ping=None, launch=None)["error"] == "unknown message"
    assert native_host.answer([1, 2], ping=None, launch=None)["error"] == "bad message"


def test_a_port_that_makes_no_sense_falls_back_to_the_saved_one(monkeypatch):
    monkeypatch.setattr(native_host, "saved_port", lambda: 17999)
    seen = []
    native_host.answer({"type": "ping", "port": "1; rm"}, ping=seen.append, launch=None)
    native_host.answer({"type": "ping", "port": 80}, ping=seen.append, launch=None)
    assert seen == [17999, 17999]


def test_the_host_answers_every_message_until_the_pipe_closes():
    fin = io.BytesIO(packed({"type": "ping", "port": 20004}, {"type": "launch", "port": 20004}))
    fout = io.BytesIO()
    assert native_host.main([ORIGIN], streams=(fin, fout), ping=lambda p: True, launch=lambda: True) == 0
    answers = unpacked(fout.getvalue())
    assert [a["ok"] for a in answers] == [True, True] and answers[1]["started"] is False


def test_an_error_inside_becomes_an_answer_not_a_crash():
    def broken(port):
        raise RuntimeError("boom")
    fout = io.BytesIO()
    native_host.main([ORIGIN], streams=(io.BytesIO(packed({"type": "ping", "port": 20005})), fout), ping=broken, launch=None)
    assert unpacked(fout.getvalue()) == [{"ok": False, "error": "RuntimeError: boom"}]


def test_launching_steps_out_of_the_browsers_job_when_it_may():
    calls = []

    def popen(cmd, **kw):
        calls.append(kw["creationflags"])
        if kw["creationflags"] & native_host.BREAKAWAY:
            raise PermissionError("breakaway not allowed")
    assert native_host.launch(["C:\\x\\DISO.exe"], popen=popen) is True
    assert calls == [native_host.DETACHED_PROCESS | native_host.NEW_GROUP | native_host.BREAKAWAY,
                     native_host.DETACHED_PROCESS | native_host.NEW_GROUP]
    assert native_host.launch(["C:\\x\\DISO.exe"], popen=lambda *a, **k: (_ for _ in ()).throw(OSError())) is False


def test_from_source_the_app_is_started_with_python_and_main_py():
    cmd = native_host.app_command()
    assert len(cmd) == 2 and cmd[1].endswith("main.py") and os.path.isfile(cmd[1])


# ----------------------------------------------------------------------------- registration
@pytest.fixture
def prefix():
    p = rf"Software\DISOTest\native-{uuid.uuid4().hex[:8]}" + "\\"
    yield p
    from hizli_setup import core
    env = core.test_env(os.path.join(os.environ.get("TEMP", "."), "x"))
    env.reg_prefix = p
    core.delete_key_tree(env, p.rstrip("\\"))


def value(key):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
        return winreg.QueryValueEx(k, "")[0]


def test_every_browser_is_pointed_at_a_manifest_that_allows_only_our_extension(tmp_path, prefix):
    exe = str(tmp_path / "Prog" / "DISO.exe")
    keys = native_host.register(str(tmp_path / "Prog"), exe, winreg.HKEY_CURRENT_USER, prefix)
    assert len(keys) == 5 and all(k.startswith(prefix) and k.endswith(r"\com.iso.diso") for k in keys)
    chrome = json.load(open(value(prefix + r"Software\Google\Chrome\NativeMessagingHosts\com.iso.diso"), encoding="utf-8"))
    assert chrome == {"name": "com.iso.diso", "description": "DISO", "path": exe, "type": "stdio",
                      "allowed_origins": [ORIGIN]}
    firefox = json.load(open(value(prefix + r"Software\Mozilla\NativeMessagingHosts\com.iso.diso"), encoding="utf-8"))
    assert firefox["allowed_extensions"] == ["diso@iso.local"] and "allowed_origins" not in firefox
    assert value(prefix + r"Software\Microsoft\Edge\NativeMessagingHosts\com.iso.diso").endswith("native_host_chrome.json")


def test_unregistering_removes_only_what_leads_into_the_given_folder(tmp_path, prefix):
    native_host.register(str(tmp_path / "A"), str(tmp_path / "A" / "DISO.exe"), winreg.HKEY_CURRENT_USER, prefix)
    assert native_host.unregister(winreg.HKEY_CURRENT_USER, prefix, inside=str(tmp_path / "B")) == []   # another copy's
    removed = native_host.unregister(winreg.HKEY_CURRENT_USER, prefix, inside=str(tmp_path / "A"))
    assert len(removed) == 5
    assert native_host.registered_command(winreg.HKEY_CURRENT_USER, prefix + r"Software\Google\Chrome\NativeMessagingHosts\com.iso.diso") is None


def test_the_app_registers_itself_for_the_user_from_source_with_a_bat(tmp_path, prefix, monkeypatch):
    monkeypatch.delenv(native_host.NO_REGISTER_ENV)
    native_host.register_for_user(data_dir=str(tmp_path), hive=winreg.HKEY_CURRENT_USER, prefix=prefix)
    bat = tmp_path / "native_host" / "diso_host.bat"
    text = bat.read_bytes().decode("utf-8")
    assert text.startswith("@echo off\r\nchcp 65001 >nul\r\n") and "main.py" in text and "%*" in text
    assert native_host.registered_command(winreg.HKEY_CURRENT_USER,
                                          prefix + r"Software\Google\Chrome\NativeMessagingHosts\com.iso.diso") == str(bat)


# ----------------------------------------------------------------------------- a real process
def converse(command, *messages, timeout=60):
    done = subprocess.run(command, input=packed(*messages), capture_output=True, timeout=timeout)
    return done.returncode, unpacked(done.stdout), done.stderr


def free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_main_py_started_the_way_chrome_starts_it_talks_the_protocol():
    code, answers, err = converse([sys.executable, os.path.join(ROOT, "main.py"), ORIGIN, "--parent-window=0"],
                                  {"type": "ping", "port": free_port()})
    assert code == 0, err
    assert answers == [{"ok": True, "app": "DISO", "version": __version__, "running": False}]


def test_the_bat_the_app_registers_from_source_works_too(tmp_path, prefix, monkeypatch):
    monkeypatch.delenv(native_host.NO_REGISTER_ENV)
    native_host.register_for_user(data_dir=str(tmp_path), hive=winreg.HKEY_CURRENT_USER, prefix=prefix)
    bat = str(tmp_path / "native_host" / "diso_host.bat")
    code, answers, err = converse(["cmd.exe", "/d", "/c", bat, ORIGIN], {"type": "ping", "port": free_port()})
    assert code == 0, err
    assert answers and answers[0]["ok"] is True and answers[0]["version"] == __version__

def test_tests_never_register_a_throw_away_copy():
    assert os.environ.get(native_host.NO_REGISTER_ENV) == "1"
    assert native_host.register_for_user(data_dir="C:\\nowhere") == []

def test_a_copy_installed_in_a_pretend_computer_never_registers(monkeypatch):
    from hizli_setup import core
    assert native_host.SETUP_TEST_ENV == core.TEST_ROOT_ENV
    monkeypatch.delenv(native_host.NO_REGISTER_ENV)
    monkeypatch.setenv(native_host.SETUP_TEST_ENV, "C:\\pretend")
    assert native_host.register_for_user(data_dir="C:\\nowhere") == []
