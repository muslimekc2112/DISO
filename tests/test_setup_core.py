"""Installing and removing the program: real files, real shortcuts and a throw-away registry key."""
import json
import os
import winreg

import pytest

from hizli_setup import core, winapi
from setup_support import Closer, make_payload

pytestmark = pytest.mark.skipif(not winapi.WINDOWS, reason="Windows only")
NOSLEEP = lambda seconds: None  # noqa: E731
REAL_PROFILE = os.environ.get("USERPROFILE", "")       # the other tests point it at a temporary folder


# ------------------------------------------------------------------------------ fixtures
@pytest.fixture
def payload(tmp_path):
    return make_payload(tmp_path / "payload")


@pytest.fixture
def env(tmp_path):
    e = core.test_env(str(tmp_path / "world"))
    yield e
    core.delete_key_tree(e, e.reg_prefix.rstrip("\\"))


def opts(env, **kw):
    return core.Options(install_dir=kw.pop("install_dir", env.default_install_dir), **kw)


def do_install(payload, env, closer=None, **kw):
    return core.install(payload, opts(env, **kw), env, closer=closer or Closer())


def value(env, subkey, name):
    return core._read_value(env, subkey, name)


def tree(folder):
    return sorted(os.path.relpath(os.path.join(r, f), folder) for r, _, fs in os.walk(folder) for f in fs)


def link_target(path):
    return os.path.normcase(winapi.read_shortcut(path)["target"])


# ------------------------------------------------------------------------------ a fresh install
def test_a_fresh_install_puts_everything_in_place(payload, env):
    steps = []
    result = core.install(payload, opts(env), env, progress=lambda f, t: steps.append((f, t)), closer=Closer())
    target = env.default_install_dir
    assert result.install_dir == target and result.exe_path == os.path.join(target, "DISO.exe")
    assert result.version == "1.2.0" and result.warnings == []
    assert tree(target) == sorted(["DISO.exe", "Uninstall.exe", os.path.join("deno", "deno.exe"), "install.json"])
    for name, rel in (("DISO.exe", "DISO.exe"), ("deno.exe", os.path.join("deno", "deno.exe"))):
        assert core.sha256_of(os.path.join(target, rel)) == core.sha256_of(str(payload / name))
    fractions = [f for f, _ in steps]
    assert fractions == sorted(fractions) and fractions[0] == 0.0 and fractions[-1] == 1.0
    assert all(t for _, t in steps)


def test_the_apps_and_features_entry(payload, env):
    do_install(payload, env)
    key, target = env.uninstall_key, env.default_install_dir
    assert value(env, key, "DisplayName") == "DISO" and value(env, key, "DisplayVersion") == "1.2.0"
    assert value(env, key, "InstallLocation") == target
    assert value(env, key, "UninstallString") == f'"{os.path.join(target, "Uninstall.exe")}"'
    assert value(env, key, "QuietUninstallString") == f'"{os.path.join(target, "Uninstall.exe")}" --silent'
    assert value(env, key, "DisplayIcon") == f'"{os.path.join(target, "DISO.exe")}",0'
    assert value(env, key, "EstimatedSize") > 300 and value(env, key, "NoModify") == 1 and value(env, key, "NoRepair") == 1
    assert len(value(env, key, "InstallDate")) == 8


def test_the_shortcuts_point_at_the_program(payload, env):
    do_install(payload, env)
    target = env.default_install_dir
    exe = os.path.normcase(os.path.join(target, "DISO.exe"))
    menu, desktop = env.start_menu_dir, env.desktop_dir
    assert link_target(os.path.join(menu, core.SHORTCUT_NAME)) == exe
    assert link_target(os.path.join(desktop, core.SHORTCUT_NAME)) == exe
    assert link_target(os.path.join(menu, core.UNINSTALL_SHORTCUT)) == os.path.normcase(os.path.join(target, "Uninstall.exe"))
    info = winapi.read_shortcut(os.path.join(desktop, core.SHORTCUT_NAME))
    assert os.path.normcase(info["workdir"]) == os.path.normcase(target) and info["description"]


