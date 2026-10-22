"""👋 The first start's tour and 🎉 "Yenilikler" (each card's "Dene" opens its feature)."""
import pytest
from music_support import FakeBackend

from app import brand, player, welcome_ui


@pytest.mark.gui
def test_the_first_start_offers_the_tour_and_an_update_the_news(app, monkeypatch):
    opened = []
    monkeypatch.setattr(app, "after", lambda ms, fn=None, *a: opened.append(fn.__name__) if fn else None)
    app.cfg.set("last_version", "")
    app._announce_version()
    assert opened == ["open_tour"]
    opened.clear()
    app.cfg.set("last_version", "0.9")
    app._announce_version()
    assert opened == ["open_whats_new"] and app.cfg.get("last_version") == brand.VERSION_LABEL
    opened.clear()
    app._announce_version()                                         # the same version again: nothing
    assert opened == []


@pytest.mark.gui
def test_in_the_tray_nothing_pops_up(app, monkeypatch):
    opened = []
    monkeypatch.setattr(app, "after", lambda ms, fn=None, *a: opened.append(fn) if fn else None)
    app._started_hidden = True
    app.cfg.set("last_version", "")
    app._announce_version()
    assert opened == []


@pytest.mark.gui
def test_the_tour_walks_through_and_outlines_what_it_tells_about(app):
    tour = app.open_tour()
    assert app.open_tour() is tour
    assert tour.head.cget("text").endswith("hoş geldin!") and tour.back_btn.cget("state") == "disabled"
    assert int(app.url_entry.cget("border_width")) == 3                # the link box is pointed at
    tour.go(+1)
    assert int(app.url_entry.cget("border_width")) != 3                 # and let go at the next step
    for _ in range(len(welcome_ui.TOUR) - 2):
        tour.go(+1)
    assert tour.next_btn.cget("text") == "Başla 🚀"
    tour.go(+1)
    assert not tour.winfo_exists()


@pytest.mark.gui
def test_whats_new_cards_open_their_features(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    win = app.open_whats_new()
    assert len(win.cards) == len(welcome_ui.WHATS_NEW)
    opened = []
    monkeypatch.setattr(app, "open_phone", lambda: opened.append("phone"))
    monkeypatch.setattr(app, "_open_settings", lambda tab=None: opened.append(tab))
    win.try_it("phone")
    win.try_it("extras")
    assert opened == ["phone", "Ekstralar"]
    stats = app.try_feature("stats")
    assert app.mode == "🎵 Müzik çalar modu" or app.music is not None
    assert stats is app.music.stats_window
    stats.destroy()
    vis = app.try_feature("visualizer")
    assert vis.show_lyrics
    vis.destroy()
    win.destroy()
