"""Beside the downloads: 🚀 the speed test, 🛡 Windows Defender's scan, 📂 the watched folder and 🔌 copying
onto a USB stick — on their own and in the window."""
import os
import time
from types import SimpleNamespace

import pytest
from ui_support import add_item

from app import extras, ui
from app.models import DONE


# ------------------------------------------------------------------------------ 🚀 speed test
def test_the_suggested_connections_follow_the_speed():
    assert [extras.suggested_connections(m) for m in (5, 39.9, 40, 199, 200, 900)] == ["8", "8", "16", "16", "32", "32"]


def test_the_speed_test_counts_what_came_in_its_seconds():
    now = [0.0]

    class Response:
        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def close(self):
            pass

        def iter_content(self, size):
            for _ in range(1000):
                now[0] += 0.01                                     # 64 KB every 10 ms
                yield b"x" * 65536

    r = extras.speed_test(seconds=1, streams=1, get=lambda url, **k: Response(url), clock=lambda: now[0])
    assert 40 < r["mbps"] < 60 and r["connections"] == "16"


def test_no_connection_is_an_error():
    def refuse(url, **k):
        raise OSError("down")
    with pytest.raises(OSError):
        extras.speed_test(seconds=0.1, streams=2, get=refuse)


# ------------------------------------------------------------------------------ 🛡 Defender
def test_defender_answers_are_read_from_its_exit_code(tmp_path):
    f = tmp_path / "a.exe"
    f.write_bytes(b"x")
    runs = []

    def run(args, **k):
        runs.append(args)
        return SimpleNamespace(returncode=codes.pop(0))
    codes = [0, 2, 5]
    assert [extras.scan_file(str(f), tool="Mp.exe", run=run) for _ in range(3)] == ["clean", "threat", "unknown"]
    assert runs[0] == ["Mp.exe", "-Scan", "-ScanType", "3", "-File", str(f)]
    assert extras.scan_file(str(tmp_path / "gone"), tool="Mp.exe", run=run) == "unknown"


def test_the_scanner_works_one_after_another():
    seen = []
    scanner = extras.Scanner(scan=lambda path: seen.append(path) or ("threat" if "bad" in path else "clean"))
    a, b = SimpleNamespace(final_path="good.zip"), SimpleNamespace(final_path="bad.exe")
    scanner.scan(a)
    scanner.scan(b)
    scanner.scan(SimpleNamespace(final_path=""))                    # nothing to scan
    end = time.time() + 5
    out = []
    while len(out) < 2 and time.time() < end:
        out += scanner.drain()
        time.sleep(0.02)
    assert out == [(a, "clean"), (b, "threat")] and seen == ["good.zip", "bad.exe"]


def test_defender_is_found_on_this_windows():
    tool = extras.defender_tool()
    assert tool is None or tool.lower().endswith("mpcmdrun.exe")


# ------------------------------------------------------------------------------ 📂 watched folder
def test_a_file_put_into_the_watched_folder_is_taken_once_it_is_complete(tmp_path):
    tmp_path = tmp_path / "izle"
    tmp_path.mkdir()
    w = extras.FolderWatcher()
    w.folder = str(tmp_path)
    (tmp_path / "linux.torrent").write_bytes(b"d4:infoe")
    (tmp_path / "notes.docx").write_bytes(b"not ours")
    assert w.look() == []                                          # first seen: maybe still being written
    taken = w.look()
    assert taken == [str(tmp_path / "Eklendi" / "linux.torrent")] and w.drain() == taken
    assert sorted(os.listdir(tmp_path)) == ["Eklendi", "notes.docx"]
    (tmp_path / "linux.torrent").write_bytes(b"d4:infoe")           # the same name again: kept apart
    w.look()
    assert w.look() == [str(tmp_path / "Eklendi" / "linux (2).torrent")]


def test_a_growing_file_waits(tmp_path):
    w = extras.FolderWatcher()
    w.folder = str(tmp_path)
    f = tmp_path / "links.txt"
    f.write_text("http://a.example/x.zip")
    w.look()
    f.write_text("http://a.example/x.zip\nhttp://a.example/y.zip")    # still growing
    assert w.look() == []
    assert w.look() == [str(tmp_path / "Eklendi" / "links.txt")]


