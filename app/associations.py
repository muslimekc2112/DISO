"""🧲 .torrent files and magnet: links open in DISO: a double click on a .torrent, a magnet link clicked in
the browser. Registered for this Windows user (HKCU\\Software\\Classes) when the program runs; DISO also
appears in Windows' "Default apps" so it can be chosen there when another program holds them. A program
that already owns magnet: links is not pushed aside (Windows asks the user then).

The program gets the file or the link on its command line: links_from_argv() reads it, send_to_running()
hands it to the DISO that is already open (its local bridge, see bridge.py)."""
import os
import sys

PROGID_TORRENT = "DISO.torrent"
PROGID_MAGNET = "DISO.magnet"
APP_NAME = "DISO"


def links_from_argv(argv) -> list:
    """magnet: links and .torrent files given to the program (as file:/// addresses, as the 📄 button does)."""
    import pathlib
    out = []
    for a in argv or []:
        a = (a or "").strip().strip('"')
        if a.lower().startswith("magnet:?"):
            out.append(a)
        elif a.lower().endswith(".torrent") and os.path.isfile(a):
            out.append(pathlib.Path(os.path.abspath(a)).as_uri())
    return out


def send_to_running(urls, port) -> bool:
    """Give these links to the DISO that already runs (True when it took them)."""
    import requests
    try:
        r = requests.post(f"http://127.0.0.1:{port}/add", json={"urls": list(urls), "kind": "auto"}, timeout=5,
                          proxies={"http": None, "https": None})
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------------------ the registry
def _paths(prefix=""):
    classes = prefix + r"Software\Classes"
    return {"classes": classes, "torrent": classes + "\\" + PROGID_TORRENT, "magnet_id": classes + "\\" + PROGID_MAGNET,
            "ext": classes + r"\.torrent", "magnet": classes + r"\magnet",
            "caps": prefix + r"Software\ISO\DISO\Capabilities", "apps": prefix + r"Software\RegisteredApplications"}


def command_for(exe) -> str:
    return f'"{exe}" "%1"'


def _set(hive, path, name, value):
    import winreg
    with winreg.CreateKeyEx(hive, path, 0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _get(hive, path, name=""):
    import winreg
    try:
        with winreg.OpenKey(hive, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _delete_tree(hive, path):
    import winreg
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            while True:
                try:
                    child = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(hive, path + "\\" + child)
        winreg.DeleteKey(hive, path)
    except OSError:
        pass


def _delete_value(hive, path, name):
    import winreg
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_WRITE) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass


def _changed():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)      # SHCNE_ASSOCCHANGED
    except Exception:  # noqa: BLE001
        pass


def register(exe, hive=None, prefix="") -> dict:
    """Make .torrent files and magnet: links open in DISO (as far as no other program holds them).
    {"torrent": True/False, "magnet": True/False}: whether DISO now opens them."""
    import winreg
    hive = winreg.HKEY_CURRENT_USER if hive is None else hive
    p = _paths(prefix)
    command, icon = command_for(exe), f'"{exe}",0'
    _set(hive, p["torrent"], "", "Torrent dosyası (DISO)")
    _set(hive, p["torrent"] + r"\DefaultIcon", "", icon)
    _set(hive, p["torrent"] + r"\shell\open\command", "", command)
    _set(hive, p["magnet_id"], "", "URL:Magnet (DISO)")
    _set(hive, p["magnet_id"], "URL Protocol", "")
    _set(hive, p["magnet_id"] + r"\DefaultIcon", "", icon)
    _set(hive, p["magnet_id"] + r"\shell\open\command", "", command)
    _set(hive, p["ext"] + r"\OpenWithProgids", PROGID_TORRENT, "")
    current = _get(hive, p["ext"])
    if not current or current == PROGID_TORRENT:
        _set(hive, p["ext"], "", PROGID_TORRENT)
    magnet_command = _get(hive, p["magnet"] + r"\shell\open\command")
    if magnet_command is None or magnet_command == command or _ours(magnet_command):
        _set(hive, p["magnet"], "", "URL:Magnet")
        _set(hive, p["magnet"], "URL Protocol", "")
        _set(hive, p["magnet"] + r"\DefaultIcon", "", icon)
        _set(hive, p["magnet"] + r"\shell\open\command", "", command)
    _set(hive, p["caps"], "ApplicationName", APP_NAME)
    _set(hive, p["caps"], "ApplicationDescription", "İndirme yöneticisi ve müzik çalar")
    _set(hive, p["caps"] + r"\FileAssociations", ".torrent", PROGID_TORRENT)
    _set(hive, p["caps"] + r"\URLAssociations", "magnet", PROGID_MAGNET)
    _set(hive, p["apps"], APP_NAME, p["caps"][len(prefix):])
    _changed()
    return status(exe, hive, prefix)


