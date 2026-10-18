"""Log file (~/.hizli_indirici/hizli_indirici.log) so a problem can be looked at afterwards."""
import logging
import logging.handlers
import os

from .utils import app_data_dir

log = logging.getLogger("hizli")
log.addHandler(logging.NullHandler())  # silent until setup_logging() is called (tests, tools)


def log_path() -> str:
    return os.path.join(app_data_dir(), "hizli_indirici.log")


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
    return path