def test_the_manifest_lists_what_was_made(payload, env):
    do_install(payload, env, autostart=True)
    manifest = core.read_manifest(env.default_install_dir)
    assert manifest["version"] == "1.2.0" and manifest["install_dir"] == env.default_install_dir
    assert set(manifest["files"]) == {"DISO.exe", "Uninstall.exe", os.path.join("deno", "deno.exe"), "install.json"}
    assert manifest["dirs"] == ["deno"] and len(manifest["shortcuts"]) == 3
    assert manifest["start_menu_dir"] == env.start_menu_dir


def test_shortcuts_can_be_left_out(payload, env):
    do_install(payload, env, desktop_shortcut=False)
    assert not os.path.exists(os.path.join(env.desktop_dir, core.SHORTCUT_NAME))
    assert os.path.isfile(os.path.join(env.start_menu_dir, core.SHORTCUT_NAME))


def test_no_start_menu_no_folder(payload, env):
    do_install(payload, env, start_menu=False, desktop_shortcut=False)
    assert not os.path.exists(env.start_menu_dir) and core.read_manifest(env.default_install_dir)["shortcuts"] == []


# ------------------------------------------------------------------------------ starting with Windows
def test_starting_with_windows_is_written_and_can_be_switched_off(payload, env):
    exe = os.path.join(env.default_install_dir, "DISO.exe")
    do_install(payload, env, autostart=True)
    assert value(env, env.run_key, "DISO") == f'"{exe}" --minimized'
    do_install(payload, env, autostart=None)                              # an upgrade leaves the choice alone
    assert value(env, env.run_key, "DISO") == f'"{exe}" --minimized'
    do_install(payload, env, autostart=False)
    assert value(env, env.run_key, "DISO") is None


def test_unticking_does_not_remove_an_entry_that_belongs_to_something_else(payload, env):
    core._write_values(env, env.run_key, {"DISO": (winreg.REG_SZ, r'"C:\baska\yer\app.exe" --minimized')})
    do_install(payload, env, autostart=False)
    assert value(env, env.run_key, "DISO") == r'"C:\baska\yer\app.exe" --minimized'


# ------------------------------------------------------------------------------ the folder
@pytest.mark.parametrize("bad", ["", "   ", "DISO", r"relative\path", r"\\sunucu\paylasim\x", "C:\\", "C:",
                                 "C:\\a\\b:c", 'C:\\a\\"b"', "C:\\a\\b?", "C:\\a \\b", "C:\\a.\\b", "C:\\a\\" + "x" * 200])
def test_unusable_folders_are_refused_with_a_reason(bad):
    with pytest.raises(core.SetupError) as e:
        core.resolve_install_dir(bad)
    assert str(e.value)


def test_spaces_around_the_whole_path_are_just_typing_slips():
    assert core.resolve_install_dir("  C:\\Programlar\\Hizli  ") == "C:\\Programlar\\Hizli"
    assert core.resolve_install_dir('"C:\\Programlar\\Hizli"') == "C:\\Programlar\\Hizli"


def test_a_folder_with_other_things_in_it_gets_a_sub_folder(tmp_path):
    busy = tmp_path / "İndirilenler"
    busy.mkdir()
    (busy / "belge.pdf").write_bytes(b"x")
    assert core.resolve_install_dir(str(busy)) == os.path.join(str(busy), "DISO")
    empty = tmp_path / "bos"
    empty.mkdir()
    assert core.resolve_install_dir(str(empty)) == str(empty)
    assert core.resolve_install_dir(str(tmp_path / "yeni" / "klasör")) == str(tmp_path / "yeni" / "klasör")


