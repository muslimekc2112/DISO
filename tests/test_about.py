"""The about window, the version badge, and remembering which version ran last."""
import json
import os
import sys
import time

import pytest
from ui_support import notice

from app import __channel__, __version__, __version_label__, about, brand, ui
from app import ui_common


def close_app(app):
    """Close a window the way the fixture does, so that a second one can be made in the same test (customtkinter
    ties its pictures to the first window of the process; the program only ever has one)."""
    import gc
    app._closing = True
    app.manager.shutdown()
    gc.collect()
    app.destroy()
    gc.enable()


def pump(window, condition, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        window.update()
        if condition():
            return True
        time.sleep(0.02)
    return condition()


# ------------------------------------------------------------------------------ the one place that names the program
def test_the_name_and_the_version_are_written_down_once():
    assert (brand.NAME, brand.PUBLISHER, brand.APP_ID) == ("DISO", "ISO", "DISO")
    assert brand.VERSION == __version__ == "0.11.3" and brand.CHANNEL == __channel__ == "beta"
    assert brand.VERSION_LABEL == __version_label__ == "0.11.3 beta" and brand.EXE_NAME == "DISO.exe"
    assert all(part.isdigit() for part in brand.VERSION.split("."))            # Windows and Chrome want numbers only


def test_the_extension_moves_with_the_program():
    manifest = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                           "browser_extension", "manifest.json"), encoding="utf-8"))
    assert manifest["version"] == brand.VERSION and manifest["version_name"] == brand.VERSION_LABEL
    assert manifest["name"] == brand.NAME


# ------------------------------------------------------------------------------ the facts
def test_the_facts_name_everything_that_helps_to_find_a_problem():
    rows = dict(about.facts())
    assert list(rows) == ["Sürüm", "Çalışma şekli", "Kurulum klasörü", "Veri klasörü", "Günlük dosyası", "Windows",
                          "Python", "yt-dlp", "FFmpeg", "Deno"]
    assert rows["Sürüm"] == "0.11.3 beta" and rows["Veri klasörü"].endswith("DISO") and rows["Günlük dosyası"].endswith("diso.log")
    assert all(str(v).strip() for v in rows.values())


def test_missing_tools_are_said_in_words_not_left_empty(monkeypatch):
    monkeypatch.setattr(about, "find_ffmpeg", lambda: None)
    monkeypatch.setattr(about.shutil, "which", lambda name: None)
    monkeypatch.setattr(about, "ytdlp_version", lambda: "")
    rows = dict(about.facts())
    assert "yok" in rows["FFmpeg"] and "yok" in rows["Deno"] and rows["yt-dlp"] == "yüklü değil"


def test_a_tool_that_is_there_is_shown_with_its_version(monkeypatch):
    monkeypatch.setattr(about.shutil, "which", lambda name: sys.executable)
    monkeypatch.setattr(about, "find_ffmpeg", lambda: r"C:\x\ffmpeg.exe")
    rows = dict(about.facts())
    assert rows["Deno"].startswith("Python") and sys.executable in rows["Deno"]       # stands in for "deno --version"
    assert rows["FFmpeg"] == r"C:\x\ffmpeg.exe"


def test_a_tool_that_will_not_start_does_not_break_the_facts(monkeypatch):
    monkeypatch.setattr(about.shutil, "which", lambda name: r"C:\yok\deno.exe")
    assert "sürüm okunamadı" in dict(about.facts())["Deno"]


def test_the_text_is_ready_to_paste():
    text = about.as_text([("Sürüm", "0.11.3 beta"), ("Windows", "Windows 11"), ("Veri klasörü", r"C:\x")])
    lines = text.splitlines()
    assert lines[0] == "DISO 0.11.3 beta" and len(lines) == 4
    assert lines[1].startswith("Sürüm:") and lines[2].startswith("Windows:") and lines[3].endswith(r"C:\x")
    assert len({l.index(" ", l.index(":") + 1) for l in lines[1:] if ":" in l}) >= 1


def test_the_folder_of_the_program(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\ISO\DISO\DISO.exe")
    assert about.install_folder() == r"C:\Program Files\ISO\DISO"
    monkeypatch.delattr(sys, "frozen")
    assert os.path.isfile(os.path.join(about.install_folder(), "main.py"))


def test_a_broken_ytdlp_is_reported_as_absent(monkeypatch):
    monkeypatch.setattr(about.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError("boom")))
    assert about.ytdlp_version() == ""


# ------------------------------------------------------------------------------ the logo
def test_the_logo_is_a_fresh_picture_each_time_and_missing_files_are_survived(monkeypatch):
    pytest.importorskip("customtkinter")
    a, b = ui_common.logo_image(40), ui_common.logo_image(40)
    assert a is not b and tuple(a.cget("size")) == (40, 40)
    monkeypatch.setattr("app.utils.resource_path", lambda rel: os.path.join(r"C:\yok", rel))
    assert ui_common.logo_image(40) is None


# ------------------------------------------------------------------------------ the windows
@pytest.mark.gui
def test_the_header_shows_the_name_the_beta_badge_and_the_icon(app):
    assert app.title() == "DISO" and app.beta_badge.cget("text") == "BETA"
    assert app._logo is not None


@pytest.mark.gui
def test_clicking_the_badge_opens_the_about_window_once(app, monkeypatch):
    monkeypatch.setattr(ui.about, "facts", lambda: [("Sürüm", "0.11.3 beta")])
    app.deiconify()                                                            # mouse events only reach a window that is shown
    app.update()
    app.beta_badge._label.event_generate("<Button-1>", x=2, y=2)
    app.update()
    app.withdraw()
    first = app.about_dialog
    assert first is not None and first.winfo_exists()
    app.open_about()
    assert app.about_dialog is first                                           # not a second window
    first.destroy()


