import json
import os
import time

import pytest

from app import jobs
from app.manager import DownloadManager, url_key
from app.models import (CANCELLED, DONE, DOWNLOADING, ERROR, PAUSED, QUEUED, Item, Settings)
from app.segmented_downloader import LIMITER
from conftest import wait_for

MB = 1024 * 1024


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return str(d)


@pytest.fixture
def settings(folder):
    return Settings(kind="file", folder=folder, connections=4)


@pytest.fixture
def manager(tmp_path):
    m = DownloadManager(max_parallel=3, store_path=str(tmp_path / "downloads.json"))
    yield m
    for it in list(m.items):
        m.remove(it)


def states(m):
    return sorted(i.state for i in m.items)


# ------------------------------------------------------------------------ basic flow
def test_a_download_runs_to_the_end_and_announces_it(manager, server, settings, folder):
    name, data = server.file(300_000)
    assert manager.add_url(server.url("f", name), settings)
    assert wait_for(lambda: states(manager) == [DONE])
    item = manager.items[0]
    assert open(item.final_path, "rb").read() == data
    kind, evented = manager.events.get(timeout=2)
    assert kind == "done" and evented is item
    assert item.fraction == 1.0


def test_a_failing_download_becomes_an_error_item_and_an_event(manager, server, settings):
    manager.add_url(server.url("f", "nothing-here.bin"), settings)
    assert wait_for(lambda: states(manager) == [ERROR])
    assert manager.items[0].error
    assert manager.events.get(timeout=2)[0] == "error"


def test_two_downloads_of_the_same_file_name_do_not_overwrite_each_other(manager, server, settings, folder):
    name, data = server.file(50_000)
    manager.add_url(server.url("f", name), settings)
    manager.add_url(server.url("norange", name), settings)
    assert wait_for(lambda: states(manager) == [DONE, DONE])
    assert sorted(os.listdir(folder)) == sorted([name, name.replace(".bin", " (1).bin")])


# ----------------------------------------------------------------------- duplicates
def test_url_key_ignores_case_fragment_and_trailing_slash_but_not_the_query():
    assert url_key("HTTP://Example.com/a/b/#top") == url_key("http://example.com/a/b")
    assert url_key("www.example.com/a") == url_key("https://www.example.com/a")
    assert url_key("http://e.com/a?x=1") != url_key("http://e.com/a?x=2")


def test_duplicate_links_are_skipped_when_asked(manager, server, settings):
    name, _ = server.file(100)
    url = server.url("f", name)
    assert manager.add_url(url, settings, skip_duplicates=True) is True
    assert manager.add_url(url + "#frag", settings, skip_duplicates=True) is False
    assert manager.add_url(url + "/", settings, skip_duplicates=True) is False
    assert len(manager.items) == 1
    assert manager.find_duplicate(url) is manager.items[0]


def test_duplicates_are_allowed_when_not_asked_to_skip(manager, server, settings):
    name, _ = server.file(100)
    assert manager.add_url(server.url("f", name), settings)
    assert manager.add_url(server.url("f", name), settings, skip_duplicates=False)
    assert len(manager.items) == 2


def test_a_cancelled_download_does_not_block_adding_the_link_again(manager, server, settings):
    name, _ = server.file(5 * MB)
    LIMITER.set_rate(256 * 1024)
    url = server.url("f", name)
    manager.add_url(url, settings)
    wait_for(lambda: manager.items[0].state == DOWNLOADING)
    manager.cancel(manager.items[0])
    assert wait_for(lambda: manager.items[0].state == CANCELLED)
    assert manager.add_url(url, settings, skip_duplicates=True) is True


# ----------------------------------------------------------- parallel limit (live change)
def test_only_max_parallel_downloads_run_and_the_limit_can_change_live(manager, server, settings):
    LIMITER.set_rate(1 * MB)
    manager.set_max_parallel(1)
    for _ in range(4):
        name, _ = server.file(8 * MB)
        manager.add_url(server.url("f", name), settings)
    assert wait_for(lambda: states(manager).count(DOWNLOADING) == 1)
    assert states(manager).count(QUEUED) == 3
    manager.set_max_parallel(3)                     # raising the limit starts the waiting ones
    assert wait_for(lambda: states(manager).count(DOWNLOADING) == 3)
    assert states(manager).count(QUEUED) == 1
    manager.set_max_parallel(1)                     # lowering it never kills a running download
    time.sleep(0.5)
    assert states(manager).count(DOWNLOADING) == 3
    manager.set_max_parallel(0)                     # nonsense is clamped to 1, not a deadlock
    assert manager.max_parallel == 1


