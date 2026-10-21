"""Explanations over the buttons: a moment after the mouse came, in the interface's language, gone when
it leaves or clicks."""
import json
import os
import subprocess
import sys
import textwrap
import time

import pytest

from app import tooltip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pump(widget, seconds):
    end = time.time() + seconds
    while time.time() < end:
        widget.update()
        time.sleep(0.01)


@pytest.mark.gui
def test_every_icon_button_of_the_download_window_explains_itself(app):
    assert tooltip.text_for(app.torrent_btn) == "Torrent dosyası ekle"
    assert tooltip.text_for(app.history_button) == "İndirme geçmişi"
    app.channels_btn.configure(text="📺 3")                           # "3 new videos": still the channels
    assert tooltip.text_for(app.channels_btn) == "Takip edilen kanallar"


@pytest.mark.gui
def test_it_shows_after_a_moment_and_goes_when_the_mouse_leaves_or_clicks(app, monkeypatch):
    monkeypatch.setattr(tooltip, "DELAY", 150)
    app.deiconify()
    app.update()
    tip = app.torrent_btn._tip
    tip.enter()
    _pump(app, 0.05)
    assert tip.win is None                                           # not at once
    _pump(app, 0.4)
    assert tip.win is not None and tip.win.winfo_exists()
    label = tip.win.winfo_children()[0]
    assert label.cget("text") == "Torrent dosyası ekle"
    monkeypatch.setattr(app.torrent_btn, "winfo_containing", lambda x, y: None)
    tip.leave()
    assert tip.win is None
    tip.enter()
    tip.cancel()                                                     # a click: nothing comes
    _pump(app, 0.4)
    assert tip.win is None


@pytest.mark.gui
def test_the_play_button_has_its_own_words(app, monkeypatch):
    from music_support import FakeBackend

    from app import player
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    assert tooltip.text_for(app.music.play_btn) == "Çal / duraklat"
    assert tooltip.text_for(app.music.next_btn) == "Sonraki şarkı"


def test_in_english_the_explanations_are_english(tmp_path):
    """The English layer is for the whole program: its own process."""
    script = textwrap.dedent(f"""
        import json, sys
        sys.path.insert(0, {ROOT!r})
        from app import i18n
        i18n.set_language("English")
        import customtkinter as ctk
        from app import tooltip
        tooltip.install()
        root = ctk.CTk()
        out = {{}}
        for text in ("🧲", "📊", "🎤 Sözler", "📋 Sıra", "🗑 Hepsini temizle"):
            b = ctk.CTkButton(root, text=text)
            out[text] = tooltip.text_for(b)
        root.destroy()
        json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
    """)
    path = tmp_path / "out.json"
    subprocess.run([sys.executable, "-c", script, str(path)], check=True, timeout=60, cwd=ROOT)
    out = json.loads(path.read_text(encoding="utf-8"))
    assert out == {"🧲": "Add a torrent file", "📊": "Download history", "🎤 Sözler": "Lyrics",
                   "📋 Sıra": "Up next", "🗑 Hepsini temizle": "Empty the list (files stay)"}
