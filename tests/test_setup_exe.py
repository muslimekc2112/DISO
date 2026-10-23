"""The real dist/DISO-Setup-<version>.exe, run the way a person's computer would run it.

Everything it changes is kept under a temporary folder and a throw-away registry key
(HIZLI_SETUP_TEST_ROOT), so the user's Start Menu, Desktop and registry are never touched.
The programs are started with a bare environment: no Python, no Node, no ffmpeg on the PATH.

Build it first:  python tools/build_installer.py"""
import glob
import json
import os
import subprocess
import time

import pytest

from hizli_setup import core, winapi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_setup():
    """The newest dist/DISO-Setup-<version>.exe (the file name carries the version)."""
    found = sorted(glob.glob(os.path.join(ROOT, "dist", "DISO-Setup-*.exe")), key=os.path.getmtime)
    return found[-1] if found else os.path.join(ROOT, "dist", "DISO-Setup-1.3.exe")


SETUP = _find_setup()
WINDIR = os.environ.get("SystemRoot", r"C:\Windows")
pytestmark = [pytest.mark.installer,
              pytest.mark.skipif(not os.path.isfile(SETUP), reason="dist/DISO-Setup-<version>.exe has not been built"),
              pytest.mark.skipif(not winapi.WINDOWS, reason="Windows only")]


class World:
    """One pretend computer: its own temp folder, profile, Start Menu and registry key."""

    def __init__(self, tmp_path):
        self.root = str(tmp_path / "bilgisayar")
        self.temp = str(tmp_path / "temp")
        self.profile = str(tmp_path / "profil")
        for d in (self.root, self.temp, self.profile):
            os.makedirs(d)
        self.env = core.test_env(self.root)
        self.base = {"SystemRoot": WINDIR, "windir": WINDIR, "ComSpec": os.path.join(WINDIR, "System32", "cmd.exe"),
                     "SystemDrive": WINDIR[:2], "TEMP": self.temp, "TMP": self.temp, "USERPROFILE": self.profile,
                     "HOME": self.profile, "LOCALAPPDATA": os.path.join(self.profile, "AppData", "Local"),
                     "APPDATA": os.path.join(self.profile, "AppData", "Roaming"), core.TEST_ROOT_ENV: self.root,
                     "HIZLI_NO_UPDATE": "1", "DISO_NO_NATIVE_HOST": "1",
                     # a computer with nothing on it: only Windows' own folders
                     "PATH": os.pathsep.join([os.path.join(WINDIR, "System32"), WINDIR, os.path.join(WINDIR, "System32", "Wbem")])}
        data = os.path.join(self.profile, "AppData", "Local", "DISO")
        os.makedirs(data)
        with open(os.path.join(data, "settings.json"), "w") as f:
            json.dump({"bridge_port": 17990}, f)         # not the port a real copy of the program may be using

    def run(self, exe, *args, timeout=240, **kw):
        return subprocess.run([exe, *args], env=self.base, capture_output=True, timeout=timeout,
                              creationflags=0x08000000, **kw)

    def popen(self, exe, *args):
        return subprocess.Popen([exe, *args], env=self.base, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=0x08000000)

    def leftovers_in_temp(self):
        """What the programs left in the temp folder, apart from their own log files (those are meant to stay)."""
        return sorted(n for n in (os.path.basename(p) for p in glob.glob(os.path.join(self.temp, "*")))
                      if not n.lower().endswith(".log"))


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    for target in glob.glob(os.path.join(w.root, "**", "DISO.exe"), recursive=True):
        winapi.close_programs_in(os.path.dirname(target), grace=0.5)
    core.delete_key_tree(w.env, w.env.reg_prefix.rstrip("\\"))


def wait_until(cond, timeout=60.0, step=0.25):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


def install(world, target, *extra):
    done = world.run(SETUP, "--silent", "--dir", str(target), *extra)
    return done.returncode