def _ours(command) -> bool:
    return "diso" in (command or "").lower()


def status(exe, hive=None, prefix="") -> dict:
    import winreg
    hive = winreg.HKEY_CURRENT_USER if hive is None else hive
    p = _paths(prefix)
    return {"torrent": _get(hive, p["ext"]) == PROGID_TORRENT,
            "magnet": _get(hive, p["magnet"] + r"\shell\open\command") == command_for(exe)}


def unregister(hive=None, prefix="", inside=None) -> bool:
    """Take DISO's registrations away (the uninstaller; `inside`: only when they lead into that folder)."""
    import winreg
    hive = winreg.HKEY_CURRENT_USER if hive is None else hive
    p = _paths(prefix)
    mine = _get(hive, p["torrent"] + r"\shell\open\command") or ""
    if inside and mine and os.path.normcase(os.path.abspath(inside)) not in os.path.normcase(mine):
        return False                                       # another copy of DISO owns them now
    magnet_command = _get(hive, p["magnet"] + r"\shell\open\command")
    if magnet_command and (magnet_command == mine or (inside and os.path.normcase(os.path.abspath(inside))
                                                      in os.path.normcase(magnet_command))):
        _delete_tree(hive, p["magnet"])
    if _get(hive, p["ext"]) == PROGID_TORRENT:
        _delete_value(hive, p["ext"], "")
    _delete_value(hive, p["ext"] + r"\OpenWithProgids", PROGID_TORRENT)
    for key in ("torrent", "magnet_id"):
        _delete_tree(hive, p[key])
    unregister_protocol(hive, prefix)
    _delete_tree(hive, p["caps"])
    _delete_value(hive, p["apps"], APP_NAME)
    _changed()
    return True


def open_default_apps():
    """Windows' "Default apps" page for DISO (to choose it for .torrent / magnet when another program has them)."""
    for target in (f"ms-settings:defaultapps?registeredAppUser={APP_NAME}", "ms-settings:defaultapps"):
        try:
            os.startfile(target)
            return True
        except OSError:
            continue
    return False


# ---- diso: links, used by the buttons of the "download finished" notification (notify.py)
PROTOCOL = "diso"


def register_protocol(exe, hive=None, prefix="") -> None:
    """diso:open?<path> / diso:folder?<path> start DISO.exe, which opens the file or shows it in its folder."""
    import winreg
    hive = winreg.HKEY_CURRENT_USER if hive is None else hive
    key = prefix + r"Software\Classes" + "\\" + PROTOCOL
    _set(hive, key, "", "URL:DISO")
    _set(hive, key, "URL Protocol", "")
    _set(hive, key + r"\DefaultIcon", "", f'"{exe}",0')
    _set(hive, key + r"\shell\open\command", "", command_for(exe))


def unregister_protocol(hive=None, prefix="") -> None:
    import winreg
    hive = winreg.HKEY_CURRENT_USER if hive is None else hive
    _delete_tree(hive, prefix + r"Software\Classes" + "\\" + PROTOCOL)


def protocol_link(action, path) -> str:
    from urllib.parse import quote
    return f"{PROTOCOL}:{action}?{quote(str(path), safe='')}"


def protocol_action(argv):
    """("open" | "folder", path) when DISO was started by such a link, else None."""
    from urllib.parse import unquote
    for a in argv or []:
        a = (a or "").strip().strip('"')
        head, sep, rest = a.partition("?")
        if sep and head.lower() in (f"{PROTOCOL}:open", f"{PROTOCOL}:folder"):
            return head.lower().split(":", 1)[1], unquote(rest).rstrip("/")
    return None


def run_protocol_action(action, path) -> bool:
    """Open the file / show it selected in Explorer (False when it is not there any more)."""
    import subprocess
    if not path or not os.path.exists(path):
        return False
    if action == "open":
        os.startfile(path)
    else:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    return True


def program_path():
    """The DISO.exe that should open them (None when running from the source: nothing to register)."""
    if os.environ.get("DISO_NO_NATIVE_HOST") or os.environ.get("HIZLI_SETUP_TEST_ROOT"):
        return None                                        # a test run: the real registry is not touched
    return sys.executable if getattr(sys, "frozen", False) else None