# ------------------------------------------------------------------------------ 🔌 USB
def test_songs_wait_for_a_usb_stick_then_go_onto_it(tmp_path):
    song = tmp_path / "Gülpembe.mp3"
    song.write_bytes(b"m" * 1000)
    stick = tmp_path / "E"
    drives = []
    copier = extras.UsbCopier(drives=lambda: list(drives))
    copier.pending.append(str(song))
    assert copier.step() is False and copier.pending == [str(song)]  # no stick: it waits
    stick.mkdir()
    drives.append(str(stick))
    assert copier.step() is True and copier.pending == []
    assert (stick / "DISO" / "Gülpembe.mp3").read_bytes() == b"m" * 1000
    assert copier.drain() == [(str(song), str(stick), None)]
    assert not list((stick / "DISO").glob("*.part"))


def test_the_usb_copier_runs_by_itself(tmp_path):
    song = tmp_path / "a.mp3"
    song.write_bytes(b"x")
    stick = tmp_path / "F"
    stick.mkdir()
    copier = extras.UsbCopier(drives=lambda: [str(stick)], every=0.05)
    copier.copy(str(song))
    end = time.time() + 5
    while not (stick / "DISO" / "a.mp3").exists() and time.time() < end:
        time.sleep(0.02)
    assert (stick / "DISO" / "a.mp3").exists()


def test_removable_drives_are_listed():
    assert all(d.endswith(":\\") for d in extras.removable_drives())


# ------------------------------------------------------------------------------ in the window
@pytest.mark.gui
def test_finished_downloads_are_scanned_and_songs_copied(app, monkeypatch, tmp_path):
    song, doc = tmp_path / "a.mp3", tmp_path / "b.pdf"
    song.write_bytes(b"x")
    doc.write_bytes(b"y")
    a = add_item(app, "A", DONE, final_path=str(song))
    b = add_item(app, "B", DONE, final_path=str(doc))
    scanned, copied = [], []
    monkeypatch.setattr(app.scanner, "scan", scanned.append)
    monkeypatch.setattr(app.usb, "copy", copied.append)
    app.cfg.set("usb_copy", "Yalnız şarkılar")
    app._after_done([a, b])
    assert scanned == [a, b] and copied == [str(song)]
    app.cfg.set("usb_copy", "Tüm indirmeler")
    app.cfg.set("defender_scan", False)
    scanned.clear()
    copied.clear()
    app._after_done([a, b])
    assert scanned == [] and copied == [str(song), str(doc)]


@pytest.mark.gui
def test_what_the_helpers_found_is_told(app, monkeypatch, tmp_path):
    it = add_item(app, "Kurulum", DONE, final_path=str(tmp_path / "x.exe"))
    monkeypatch.setattr(app.scanner, "drain", lambda: [(it, "threat")])
    monkeypatch.setattr(ui.notify, "toast", lambda *a: None)
    torrent = tmp_path / "Eklendi" / "a.torrent"
    monkeypatch.setattr(app.watcher, "drain", lambda: [str(torrent)])
    added = []
    monkeypatch.setattr(app, "_add_from_paths", lambda paths: added.extend(paths) or len(paths))
    monkeypatch.setattr(app.usb, "drain", lambda: [])
    app._drain_extras()
    assert it.message.startswith("⚠") and added == [str(torrent)]
    assert "İzlenen klasörden 1 indirme eklendi" in app._notice


@pytest.mark.gui
def test_the_extras_in_the_settings(app, monkeypatch, tmp_path):
    app._open_settings()
    s = app.settings_panel
    app.update()
    assert "Kapalı" in s.watch_hint.cget("text")
    s._set_watch(str(tmp_path))
    assert app.cfg.get("watch_folder") == str(tmp_path) and app.watcher.folder == str(tmp_path)
    assert str(tmp_path) in s.watch_hint.cget("text")
    s._set_watch("")
    assert app.watcher.folder == ""
    monkeypatch.setattr(extras, "speed_test", lambda: {"mbps": 250.0, "ping_ms": 12, "connections": "32"})
    app.cfg.set("connections", "8")
    s._speed_test()
    end = time.time() + 5
    while "Mbit" not in s.speed_hint.cget("text") and time.time() < end:
        app.update()
        time.sleep(0.02)
    assert "250.0 Mbit/sn" in s.speed_hint.cget("text") and "32" in s.speed_hint.cget("text")
    s._apply_speed()
    assert app.cfg.get("connections") == "32"
    s.destroy()