@pytest.mark.gui
def test_the_about_window_fills_in_and_copies_the_details(app):
    rows = [("Sürüm", "0.11.3 beta"), ("Windows", "Windows 11"), ("Veri klasörü", r"C:\Veri")]
    dialog = ui.AboutDialog(app, provider=lambda: rows)
    dialog.withdraw()
    try:
        assert dialog.title() == "DISO hakkında" and str(dialog.copy_btn.cget("state")) == "disabled" or dialog.rows is not None
        assert pump(dialog, lambda: dialog.rows == rows)
        assert str(dialog.copy_btn.cget("state")) == "normal"
        texts = [str(w.cget("text")) for w in dialog.body.winfo_children() if hasattr(w, "cget")]
        assert {"Sürüm", "0.11.3 beta", "Windows 11", r"C:\Veri"} <= set(texts)
        dialog.copy_details()
        clip = app.clipboard_get()
        assert clip.startswith("DISO 0.11.3 beta") and "Windows 11" in clip and r"C:\Veri" in clip
        assert "panoya kopyalandı" in notice(app)
    finally:
        dialog.destroy()


@pytest.mark.gui
def test_the_about_window_survives_a_lookup_that_fails(app):
    def broken():
        raise RuntimeError("deno exploded")

    dialog = ui.AboutDialog(app, provider=broken)
    dialog.withdraw()
    try:
        assert pump(dialog, lambda: dialog.rows is not None)
        assert dict(dialog.rows)["Sürüm"] == "0.11.3 beta" and "Hata" in dict(dialog.rows)
    finally:
        dialog.destroy()


@pytest.mark.gui
def test_closing_the_about_window_before_the_facts_arrive_is_harmless(app):
    release = {}

    def slow():
        time.sleep(0.4)
        return [("Sürüm", "x")]

    dialog = ui.AboutDialog(app, provider=slow)
    dialog.withdraw()
    dialog.destroy()
    time.sleep(0.8)
    app.update()                                                                # the late answer finds no window: no error


@pytest.mark.gui
def test_the_data_folder_button_opens_the_data_folder(app, monkeypatch):
    opened = []
    monkeypatch.setattr(ui, "open_in_file_manager", opened.append)
    dialog = ui.AboutDialog(app, provider=lambda: [("Sürüm", "x")])
    dialog.withdraw()
    try:
        dialog.open_data()
        assert opened and opened[0].endswith("DISO")
    finally:
        dialog.destroy()


@pytest.mark.gui
def test_contact_us_opens_a_new_issue_on_github(app, monkeypatch):
    opened = []
    monkeypatch.setattr(ui.webbrowser, "open", opened.append)
    dialog = ui.AboutDialog(app, provider=lambda: [("Sürüm", "x")])
    dialog.withdraw()
    try:
        dialog.contact_btn.invoke()
        assert opened == ["https://github.com/muslimekc2112/DISO/issues/new"]
        texts = " ".join(str(w.cget("text")) for w in dialog.winfo_children() if isinstance(w, ui.ctk.CTkLabel))
        assert "Bize ulaş" in texts and "bana" not in texts
    finally:
        dialog.destroy()


@pytest.mark.gui
def test_the_settings_window_has_an_about_button_and_the_version(app, monkeypatch):
    monkeypatch.setattr(ui.about, "facts", lambda: [("Sürüm", "x")])
    app._open_settings()
    panel = app.settings_panel
    texts = []

    def walk(w):
        for c in w.winfo_children():
            try:
                texts.append(str(c.cget("text")))
            except Exception:  # noqa: BLE001
                pass
            walk(c)

    walk(panel)
    assert "DISO 0.11.3 beta" in texts and "ℹ Hakkında" in texts
    panel.about_button.invoke()
    app.update()
    assert app.about_dialog is not None and app.about_dialog.winfo_exists()
    app.about_dialog.destroy()


# ------------------------------------------------------------------------------ remembering the version
@pytest.mark.gui
def test_the_first_start_welcomes_and_remembers(make_app, isolated_home, monkeypatch):
    from app import config
    monkeypatch.setitem(config.DEFAULTS, "last_version", "")                # the real default: nothing remembered yet
    app = make_app()
    assert "hoş geldin" in notice(app) and app.cfg.get("last_version") == "0.11.3 beta"
    saved = json.load(open(isolated_home / "AppData" / "Local" / "DISO" / "settings.json", encoding="utf-8"))
    assert saved["last_version"] == "0.11.3 beta"


@pytest.mark.gui
def test_the_same_version_again_says_nothing(make_app, isolated_home):
    close_app(make_app())
    again = make_app()
    assert "hoş geldin" not in notice(again) and "güncellendi" not in notice(again)


@pytest.mark.gui
def test_a_newer_version_is_announced_once_and_remembered(make_app, isolated_home):
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir(parents=True)
    (d / "settings.json").write_text(json.dumps({"last_version": "0.9.0 beta"}), encoding="utf-8")
    app = make_app()
    assert "0.11.3 beta sürümüne güncellendi" in notice(app) and app.cfg.get("last_version") == "0.11.3 beta"
    close_app(app)
    assert "güncellendi" not in notice(make_app())


@pytest.mark.gui
def test_a_warning_is_not_hidden_by_the_welcome(make_app, isolated_home):
    import socket
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    d = isolated_home / "AppData" / "Local" / "DISO"
    d.mkdir(parents=True)
    (d / "settings.json").write_text(json.dumps({"bridge_port": blocker.getsockname()[1]}), encoding="utf-8")
    try:
        app = make_app()
        assert "port başka bir programda" in notice(app)                       # the more important message is the last one
    finally:
        blocker.close()
