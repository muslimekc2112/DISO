"""🧲 Torrents: magnet / .torrent links, aria2 downloaded once and checked, the progress of a torrent, pause,
resume and cancel. The real-aria2 tests make their own torrent, tracker and seeder on this computer."""
import filecmp
import io
import os
import pathlib
import time
import zipfile

import pytest
from conftest import wait_for
from torrent_support import Tracker, make_torrent, seed

from app import torrent, utils
from app.manager import DownloadManager
from app.models import CANCELLED, DONE, PAUSED, Item, Settings
from app.segmented_downloader import DownloadError, DownloadStopped

ARIA2 = torrent.find_aria2()            # the real one, looked up before the tests hide the user's folders
needs_aria2 = pytest.mark.skipif(not ARIA2, reason="aria2c is not installed")


# ------------------------------------------------------------------------------ what a torrent is
def test_magnets_torrent_links_and_files_are_torrents():
    magnet = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=Ubuntu+24.04"
    assert torrent.is_torrent_link(magnet) and torrent.magnet_name(magnet) == "Ubuntu 24.04"
    assert torrent.is_torrent_link("https://releases.example/ubuntu.iso.torrent?x=1")
    assert torrent.is_torrent_link("file:///C:/İndirilenler/a%20b.torrent")
    assert torrent.local_torrent("file:///C:/İndirilenler/a%20b.torrent") == os.path.normpath("C:/İndirilenler/a b.torrent")
    assert not torrent.is_torrent_link("https://x.example/a.zip") and torrent.local_torrent("https://x/a.torrent") == ""
    assert utils.is_url(magnet) and utils.is_url("file:///C:/a.torrent") and not utils.is_url("file:///C:/a.exe")
    assert utils.extract_urls(f"bak: {magnet} ve https://a.example/b.") == [magnet, "https://a.example/b"]


# ------------------------------------------------------------------------------ aria2 itself
def _aria2_zip():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("aria2-1.37.0-win-64bit-build1/aria2c.exe", b"MZ fake aria2")
        z.writestr("aria2-1.37.0-win-64bit-build1/README.html", "readme")
    return out.getvalue()


def test_aria2_is_downloaded_once_and_only_when_its_checksum_is_right(server, monkeypatch):
    import hashlib
    monkeypatch.setattr(torrent.shutil, "which", lambda name: None)
    data = _aria2_zip()
    name = server.add(data, ".zip")
    with pytest.raises(DownloadError, match="SHA-256"):
        torrent.ensure_aria2(url=server.url("f", name), sha256="0" * 64)
    assert torrent.find_aria2() is None and os.listdir(utils.user_tools_dir()) == []      # nothing is kept
    path = torrent.ensure_aria2(url=server.url("f", name), sha256=hashlib.sha256(data).hexdigest())
    assert open(path, "rb").read() == b"MZ fake aria2" and os.listdir(utils.user_tools_dir()) == [os.path.basename(path)]
    hits = server.hits(name)
    assert torrent.ensure_aria2(url=server.url("f", name), sha256="x") == path and server.hits(name) == hits


def test_aria2_that_cannot_be_reached_is_a_connection_problem(server, monkeypatch):
    monkeypatch.setattr(torrent.shutil, "which", lambda name: None)
    monkeypatch.setattr(torrent.time, "sleep", lambda s: None)
    with pytest.raises(DownloadError) as e:
        torrent.ensure_aria2(url=server.url("f", "yok.zip"), tries=2)
    assert e.value.network


# ------------------------------------------------------------------------------ one torrent, fake aria2
class FakeAria2:
    """Answers tellStatus from a script: a magnet's metadata first, then the files."""

    def __init__(self, script, folder):
        self.script, self.folder, self.calls, self.closed = list(script), folder, [], None

    def call(self, method, *params):
        self.calls.append((method, params))
        if method in ("addUri", "addTorrent"):
            return "g1"
        if method == "tellStatus":
            return self.script.pop(0) if len(self.script) > 1 else self.script[0]
        return None

    def close(self, wait=5.0):
        self.closed = wait


def _status(**kw):
    out = {"status": "active", "totalLength": "0", "completedLength": "0", "downloadSpeed": "0", "connections": "0",
           "seeder": "false", "files": []}
    out.update(kw)
    return out


def _bt(name):
    return {"info": {"name": name}}


