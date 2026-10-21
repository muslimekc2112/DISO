"""DISO's own files (settings, playlists, the download list, the history, the channels) written so that a power
cut or a full disk never leaves them broken, and read so that a broken one comes back from its last good copy.

write_json(): the new text goes to "<file>.tmp", is forced onto the disk, then takes the place of the old file;
about once an hour the old file (when it reads well) is kept as "<file>.bak" first. read_json(): a file that
does not read (empty, cut off, not JSON) is put aside as "<file>.bozuk" and its .bak is used instead, and the
window says so once (recovered)."""
import json
import os
import shutil
import threading
import time

from .logs import log

BACKUP_EVERY = 3600            # seconds: how old the .bak may get before a good file is copied over it
recovered = []                 # names of the files that came back from their .bak in this run (shown once)
_lock = threading.Lock()


class Broken(ValueError):
    """The file and its last good copy both do not read."""


def _read(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        raise ValueError("empty")
    return json.loads(text)


def read_json(path):
    """The data of a JSON file; its .bak when the file itself is broken. FileNotFoundError when there is
    none at all, Broken when neither reads."""
    try:
        return _read(path)
    except FileNotFoundError:
        if not os.path.isfile(path + ".bak"):
            raise
        problem = "missing"
    except (OSError, ValueError) as e:
        problem = str(e)[:120] or type(e).__name__
        try:
            shutil.copy2(path, path + ".bozuk")            # kept for a look later, never read again
        except OSError:
            pass
    try:
        data = _read(path + ".bak")
    except (OSError, ValueError) as e:
        log.error("%s is broken (%s) and its copy too (%s)", path, problem, e)
        raise Broken(path) from e
    log.warning("%s was broken (%s): its last good copy is used", path, problem)
    try:
        shutil.copy2(path + ".bak", path)
    except OSError:
        pass
    with _lock:
        recovered.append(os.path.basename(path))
    return data


def _backup(path):
    """Keep the file that is about to be replaced as .bak, when it reads well and the .bak is old."""
    try:
        if time.time() - os.path.getmtime(path + ".bak") < BACKUP_EVERY:
            return
    except OSError:
        pass                                               # no .bak yet
    try:
        _read(path)
        shutil.copy2(path, path + ".bak")
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        log.info("no backup of %s: %s", path, e)


def write_json(path, data, **dump_options):
    """Write data as JSON so that the file is either the old one or the whole new one, never half of each."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, **dump_options)
        f.flush()
        os.fsync(f.fileno())
    _backup(path)
    os.replace(tmp, path)


def take_recovered():
    """The files that came back from a copy since the last call (for one notice in the window)."""
    with _lock:
        out = list(dict.fromkeys(recovered))
        recovered.clear()
    return out