# ------------------------------------------------------------------------------ install
def test_the_setup_installs_the_program_with_everything_it_needs(world, tmp_path):
    target = tmp_path / "Hızlı Klasör" / "Uygulama Yeri"
    assert install(world, target) == 0
    assert (target / "DISO.exe").is_file() and (target / "_internal").is_dir()        # the program is a folder: it starts at once
    assert sum(f.stat().st_size for f in (target / "_internal").rglob("*") if f.is_file()) > 50_000_000
    assert not (target / "Uninstall.exe").exists() and (target / "deno" / "deno.exe").is_file()   # DISO removes itself
    manifest = core.read_manifest(str(target))
    assert manifest and manifest["version"] and set(manifest["files"]) >= {"DISO.exe", "install.json"}
    assert os.path.isfile(os.path.join(world.env.start_menu_dir, core.SHORTCUT_NAME))
    assert os.path.isfile(os.path.join(world.env.desktop_dir, core.SHORTCUT_NAME))
    assert core.find_existing(world.env) == (str(target), manifest["version"])
    uninstall_string = core._read_value(world.env, world.env.uninstall_key, "UninstallString")
    assert uninstall_string == f'"{target / "DISO.exe"}" --uninstall'
    assert world.leftovers_in_temp() == []                                    # the setup cleaned up its own unpacking


def test_the_installed_program_runs_on_a_computer_with_nothing_on_it(world, tmp_path):
    target = tmp_path / "Kurulu"
    assert install(world, target) == 0
    out = str(tmp_path / "selftest.json")
    done = world.run(str(target / "DISO.exe"), "--selftest", out)
    assert done.returncode == 0, done.stderr
    info = json.load(open(out, encoding="utf-8"))
    assert info["frozen"] is True and info["yt_dlp_version"]
    for part in ("customtkinter", "pystray", "PIL", "socks", "requests"):
        assert info[part] is True, (part, info[part])
    assert info["ffmpeg"] and info["tag_tools"] is True and info["music_player"] is True and info["music_ui"] is True
    assert info["deno"] and os.path.normcase(info["deno"]).startswith(os.path.normcase(str(target)))    # found beside the program
    assert info["deno_version"].lower().startswith("deno")                    # and it runs
    assert info["tray_icon"] is True
    assert info["media_panel"] is True and info["extras"] is True                    # winrt and the new parts are inside
    assert info["ytmusic"] is True                                                  # lyrics from YouTube Music
    assert info["visualizer"] is True and info["phone_qr"] is True                  # numpy, segno, websockets inside


def test_the_shortcuts_made_by_the_real_setup_point_at_the_installed_program(world, tmp_path):
    target = tmp_path / "Kisayol"
    assert install(world, target) == 0
    for link in (os.path.join(world.env.start_menu_dir, core.SHORTCUT_NAME), os.path.join(world.env.desktop_dir, core.SHORTCUT_NAME)):
        info = winapi.read_shortcut(link)
        assert os.path.normcase(info["target"]) == os.path.normcase(str(target / "DISO.exe"))


def test_the_switches_of_the_real_setup(world, tmp_path):
    target = tmp_path / "Secenekler"
    assert install(world, target, "--no-desktop", "--no-start-menu", "--autostart") == 0
    assert not os.path.exists(os.path.join(world.env.desktop_dir, core.SHORTCUT_NAME))
    assert not os.path.exists(world.env.start_menu_dir)
    assert core._read_value(world.env, world.env.run_key, "DISO") == f'"{target / "DISO.exe"}" --minimized'


def test_a_setup_that_finds_another_one_running_gives_way_and_changes_nothing(world, tmp_path):
    lock = winapi.single_instance("Local" + chr(92) + "DISO-Setup")        # "another setup is running"
    try:
        assert install(world, tmp_path / "Ikinci") == 4
        assert not (tmp_path / "Ikinci").exists() and core.find_existing(world.env) == (None, None)
    finally:
        winapi.release_instance(lock)
    assert install(world, tmp_path / "Ikinci") == 0                                 # and works once the other is gone


def test_the_properties_of_the_files_name_the_program_and_its_version(world, tmp_path):
    target = tmp_path / "Ozellikler"
    assert install(world, target) == 0
    version = core.read_manifest(str(target))["version"]
    for path in (SETUP, str(target / "DISO.exe")):
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              f"$v=(Get-Item -LiteralPath '{path}').VersionInfo; [Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                              "\"$($v.CompanyName)|$($v.FileVersion)|$($v.FileDescription)|$($v.ProductName)|$($v.ProductVersion)\""],
                             capture_output=True, text=True, encoding="utf-8", creationflags=0x08000000).stdout.strip()
        company, file_version, description, product, product_version = out.split("|")
        assert company == "ISO" and product == "DISO", (path, out)                   # the publisher and the product
        assert file_version.startswith(version.split()[0]) and description and product_version == version, (path, out)


