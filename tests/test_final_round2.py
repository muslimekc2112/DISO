"""The very last round of 1.1, part two: "⏫ En üste al", a start that is not held up, Deno kept new, the health
check, "Sorun bildir" and the better 30 second preview."""
import datetime
import os
import socket
import time
import zipfile

import pytest


# ------------------------------------------------------------------------------ ⏫ to the front of the line
def test_a_queued_download_can_go_to_the_front():
    from app.manager import LineQueue
    from app.models import QUEUED, Item
    line = LineQueue()
    items = [Item(f"https://x.example/{n}.zip") for n in "abc"]
    for it in items:
        it.state = QUEUED
        line.put(it)
    assert [line.position(it) for it in items] == [1, 2, 3]
    assert line.to_front(items[2]) and line.position(items[2]) == 1
    items[0].state = "paused"                                     # a paused one waits but does not count
    assert line.position(items[1]) == 2
    assert line.get() is items[2] and line.get() is items[0]
    assert not line.to_front(Item("https://x.example/yok.zip"))


@pytest.mark.gui
def test_the_menu_offers_to_go_first_only_when_it_waits(app):
    from ui_support import add_item

    from app.models import QUEUED
    from app.ui import ItemMenu
    app.manager.set_gate(False)                                   # nothing starts: they all wait
    first = add_item(app, "a.zip", QUEUED)
    second = add_item(app, "b.zip", QUEUED)
    for it in (first, second):
        app.manager.q.put(it)
    assert "⏫ En üste al (sıradaki bu olsun)" not in dict(ItemMenu(first, app).menu_commands())   # next already
    dict(ItemMenu(second, app).menu_commands())["⏫ En üste al (sıradaki bu olsun)"]()
    assert app.manager.q.position(second) == 1 and "Sıradaki" in app._notice
    for it in (first, second):
        it.state = "paused"
    app.manager.set_gate(True)


# ------------------------------------------------------------------------------ the start is not held up
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_free_port_says_no_other_diso_at_once():
    from app import bridge
    start = time.perf_counter()
    assert bridge.ping_existing(free_port()) is False
    assert time.perf_counter() - start < 0.5                       # it used to wait 1.5 s for nothing
    assert bridge.port_taken(0) is False


# ------------------------------------------------------------------------------ Deno kept new
class Answer:
    def __init__(self, url="", data=None, status=200):
        self.url, self._data, self.status_code = url, data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(self.status_code)

    def json(self):
        return self._data


def test_deno_is_updated_for_a_new_minor_version_only():
    from app import deno_setup
    assert deno_setup.wanted("2.9.7", "2.10.0") and deno_setup.wanted("", "2.9.8") and deno_setup.wanted("1.46.3", "2.0.0")
    assert not deno_setup.wanted("2.9.7", "2.9.8") and not deno_setup.wanted("2.10.0", "2.9.9")
    from conftest import REAL_DENO_LATEST_TAG as latest_tag
    assert latest_tag(get=lambda url, **k: Answer(data={"tag_name": "v2.10.1"})) == "v2.10.1"

    def limited(url, **k):                                         # the API says "too many": the page tells
        return Answer(status=403) if "api.github" in url else Answer(url="https://github.com/denoland/deno/releases/tag/v2.10.2")
    assert latest_tag(get=limited) == "v2.10.2"


def test_a_deno_of_the_user_is_not_touched(monkeypatch):
    from app import deno_setup, updater
    monkeypatch.setattr(deno_setup, "find", lambda: r"C:\Kendi\deno.exe")
    monkeypatch.setattr(deno_setup, "version_of", lambda path: "2.0.0")
    monkeypatch.setattr(deno_setup, "latest_tag", lambda: pytest.fail("not asked"))
    u = updater.Updater()
    u._check_deno(install=True)
    assert u.components["deno"].status == "manual"