def test_a_magnet_gets_its_name_then_its_files(tmp_path, monkeypatch):
    monkeypatch.setattr(torrent, "ensure_aria2", lambda progress=None: "aria2c")
    monkeypatch.setattr(torrent, "POLL", 0)
    folder = str(tmp_path / "dl")
    seen = []
    script = [_status(status="complete", followedBy=["g2"], files=[{"path": "[METADATA]abc"}]),
              _status(totalLength="1000", completedLength="250", downloadSpeed="50", connections="3", numSeeders="2",
                      bittorrent=_bt("Albüm"), files=[{"path": os.path.join(folder, "Albüm", "a.bin")}]),
              _status(totalLength="1000", completedLength="1000", seeder="true", bittorrent=_bt("Albüm"))]
    item = Item("magnet:?xt=urn:btih:abc&dn=Albüm", folder=folder)
    original = item.on_progress
    item.on_progress = lambda *a: seen.append((a, item.message)) or original(*a)
    sessions = []
    path = torrent.run(item, aria2_factory=lambda exe, f: sessions.append(FakeAria2(script, f)) or sessions[-1])
    assert path == os.path.join(folder, "Albüm") and item.title == "Albüm" and item.final_path == path
    assert ("tellStatus", ("g2", torrent.KEYS)) in sessions[0].calls                   # it followed the metadata
    assert (250, 1000, 50.0, 15.0, 3) in [s[0] for s in seen]
    assert sessions[0].closed == 1.0 and os.path.isdir(folder)


def test_pause_and_cancel_stop_aria2_and_cancel_names_its_files(tmp_path, monkeypatch):
    monkeypatch.setattr(torrent, "ensure_aria2", lambda progress=None: "aria2c")
    monkeypatch.setattr(torrent, "POLL", 0.01)
    folder = str(tmp_path / "dl")
    part = os.path.join(folder, "Film", "film.mkv")
    for reason in ("pause", "cancel"):
        item = Item("https://x.example/film.torrent", folder=folder)
        script = [_status(totalLength="100", completedLength="10", bittorrent=_bt("Film"), files=[{"path": part}])]
        sessions = []
        factory = lambda exe, f: sessions.append(FakeAria2(script, f)) or sessions[-1]     # noqa: E731
        import threading
        threading.Timer(0.1, lambda: item.request_stop(reason)).start()
        with pytest.raises(DownloadStopped) as e:
            torrent.run(item, aria2_factory=factory)
        assert e.value.reason == reason and sessions[0].closed == 5.0
        assert item.temp_files == ([] if reason == "pause" else [part, part + ".aria2", os.path.join(folder, "Film.aria2")])


def test_the_manager_sends_any_torrent_link_to_aria2(tmp_path, monkeypatch):
    ran = []

    def fake_run(item, ask=None):
        ran.append((item.url, item.kind))
        item.title, item.final_path = "Ubuntu", str(tmp_path / "Ubuntu")
        return item.final_path
    monkeypatch.setattr(torrent, "run", fake_run)
    m = DownloadManager(store_path=str(tmp_path / "d.json"))
    magnet = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
    assert m.add_url(magnet, Settings(kind="audio", folder=str(tmp_path)))       # MP3 was chosen: still a torrent
    wait_for(lambda: m.items[0].state == DONE)
    assert ran == [(magnet, "audio")] and m.items[0].final_path.endswith("Ubuntu")
    assert m.find_duplicate(magnet)


@pytest.mark.gui
def test_a_torrent_file_from_the_file_button(app, tmp_path):
    t = tmp_path / "film.torrent"
    t.write_bytes(b"d4:infod4:name4:filmee")
    added = []
    app.add_urls = lambda urls, kind=None: added.append(urls) or len(urls)
    app._add_from_paths([str(t)])
    assert added == [[pathlib.Path(str(t)).as_uri()]]


# ------------------------------------------------------------------------------ the real aria2
@pytest.fixture
def world(tmp_path):
    """A folder of two files, its .torrent, a tracker and a seeder (slow when asked)."""
    src = tmp_path / "seed"
    (src / "Albüm" / "CD 2").mkdir(parents=True)
    (src / "Albüm" / "01 Şarkı.bin").write_bytes(os.urandom(3_000_000))
    (src / "Albüm" / "CD 2" / "02.bin").write_bytes(os.urandom(1_500_000))
    tracker = Tracker()
    tfile = tmp_path / "albüm.torrent"
    tfile.write_bytes(make_torrent(str(src), "Albüm", tracker.announce))
    procs = []
    yield {"src": src, "torrent": tfile, "seed": lambda limit="0": procs.append(seed(ARIA2, str(tfile), str(src), limit))}
    for p in procs:
        p.kill()
        p.wait(5)
    tracker.stop()


