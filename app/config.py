"""
User settings, saved in %LOCALAPPDATA%\\DISO/settings.json so they survive a restart.

Two kinds live here: what the option bar of the main window shows (folder, quality,
connections ...) and the global switches of the settings window (parallel downloads,
speed limit, notifications ...).
"""
import json
import os
import threading

from .utils import app_data_dir

# value shown in the speed-limit menu -> KB/s (0 = no limit)
SPEED_LIMITS = {
    "Sınırsız": 0,
    "128 KB/s": 128,
    "256 KB/s": 256,
    "512 KB/s": 512,
    "1 MB/s": 1024,
    "2 MB/s": 2048,
    "5 MB/s": 5120,
    "10 MB/s": 10240,
    "25 MB/s": 25600,
}
AFTER_ALL = {  # menu text -> action. Not saved: it applies once, to the current session only.
    "Hiçbir şey yapma": "none",
    "Uygulamayı kapat": "close",
    "Bilgisayarı uyut": "sleep",
    "Bilgisayarı kapat": "shutdown",
}
THEMES = {"Koyu": "dark", "Açık": "light", "Sistem": "system"}
AUTO_RETRY = {"Kapalı": 0, "1 kez": 1, "3 kez": 3, "5 kez": 5, "10 kez": 10}
SORTS = ["Yeni üstte", "Eski üstte", "Ad (A→Z)", "Boyut (büyük üstte)", "Duruma göre"]
FILTERS = ["Hepsi", "Aktif", "Sırada", "Duraklatılmış", "Tamamlanan", "Hatalı"]
MAX_PARALLEL_CHOICES = [str(n) for n in range(1, 9)]

DEFAULTS = {
    # main window option bar
    "folder": "",
    "kind": "Otomatik (dosya / video)",
    "quality": "En iyi",
    "bitrate": "320",
    "connections": "16",
    "cookies": "Yok",
    "playlist": False,
    "clip_watch": False,
    "subs": "Yok",
    "cover": True,
    "sort_folders": False,
    # settings window
    "max_parallel": 3,
    "speed_limit": "Sınırsız",
    "notify_sound": True,
    "notify_toast": True,
    "block_duplicates": True,
    "auto_retry": 3,
    "proxy": "",
    "playlist_ask": True,
    "auto_music": True,
    "schedule_on": False,
    "schedule_start": "02:00",
    "schedule_stop": "07:00",
    "tray_on_close": False,
    "start_with_windows": False,
    "bridge_on": True,
    "bridge_port": 17653,
    "theme": "Koyu",
    "look": "Yeni",
    "language": "Türkçe",                # the interface language (app/i18n.py)
    "last_version": "",                 # the version that last ran: a new one is announced once
    "extension_seen": False,            # the browser extension has talked to DISO (so it is in a browser)
    "extension_ask": True,              # offer to add the browser extension (until it is added, or "don't ask again")
    "extension_ask_after": 0,           # "remind me later": not before this time (seconds since 1970)
    # list
    "sort": "Yeni üstte",
    "filter": "Hepsi",
}


class Config:
    def __init__(self, path=None):
        self.path = path or os.path.join(app_data_dir(), "settings.json")
        self.data = dict(DEFAULTS)
        self.saved = set()                  # the keys that came from the file (not defaults)
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            return
        if not isinstance(saved, dict):
            return
        for key, default in DEFAULTS.items():
            if key in saved and isinstance(saved[key], type(default)):
                self.data[key] = saved[key]
                self.saved.add(key)

    def sanitize(self, choices: dict):
        """Drop saved values that are not in the menus any more (e.g. renamed options)."""
        for key, allowed in choices.items():
            if self.data.get(key) not in allowed:
                self.data[key] = DEFAULTS[key]

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        with self._lock:
            if self.data.get(key) == value:
                return
            self.data[key] = value
            self._write()

    def _write(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass
