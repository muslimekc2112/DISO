import json
import os
import threading
import time

import pytest
import requests

from app.segmented_downloader import (LIMITER, DownloadError, DownloadStopped, FastDownloader,
                                      RateLimiter, probe)
from conftest import wait_for

MB = 1024 * 1024


def leftovers(dest):
    return [p for p in (dest + ".part", dest + ".part.json", dest + ".part.json.tmp") if os.path.exists(p)]


# --------------------------------------------------------------------------- probing
def test_probe_reports_size_range_support_and_name(server):
    name, data = server.file(12345, ".zip")
    pr = probe(server.url("f", name))
    assert pr.total == 12345 and pr.resumable and pr.filename == name


def test_probe_uses_the_file_name_the_server_announces(server):
    name, _ = server.file(100)
    assert probe(server.url("disp", name)).filename == "güzel dosya.zip"


def test_probe_on_a_server_without_range_support(server):
    name, data = server.file(5000)
    pr = probe(server.url("norange", name))
    assert not pr.resumable and pr.total == 5000


def test_probe_of_a_missing_file_raises(server):
    with pytest.raises(requests.HTTPError):
        probe(server.url("f", "does-not-exist.bin"))


# ------------------------------------------------------------------------ downloading
@pytest.mark.parametrize("connections", [1, 8, 32])
def test_download_is_byte_identical(server, tmp_path, connections):
    name, data = server.file(5 * MB + 123)
    dest = str(tmp_path / "out.bin")
    fd = FastDownloader(server.url("f", name), dest, connections)
    assert fd.run() == dest
    assert open(dest, "rb").read() == data
    assert fd.resumable and not leftovers(dest)


def test_tiny_file_with_more_connections_than_blocks(server, tmp_path):
    name, data = server.file(10)
    dest = str(tmp_path / "tiny.bin")
    FastDownloader(server.url("f", name), dest, 32).run()
    assert open(dest, "rb").read() == data


def test_server_without_range_support_falls_back_to_one_stream(server, tmp_path):
    name, data = server.file(2 * MB)
    dest = str(tmp_path / "out.bin")
    fd = FastDownloader(server.url("norange", name), dest, 16)
    fd.run()
    assert not fd.resumable
    assert open(dest, "rb").read() == data and not leftovers(dest)


def test_survives_connections_that_drop_in_the_middle(server, tmp_path):
    name, data = server.file(3 * MB)
    dest = str(tmp_path / "out.bin")
    FastDownloader(server.url("flaky", name), dest, 8).run()
    assert open(dest, "rb").read() == data
    assert server.state.flaky_counter >= 3  # the drops really happened


def test_adapts_when_the_server_allows_only_a_few_connections(server, tmp_path):
    name, data = server.file(4 * MB)
    dest = str(tmp_path / "out.bin")
    FastDownloader(server.url("limit", name), dest, 16).run()  # server answers 429 beyond 3
    assert open(dest, "rb").read() == data


def test_progress_callback_reports_bytes_speed_and_connections(server, tmp_path):
    name, data = server.file(3 * MB)
    LIMITER.set_rate(2 * MB)  # slow enough to be observed
    seen = []
    FastDownloader(server.url("f", name), str(tmp_path / "o.bin"), 4,
                   on_progress=lambda *a: seen.append(a)).run()
    assert seen[-1][0] == len(data)                      # last call: everything downloaded
    assert any(s[2] > 0 for s in seen)                   # a speed was measured
    assert any(s[4] > 0 for s in seen)                   # connections were reported


# ------------------------------------------------------------------ pause / resume / cancel
def run_in_thread(fd):
    box = {}

    def go():
        try:
            box["result"] = fd.run()
        except BaseException as e:  # noqa: BLE001 - the test inspects it
            box["error"] = e

    t = threading.Thread(target=go, daemon=True)
    t.start()
    return t, box


def test_pause_keeps_progress_and_resume_downloads_only_the_rest(server, tmp_path):
    name, data = server.file(6 * MB)
    dest = str(tmp_path / "out.bin")
    LIMITER.set_rate(1 * MB)
    fd = FastDownloader(server.url("f", name), dest, 4)
    t, box = run_in_thread(fd)
    assert wait_for(lambda: fd.downloaded > 1.5 * MB, 20)
    fd.stop("pause")
    t.join(10)
    assert isinstance(box.get("error"), DownloadStopped) and box["error"].reason == "pause"
    assert os.path.exists(dest + ".part") and os.path.exists(dest + ".part.json")
    meta = json.load(open(dest + ".part.json"))
    assert meta["done"], "finished blocks must be remembered"

    sent_before = server.sent(name)
    LIMITER.set_rate(0)
    FastDownloader(server.url("f", name), dest, 4).run()
    assert open(dest, "rb").read() == data
    # a real resume: far less than the whole file was requested the second time
    assert server.sent(name) - sent_before < len(data) - 0.5 * MB
    assert not leftovers(dest)


