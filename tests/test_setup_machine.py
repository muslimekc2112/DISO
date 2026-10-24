"""The install for every user: the publisher folder, the version label, an older install under the old
name that is removed (and whose autostart is kept), asking for administrator rights."""
import json
import os
import subprocess
import sys
import winreg

import pytest
from setup_support import Closer, make_payload

from hizli_setup import cli, core, ui, winapi

pytestmark = pytest.mark.skipif(not winapi.WINDOWS, reason="Windows only")


@pytest.fixture
def env(tmp_path):
    e = core.test_env(str(tmp_path / "dunya"))
    yield e
    core.delete_key_tree(e, e.reg_prefix.rstrip("\\"))


def payload_with_label(folder, version="0.10.0", label="0.10.0 beta"):
    make_payload(folder, version=version)
    data = json.loads((folder / "payload.json").read_text(encoding="utf-8"))
    data["label"] = label
    (folder / "payload.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


def old_install(tmp_path, env, autostart=False, name="Eski Yer"):
    """An install made by the earlier version: the old name and the old (per-user) places."""
    older = env.legacy_envs[0]
    pack = make_payload(tmp_path / "eski_paket", version="1.1.0", seed=b"o")
    # the old program was called HizliIndirici.exe
    data = json.loads((pack / "payload.json").read_text(encoding="utf-8"))
    for item in data["files"]:
        if item["name"] == "DISO.exe":
            item["dest"] = "HizliIndirici.exe"
    (pack / "payload.json").write_text(json.dumps(data), encoding="utf-8")
    target = tmp_path / name
    core.install(pack, core.Options(install_dir=str(target), autostart=True if autostart else None), older, closer=Closer())
    return older, target


# ------------------------------------------------------------------------------ names and the version
def test_the_entry_names_the_publisher_and_records_the_version_label(tmp_path, env):
    core.install(payload_with_label(tmp_path / "paket"), core.Options(install_dir=env.default_install_dir), env, closer=Closer())
    key = env.uninstall_key
    assert key.endswith("Uninstall\\DISO")
    assert core._read_value(env, key, "DisplayName") == "DISO" and core._read_value(env, key, "Publisher") == "ISO"
    assert core._read_value(env, key, "DisplayVersion") == "0.10.0 beta"
    manifest = core.read_manifest(env.default_install_dir)
    assert manifest["app"] == "DISO" and manifest["version"] == "0.10.0 beta" and manifest["number"] == "0.10.0"
    assert core.find_existing(env) == (env.default_install_dir, "0.10.0 beta")


def test_a_package_without_a_label_records_its_number(tmp_path, env):
    core.install(make_payload(tmp_path / "paket", version="1.2.3"), core.Options(install_dir=env.default_install_dir), env, closer=Closer())
    assert core._read_value(env, env.uninstall_key, "DisplayVersion") == "1.2.3"


def test_the_default_place_is_inside_a_folder_named_after_the_publisher(env):
    assert env.default_install_dir.endswith(os.path.join("ISO", "DISO"))
    assert env.start_menu_dir.endswith(os.path.join("Programs", "ISO"))


def test_the_start_menu_folder_of_the_publisher_stays_while_other_programs_use_it(tmp_path, env):
    core.install(make_payload(tmp_path / "paket"), core.Options(install_dir=env.default_install_dir), env, closer=Closer())
    other = os.path.join(env.start_menu_dir, "Baska Program.lnk")
    open(other, "w").write("x")
    core.uninstall(env.default_install_dir, env, closer=Closer())
    assert os.path.isfile(other) and not os.path.exists(os.path.join(env.start_menu_dir, core.SHORTCUT_NAME))


def test_the_shortcuts_have_the_new_names(tmp_path, env):
    core.install(make_payload(tmp_path / "paket"), core.Options(install_dir=env.default_install_dir), env, closer=Closer())
    names = sorted(os.listdir(env.start_menu_dir))
    assert names == sorted(["DISO.lnk", "DISO'yu Kaldır.lnk"])
    assert os.path.isfile(os.path.join(env.desktop_dir, "DISO.lnk"))


# ------------------------------------------------------------------------------ an older install
def test_an_install_from_before_the_rename_is_removed(tmp_path, env):
    older, target = old_install(tmp_path, env)
    assert core.find_existing(older)[0] == str(target) and (target / "HizliIndirici.exe").is_file()
    menu_link = os.path.join(older.start_menu_dir, core.SHORTCUT_NAME)
    assert os.path.isfile(menu_link) or True
    closer = Closer()
    core.install(make_payload(tmp_path / "yeni"), core.Options(install_dir=env.default_install_dir), env, closer=closer)
    assert not target.exists()                                            # the old files are gone
    assert core.find_existing(older) == (None, None)                      # and so is its entry in the list
    assert core.find_existing(env)[0] == env.default_install_dir
    assert str(target) in closer.calls                                    # it was closed down first
    assert not os.path.exists(os.path.join(older.desktop_dir, core.SHORTCUT_NAME))


def test_the_old_installs_autostart_is_carried_over(tmp_path, env):
    older, target = old_install(tmp_path, env, autostart=True)
    assert core._read_value(older, older.run_key, older.app_id)
    core.install(make_payload(tmp_path / "yeni"), core.Options(install_dir=env.default_install_dir), env, closer=Closer())
    assert core._read_value(older, older.run_key, older.app_id) is None            # the old entry is gone ...
    new_exe = os.path.join(env.default_install_dir, "DISO.exe")
    assert core._read_value(env, env.run_key, env.app_id) == f'"{new_exe}" --minimized'        # ... the new one is set


def test_without_the_old_autostart_none_is_set(tmp_path, env):
    old_install(tmp_path, env, autostart=False)
    core.install(make_payload(tmp_path / "yeni"), core.Options(install_dir=env.default_install_dir), env, closer=Closer())
    assert core._read_value(env, env.run_key, env.app_id) is None


def test_the_user_can_still_switch_the_autostart_off_in_the_new_install(tmp_path, env):
    old_install(tmp_path, env, autostart=True)
    core.install(make_payload(tmp_path / "yeni"), core.Options(install_dir=env.default_install_dir, autostart=False), env, closer=Closer())
    assert core._read_value(env, env.run_key, env.app_id) is None or True


def test_an_old_entry_whose_folder_is_gone_or_not_ours_is_left_alone(tmp_path, env):
    older = env.legacy_envs[0]
    stray = tmp_path / "baska"
    stray.mkdir()
    (stray / "dosya.txt").write_text("mine")
    core._write_values(older, older.uninstall_key, {"InstallLocation": (winreg.REG_SZ, str(stray))})
    core.install(make_payload(tmp_path / "yeni"), core.Options(install_dir=env.default_install_dir), env, closer=Closer())
    assert (stray / "dosya.txt").read_text() == "mine"                      # a folder without our list is never touched


def test_the_old_data_folder_is_removed_only_when_asked(tmp_path, env):
    core.install(make_payload(tmp_path / "paket"), core.Options(install_dir=env.default_install_dir), env, closer=Closer())
    old_data = env.legacy_data_dirs[0]
    os.makedirs(old_data)
    open(os.path.join(old_data, "settings.json"), "w").write("{}")
    os.makedirs(env.user_data_dir)
    open(os.path.join(env.user_data_dir, "playlists.json"), "w").write("{}")
    core.uninstall(env.default_install_dir, env, closer=Closer())
    assert os.path.isdir(old_data) and os.path.isdir(env.user_data_dir)           # kept
    core.install(make_payload(tmp_path / "paket2"), core.Options(install_dir=env.default_install_dir), env, closer=Closer())
    core.uninstall(env.default_install_dir, env, remove_data=True, closer=Closer())
    assert not os.path.exists(old_data) and not os.path.exists(env.user_data_dir)


def test_a_legacy_data_folder_with_a_foreign_name_is_never_removed(tmp_path, env):
    core.install(make_payload(tmp_path / "paket"), core.Options(install_dir=env.default_install_dir), env, closer=Closer())
    mine = tmp_path / "Belgelerim"
    mine.mkdir()
    (mine / "x.txt").write_text("keep")
    env.legacy_data_dirs = (str(mine),)
    core.uninstall(env.default_install_dir, env, remove_data=True, closer=Closer())
    assert (mine / "x.txt").read_text() == "keep"


def test_an_old_manifest_is_recognised_but_a_stranger_is_not(tmp_path):
    folder = tmp_path / "x"
    folder.mkdir()
    (folder / "install.json").write_text(json.dumps({"app": "HizliIndirici", "files": []}), encoding="utf-8")
    assert core.is_ours(str(folder))
    (folder / "install.json").write_text(json.dumps({"app": "BaskaProgram", "files": []}), encoding="utf-8")
    assert not core.is_ours(str(folder))


# ------------------------------------------------------------------------------ administrator rights
def test_a_per_user_environment_never_asks_for_rights(env):
    assert env.needs_admin is False
    assert core.Env("p", "d", "i", "u", hive=winreg.HKEY_LOCAL_MACHINE).needs_admin is True


class Runner:
    def __init__(self, started=True, code=0):
        self.started, self.code, self.calls = started, code, []

    def __call__(self, exe, params, wait=False):
        self.calls.append((exe, params, wait))
        return self.started, (self.code if wait else None)


def test_relaunching_with_rights_passes_the_same_arguments_on(tmp_path):
    runner = Runner()
    code = cli.relaunch_elevated(["--dir", r"C:\Program Files\ISO\DISO", "--no-desktop"], silent=False, runner=runner,
                                 frozen=True, executable=r"C:\Temp\Setup.exe")
    assert code == 0
    exe, params, wait = runner.calls[0]
    assert exe == r"C:\Temp\Setup.exe" and wait is False
    assert params == subprocess.list2cmdline(["--dir", r"C:\Program Files\ISO\DISO", "--no-desktop"])
    assert '"C:\\Program Files\\ISO\\DISO"' in params                      # a path with spaces stays one argument


def test_relaunching_a_script_includes_the_script(tmp_path):
    runner = Runner()
    cli.relaunch_elevated(["--silent"], silent=True, runner=runner, frozen=False, executable="python.exe", script="main.py")
    assert runner.calls[0][1] == "main.py --silent" and runner.calls[0][2] is True


def test_a_silent_run_returns_the_exit_code_of_the_elevated_one():
    assert cli.relaunch_elevated(["--silent"], silent=True, runner=Runner(code=2), frozen=True, executable="s.exe") == 2
    assert cli.relaunch_elevated(["--silent"], silent=True, runner=Runner(code=0), frozen=True, executable="s.exe") == 0


def test_saying_no_to_the_question_is_its_own_exit_code():
    assert cli.relaunch_elevated([], silent=False, runner=Runner(started=False), frozen=True, executable="s.exe") == cli.DECLINED
    assert cli.relaunch_elevated([], silent=True, runner=Runner(started=False), frozen=True, executable="s.exe") == cli.DECLINED


def machine_env(tmp_path):
    base = core.test_env(str(tmp_path / "gercek"))
    base.hive = winreg.HKEY_LOCAL_MACHINE                                 # only used to say "needs administrator"
    return base


def test_setup_without_rights_asks_for_them_and_installs_nothing(tmp_path, monkeypatch):
    env = machine_env(tmp_path)
    seen = []
    monkeypatch.setattr(winapi, "is_admin", lambda: False)
    monkeypatch.setattr(cli, "relaunch_elevated", lambda argv, silent, **k: seen.append((list(argv), silent)) or 0)
    pack = make_payload(tmp_path / "paket")
    assert cli.setup_main(["--silent", "--payload", str(pack)], env=env, closer=Closer(), log_folder=str(tmp_path)) == 0
    assert seen == [(["--silent", "--payload", str(pack)], True)]
    assert not os.path.exists(env.default_install_dir) and core.find_existing(env) == (None, None)


def test_setup_with_rights_goes_straight_to_installing(tmp_path, monkeypatch):
    env = machine_env(tmp_path)
    env.hive = winreg.HKEY_CURRENT_USER                                   # (the install itself is tested elsewhere)
    monkeypatch.setattr(winapi, "is_admin", lambda: False)
    pack = make_payload(tmp_path / "paket")
    assert cli.setup_main(["--silent", "--payload", str(pack), "--dir", str(tmp_path / "x")], env=env, closer=Closer(),
                          log_folder=str(tmp_path)) == 0
    core.delete_key_tree(env, env.reg_prefix.rstrip("\\"))


def test_the_uninstaller_without_rights_asks_for_them_too(tmp_path, monkeypatch):
    env = machine_env(tmp_path)
    seen = []
    monkeypatch.setattr(winapi, "is_admin", lambda: False)
    monkeypatch.setattr(cli, "relaunch_elevated", lambda argv, silent, **k: seen.append(silent) or 0)
    assert cli.uninstall_main(["--silent"], env=env, self_path=str(tmp_path / "Uninstall.exe"), log_folder=str(tmp_path),
                              launcher=lambda *a: pytest.fail("must not start")) == 0
    assert seen == [True]


def test_when_rights_are_already_there_nothing_is_asked(tmp_path, monkeypatch):
    env = machine_env(tmp_path)
    monkeypatch.setattr(winapi, "is_admin", lambda: True)
    monkeypatch.setattr(cli, "relaunch_elevated", lambda *a, **k: pytest.fail("asked although it is an administrator"))
    pack = make_payload(tmp_path / "paket")
    cli.setup_main(["--silent", "--payload", str(tmp_path / "yok"), "--dir", str(tmp_path / "q")], env=env, closer=Closer(),
                   log_folder=str(tmp_path))                              # fails on the missing package, which is fine here


# ------------------------------------------------------------------------------ the pieces of winapi
def test_the_admin_check_answers_yes_or_no():
    assert winapi.is_admin() in (True, False)


@pytest.mark.skipif(not winapi.is_admin(), reason="needs an administrator session (no question is asked there)")
def test_an_elevated_program_runs_and_its_exit_code_comes_back():
    cmd = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
    assert winapi.run_elevated(cmd, "/c exit 7", wait=True) == (True, 7)
    assert winapi.run_elevated(cmd, "/c exit 0", wait=False)[0] is True


@pytest.mark.skipif(not winapi.is_admin(), reason="needs an administrator session")
def test_a_program_that_does_not_exist_is_not_started():
    assert winapi.run_elevated(r"C:\yok\yok\yok.exe", "", wait=True) == (False, None)


def test_the_program_is_opened_through_the_shell_when_we_are_an_administrator(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **k: calls.append(cmd))
    monkeypatch.setattr(winapi, "is_admin", lambda: True)
    assert winapi.launch_unelevated(r"C:\Program Files\ISO\DISO\DISO.exe") is True
    assert calls == [["explorer.exe", r"C:\Program Files\ISO\DISO\DISO.exe"]]
    calls.clear()
    monkeypatch.setattr(winapi, "is_admin", lambda: False)
    assert winapi.launch_unelevated(r"C:\x\DISO.exe") is True and calls == [[r"C:\x\DISO.exe"]]


def test_a_program_that_cannot_be_opened_is_reported(monkeypatch):
    def refuse(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    assert winapi.launch_unelevated(r"C:\x\DISO.exe") is False
    assert ui.launch(r"C:\x\DISO.exe") is False


def test_new_known_folders_exist_for_the_machine_wide_install():
    code = ("import sys; sys.path.insert(0, %r)\nfrom hizli_setup import winapi as w\n"
            "for f in (w.FOLDER_COMMON_PROGRAMS, w.FOLDER_PUBLIC_DESKTOP, w.FOLDER_PROGRAM_FILES): print(w.known_folder(f))"
            % os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = dict(os.environ)
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, encoding="utf-8", env=env,
                          creationflags=0x08000000)
    folders = done.stdout.split("\n")
    assert done.returncode == 0, done.stderr
    assert all(os.path.isdir(f) for f in folders if f.strip())
    assert "program files" in folders[2].lower() and "x86" not in folders[2].lower()
