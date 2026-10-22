"""Small helpers that run beside the downloads, each switched on in the settings:

- 🚀 speed_test(): how fast the internet is (a few seconds of downloading from Cloudflare) and how many
  connections suit it;
- 🛡 Scanner: every finished download is scanned with Windows Defender (MpCmdRun); a threat is reported
  (Defender itself quarantines it);
- 📂 FolderWatcher: a .torrent file or a text file with links put into a chosen folder is downloaded; the
  file then moves into the "Eklendi" folder inside it, so it is not taken twice;
- 🔌 UsbCopier: finished songs (or every download) are copied onto a USB stick that is plugged in; when
  none is, they wait until one comes.

Nothing here touches the window: results come through queues the window polls."""
import ctypes
import glob
import os
import queue
import shutil
import subprocess
import threading
import time

from .logs import log
from .utils import subprocess_flags

# ------------------------------------------------------------------------------ 🚀 speed test
SPEED_URL = "https://speed.cloudflare.com/__down?bytes=50000000"
PING_URL = "https://speed.cloudflare.com/__down?bytes=0"
TEST_SECONDS = 6
TEST_STREAMS = 4


def suggested_connections(mbps) -> str:
    """The "Bağlantı sayısı" that suits this speed (more connections help a fast line more)."""
    if mbps >= 200:
        return "32"
    if mbps >= 40:
        return "16"
    return "8"


def speed_test(seconds=TEST_SECONDS, streams=TEST_STREAMS, get=None, clock=time.monotonic) -> dict:
    """{"mbps", "ping_ms", "connections"}: several downloads at once for a few seconds."""
    import requests
    get = get or requests.get
    t0 = clock()
    try:
        get(PING_URL, timeout=10).close()
        ping = (clock() - t0) * 1000
    except Exception:  # noqa: BLE001
        ping = 0.0
    got = [0] * streams
    stop = clock() + seconds
    start = clock()

    def pull(i):
        try:
            with get(SPEED_URL, stream=True, timeout=10) as r:
                for chunk in r.iter_content(65536):
                    got[i] += len(chunk)
                    if clock() >= stop:
                        break
        except Exception as e:  # noqa: BLE001
            log.info("speed test stream: %s", e)

    threads = [threading.Thread(target=pull, args=(i,), daemon=True) for i in range(streams)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(seconds + 15)
    took = max(0.001, min(clock(), stop) - start)
    mbps = sum(got) * 8 / took / 1_000_000
    if not sum(got):
        raise OSError("no connection")
    return {"mbps": round(mbps, 1), "ping_ms": round(ping), "connections": suggested_connections(mbps)}


# ------------------------------------------------------------------------------ 🛡 Windows Defender
def defender_tool():
    """MpCmdRun.exe, the newest platform version first (None when Defender is not there)."""
    data = os.environ.get("ProgramData", r"C:\ProgramData")
    found = sorted(glob.glob(os.path.join(data, "Microsoft", "Windows Defender", "Platform", "*", "MpCmdRun.exe")),
                   reverse=True)
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    found.append(os.path.join(pf, "Windows Defender", "MpCmdRun.exe"))
    return next((p for p in found if os.path.isfile(p)), None)


def scan_file(path, tool=None, run=subprocess.run) -> str:
    """"clean", "threat" or "unknown" (Defender could not say)."""
    tool = tool or defender_tool()
    if not tool or not os.path.exists(path):
        return "unknown"
    try:
        r = run([tool, "-Scan", "-ScanType", "3", "-File", path], capture_output=True, timeout=600,
                **subprocess_flags())
    except (OSError, subprocess.SubprocessError) as e:
        log.info("defender: %s", e)
        return "unknown"
    return {0: "clean", 2: "threat"}.get(r.returncode, "unknown")


class Scanner:
    """scan(item) on one worker thread; drain() gives (item, verdict)."""

    def __init__(self, scan=scan_file):
        self._scan = scan
        self._jobs, self._done = queue.Queue(), queue.Queue()
        self._thread = None

    def scan(self, item):
        if not item.final_path:
            return
        self._jobs.put(item)
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._work, daemon=True, name="defender")
            self._thread.start()

    def _work(self):
        while True:
            try:
                item = self._jobs.get(timeout=5)
            except queue.Empty:
                return
            self._done.put((item, self._scan(item.final_path)))

    def drain(self):
        out = []
        while True:
            try:
                out.append(self._done.get_nowait())
            except queue.Empty:
                return out


# ------------------------------------------------------------------------------ 📂 a watched folder
WATCHED = (".torrent", ".txt", ".url", ".list")
DONE_FOLDER = "Eklendi"


