"""Shared by the window tests: stand-ins for the countdown window and the tray icon, the
`make_app` / `app` fixtures (a real, hidden window with a private home folder) and helpers."""
import gc

import pytest

from app import notify, updater
from app.models import Item


class FakeCountdown:
    """Stands in for the countdown window: records the question and answers 'yes' at once."""
    log = []

    def __init__(self, app, text, seconds, on_done):
        FakeCountdown.log.append((text, seconds))
        on_done()


class FakeTray:
    """Stands in for the tray icon (no icon appears on the real taskbar during tests)."""
    instances = []

    def __init__(self, title, on_event, image=None, language="tr"):
        self.on_event, self.title, self.started, self.stopped = on_event, title, False, False
        self.state = {"lang": language}
        FakeTray.instances.append(self)

    def set_state(self, **values):
        self.state.update(values)

    def set_language(self, code):
        self.state["lang"] = "en" if code in ("en", "English") else "tr"

    def t(self, text):
        return text

    def start(self):
        self.started = True

    def set_title(self, text):
        self.title = text

    def stop(self):
        self.stopped = True


@pytest.fixture
def make_app(monkeypatch, isolated_home):
    """Returns make(minimized=False) -> a hidden App. Everything that would touch the real
    machine (tray icon, registry, sounds, toasts, shutdown, network update) is replaced."""
    pytest.importorskip("customtkinter")
    from app import brand, config, ui
    FakeCountdown.log = []
    FakeTray.instances = []
    notes = {"sound": [], "toast": [], "power": [], "startup": []}
    monkeypatch.setitem(config.DEFAULTS, "bridge_port", 0)                    # any free port
    monkeypatch.setitem(config.DEFAULTS, "last_version", brand.VERSION_LABEL)  # not a first run: no welcome note in the way
    monkeypatch.setitem(config.DEFAULTS, "extension_ask", False)              # nor the "add the extension?" window
    monkeypatch.setattr(ui.tray, "TrayIcon", FakeTray)
    monkeypatch.setattr(ui.startup, "set_enabled", lambda on, *a, **k: notes["startup"].append(on) or True)
    monkeypatch.setattr(updater.Updater, "start", lambda self: None)          # no network
    from app import app_update

    def no_github():
        raise ConnectionError("no internet in the tests")
    monkeypatch.setattr(app_update.AppUpdate, "start", lambda self: None)     # nor a look for a new DISO
    monkeypatch.setattr(app_update, "latest_release", no_github)
    monkeypatch.setattr(notify, "play_sound", lambda kind="done": notes["sound"].append(kind))
    monkeypatch.setattr(notify, "toast", lambda title, body, path=None: notes["toast"].append((title, body)))
    monkeypatch.setattr(notify, "power_action", lambda kind: notes["power"].append(kind) or True)
    monkeypatch.setattr(ui, "CountdownDialog", FakeCountdown)
    from music_support import FakeKeys, FakeSearcher
    from app import mediakeys, music_search
    monkeypatch.setattr(mediakeys, "MediaKeys", FakeKeys)                     # never the user's real keyboard keys
    monkeypatch.setattr(music_search, "Searcher", FakeSearcher)               # no internet
    from app import lyrics
    monkeypatch.setattr(lyrics, "fetch", lambda *a, **k: None)                 # no internet for lyrics either
    from app import channels

    def no_channel(url):
        raise ConnectionError("no internet in the tests")
    monkeypatch.setattr(channels, "read_channel", no_channel)                  # nor for followed channels
    from music_support import FakeEqBackend, FakeOverlay, FakeThumbBar
    from app import player
    monkeypatch.setattr(player, "new_eq_backend", FakeEqBackend)                # no real sound for the equalizer
    from app import smtc
    from app import taskbar as taskbar_module
    monkeypatch.setattr(smtc, "MediaOverlay", FakeOverlay)                    # not Windows' real media panel
    monkeypatch.setattr(taskbar_module, "ThumbBar", FakeThumbBar)             # nor the real taskbar
    made = []

    def make(minimized=False):
        try:
            app = ui.App(minimized=minimized)
        except Exception as e:  # noqa: BLE001 - no display
            pytest.skip(f"no display: {e}")
        if not minimized:
            app.withdraw()
        app.update()
        app.notes = notes
        made.append(app)
        return app

    yield make
    import customtkinter
    for app in made:
        try:
            app._closing = True
            app.manager.shutdown()
            app.channel_watcher.stop()
            gc.collect()      # same rule as the real window: collect Tk objects on this thread
            app.destroy()
        except Exception:  # noqa: BLE001 - already closed by the test
            pass
    gc.collect()
    gc.enable()
    customtkinter.set_appearance_mode("dark")   # a test may have switched the theme


@pytest.fixture
def app(make_app):
    return make_app()


def add_item(app, title, state, **kw):
    it = Item(f"http://x/{title.lower()}", kind="file", title=title)
    it.state = state
    for k, v in kw.items():
        setattr(it, k, v)
    app.manager.items.append(it)
    return it


def shown(app):
    app._sync_rows()
    return [app.rows[i].item.title for i in app._order]


def notice(app):
    return app._notice


def local_urls(server, n, size=2000):
    return [server.url("f", server.file(size)[0]) for _ in range(n)]


def destroyed(app):
    try:
        app.update()
        return not app.winfo_exists()
    except Exception:  # noqa: BLE001 - Tcl error: the window is gone
        return True