def _same(a, b):
    return filecmp.cmp(a, b, shallow=False)


@needs_aria2
def test_a_real_torrent_is_downloaded_whole(world, tmp_path, monkeypatch):
    monkeypatch.setattr(torrent, "find_aria2", lambda: ARIA2)
    world["seed"]()
    dl = tmp_path / "dl"
    item = Item(pathlib.Path(world["torrent"]).as_uri(), folder=str(dl))
    start = time.time()
    path = torrent.run(item)
    assert path == str(dl / "Albüm") and time.time() - start < 40
    assert _same(world["src"] / "Albüm" / "01 Şarkı.bin", dl / "Albüm" / "01 Şarkı.bin")
    assert _same(world["src"] / "Albüm" / "CD 2" / "02.bin", dl / "Albüm" / "CD 2" / "02.bin")
    assert sorted(os.listdir(dl)) == ["Albüm"]                                   # no control or metadata files


@needs_aria2
def test_a_real_torrent_paused_goes_on_and_cancelled_leaves_nothing(world, tmp_path, monkeypatch):
    monkeypatch.setattr(torrent, "find_aria2", lambda: ARIA2)
    world["seed"]("600K")                                                        # ~8 s for the whole album
    dl = tmp_path / "dl"
    m = DownloadManager(store_path=str(tmp_path / "d.json"))
    m.add_url(pathlib.Path(world["torrent"]).as_uri(), Settings(kind="auto", folder=str(dl)))
    item = m.items[0]
    wait_for(lambda: item.done > 300_000, timeout=30)
    m.pause(item)
    wait_for(lambda: item.state == PAUSED, timeout=15)
    done_before = item.done
    m.resume(item)
    wait_for(lambda: item.state == DONE, timeout=60)
    assert done_before > 0 and _same(world["src"] / "Albüm" / "01 Şarkı.bin", dl / "Albüm" / "01 Şarkı.bin")

    other = tmp_path / "dl2"
    m.add_url(pathlib.Path(world["torrent"]).as_uri(), Settings(kind="auto", folder=str(other)))
    second = m.items[1]
    wait_for(lambda: second.done > 300_000, timeout=30)
    m.cancel(second)
    wait_for(lambda: second.state == CANCELLED, timeout=15)
    assert os.listdir(other) == []                                               # its half files went too


# ------------------------------------------------------------------------------ 🧲 which files
def test_a_kept_choice_goes_to_aria2_and_is_not_asked_again(tmp_path, monkeypatch):
    monkeypatch.setattr(torrent, "ensure_aria2", lambda progress=None: "aria2c")
    monkeypatch.setattr(torrent, "POLL", 0)
    folder = str(tmp_path / "dl")
    script = [_status(totalLength="10", completedLength="10", seeder="true", bittorrent=_bt("Film"))]
    item = Item("https://x.example/film.torrent", folder=folder)
    item.torrent_select = [3, 1]
    sessions = []
    torrent.run(item, aria2_factory=lambda exe, f: sessions.append(FakeAria2(script, f)) or sessions[-1],
                ask=lambda *a: pytest.fail("asked again"))
    assert sessions[0].calls[0] == ("addUri", (["https://x.example/film.torrent"], {"select-file": "1,3"}))
    assert torrent.select_text([3, "1", 3]) == "1,3"


