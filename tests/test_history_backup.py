"""The download history and its numbers, and backups of DISO's own data (no window)."""
import json
import os
import zipfile

import pytest

from app import backup, history
from app.models import Item


def done(url, title, size, seconds, kind="video", finished=1000.0, path=""):
    it = Item(url, kind=kind, title=title)
    it.total = size
    it.started = finished - seconds
    it.final_path = path
    return it


# ------------------------------------------------------------------------------ history
def test_a_finished_download_is_remembered_with_its_speed_and_site(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x" * 5000)
    h = history.History(str(tmp_path / "h.json"))
    [e] = h.record([done("https://www.youtube.com/watch?v=1", "Video", 999, 5, path=str(f))], now=1000.0)
    assert e["size"] == 5000 and e["seconds"] == 5 and e["site"] == "youtube.com" and e["kind"] == "video"
    again = history.History(str(tmp_path / "h.json"))
    assert again.entries == [e]


def test_the_newest_comes_first_and_the_list_has_a_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "MAX_ENTRIES", 3)
    h = history.History(str(tmp_path / "h.json"))
    for i in range(5):
        h.record([done(f"https://x.com/{i}", f"n{i}", 10, 1)], now=1000.0 + i)
    assert [e["title"] for e in h.entries] == ["n4", "n3", "n2"]


def test_the_numbers(tmp_path):
    h = history.History(str(tmp_path / "h.json"))
    now = 10 * 86400.0
    h.record([done("https://www.youtube.com/a", "A", 10_000_000, 10, finished=now - 86400),
              done("https://youtu.be/b", "B", 2_000_000, 1, kind="audio", finished=now - 86400),
              done("https://files.example.com/c.zip", "C", 50_000_000, 100, kind="file", finished=now - 86400)],
             now=now - 86400)
    next(e for e in h.entries if e["title"] == "C")["finished"] = now - 30 * 86400      # an old one
    s = h.stats(now=now)
    assert s["count"] == 3 and s["size"] == 62_000_000
    assert s["week_count"] == 2 and s["week_size"] == 12_000_000
    assert s["fastest"]["title"] == "B" and s["fastest_speed"] == 2_000_000
    assert s["average_speed"] == pytest.approx(62_000_000 / 111)
    assert s["biggest"]["title"] == "C" and s["sites"][0] == ("youtube.com", 2)
    assert s["kinds"] == {"Video": 1, "MP3": 1, "Dosya": 1}


def test_searching_and_clearing(tmp_path):
    h = history.History(str(tmp_path / "h.json"))
    h.record([done("https://www.youtube.com/a", "Barış Manço", 1, 1), done("https://x.com/b", "Tarkan", 1, 1)])
    assert [e["title"] for e in h.find("barış")] == ["Barış Manço"]
    assert [e["title"] for e in h.find("x.com")] == ["Tarkan"]
    h.clear()
    assert history.History(str(tmp_path / "h.json")).entries == []


def test_a_broken_history_file_is_an_empty_history(tmp_path):
    p = tmp_path / "h.json"
    p.write_text('{"entries": [{"title": 5}, {"title": "ok", "finished": 1, "size": -3, "kind": 7}]}')
    h = history.History(str(p))
    assert h.entries == [{"title": "ok", "finished": 1.0, "url": "", "kind": "", "path": "", "site": "", "size": 0,
                          "seconds": 0}]
    p.write_text("çöp")
    assert history.History(str(p)).entries == []


def test_an_empty_history_has_calm_numbers(tmp_path):
    s = history.History(str(tmp_path / "h.json")).stats()
    assert s["count"] == 0 and s["fastest"] is None and s["biggest"] is None and s["average_speed"] == 0


# ------------------------------------------------------------------------------ backup
def data_folder(tmp_path, name="veri"):
    d = tmp_path / name
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"theme": "Açık"}), encoding="utf-8")
    (d / "playlists.json").write_text(json.dumps({"playlists": {"Gece": []}}), encoding="utf-8")
    (d / "history.json").write_text(json.dumps({"entries": []}), encoding="utf-8")
    (d / "diso.log").write_text("not in a backup")
    return d


def test_a_backup_holds_the_data_files_only(tmp_path):
    d = data_folder(tmp_path)
    target = tmp_path / "yedek.disoyedek"
    assert backup.make_backup(str(target), str(d)) == ["settings.json", "playlists.json", "history.json"]
    with zipfile.ZipFile(target) as z:
        assert sorted(z.namelist()) == sorted(["diso-yedek.json", "settings.json", "playlists.json", "history.json"])


def test_restoring_waits_for_the_next_start_and_keeps_the_old_files(tmp_path):
    src = data_folder(tmp_path, "eski")
    target = tmp_path / "y.disoyedek"
    backup.make_backup(str(target), str(src))
    dest = tmp_path / "yeni"
    dest.mkdir()
    (dest / "settings.json").write_text(json.dumps({"theme": "Koyu"}), encoding="utf-8")
    content = backup.prepare_restore(str(target), str(dest))
    assert set(content["files"]) == {"settings.json", "playlists.json", "history.json"}
    assert json.loads((dest / "settings.json").read_text(encoding="utf-8")) == {"theme": "Koyu"}   # not yet
    assert sorted(backup.apply_pending(str(dest))) == ["history.json", "playlists.json", "settings.json"]
    assert json.loads((dest / "settings.json").read_text(encoding="utf-8")) == {"theme": "Açık"}
    assert json.loads((dest / "settings.json.before-restore").read_text(encoding="utf-8")) == {"theme": "Koyu"}
    assert not (dest / backup.PENDING).exists() and backup.apply_pending(str(dest)) == []


@pytest.mark.parametrize("make, message", [
    (lambda z: z.writestr("settings.json", "{}"), "DISO yedeği değil"),                              # no meta
    (lambda z: (z.writestr("diso-yedek.json", '{"app": "Başka"}'), z.writestr("settings.json", "{}")), "DISO yedeği değil"),
    (lambda z: (z.writestr("diso-yedek.json", '{"app": "DISO"}'), z.writestr("../../evil.json", "{}")), "tanımadığım"),
    (lambda z: (z.writestr("diso-yedek.json", '{"app": "DISO"}'), z.writestr("settings.json", "bozuk{")), "bozuk"),
    (lambda z: z.writestr("diso-yedek.json", '{"app": "DISO"}'), "boş"),
])
def test_a_wrong_or_dangerous_file_is_refused_and_changes_nothing(tmp_path, make, message):
    path = tmp_path / "x.disoyedek"
    with zipfile.ZipFile(path, "w") as z:
        make(z)
    dest = tmp_path / "veri"
    dest.mkdir()
    with pytest.raises(backup.BackupError, match=message):
        backup.prepare_restore(str(path), str(dest))
    assert not (dest / backup.PENDING).exists() and not (tmp_path / "evil.json").exists()


def test_not_a_zip_at_all_is_refused(tmp_path):
    p = tmp_path / "x.disoyedek"
    p.write_text("merhaba")
    with pytest.raises(backup.BackupError, match="bozuk"):
        backup.read_backup(str(p))


def test_nothing_to_back_up_is_said(tmp_path):
    (tmp_path / "bos").mkdir()
    with pytest.raises(backup.BackupError, match="Yedeklenecek"):
        backup.make_backup(str(tmp_path / "y.disoyedek"), str(tmp_path / "bos"))


def test_the_backup_name_carries_the_date():
    assert backup.default_name(0).startswith("DISO-yedek-19") and backup.default_name().endswith(".disoyedek")