def test_a_folder_that_is_a_file_is_refused(tmp_path):
    f = tmp_path / "dosya"
    f.write_bytes(b"x")
    with pytest.raises(core.SetupError):
        core.resolve_install_dir(str(f))
    busy = tmp_path / "dolu"
    busy.mkdir()
    (busy / "DISO").write_bytes(b"x")
    with pytest.raises(core.SetupError):
        core.resolve_install_dir(str(busy))


def test_quotes_around_the_path_and_odd_but_legal_names(payload, env, tmp_path):
    target = tmp_path / "Programlar Klasörü" / "Hızlı Şğü İ (x86)"
    result = core.install(payload, core.Options(install_dir=f'  "{target}"  '), env, closer=Closer())
    assert result.install_dir == str(target) and os.path.isfile(target / "DISO.exe")


def test_installing_into_a_folder_with_other_files_leaves_them_alone(payload, env, tmp_path):
    busy = tmp_path / "Belgelerim"
    busy.mkdir()
    (busy / "önemli.docx").write_bytes(b"precious")
    result = do_install(payload, env, install_dir=str(busy))
    assert result.install_dir == str(busy / "DISO") and (busy / "önemli.docx").read_bytes() == b"precious"
    core.uninstall(result.install_dir, env, closer=Closer())
    assert (busy / "önemli.docx").read_bytes() == b"precious" and not (busy / "DISO").exists()


def test_an_existing_empty_folder_is_used_and_kept_on_failure(payload, env, tmp_path):
    folder = tmp_path / "bos klasör"
    folder.mkdir()
    (payload / "deno.exe").write_bytes(b"corrupted")                       # the package is damaged
    with pytest.raises(core.SetupError):
        do_install(payload, env, install_dir=str(folder))
    assert folder.is_dir() and list(folder.iterdir()) == []


# ------------------------------------------------------------------------------ before anything is touched
def test_not_enough_room_is_reported_before_anything_is_written(payload, env):
    with pytest.raises(core.SetupError, match="yeterli yer"):
        core.install(payload, opts(env), env, closer=Closer(), free_space=lambda p: 1000)
    assert not os.path.exists(env.default_install_dir) and core.find_existing(env) == (None, None)


def test_a_damaged_or_missing_package_is_refused_and_nothing_remains(payload, env):
    (payload / "DISO.exe").write_bytes(b"x" * 300_000)            # same size, other content
    with pytest.raises(core.SetupError, match="bozulmuş"):
        do_install(payload, env)
    (payload / "DISO.exe").unlink()
    with pytest.raises(core.SetupError, match="yok"):
        do_install(payload, env)
    assert not os.path.exists(env.default_install_dir) and not os.path.exists(env.start_menu_dir)


def test_a_package_without_its_list_is_refused(tmp_path, env):
    with pytest.raises(core.SetupError, match="payload.json"):
        do_install(tmp_path / "nowhere", env)
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "payload.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(core.SetupError):
        do_install(broken, env)
    (broken / "payload.json").write_text(json.dumps({"files": []}), encoding="utf-8")
    with pytest.raises(core.SetupError):
        do_install(broken, env)


def test_a_file_that_is_written_wrongly_is_caught(payload, env, monkeypatch):
    real = core.sha256_of
    calls = {"n": 0}

    def liar(path, chunk=1 << 20):
        # the checks of the package pass; the check of the copy on disk fails for the first file
        if path.endswith(".new"):
            calls["n"] += 1
            return "0" * 64
        return real(path, chunk)

    monkeypatch.setattr(core, "sha256_of", liar)
    with pytest.raises(core.SetupError, match="doğru yazılamadı"):
        do_install(payload, env)
    assert calls["n"] == 1 and not os.path.exists(env.default_install_dir)


