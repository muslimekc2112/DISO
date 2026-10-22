"""The media keys of the keyboard (play / pause, next, previous, stop) for the music player, also
when DISO is not the window in front.

The keys are taken with RegisterHotKey on a small thread of their own. While they are taken no other
program gets them, so the music window only takes them while music is playing or paused and gives
them back when it stops. A key another program already holds is simply not taken (no error)."""
import ctypes
import queue
import sys
import threading

try:
    from ctypes import wintypes
except (ImportError, ValueError):  # not Windows
    wintypes = None

from .logs import log

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NOREPEAT = 0x4000
KEYS = {1: (0xB3, "toggle"), 2: (0xB0, "next"), 3: (0xB1, "previous"), 4: (0xB2, "stop")}


EXTRA_FIRST_ID = 100


class MediaKeys:
    def __init__(self):
        self.pressed = queue.Queue()          # "toggle" / "next" / "previous" / "stop", read on the UI thread
        self.taken = set()                    # the names of the keys this program holds
        self.extra = {}                       # ⌨ the user's keys that work everywhere: name -> (modifiers, vk)
        self._thread = None
        self._thread_id = 0
        self._ready = threading.Event()

    @property
    def active(self) -> bool:
        return self._thread is not None

    def start(self) -> set:
        """Take the keys; returns the names of the ones taken (empty when none could be)."""
        if self._thread is not None:
            return self.taken
        if not sys.platform.startswith("win"):     # Windows only (macOS / Linux: the window's own keys)
            return set()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="media-keys", daemon=True)
        self._thread.start()
        self._ready.wait(3)
        return self.taken

    def set_extra(self, keys):
        """The user's own keys that work everywhere ({action: (modifiers, virtual key)}); taken at once if
        the keys are being held now."""
        keys = {name: combo for name, combo in (keys or {}).items() if combo}
        if keys == self.extra:
            return
        self.extra = keys
        if self.active:
            self.stop()
            self.start()

    def stop(self):
        """Give the keys back."""
        thread, self._thread = self._thread, None
        if thread is None:
            return
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        thread.join(3)
        self.taken = set()

    def _run(self):
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
            self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            msg = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)     # make this thread's message queue
            ids = {}
            for hotkey_id, (vk, name) in KEYS.items():
                if user32.RegisterHotKey(None, hotkey_id, MOD_NOREPEAT, vk):
                    ids[hotkey_id] = name
            for n, (name, (mods, vk)) in enumerate(sorted(self.extra.items())):
                if user32.RegisterHotKey(None, EXTRA_FIRST_ID + n, mods | MOD_NOREPEAT, vk):
                    ids[EXTRA_FIRST_ID + n] = name
            self.taken = set(ids.values())
        except Exception:  # noqa: BLE001 - no media keys then; the player works without them
            log.exception("media keys unavailable")
            self._ready.set()
            return
        self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam in ids:
                    self.pressed.put(ids[msg.wParam])
        finally:
            for hotkey_id in ids:
                user32.UnregisterHotKey(None, hotkey_id)
            self._thread_id = 0

    def post(self, name):
        """Act as if the key were pressed: sends the real WM_HOTKEY message to the key thread (tests)."""
        for hotkey_id, (_, n) in KEYS.items():
            if n == name and self._thread_id:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_HOTKEY, hotkey_id, 0)
