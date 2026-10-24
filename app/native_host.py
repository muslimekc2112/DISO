"""The browser's own door to DISO ("native messaging", the way IDM does it).

The extension normally talks to the running app over the local bridge (bridge.py). When DISO is closed
there is nobody to answer, so the extension asks the browser to start this program as its "native host":
the browser runs DISO.exe with the extension's address as the argument and talks to it through
stdin / stdout (each message: 4 bytes of length, then JSON). The host starts the real app, waits until
its bridge answers, says so and ends; the extension then hands the links over as usual.

Messages: {"type": "ping"} and {"type": "launch", "port": n}.

The browser finds the host through the registry: a key per browser whose default value is the path of
a small JSON file (host manifest) that names the program and the one extension allowed to start it.
The installer registers it for every user (HKLM), the app itself for the current user (HKCU) at every
start, so a portable DISO.exe works too. macOS and Linux have no registry: there the manifest itself goes
into a folder of each browser (see host_dirs), also at every start of the app."""
import json
import os
import struct
import subprocess
import sys
import time

from . import __version__

HOST_NAME = "com.iso.diso"
APP_ID = "DISO"
EXTENSION_ID = "adkiobcdpklfjnbajjiocmlifmbhdnei"        # fixed by the "key" in browser_extension/manifest.json
FIREFOX_ID = "diso@iso.local"
DEFAULT_PORT = 17653
# where each browser family looks for native hosts (under HKCU or HKLM); Opera, Vivaldi and other
# Chromium browsers read Chrome's place
CHROMIUM_KEYS = (r"Software\Google\Chrome\NativeMessagingHosts", r"Software\Microsoft\Edge\NativeMessagingHosts",
                 r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts", r"Software\Chromium\NativeMessagingHosts")
FIREFOX_KEY = r"Software\Mozilla\NativeMessagingHosts"
CHROME_MANIFEST = "native_host_chrome.json"
FIREFOX_MANIFEST = "native_host_firefox.json"
MAX_MESSAGE = 1 << 20
LAUNCH_WAIT = 40                                          # s: a portable DISO.exe unpacks itself first
DETACHED_PROCESS, NEW_GROUP, BREAKAWAY = 0x00000008, 0x00000200, 0x01000000
NO_REGISTER_ENV = "DISO_NO_NATIVE_HOST"                   # tests: a throw-away copy must not point the real browsers at itself
SETUP_TEST_ENV = "HIZLI_SETUP_TEST_ROOT"                  # the installer's tests (hizli_setup.core.TEST_ROOT_ENV)


# ------------------------------------------------------------------------------- the host itself
def is_host_call(argv) -> bool:
    """Chrome / Edge / Brave pass the extension's origin; Firefox passes the manifest path and the add-on id."""
    return any(str(a).startswith("chrome-extension://") for a in argv) or FIREFOX_ID in argv


def read_message(stream):
    """The next message, or None when the browser has closed the pipe."""
    head = _read_exact(stream, 4)
    if head is None:
        return None
    size = struct.unpack("<I", head)[0]
    if size > MAX_MESSAGE:
        raise ValueError("message too big")
    body = _read_exact(stream, size)
    if body is None:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(stream, message):
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    stream.write(struct.pack("<I", len(data)) + data)
    stream.flush()


def _read_exact(stream, n):
    out = b""
    while len(out) < n:
        block = stream.read(n - len(out))
        if not block:
            return None
        out += block
    return out


def answer(message, ping, launch, wait=LAUNCH_WAIT, sleep=time.sleep, clock=time.monotonic):
    """What the host says to one message. ping(port) -> bool, launch() -> bool."""
    if not isinstance(message, dict):
        return {"ok": False, "error": "bad message"}
    port = _port(message.get("port"))
    kind = message.get("type")
    if kind == "ping":
        return {"ok": True, "app": APP_ID, "version": __version__, "running": bool(ping(port))}
    if kind == "launch":
        if ping(port):
            return {"ok": True, "started": False}
        if not launch():
            return {"ok": False, "error": "launch failed"}
        end = clock() + wait
        while clock() < end:
            if ping(port):
                return {"ok": True, "started": True}
            sleep(0.25)
        return {"ok": False, "error": "timeout"}
    return {"ok": False, "error": "unknown message"}


def _port(value):
    if isinstance(value, int) and 1024 <= value <= 65535:
        return value
    return saved_port()


def saved_port():
    """The bridge port chosen in DISO's settings."""
    try:
        from .utils import app_data_dir
        with open(os.path.join(app_data_dir(), "settings.json"), encoding="utf-8") as f:
            port = json.load(f).get("bridge_port")
        if isinstance(port, int) and 1024 <= port <= 65535:
            return port
    except Exception:  # noqa: BLE001 - no settings yet
        pass
    return DEFAULT_PORT


def ping(port) -> bool:
    """Does DISO answer on this port? (no Origin header: a local program, which the bridge allows)"""
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{int(port)}/ping", timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP_ID
    except Exception:  # noqa: BLE001 - not running, or something else on the port
        return False


def app_command():
    """How to start DISO: the exe we are, or (from source) Python with main.py."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    exe = sys.executable
    windowless = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return [windowless if os.path.isfile(windowless) else exe, main]


def launch(command=None, popen=subprocess.Popen) -> bool:
    """Start DISO on its own: not a child the browser may kill when it closes us (Firefox puts its native
    hosts in a job; CREATE_BREAKAWAY_FROM_JOB takes the app out of it where that is allowed)."""
    command = command or app_command()
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")     # a fresh copy, not a child of our unpacked files
    if not sys.platform.startswith("win"):                         # macOS / Linux: a session of its own
        try:
            popen(command, cwd=os.path.dirname(command[-1]) or None, close_fds=True, start_new_session=True,
                  env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            return False
    for flags in (DETACHED_PROCESS | NEW_GROUP | BREAKAWAY, DETACHED_PROCESS | NEW_GROUP):
        try:
            popen(command, cwd=os.path.dirname(command[-1]) or None, close_fds=True, creationflags=flags, env=env,
                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue                                               # breaking away is not allowed here: without it
    return False


def std_streams():
    """Binary stdin / stdout. A windowed exe has no sys.stdin, but the browser's pipes are still there."""
    i, o = getattr(sys.stdin, "buffer", None), getattr(sys.stdout, "buffer", None)
    if i is not None and o is not None:
        return i, o
    if not sys.platform.startswith("win"):
        return os.fdopen(0, "rb", buffering=0), os.fdopen(1, "wb", buffering=0)
    import ctypes
    import msvcrt
    k32 = ctypes.windll.kernel32
    k32.GetStdHandle.restype = ctypes.c_void_p
    fin = os.fdopen(msvcrt.open_osfhandle(k32.GetStdHandle(-10), os.O_RDONLY | os.O_BINARY), "rb", buffering=0)
    fout = os.fdopen(msvcrt.open_osfhandle(k32.GetStdHandle(-11), os.O_WRONLY | os.O_BINARY), "wb", buffering=0)
    return fin, fout


def main(argv, streams=None, ping=ping, launch=launch) -> int:
    """Run as the browser's native host until the browser closes the pipe."""
    fin, fout = streams or std_streams()
    while True:
        try:
            message = read_message(fin)
        except (ValueError, UnicodeDecodeError):
            write_message(fout, {"ok": False, "error": "bad message"})
            return 1
        if message is None:
            return 0
        try:
            reply = answer(message, ping, launch)
        except Exception as e:  # noqa: BLE001 - the extension gets told, the browser does not see a crash
            reply = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        write_message(fout, reply)


# ------------------------------------------------------------------------------- registration
def host_manifest(command_path, firefox=False) -> dict:
    out = {"name": HOST_NAME, "description": "DISO", "path": command_path, "type": "stdio"}
    if firefox:
        out["allowed_extensions"] = [FIREFOX_ID]
    else:
        out["allowed_origins"] = [f"chrome-extension://{EXTENSION_ID}/"]
    return out


def write_manifests(folder, command_path) -> list:
    """The two host manifests in `folder`; returns their paths (Chromium, Firefox)."""
    os.makedirs(folder, exist_ok=True)
    paths = []
    for name, firefox in ((CHROME_MANIFEST, False), (FIREFOX_MANIFEST, True)):
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(host_manifest(command_path, firefox), f, ensure_ascii=False, indent=2)
        paths.append(path)
    return paths


def key_paths(prefix=""):
    """[(registry key, firefox?)] for every browser family."""
    return [(prefix + k + "\\" + HOST_NAME, False) for k in CHROMIUM_KEYS] + [(prefix + FIREFOX_KEY + "\\" + HOST_NAME, True)]


def register(folder, command_path, hive, prefix="") -> list:
    """Write the manifests into `folder` and point every browser at them. Returns the keys written."""
    import winreg
    chrome_json, firefox_json = write_manifests(folder, command_path)
    written = []
    for key, firefox in key_paths(prefix):
        with winreg.CreateKeyEx(hive, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, firefox_json if firefox else chrome_json)
        written.append(key)
    return written


def registered_command(hive, key):
    """The program a registered host key leads to (via its manifest), or None."""
    import winreg
    try:
        with winreg.OpenKey(hive, key) as k:
            manifest = winreg.QueryValueEx(k, "")[0]
        with open(manifest, encoding="utf-8") as f:
            return json.load(f).get("path")
    except (OSError, ValueError):
        return None


def unregister(hive, prefix="", inside=None) -> list:
    """Remove our host keys; with `inside`, only the ones that lead to a program in that folder (or to
    a manifest that is gone). Returns the keys removed."""
    import winreg
    folder = os.path.normcase(os.path.abspath(inside)).rstrip("\\/") + os.sep if inside else None
    removed = []
    for key, _firefox in key_paths(prefix):
        try:
            winreg.OpenKey(hive, key).Close()
        except OSError:
            continue
        if folder:
            command = registered_command(hive, key)
            if command and not os.path.normcase(os.path.abspath(command)).startswith(folder):
                continue                                           # another copy of DISO owns it now
        try:
            winreg.DeleteKey(hive, key)
            removed.append(key)
        except OSError:
            pass
    return removed


def register_for_user(data_dir=None, hive=None, prefix="") -> list:
    """The app does this at every start: the current user's browsers can start this very copy of DISO."""
    if os.environ.get(NO_REGISTER_ENV) or os.environ.get(SETUP_TEST_ENV):
        return []                              # a copy that tests started (in a pretend computer) stays out of the real one
    from .utils import app_data_dir
    folder = os.path.join(data_dir or app_data_dir(), "native_host")
    command = app_command()
    if not sys.platform.startswith("win"):
        target = command[0] if len(command) == 1 else _source_script(folder, command)
        return register_files(target)
    import winreg
    if len(command) == 1:
        target = command[0]
    else:                                     # from source: the browser can only start a program, so a .bat
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, "diso_host.bat")
        python = sys.executable                # with a console exe: the host needs stdin / stdout
        with open(target, "w", encoding="utf-8", newline="\r\n") as f:     # chcp: the paths may be "C:\Users\Tuğra\..."
            f.write(f'@echo off\nchcp 65001 >nul\n"{python}" "{command[1]}" %*\n')
    return register(folder, target, winreg.HKEY_CURRENT_USER if hive is None else hive, prefix)


