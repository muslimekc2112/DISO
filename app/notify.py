"""Finished-download notifications (sound, Windows toast) and the power actions."""
import base64
import os
import shutil
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
$actions = ''
if ($env:HI_OPEN_LINK) {
  $a1 = [System.Security.SecurityElement]::Escape($env:HI_OPEN_LINK)
  $a2 = [System.Security.SecurityElement]::Escape($env:HI_FOLDER_LINK)
  $l1 = [System.Security.SecurityElement]::Escape($env:HI_OPEN)
  $l2 = [System.Security.SecurityElement]::Escape($env:HI_FOLDER)
  $actions = "<actions><action content='$l1' activationType='protocol' arguments='$a1'/><action content='$l2' activationType='protocol' arguments='$a2'/></actions>"
}
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$title</text><text>$body</text></binding></visual>$actions</toast>")
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


def toast_command(title: str, body: str, system=None):
    """macOS / Linux: the command that shows the notification (None: there is none)."""
    system = system or sys.platform
    if system == "darwin":
        def q(text):
            return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'
        return ["osascript", "-e", f"display notification {q(str(body)[:240])} with title {q(str(title)[:100])}"]
    if shutil.which("notify-send"):
        return ["notify-send", "--app-name=DISO", str(title)[:100], str(body)[:240]]
    return None


def toast_buttons(path) -> dict:
    """The environment that puts "Open" / "Show in folder" on the toast (empty: no buttons; DISO must be
    the installed DISO.exe, which answers the diso: links)."""
    from . import associations
    from .i18n import tr
    if not path or not associations.program_path():
        return {}
    return {"HI_OPEN": tr("Aç"), "HI_FOLDER": tr("Klasörde göster"),
            "HI_OPEN_LINK": associations.protocol_link("open", path),
            "HI_FOLDER_LINK": associations.protocol_link("folder", path)}


def show_toast(title: str, body: str, timeout: int = 20, path=None) -> int:
    """Windows notification (macOS: Notification Center, Linux: notify-send). Blocks until it is shown;
    returns the exit code (-1: n/a). path: a finished file, for the "Open" / "Show in folder" buttons."""
    if not _WIN:
        cmd = toast_command(title, body)
        if not cmd:
            return -1
        try:
            return subprocess.run(cmd, timeout=timeout, capture_output=True, stdin=subprocess.DEVNULL).returncode
        except Exception:
            return -1
    script = base64.b64encode(_TOAST_PS.encode("utf-16-le")).decode("ascii")
    env = dict(os.environ, HI_TITLE=str(title)[:100], HI_BODY=str(body)[:240])
    env.pop("HI_OPEN_LINK", None)
    env.update(toast_buttons(path))
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", script],
                           env=env, timeout=timeout, capture_output=True, **subprocess_flags())
        return r.returncode
    except Exception:
        return -1


def toast(title: str, body: str, path=None) -> None:
    """Same, in the background (the window must not wait for PowerShell)."""
    threading.Thread(target=show_toast, args=(title, body), kwargs={"path": path}, daemon=True).start()


def power_action(kind: str) -> bool:
    """'sleep' or 'shutdown'. ('close' is done by the window itself.) Returns True if started."""
    try:
        if kind == "shutdown":
            if _WIN:
                subprocess.Popen(["shutdown", "/s", "/t", "5"], **subprocess_flags())
            elif sys.platform == "darwin":
                subprocess.Popen(["osascript", "-e", 'tell application "System Events" to shut down'])
            else:
                subprocess.Popen(["systemctl", "poweroff"])
        elif kind == "sleep":
            if _WIN:
                subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], **subprocess_flags())
            elif sys.platform == "darwin":
                subprocess.Popen(["pmset", "sleepnow"])
            else:
                subprocess.Popen(["systemctl", "suspend"])
        else:
            return False
        return True
    except Exception:
        return False
