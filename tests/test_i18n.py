"""English: the translation itself (no window), and the real program in English in a process of its own
(the English layer changes the widget classes for the whole process, so the other tests must not share it)."""
import json
import os
import subprocess
import sys

import pytest

from app import i18n, lang_en

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def english(monkeypatch):
    i18n._load()
    monkeypatch.setattr(i18n, "current", "en")


def test_turkish_changes_nothing(monkeypatch):
    monkeypatch.setattr(i18n, "current", "tr")
    assert i18n.tr("Kapat") == "Kapat" and i18n.tr(5) == 5


def test_whole_texts_and_texts_with_parts(english):
    assert i18n.tr("Kapat") == "Close"
    assert i18n.tr("12 parça") == "12 songs"
    assert i18n.tr("“Gece” listesi silinsin mi? (3 parça)\nDosyalar silinmez.") == "Delete the list “Gece”? (3 songs)\nThe files stay."
    assert i18n.tr("Liste parça adına göre sıralandı") == "List sorted by title"          # a known part is translated too
    assert i18n.tr("Bilinmeyen bir şey") == "Bilinmeyen bir şey"                          # unknown: left as it is


def test_lines_pieces_and_icons_in_front(english):
    assert i18n.tr("✅ Bitti • 3 MB\n1 altyazı kaydedildi") == "✅ Done • 3 MB\n1 subtitles saved"
    assert i18n.tr("🗑 Listeden kaldır") == "🗑 Remove from list"
    assert i18n.tr("3 parça • 1 sa 5 dk") == "3 songs • 1 h 5 min"                     # each piece by its own template
    assert i18n.tr("⬇ Şarkı • %45") == "⬇ Şarkı • 45%"                               # a template that has the dot itself


def test_every_template_has_as_many_parts_in_both_languages():
    for tr_text, en_text in lang_en.TEMPLATES:
        assert tr_text.count("{}") == en_text.count("{}"), tr_text


def test_the_choice_values_of_the_program_are_all_translated(english):
    from app import config, models
    from app.music_ui import MODES, SLEEP_CHOICES, VIEW_FIND, VIEW_LISTS
    from app.player import REPEAT_MODES
    from app.ui import FILTER_STATES, KIND_LABELS, SORT_KEYS
    values = (list(config.THEMES) + list(config.AFTER_ALL) + config.SORTS + config.FILTERS + models.SUBTITLE_CHOICES
              + MODES + SLEEP_CHOICES + [VIEW_LISTS, VIEW_FIND] + list(REPEAT_MODES)
              + list(FILTER_STATES) + list(KIND_LABELS) + list(SORT_KEYS))
    same_in_english = {"Video (MP4)", "Proxy"}
    untranslated = [v for v in values if i18n.tr(v) == v and v not in same_in_english]
    assert untranslated == []


def test_the_language_comes_from_the_settings_or_else_from_windows(tmp_path, monkeypatch):
    from app.config import Config
    settings = tmp_path / "settings.json"
    monkeypatch.setattr(i18n, "windows_language", lambda: "English")
    assert i18n.saved_language(str(settings)) == "English"                       # nothing chosen yet: Windows' own
    assert i18n.saved_language(str(settings), "Türkçe") == "Türkçe"
    settings.write_text(json.dumps({"language": "Türkçe"}), encoding="utf-8")
    assert i18n.saved_language(str(settings)) == "Türkçe"                        # a choice wins
    assert "language" in Config(str(settings)).saved
    settings.write_text(json.dumps({"theme": "Koyu"}), encoding="utf-8")
    assert "language" not in Config(str(settings)).saved


def test_texts_built_from_pieces_are_translated_too(english):
    assert i18n.tr("Altyazı: tr, en  (+3 otomatik dil)") == "Subtitles: tr, en  (+3 automatic languages)"
    assert i18n.tr("Altyazı: yok") == "Subtitles: none"
    assert i18n.tr("Bugün 14:05") == "Today 14:05" and i18n.tr("toplam 3 MB") == "3 MB in total"
    assert i18n.tr("Video: 3 • MP3: 2 • Dosya: 1") == "Video: 3 • MP3: 2 • Files: 1"
    assert i18n.tr("⏸ Beklemede • 45.0%") == "⏸ Paused • 45.0%"
    assert i18n.tr("Sadece ses (MP3) • ~3 MB") == "Audio only (MP3) • ~3 MB"
    assert i18n.tr("Çalamadım, sıradakine geçtim: Şarkı") == "Could not play it, went on to the next one: Şarkı"