# ------------------------------------------------------------------------------ going wrong half way
def test_an_error_during_the_swap_restores_the_old_version(tmp_path, env, monkeypatch):
    old = make_payload(tmp_path / "v1", version="1.0.0", seed=b"1")
    do_install(old, env, autostart=True)
    target = env.default_install_dir
    before = {rel: open(os.path.join(target, rel), "rb").read() for rel in tree(target)}
    new = make_payload(tmp_path / "v2", version="2.0.0", seed=b"2")
    real = core.os.replace
    state = {"n": 0}

    def flaky(src, dst, *a, **k):
        if str(src).endswith(".new"):
            state["n"] += 1
            if state["n"] == 2:                                   # the second file of the swap fails
                raise OSError(28, "Aygıtta boş yer kalmadı")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(core.os, "replace", flaky)
    with pytest.raises(core.SetupError, match="yazılamadı"):
        do_install(new, env)
    monkeypatch.undo()
    after = {rel: open(os.path.join(target, rel), "rb").read() for rel in tree(target)}
    assert after == before                                         # exactly as it was: no .new, no .old, old contents
    assert value(env, env.uninstall_key, "DisplayVersion") == "1.0.0"
    assert os.path.isfile(os.path.join(env.start_menu_dir, core.SHORTCUT_NAME))


def test_an_error_while_registering_removes_a_fresh_install_completely(payload, env, monkeypatch):
    real = core._write_values

    def fail(env_, subkey, values):
        if subkey == env_.uninstall_key:
            raise OSError("Erişim engellendi")
        return real(env_, subkey, values)

    monkeypatch.setattr(core, "_write_values", fail)
    with pytest.raises(core.SetupError):
        do_install(payload, env, autostart=True)
    monkeypatch.undo()
    assert not os.path.exists(env.default_install_dir)
    assert not os.path.exists(os.path.join(env.start_menu_dir, core.SHORTCUT_NAME))
    assert not os.path.exists(os.path.join(env.desktop_dir, core.SHORTCUT_NAME))
    assert value(env, env.uninstall_key, "DisplayName") is None and value(env, env.run_key, "DISO") is None


def test_no_write_permission_gives_a_clear_message(payload, env, monkeypatch):
    def denied(*a, **k):
        raise PermissionError(13, "Erişim engellendi")

    monkeypatch.setattr(core.os, "makedirs", denied)
    with pytest.raises(core.SetupError, match="yazma izni"):
        do_install(payload, env)


def test_a_failing_shortcut_is_a_warning_not_a_failure(payload, env):
    def broken(link, *a, **k):
        if link.endswith(core.UNINSTALL_SHORTCUT):
            raise OSError("COM hatası")
        return winapi.create_shortcut(link, *a, **k)

    result = core.install(payload, opts(env), env, closer=Closer(), shortcut=broken)
    assert len(result.warnings) == 1 and "Kaldır" in result.warnings[0]
    assert os.path.isfile(os.path.join(env.default_install_dir, "DISO.exe"))
    assert len(core.read_manifest(env.default_install_dir)["shortcuts"]) == 2


# ------------------------------------------------------------------------------ upgrades and moves
def test_an_upgrade_replaces_the_files_and_drops_the_ones_that_are_gone(tmp_path, env):
    v1 = make_payload(tmp_path / "v1", version="1.0.0", extra=("eski.dll",), seed=b"1")
    v2 = make_payload(tmp_path / "v2", version="2.0.0", seed=b"2")
    do_install(v1, env)
    target = env.default_install_dir
    assert os.path.isfile(os.path.join(target, "eski.dll"))
    closer = Closer()
    do_install(v2, env, closer=closer, desktop_shortcut=False)
    assert closer.calls == [target]                                           # the running program was closed first
    assert not os.path.exists(os.path.join(target, "eski.dll"))
    assert open(os.path.join(target, "DISO.exe"), "rb").read()[:1] == b"2"
    assert not [f for f in tree(target) if f.endswith((".old", ".new"))]
    assert value(env, env.uninstall_key, "DisplayVersion") == "2.0.0"
    assert not os.path.exists(os.path.join(env.desktop_dir, core.SHORTCUT_NAME))   # unticked now: gone
    assert core.read_manifest(target)["version"] == "2.0.0" and "eski.dll" not in core.read_manifest(target)["files"]


