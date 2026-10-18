"""Setup.exe and Uninstall.exe without a window (--silent), and how Uninstall hands over to a copy."""
import os
import shutil
import subprocess
import sys
import time

import pytest
from setup_support import Closer, make_payload

from hizli_setup import cli, core, winapi

pytestmark = pytest.mark.skipif(not winapi.WINDOWS, reason="Windows only")
SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")


@pytest.fixture
def package(tmp_path):
    return make_payload(tmp_path / "paket")


@pytest.fixture
def env(tmp_path):
    e = core.test_env(str(tmp_path / "dunya"))
    yield e
    core.delete_key_tree(e, e.reg_prefix.rstrip("\\"))


@pytest.fixture
def logs(tmp_path):
    folder = tmp_path / "loglar"
    folder.mkdir()
    return str(folder)


def read_log(folder, name):
    path = os.path.join(folder, name)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def silent_setup(env, logs, *args, closer=None):
    return cli.setup_main(["--silent", *args], env=env, closer=closer or Closer(), log_folder=logs)


# ------------------------------------------------------------------------------ setup
def test_a_silent_install_does_everything_and_says_so_in_the_log(package, env, logs, tmp_path):
    target = tmp_path / "Kurulum Yeri"
    assert silent_setup(env, logs, "--payload", str(package), "--dir", str(target)) == 0
    assert (target / "DISO.exe").is_file() and (target / "Uninstall.exe").is_file()
    assert (target / "deno" / "deno.exe").is_file()
    assert os.path.isfile(os.path.join(env.start_menu_dir, core.SHORTCUT_NAME))
    assert core.find_existing(env) == (str(target), "1.2.0")
    log = read_log(logs, "DISO-kurulum.log")
    assert "setup started" in log and "installed 1.2.0" in log


def test_without_a_folder_it_uses_the_usual_place(package, env, logs):
    assert silent_setup(env, logs, "--payload", str(package)) == 0
    assert os.path.isfile(os.path.join(env.default_install_dir, "DISO.exe"))


def test_the_switches_work(package, env, logs, tmp_path):
    target = tmp_path / "x"
    assert silent_setup(env, logs, "--payload", str(package), "--dir", str(target), "--no-desktop",
                        "--no-start-menu", "--autostart") == 0
    assert not os.path.exists(os.path.join(env.desktop_dir, core.SHORTCUT_NAME))
    assert not os.path.exists(env.start_menu_dir)
    assert core._read_value(env, env.run_key, "DISO") == f'"{target / "DISO.exe"}" --minimized'


def test_the_nsis_style_switch_and_unknown_switches_are_accepted(package, env, logs, tmp_path):
    assert cli.setup_main(["/S", "--payload", str(package), "--dir", str(tmp_path / "y"), "--bilinmeyen", "x"],
                          env=env, closer=Closer(), log_folder=logs) == 0


def test_an_update_goes_into_the_folder_of_the_installed_copy(tmp_path, env, logs):
    v1 = make_payload(tmp_path / "v1", version="1.0.0", seed=b"1")
    v2 = make_payload(tmp_path / "v2", version="2.0.0", seed=b"2")
    home = tmp_path / "Benim Yerim"
    assert silent_setup(env, logs, "--payload", str(v1), "--dir", str(home)) == 0
    assert silent_setup(env, logs, "--payload", str(v2)) == 0                 # no --dir: where it already is
    assert core.find_existing(env) == (str(home), "2.0.0")
    assert not os.path.exists(env.default_install_dir)


def test_a_damaged_package_fails_with_code_2_and_leaves_nothing(package, env, logs, tmp_path):
    (package / "deno.exe").write_bytes(b"broken")
    target = tmp_path / "z"
    assert silent_setup(env, logs, "--payload", str(package), "--dir", str(target)) == 2
    assert not target.exists() and core.find_existing(env) == (None, None)
    assert "install failed" in read_log(logs, "DISO-kurulum.log")


def test_a_missing_package_and_a_bad_folder_fail_cleanly(env, logs, package, tmp_path):
    assert silent_setup(env, logs, "--payload", str(tmp_path / "yok"), "--dir", str(tmp_path / "a")) == 2
    assert silent_setup(env, logs, "--payload", str(package), "--dir", "bagil\\yol") == 2


