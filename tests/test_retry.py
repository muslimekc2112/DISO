"""Automatic retry after connection problems (the WAITING state)."""
import json
import os

import pytest
import requests

from app import manager as manager_module
from app.manager import DownloadManager
from app.models import CANCELLED, DONE, ERROR, PAUSED, WAITING, Item, Settings
from app.segmented_downloader import DownloadError, TransientError, is_transient
from conftest import wait_for


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return str(d)


@pytest.fixture
def settings(folder):
    return Settings(kind="file", folder=folder, connections=4)


@pytest.fixture
def fast_retries(monkeypatch):
    monkeypatch.setattr(manager_module, "RETRY_DELAYS", (0.2, 0.2, 0.2, 0.2, 0.2))


@pytest.fixture
def manager(tmp_path, fast_retries):
    m = DownloadManager(max_parallel=3, store_path=str(tmp_path / "d.json"), max_retries=3)
    yield m
    for it in list(m.items):
        m.remove(it)


def states(m):
    return [i.state for i in m.items]


# ------------------------------------------------------------------ what is transient
def http_error(code):
    r = requests.Response()
    r.status_code = code
    return requests.HTTPError(response=r)


@pytest.mark.parametrize("error,expected", [
    (requests.ConnectionError("x"), True),
    (requests.Timeout("x"), True),
    (requests.exceptions.ChunkedEncodingError("x"), True),
    (ConnectionResetError(), True),
    (TimeoutError(), True),
    (http_error(503), True), (http_error(502), True), (http_error(429), True), (http_error(408), True),
    (http_error(404), False), (http_error(403), False), (http_error(401), False),
    (DownloadError("connection failed", network=True), True),
    (DownloadError("Sunucu parçalı indirmeyi desteklemiyor"), False),
    (TransientError("anything"), True),
    (RuntimeError("[generic] Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>"), True),
    (RuntimeError("ERROR: HTTP Error 503: Service Unavailable"), True),
    (RuntimeError("Read timed out"), True),
    (RuntimeError("ERROR: Unsupported URL: http://x"), False),
    (RuntimeError("HTTP Error 404: Not Found"), False),
    (ValueError("nothing to do with the network"), False),
])
def test_which_errors_are_worth_retrying(error, expected):
    assert is_transient(error) is expected


# ---------------------------------------------------------------------- the retry flow
def test_a_download_that_hits_a_network_problem_recovers_by_itself(manager, server, settings):
    name, data = server.file(300_000)
    server.state.fail_requests = 2                       # the first two requests get no answer
    manager.add_url(server.url("f", name), settings)
    item = manager.items[0]
    assert wait_for(lambda: item.state == WAITING, 10)
    assert "tekrar denenecek" in item.message and "1/3" in item.message
    assert wait_for(lambda: item.state == DONE, 15)
    assert open(item.final_path, "rb").read() == data
    assert item.retries == 0                             # reset after the success


def test_after_the_allowed_retries_it_becomes_an_error(manager, server, settings):
    name, _ = server.file(1000)
    server.state.fail_requests = 100
    manager.add_url(server.url("f", name), settings)
    item = manager.items[0]
    assert wait_for(lambda: item.state == ERROR, 20)
    assert item.retries == 3                             # tried 3 times, then gave up
    assert manager.events.get(timeout=2)[0] == "error"   # only now the user is told


def test_a_permanent_error_is_not_retried(manager, server, settings):
    manager.add_url(server.url("f", "missing.bin"), settings)
    item = manager.items[0]
    assert wait_for(lambda: item.state == ERROR, 10)
    assert item.retries == 0


def test_retrying_can_be_switched_off(manager, server, settings):
    manager.set_max_retries(0)
    name, _ = server.file(1000)
    server.state.fail_requests = 5
    manager.add_url(server.url("f", name), settings)
    assert wait_for(lambda: manager.items[0].state == ERROR, 10)
    assert manager.items[0].retries == 0


def test_every_retry_announces_itself_in_the_message(manager, server, settings, monkeypatch):
    monkeypatch.setattr(manager_module, "RETRY_DELAYS", (0.3, 0.3, 0.3))
    name, _ = server.file(1000)
    server.state.fail_requests = 100
    manager.add_url(server.url("f", name), settings)
    item = manager.items[0]
    seen = set()

    def watch():
        if item.state == WAITING:
            seen.add(item.message)
        return item.state == ERROR

    assert wait_for(watch, 20, interval=0.02)
    assert any("1/3" in m for m in seen) and any("3/3" in m for m in seen)


def test_pausing_a_waiting_download_stops_the_countdown(manager, server, settings, monkeypatch):
    monkeypatch.setattr(manager_module, "RETRY_DELAYS", (30,))     # would wait 30 s
    name, _ = server.file(1000)
    server.state.fail_requests = 100
    manager.add_url(server.url("f", name), settings)
    item = manager.items[0]
    assert wait_for(lambda: item.state == WAITING, 10)
    timer = item._timer
    manager.pause(item)
    assert item.state == PAUSED and item._timer is None
    assert wait_for(lambda: not timer.is_alive(), 3)
    server.state.fail_requests = 0
    manager.resume(item)                                 # the user continues by hand
    assert wait_for(lambda: item.state == DONE, 15)


def test_cancelling_and_removing_a_waiting_download_clean_up(manager, server, settings, folder, monkeypatch):
    monkeypatch.setattr(manager_module, "RETRY_DELAYS", (30,))
    server.state.fail_requests = 100
    for _ in range(2):
        name, _ = server.file(1000)
        manager.add_url(server.url("f", name), settings)
    assert wait_for(lambda: states(manager) == [WAITING, WAITING], 10)
    first, second = manager.items
    manager.cancel(first)
    assert first.state == CANCELLED and first._timer is None
    manager.remove(second)
    assert second._timer is None and manager.items == [first]
    assert os.listdir(folder) == []                      # no leftover placeholder files


def test_a_waiting_download_does_not_survive_a_restart_as_waiting(manager, server, settings, monkeypatch):
    monkeypatch.setattr(manager_module, "RETRY_DELAYS", (30,))
    server.state.fail_requests = 100
    name, _ = server.file(1000)
    manager.add_url(server.url("f", name), settings)
    assert wait_for(lambda: manager.items[0].state == WAITING, 10)
    manager.shutdown()
    assert manager.items[0].state == PAUSED and manager.items[0]._timer is None
    saved = json.load(open(manager.store_path, encoding="utf-8"))
    assert saved["items"][0]["state"] == PAUSED
    assert Item.from_dict({"url": "x", "state": WAITING}).state == PAUSED


def test_a_download_that_keeps_losing_connections_still_finishes(manager, server, settings):
    name, data = server.file(3 * 1024 * 1024)
    manager.add_url(server.url("flaky", name), settings)         # drops connections mid-block
    item = manager.items[0]
    assert wait_for(lambda: item.state == DONE, 30)
    assert open(item.final_path, "rb").read() == data


def test_the_connection_problem_of_a_video_page_is_retried_too(manager, folder, monkeypatch):
    calls = []

    def resolve(url, kind, quality, cookies=None):
        calls.append(1)
        raise Exception("[generic] Unable to download webpage: getaddrinfo failed")

    monkeypatch.setattr(manager_module.ve, "resolve", resolve)
    manager.add_url("http://page.example/v", Settings(kind="video", folder=folder))
    item = manager.items[0]
    assert wait_for(lambda: item.state == ERROR, 20)
    assert len(calls) == 4                               # first try + 3 retries