def test_installing_the_same_version_again_is_harmless(payload, env):
    do_install(payload, env)
    do_install(payload, env)
    assert tree(env.default_install_dir) == sorted(["DISO.exe", "Uninstall.exe", os.path.join("deno", "deno.exe"), "install.json"])


def test_a_new_place_removes_the_old_copy(payload, env, tmp_path):
    first = tmp_path / "ilk yer"
    second = tmp_path / "ikinci yer"
    do_install(payload, env, install_dir=str(first))
    closer = Closer()
    do_install(payload, env, install_dir=str(second), closer=closer)
    assert not first.exists() and (second / "DISO.exe").is_file()
    assert core.find_existing(env)[0] == str(second) and closer.calls == [str(first)]     # the old place was closed down
    assert link_target(os.path.join(env.start_menu_dir, core.SHORTCUT_NAME)) == os.path.normcase(str(second / "DISO.exe"))


def test_an_unknown_folder_that_looks_like_the_old_one_is_not_deleted(payload, env, tmp_path):
    do_install(payload, env, install_dir=str(tmp_path / "ilk"))
    os.remove(tmp_path / "ilk" / "install.json")                       # not recognisably ours any more
    (tmp_path / "ilk" / "benim.txt").write_text("mine")
    do_install(payload, env, install_dir=str(tmp_path / "ikinci"))
    assert (tmp_path / "ilk" / "benim.txt").read_text() == "mine"


# ------------------------------------------------------------------------------ uninstalling
def test_uninstall_removes_everything_it_installed(payload, env):
    do_install(payload, env, autostart=True)
    target = env.default_install_dir
    result = core.uninstall(target, env, closer=Closer())
    assert result.leftovers == []
    assert not os.path.exists(target)
    assert not os.path.exists(env.start_menu_dir) and not os.path.exists(os.path.join(env.desktop_dir, core.SHORTCUT_NAME))
    assert value(env, env.uninstall_key, "DisplayName") is None and value(env, env.run_key, "DISO") is None
    assert core.find_existing(env) == (None, None)


def test_the_empty_publisher_folder_goes_too_but_a_busy_one_stays(payload, env):
    do_install(payload, env)
    target = env.default_install_dir
    publisher = os.path.dirname(target)
    assert os.path.basename(publisher) == core.PUBLISHER
    core.uninstall(target, env, closer=Closer())
    assert not os.path.exists(publisher)
    do_install(payload, env)
    other = os.path.join(publisher, "BaşkaProgram")
    os.makedirs(other)
    core.uninstall(target, env, closer=Closer())
    assert os.path.isdir(other) and not os.path.exists(target)


def test_uninstall_closes_the_running_program_first(payload, env):
    do_install(payload, env)
    closer = Closer()
    core.uninstall(env.default_install_dir, env, closer=closer)
    assert closer.calls == [env.default_install_dir]


def test_uninstall_keeps_the_users_data_unless_asked(payload, env):
    do_install(payload, env)
    data = env.user_data_dir
    os.makedirs(os.path.join(data, "tools"))
    for name in ("settings.json", "playlists.json", os.path.join("tools", "deno.exe")):
        with open(os.path.join(data, name), "w") as f:
            f.write("x")
    core.uninstall(env.default_install_dir, env, closer=Closer())
    assert sorted(tree(data)) == sorted(["settings.json", "playlists.json", os.path.join("tools", "deno.exe")])
    do_install(payload, env)
    result = core.uninstall(env.default_install_dir, env, remove_data=True, closer=Closer())
    assert not os.path.exists(data) and result.leftovers == []


