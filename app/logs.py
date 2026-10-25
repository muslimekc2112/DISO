"""Log file (%LOCALAPPDATA%\\DISO/diso.log) so a problem can be looked at afterwards."""
import logging
import logging.handlers
import faulthandler
import os

from .utils import app_data_dir

log = logging.getLogger("hizli")
log.addHandler(logging.NullHandler())  # silent until setup_logging() is called (tests, tools)


def log_path() -> str:
    return os.path.join(app_data_dir(), "diso.log")


def crash_path() -> str:
    return os.path.join(app_data_dir(), "crash.log")


def setup_logging(level=logging.INFO) -> str:
    """Write the log to a file of at most ~0.5 MB (plus two older ones). Safe to call twice."""
    path = log_path()
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in log.handlers):
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=2,
                                                       encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        log.addHandler(handler)
        log.setLevel(level)
        log.propagate = False
        _record_hard_crashes()
    return path


_crash_file = None      # (kept open: the handler writes to it when the program dies without a Python error)


def _record_hard_crashes():
    """A crash inside a native library (sound, graphics) leaves no Python error: faulthandler writes where it
    happened to crash.log, so the next look at it says what died."""
    global _crash_file
    if _crash_file is not None:
        return
    try:
        _crash_file = open(crash_path(), "a", encoding="utf-8")
        faulthandler.enable(_crash_file, all_threads=True)
    except (OSError, RuntimeError, ValueError):
        _crash_file = None
