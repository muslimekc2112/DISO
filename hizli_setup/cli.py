"""The two programs: Setup (installs) and Uninstall (removes). Both can run without a window
(--silent), which is also how they are tested."""
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from app import i18n

from . import core, winapi

CREATE_NO_WINDOW = 0x08000000
DETACHED = 0x00000008 | 0x00000200
log = logging.getLogger("hizli_setup")


def setup_logging(filename, folder=None):
    """A log file in the temp folder: when something goes wrong it says what."""
    path = os.path.join(folder or tempfile.gettempdir(), filename)
    for h in list(log.handlers):
        log.removeHandler(h)
    try:
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        log.addHandler(handler)
    except OSError:
        pass
    log.setLevel(logging.INFO)
    log.propagate = False
    return path


def default_payload_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "payload")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "payload")


def _parser(kind):
    p = argparse.ArgumentParser(prog=kind, add_help=False, allow_abbrev=False)
    p.add_argument("--silent", action="store_true")
    p.add_argument("--dir")
    p.add_argument("--payload")
    p.add_argument("--no-desktop", action="store_true")
    p.add_argument("--no-start-menu", action="store_true")
    p.add_argument("--autostart", action="store_true")
    p.add_argument("--launch", action="store_true")
    p.add_argument("--remove-data", action="store_true")
    p.add_argument("--stage2", action="store_true")
    p.add_argument("--self-delete")
    p.add_argument("--result")
    p.add_argument("--parent-pid", type=int)
    return p


def parse(kind, argv):
    """Unknown switches are ignored; /S and /s (the usual installer spelling) mean --silent."""
    argv = ["--silent" if a in ("/S", "/s") else a for a in argv]
    return _parser(kind).parse_known_args(argv)[0]


def _message(title, text, error=True):
    """A message box for the case where there is no window of our own to show it in."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, i18n.tr(text), title, 0x10 if error else 0x40)
    except Exception:  # noqa: BLE001
        pass


def use_language(env):
    """Speak the language DISO speaks: the one chosen in its settings, or else Windows' own.
    Tests (a test root) stay Turkish unless their settings say otherwise."""
    fallback = "Türkçe" if os.environ.get(core.TEST_ROOT_ENV) else None
    i18n.set_language(i18n.saved_language(os.path.join(env.user_data_dir, "settings.json"), fallback))


# ----------------------------------------------------------------------------------- administrator
DECLINED = 5                                              # the user said no to Windows' "allow this?" question


def relaunch_elevated(argv, silent, runner=winapi.run_elevated, frozen=None, executable=None, script=None):
    """This program was started without administrator rights but needs them (Program Files, HKLM).
    Start it again with them: Windows asks the user once. A silent run waits for the new one and returns
    its exit code; a window run just hands over."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    exe = executable or sys.executable
    params = list(argv) if frozen else [script or sys.argv[0], *argv]
    started, code = runner(exe, subprocess.list2cmdline(params), wait=silent)
    if not started:
        log.info("administrator rights were not granted")
        return DECLINED
    return code if (silent and code is not None) else 0


# ----------------------------------------------------------------------------------- setup
def setup_main(argv=None, payload_dir=None, env=None, closer=winapi.close_programs_in, log_folder=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    args = parse("setup", raw)
    setup_logging("DISO-kurulum.log", log_folder)
    log.info("setup started: silent=%s dir=%s", args.silent, args.dir)
    env = env or core.production_env()
    if env.needs_admin and not winapi.is_admin():
        return relaunch_elevated(raw, args.silent)
    use_language(env)
    payload_dir = args.payload or payload_dir or default_payload_dir()
    lock = winapi.single_instance("Local\\DISO-Setup")
    if lock is None:
        if not args.silent:
            _message(core.DISPLAY_NAME, "Kurulum zaten açık.", error=False)
        return 4
    try:
        return _run_setup(args, env, payload_dir, closer)
    finally:
        winapi.release_instance(lock)


def _run_setup(args, env, payload_dir, closer) -> int:
    if args.silent:
        old_dir, _ = core.find_existing(env)
        options = core.Options(install_dir=args.dir or old_dir or env.default_install_dir,
                               desktop_shortcut=not args.no_desktop, start_menu=not args.no_start_menu,
                               autostart=True if args.autostart else None)
        try:
            result = core.install(payload_dir, options, env, closer=closer)
        except core.SetupError as e:
            log.error("install failed: %s", e)
            return 2
        except Exception:  # noqa: BLE001
            log.exception("install crashed")
            return 1
        log.info("installed %s into %s", result.version, result.install_dir)
        if args.launch:
            from .ui import launch
            launch(result.exe_path)
        return 0
    from app import look

    from .ui import SetupWindow
    look.apply("Yeni")
    window = SetupWindow(payload_dir, env, closer=closer, preset_dir=args.dir)
    window.mainloop()
    return window.exit_code


# ----------------------------------------------------------------------------------- uninstall
def schedule_self_delete(path, runner=subprocess.Popen):
    """Delete a program file that is still running, a moment after it has ended."""
    command = (f'cmd.exe /d /c for /l %i in (1,1,40) do @(if exist "{path}" (del /f /q "{path}" 2>nul'
               f' & ping -n 2 127.0.0.1 >nul))')
    try:
        runner(command, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
               creationflags=CREATE_NO_WINDOW | DETACHED)
        return True
    except OSError:
        return False


def start_copy(path, args):
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    return subprocess.Popen([path, *args], env=env, close_fds=True, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=DETACHED)


UNINSTALL_LOCK = "Local" + chr(92) + "DISO-Uninstall"
RESULT_WAIT = 600.0


def close_others(folder):
    """Close what runs from the install folder, except the uninstaller itself (that is us, or the process that
    started us and is waiting for the result)."""
    return winapi.close_programs_in(folder, ignore_names=(core.UNINSTALLER_NAME.lower(),))


def write_result(path, code):
    if not path:
        return
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"code": code}, f)
        os.replace(path + ".tmp", path)
    except OSError:
        pass


