"""Proxy, browser-session headers (Referer / Cookie), type folders and the scheduler gate."""
import os
import time

import pytest
import requests

from app import jobs, utils
from app.manager import DownloadManager
from app.models import DONE, ERROR, QUEUED, Item, Settings
from app.segmented_downloader import (FastDownloader, get_proxies, get_proxy, probe,
                                      set_proxy)
from conftest import wait_for

MB = 1024 * 1024


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return str(d)


@pytest.fixture
def manager(tmp_path):
    m = DownloadManager(max_parallel=3, store_path=str(tmp_path / "d.json"))
    yield m
    for it in list(m.items):
        m.remove(it)


# ------------------------------------------------------------------------------ proxy
def test_proxy_setting_is_validated():
    set_proxy("http://127.0.0.1:8080")
    assert get_proxy() == "http://127.0.0.1:8080"
    assert get_proxies() == {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}
    for good in ("https://p:1", "socks5://p:1080", "socks5h://u:pw@p:1080", "socks4://p:1"):
        set_proxy(good)
    for bad in ("p:8080", "ftp://p:21", "http://", "not a proxy", "javascript:alert(1)"):
        with pytest.raises(ValueError):
            set_proxy(bad)
    set_proxy("")
    assert get_proxy() == "" and get_proxies() is None


def test_probe_and_download_go_through_the_proxy(server, proxy, tmp_path):
    name, data = server.file(2 * MB)
    set_proxy(proxy.url)
    pr = probe(server.url("f", name))
    assert pr.total == len(data) and pr.resumable
    dest = str(tmp_path / "o.bin")
    FastDownloader(server.url("f", name), dest, 4).run()
    assert open(dest, "rb").read() == data
    assert len(proxy.hits) > 4                             # the probe and every block


def test_without_the_setting_the_proxy_is_not_used(server, proxy, tmp_path):
    name, _ = server.file(1000)
    FastDownloader(server.url("f", name), str(tmp_path / "o.bin"), 2).run()
    assert proxy.hits == []


def test_a_dead_proxy_is_a_connection_error(server, tmp_path):
    name, _ = server.file(1000)
    set_proxy("http://127.0.0.1:9")
    with pytest.raises(requests.RequestException):
        probe(server.url("f", name))


def test_the_manager_downloads_through_the_proxy_and_yt_dlp_gets_the_setting(server, proxy, folder, manager):
    from app import video_engine as ve
    set_proxy(proxy.url)
    assert ve.base_opts()["proxy"] == proxy.url
    set_proxy("")
    assert "proxy" not in ve.base_opts()
    set_proxy(proxy.url)
    name, data = server.file(300_000)
    manager.add_url(server.url("f", name), Settings(kind="file", folder=folder))
    assert wait_for(lambda: [i.state for i in manager.items] == [DONE], 15)
    assert proxy.hits


# ---------------------------------------------------------------- session headers
def test_item_builds_headers_from_what_the_browser_sent():
    it = Item("http://x", referer="http://site.example/page", user_agent="TestUA/1", cookie_header="sid=1")
    assert it.request_headers() == {"Referer": "http://site.example/page", "User-Agent": "TestUA/1",
                                    "Cookie": "sid=1"}
    assert Item("http://x").request_headers() == {}


def test_cookies_are_never_written_to_disk_but_the_referer_is(tmp_path):
    it = Item("http://x", referer="http://site.example/page", cookie_header="sid=secret")
    d = it.to_dict()
    assert d["referer"] == "http://site.example/page"
    assert "secret" not in str(d) and "cookie_header" not in d


def test_a_site_that_wants_referer_and_cookie_works_when_they_are_passed_on(server, manager, folder):
    name, data = server.file(200_000)
    s = Settings(kind="file", folder=folder)
    manager.add_url(server.url("auth", name), s, extra={
        "referer": "http://site.example/page", "cookie": "sid=1; other=2", "user_agent": "TestUA/1"})
    assert wait_for(lambda: [i.state for i in manager.items] == [DONE], 15)
    assert open(manager.items[0].final_path, "rb").read() == data
    seen = server.state.seen[name]
    assert seen["referer"] == "http://site.example/page" and seen["user-agent"] == "TestUA/1"
    assert "sid=1" in seen["cookie"]


def test_the_same_site_refuses_without_them(server, manager, folder):
    name, _ = server.file(1000)
    manager.add_url(server.url("auth", name), Settings(kind="file", folder=folder))
    assert wait_for(lambda: [i.state for i in manager.items] == [ERROR], 10)
    assert "403" in manager.items[0].error


def test_classify_uses_the_session_headers_too(server):
    name, _ = server.file(100)
    anonymous = Item(server.url("auth", name), kind="auto")
    jobs.classify(anonymous)
    assert anonymous.kind == "video"                       # probe failed: looks like a page
    with_session = Item(server.url("auth", name), kind="auto", referer="http://site.example/page",
                        cookie_header="sid=1")
    jobs.classify(with_session)
    assert with_session.kind == "file"


