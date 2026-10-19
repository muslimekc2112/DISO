"""Installing and removing DISO. No window in here: setup_main / uninstall_main show it.

Everything the installer creates is written into install.json inside the install folder, and the
uninstaller removes exactly that (never a whole folder it did not make). Installing is done in two
steps (copy and check everything under temporary names, then swap), and any error puts the
computer back the way it was."""
import hashlib
import json
import os
import shutil
import time
import winreg
from dataclasses import dataclass, field

from app import brand, i18n

from . import winapi

APP_ID = brand.APP_ID
DISPLAY_NAME = brand.NAME
PUBLISHER = brand.PUBLISHER
EXE_NAME = brand.EXE_NAME
LEGACY_IDS = tuple(brand.LEGACY_APP_IDS)
SHORTCUT_NAME = DISPLAY_NAME + ".lnk"
UNINSTALL_SHORTCUT = DISPLAY_NAME + "'yu Kaldır.lnk"
UNINSTALL_SHORTCUT_EN = "Uninstall " + DISPLAY_NAME + ".lnk"     # the same, made by an English install
UNINSTALLER_NAME = "Uninstall.exe"
MANIFEST_NAME = "install.json"
PAYLOAD_NAME = "payload.json"
# folders with the user's data that may be deleted (only if the user asks): the current one and the old one
DATA_DIR_NAMES = {brand.DATA_DIR_NAME.lower(), *(n.lower() for n in brand.LEGACY_DATA_DIR_NAMES)}
UNINSTALL_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
TEST_ROOT_ENV = "HIZLI_SETUP_TEST_ROOT"          # tests: keep every change under this folder / registry key
MAX_PATH_LEN = 150
ILLEGAL = '<>:"|?*'


class SetupError(Exception):
    """Something the user can understand and act on (the message is shown as it is)."""


@dataclass
class Env:
    """Where things go. The real one asks Windows; tests give temporary places."""
    programs_dir: str                            # the Start Menu's Programs folder
    desktop_dir: str
    default_install_dir: str
    user_data_dir: str
    reg_prefix: str = ""                         # put in front of every registry path (tests)
    hive: int = winreg.HKEY_CURRENT_USER
    app_id: str = APP_ID
    legacy_data_dirs: tuple = ()                 # where earlier versions kept the user's data
    legacy_envs: tuple = ()                      # earlier installs (under the old name) to remove first

    @property
    def uninstall_key(self):
        return self.reg_prefix + UNINSTALL_ROOT + "\\" + self.app_id

    @property
    def run_key(self):
        return self.reg_prefix + RUN_SUBKEY

    @property
    def start_menu_dir(self):
        return os.path.join(self.programs_dir, PUBLISHER)

    @property
    def needs_admin(self):
        """An install for every user (Program Files, HKLM) can only be made by an administrator."""
        return self.hive == winreg.HKEY_LOCAL_MACHINE


def production_env() -> Env:
    root = os.environ.get(TEST_ROOT_ENV)
    if root:
        return test_env(root)
    local = winapi.known_folder(winapi.FOLDER_LOCAL_APPDATA)
    home = os.path.expanduser("~")
    older = Env(programs_dir=winapi.known_folder(winapi.FOLDER_PROGRAMS), desktop_dir=winapi.known_folder(winapi.FOLDER_DESKTOP),
                default_install_dir=os.path.join(local, "Programs", LEGACY_IDS[0]),
                user_data_dir=os.path.join(home, brand.LEGACY_DATA_DIR_NAMES[0]),
                hive=winreg.HKEY_CURRENT_USER, app_id=LEGACY_IDS[0])
    return Env(programs_dir=winapi.known_folder(winapi.FOLDER_COMMON_PROGRAMS),
               desktop_dir=winapi.known_folder(winapi.FOLDER_PUBLIC_DESKTOP),
               default_install_dir=os.path.join(winapi.known_folder(winapi.FOLDER_PROGRAM_FILES), PUBLISHER, APP_ID),
               user_data_dir=os.path.join(local, brand.DATA_DIR_NAME), hive=winreg.HKEY_LOCAL_MACHINE,
               legacy_data_dirs=tuple(os.path.join(home, n) for n in brand.LEGACY_DATA_DIR_NAMES), legacy_envs=(older,))


