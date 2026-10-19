"""
System tray icon (needs the optional 'pystray' package; everything works without it).

The icon runs in its own thread. Its menu never touches the window directly: it only calls
on_event(name) with "show", "pause_all", "resume_all" or "quit", and the window handles
those on its own thread.
"""
import os
import sys
import threading

from .i18n import tr
from .utils import resource_path

try:
    import pystray
    from PIL import Image
except Exception:  # not installed / no tray on this system
    pystray = None
    Image = None

# macOS: pystray wants the main thread, which belongs to the window (DISO goes into the Dock there instead)
AVAILABLE = pystray is not None and sys.platform != "darwin"


def load_image(path=None):
    """The tray picture: assets/icon.png, or a plain blue square if the file is missing."""
    path = path or resource_path(os.path.join("assets", "icon.png"))
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return Image.new("RGBA", (64, 64), (40, 110, 220, 255))


class TrayIcon:
    def __init__(self, title: str, on_event, image=None):
        if not AVAILABLE:
            raise RuntimeError("pystray is not installed")
        self._on_event = on_event
        menu = pystray.Menu(
            pystray.MenuItem(tr("Göster"), lambda: self._fire("show"), default=True),
            pystray.MenuItem(tr("Hepsini duraklat"), lambda: self._fire("pause_all")),
            pystray.MenuItem(tr("Hepsini başlat"), lambda: self._fire("resume_all")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("Çıkış"), lambda: self._fire("quit")),
        )
        self._icon = pystray.Icon("DISO", image or load_image(), title[:127], menu)
        self.running = False

    def _fire(self, name):
        try:
            self._on_event(name)
        except Exception:
            pass

    def start(self):
        """Show the icon. It runs in a daemon thread (pystray's own run_detached thread is not a
        daemon and keeps the process alive after the window is gone). Waits until it is visible:
        stopping an icon that is still starting can hang."""
        ready = threading.Event()

        def setup(icon):
            icon.visible = True
            ready.set()

        self._thread = threading.Thread(target=self._icon.run, args=(setup,), daemon=True)
        self._thread.start()
        ready.wait(3)
        self.running = True

    def set_title(self, text: str):
        """Tooltip. Windows cuts it at 127 characters."""
        try:
            self._icon.title = text[:127]
        except Exception:
            pass

    def stop(self):
        self.running = False
        try:
            self._icon.stop()
        except Exception:
            pass
        thread = getattr(self, "_thread", None)
        if thread is not None:
            thread.join(2)