SCRIPT = r'''
import json, os, sys, tkinter as tk
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from app import config, i18n
config.DEFAULTS["bridge_port"] = 0
i18n.set_language("English")
from app import player, tags
sys.path.insert(0, os.path.join(ROOT, "tests"))
from music_support import FakeBackend, FakeReader, FakeKeys, FakeSearcher, FakeOverlay, FakeThumbBar
from app import mediakeys, music_search, smtc, taskbar, updater
player.new_backend = FakeBackend; tags.TagReader = FakeReader; mediakeys.MediaKeys = FakeKeys
music_search.Searcher = FakeSearcher; smtc.MediaOverlay = FakeOverlay; taskbar.ThumbBar = FakeThumbBar
updater.Updater.start = lambda self: None
from app.ui import App
app = App(); app.withdraw(); app.update()
app._open_settings(); app._ensure_music(); app.open_history(); app.open_shortcuts(); app.open_channels(); app.update()
texts = []
def walk(w):
    for c in w.winfo_children():
        try:
            t = c.cget("text")
            if isinstance(t, str) and t.strip(): texts.append(t)
        except Exception:
            pass
        try:
            ph = c.cget("placeholder_text")
            if isinstance(ph, str) and ph.strip(): texts.append(ph)
        except Exception:
            pass
        walk(c)
walk(app)
out = {"texts": texts, "kind": app.kind_menu.get(), "kind_shown": app.kind_menu._current_value,
       "mode": app.music.mode_bar.get(), "titles": [app.title(), app.music.title(), app.settings_panel.title()],
       "headings": [app.music.tree.heading(c)["text"] for c in ("title", "artist")]}
app.kind_menu._dropdown_callback(app.kind_menu._values[1])
out["kind_after"] = app.cfg.get("kind")
app._on_close()
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
'''


@pytest.mark.gui
def test_the_real_program_in_english(tmp_path, isolated_home):
    script = tmp_path / "en.py"
    script.write_text(SCRIPT.replace("ROOT", repr(ROOT)).replace("sys.path.insert(0, " + repr(ROOT) + ")",
                                                                  "sys.path.insert(0, " + repr(ROOT) + ")"), encoding="utf-8")
    out = tmp_path / "out.json"
    env = dict(os.environ, HIZLI_NO_UPDATE="1")
    done = subprocess.run([sys.executable, str(script), str(out)], capture_output=True, text=True, timeout=120, env=env)
    if done.returncode != 0 and "no display" in done.stderr.lower():
        pytest.skip("no display")
    assert done.returncode == 0, done.stderr[-3000:]
    data = json.load(open(out, encoding="utf-8"))
    texts = data["texts"]
    for english in ("⚙ Settings", "Download mode", "Music player mode", "🔍 Find songs", "Keyboard shortcuts",
                    "📊 Download history", "Close", "＋ File", "🎤 Lyrics", "⬇  Download", "📺 Followed channels",
                    "＋ Follow", "⟳ Look now"):
        assert any(english in t for t in texts), english
    assert data["kind"] == "Otomatik (dosya / video)" and data["kind_shown"] == "Automatic (file / video)"
    assert data["mode"] in ("Müzik çalar modu", "İndirme modu")                       # the program reads Turkish
    assert data["kind_after"] in ("Video (MP4)",)                                      # a choice is saved in Turkish
    assert data["titles"][1] == "DISO • Music player" and data["headings"] == ["Song", "Artist"]
    turkish = [t for t in texts if any(c in t for c in "çğıöşüÇĞİÖŞÜ")
               and not any(name in t for name in ("Barış", "Gülpembe", "Tuğra"))]
    assert turkish == [], turkish