def test_env(root: str) -> Env:
    """An environment that touches nothing outside `root` and one throw-away registry key (the key is
    under HKCU, so no administrator is needed; the real one is under HKLM)."""
    digest = hashlib.sha1(os.path.abspath(root).lower().encode("utf-8")).hexdigest()[:12]
    prefix = rf"Software\DISOTest\{digest}" + "\\"
    older = Env(programs_dir=os.path.join(root, "StartMenuOlder", "Programs"), desktop_dir=os.path.join(root, "DesktopOlder"),
                default_install_dir=os.path.join(root, "Programs", LEGACY_IDS[0]),
                user_data_dir=os.path.join(root, "User", brand.LEGACY_DATA_DIR_NAMES[0]),
                reg_prefix=prefix + "older" + "\\", app_id=LEGACY_IDS[0])
    return Env(programs_dir=os.path.join(root, "StartMenu", "Programs"), desktop_dir=os.path.join(root, "Desktop"),
               default_install_dir=os.path.join(root, "Programs", PUBLISHER, APP_ID),
               user_data_dir=os.path.join(root, "User", brand.DATA_DIR_NAME), reg_prefix=prefix,
               legacy_data_dirs=(older.user_data_dir,), legacy_envs=(older,))


@dataclass
class Options:
    install_dir: str
    desktop_shortcut: bool = True
    start_menu: bool = True
    autostart: object = None                     # True: start with Windows, False: do not, None: leave as it is


@dataclass
class Result:
    install_dir: str
    exe_path: str
    version: str = ""
    warnings: list = field(default_factory=list)
    leftovers: list = field(default_factory=list)


