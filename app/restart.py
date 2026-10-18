"""Start the program again after it has closed (used when a setting only applies to a new start)."""
import os
import subprocess
import sys
import time

RESTART_ENV = "HIZLI_RESTART"
_DETACHED = 0x00000008          # DETACHED_PROCESS
_NEW_GROUP = 0x00000200         # CREATE_NEW_PROCESS_GROUP


def command(argv=None):
    """The command line that starts this program the way it was started now (exe or main.py)."""
    args = list(sys.argv[1:] if argv is None else argv)
    if getattr(sys, "frozen", False):
        return [sys.executable] + args
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return [sys.executable, main] + args


def relaunch(argv=None):
    """Start a new copy of the program. It waits for this one to let go of the single-window lock
    (see wait_for_previous). Returns True when it could be started."""
    env = dict(os.environ)
    env[RESTART_ENV] = "1"
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"      # a one-file exe must unpack itself again, not reuse our folder
    try:
        subprocess.Popen(command(argv), env=env, close_fds=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=_DETACHED | _NEW_GROUP if os.name == "nt" else 0)
        return True
    except OSError:
        return False


def wait_for_previous(is_running, timeout=20.0, step=0.25):
    """In a copy started by relaunch(): wait until the old window has really closed. Returns
    True when it is gone (or this is a normal start), False if it never went away."""
    if os.environ.pop(RESTART_ENV, None) is None:
        return True
    deadline = time.time() + timeout
    while is_running():
        if time.time() > deadline:
            return False
        time.sleep(step)
    return True
