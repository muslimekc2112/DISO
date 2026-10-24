"""The Windows helpers of the installer: folders, shortcuts, finding and closing programs."""
import os
import shutil
import subprocess
import sys
import time

import pytest

from hizli_setup import winapi

pytestmark = pytest.mark.skipif(not winapi.WINDOWS, reason="Windows only")
NO_WINDOW = 0x08000000
SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")


REAL_PROFILE = os.environ.get("USERPROFILE", "")


@pytest.fixture
def real_profile(monkeypatch):
    """The other tests point USERPROFILE at a temporary folder; Windows' folder lookup follows it."""
    monkeypatch.setenv("USERPROFILE", REAL_PROFILE)


def wait_until(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return cond()


# ------------------------------------------------------------------------------ folders
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def in_clean_process(code):
    """Run python code in a fresh process with the real user profile. (Windows keeps the folder paths
    it resolved once per process; earlier tests in this process used a pretend profile.)"""
    env = dict(os.environ, USERPROFILE=REAL_PROFILE)
    full = f"import sys; sys.path.insert(0, {REPO!r})\n" + code
    done = subprocess.run([sys.executable, "-I", "-c", full], capture_output=True, text=True, encoding="utf-8",
                          env=env, creationflags=NO_WINDOW)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_the_well_known_folders_exist():
    out = in_clean_process("from hizli_setup import winapi as w\n"
                           "print(w.known_folder(w.FOLDER_PROGRAMS)); print(w.known_folder(w.FOLDER_DESKTOP)); "
                           "print(w.known_folder(w.FOLDER_LOCAL_APPDATA))")
    programs, desktop, local = out.splitlines()
    for path in (programs, desktop, local):
        assert os.path.isabs(path) and os.path.isdir(path)
    assert local.lower().endswith("local") and "start menu" in programs.lower() or "programs" in programs.lower()


def test_free_space_of_a_folder_that_does_not_exist_yet(tmp_path):
    assert winapi.free_space(str(tmp_path / "a" / "b" / "c")) > 0
    assert winapi.free_space(str(tmp_path)) > 0


# ------------------------------------------------------------------------------ shortcuts
def test_a_shortcut_is_written_and_reads_back_exactly(tmp_path):
    target = tmp_path / "Klasör şğü" / "DISO.exe"
    target.parent.mkdir()
    target.write_bytes(b"MZ")
    link = tmp_path / "menü" / "alt" / "DISO.lnk"
    winapi.create_shortcut(str(link), str(target), arguments="--minimized", workdir=str(target.parent),
                           description="Dosya, video ve müzik indirme yöneticisi", icon=str(target), icon_index=0)
    assert link.is_file()
    info = winapi.read_shortcut(str(link))
    assert os.path.normcase(info["target"]) == os.path.normcase(str(target))
    assert info["arguments"] == "--minimized" and info["description"] == "Dosya, video ve müzik indirme yöneticisi"
    assert os.path.normcase(info["workdir"]) == os.path.normcase(str(target.parent))


def test_a_shortcut_without_the_extras_and_overwriting_one(tmp_path):
    a, b = tmp_path / "a.exe", tmp_path / "b.exe"
    a.write_bytes(b"MZ")
    b.write_bytes(b"MZ")
    link = str(tmp_path / "x.lnk")
    winapi.create_shortcut(link, str(a))
    assert os.path.normcase(winapi.read_shortcut(link)["target"]) == os.path.normcase(str(a))
    winapi.create_shortcut(link, str(b), arguments="x")
    info = winapi.read_shortcut(link)
    assert os.path.normcase(info["target"]) == os.path.normcase(str(b)) and info["arguments"] == "x"


def test_reading_a_missing_or_broken_shortcut_is_an_error(tmp_path):
    with pytest.raises(OSError):
        winapi.read_shortcut(str(tmp_path / "missing.lnk"))
    bad = tmp_path / "bad.lnk"
    bad.write_bytes(b"not a shortcut")
    with pytest.raises(OSError):
        winapi.read_shortcut(str(bad))


def test_shortcuts_work_from_several_threads(tmp_path):
    import threading
    errors = []
    target = tmp_path / "t.exe"
    target.write_bytes(b"MZ")

    def work(i):
        try:
            winapi.create_shortcut(str(tmp_path / f"s{i}.lnk"), str(target))
            winapi.read_shortcut(str(tmp_path / f"s{i}.lnk"))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []


# ------------------------------------------------------------------------------ processes
@pytest.fixture
def fake_app(tmp_path):
    """A copy of ping.exe inside a folder of its own, running (a stand-in for the installed program)."""
    folder = tmp_path / "Kurulu Uygulama"
    folder.mkdir()
    exe = folder / "DISO.exe"
    shutil.copy(os.path.join(SYSTEM32, "ping.exe"), exe)
    procs = []

    def start():
        p = subprocess.Popen([str(exe), "-t", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        procs.append(p)
        return p

    yield folder, start
    for p in procs:
        if p.poll() is None:
            p.kill()


def test_a_running_program_is_found_by_its_folder_and_nothing_else(fake_app, tmp_path):
    folder, start = fake_app
    assert winapi.processes_in(str(folder)) == []
    p = start()
    assert wait_until(lambda: [pid for pid, _, _ in winapi.processes_in(str(folder))] == [p.pid])
    pid, parent, path = winapi.processes_in(str(folder))[0]
    assert parent == os.getpid() and os.path.normcase(path) == os.path.normcase(str(folder / "DISO.exe"))
    assert winapi.processes_in(str(tmp_path / "Başka Klasör")) == []
    assert winapi.processes_in(str(folder) + "x") == []                  # "Uygulama" is not "Uygulamax"
    assert winapi.processes_in("") == []


def test_a_folder_with_a_similar_name_is_not_touched(fake_app, tmp_path):
    folder, start = fake_app
    start()
    assert wait_until(lambda: winapi.processes_in(str(folder)))
    sibling = tmp_path / "Kurulu Uygulama 2"
    sibling.mkdir()
    assert winapi.processes_in(str(sibling)) == []


def test_closing_ends_a_program_that_ignores_the_close_request(fake_app):
    folder, start = fake_app
    p = start()
    assert wait_until(lambda: winapi.processes_in(str(folder)))
    forced = winapi.close_programs_in(str(folder), grace=1.0)
    assert forced >= 1 and winapi.processes_in(str(folder)) == []
    assert wait_until(lambda: p.poll() is not None)


def test_closing_when_nothing_runs_does_nothing(tmp_path):
    assert winapi.close_programs_in(str(tmp_path)) == 0


def test_a_launcher_and_its_child_both_go_and_the_child_goes_first(tmp_path):
    folder = tmp_path / "Çift Süreç"
    folder.mkdir()
    launcher, child = folder / "DISO.exe", folder / "child.exe"
    shutil.copy(os.path.join(SYSTEM32, "cmd.exe"), launcher)
    shutil.copy(os.path.join(SYSTEM32, "ping.exe"), child)
    command = f'"{launcher}" /s /c ""{child}" -t 127.0.0.1"'
    p = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         creationflags=NO_WINDOW)
    try:
        assert wait_until(lambda: len(winapi.processes_in(str(folder))) == 2)
        terminated = []
        real = winapi._terminate
        winapi._terminate = lambda pid: (terminated.append(pid), real(pid))[1]
        try:
            winapi.close_programs_in(str(folder), grace=0.5)
        finally:
            winapi._terminate = real
        assert winapi.processes_in(str(folder)) == []
        found_child = terminated[0]
        assert found_child != p.pid                          # the inner process was ended first
    finally:
        if p.poll() is None:
            p.kill()


def test_a_window_is_asked_to_close_politely():
    code = ("import tkinter as tk\nr = tk.Tk()\nr.after(60000, r.destroy)\nprint('ready', flush=True)\nr.mainloop()\n")
    p = subprocess.Popen([sys.executable, "-I", "-c", code], stdout=subprocess.PIPE, creationflags=NO_WINDOW)
    try:
        assert p.stdout.readline().strip() == b"ready"
        time.sleep(0.5)
        assert winapi._post_close({p.pid}) >= 1
        assert wait_until(lambda: p.poll() is not None, 10)
        assert p.returncode == 0                              # it closed by itself, it was not killed
    finally:
        if p.poll() is None:
            p.kill()


def test_the_installer_never_closes_itself(fake_app):
    folder, start = fake_app
    assert all(pid != os.getpid() for pid, _, _ in winapi.processes_in(os.path.dirname(sys.executable)))