# ----------------------------------------------------------------------------------- helpers
def sha256_of(path, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                return h.hexdigest()
            h.update(block)


def _noop(fraction, text):
    pass


def same_path(a, b) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def inside(path, folder) -> bool:
    folder = os.path.normcase(os.path.abspath(folder)).rstrip("\\/") + os.sep
    return os.path.normcase(os.path.abspath(path)).startswith(folder)


def _remove_file(path, retries=6, wait=0.4, sleep=time.sleep):
    """Delete a file, trying again for a moment (antivirus often holds a new file for a second).
    Returns True when it is gone."""
    for attempt in range(retries):
        try:
            os.remove(path)
            return True
        except FileNotFoundError:
            return True
        except PermissionError:
            try:
                os.chmod(path, 0o666)
            except OSError:
                pass
        except OSError:
            pass
        if attempt < retries - 1:
            sleep(wait)
    return not os.path.exists(path)


def _replace(src, dst, retries=6, wait=0.5, sleep=time.sleep):
    """os.replace that tries again for a moment when something (antivirus, an indexer) holds the file."""
    for attempt in range(retries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            sleep(wait)


def all_dirs(dests) -> list:
    """Every folder the files need, the ones in between too: 'a/b/c.txt' -> ['a', 'a/b'] (OS separators)."""
    out = set()
    for dest in dests:
        parent = os.path.dirname(dest.replace("/", os.sep))
        while parent:
            out.add(parent)
            parent = os.path.dirname(parent)
    return sorted(out)


def _make_dirs(path, created) -> None:
    """os.makedirs that notes each folder it really made (a roll-back removes exactly those)."""
    missing = []
    while path and not os.path.isdir(path):
        missing.append(path)
        path = os.path.dirname(path)
    for folder in reversed(missing):
        os.mkdir(folder)
        created.append(folder)


def _rmdir_if_empty(path):
    try:
        os.rmdir(path)
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------------------- registry
def _read_value(env, subkey, name, default=None):
    try:
        with winreg.OpenKey(env.hive, subkey) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def _write_values(env, subkey, values: dict):
    with winreg.CreateKeyEx(env.hive, subkey, 0, winreg.KEY_SET_VALUE) as key:
        for name, (kind, data) in values.items():
            winreg.SetValueEx(key, name, 0, kind, data)


def _snapshot_key(env, subkey):
    """All values of a key as {name: (type, data)}, or None if the key does not exist."""
    try:
        with winreg.OpenKey(env.hive, subkey) as key:
            out, i = {}, 0
            while True:
                try:
                    name, data, kind = winreg.EnumValue(key, i)
                except OSError:
                    return out
                out[name] = (kind, data)
                i += 1
    except OSError:
        return None


def _restore_key(env, subkey, snapshot):
    if snapshot is None:
        delete_key_tree(env, subkey)
    else:
        _write_values(env, subkey, snapshot)


def _delete_value(env, subkey, name) -> bool:
    try:
        with winreg.OpenKey(env.hive, subkey, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
        return True
    except OSError:
        return False


def delete_key_tree(env, subkey):
    """Remove a registry key with everything below it (nothing happens if it does not exist)."""
    try:
        with winreg.OpenKey(env.hive, subkey, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                delete_key_tree(env, subkey + "\\" + child)
        winreg.DeleteKey(env.hive, subkey)
    except FileNotFoundError:
        pass


def find_existing(env):
    """(install folder, version) of a copy that is registered for this user, else (None, None)."""
    location = _read_value(env, env.uninstall_key, "InstallLocation")
    if location and os.path.isdir(location):
        return location, _read_value(env, env.uninstall_key, "DisplayVersion", "")
    return None, None


def autostart_command(exe_path) -> str:
    return f'"{exe_path}" --minimized'


# ----------------------------------------------------------------------------------- checks
def read_manifest(install_dir, app_ids=None):
    """install.json of a folder if it was made by us (under this name or an older one), else None."""
    ids = tuple(app_ids) if app_ids else (APP_ID,) + LEGACY_IDS
    try:
        with open(os.path.join(install_dir, MANIFEST_NAME), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and data.get("app") in ids else None
    except (OSError, ValueError):
        return None


def is_ours(install_dir) -> bool:
    return read_manifest(install_dir) is not None


def resolve_install_dir(chosen: str) -> str:
    """The folder the program will really go into. A folder the user picked that already holds
    other things (Downloads, Desktop ...) gets a sub-folder of its own, so that removing the
    program can never take anything else with it."""
    text = (chosen or "").strip().strip('"')
    if not text:
        raise SetupError("Kurulum klasörünü yaz.")
    if not os.path.isabs(text) or text.startswith("\\\\"):
        raise SetupError("Klasörü tam yol olarak yaz, bu bilgisayardaki bir sürücüde olsun (örn. C:\\Programlar\\DISO).")
    path = os.path.normpath(text)
    drive, rest = os.path.splitdrive(path)
    if not rest.strip("\\/"):
        raise SetupError("Bir klasör seç; sürücünün kendisi olmaz.")
    for part in rest.strip("\\/").split("\\"):
        if any(c in part for c in ILLEGAL) or part.endswith((" ", ".")) or not part:
            raise SetupError(f"Klasör adında geçersiz karakter var: “{part}”")
    if len(path) > MAX_PATH_LEN:
        raise SetupError("Klasör yolu çok uzun; daha kısa bir klasör seç.")
    if os.path.isfile(path):
        raise SetupError("Seçtiğin yol bir dosya; bir klasör seç.")
    if os.path.isdir(path) and os.listdir(path) and not is_ours(path):
        path = os.path.join(path, APP_ID)
        if os.path.isfile(path):
            raise SetupError("Seçtiğin klasörde aynı adlı bir dosya var; başka klasör seç.")
    return path


def _shown(dest) -> str:
    """What the progress line says about a file: the program's own inner files are just 'DISO'."""
    return "DISO" if dest.replace("\\", "/").startswith("_internal/") else dest


def load_payload(payload_dir):
    """The list of files this setup carries: [{"name", "dest", "sha256", "size"}], and its version."""
    try:
        with open(os.path.join(payload_dir, PAYLOAD_NAME), encoding="utf-8") as f:
            data = json.load(f)
        files = data["files"]
        assert isinstance(files, list) and files
    except Exception as e:  # noqa: BLE001
        raise SetupError("Kurulum paketi eksik ya da bozuk (payload.json okunamadı). Kurulum dosyasını yeniden indir.") from e
    return data


# ----------------------------------------------------------------------------------- install
def install(payload_dir, options: Options, env: Env, progress=_noop, closer=winapi.close_programs_in,
            shortcut=winapi.create_shortcut, free_space=winapi.free_space, now=time.time) -> Result:
    data = load_payload(payload_dir)
    files = data["files"]
    number = str(data.get("version", ""))
    version = str(data.get("label") or number)                    # "0.10.0 beta": what the user sees and what is recorded
    target = resolve_install_dir(options.install_dir)
    result = Result(install_dir=target, exe_path=os.path.join(target, EXE_NAME), version=version)

    # ---- before touching anything: is it all there, and is there room?
    progress(0.0, "Dosyalara bakıyorum…")
    for item in files:
        src = os.path.join(payload_dir, item["name"])
        if not os.path.isfile(src):
            raise SetupError(f"Kurulum paketinde “{item['name']}” yok. Kurulum dosyasını yeniden indir.")
        if os.path.getsize(src) != item["size"] or sha256_of(src) != item["sha256"]:
            raise SetupError(f"“{item['name']}” bozulmuş (kurulum dosyası eksik inmiş olabilir). Yeniden indir.")
    need = int(sum(item["size"] for item in files) * 2.1) + (50 << 20)       # staged copy + the old one + room
    if free_space(target) < need:
        raise SetupError(f"Diskte yeterli yer yok: yaklaşık {need >> 20} MB lazım. Başka bir sürücü seç.")

    # ---- an older copy somewhere else is removed first (one program, one entry in the list)
    old_dir, _ = find_existing(env)
    if old_dir and not same_path(old_dir, target) and is_ours(old_dir):
        progress(0.05, "Önceki kurulum kaldırılıyor…")
        uninstall(old_dir, env, remove_data=False, closer=closer, progress=_noop)
    # ---- an install from before the rename (per user, under the old name) is removed too; if it started
    #      with Windows, the new one does as well
    legacy_autostart = False
    for older in env.legacy_envs:
        old_dir, _ = find_existing(older)
        if old_dir and is_ours(old_dir):
            progress(0.06, "Eski sürüm kaldırılıyor…")
            run = str(_read_value(older, older.run_key, older.app_id, "") or "")
            if run and inside(run.strip().split('" ')[0].strip('"'), old_dir):
                legacy_autostart = True
            uninstall(old_dir, older, remove_data=False, closer=closer, progress=_noop)
    autostart = options.autostart
    if autostart is None and legacy_autostart:
        autostart = True
    progress(0.08, "Çalışan uygulama kapatılıyor…")
    if os.path.isdir(target):
        closer(target)

    created_dirs, committed, staged, created_links = [], [], [], []
    previous = read_manifest(target) or {}
    registry_written = False
    run_before = _read_value(env, env.run_key, env.app_id)
    key_before = _snapshot_key(env, env.uninstall_key)
    try:
        # ---- 1. copy everything beside its place under a temporary name and check it
        existed = os.path.isdir(target)
        os.makedirs(target, exist_ok=True)
        if not existed:
            created_dirs.append(target)
        total = sum(item["size"] for item in files) or 1
        done = 0
        for item in files:
            dest = os.path.join(target, item["dest"])
            _make_dirs(os.path.dirname(dest), created_dirs)
            temp = dest + ".new"
            src = os.path.join(payload_dir, item["name"])
            staged.append(temp)
            with open(src, "rb") as fin, open(temp, "wb") as fout:
                while True:
                    block = fin.read(4 << 20)
                    if not block:
                        break
                    fout.write(block)
                    done += len(block)
                    progress(0.10 + 0.70 * done / total, f"Kopyalanıyor: {_shown(item['dest'])}")
            if sha256_of(temp) != item["sha256"]:
                raise SetupError(f"“{item['dest']}” diske doğru yazılamadı (disk dolu ya da bir güvenlik programı engelledi).")

        # ---- 2. swap them in (the old ones are kept as .old until everything worked)
        progress(0.82, "Dosyalar yerine konuyor…")
        for item in files:
            dest = os.path.join(target, item["dest"])
            entry = [dest, os.path.exists(dest), "waiting"]       # what a roll-back must undo depends on how far it got
            committed.append(entry)
            if entry[1]:
                _replace(dest, dest + ".old")
            entry[2] = "old aside"
            _replace(dest + ".new", dest)
            entry[2] = "in place"
            staged.remove(dest + ".new")

        # ---- 3. shortcuts (a missing shortcut is a pity, not a reason to undo everything)
        progress(0.88, "Kısayolları koyuyorum…")
        exe = os.path.join(target, EXE_NAME)
        uninstaller = os.path.join(target, UNINSTALLER_NAME)
        wanted = []
        about = i18n.tr("Dosya, video ve müzik indirme yöneticisi")
        if options.start_menu:
            wanted.append((os.path.join(env.start_menu_dir, SHORTCUT_NAME), exe, "", about))
            if os.path.isfile(uninstaller):
                wanted.append((os.path.join(env.start_menu_dir, i18n.tr(UNINSTALL_SHORTCUT)), uninstaller, "",
                               i18n.tr(f"{DISPLAY_NAME}'yu kaldır")))
        if options.desktop_shortcut:
            wanted.append((os.path.join(env.desktop_dir, SHORTCUT_NAME), exe, "", about))
        for link, link_target, args, text in wanted:
            try:
                shortcut(link, link_target, arguments=args, workdir=target, description=text, icon=exe, icon_index=0)
                created_links.append(link)
            except Exception as e:  # noqa: BLE001
                result.warnings.append(f"Kısayol oluşturulamadı ({os.path.basename(link)}): {e}")

        # ---- 4. the entry in "Apps & features", and (if asked) starting with Windows
        progress(0.93, "Uygulamalar listesine yazıyorum…")
        size_kb = int(sum(item["size"] for item in files) / 1024)
        registry_written = True
        _write_values(env, env.uninstall_key, {
            "DisplayName": (winreg.REG_SZ, DISPLAY_NAME), "DisplayVersion": (winreg.REG_SZ, version),
            "Publisher": (winreg.REG_SZ, PUBLISHER), "InstallLocation": (winreg.REG_SZ, target),
            "DisplayIcon": (winreg.REG_SZ, f'"{exe}",0'),
            "UninstallString": (winreg.REG_SZ, f'"{uninstaller}"'),
            "QuietUninstallString": (winreg.REG_SZ, f'"{uninstaller}" --silent'),
            "EstimatedSize": (winreg.REG_DWORD, size_kb), "NoModify": (winreg.REG_DWORD, 1),
            "NoRepair": (winreg.REG_DWORD, 1), "InstallDate": (winreg.REG_SZ, time.strftime("%Y%m%d", time.localtime(now()))),
        })
        if autostart is True:
            _write_values(env, env.run_key, {env.app_id: (winreg.REG_SZ, autostart_command(exe))})
        elif autostart is False and inside(str(_read_value(env, env.run_key, env.app_id, "")).strip('"'), target):
            _delete_value(env, env.run_key, env.app_id)

        # ---- 5. the list of what we made (the uninstaller works from this)
        manifest = {"app": env.app_id, "version": version, "number": number, "install_dir": target,
                    "files": [item["dest"].replace("/", os.sep) for item in files] + [MANIFEST_NAME],
                    "dirs": all_dirs(item["dest"] for item in files),
                    "shortcuts": created_links, "start_menu_dir": env.start_menu_dir if options.start_menu else "",
                    "installed_at": int(now())}
        manifest_path = os.path.join(target, MANIFEST_NAME)
        staged.append(manifest_path + ".new")                       # a roll-back removes it if the next steps fail
        with open(manifest_path + ".new", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        _replace(manifest_path + ".new", manifest_path)
        staged.remove(manifest_path + ".new")
    except SetupError:
        _roll_back(env, target, committed, staged, created_dirs, created_links, registry_written, run_before, key_before)
        raise
    except PermissionError as e:
        _roll_back(env, target, committed, staged, created_dirs, created_links, registry_written, run_before, key_before)
        raise SetupError(f"“{target}” klasörüne yazma iznim yok ya da bir dosya kullanımda (DISO açıksa kapat). "
                         "Başka bir klasör seçmeyi dene.") from e
    except OSError as e:
        _roll_back(env, target, committed, staged, created_dirs, created_links, registry_written, run_before, key_before)
        raise SetupError(f"Dosyalar yazılamadı: {e.strerror or e}. Disk dolu olabilir; başka bir sürücü seçmeyi dene.") from e
    except BaseException:
        _roll_back(env, target, committed, staged, created_dirs, created_links, registry_written, run_before, key_before)
        raise
    # ---- done: the old copies are not needed any more
    progress(0.97, "Temizleniyor…")
    for dest, had_old, _state in committed:
        if had_old:
            _remove_file(dest + ".old")
    for rel in previous.get("files", []):                         # a file of an older version that is gone now
        if rel not in manifest["files"]:
            _remove_file(os.path.join(target, rel))
    for rel in sorted(previous.get("dirs", []), reverse=True):
        if rel not in manifest["dirs"]:
            _rmdir_if_empty(os.path.join(target, rel))
    for link in previous.get("shortcuts", []):
        if link not in created_links and os.path.isfile(link):
            _forget_link(link, target)
    progress(1.0, "Kurulum bitti, hazırız")
    return result


def _forget_link(link, install_dir) -> bool:
    """Delete a shortcut of ours, but only if it still points into the install folder."""
    try:
        info = winapi.read_shortcut(link)
        if not inside(info["target"], install_dir):
            return False
    except OSError:
        pass                                    # unreadable: it is ours by name and place, remove it
    return _remove_file(link, retries=2)


def _roll_back(env, target, committed, staged, created_dirs, created_links, registry_written, run_before, key_before):
    for temp in staged:
        _remove_file(temp, retries=2)
    for dest, had_old, state in reversed(committed):
        if state == "waiting":
            continue                                    # nothing of this file was touched yet
        if state == "in place":
            _remove_file(dest, retries=2)               # the new file goes ...
        if had_old and os.path.exists(dest + ".old"):
            try:
                _replace(dest + ".old", dest, retries=3)   # ... and the old one comes back
            except OSError:
                pass
    for link in created_links:
        _remove_file(link, retries=1)
    if env.start_menu_dir:
        _rmdir_if_empty(env.start_menu_dir)
    if registry_written:
        _restore_key(env, env.uninstall_key, key_before)      # gone, or exactly as the older install had it
        if run_before is None:
            _delete_value(env, env.run_key, env.app_id)
        else:
            _write_values(env, env.run_key, {env.app_id: (winreg.REG_SZ, run_before)})
    for folder in sorted(created_dirs, key=len, reverse=True):
        _rmdir_if_empty(folder)


# ----------------------------------------------------------------------------------- uninstall
def uninstall(install_dir, env: Env, remove_data=False, progress=_noop, closer=winapi.close_programs_in,
              read_link=winapi.read_shortcut, sleep=time.sleep, keep=()) -> Result:
    """Remove what install() made. Files that cannot be deleted now (something holds them) are
    scheduled for the next restart and listed in Result.leftovers.
    keep: files to leave for a second call (the uninstaller cannot delete itself while it runs);
    then the list (install.json) and the folder stay too, so that a second call finishes the job."""
    keep = set(keep or ())
    result = Result(install_dir=install_dir, exe_path=os.path.join(install_dir, EXE_NAME))
    manifest = read_manifest(install_dir) or {}
    files = list(manifest.get("files") or [EXE_NAME, UNINSTALLER_NAME, os.path.join("deno", "deno.exe"), MANIFEST_NAME])
    dirs = list(manifest.get("dirs") or ["deno"])
    links = list(manifest.get("shortcuts") or [os.path.join(env.start_menu_dir, SHORTCUT_NAME),
                                               os.path.join(env.start_menu_dir, UNINSTALL_SHORTCUT),
                                               os.path.join(env.start_menu_dir, UNINSTALL_SHORTCUT_EN),
                                               os.path.join(env.desktop_dir, SHORTCUT_NAME)])
    menu_dir = manifest.get("start_menu_dir") or env.start_menu_dir

    progress(0.05, "Çalışan uygulama kapatılıyor…")
    if os.path.isdir(install_dir):
        closer(install_dir)

    progress(0.20, "Başlangıç kaydı temizleniyor…")
    run_value = str(_read_value(env, env.run_key, env.app_id, "") or "")
    if run_value and inside(run_value.strip().split('" ')[0].strip('"'), install_dir):
        _delete_value(env, env.run_key, env.app_id)

    progress(0.30, "Kısayollar siliniyor…")
    for link in links:
        if not os.path.isfile(link):
            continue
        try:
            if not inside(read_link(link)["target"], install_dir):
                continue                                   # the user pointed it somewhere else: not ours any more
        except OSError:
            pass
        if not _remove_file(link, retries=3, sleep=sleep):
            result.leftovers.append(link)
    if menu_dir:
        _rmdir_if_empty(menu_dir)

    progress(0.45, "Uygulamalar listesinden kaldırılıyor…")
    delete_key_tree(env, env.uninstall_key)

    progress(0.55, "Dosyalar siliniyor…")
    leftovers = []
    names = set(files)
    for rel in files:
        names.add(rel + ".new")
        names.add(rel + ".old")
    for rel in sorted(names, key=len, reverse=True):
        if rel in keep or (keep and rel in (MANIFEST_NAME, MANIFEST_NAME + ".new", MANIFEST_NAME + ".old")):
            continue
        path = os.path.join(install_dir, rel)
        if os.path.isfile(path) and not _remove_file(path, sleep=sleep):
            winapi.delete_on_reboot(path)
            leftovers.append(path)
    for rel in sorted(dirs, key=len, reverse=True):
        _rmdir_if_empty(os.path.join(install_dir, rel))
    if not leftovers and not keep:
        _rmdir_if_empty(install_dir)
        parent = os.path.dirname(os.path.normpath(install_dir))
        if os.path.basename(parent).lower() == PUBLISHER.lower() and not os.path.isdir(install_dir):
            _rmdir_if_empty(parent)                                       # the "ISO" folder, once nothing of ours is in it
    result.leftovers += leftovers

    if remove_data:
        progress(0.85, "Ayarlar ve çalma listeleri siliniyor…")
        for folder in (env.user_data_dir, *env.legacy_data_dirs):         # the current one and, if it is still there, the old one
            if os.path.basename(os.path.normpath(folder)).lower() in DATA_DIR_NAMES and os.path.isdir(folder):
                shutil.rmtree(folder, onexc=lambda func, path, exc: result.leftovers.append(path))
    progress(1.0, "Kaldırıldı")
    return result