class FolderWatcher:
    """Looks into `folder` every few seconds; files that came (and stopped growing) are handed to
    on_files(paths) on the window's thread (through drain) and moved into its "Eklendi" folder."""

    def __init__(self, every=3.0):
        self.folder = ""
        self.every = every
        self._sizes = {}
        self._found = queue.Queue()
        self._stop = threading.Event()
        self._thread = None

    def watch(self, folder):
        self.folder = folder or ""
        self._sizes = {}
        if self.folder and (self._thread is None or not self._thread.is_alive()):
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="watch-folder")
            self._thread.start()
        elif not self.folder:
            self._stop.set()

    def look(self):
        """One look (the thread calls it; tests too): files that are ready are moved and queued."""
        folder = self.folder
        if not folder or not os.path.isdir(folder):
            return []
        ready = []
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if not name.lower().endswith(WATCHED) or not os.path.isfile(path):
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if self._sizes.get(path) != size:               # new, or still being written: next time
                self._sizes[path] = size
                continue
            target_dir = os.path.join(folder, DONE_FOLDER)
            os.makedirs(target_dir, exist_ok=True)
            target = os.path.join(target_dir, name)
            stem, ext = os.path.splitext(name)
            n = 2
            while os.path.exists(target):
                target = os.path.join(target_dir, f"{stem} ({n}){ext}")
                n += 1
            try:
                shutil.move(path, target)
            except OSError:
                continue
            self._sizes.pop(path, None)
            ready.append(target)
        if ready:
            self._found.put(ready)
        return ready

    def _loop(self):
        while not self._stop.wait(self.every):
            try:
                self.look()
            except Exception:  # noqa: BLE001 - the next look tries again
                log.exception("watched folder")

    def drain(self):
        out = []
        while True:
            try:
                out += self._found.get_nowait()
            except queue.Empty:
                return out

    def stop(self):
        self._stop.set()


# ------------------------------------------------------------------------------ 🔌 USB sticks
DRIVE_REMOVABLE = 2
USB_FOLDER = "DISO"


def removable_drives():
    """['E:\\', …]: the removable drives (USB sticks, card readers) that hold a disk now."""
    k32 = ctypes.windll.kernel32
    mask = k32.GetLogicalDrives()
    out = []
    for i in range(26):
        if mask & (1 << i):
            root = f"{chr(65 + i)}:\\"
            if k32.GetDriveTypeW(root) == DRIVE_REMOVABLE and os.path.isdir(root):
                out.append(root)
    return out


class UsbCopier:
    """copy(path) puts a finished file on the USB stick (into DISO\\ there); with no stick in, it waits
    and goes when one is plugged in. drain() gives (path, drive or "", error) on the window's thread."""

    def __init__(self, drives=removable_drives, every=3.0):
        self._drives = drives
        self.every = every
        self.pending = []
        self._lock = threading.Lock()
        self._done = queue.Queue()
        self._thread = None
        self.folder = USB_FOLDER

    def copy(self, path):
        with self._lock:
            if path not in self.pending:
                self.pending.append(path)
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, daemon=True, name="usb-copy")
            self._thread.start()

    def step(self) -> bool:
        """Copy what waits, if a stick is in (True when there was one)."""
        try:
            drives = self._drives()
        except OSError:
            drives = []
        if not drives:
            return False
        drive = drives[0]
        while True:
            with self._lock:
                if not self.pending:
                    return True
                path = self.pending[0]
            try:
                target_dir = os.path.join(drive, self.folder)
                os.makedirs(target_dir, exist_ok=True)
                target = os.path.join(target_dir, os.path.basename(path))
                if not (os.path.exists(target) and os.path.getsize(target) == os.path.getsize(path)):
                    shutil.copy2(path, target + ".part")
                    os.replace(target + ".part", target)
                self._done.put((path, drive, None))
            except OSError as e:
                if not os.path.exists(path):
                    self._done.put((path, drive, e))         # the file itself is gone: forget it
                elif not os.path.isdir(drive):
                    return False                             # the stick was pulled out: wait for it
                else:
                    self._done.put((path, drive, e))         # full, read-only …: told once
            with self._lock:
                if self.pending and self.pending[0] == path:
                    self.pending.pop(0)

    def _loop(self):
        while True:
            self.step()
            with self._lock:
                if not self.pending:
                    return
            time.sleep(self.every)

    def drain(self):
        out = []
        while True:
            try:
                out.append(self._done.get_nowait())
            except queue.Empty:
                return out