def test_diso_s_own_deno_is_updated(monkeypatch):
    from app import deno_setup, updater, utils
    own = os.path.join(utils.user_tools_dir(), "deno.exe")
    monkeypatch.setattr(deno_setup, "find", lambda: own)
    monkeypatch.setattr(deno_setup, "version_of", lambda path: "2.9.7")
    monkeypatch.setattr(deno_setup, "latest_tag", lambda: "v2.10.0")
    asked = []
    monkeypatch.setattr(deno_setup, "install", lambda tag, progress=None: asked.append(tag) or own)
    u = updater.Updater()
    u._check_deno(install=True)
    assert asked == ["v2.10.0"] and u.components["deno"].status == "done"
    asked.clear()
    monkeypatch.setattr(deno_setup, "latest_tag", lambda: "v2.9.9")
    u._check_deno(install=True)
    assert asked == [] and u.components["deno"].status == "current"


# ------------------------------------------------------------------------------ 🩺 health check
class Reply:
    status_code = 200

    def close(self):
        pass


def test_the_health_check_names_what_is_wrong_and_how_to_fix_it(tmp_path, monkeypatch):
    from app import about, deno_setup, health, torrent
    monkeypatch.setattr(health, "find_ffmpeg", lambda: None)
    monkeypatch.setattr(deno_setup, "find", lambda: None)
    monkeypatch.setattr(torrent, "find_aria2", lambda: None)
    monkeypatch.setattr(about, "ytdlp_version", lambda: "2020.01.01")
    checks = list(health.run(str(tmp_path), get=lambda url, **k: Reply(), online=lambda proxy=None: (True, "HTTP 204")))
    by = {c.name: c for c in checks}
    assert by["İnternet bağlantısı"].status == health.OK and by["YouTube"].status == health.OK
    assert by["yt-dlp"].status == health.WARN and by["yt-dlp"].fix == "update"
    assert by["FFmpeg"].fix == "ffmpeg" and by["Deno"].status == health.BAD and by["Deno"].fix == "deno"
    assert by["Tarayıcı eklentisi"].fix == "extension" and by["İndirme klasörü"].status == health.OK
    offline = list(health.run(str(tmp_path / "yok"), online=lambda proxy=None: (False, "x")))
    assert "YouTube" not in [c.name for c in offline]
    assert {c.name: c for c in offline}["İndirme klasörü"].status == health.BAD
    assert "✗ Deno" in health.as_text(offline)
    assert health.ytdlp_age("2026.08.19", today=datetime.date(2026, 10, 21)) == 63


@pytest.mark.gui
def test_the_health_window_shows_each_check_and_its_fix(app):
    from app import health
    fixes = []
    checks = [health.Check("İnternet bağlantısı", health.OK, "var"), health.Check("Deno", health.BAD, "yok", "deno")]
    app._health_checks = lambda: iter(checks)
    app.health_fix = fixes.append
    win = app.open_health()
    end = time.time() + 5
    while time.time() < end and win.running:
        app.update()
        time.sleep(0.02)
    assert [c.name for c in win.results] == ["İnternet bağlantısı", "Deno"] and "1 sorun" in win.summary.cget("text")
    buttons = [w for w in win.rows.winfo_children() if type(w).__name__ == "CTkButton"]
    assert len(buttons) == 1                                        # only the broken one has a fix
    buttons[0].invoke()
    assert fixes == ["deno"]
    win.destroy()


# ------------------------------------------------------------------------------ 🐞 report a problem
def test_the_report_has_what_helps_and_nothing_private(tmp_path):
    from app import report
    from app.logs import log_path
    from app.models import ERROR, Item
    os.makedirs(os.path.dirname(log_path()), exist_ok=True)
    with open(log_path(), "w", encoding="utf-8") as f:
        f.write("failed: https://www.youtube.com/watch?v=GIZLI&list=x 403\n")
    it = Item("https://site.example/ozel/dosya.zip?token=abc", kind="file")
    it.state, it.error = ERROR, "403 https://site.example/ozel/dosya.zip?token=abc"
    path = report.make("DISO 1.1\nWindows 11", "✓ İnternet: var", {"proxy": "http://ali:sifre@proxy:8080", "theme": "Koyu"},
                       [it], folder=str(tmp_path))
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        text = "\n".join(z.read(n).decode("utf-8") for n in names)
    assert {"bilgi.txt", "ayarlar.json", "indirmeler.txt", "diso.log", "NOT.txt"} <= names
    assert "GIZLI" not in text and "token=abc" not in text and "sifre" not in text and "ozel" not in text
    assert "https://www.youtube.com/…" in text and "http://***@proxy:8080" in text and "Koyu" in text
    url = report.issue_url("DISO 1.1\nWindows 11", os.path.basename(path))
    assert url.startswith("https://github.com/") and "body=" in url and "DISO-sorun-raporu" in url


