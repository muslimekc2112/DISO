"""❓ "Neden inmedi?": technical errors in plain words, and the click that fixes them."""
import pytest
from ui_support import add_item

from app import explain, ui
from app.models import ERROR, QUEUED


@pytest.mark.parametrize("error, fix, words", [
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot. Use --cookies-from-browser", "cookies", "giriş"),
    ("ERROR: [youtube] abc: Sign in to confirm your age. This video may be inappropriate", "cookies", "Yaş"),
    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", None, "gizli"),
    ("ERROR: [youtube] abc: Video unavailable. This video has been removed by the uploader", None, "kaldırılmış"),
    ("The uploader has not made this video available in your country", "proxy", "ülkende"),
    ("[Errno 28] No space left on device", "folder", "yer"),
    ("[Errno 13] Permission denied: 'C:\\\\x'", "folder", "izni"),
    ("ERROR: unable to extract nsig function", "tools", "Site değişmiş"),
    ("HTTP Error 404: Not Found", None, "sunucuda yok"),
    ("HTTP Error 403: Forbidden", "retry", "izin vermedi"),
    ("Read timed out. (read timeout=30)", "retry", "bağlantısı"),
    ("ERROR: Unsupported URL: https://example.com/", None, "desteklenmiyor"),
    ("something nobody has seen", "retry", "Beklenmedik"),
])
def test_errors_get_a_reason_and_a_fix(error, fix, words):
    reason, got = explain.explain(error)
    assert got == fix and words.lower() in reason.lower()


def test_the_browser_for_login_cookies():
    names = ["Yok", "firefox", "chrome", "edge", "brave"]
    assert explain.cookie_browser({"chrome": "c", "edge": "e"}, names) == "edge"
    assert explain.cookie_browser({"chrome": "c", "firefox": "f"}, names) == "firefox"
    assert explain.cookie_browser({}, names) is None


@pytest.mark.gui
def test_a_failed_row_says_why_and_play_fixes_it(app, monkeypatch):
    it = add_item(app, "Video", ERROR, error="ERROR: Sign in to confirm you're not a bot")
    app._sync_rows()
    row = app.rows[it.id]
    row.refresh()
    assert row.info.cget("text") == "❌ Site giriş yapmanı istiyor.\n🔧 ▶: Giriş çerezlerini aç ve tekrar dene"
    labels = [label for label, _ in row.menu_commands()]
    assert labels[:2] == ["🔧 Giriş çerezlerini aç ve tekrar dene", "❓ Hatanın ayrıntısı"]
    monkeypatch.setattr(ui.extension_setup, "find_browsers", lambda: {"firefox": "f.exe"})
    started = []
    monkeypatch.setattr(app.manager, "start", started.append)
    row._toggle()                                                     # ▶ on the failed row
    assert started == [it] and it.cookies == "firefox" and app.cfg.get("cookies") == "firefox"
    assert app.cookie_menu.get() == "firefox"


@pytest.mark.gui
def test_other_fixes(app, monkeypatch, tmp_path):
    it = add_item(app, "Dosya", ERROR, error="[Errno 28] No space left on device")
    monkeypatch.setattr(ui.filedialog, "askdirectory", lambda **k: str(tmp_path))
    again = []
    monkeypatch.setattr(app.manager, "redownload", again.append)
    assert app.fix_error(it, "folder") and it.folder == str(tmp_path) and again == [it]
    opened = []
    monkeypatch.setattr(app, "_open_updates", lambda: opened.append("updates"))
    monkeypatch.setattr(app, "_open_settings", lambda tab=None: opened.append(tab))
    app.fix_error(it, "tools")
    app.fix_error(it, "proxy")
    assert opened == ["updates", "İndirme"]
    shown = []
    monkeypatch.setattr(ui.messagebox, "showinfo", lambda title, text, **k: shown.append(text))
    app.show_error(it)
    assert "Diskte yer kalmadı." in shown[0] and "No space left" in shown[0]
    q = add_item(app, "Q", QUEUED)
    assert all(not label.startswith("🔧") for label, _ in app.rows.get(q.id, None).menu_commands()) \
        if q.id in app.rows else True