def test_an_unexpected_crash_is_logged_and_gives_code_1(package, env, logs, monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("beklenmeyen")

    monkeypatch.setattr(core, "install", boom)
    assert silent_setup(env, logs, "--payload", str(package), "--dir", str(tmp_path / "q")) == 1
    assert "beklenmeyen" in read_log(logs, "DISO-kurulum.log")


def test_a_second_setup_at_the_same_time_steps_aside(package, env, logs, tmp_path):
    lock = winapi.single_instance("Local\\DISO-Setup")
    try:
        assert silent_setup(env, logs, "--payload", str(package), "--dir", str(tmp_path / "w")) == 4
        assert not (tmp_path / "w").exists()
    finally:
        winapi.release_instance(lock)
    assert silent_setup(env, logs, "--payload", str(package), "--dir", str(tmp_path / "w")) == 0     # lock was released


def test_the_launch_switch_starts_the_installed_program(package, env, logs, tmp_path, monkeypatch):
    started = []
    from hizli_setup import ui
    monkeypatch.setattr(ui, "launch", lambda exe: started.append(exe) or True)
    assert silent_setup(env, logs, "--payload", str(package), "--dir", str(tmp_path / "l"), "--launch") == 0
    assert started == [str(tmp_path / "l" / "DISO.exe")]


def test_the_payload_is_looked_for_beside_the_program_when_not_given(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", r"C:\Temp\_MEI123", raising=False)
    assert cli.default_payload_dir() == os.path.join(r"C:\Temp\_MEI123", "payload")
    monkeypatch.delattr(sys, "frozen")
    assert cli.default_payload_dir().endswith(os.path.join("build", "payload"))


# ------------------------------------------------------------------------------ uninstall: stage 1
@pytest.fixture
def installed(package, env, logs, tmp_path):
    target = tmp_path / "Kurulu"
    assert silent_setup(env, logs, "--payload", str(package), "--dir", str(target)) == 0
    return target


class FakeProc:
    """A started program: running (code None) or ended with a code."""

    def __init__(self, code=None):
        self.returncode = code

    def poll(self):
        return self.returncode


def test_the_uninstaller_first_makes_a_copy_of_itself_elsewhere(installed, env, logs):
    launched = []
    proc = FakeProc()
    code = cli.uninstall_main([], env=env, self_path=str(installed / "Uninstall.exe"), log_folder=logs,
                              launcher=lambda path, args: launched.append((path, args)) or proc)
    assert code == 0                                                       # the window case: hand over and leave at once
    copy, args = launched[0]
    assert os.path.isfile(copy) and not core.inside(copy, str(installed)) and copy.endswith(".exe")
    assert args[:5] == ["--stage2", "--dir", str(installed), "--self-delete", copy]
    assert "--silent" not in args and "--result" not in args and args[args.index("--parent-pid") + 1] == str(os.getpid())
    os.remove(copy)


def test_a_silent_uninstall_waits_for_the_answer_the_copy_writes(installed, env, logs):
    launched = []

    def launcher(path, args):
        launched.append((path, args))
        cli.write_result(args[args.index("--result") + 1], 0)               # the copy reports, but keeps running
        return FakeProc()                                                  # (it waits for us to leave)

    code = cli.uninstall_main(["--silent", "--remove-data"], env=env, self_path=str(installed / "Uninstall.exe"),
                              log_folder=logs, launcher=launcher)
    assert code == 0
    path, args = launched[0]
    assert "--silent" in args and "--remove-data" in args and not os.path.exists(args[args.index("--result") + 1])
    os.remove(path)


def test_a_silent_uninstall_whose_copy_ends_without_an_answer_gives_the_copys_code(installed, env, logs):
    launched = []
    code = cli.uninstall_main(["--silent"], env=env, self_path=str(installed / "Uninstall.exe"), log_folder=logs,
                              launcher=lambda path, args: launched.append((path, args)) or FakeProc(code=2))
    assert code == 2
    os.remove(launched[0][0])


def test_waiting_for_an_answer_gives_up_eventually(tmp_path):
    ticks = iter(range(0, 1000, 100))
    assert cli.wait_for_result(str(tmp_path / "never"), FakeProc(), timeout=250, sleep=lambda s: None,
                               now=lambda: next(ticks)) == 1
    (tmp_path / "bad.json").write_text("{half", encoding="utf-8")            # a half-written answer is looked at again
    ticks = iter(range(0, 1000, 100))
    assert cli.wait_for_result(str(tmp_path / "bad.json"), FakeProc(code=3), timeout=1000, sleep=lambda s: None,
                               now=lambda: next(ticks)) == 3


def test_the_uninstaller_finds_the_install_through_the_registry_when_its_own_folder_has_no_list(installed, env, logs, tmp_path):
    stray = tmp_path / "irgendwo"
    stray.mkdir()
    shutil.copy(installed / "Uninstall.exe", stray / "Uninstall.exe")
    launched = []
    cli.uninstall_main([], env=env, self_path=str(stray / "Uninstall.exe"), log_folder=logs,
                       launcher=lambda path, args: launched.append((path, args)) or None)
    assert launched[0][1][2] == str(installed)
    os.remove(launched[0][0])


def test_the_uninstaller_with_no_installation_around_says_so(tmp_path, env, logs):
    lone = tmp_path / "lone"
    lone.mkdir()
    (lone / "Uninstall.exe").write_bytes(b"MZ")
    assert cli.uninstall_main(["--silent"], env=env, self_path=str(lone / "Uninstall.exe"), log_folder=logs,
                              launcher=lambda *a: pytest.fail("must not start")) == 3
    assert "no installation found" in read_log(logs, "DISO-kaldirma.log")


def test_a_copy_that_cannot_be_made_is_reported(installed, env, logs, monkeypatch):
    def broken(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(cli.shutil, "copy2", broken)
    assert cli.uninstall_main(["--silent"], env=env, self_path=str(installed / "Uninstall.exe"), log_folder=logs,
                              launcher=lambda *a: pytest.fail("must not start")) == 1


# ------------------------------------------------------------------------------ uninstall: stage 2
def stage2(env, logs, installed, *extra, deleted=None, closer=None):
    deleted = deleted if deleted is not None else []
    return cli.uninstall_main(["--stage2", "--silent", "--dir", str(installed), "--self-delete", r"C:\Temp\kopya.exe", *extra],
                              env=env, closer=closer or Closer(), log_folder=logs, delete_later=deleted.append)


def test_the_copy_removes_the_program_and_deletes_itself_afterwards(installed, env, logs):
    deleted = []
    assert stage2(env, logs, installed, deleted=deleted) == 0
    assert not installed.exists() and core.find_existing(env) == (None, None)
    assert deleted == [r"C:\Temp\kopya.exe"]


def test_the_data_is_kept_unless_the_switch_is_given(installed, env, logs):
    os.makedirs(env.user_data_dir)
    open(os.path.join(env.user_data_dir, "playlists.json"), "w").write("{}")
    assert stage2(env, logs, installed) == 0
    assert os.path.isfile(os.path.join(env.user_data_dir, "playlists.json"))
    cli_installed = installed
    assert silent_setup(env, logs, "--payload", str(installed.parent / "paket"), "--dir", str(cli_installed)) == 0
    assert stage2(env, logs, installed, "--remove-data") == 0
    assert not os.path.exists(env.user_data_dir)


def test_a_crash_in_the_removal_gives_code_1_and_still_cleans_the_copy(installed, env, logs, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("beklenmeyen")

    monkeypatch.setattr(core, "uninstall", boom)
    deleted = []
    assert stage2(env, logs, installed, deleted=deleted) == 1 and deleted == [r"C:\Temp\kopya.exe"]


def test_two_removals_at_once_the_second_steps_aside(installed, env, logs):
    lock = winapi.single_instance("Local\\DISO-Uninstall")
    deleted = []
    try:
        assert stage2(env, logs, installed, deleted=deleted) == 4
        assert installed.exists() and deleted == [r"C:\Temp\kopya.exe"]
    finally:
        winapi.release_instance(lock)


# ------------------------------------------------------------------------------ deleting a running copy
def test_a_program_file_is_deleted_after_it_has_ended(tmp_path):
    copy = tmp_path / "kopya.exe"
    shutil.copy(os.path.join(SYSTEM32, "ping.exe"), copy)
    p = subprocess.Popen([str(copy), "-n", "3", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x08000000)
    assert cli.schedule_self_delete(str(copy)) is True
    time.sleep(0.5)
    assert copy.exists()                                                  # still running: cannot be deleted yet
    p.wait(timeout=20)
    end = time.time() + 15
    while copy.exists() and time.time() < end:
        time.sleep(0.3)
    assert not copy.exists()


def test_scheduling_a_delete_that_cannot_start_is_reported():
    def refuse(*a, **k):
        raise OSError("no cmd")

    assert cli.schedule_self_delete(r"C:\x.exe", runner=refuse) is False