def test_queue_order_is_first_come_first_served(manager, server, settings):
    LIMITER.set_rate(2 * MB)
    manager.set_max_parallel(1)
    for _ in range(3):
        name, _ = server.file(6 * MB)
        manager.add_url(server.url("f", name), settings)
    assert wait_for(lambda: manager.items[0].state == DOWNLOADING)
    assert [i.state for i in manager.items[1:]] == [QUEUED, QUEUED]
    manager.cancel(manager.items[0])
    assert wait_for(lambda: manager.items[1].state == DOWNLOADING)   # second item is next
    assert manager.items[2].state == QUEUED


def test_pausing_a_queued_item_removes_it_from_the_waiting_line(manager, server, settings):
    LIMITER.set_rate(1 * MB)
    manager.set_max_parallel(1)
    for _ in range(2):
        name, _ = server.file(8 * MB)
        manager.add_url(server.url("f", name), settings)
    wait_for(lambda: manager.items[0].state == DOWNLOADING)
    manager.pause(manager.items[1])
    assert manager.items[1].state == PAUSED
    manager.cancel(manager.items[0])
    wait_for(lambda: manager.items[0].state == CANCELLED)
    assert manager.items[1].state == PAUSED         # the dispatcher did not start it


# --------------------------------------------------------------- pause / resume / remove
def test_pause_then_resume_finishes_the_file(manager, server, settings):
    name, data = server.file(6 * MB)
    LIMITER.set_rate(1 * MB)
    manager.add_url(server.url("f", name), settings)
    item = manager.items[0]
    assert wait_for(lambda: item.state == DOWNLOADING and item.done > 1 * MB, 20)
    manager.pause(item)
    assert wait_for(lambda: item.state == PAUSED)
    assert os.path.exists(item.dest + ".part")
    LIMITER.set_rate(0)
    manager.resume(item)
    assert wait_for(lambda: item.state == DONE, 20)
    assert open(item.final_path, "rb").read() == data


def test_cancel_deletes_temporary_files(manager, server, settings, folder):
    name, _ = server.file(6 * MB)
    LIMITER.set_rate(1 * MB)
    manager.add_url(server.url("f", name), settings)
    item = manager.items[0]
    wait_for(lambda: item.state == DOWNLOADING and item.done > 0.5 * MB, 20)
    manager.cancel(item)
    assert wait_for(lambda: item.state == CANCELLED)
    assert os.listdir(folder) == []


def test_removing_a_running_download_stops_it_and_cleans_up(manager, server, settings, folder):
    name, _ = server.file(6 * MB)
    LIMITER.set_rate(1 * MB)
    manager.add_url(server.url("f", name), settings)
    item = manager.items[0]
    wait_for(lambda: item.state == DOWNLOADING and item.done > 0.5 * MB, 20)
    manager.remove(item)
    assert manager.items == []
    assert wait_for(lambda: os.listdir(folder) == [])


def test_resume_all_and_pause_all(manager, server, settings):
    LIMITER.set_rate(1 * MB)
    for _ in range(2):
        name, _ = server.file(8 * MB)
        manager.add_url(server.url("f", name), settings)
    wait_for(lambda: states(manager) == [DOWNLOADING, DOWNLOADING])
    manager.pause_all()
    assert wait_for(lambda: states(manager) == [PAUSED, PAUSED])
    manager.resume_all()
    assert wait_for(lambda: states(manager) == [DOWNLOADING, DOWNLOADING])


def test_clear_finished_keeps_everything_else(manager, server, settings):
    name, _ = server.file(1000)
    manager.add_url(server.url("f", name), settings)
    wait_for(lambda: states(manager) == [DONE])
    manager.add_url(server.url("f", "missing.bin"), settings)
    wait_for(lambda: states(manager) == [DONE, ERROR])
    manager.clear_finished()
    assert states(manager) == [ERROR]


# --------------------------------------------------------------- persistence / shutdown
def test_the_list_is_restored_after_a_restart_with_running_items_paused(tmp_path, server, settings):
    store = str(tmp_path / "d.json")
    m1 = DownloadManager(store_path=store)
    name, _ = server.file(500)
    m1.add_url(server.url("f", name), settings)
    wait_for(lambda: m1.items[0].state == DONE)
    LIMITER.set_rate(1 * MB)
    big, _ = server.file(8 * MB)
    m1.add_url(server.url("f", big), settings)
    wait_for(lambda: m1.items[1].state == DOWNLOADING)
    m1.save()
    m2 = DownloadManager(store_path=store)              # "the app was killed and started again"
    assert [i.state for i in m2.items] == [DONE, PAUSED]
    assert m2.items[0].fraction == 1.0
    m1.remove(m1.items[0])
    for it in list(m1.items):
        m1.remove(it)


def test_a_damaged_download_list_is_ignored(tmp_path):
    store = tmp_path / "d.json"
    store.write_text("{oops", encoding="utf-8")
    assert DownloadManager(store_path=str(store)).items == []


