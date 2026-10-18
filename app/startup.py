"""'Start with Windows': a value in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run."""
import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "HizliIndirici"


def command(minimized: bool = True) -> str:
    """The command line Windows runs at log-in (started hidden in the tray)."""
    flag = " --minimized" if minimized else ""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"{flag}'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")  # no console window
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return f'"{exe}" "{main}"{flag}'


def _winreg():
    if not sys.platform.startswith("win"):
        return None
    import winreg
    return winreg


def is_enabled(name: str = APP_NAME) -> bool:
    reg = _winreg()
    if reg is None:
        return False
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
            reg.QueryValueEx(key, name)
        return True
    except OSError:
        return False


def set_enabled(on: bool, name: str = APP_NAME, minimized: bool = True) -> bool:
    """Turn it on or off. Returns True if the registry now matches `on`."""
    reg = _winreg()
    if reg is None:
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
