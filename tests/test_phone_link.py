"""📱 Links from the phone: the little page on the local network, its key, and the window with the QR code."""
import time

import pytest
import requests

from app import phone_link

NO_PROXY = {"http": None, "https": None}


@pytest.fixture(autouse=True)
def only_this_pc(monkeypatch):
    monkeypatch.setattr(phone_link, "HOST", "127.0.0.1")       # no firewall question during the tests


@pytest.fixture
def link():
    got = []
    pl = phone_link.PhoneLink(on_links=lambda urls, kind: got.append((urls, kind)), language=lambda: "en")
    pl.start()
    pl.got = got
    yield pl
    pl.stop()


def _base(pl):
    return f"http://127.0.0.1:{pl.server.server_address[1]}"


def test_the_page_opens_only_with_the_key_of_the_qr_code(link):
    assert link.url().endswith(f"/?k={link.key}") and link.url().startswith("http://")
    r = requests.get(_base(link) + "/?k=" + link.key, proxies=NO_PROXY, timeout=5)
    assert r.status_code == 200 and "Send to DISO" in r.text and "⬇ Download" in r.text
    assert requests.get(_base(link) + "/?k=wrong", proxies=NO_PROXY, timeout=5).status_code == 403
    assert requests.get(_base(link) + "/", proxies=NO_PROXY, timeout=5).status_code == 403


def test_links_sent_from_the_page_reach_the_app(link):
    r = requests.post(_base(link) + "/add?k=" + link.key, json={"text": "bak: https://a.example/x.zip ve "
                                                                        "https://b.example/v", "kind": "audio"},
                      proxies=NO_PROXY, timeout=5)
    assert r.json() == {"added": 2}
    assert link.got == [(["https://a.example/x.zip", "https://b.example/v"], "audio")]
    r = requests.post(_base(link) + "/add?k=" + link.key, json={"text": "no link", "kind": "evil"},
                      proxies=NO_PROXY, timeout=5)
    assert r.json() == {"added": 0} and len(link.got) == 1
    bad = requests.post(_base(link) + "/add?k=nope", json={"text": "https://a.example/y"}, proxies=NO_PROXY, timeout=5)
    assert bad.status_code == 403 and len(link.got) == 1


def test_closing_changes_the_key(link):
    old = link.key
    link.stop()
    assert not link.running and link.key != old
    link.start()
    assert link.running and link.key != old


def test_the_qr_code_is_an_image():
    img = phone_link.qr_image("http://192.168.1.5:5000/?k=abc")
    assert img.size[0] == img.size[1] and img.size[0] > 100


@pytest.mark.gui
def test_the_phone_button_opens_the_qr_code_and_links_are_added(app, monkeypatch):
    added = []
    monkeypatch.setattr(app, "add_urls", lambda urls, kind=None: added.append((urls, kind)) or len(urls))
    win = app.open_phone()
    assert app.phone_btn.cget("text") == "📱" and app.phone_link.running
    assert win.url_label.cget("text") == app.phone_link.url() and app.open_phone() is win
    requests.post(f"http://127.0.0.1:{app.phone_link.server.server_address[1]}/add?k={app.phone_link.key}",
                  json={"text": "https://a.example/song", "kind": "auto"}, proxies=NO_PROXY, timeout=5)
    end = time.time() + 5
    while not added and time.time() < end:
        app._drain_ui_calls()
        app.update()
        time.sleep(0.02)
    assert added == [(["https://a.example/song"], None)] and "Telefondan 1 link geldi" in app._notice
    win.toggle()
    assert not app.phone_link.running and win.toggle_btn.cget("text") == "Bağlantıyı aç"
    win.destroy()
