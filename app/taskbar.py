"""⏮ ⏯ ⏭ in the little preview that opens over the music window's taskbar button.

Windows' ITaskbarList3 "thumbnail toolbar", used through ctypes. A click comes to the window as a
WM_COMMAND message, so the window's message function is wrapped (and given back on detach). The
buttons vanish when the window is hidden; Windows then sends "TaskbarButtonCreated" when it is shown
again, and they are put back. Anything that goes wrong here just means: no buttons."""
import ctypes
import os
import queue
from ctypes import wintypes

from .i18n import tr
from .logs import log

WM_COMMAND = 0x0111
THBN_CLICKED = 0x1800
GWLP_WNDPROC = -4
THB_ICON, THB_TOOLTIP, THB_FLAGS = 0x2, 0x4, 0x8
CLSID_TASKBARLIST = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
IID_ITASKBARLIST3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"
BUTTONS = {1: "previous", 2: "toggle", 3: "next"}
TIPS = {"previous": "Önceki", "play": "Çal", "pause": "Duraklat", "next": "Sonraki"}

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


class THUMBBUTTON(ctypes.Structure):
    _fields_ = [("dwMask", wintypes.DWORD), ("iId", wintypes.UINT), ("iBitmap", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 260), ("dwFlags", wintypes.DWORD)]


def _guid(text):
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(text, ctypes.byref(g))
    return g


def _method(ptr, index, *argtypes):
    """A method of a COM object, by its place in the object's table."""
    table = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])
    return lambda *args: fn(ptr, *args)


def draw_icons(folder) -> dict:
    """White ⏮ ▶ ⏸ ⏭ as .ico files (drawn here: nothing to ship). {name: path}."""
    from PIL import Image, ImageDraw
    os.makedirs(folder, exist_ok=True)
    shapes = {
        "previous": [("rect", (8, 8, 12, 56)), ("poly", [(56, 8), (56, 56), (14, 32)])],
        "play": [("poly", [(14, 6), (14, 58), (58, 32)])],
        "pause": [("rect", (12, 8, 26, 56)), ("rect", (38, 8, 52, 56))],
        "next": [("rect", (52, 8, 56, 56)), ("poly", [(8, 8), (8, 56), (50, 32)])],
    }
    out = {}
    for name, parts in shapes.items():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for kind, xy in parts:
            (d.rectangle if kind == "rect" else d.polygon)(xy, fill=(255, 255, 255, 255))
        path = os.path.join(folder, f"thumb-{name}.ico")
        img.save(path, sizes=[(16, 16), (24, 24), (32, 32)])
        out[name] = path
    return out


class ThumbBar:
    """attach(hwnd, icon_folder) / set_playing(bool) / pressed queue / detach()."""

    def __init__(self):
        self.pressed = queue.Queue()
        self.hwnd = None
        self.added = False
        self.playing = False
        self._list = None
        self._icons = {}
        self._old_proc = None
        self._proc = None
        self._created_msg = 0

    @property
    def active(self) -> bool:
        return self.hwnd is not None

    def attach(self, hwnd, icon_folder) -> bool:
        if self.hwnd is not None or os.name != "nt":
            return self.hwnd is not None
        try:
            user32 = ctypes.windll.user32
            ole32 = ctypes.windll.ole32
            ole32.CoInitializeEx(None, 0x2)                        # apartment; "already" is fine too
            ptr = ctypes.c_void_p()
            hr = ole32.CoCreateInstance(ctypes.byref(_guid(CLSID_TASKBARLIST)), None, 1,
                                        ctypes.byref(_guid(IID_ITASKBARLIST3)), ctypes.byref(ptr))
            if hr != 0 or not ptr.value:
                return False
            if _method(ptr, 3)() != 0:                             # HrInit
                return False
            self._list = ptr
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
                                          ctypes.c_int, wintypes.UINT]
            size = user32.GetSystemMetrics(49) or 16                # SM_CXSMICON
            for name, path in draw_icons(icon_folder).items():
                self._icons[name] = user32.LoadImageW(None, path, 1, size, size, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
            self._created_msg = user32.RegisterWindowMessageW("TaskbarButtonCreated")
            for msg in (self._created_msg, WM_COMMAND):            # also when DISO runs as administrator
                try:
                    user32.ChangeWindowMessageFilterEx(wintypes.HWND(hwnd), msg, 1, None)
                except Exception:  # noqa: BLE001
                    pass
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            user32.CallWindowProcW.restype = LRESULT
            user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                               wintypes.LPARAM]
            self._proc = WNDPROC(self._wndproc)
            self._old_proc = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(self._proc, ctypes.c_void_p))
            if not self._old_proc:
                self._proc = None
                return False
            self.hwnd = hwnd
            self._add()
            return True
        except Exception:  # noqa: BLE001
            log.exception("taskbar buttons unavailable")
            return False

    def _buttons(self):
        arr = (THUMBBUTTON * 3)()
        for i, (bid, name) in enumerate(BUTTONS.items()):
            icon = "pause" if name == "toggle" and self.playing else ("play" if name == "toggle" else name)
            arr[i].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
            arr[i].iId = bid
            arr[i].hIcon = self._icons.get(icon) or 0
            arr[i].szTip = tr(TIPS[icon])
            arr[i].dwFlags = 0
        return arr

    def _add(self):
        if self.hwnd is None or self._list is None:
            return False
        arr = self._buttons()
        hr = _method(self._list, 15, wintypes.HWND, wintypes.UINT, ctypes.c_void_p)(self.hwnd, 3, ctypes.byref(arr))
        self.added = hr == 0
        return self.added

    def set_playing(self, playing: bool):
        if playing == self.playing:
            return
        self.playing = playing
        if self.added:
            arr = self._buttons()
            _method(self._list, 16, wintypes.HWND, wintypes.UINT, ctypes.c_void_p)(self.hwnd, 3, ctypes.byref(arr))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_COMMAND and (wparam >> 16) & 0xFFFF == THBN_CLICKED:
                name = BUTTONS.get(wparam & 0xFFFF)
                if name:
                    self.pressed.put(name)
                    return 0
            elif msg == self._created_msg and self._created_msg:
                self.added = False
                self._add()                                       # the taskbar button came (back): buttons too
        except Exception:  # noqa: BLE001 - never let an error out of a window function
            pass
        return ctypes.windll.user32.CallWindowProcW(self._old_proc, hwnd, msg, wparam, lparam)

    def detach(self):
        """Give the window its own message function back (before the window goes)."""
        if self.hwnd is not None and self._old_proc:
            try:
                ctypes.windll.user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, self._old_proc)
            except Exception:  # noqa: BLE001
                pass
        for icon in self._icons.values():
            if icon:
                ctypes.windll.user32.DestroyIcon(wintypes.HANDLE(icon))
        self._icons = {}
        if self._list is not None:
            try:
                _method(self._list, 2)()                          # Release
            except Exception:  # noqa: BLE001
                pass
        self._list = None
        self.hwnd = None
        self.added = False
