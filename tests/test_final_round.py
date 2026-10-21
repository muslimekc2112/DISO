"""The very last round of 1.1: files that survive a power cut, "⏫ En üste al", Deno kept new, the health
check, "Sorun bildir", the better 30 second preview."""
import json
import os
import time

import pytest

from app import safefile


# ------------------------------------------------------------------------------ files that survive
def test_a_broken_file_comes_back_from_its_last_good_copy(tmp_path):
    path = str(tmp_path / "settings.json")
    safefile.write_json(path, {"a": 1})
    assert json.load(open(path, encoding="utf-8")) == {"a": 1} and not os.path.exists(path + ".tmp")
    safefile.write_json(path, {"a": 2})                         # the first good one is kept as the copy
    assert json.load(open(path + ".bak", encoding="utf-8")) == {"a": 1}
    open(path, "w").write('{"a": 2, "b": [1, 2')               # cut off by a power cut
    safefile.take_recovered()
    assert safefile.read_json(path) == {"a": 1}
    assert open(path + ".bozuk").read().startswith('{"a": 2') and safefile.take_recovered() == ["settings.json"]
    assert safefile.read_json(path) == {"a": 1}                 # the copy took the broken one's place
    open(path, "w").write("")
    open(path + ".bak", "w").write("çöp")
    with pytest.raises(safefile.Broken):
        safefile.read_json(path)
    with pytest.raises(FileNotFoundError):
        safefile.read_json(str(tmp_path / "yok.json"))


def test_the_copy_is_renewed_at_most_once_an_hour(tmp_path, monkeypatch):
    path = str(tmp_path / "p.json")
    safefile.write_json(path, {"v": 1})
    safefile.write_json(path, {"v": 2})
    safefile.write_json(path, {"v": 3})
    assert json.load(open(path + ".bak", encoding="utf-8")) == {"v": 1}
    old = time.time() - safefile.BACKUP_EVERY - 5
    os.utime(path + ".bak", (old, old))
    safefile.write_json(path, {"v": 4})
    assert json.load(open(path + ".bak", encoding="utf-8")) == {"v": 3}


def test_the_stores_come_back_too(tmp_path):
    from app.config import Config
    from app.playlists import PlaylistStore
    cfg = Config(str(tmp_path / "settings.json"))
    cfg.set("theme", "Açık")
    cfg.set("theme", "Koyu")
    open(tmp_path / "settings.json", "w").write("{bozuk")
    assert Config(str(tmp_path / "settings.json")).get("theme") == "Açık"
    store = PlaylistStore(str(tmp_path / "playlists.json"))
    store.create("Gece")
    store.create("Sabah")
    (tmp_path / "playlists.json").write_bytes(b"\x00" * 100)
    assert "Gece" in PlaylistStore(str(tmp_path / "playlists.json")).lists


@pytest.mark.gui
def test_the_window_says_once_what_came_back(app):
    safefile.recovered.append("playlists.json")
    app._tell_recovered()
    assert "çalma listeleri" in app._notice
    app._notice = ""
    app._tell_recovered()
    assert app._notice == ""
