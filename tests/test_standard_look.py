"""🎨 "Standart (Önerilen)": the new look of a new computer. Our own palette ("Yeni") with the colourful pictures of
"Nostalji" in place of the flat emoji on the buttons."""
import customtkinter as ctk
import pytest

from app import classic_icons, icon_buttons, look
from app.config import DEFAULTS


@pytest.fixture
def standard():
    look.apply("Standart", "Koyu")
    yield
    look.apply("Yeni")


def test_it_is_the_first_look_of_a_new_computer():
    assert DEFAULTS["look"] == look.DEFAULT_STYLE == "Standart" == look.STYLES[0]
    assert look.label("Standart") == "Standart (Önerilen)"


def test_a_known_emoji_becomes_a_picture_and_media_keys_stay_symbols():
    assert icon_buttons.split("⬇  İndir") == ("download", "İndir")
    assert icon_buttons.split("📋") == ("paste", "")
    assert icon_buttons.split("⚙ Ayarlar") == ("options", "Ayarlar")
    assert icon_buttons.split("▶ Hepsini başlat") == ("start_all", "Hepsini başlat")
    assert icon_buttons.split("▶") is None and icon_buttons.split("⏸") is None      # the player's own keys
    assert icon_buttons.split("Klasör Seç") is None and icon_buttons.split("") is None
    for name in set(icon_buttons.PICTURES.values()) | set(icon_buttons.WITH_WORDS.values()):
        assert classic_icons.image(name, 24).size == (24, 24)                     # every picture is drawn


def test_buttons_get_their_picture_but_the_program_still_reads_its_text(standard):
    root = ctk.CTk()
    try:
        b = ctk.CTkButton(root, text="⚙ Ayarlar")
        assert b.cget("text") == "⚙ Ayarlar" and b._text == "Ayarlar" and b.cget("image") is not None
        b.configure(text="📺 3")
        assert b.cget("text") == "📺 3" and b._text == "3"
        b.configure(text="Kanallar")                                              # no emoji any more
        assert b.cget("text") == "Kanallar" and b.cget("image") is None
        plain = ctk.CTkButton(root, text="▶")
        assert plain.cget("text") == "▶" and plain.cget("image") is None
        tall = ctk.CTkButton(root, text="📋", height=44)
        assert tall.cget("image").cget("size") == (icon_buttons.BIG, icon_buttons.BIG)
    finally:
        root.destroy()


def test_other_looks_keep_their_emoji():
    look.apply("Yeni")
    root = ctk.CTk()
    try:
        b = ctk.CTkButton(root, text="⚙ Ayarlar")
        assert b._text == "⚙ Ayarlar" and b.cget("image") is None
    finally:
        root.destroy()


def test_the_main_button_keeps_the_accent_and_the_others_are_calm(standard, make_app):
    app = make_app()
    assert app.download_btn.cget("fg_color") == look.ACCENT
    assert ctk.ThemeManager.theme["CTkButton"]["fg_color"] == list(look.BUTTON)
    assert app.account_btn.cget("text").startswith("👤")
    app.withdraw()


def test_a_second_window_root_gets_pictures_of_its_own(standard):
    for _ in range(2):                          # the tests (and a restart in one process) make a new root
        root = ctk.CTk()
        try:
            b = ctk.CTkButton(root, text="📋 Yapıştır")
            root.update()                       # drawing it needs its pictures to exist in this root
            assert b.cget("image") is not None
        finally:
            root.destroy()