# ------------------------------------------------------------------------------ upgrade over a running program
def test_installing_over_a_running_program_closes_it_and_replaces_it(world, tmp_path):
    target = tmp_path / "Calisan"
    assert install(world, target) == 0
    app = world.popen(str(target / "DISO.exe"))
    assert wait_until(lambda: len(winapi.processes_in(str(target))) >= 1, 60)
    time.sleep(4)                                                              # let it open its window
    assert install(world, target) == 0                                         # the same folder, while it runs
    assert wait_until(lambda: winapi.processes_in(str(target)) == [], 30)
    assert (target / "DISO.exe").is_file() and core.read_manifest(str(target))
    assert not [f for r, _, fs in os.walk(target) for f in fs if f.endswith((".old", ".new"))]
    assert app.poll() is not None


# ------------------------------------------------------------------------------ uninstall
def installed_copy(world, tmp_path, name="Kaldirilacak"):
    target = tmp_path / name
    assert install(world, target) == 0
    return target


def test_the_uninstaller_removes_everything_and_leaves_no_trace(world, tmp_path):
    target = installed_copy(world, tmp_path)
    core._write_values(world.env, world.env.run_key, {"DISO": (1, f'"{target / "DISO.exe"}" --minimized')})
    data = world.env.user_data_dir
    os.makedirs(data)
    open(os.path.join(data, "playlists.json"), "w").write("{}")
    done = world.run(str(target / "DISO.exe"), "--uninstall", "--silent")
    assert done.returncode == 0, done.stderr
    assert wait_until(lambda: not target.exists(), 60)
    assert not os.path.exists(os.path.join(world.env.start_menu_dir, core.SHORTCUT_NAME))
    assert not os.path.exists(os.path.join(world.env.desktop_dir, core.SHORTCUT_NAME))
    assert core._read_value(world.env, world.env.uninstall_key, "DisplayName") is None
    assert core._read_value(world.env, world.env.run_key, "DISO") is None
    assert os.path.isfile(os.path.join(data, "playlists.json"))                 # the user's data stays
    assert wait_until(lambda: world.leftovers_in_temp() == [], 40), world.leftovers_in_temp()     # no copies, no unpacked folders


def test_the_uninstaller_can_remove_the_users_data_too(world, tmp_path):
    target = installed_copy(world, tmp_path, "MitVeri")
    data = world.env.user_data_dir
    os.makedirs(data)
    open(os.path.join(data, "playlists.json"), "w").write("{}")
    assert world.run(str(target / "DISO.exe"), "--uninstall", "--silent", "--remove-data").returncode == 0
    assert wait_until(lambda: not target.exists() and not os.path.exists(data), 60)


def test_uninstalling_a_running_program(world, tmp_path):
    target = installed_copy(world, tmp_path, "AcikKaldir")
    world.popen(str(target / "DISO.exe"))
    assert wait_until(lambda: len(winapi.processes_in(str(target))) >= 1, 60)
    time.sleep(4)
    assert world.run(str(target / "DISO.exe"), "--uninstall", "--silent").returncode == 0
    assert wait_until(lambda: not target.exists(), 60)
    assert winapi.processes_in(str(target)) == []


def test_files_the_user_added_to_the_folder_survive_the_uninstall(world, tmp_path):
    target = installed_copy(world, tmp_path, "BenimDosyam")
    (target / "notlarim.txt").write_text("keep me")
    assert world.run(str(target / "DISO.exe"), "--uninstall", "--silent").returncode == 0
    assert wait_until(lambda: not (target / "DISO.exe").exists(), 60)
    assert (target / "notlarim.txt").read_text() == "keep me"


def test_a_reinstall_after_an_uninstall_works_like_the_first_time(world, tmp_path):
    target = installed_copy(world, tmp_path, "TekrarKur")
    assert world.run(str(target / "DISO.exe"), "--uninstall", "--silent").returncode == 0
    assert wait_until(lambda: not target.exists(), 60)
    assert install(world, target) == 0 and (target / "DISO.exe").is_file()
