"""The uninstaller must not be in its own way: it keeps its own file for last, never closes itself, and
tells the process that started it how the removal went."""
import json
import os
import shutil
import subprocess
import threading
import time

import pytest
from setup_support import Closer, make_payload

from hizli_setup import cli, core, ui, winapi

pytestmark = pytest.mark.skipif(not winapi.WINDOWS, reason="Windows only")
SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
NO_WINDOW = 0x08000000


@pytest.fixture
def env(tmp_path):
    e = core.test_env(str(tmp_path / "dunya"))
    yield e
    core.delete_key_tree(e, e.reg_prefix.rstrip("\\"))


@pytest.fixture
def installed(tmp_path, env):
    target = tmp_path / "Kurulu"
    core.install(make_payload(tmp_path / "paket"), core.Options(install_dir=str(target)), env, closer=Closer())
    return target


@pytest.fixture
def logs(tmp_path):
    (tmp_path / "log").mkdir()
    return str(tmp_path / "log")


def tree(folder):
    return sorted(os.path.relpath(os.path.join(r, f), folder) for r, _, fs in os.walk(folder) for f in fs)


def wait_until(cond, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def ping(path, seconds):
    """A real process that lives about `seconds` seconds, under the name given."""
    shutil.copy(os.path.join(SYSTEM32, "ping.exe"), path)
    return subprocess.Popen([str(path), "-n", str(seconds + 1), "127.0.0.1"], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)


# ------------------------------------------------------------------------------ core: keep
def test_keep_leaves_the_named_file_the_list_and_the_folder_for_a_second_call(installed, env):
    result = core.uninstall(str(installed), env, closer=Closer(), keep=["Uninstall.exe"])
    assert result.leftovers == []
    assert tree(installed) == ["Uninstall.exe", "install.json"]                  # everything else is gone
    assert core.find_existing(env) == (None, None) and not os.path.exists(env.start_menu_dir)
    core.uninstall(str(installed), env, closer=Closer())                           # the second call finishes the job
    assert not installed.exists()


def test_a_folder_left_half_removed_can_be_finished_later(installed, env):
    core.uninstall(str(installed), env, closer=Closer(), keep=["Uninstall.exe"])
    manifest = core.read_manifest(str(installed))
    assert manifest and "Uninstall.exe" in manifest["files"]


# ------------------------------------------------------------------------------ winapi
def test_closing_skips_the_programs_it_was_told_to_ignore(tmp_path):
    folder = tmp_path / "Kurulum"
    folder.mkdir()
    app = ping(folder / "DISO.exe", 30)
    remover = ping(folder / "Uninstall.exe", 30)
    try:
        assert wait_until(lambda: len(winapi.processes_in(str(folder))) == 2)
        assert [os.path.basename(p) for _, _, p in winapi.processes_in(str(folder), ignore_names=("UNINSTALL.EXE",))] == ["DISO.exe"]
        forced = winapi.close_programs_in(str(folder), grace=0.5, ignore_names=("uninstall.exe",))
        assert forced == 1 and wait_until(lambda: app.poll() is not None)
        assert remover.poll() is None                                              # the uninstaller itself was left alone
    finally:
        for p in (app, remover):
            if p.poll() is None:
                p.kill()


def test_waiting_for_a_process_to_end(tmp_path):
    quick = ping(tmp_path / "kisa.exe", 1)
    started = time.time()
    assert winapi.wait_for_exit(quick.pid, timeout=15) is True and time.time() - started < 10
    slow = ping(tmp_path / "uzun.exe", 30)
    try:
        assert winapi.wait_for_exit(slow.pid, timeout=0.4) is False                # still running: gives up
    finally:
        slow.kill()
    assert winapi.wait_for_exit(None) is True and winapi.wait_for_exit(0) is True
    assert winapi.wait_for_exit(4_000_000_000 % 2 ** 31 or 999999, timeout=0.2) is True      # not a process any more


# ------------------------------------------------------------------------------ stage 2
def stage2(env, logs, installed, *extra, closer=None, deleted=None):
    deleted = deleted if deleted is not None else []
    return cli.uninstall_main(["--stage2", "--silent", "--dir", str(installed), "--self-delete", r"C:\Temp\kopya.exe", *extra],
                              env=env, closer=closer or Closer(), log_folder=logs, delete_later=deleted.append)


def test_the_copy_reports_first_then_waits_for_the_first_process_then_finishes(installed, env, logs, tmp_path):
    parent = ping(tmp_path / "ebeveyn.exe", 4)
    result_file = str(tmp_path / "sonuc.result")
    out = {}

    def run():
        out["code"] = stage2(env, logs, installed, "--result", result_file, "--parent-pid", str(parent.pid))

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert wait_until(lambda: os.path.isfile(result_file), 20)
        assert json.load(open(result_file, encoding="utf-8")) == {"code": 0}
        assert tree(installed) == ["Uninstall.exe", "install.json"]               # the first process still holds its file
        assert thread.is_alive()                                                   # ... so the copy waits
    finally:
        thread.join(timeout=40)
    assert out["code"] == 0 and not installed.exists() and not thread.is_alive()


def test_a_failed_removal_is_reported_and_leaves_things_as_they_are(installed, env, logs, monkeypatch, tmp_path):
    calls = []

    def failing(*a, **k):
        calls.append(1)
        raise core.SetupError("Bir dosya silinemedi")

    monkeypatch.setattr(core, "uninstall", failing)
    deleted = []
    result_file = str(tmp_path / "sonuc.result")
    assert stage2(env, logs, installed, "--result", result_file, deleted=deleted) == 2
    assert json.load(open(result_file, encoding="utf-8")) == {"code": 2}
    assert len(calls) == 1 and deleted == [r"C:\Temp\kopya.exe"]                  # no "last step" after a failure
    assert (installed / "install.json").is_file()                                  # still there to try again


def test_a_second_removal_reports_that_it_stepped_aside(installed, env, logs, tmp_path):
    lock = winapi.single_instance(cli.UNINSTALL_LOCK)
    result_file = str(tmp_path / "sonuc.result")
    try:
        assert stage2(env, logs, installed, "--result", result_file) == 4
        assert json.load(open(result_file, encoding="utf-8")) == {"code": 4}
        assert installed.exists()
    finally:
        winapi.release_instance(lock)


def test_the_default_closer_never_closes_the_uninstaller(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli.winapi, "close_programs_in", lambda folder, **kw: seen.update(folder=folder, **kw) or 0)
    assert cli.close_others(r"C:\Kurulu") == 0
    assert seen == {"folder": r"C:\Kurulu", "ignore_names": ("uninstall.exe",)}


def test_the_stage_two_in_a_silent_run_uses_that_closer_by_default(installed, env, logs, monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "close_others", lambda folder: seen.append(folder) or 0)
    assert cli.uninstall_main(["--stage2", "--silent", "--dir", str(installed)], env=env, log_folder=logs,
                              delete_later=lambda p: None) == 0
    assert seen == [str(installed)]


# ------------------------------------------------------------------------------ the window
@pytest.mark.gui
def test_the_window_leaves_the_uninstaller_for_the_last_step(installed, env):
    from app import look
    look.apply("Yeni")
    try:
        w = ui.UninstallWindow(str(installed), env, closer=Closer(), keep=["Uninstall.exe"])
    except Exception as e:  # noqa: BLE001 - no display
        pytest.skip(f"no display: {e}")
    try:
        w.withdraw()
        w.start()
        end = time.time() + 20
        while w.result is None and time.time() < end:
            w.update()
            time.sleep(0.02)
        assert w.exit_code == 0 and tree(installed) == ["Uninstall.exe", "install.json"]
    finally:
        w.destroy()
        look.apply("Klasik")