def test_removing_data_refuses_a_folder_that_is_not_ours_by_name(payload, env, tmp_path):
    other = tmp_path / "Belgelerim"
    other.mkdir()
    (other / "x.txt").write_text("keep")
    env.user_data_dir = str(other)
    do_install(payload, env)
    core.uninstall(env.default_install_dir, env, remove_data=True, closer=Closer())
    assert (other / "x.txt").read_text() == "keep"


def test_files_the_installer_did_not_make_survive_and_keep_their_folder(payload, env):
    do_install(payload, env)
    target = env.default_install_dir
    with open(os.path.join(target, "notlarim.txt"), "w") as f:
        f.write("mine")
    core.uninstall(target, env, closer=Closer())
    assert tree(target) == ["notlarim.txt"]


def test_a_shortcut_the_user_repointed_is_left_alone(payload, env, tmp_path):
    do_install(payload, env)
    other = tmp_path / "baska.exe"
    other.write_bytes(b"MZ")
    mine = os.path.join(env.desktop_dir, core.SHORTCUT_NAME)
    winapi.create_shortcut(mine, str(other))
    core.uninstall(env.default_install_dir, env, closer=Closer())
    assert os.path.isfile(mine) and link_target(mine) == os.path.normcase(str(other))


def test_other_things_in_the_start_menu_folder_keep_it_alive(payload, env):
    do_install(payload, env)
    with open(os.path.join(env.start_menu_dir, "Başka.txt"), "w") as f:
        f.write("x")
    core.uninstall(env.default_install_dir, env, closer=Closer())
    assert tree(env.start_menu_dir) == ["Başka.txt"]


def test_a_start_entry_of_another_copy_is_not_removed(payload, env):
    do_install(payload, env)
    core._write_values(env, env.run_key, {"DISO": (winreg.REG_SZ, r'"C:\dev\python.exe" "C:\dev\main.py" --minimized')})
    core.uninstall(env.default_install_dir, env, closer=Closer())
    assert value(env, env.run_key, "DISO") is not None


def test_uninstall_without_its_list_still_removes_the_usual_files(payload, env):
    do_install(payload, env)
    target = env.default_install_dir
    os.remove(os.path.join(target, "install.json"))
    result = core.uninstall(target, env, closer=Closer())
    assert not os.path.exists(target) and result.leftovers == []
    assert not os.path.exists(os.path.join(env.start_menu_dir, core.SHORTCUT_NAME))


def test_uninstalling_twice_or_a_missing_folder_is_quiet(payload, env, tmp_path):
    do_install(payload, env)
    core.uninstall(env.default_install_dir, env, closer=Closer())
    again = core.uninstall(env.default_install_dir, env, closer=Closer())
    assert again.leftovers == []
    assert core.uninstall(str(tmp_path / "hiç yok"), env, closer=Closer()).leftovers == []


def test_a_file_that_is_in_use_is_scheduled_for_the_next_restart(payload, env, monkeypatch):
    do_install(payload, env)
    target = env.default_install_dir
    exe = os.path.join(target, "DISO.exe")
    scheduled = []
    monkeypatch.setattr(core.winapi, "delete_on_reboot", lambda p: scheduled.append(p) or True)
    with open(exe, "rb"):                                              # something holds the file open
        result = core.uninstall(target, env, closer=Closer(), sleep=NOSLEEP)
    assert result.leftovers == [exe] and scheduled == [exe]
    assert os.path.isdir(target) and tree(target) == ["DISO.exe"]
    assert value(env, env.uninstall_key, "DisplayName") is None              # the rest is gone
    assert not os.path.exists(env.start_menu_dir)


# ------------------------------------------------------------------------------ lookups
def test_the_registered_install_is_found_and_forgotten(payload, env):
    assert core.find_existing(env) == (None, None)
    do_install(payload, env)
    assert core.find_existing(env) == (env.default_install_dir, "1.2.0")
    core.uninstall(env.default_install_dir, env, closer=Closer())
    assert core.find_existing(env) == (None, None)


