import base64
import sys
import types

from app import notify
from conftest import wait_for


class _Done:
    returncode = 0


def test_toast_hands_title_and_text_to_powershell_through_the_environment(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["env"] = cmd, kw["env"]
        return _Done()

    monkeypatch.setattr(notify, "_WIN", True)
    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    assert notify.show_toast('Başlık "tırnaklı"', "Metin <b> & şeyler") == 0
    assert seen["env"]["HI_TITLE"] == 'Başlık "tırnaklı"' and seen["env"]["HI_BODY"] == "Metin <b> & şeyler"
    assert "-EncodedCommand" in seen["cmd"]
    script = base64.b64decode(seen["cmd"][seen["cmd"].index("-EncodedCommand") + 1]).decode("utf-16-le")
    assert "ToastNotificationManager" in script and "$env:HI_TITLE" in script


def test_toast_survives_powershell_failing(monkeypatch):
    def broken(cmd, **kw):
        raise FileNotFoundError("powershell.exe")

    monkeypatch.setattr(notify, "_WIN", True)
    monkeypatch.setattr(notify.subprocess, "run", broken)
    assert notify.show_toast("a", "b") == -1


def test_toast_does_nothing_off_windows(monkeypatch):
    monkeypatch.setattr(notify, "_WIN", False)
    monkeypatch.setattr(notify, "toast_command", lambda title, body: None)   # no notify-send / osascript
    assert notify.show_toast("a", "b") == -1


def test_toast_runs_in_the_background(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "show_toast", lambda t, b: calls.append((t, b)) or 0)
    notify.toast("T", "B")
    assert wait_for(lambda: calls == [("T", "B")])


def test_sound_uses_the_right_system_sound(monkeypatch):
    beeps = []
    stub = types.SimpleNamespace(MB_ICONASTERISK=64, MB_ICONHAND=16, MessageBeep=beeps.append)
    monkeypatch.setitem(sys.modules, "winsound", stub)
    monkeypatch.setattr(notify, "_WIN", True)
    notify.play_sound("done")
    notify.play_sound("error")
    assert beeps == [64, 16]


def test_sound_never_raises(monkeypatch):
    def boom(_):
        raise RuntimeError("no sound card")

    stub = types.SimpleNamespace(MB_ICONASTERISK=64, MB_ICONHAND=16, MessageBeep=boom)
    monkeypatch.setitem(sys.modules, "winsound", stub)
    monkeypatch.setattr(notify, "_WIN", True)
    notify.play_sound("done")


def test_power_actions_start_the_right_windows_commands(monkeypatch):
    started = []
    monkeypatch.setattr(notify, "_WIN", True)
    monkeypatch.setattr(notify.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    assert notify.power_action("shutdown") is True
    assert notify.power_action("sleep") is True
    assert started == [["shutdown", "/s", "/t", "5"],
                       ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]]


def test_unknown_power_action_does_nothing(monkeypatch):
    started = []
    monkeypatch.setattr(notify.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    assert notify.power_action("close") is False        # "close" belongs to the window
    assert notify.power_action("explode") is False
    assert started == []


def test_power_action_reports_failure(monkeypatch):
    def broken(cmd, **kw):
        raise OSError("denied")

    monkeypatch.setattr(notify.subprocess, "Popen", broken)
    assert notify.power_action("shutdown") is False