def wait_for_result(result_file, proc, timeout=RESULT_WAIT, poll=0.2, sleep=time.sleep, now=time.time):
    """A silent uninstall must not return before the removal is done, but the first process cannot wait
    for the copy to END (the copy waits for the first one to end, to delete its file). So the copy writes
    how it went into a small file, and the first process waits for that."""
    deadline = now() + timeout
    while now() < deadline:
        if os.path.isfile(result_file):
            try:
                with open(result_file, encoding="utf-8") as f:
                    return int(json.load(f)["code"])
            except (OSError, ValueError, KeyError):
                pass                                      # it is being written right now: look again
        if proc is not None and hasattr(proc, "poll") and proc.poll() is not None:
            return proc.returncode if proc.returncode is not None else 1
        sleep(poll)
    return 1


def uninstall_main(argv=None, env=None, closer=None, self_path=None, launcher=start_copy,
                   log_folder=None, delete_later=schedule_self_delete) -> int:
    args = parse("uninstall", sys.argv[1:] if argv is None else argv)
    setup_logging("DISO-kaldirma.log", log_folder)
    env = env or core.production_env()
    closer = closer or close_others
    self_path = self_path or sys.executable
    log.info("uninstall started: stage2=%s silent=%s dir=%s", args.stage2, args.silent, args.dir)
    use_language(env)

    if not args.stage2:
        if env.needs_admin and not winapi.is_admin():
            return relaunch_elevated(list(sys.argv[1:] if argv is None else argv), args.silent)
        # Stage 1: we live inside the folder that is about to be deleted, so a copy of us does the work.
        install_dir = os.path.dirname(os.path.abspath(self_path))
        if not core.is_ours(install_dir):
            install_dir = core.find_existing(env)[0] or install_dir
            if not core.is_ours(install_dir):
                log.error("no installation found around %s", self_path)
                if not args.silent:
                    _message(core.DISPLAY_NAME, "Kurulu bir DISO bulunamadı.")
                return 3
        copy = os.path.join(tempfile.gettempdir(), f"DISO-kaldir-{uuid.uuid4().hex[:8]}.exe")
        try:
            shutil.copy2(self_path, copy)
        except OSError as e:
            log.error("cannot make the temporary copy: %s", e)
            if not args.silent:
                _message(core.DISPLAY_NAME, f"Kaldırıcı başlatılamadı: {e}")
            return 1
        result_file = copy + ".result"
        passed = ["--stage2", "--dir", install_dir, "--self-delete", copy, "--parent-pid", str(os.getpid())]
        passed += ["--silent", "--result", result_file] if args.silent else []
        passed += ["--remove-data"] if args.remove_data else []
        proc = launcher(copy, passed)
        if not args.silent:
            return 0                                      # the copy shows the window; we leave at once
        code = wait_for_result(result_file, proc)
        try:
            os.remove(result_file)
        except OSError:
            pass
        return code

    # Stage 2: the real work, from the copy in the temp folder
    install_dir = args.dir or os.path.dirname(os.path.abspath(self_path))
    lock = winapi.single_instance(UNINSTALL_LOCK)
    if lock is None:
        if not args.silent:
            _message(core.DISPLAY_NAME, "Kaldırma zaten açık.", error=False)
        write_result(args.result, 4)
        if args.self_delete:
            delete_later(args.self_delete)
        return 4
    code = 1
    try:
        keep = [core.UNINSTALLER_NAME]                    # the first process still runs it: removed in the last step
        if args.silent:
            try:
                core.uninstall(install_dir, env, remove_data=args.remove_data, closer=closer, keep=keep)
                code = 0
            except core.SetupError as e:
                log.error("uninstall failed: %s", e)
                code = 2
            except Exception:  # noqa: BLE001
                log.exception("uninstall crashed")
                code = 1
        else:
            from app import look

            from .ui import UninstallWindow
            look.apply("Yeni")
            window = UninstallWindow(install_dir, env, closer=closer, remove_data=args.remove_data, keep=keep)
            window.mainloop()
            code = window.exit_code
        write_result(args.result, code)
        if code == 0:
            winapi.wait_for_exit(args.parent_pid, 60)     # let the first process go (it holds Uninstall.exe) ...
            try:
                core.uninstall(install_dir, env, closer=lambda folder: 0)       # ... then remove the last files
            except Exception:  # noqa: BLE001
                log.exception("the last step of the removal failed")
    finally:
        winapi.release_instance(lock)
        if args.self_delete:
            delete_later(args.self_delete)
    return code