# ------------------------------------------------------------------------------- macOS / Linux
# no registry there: every browser reads <HOST_NAME>.json from a folder of its own (per user)
MAC_CHROMIUM = ("Google/Chrome", "Google/Chrome Beta", "Chromium", "Microsoft Edge", "BraveSoftware/Brave-Browser",
                "Vivaldi")
LINUX_CHROMIUM = ("google-chrome", "google-chrome-beta", "chromium", "microsoft-edge", "BraveSoftware/Brave-Browser",
                  "vivaldi")


def host_dirs(home=None, mac=None, environ=os.environ) -> list:
    """[(the browser's own folder, its NativeMessagingHosts folder, firefox?)] for every browser family."""
    home = home or os.path.expanduser("~")
    mac = sys.platform == "darwin" if mac is None else mac
    if mac:
        base = os.path.join(home, "Library", "Application Support")
        out = [(os.path.join(base, *b.split("/")), False) for b in MAC_CHROMIUM]
        out.append((os.path.join(base, "Mozilla"), True))
        return [(own, os.path.join(own, "NativeMessagingHosts"), ff) for own, ff in out]
    config = environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    out = [(os.path.join(config, *b.split("/")), os.path.join(config, *b.split("/"), "NativeMessagingHosts"), False)
           for b in LINUX_CHROMIUM]
    mozilla = os.path.join(home, ".mozilla")
    return out + [(mozilla, os.path.join(mozilla, "native-messaging-hosts"), True)]