def test_a_registered_install_whose_folder_is_gone_is_not_found(payload, env):
    do_install(payload, env)
    import shutil
    shutil.rmtree(env.default_install_dir)
    assert core.find_existing(env) == (None, None)
    core.delete_key_tree(env, env.uninstall_key)                          # and deleting it twice is fine
    core.delete_key_tree(env, env.uninstall_key)


def test_the_real_environment_points_at_real_places(monkeypatch, tmp_path):
    import subprocess
    import sys
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = (f"import sys, json; sys.path.insert(0, {repo!r})\nfrom hizli_setup import core\n"
            "e = core.production_env()\nprint(json.dumps([e.programs_dir, e.desktop_dir, e.default_install_dir, "
            "e.user_data_dir, e.reg_prefix, e.needs_admin, [o.default_install_dir for o in e.legacy_envs], "
            "[o.hive for o in e.legacy_envs], list(e.legacy_data_dirs)]))")
    env = {k: v for k, v in os.environ.items() if k != core.TEST_ROOT_ENV}
    env["USERPROFILE"] = REAL_PROFILE
    env.pop("LOCALAPPDATA", None) if not env.get("LOCALAPPDATA", "").startswith(REAL_PROFILE) else None
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, encoding="utf-8",
                          env=env, creationflags=0x08000000)
    assert done.returncode == 0, done.stderr
    programs, desktop, install, data, prefix, needs_admin, older_dirs, older_hives, legacy_data = json.loads(done.stdout)
    assert os.path.isdir(programs) and os.path.isdir(desktop) and prefix == ""
    assert "programdata" in programs.lower() and "public" in desktop.lower()          # for every user, not just this one
    assert install.endswith(os.path.join("ISO", "DISO")) and "program files" in install.lower()
    assert os.path.basename(data) == "DISO" and needs_admin is True
    assert older_dirs[0].endswith(os.path.join("Programs", "HizliIndirici")) and older_hives == [core.winreg.HKEY_CURRENT_USER]
    assert os.path.basename(legacy_data[0]) == ".hizli_indirici"
    monkeypatch.setenv(core.TEST_ROOT_ENV, str(tmp_path / "root"))
    hooked = core.production_env()
    assert hooked.reg_prefix.startswith(r"Software\DISOTest") and hooked.desktop_dir.startswith(str(tmp_path))
    assert core.test_env(str(tmp_path / "a")).reg_prefix != core.test_env(str(tmp_path / "b")).reg_prefix


def test_an_error_after_the_registry_was_written_puts_the_old_entry_back(tmp_path, env, monkeypatch):
    v1 = make_payload(tmp_path / "v1", version="1.0.0", seed=b"1")
    v2 = make_payload(tmp_path / "v2", version="2.0.0", seed=b"2")
    do_install(v1, env, autostart=True)
    target = env.default_install_dir
    before = {rel: open(os.path.join(target, rel), "rb").read() for rel in tree(target)}
    entry_before = core._snapshot_key(env, env.uninstall_key)
    run_before = value(env, env.run_key, "DISO")
    real = core.os.replace

    def fail_on_the_list(src, dst, *a, **k):
        if str(dst).endswith("install.json") and str(src).endswith(".new") and "v2" not in str(src):
            raise OSError(5, "Erişim engellendi")                 # the very last step of the install
        return real(src, dst, *a, **k)

    monkeypatch.setattr(core.os, "replace", fail_on_the_list)
    with pytest.raises(core.SetupError):
        do_install(v2, env, autostart=False)                      # it would also have switched the autostart off
    monkeypatch.undo()
    assert core._snapshot_key(env, env.uninstall_key) == entry_before          # "Apps & features" as before
    assert value(env, env.uninstall_key, "DisplayVersion") == "1.0.0"
    assert value(env, env.run_key, "DISO") == run_before              # and so is the autostart
    assert {rel: open(os.path.join(target, rel), "rb").read() for rel in tree(target)} == before