def test_resume_survives_a_new_process_reading_the_meta_file(server, tmp_path):
    """Same as above but the resuming downloader is a fresh object that only has the files."""
    name, data = server.file(4 * MB)
    dest = str(tmp_path / "out.bin")
    LIMITER.set_rate(1 * MB)
    fd = FastDownloader(server.url("f", name), dest, 4)
    t, box = run_in_thread(fd)
    wait_for(lambda: fd.downloaded > 1 * MB, 20)
    fd.stop("pause")
    t.join(10)
    LIMITER.set_rate(0)
    fresh = FastDownloader(server.url("f", name), dest, 16)  # different connection count
    fresh.run()
    assert open(dest, "rb").read() == data


def test_cancel_removes_every_temporary_file(server, tmp_path):
    name, _ = server.file(5 * MB)
    dest = str(tmp_path / "out.bin")
    LIMITER.set_rate(1 * MB)
    fd = FastDownloader(server.url("f", name), dest, 4)
    t, box = run_in_thread(fd)
    wait_for(lambda: fd.downloaded > 0.5 * MB, 20)
    fd.stop("cancel")
    t.join(10)
    assert isinstance(box.get("error"), DownloadStopped) and box["error"].reason == "cancel"
    assert not leftovers(dest) and not os.path.exists(dest)


def test_stop_before_start_raises_immediately(server, tmp_path):
    name, _ = server.file(1000)
    fd = FastDownloader(server.url("f", name), str(tmp_path / "o.bin"), 4)
    fd.stop("pause")
    with pytest.raises(DownloadStopped):
        fd.run()


def test_corrupt_meta_file_means_a_clean_restart_not_a_crash(server, tmp_path):
    name, data = server.file(2 * MB)
    dest = str(tmp_path / "out.bin")
    with open(dest + ".part", "wb") as f:
        f.truncate(len(data))
    open(dest + ".part.json", "w").write("{broken")
    FastDownloader(server.url("f", name), dest, 4).run()
    assert open(dest, "rb").read() == data


def test_meta_from_a_different_file_size_is_not_reused(server, tmp_path):
    name, data = server.file(2 * MB)
    dest = str(tmp_path / "out.bin")
    with open(dest + ".part", "wb") as f:
        f.truncate(len(data))
    json.dump({"total": len(data) + 1, "block": 262144, "done": [0, 1, 2]}, open(dest + ".part.json", "w"))
    FastDownloader(server.url("f", name), dest, 4).run()
    assert open(dest, "rb").read() == data   # blocks 0-2 were NOT trusted


# ------------------------------------------------------------------------ failing fast
def test_missing_file_fails_quickly(server, tmp_path):
    t0 = time.time()
    with pytest.raises(requests.HTTPError):
        FastDownloader(server.url("f", "nope.bin"), str(tmp_path / "o.bin"), 4).run()
    assert time.time() - t0 < 5


def test_server_that_ignores_range_mid_download_fails_fast_not_after_many_retries(server, tmp_path):
    name, _ = server.file(3 * MB)
    t0 = time.time()
    with pytest.raises(DownloadError, match="Range"):
        FastDownloader(server.url("noblock", name), str(tmp_path / "o.bin"), 4).run()
    assert time.time() - t0 < 5


def test_unreachable_server_gives_an_error(tmp_path):
    with pytest.raises(requests.RequestException):
        FastDownloader("http://127.0.0.1:9/x.bin", str(tmp_path / "o.bin"), 2).run()


# ------------------------------------------------------------------------- speed limit
def test_rate_limiter_is_off_by_default_and_costs_nothing():
    lim = RateLimiter()
    t0 = time.time()
    lim.consume(10 * MB)
    assert time.time() - t0 < 0.1


def test_rate_limiter_makes_the_caller_wait_in_proportion():
    lim = RateLimiter()
    lim.set_rate(4 * MB)
    t0 = time.time()
    for _ in range(4):
        lim.consume(MB)          # 4 MB at 4 MB/s
    assert 0.7 < time.time() - t0 < 2.0


def test_rate_limiter_wait_is_interrupted_by_stop():
    lim = RateLimiter()
    lim.set_rate(1024)           # 1 KB/s: a 1 MB consume would take ~17 minutes
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    t0 = time.time()
    lim.consume(MB, stop)
    assert time.time() - t0 < 3


def test_limit_applies_to_downloads(server, tmp_path):
    name, _ = server.file(3 * MB)
    LIMITER.set_rate(1 * MB)
    t0 = time.time()
    FastDownloader(server.url("f", name), str(tmp_path / "o.bin"), 8).run()
    assert time.time() - t0 > 1.8


def test_downloads_started_by_the_app_itself_ignore_the_user_limit(server, tmp_path):
    name, _ = server.file(2 * MB)
    LIMITER.set_rate(50 * 1024)  # 50 KB/s would take 40 s
    t0 = time.time()
    FastDownloader(server.url("f", name), str(tmp_path / "o.bin"), 8, limited=False).run()
    assert time.time() - t0 < 5


def test_limit_can_be_lifted_while_a_download_runs(server, tmp_path):
    name, data = server.file(4 * MB)
    dest = str(tmp_path / "o.bin")
    LIMITER.set_rate(512 * 1024)
    fd = FastDownloader(server.url("f", name), dest, 4)
    t, box = run_in_thread(fd)
    time.sleep(0.5)
    LIMITER.set_rate(0)
    t.join(10)
    assert box.get("result") == dest and open(dest, "rb").read() == data
