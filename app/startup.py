"""'Start with Windows': a value in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.

macOS: a LaunchAgent (~/Library/LaunchAgents/com.iso.diso.plist). Linux: an autostart entry
(~/.config/autostart/DISO.desktop)."""
import os
import plistlib
import shlex
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "DISO"
MAC_LABEL = "com.iso.diso"


def arguments(minimized: bool = True) -> list:
    """The program and its arguments that run at log-in (started hidden in the tray)."""
    flag = ["--minimized"] if minimized else []
    if getattr(sys, "frozen", False):
        return [sys.executable, *flag]
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")  # no console window
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return [exe, main, *flag]


def command(minimized: bool = True) -> str:
    """The command line Windows runs at log-in (started hidden in the tray)."""
    return " ".join(f'"{a}"' for a in arguments(False)) + (" --minimized" if minimized else "")


def _winreg():
    if not sys.platform.startswith("win"):
        return None
    import winreg
    return winreg


def entry_path(home=None, mac=None, environ=os.environ) -> str:
    """macOS / Linux: the file that makes the system start DISO at log-in."""
    home = home or os.path.expanduser("~")
    if sys.platform == "darwin" if mac is None else mac:
        return os.path.join(home, "Library", "LaunchAgents", MAC_LABEL + ".plist")
    config = environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    return os.path.join(config, "autostart", APP_NAME + ".desktop")


def entry_text(minimized=True, mac=None) -> bytes:
    args = arguments(minimized)
    if sys.platform == "darwin" if mac is None else mac:
        return plistlib.dumps({"Label": MAC_LABEL, "ProgramArguments": args, "RunAtLoad": True,
                               "ProcessType": "Interactive"})
    return ("[Desktop Entry]\nType=Application\nName=DISO\n"
            f"Exec={' '.join(shlex.quote(a) for a in args)}\n"
            "X-GNOME-Autostart-enabled=true\nNoDisplay=false\nTerminal=false\n").encode("utf-8")


def is_enabled(name: str = APP_NAME) -> bool:
    reg = _winreg()
    if reg is None:
        return os.path.isfile(entry_path())
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
            reg.QueryValueEx(key, name)
        return True
    except OSError:
        return False


def set_enabled(on: bool, name: str = APP_NAME, minimized: bool = True) -> bool:
    """Turn it on or off. Returns True if the system now matches `on`."""
    reg = _winreg()
    if reg is None:
        path = entry_path()
        try:
            if on:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(entry_text(minimized))
            elif os.path.exists(path):
                os.remove(path)
            return True
        except OSError:
            return False
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
            if on:
                reg.SetValueEx(key, name, 0, reg.REG_SZ, command(minimized))
            else:
                try:
                    reg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