@pytest.mark.gui
def test_report_problem_asks_first_then_puts_the_zip_on_the_desktop(app, monkeypatch, tmp_path):
    from tkinter import messagebox

    from app import health, report, ui
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)
    app.report_problem()
    assert "Rapor" not in app._notice                              # "no": nothing happens
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(report, "desktop", lambda: str(tmp_path))
    opened = []
    monkeypatch.setattr(ui, "open_in_file_manager", opened.append)
    monkeypatch.setattr(ui.webbrowser, "open", opened.append)
    app.report_problem([health.Check("Deno", health.OK, "2.9.8")])
    end = time.time() + 15
    while time.time() < end and len(opened) < 2:
        app._drain_ui_calls()
        time.sleep(0.05)
    assert opened[0].startswith(str(tmp_path)) and opened[0].endswith(".zip") and "issues/new" in opened[1]


# ------------------------------------------------------------------------------ 🎧 the better preview
def test_the_preview_starts_at_the_most_replayed_part():
    from app import music_search
    falling = [{"start_time": i * 2.0, "end_time": i * 2.0 + 2, "value": 1.0 - i * 0.008} for i in range(100)]
    assert music_search.most_replayed(200, falling) is None                 # only the start: no chorus
    bump = [dict(p) for p in falling]
    for p in bump[25:30]:                                                    # 50–60 s: people jump back here
        p["value"] += 0.3
    assert 46 <= music_search.preview_start(200, bump) <= 50
    assert music_search.preview_start(200, falling) == 60                   # no bump: a third in, as before
    assert music_search.preview_start(50, bump) == 0


def test_a_preview_is_made_once_with_fades_and_kept(monkeypatch):
    from app import music_search
    import app.utils as utils
    monkeypatch.setattr(utils, "find_ffmpeg", lambda: "ffmpeg")
    resolved, ran = [], []

    def resolve(url, kind, quality):
        resolved.append(url)
        return {"url": "https://stream.example/a", "duration": 200, "heatmap": None}

    def run(cmd, **kw):
        ran.append(cmd)
        with open(cmd[-1], "wb") as f:
            f.write(b"\xff" * 5000)
    url = "https://music.youtube.com/watch?v=x"
    first = music_search.prepare_preview(url, 200, run=run, resolve=resolve)
    again = music_search.prepare_preview(url, 200, run=run, resolve=resolve)
    assert first == again == {"path": music_search.preview_file(url), "start": 60, "chorus": False}
    assert len(resolved) == len(ran) == 1                                    # the second time: the kept file
    assert any("afade=t=in" in a and "afade=t=out" in a for a in ran[0])
    for n in range(music_search.PREVIEW_KEEP + 3):
        with open(os.path.join(music_search.preview_dir(), f"onizleme-{n:04d}.mp3"), "wb") as f:
            f.write(b"x")
        time.sleep(0.002)
    music_search.prune_previews()
    assert len([n for n in os.listdir(music_search.preview_dir()) if n.endswith(".mp3")]) == music_search.PREVIEW_KEEP


@pytest.mark.gui
def test_the_preview_shows_how_far_it_is_and_its_part(app, monkeypatch, tmp_path):
    from music_support import FakeBackend, FakeReader, make_wav

    from app import player, tags
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    monkeypatch.setattr(tags, "TagReader", FakeReader)
    app._ensure_music()
    music = app.music
    result = {"title": "Şımarık", "url": "https://music.youtube.com/watch?v=x", "duration": 192}
    music._start_preview(result, {"path": make_wav(tmp_path / "p.mp3"), "start": 42, "chorus": True})
    text = music.find_label.cget("text")
    assert text.startswith("🎧 0:00 / 0:30") and "Şımarık" in text and "en çok dinlenen kısım" in text
    music.stop_preview()
    assert os.path.isfile(tmp_path / "p.mp3")                                # kept: played again at once
