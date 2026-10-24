"""
System tray icon (needs the optional 'pystray' package; everything works without it).

The icon runs in its own thread. Its menu never touches the window directly: it only calls
on_event(name) - or on_event(name, value) - and the window handles those on its own thread.

The menu is made again from `state` each time it opens (a right click), so it always shows what plays,
the volume, the downloads ... in the language DISO speaks right now. The window keeps `state` up to date
with set_state(); the keys are in EMPTY_STATE.
"""
import os
import sys
import threading

from .utils import resource_path

try:
    import pystray
    from PIL import Image
except Exception:  # not installed / no tray on this system
    pystray = None
    Image = None

# macOS: pystray wants the main thread, which belongs to the window (DISO goes into the Dock there instead)
AVAILABLE = pystray is not None and sys.platform != "darwin"

REPEATS = ("Kapalı", "Liste", "Tek")                        # player.REPEAT_MODES
VOLUMES = (100, 75, 50, 25)
SLEEPS = ("15 dk", "30 dk", "45 dk", "60 dk", "90 dk")      # music_ui.SLEEP_CHOICES without "off" / "track"
SLEEP_TRACK = "Parça bitince"
MAX_LISTS = 20                                              # a menu taller than the screen helps nobody

# what the menu shows before the window has told anything
EMPTY_STATE = {
    "lang": "tr",
    "track": "", "artist": "", "player": "stopped",         # "playing" / "paused" / "preparing" / "stopped"
    "time": "",                                             # "1:23 / 3:45"
    "next": "",                                             # the song that comes next, when it is known
    "shuffle": False, "repeat": "Kapalı", "volume": 80, "muted": False,
    "sleep": "",                                            # "" / "track" / "12 dk" (time left)
    "lists": [], "playing_list": "", "mini": False, "can_resume": False,
    "active": 0, "queued": 0, "paused": 0, "speed": "",     # downloads; speed like "3.4 MB"
    "mode": "download",                                     # the window shown now: "download" / "music"
}

# The menu speaks the language DISO speaks *now* (switching it in the window changes the menu at once,
# even before DISO starts again), so it has its own small dictionary.
EN = {
    "Göster": "Show", "Çıkış": "Quit",
    "Hepsini duraklat": "Pause all", "Hepsini başlat": "Start all",
    "Şu an müzik çalmıyor": "No music is playing",
    "Kaldığın yerden çal": "Play from where you left off", "Müzik çal": "Play music",
    "Çal": "Play", "Duraklat": "Pause", "Sonraki şarkı": "Next song", "Önceki şarkı": "Previous song",
    "Durdur": "Stop", "Hazırlanıyor…": "Getting ready…",
    "Karışık çal": "Shuffle", "Tekrar": "Repeat", "Kapalı": "Off", "Liste": "Whole list", "Tek": "This song",
    "Ses": "Volume", "Sesi aç": "Louder", "Sesi kıs": "Quieter", "Sessiz": "Mute", "Sesi geri aç": "Unmute",
    "Uyku zamanlayıcısı": "Sleep timer", "Parça bitince": "When this song ends", "kaldı": "left",
    "dk": "min", "Çalma listesi": "Playlist", "Sıradaki": "Up next",
    "Mini oynatıcı": "Mini player", "Mini oynatıcıyı kapat": "Close the mini player",
    "Şarkı sözleri": "Lyrics", "Ekolayzır": "Equalizer", "Müzik": "Music",
    "İndirmeler": "Downloads", "Şu an indirme yok": "Nothing is downloading",
    "indiriliyor": "downloading", "sırada": "queued", "duraklatıldı": "paused",
    "Panodaki linki indir": "Download the link in the clipboard",
    "Panoda indirilecek bir link yok": "There is no link to download in the clipboard",
    "İndirme klasörünü aç": "Open the download folder",
    "İndirme penceresi": "Download window", "Müzik çalar": "Music player", "Ayarlar": "Settings",
}


def load_image(path=None):
    """The tray picture: assets/icon.png, or a plain blue square if the file is missing."""
    path = path or resource_path(os.path.join("assets", "icon.png"))
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return Image.new("RGBA", (64, 64), (40, 110, 220, 255))


