"""A backup of DISO's own data in one file (.disoyedek, a zip): the settings, the playlists, the download list
and history, the searches. Taken to another PC (or kept for a rainy day) and brought back from there.

Bringing a backup back cannot happen while DISO runs (it would write its own state over it when closing),
so the files wait in "restore-pending" and are put in place at the next start, before anything reads them."""
import json
import os
import shutil
import time
import zipfile

from . import brand
from .utils import app_data_dir

EXTENSION = ".disoyedek"
META = "diso-yedek.json"
FILES = ("settings.json", "playlists.json", "downloads.json", "history.json")
PENDING = "restore-pending"


class BackupError(Exception):
    pass


def default_name(now=None) -> str:
    return time.strftime("DISO-yedek-%Y-%m-%d", time.localtime(now)) + EXTENSION


def make_backup(target: str, folder=None) -> list:
    """Write the backup; returns the names of the files in it."""
    folder = folder or app_data_dir()
    present = [n for n in FILES if os.path.isfile(os.path.join(folder, n))]
    if not present:
        raise BackupError("Yedeklenecek bir şey yok: DISO'da henüz ayar ya da liste kaydedilmemiş.")
    tmp = target + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(META, json.dumps({"app": brand.NAME, "version": brand.VERSION_LABEL, "made": time.time(),
                                     "files": present}, ensure_ascii=False))
        for name in present:
            z.write(os.path.join(folder, name), name)
    os.replace(tmp, target)
    return present


def read_backup(path: str) -> dict:
    """What a backup holds: {"version", "made", "files": {name: bytes}}. Refuses anything that is not ours."""
    try:
        with zipfile.ZipFile(path) as z:
            meta = json.loads(z.read(META).decode("utf-8"))
            if meta.get("app") != brand.NAME:
                raise BackupError("Bu bir DISO yedeği değil.")
            files = {}
            for name in z.namelist():
                if name == META:
                    continue
                if name not in FILES:                       # only our own files, by exact name (no paths)
                    raise BackupError(f"Yedekte tanımadığım bir dosya var: {name}")
                data = z.read(name)
                json.loads(data.decode("utf-8"))            # each one must be readable JSON
                files[name] = data
    except BackupError:
        raise
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
        raise BackupError("Bu dosya bir DISO yedeği değil ya da bozuk.") from e
    if not files:
        raise BackupError("Yedeğin içi boş.")
    return {"version": str(meta.get("version", "")), "made": meta.get("made"), "files": files}


def prepare_restore(path: str, folder=None) -> dict:
    """Check the backup and put its files aside; they are used at the next start (apply_pending)."""
    content = read_backup(path)
    folder = folder or app_data_dir()
    pending = os.path.join(folder, PENDING)
    shutil.rmtree(pending, ignore_errors=True)
    os.makedirs(pending)
    for name, data in content["files"].items():
        with open(os.path.join(pending, name), "wb") as f:
            f.write(data)
    return content


def apply_pending(folder=None) -> list:
    """At start, before the settings are read: a waiting backup replaces the current files. The files
    it replaces are kept as *.before-restore, in case. Returns the names that were brought back."""
    folder = folder or app_data_dir()
    pending = os.path.join(folder, PENDING)
    if not os.path.isdir(pending):
        return []
    done = []
    for name in FILES:
        src = os.path.join(pending, name)
        if not os.path.isfile(src):
            continue
        dest = os.path.join(folder, name)
        if os.path.isfile(dest):
            shutil.copy2(dest, dest + ".before-restore")
        os.replace(src, dest)
        done.append(name)
    shutil.rmtree(pending, ignore_errors=True)
    return done


def cancel_pending(folder=None) -> None:
    shutil.rmtree(os.path.join(folder or app_data_dir(), PENDING), ignore_errors=True)