def test_shutdown_pauses_everything_without_blocking_and_saves(manager, server, settings, tmp_path):
    LIMITER.set_rate(1 * MB)
    for _ in range(2):
        name, _ = server.file(8 * MB)
        manager.add_url(server.url("f", name), settings)
    wait_for(lambda: states(manager) == [DOWNLOADING, DOWNLOADING])
    t0 = time.time()
    manager.shutdown()
    assert time.time() - t0 < 0.5                        # returns at once
    assert wait_for(lambda: not manager.busy(), 10)
    assert states(manager) == [PAUSED, PAUSED]
    saved = json.load(open(manager.store_path, encoding="utf-8"))
    assert [i["state"] for i in saved["items"]] == [PAUSED, PAUSED]


def test_only_the_last_200_items_are_kept_on_load(tmp_path):
    store = tmp_path / "d.json"
    items = [Item(f"http://x/{i}", title=str(i)).to_dict() for i in range(250)]
    store.write_text(json.dumps({"items": items}), encoding="utf-8")
    m = DownloadManager(store_path=str(store))
    assert len(m.items) == 200 and m.items[0].title == "50"


# ----------------------------------------------------------------------------- jobs
def test_auto_mode_tells_files_from_video_pages(server):
    page = server.add(b"<html></html>", ".html", "text/html")
    binary, _ = server.file(100, ".zip")
    manifest = server.add(b"#EXTM3U", ".m3u8", "application/vnd.apple.mpegurl")
    for name, expected in ((page, "video"), (binary, "file"), (manifest, "video")):
        item = Item(server.url("f", name), kind="auto")
        jobs.classify(item)
        assert item.kind == expected, name


def test_auto_mode_treats_an_unreachable_page_as_a_video_site():
    item = Item("http://127.0.0.1:9/page", kind="auto")
    jobs.classify(item)
    assert item.kind == "video"


# ------------------------------------------------------------- redownload / delete with file
def test_redownload_fetches_the_file_again_from_the_start(manager, server, settings, folder):
    name, data = server.file(100_000)
    manager.add_url(server.url("f", name), settings)
    assert wait_for(lambda: states(manager) == [DONE])
    item = manager.items[0]
    first = item.final_path
    manager.redownload(item)
    assert wait_for(lambda: item.state == DONE and item.final_path and item.final_path != first)
    assert open(item.final_path, "rb").read() == data
    assert sorted(os.listdir(folder)) == sorted([name, name.replace(".bin", " (1).bin")])  # old copy kept
    assert server.hits(name) >= 4                                                          # fetched twice


def test_redownload_throws_the_partial_file_away(manager, server, settings, folder):
    name, data = server.file(6 * MB)
    LIMITER.set_rate(1 * MB)
    manager.add_url(server.url("f", name), settings)
    item = manager.items[0]
    wait_for(lambda: item.state == DOWNLOADING and item.done > 1 * MB, 20)
    manager.pause(item)
    assert wait_for(lambda: item.state == PAUSED)
    partial = item.dest + ".part"
    assert os.path.exists(partial)
    LIMITER.set_rate(0)
    sent = server.sent(name)
    manager.redownload(item)
    assert wait_for(lambda: item.state == DONE, 20)
    assert server.sent(name) - sent >= len(data)          # the whole file again, no resume
    assert open(item.final_path, "rb").read() == data


def test_a_running_download_is_not_restarted(manager, server, settings):
    name, _ = server.file(6 * MB)
    LIMITER.set_rate(1 * MB)
    manager.add_url(server.url("f", name), settings)
    item = manager.items[0]
    wait_for(lambda: item.state == DOWNLOADING and item.done > 0.5 * MB, 20)
    dest = item.dest
    manager.redownload(item)
    assert item.state == DOWNLOADING and item.dest == dest


def test_a_failed_download_can_be_redownloaded(manager, server, settings):
    manager.add_url(server.url("f", "missing.bin"), settings)
    assert wait_for(lambda: states(manager) == [ERROR])
    hits = server.hits("missing.bin")
    manager.redownload(manager.items[0])
    assert wait_for(lambda: server.hits("missing.bin") > hits)
    assert wait_for(lambda: states(manager) == [ERROR])


def test_delete_with_file_removes_the_item_and_the_file(manager, server, settings, folder):
    name, _ = server.file(5000)
    manager.add_url(server.url("f", name), settings)
    assert wait_for(lambda: states(manager) == [DONE])
    path = manager.items[0].final_path
    assert os.path.exists(path)
    manager.delete_with_file(manager.items[0])
    assert manager.items == [] and not os.path.exists(path) and os.listdir(folder) == []


def test_delete_with_file_copes_with_a_file_that_is_already_gone(manager, server, settings):
    name, _ = server.file(5000)
    manager.add_url(server.url("f", name), settings)
    assert wait_for(lambda: states(manager) == [DONE])
    os.remove(manager.items[0].final_path)
    manager.delete_with_file(manager.items[0])
    assert manager.items == []