@needs_aria2
def test_only_the_chosen_files_come_and_the_choice_can_change(world, tmp_path, monkeypatch):
    monkeypatch.setattr(torrent, "find_aria2", lambda: ARIA2)
    world["seed"]("400K")
    dl = tmp_path / "dl"
    asked = []

    def ask(item, files, reply):
        asked.append(sorted(f["path"] for f in files))
        reply([f["index"] for f in files if f["path"].endswith("02.bin")])
    m = DownloadManager(store_path=str(tmp_path / "d.json"))
    m.torrent_ask = ask
    m.add_url(pathlib.Path(world["torrent"]).as_uri(), Settings(kind="auto", folder=str(dl)))
    item = m.items[0]
    wait_for(lambda: item.done > 100_000, timeout=30)
    assert asked == [["Albüm/01 Şarkı.bin", "Albüm/CD 2/02.bin"]] and len(item.torrent_files) == 2
    item.reselect = [f["index"] for f in item.torrent_files]                  # "Dosyaları seç…": both after all
    wait_for(lambda: item.state == DONE, timeout=60)
    assert _same(world["src"] / "Albüm" / "01 Şarkı.bin", dl / "Albüm" / "01 Şarkı.bin")
    assert _same(world["src"] / "Albüm" / "CD 2" / "02.bin", dl / "Albüm" / "CD 2" / "02.bin")
    assert sorted(item.torrent_select) == [1, 2] and sorted(os.listdir(dl)) == ["Albüm"]


@needs_aria2
def test_cancelling_the_question_cancels_the_torrent(world, tmp_path, monkeypatch):
    monkeypatch.setattr(torrent, "find_aria2", lambda: ARIA2)
    world["seed"]()
    dl = tmp_path / "dl"
    m = DownloadManager(store_path=str(tmp_path / "d.json"))
    m.torrent_ask = lambda item, files, reply: reply(None)
    m.add_url(pathlib.Path(world["torrent"]).as_uri(), Settings(kind="auto", folder=str(dl)))
    wait_for(lambda: m.items[0].state == CANCELLED, timeout=30)
    assert not dl.exists() or os.listdir(dl) == []


FILES = [{"index": 1, "path": "Film/Film.mkv", "size": 4_000_000_000, "done": 0},
         {"index": 2, "path": "Film/Altyazı/tr.srt", "size": 60_000, "done": 0},
         {"index": 3, "path": "Film/Ses/müzik.mp3", "size": 9_000_000, "done": 0},
         {"index": 4, "path": "Film/kapak.jpg", "size": 200_000, "done": 0}]


@pytest.mark.gui
def test_the_file_window_ticks_folders_and_kinds_and_answers(app, tmp_path):
    from app.torrent_ui import TorrentFilesDialog
    got = []
    win = TorrentFilesDialog(app, "Film", FILES, str(tmp_path), lambda v, remember: got.append((v, remember)))
    app.update()
    assert "4 / 4 dosya" in win.summary.cget("text") and str(win.ok_btn.cget("state")) == "normal"
    assert set(win.quick) == {"all", "none", "video", "music", "pictures"}        # only the kinds it has
    win.pick("video")
    assert win.ticked == {1}
    folder = next(n for n, idx in win._nodes.items() if idx == {2} and win.tree.get_children(n))   # "Altyazı"
    win.toggle(folder)
    assert win.ticked == {1, 2} and win.tree.item(folder, "text").startswith("☑")
    top = next(n for n, idx in win._nodes.items() if idx == {1, 2, 3, 4})
    assert win.tree.item(top, "text").startswith("◩")                         # some of it
    win.pick("none")
    assert str(win.ok_btn.cget("state")) == "disabled"
    win.search.insert(0, "srt")
    win._fill()
    assert len([n for n, idx in win._nodes.items() if not win.tree.get_children(n)]) == 1
    win.pick("music")
    win.remember.select()
    win.accept()
    assert got == [([3], True)]


@pytest.mark.gui
def test_the_app_asks_once_and_can_ask_again_while_it_downloads(app, tmp_path):
    item = Item("magnet:?xt=urn:btih:abc&dn=Film", folder=str(tmp_path))
    answers = []
    app._ask_torrent_files(item, FILES, answers.append)
    app._drain_ui_calls()
    win = app.torrent_dialogs[item.id]
    win.pick("video")
    win.accept()
    assert answers == [[1]]
    item.torrent_files, item.torrent_select = FILES, [1]
    from app.ui import ItemMenu
    item.state = "downloading"
    menu = dict(ItemMenu(item, app).menu_commands())
    win = menu["🧲 Dosyaları seç…"]()
    assert win.ticked == {1} and win.ok_btn.cget("text") == "✓ Uygula"
    win.pick("all")
    win.accept()
    assert item.reselect == [1, 2, 3, 4] and answers == [[1]]
    app.cfg.set("torrent_ask", False)
    app._ask_torrent_files(item, FILES, answers.append)                        # not asked: all of them
    assert answers[-1] == [1, 2, 3, 4]