def test_the_referer_survives_a_restart_so_a_resume_can_use_it(tmp_path):
    it = Item("http://x", referer="http://site.example/page")
    assert Item.from_dict(it.to_dict()).referer == "http://site.example/page"


# ------------------------------------------------------------------------ type folders
@pytest.mark.parametrize("name,expected", [
    ("movie.MP4", "Video"), ("clip.mkv", "Video"), ("song.mp3", "Müzik"), ("a.flac", "Müzik"),
    ("pack.zip", "Arşiv"), ("disk.iso", "Arşiv"), ("a.7z", "Arşiv"), ("doc.pdf", "Belge"),
    ("sheet.xlsx", "Belge"), ("setup.exe", "Program"), ("app.apk", "Program"), ("pic.jpg", "Resim"),
    ("pic.WEBP", "Resim"), ("data.bin", "Diğer"), ("noextension", "Diğer"), ("", "Diğer"),
])
def test_category_for(name, expected):
    assert utils.category_for(name) == expected


def test_media_folder():
    assert utils.media_folder("D:/dl", "video", False) == "D:/dl"
    assert utils.media_folder("D:/dl", "video", True) == os.path.join("D:/dl", "Video")
    assert utils.media_folder("D:/dl", "audio", True) == os.path.join("D:/dl", "Müzik")


def test_files_go_into_type_sub_folders_when_asked(server, manager, folder):
    zname, zdata = server.file(5000, ".zip")
    vname, vdata = server.file(5000, ".mp4")
    oname, odata = server.file(5000, ".xyz")
    s = Settings(kind="file", folder=folder, sort_folders=True)
    for name in (zname, vname, oname):
        manager.add_url(server.url("f", name), s)
    assert wait_for(lambda: all(i.state == DONE for i in manager.items), 15)
    assert sorted(os.listdir(folder)) == ["Arşiv", "Diğer", "Video"]
    assert open(os.path.join(folder, "Arşiv", zname), "rb").read() == zdata
    assert open(os.path.join(folder, "Video", vname), "rb").read() == vdata
    assert open(os.path.join(folder, "Diğer", oname), "rb").read() == odata


def test_without_the_option_everything_stays_in_the_chosen_folder(server, manager, folder):
    name, _ = server.file(5000, ".zip")
    manager.add_url(server.url("f", name), Settings(kind="file", folder=folder))
    assert wait_for(lambda: manager.items[0].state == DONE, 15)
    assert os.listdir(folder) == [name]


def test_two_files_with_the_same_name_in_a_type_folder_get_numbers(server, manager, folder):
    name, _ = server.file(2000, ".zip")
    s = Settings(kind="file", folder=folder, sort_folders=True)
    manager.add_url(server.url("f", name), s)
    manager.add_url(server.url("norange", name), s)
    assert wait_for(lambda: all(i.state == DONE for i in manager.items), 15)
    assert sorted(os.listdir(os.path.join(folder, "Arşiv"))) == sorted([name, name.replace(".zip", " (1).zip")])


def test_the_type_folder_is_remembered_for_resume(server, manager, folder):
    name, _ = server.file(5000, ".zip")
    manager.add_url(server.url("f", name), Settings(kind="file", folder=folder, sort_folders=True))
    assert wait_for(lambda: manager.items[0].state == DONE, 15)
    assert manager.items[0].sort_folders is True
    assert Item.from_dict(manager.items[0].to_dict()).sort_folders is True


# ------------------------------------------------------------------- scheduler gate
def test_a_closed_gate_holds_queued_downloads_and_opening_it_starts_them(server, manager, folder):
    name, data = server.file(5000)
    manager.set_gate(False)
    manager.add_url(server.url("f", name), Settings(kind="file", folder=folder))
    time.sleep(1.2)
    assert manager.items[0].state == QUEUED and manager.gate_open is False
    manager.set_gate(True)
    assert wait_for(lambda: manager.items[0].state == DONE, 10)


def test_a_closed_gate_does_not_stop_a_running_download(server, manager, folder):
    from app.segmented_downloader import LIMITER
    name, _ = server.file(4 * MB)
    LIMITER.set_rate(1 * MB)
    manager.add_url(server.url("f", name), Settings(kind="file", folder=folder))
    assert wait_for(lambda: manager.items[0].state == "downloading")
    manager.set_gate(False)
    time.sleep(0.5)
    assert manager.items[0].state == "downloading"
    LIMITER.set_rate(0)
    assert wait_for(lambda: manager.items[0].state == DONE, 15)


def test_items_added_while_the_gate_is_closed_keep_their_order(server, manager, folder):
    from app.segmented_downloader import LIMITER
    LIMITER.set_rate(1 * MB)
    manager.set_max_parallel(1)
    manager.set_gate(False)
    for _ in range(3):
        name, _ = server.file(3 * MB)
        manager.add_url(server.url("f", name), Settings(kind="file", folder=folder))
    time.sleep(0.5)
    assert [i.state for i in manager.items] == [QUEUED] * 3
    manager.set_gate(True)
    assert wait_for(lambda: manager.items[0].state == "downloading")
    assert manager.items[1].state == QUEUED and manager.items[2].state == QUEUED
