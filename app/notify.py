"""Finished-download notifications (sound, Windows toast) and the power actions."""
import base64
import os
import subprocess
import sys
import threading

from .utils import subprocess_flags

_WIN = sys.platform.startswith("win")

# PowerShell shows the toast through the Windows API: no extra library is needed.
# Title and text come in through environment variables, so nothing needs quoting.
_TOAST_PS = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$title = [System.Security.SecurityElement]::Escape($env:HI_TITLE)
$body = [System.Security.SecurityElement]::Escape($env:HI_BODY)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$title</text><text>$body</text></binding></visual></toast>")
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($toast)
"""


def play_sound(kind: str = "done") -> None:
    """kind: 'done' (soft ping) or 'error' (warning sound)."""
    try:
        if _WIN:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK if kind == "done" else winsound.MB_ICONHAND)
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()
    except Exception:
        pass


def show_toast(title: str, body: str, timeout: int = 20) -> int:
    """Windows notification. Blocks until PowerShell is done; returns its exit code (-1: n/a)."""
    if not _WIN:
        return -1
    script = base64.b64encode(_TOAST_PS.encode("utf-16-le")).decode("ascii")
    env = dict(os.environ, HI_TITLE=str(title)[:100], HI_BODY=str(body)[:240])
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", script],
                           env=env, timeout=timeout, capture_output=True, **subprocess_flags())
        return r.returncode
    except Exception:
        return -1


def toast(title: str, body: str) -> None:
    """Same, in the background (the window must not wait for PowerShell)."""
    threading.Thread(target=show_toast, args=(title, body), daemon=True).start()


def power_action(kind: str) -> bool:
    """'sleep' or 'shutdown'. ('close' is done by the window itself.) Returns True if started."""
    try:
        if kind == "shutdown":
            if _WIN:
                subprocess.Popen(["shutdown", "/s", "/t", "5"], **subprocess_flags())
            else:
                subprocess.Popen(["shutdown", "-h", "now"])
        elif kind == "sleep":
            if _WIN:
                subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], **subprocess_flags())
            else:
                subprocess.Popen(["systemctl", "suspend"])
        else:
            return False
        return True
    except Exception:
        return False