def _short(text, limit=48):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


if AVAILABLE:
    class _Icon(pystray.Icon):
        """pystray's icon, but the menu is made again right before it opens (Windows): what it shows is
        never older than the click. Elsewhere set_state() refreshes it."""

        def _on_notify(self, wparam, lparam):
            try:
                from pystray._util import win32
                if lparam == win32.WM_RBUTTONUP:
                    self._update_menu()
            except Exception:  # noqa: BLE001 - an old menu is better than none
                pass
            return super()._on_notify(wparam, lparam)

    REFRESHES_ITSELF = hasattr(pystray.Icon, "_on_notify")
else:
    _Icon = None
    REFRESHES_ITSELF = False


class TrayIcon:
    def __init__(self, title: str, on_event, image=None, language="tr"):
        if not AVAILABLE:
            raise RuntimeError("pystray is not installed")
        self._on_event = on_event
        self.state = dict(EMPTY_STATE, lang=language)
        self._icon = _Icon("DISO", image or load_image(), title[:127], pystray.Menu(self._items))
        self.running = False

    # ------------------------------------------------------------------ what the window tells
    def t(self, text):
        return EN.get(text, text) if self.state.get("lang") == "en" else text

    def set_state(self, **values):
        """Called by the window (its own thread) with what changed. Language changes show at once."""
        new = dict(self.state)
        new.update(values)
        if new == self.state:
            return
        self.state = new                                  # one assignment: the icon's thread sees old or new
        if not REFRESHES_ITSELF and self.running:
            try:
                self._icon.update_menu()
            except Exception:  # noqa: BLE001
                pass

    def set_language(self, code):
        self.set_state(lang="en" if code in ("en", "English") else "tr")

    # ------------------------------------------------------------------ the menu
    def _fire(self, name, value=None):
        try:
            if value is None:
                self._on_event(name)
            else:
                self._on_event(name, value)
        except Exception:
            pass

    def _act(self, name, value=None):
        def action():                                     # no arguments: pystray calls it as it is
            self._fire(name, value)
        return action

    def _item(self, text, name, value=None, checked=None, radio=False, enabled=True, default=False):
        kw = {}
        if checked is not None:
            kw["checked"] = (lambda item: True) if checked else (lambda item: False)
            kw["radio"] = radio
        return pystray.MenuItem(text, self._act(name, value), enabled=enabled, default=default, **kw)

    def _note(self, text):
        return pystray.MenuItem(text, None, enabled=False)

    def _items(self):
        """Every entry of the menu, made from `state` (pystray calls this each time it builds the menu)."""
        s, t = self.state, self.t
        yield self._item(t("Göster"), "show", default=True)
        yield pystray.Menu.SEPARATOR
        yield from self._music_items(s, t)
        yield pystray.Menu.SEPARATOR
        yield from self._download_items(s, t)
        yield pystray.Menu.SEPARATOR
        yield self._item("⬇ " + t("İndirme penceresi"), "show_download", checked=s["mode"] == "download", radio=True)
        yield self._item("🎵 " + t("Müzik çalar"), "show_music", checked=s["mode"] == "music", radio=True)
        yield self._item("⚙ " + t("Ayarlar"), "settings")
        yield pystray.Menu.SEPARATOR
        yield self._item(t("Çıkış"), "quit")

    def _music_items(self, s, t):
        playing, stopped = s["player"] == "playing", s["player"] == "stopped"
        if stopped:
            yield self._note("♪ " + t("Şu an müzik çalmıyor"))
        else:
            head = s["track"] if not s["artist"] else f"{s['artist']} — {s['track']}"
            yield self._note(("♪ " if playing else "⏸ ") + _short(head))
            extra = t("Hazırlanıyor…") if s["player"] == "preparing" else s["time"]
            if s["playing_list"]:
                extra = f"{extra}   •   {_short(s['playing_list'], 24)}" if extra else _short(s["playing_list"], 24)
            if extra:
                yield self._note("     " + extra)
            if s["next"]:
                yield self._note(f"     {t('Sıradaki')}: {_short(s['next'], 40)}")
        if stopped:
            yield self._item("▶ " + t("Kaldığın yerden çal" if s["can_resume"] else "Müzik çal"), "music", "toggle")
        else:
            yield self._item(("⏸ " + t("Duraklat")) if playing else ("▶ " + t("Çal")), "music", "toggle")
        yield self._item("⏭ " + t("Sonraki şarkı"), "music", "next")
        yield self._item("⏮ " + t("Önceki şarkı"), "music", "previous")
        yield self._item("⏹ " + t("Durdur"), "music", "stop", enabled=not stopped)
        yield self._item("🔀 " + t("Karışık çal"), "music", "shuffle", checked=s["shuffle"])
        yield pystray.MenuItem("🔁 " + t("Tekrar") + ": " + t(s["repeat"]), pystray.Menu(
            *[self._item(t(r), "repeat", r, checked=r == s["repeat"], radio=True) for r in REPEATS]))
        volume = 0 if s["muted"] else s["volume"]
        yield pystray.MenuItem(f"🔊 {t('Ses')}: %{volume}" if s["lang"] == "tr" else f"🔊 {t('Ses')}: {volume}%",
                               pystray.Menu(*self._volume_items(s, t)))
        sleep = s["sleep"]
        sleep_text = (t("Parça bitince") if sleep == "track" else
                      f"{sleep.replace('dk', t('dk'))} {t('kaldı')}" if sleep else t("Kapalı"))
        yield pystray.MenuItem("😴 " + t("Uyku zamanlayıcısı") + ": " + sleep_text, pystray.Menu(
            self._item(t("Kapalı"), "sleep", "off", checked=not sleep, radio=True),
            *[self._item(c.replace("dk", t("dk")), "sleep", c) for c in SLEEPS],
            self._item(t("Parça bitince"), "sleep", "track", checked=sleep == "track", radio=True)))
        if s["lists"]:
            names = s["lists"][:MAX_LISTS]
            yield pystray.MenuItem("📋 " + t("Çalma listesi"), pystray.Menu(
                *[self._item(_short(n, 40), "play_list", n, checked=n == s["playing_list"], radio=True)
                  for n in names]))
        yield self._item("🗗 " + t("Mini oynatıcıyı kapat" if s["mini"] else "Mini oynatıcı"), "music", "mini")
        yield self._item("🎤 " + t("Şarkı sözleri"), "music", "lyrics", enabled=not stopped)
        yield self._item("🎛 " + t("Ekolayzır"), "music", "eq")

    def _volume_items(self, s, t):
        yield self._item("➕ " + t("Sesi aç"), "volume", "+")
        yield self._item("➖ " + t("Sesi kıs"), "volume", "-")
        yield pystray.Menu.SEPARATOR
        for v in VOLUMES:
            yield self._item(f"%{v}" if s["lang"] == "tr" else f"{v}%", "volume", v,
                             checked=not s["muted"] and s["volume"] == v, radio=True)
        yield self._item("🔇 " + t("Sesi geri aç" if s["muted"] else "Sessiz"), "volume", "mute")

    def _download_items(self, s, t):
        parts = []
        if s["active"]:
            parts.append(f"{s['active']} {t('indiriliyor')}" + (f" • {s['speed']}/s" if s["speed"] else ""))
        if s["queued"]:
            parts.append(f"{s['queued']} {t('sırada')}")
        if s["paused"]:
            parts.append(f"{s['paused']} {t('duraklatıldı')}")
        yield self._note("⬇ " + (" • ".join(parts) if parts else t("Şu an indirme yok")))
        yield self._item("⏸ " + t("Hepsini duraklat"), "pause_all", enabled=bool(s["active"] or s["queued"]))
        yield self._item("▶ " + t("Hepsini başlat"), "resume_all", enabled=bool(s["paused"]))
        yield self._item("📋 " + t("Panodaki linki indir"), "paste")
        yield self._item("📂 " + t("İndirme klasörünü aç"), "open_folder")

    # ------------------------------------------------------------------ the icon itself
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
