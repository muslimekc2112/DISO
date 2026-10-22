"""🧲 .torrent files and magnet: links open in DISO: the registry entries (under a throw-away test key, never
the real Classes), the links read from the command line, and handing them to the DISO that already runs."""
import secrets
import time
import winreg

import pytest

from app import associations as a

EXE = r"C:\Program Files\ISO\DISO\DISO.exe"


@pytest.fixture
def prefix():
    p = rf"Software\DISOTest\assoc_{secrets.token_hex(4)}" + "\\"
    yield p
    a._delete_tree(winreg.HKEY_CURRENT_USER, p.rstrip("\\"))


def get(prefix, path, name=""):
    return a._get(winreg.HKEY_CURRENT_USER, prefix + path, name)


def test_registering_makes_torrent_files_and_magnet_links_open_in_diso(prefix):
    got = a.register(EXE, prefix=prefix)
    assert got == {"torrent": True, "magnet": True}
    assert get(prefix, r"Software\Classes\.torrent") == "DISO.torrent"
    assert get(prefix, r"Software\Classes\DISO.torrent\shell\open\command") == f'"{EXE}" "%1"'
    assert get(prefix, r"Software\Classes\magnet", "URL Protocol") == ""
    assert get(prefix, r"Software\RegisteredApplications", "DISO") == r"Software\ISO\DISO\Capabilities"
    assert get(prefix, r"Software\ISO\DISO\Capabilities\URLAssociations", "magnet") == "DISO.magnet"
    assert a.unregister(prefix=prefix, inside=r"C:\Program Files\ISO\DISO")
    assert get(prefix, r"Software\Classes\.torrent") is None and get(prefix, r"Software\Classes\magnet") is None
    assert get(prefix, r"Software\Classes\DISO.torrent") is None
    assert get(prefix, r"Software\RegisteredApplications", "DISO") is None


def test_another_programs_links_are_not_taken_and_not_removed(prefix):
    other = '"C:\\qBittorrent\\qbittorrent.exe" "%1"'
    a._set(winreg.HKEY_CURRENT_USER, prefix + r"Software\Classes\magnet\shell\open\command", "", other)
    a._set(winreg.HKEY_CURRENT_USER, prefix + r"Software\Classes\.torrent", "", "qBittorrent.File.Torrent")
    got = a.register(EXE, prefix=prefix)
    assert got == {"torrent": False, "magnet": False}                    # Windows' default apps decides
    assert get(prefix, r"Software\Classes\.torrent\OpenWithProgids", "DISO.torrent") == ""   # offered in "Open with"
    a.unregister(prefix=prefix)
    assert get(prefix, r"Software\Classes\magnet\shell\open\command") == other
    assert get(prefix, r"Software\Classes\.torrent") == "qBittorrent.File.Torrent"


def test_another_copy_of_diso_keeps_its_registrations(prefix):
    a.register(r"D:\Başka\ISO\DISO\DISO.exe", prefix=prefix)
    assert a.unregister(prefix=prefix, inside=r"C:\Program Files\ISO\DISO") is False
    assert get(prefix, r"Software\Classes\.torrent") == "DISO.torrent"


def test_links_from_the_command_line(tmp_path):
    t = tmp_path / "linux.torrent"
    t.write_bytes(b"d4:infoe")
    got = a.links_from_argv(["--minimized", "magnet:?xt=urn:btih:abc", str(t), str(tmp_path / "missing.torrent"),
                             "notes.txt"])
    assert got == ["magnet:?xt=urn:btih:abc", t.as_uri()]


def test_no_registry_in_tests_or_from_the_source(monkeypatch):
    monkeypatch.setenv("DISO_NO_NATIVE_HOST", "1")
    assert a.program_path() is None


@pytest.mark.gui
def test_a_running_diso_takes_the_links_of_a_second_start(app, monkeypatch):
    started = []
    monkeypatch.setattr(app.manager, "start", started.append)          # not downloaded for real here
    assert a.send_to_running(["magnet:?xt=urn:btih:abc"], app.bridge.port)
    assert app.manager.find_duplicate("magnet:?xt=urn:btih:abc") is not None


@pytest.mark.gui
def test_the_setting_is_a_switch(app, monkeypatch):
    called = []
    monkeypatch.setattr(a, "program_path", lambda: EXE)
    monkeypatch.setattr(a, "register", lambda exe: called.append(("on", exe)) or {"torrent": True, "magnet": True})
    monkeypatch.setattr(a, "unregister", lambda: called.append(("off",)))
    app.set_associate(False)
    app.set_associate(True)
    assert called == [("off",), ("on", EXE)] and app.cfg.get("associate") is True
