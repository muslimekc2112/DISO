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
    assert tour.count.cget("text") == f"1 / {len(welcome_ui.DOWNLOAD_TOUR)}"
    tour.go(+1)
    assert int(app.url_entry.cget("border_width")) == 3                # the link box is pointed at
    tour.go(+1)
    assert int(app.url_entry.cget("border_width")) != 3                 # and let go at the next step
    for _ in range(len(welcome_ui.TOUR) - 3):
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


@pytest.mark.gui
def test_the_new_cards_of_1_2_open_their_features(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    actions = {card[3] for card in welcome_ui.WHATS_NEW}
    assert {"friends", "share_song", "like", "account"} == actions - {None}
    opened = []
    monkeypatch.setattr(app, "open_extension_guide", lambda: opened.append("guide"))
    app.try_feature("extension")
    assert opened == ["guide"]
    assert "account" in actions
    monkeypatch.setattr(app, "open_account", lambda: opened.append("account"))
    app.try_feature("account")
    assert opened == ["guide", "account"]
    opened.clear()
    opened.append("guide")
    assert app._ensure_music()
    monkeypatch.setattr(app.music, "_open_speed_menu", lambda: opened.append("speed"))
    monkeypatch.setattr(app.music.order_menu, "_open_dropdown_menu", lambda: opened.append("order"))
    app.try_feature("speed")
    app.try_feature("order")
    end = __import__("time").time() + 2
    while len(opened) < 3 and __import__("time").time() < end:
        app.update()
    assert opened == ["guide", "speed", "order"]


@pytest.mark.gui
def test_every_step_of_both_tours_points_at_something_real(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    assert app._ensure_music()
    for steps, owner in ((welcome_ui.DOWNLOAD_TOUR, app), (welcome_ui.MUSIC_TOUR, app.music)):
        assert len(steps) >= 12                                          # a real tour, not five lines
        for _, _, _, target in steps:
            assert target is None or getattr(owner, target, None) is not None, target
        tour = welcome_ui.TourWindow(owner, steps)
        for i, (_, _, _, target) in enumerate(steps):
            tour.step = i
            tour.show()
            assert (tour._outlined is not None) == bool(target), target          # each one is really pointed at
        tour.finish()


@pytest.mark.gui
def test_the_music_tour_comes_the_first_time_the_player_opens_and_never_beside_the_other(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    app.cfg.set("music_tour_done", False)
    tour = app.open_tour()                                               # the download window's tour is open
    app._switch_mode("Müzik çalar modu")
    assert not tour.winfo_exists() and app.tour_window is None           # it goes when the player comes
    app._maybe_music_tour()
    music_tour = app.music_tour_window
    assert music_tour is not None and music_tour.winfo_exists() and music_tour.owner is app.music
    assert music_tour._outlined is None                                  # the welcome: the whole player
    music_tour.go(+1)
    assert music_tour._outlined[0] is app.music.view_switch               # it points into the player
    app._switch_mode("İndirme modu")
    assert not music_tour.winfo_exists() and not app.cfg.get("music_tour_done")   # closed by the switch: not seen
    app._switch_mode("Müzik çalar modu")
    app._maybe_music_tour()
    app.music_tour_window.finish()                                       # "Atla" / walked to the end: seen
    assert app.cfg.get("music_tour_done") is True
    app.music_tour_window = None
    app._maybe_music_tour()
    assert app.music_tour_window is None                                 # only once
    app.open_music_tour()                                                # but again whenever asked for
    assert app.music_tour_window.winfo_exists()
    app.open_tour()                                                      # and the other one takes its place
    assert app.music_tour_window is None and app.tour_window.winfo_exists() and app.mode == "İndirme modu"
    app.tour_window.finish()


@pytest.mark.gui
def test_some_steps_are_tried_by_hand_and_the_tour_goes_on_by_itself(app, monkeypatch):
    import time
    monkeypatch.setattr(welcome_ui, "TRY_DONE_WAIT", 50)

    def wait_for(done, seconds=3):
        end = time.time() + seconds
        while not done() and time.time() < end:
            app.update()
            time.sleep(0.02)
        return done()

    tour = app.open_tour()
    tour.go(+1)                                                          # "Linki buraya yapıştır"
    assert tour.try_label.winfo_manager() == "grid" and "Ctrl+V" in tour.try_label.cget("text")
    app.url_entry.insert(0, "https://www.youtube.com/watch?v=xyz")
    assert wait_for(lambda: tour.step == 2)                              # seen: on to "İndir" by itself
    assert "İndir" in tour.try_label.cget("text")
    app.manager.items.append(object())                                    # (as if ⬇ İndir was pressed)
    assert wait_for(lambda: tour.step == 3)
    assert tour.try_label.winfo_manager() == ""                          # a step that is only told
    tour.go(-1)
    tour.go(+1)                                                          # "İleri" goes on without trying
    assert tour.step == 3
    app.manager.items.pop()
    tour.finish()


@pytest.mark.gui
def test_the_cards_of_1_5_open_their_features(app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    opened = []
    monkeypatch.setattr(app, "open_account", lambda page=None: opened.append(("account", page)))
    monkeypatch.setattr(app, "_open_settings", lambda tab=None: opened.append(("settings", tab)))
    monkeypatch.setattr(app, "open_tour", lambda: opened.append(("tour", None)))
    monkeypatch.setattr(app, "share_list", lambda name: opened.append(("share", name)))
    for action in ("devices", "look", "settings", "tour", "share", "karaoke"):
        if action == "karaoke":
            monkeypatch.setattr(app.music, "set_karaoke", lambda on=None: opened.append(("karaoke", on)))
        app.try_feature(action)
    assert opened == [("account", "devices"), ("settings", "Sistem"), ("settings", None), ("tour", None),
                      ("share", app.music.viewed), ("karaoke", True)]
    assert app.mode == "Müzik çalar modu"
