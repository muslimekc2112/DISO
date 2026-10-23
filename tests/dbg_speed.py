import cProfile, pstats, io, time
import pytest
from music_support import FakeBackend
from app import player


@pytest.mark.gui
def test_speed(make_app, monkeypatch):
    monkeypatch.setattr(player, "new_backend", FakeBackend)
    app = make_app()
    app.update()
    pr = cProfile.Profile()
    t = time.perf_counter()
    pr.enable()
    app._open_settings()
    t1 = time.perf_counter()
    app.update()
    pr.disable()
    print("SETTINGS build", round((t1 - t) * 1000), "update", round((time.perf_counter() - t1) * 1000))
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(r"app\|ctk_scrollbar|ctk_scrollable|ctk_label|update", 30)
    print(s.getvalue()[-5000:])
