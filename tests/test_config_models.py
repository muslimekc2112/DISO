import json

from app import config
from app.models import (ACTIVE_STATES, DONE, DOWNLOADING, PAUSED, QUEUED, Item)


# ------------------------------------------------------------------------------ config
def test_settings_survive_a_restart(tmp_path):
    path = str(tmp_path / "s.json")
    c = config.Config(path)
    c.set("quality", "720p")
    c.set("max_parallel", 5)
    c.set("playlist", True)
    again = config.Config(path)
    assert (again.get("quality"), again.get("max_parallel"), again.get("playlist")) == ("720p", 5, True)


def test_defaults_are_used_when_nothing_is_saved(tmp_path):
    c = config.Config(str(tmp_path / "none.json"))
    assert c.data == config.DEFAULTS


def test_wrong_types_and_unknown_keys_in_the_file_are_ignored(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"quality": 5, "max_parallel": "x", "playlist": "yes",
                                "folder": "C:/x", "nonsense": 1}), encoding="utf-8")
    c = config.Config(str(path))
    assert c.get("quality") == config.DEFAULTS["quality"]
    assert c.get("max_parallel") == config.DEFAULTS["max_parallel"]
    assert c.get("playlist") is False
    assert c.get("folder") == "C:/x"            # the one valid value is kept
    assert "nonsense" not in c.data


def test_corrupt_settings_file_does_not_crash(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json", encoding="utf-8")
    assert config.Config(str(path)).data == config.DEFAULTS
    path.write_text("[1, 2]", encoding="utf-8")
    assert config.Config(str(path)).data == config.DEFAULTS


def test_sanitize_resets_values_that_are_no_longer_menu_choices(tmp_path):
    c = config.Config(str(tmp_path / "s.json"))
    c.data["quality"] = "4320p"
    c.sanitize({"quality": ["En iyi", "720p"]})
    assert c.get("quality") == "En iyi"


def test_setting_the_same_value_does_not_rewrite_the_file(tmp_path):
    path = tmp_path / "s.json"
    c = config.Config(str(path))
    c.set("quality", "720p")
    stamp = path.stat().st_mtime_ns
    c.set("quality", "720p")
    assert path.stat().st_mtime_ns == stamp


def test_choice_tables_are_consistent():
    assert config.SPEED_LIMITS["Sınırsız"] == 0
    assert all(v > 0 for k, v in config.SPEED_LIMITS.items() if k != "Sınırsız")
    assert config.DEFAULTS["speed_limit"] in config.SPEED_LIMITS
    assert config.DEFAULTS["sort"] in config.SORTS and config.DEFAULTS["filter"] in config.FILTERS
    assert "none" in config.AFTER_ALL.values()


# ------------------------------------------------------------------------------- Item
def test_item_roundtrip_keeps_only_persisted_fields():
    it = Item("http://x/a.zip", kind="file", connections=8, folder="D:/dl", title="a.zip")
    it.state = DONE
    d = it.to_dict()
    assert set(d) == set(Item.PERSISTED)
    back = Item.from_dict({**d, "unknown": 1})
    assert (back.url, back.kind, back.connections, back.folder, back.title) == \
           ("http://x/a.zip", "file", 8, "D:/dl", "a.zip")
    assert back.fraction == 1.0  # a finished download shows 100 % after a restart


def test_items_that_were_running_when_the_app_closed_come_back_paused():
    for state in ACTIVE_STATES:
        it = Item.from_dict({"url": "http://x", "state": state})
        assert it.state == PAUSED
    assert Item.from_dict({"url": "http://x", "state": DONE}).state == DONE


def test_display_name_prefers_title_then_file_name_then_url():
    it = Item("http://x/y")
    assert it.display_name == "http://x/y"
    it.dest = "C:\\dl\\file.zip"
    assert it.display_name == "file.zip"
    it.title = "My video"
    assert it.display_name == "My video"


def test_progress_updates_fraction():
    it = Item("http://x")
    it.on_progress(50, 200, 1000.0, 3.0, 4)
    assert (it.fraction, it.speed, it.eta, it.conns) == (0.25, 1000.0, 3.0, 4)
    it.on_progress(10, 0, 0.0, None, 0)       # unknown size must not divide by zero
    assert it.fraction == 0.0


class _FakeEngine:
    def __init__(self):
        self.reasons = []

    def stop(self, reason):
        self.reasons.append(reason)


class _FakeProc:
    killed = False

    def kill(self):
        self.killed = True


def test_request_stop_reaches_the_engine_and_a_running_ffmpeg():
    it = Item("http://x")
    fd, proc = _FakeEngine(), _FakeProc()
    it.attach(fd)
    it._proc = proc
    it.request_stop("pause")
    assert it.stop_reason == "pause" and fd.reasons == ["pause"] and proc.killed


def test_a_stop_requested_before_the_engine_exists_is_applied_on_attach():
    it = Item("http://x")
    it.request_stop("cancel")
    fd = _FakeEngine()
    it.attach(fd)
    assert fd.reasons == ["cancel"]


def test_new_item_starts_queued():
    assert Item("http://x").state == QUEUED and DOWNLOADING in ACTIVE_STATES
