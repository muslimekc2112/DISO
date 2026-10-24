"""Starting the program again after it closed (the look is chosen at start-up)."""
import os
import sys

from app import restart


def test_the_command_for_a_python_start(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd = restart.command(["--minimized"])
    assert cmd[0] == sys.executable and cmd[1].endswith("main.py") and os.path.isfile(cmd[1])
    assert cmd[2:] == ["--minimized"]


def test_the_command_for_the_exe(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\apps\DISO.exe")
    assert restart.command([]) == [r"C:\apps\DISO.exe"]
    assert restart.command(["--minimized"]) == [r"C:\apps\DISO.exe", "--minimized"]


def test_relaunch_starts_a_detached_copy_that_knows_it_is_a_restart(monkeypatch):
    seen = {}

    def fake_popen(cmd, **kw):
        seen.update(cmd=cmd, **kw)

    monkeypatch.setattr(restart.subprocess, "Popen", fake_popen)
    assert restart.relaunch(["--minimized"]) is True
    assert seen["cmd"][-1] == "--minimized"
    assert seen["env"][restart.RESTART_ENV] == "1"
    assert seen["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"        # a one-file exe unpacks itself again
    assert RESTART_ENV_NOT_LEAKED()
    if os.name == "nt":
        assert seen["creationflags"] & 0x00000008                     # detached: it outlives this process


def RESTART_ENV_NOT_LEAKED():
    return restart.RESTART_ENV not in os.environ


def test_a_start_that_fails_is_reported(monkeypatch):
    def broken(*a, **k):
        raise OSError("no such file")
    monkeypatch.setattr(restart.subprocess, "Popen", broken)
    assert restart.relaunch([]) is False


def test_a_normal_start_never_waits(monkeypatch):
    monkeypatch.delenv(restart.RESTART_ENV, raising=False)
    assert restart.wait_for_previous(lambda: True, timeout=0.2) is True


def test_a_restart_waits_until_the_old_window_is_gone(monkeypatch):
    monkeypatch.setenv(restart.RESTART_ENV, "1")
    answers = iter([True, True, False])
    assert restart.wait_for_previous(lambda: next(answers), timeout=5, step=0.01) is True
    assert restart.RESTART_ENV not in os.environ                      # the next start is a normal one


def test_a_restart_gives_up_if_the_old_window_never_closes(monkeypatch):
    monkeypatch.setenv(restart.RESTART_ENV, "1")
    assert restart.wait_for_previous(lambda: True, timeout=0.1, step=0.01) is False