def register_files(command_path, home=None, mac=None) -> list:
    """Write our host manifest for every browser that has been used here (its own folder exists; DISO does
    this at every start, so a browser installed later is found then). Returns the files written."""
    written = []
    for own, folder, firefox in host_dirs(home, mac):
        if not os.path.isdir(own):
            continue
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, HOST_NAME + ".json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(host_manifest(command_path, firefox), f, ensure_ascii=False, indent=2)
            written.append(path)
        except OSError:
            continue
    return written


def unregister_files(home=None, mac=None, inside=None) -> list:
    """Remove our host manifests; with `inside`, only the ones that lead to a program in that folder."""
    folder = os.path.join(os.path.abspath(inside), "") if inside else None       # with its separator at the end
    removed = []
    for _own, hosts, _firefox in host_dirs(home, mac):
        path = os.path.join(hosts, HOST_NAME + ".json")
        if not os.path.isfile(path):
            continue
        if folder:
            try:
                with open(path, encoding="utf-8") as f:
                    command = json.load(f).get("path") or ""
            except (OSError, ValueError):
                command = ""
            if command and not os.path.abspath(command).startswith(folder):
                continue
        try:
            os.remove(path)
            removed.append(path)
        except OSError:
            pass
    return removed


def _source_script(folder, command) -> str:
    """From source the browser can only start a program: a small shell script that runs main.py."""
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, "diso_host.sh")
    with open(target, "w", encoding="utf-8") as f:
        f.write(f'#!/bin/sh\nexec "{command[0]}" "{command[1]}" "$@"\n')
    os.chmod(target, 0o755)
    return target
