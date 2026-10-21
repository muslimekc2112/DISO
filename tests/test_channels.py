"""📺 Followed channels: new videos are announced and listed, never downloaded by themselves."""
import json
import time

import pytest
from conftest import wait_for

from app import channels


def video(n, channel="kanal"):
    return {"id": f"{channel}{n}", "url": f"https://www.youtube.com/watch?v={channel}{n}", "title": f"Video {n}",
            "duration": 60 + n}


def read(name="Kanal", ids=(3, 2, 1), url="https://www.youtube.com/@kanal/videos"):
    return {"url": url, "name": name, "videos": [video(i) for i in ids]}


# ------------------------------------------------------------------------------ links
@pytest.mark.parametrize("text, link", [
    ("@BarisMancoOfficial", "https://www.youtube.com/@BarisMancoOfficial/videos"),
    ("https://www.youtube.com/@kanal", "https://www.youtube.com/@kanal/videos"),
    ("https://youtube.com/@kanal/featured", "https://www.youtube.com/@kanal/videos"),
    ("https://m.youtube.com/channel/UCR5wZcXtOUka8jTA57flzMg/streams", "https://www.youtube.com/channel/UCR5wZcXtOUka8jTA57flzMg/videos"),
    ("https://www.youtube.com/c/eski/videos", "https://www.youtube.com/c/eski/videos"),
    ("https://www.twitch.tv/biri/videos", "https://www.twitch.tv/biri/videos"),
    ("https://www.youtube.com/watch?v=zd8IFDgQCUc", "https://www.youtube.com/watch?v=zd8IFDgQCUc"),
    ("bir şarkı", ""), ("", "")])
def test_what_the_user_types_becomes_the_channels_video_list(text, link):
    assert channels.channel_link(text) == link


class FakeYDL:
    """yt-dlp's YoutubeDL as read_channel uses it: answers by link."""
    answers = {}
    asked = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False, process=True):
        FakeYDL.asked.append((url, dict(self.opts), process))
        return FakeYDL.answers[url]


def test_a_channel_is_read_without_downloading_and_newest_first():
    FakeYDL.asked = []
    FakeYDL.answers = {
        "https://www.youtube.com/watch?v=zd8IFDgQCUc": {"channel_url": "https://www.youtube.com/channel/UCx"},
        "https://www.youtube.com/channel/UCx/videos": {"_type": "playlist", "title": "netd müzik - Videos", "entries": [
            {"id": "a1", "url": "a1", "title": "Yeni", "duration": 200.0},
            {"id": "live", "url": "live", "title": "Canlı", "live_status": "is_live"},
            {"id": "b2", "url": "https://www.youtube.com/watch?v=b2", "title": "Eski"}, None]}}
    got = channels.read_channel("https://www.youtube.com/watch?v=zd8IFDgQCUc", ydl_class=FakeYDL, opts={})
    assert got == {"url": "https://www.youtube.com/channel/UCx/videos", "name": "netd müzik", "videos": [
        {"id": "a1", "url": "https://www.youtube.com/watch?v=a1", "title": "Yeni", "duration": 200},
        {"id": "b2", "url": "https://www.youtube.com/watch?v=b2", "title": "Eski", "duration": 0}]}
    url, opts, _ = FakeYDL.asked[-1]
    assert opts["extract_flat"] == "in_playlist" and opts["skip_download"] and opts["playlistend"] == channels.LATEST


def test_a_link_that_is_no_channel_is_refused():
    FakeYDL.answers = {"https://a.com/x": {"_type": "video", "title": "tek"}}
    with pytest.raises(ValueError):
        channels.read_channel("https://a.com/x", ydl_class=FakeYDL, opts={})


# ------------------------------------------------------------------------------ the store
def test_following_does_not_make_the_old_videos_new(tmp_path):
    store = channels.Store(str(tmp_path / "c.json"))
    assert store.follow(read()) and not store.follow(read())                  # once
    assert store.new == [] and store.channels[0]["seen"] == ["kanal3", "kanal2", "kanal1"]


def test_only_videos_not_seen_before_are_new_and_kept_after_a_restart(tmp_path):
    path = str(tmp_path / "c.json")
    store = channels.Store(path)
    store.follow(read())
    found = store.update(read()["url"], read(ids=(5, 4, 3, 2)))
    assert [v["id"] for v in found] == ["kanal5", "kanal4"] and found[0]["channel"] == "Kanal"
    assert store.update(read()["url"], read(ids=(5, 4, 3))) == []                # the same again: nothing new
    again = channels.Store(path)
    assert [v["id"] for v in again.new] == ["kanal5", "kanal4"] and again.channels[0]["seen"][:2] == ["kanal5", "kanal4"]
    again.dismiss(["https://www.youtube.com/watch?v=kanal5"])
    assert [v["id"] for v in channels.Store(path).new] == ["kanal4"]


def test_an_error_is_remembered_and_a_broken_file_is_no_problem(tmp_path):
    path = tmp_path / "c.json"
    store = channels.Store(str(path))
    store.follow(read())
    store.update(read()["url"], error="Bağlantı yok")
    assert channels.Store(str(path)).channels[0]["error"] == "Bağlantı yok"
    path.write_text("{bozuk", encoding="utf-8")
    assert len(channels.Store(str(path)).channels) == 1                           # back from its last good copy
    path.write_text("{bozuk", encoding="utf-8")
    (tmp_path / "c.json.bak").write_text("{bozuk", encoding="utf-8")
    assert channels.Store(str(path)).channels == []                               # nothing good left: empty


def test_how_often_is_remembered(tmp_path):
    store = channels.Store(str(tmp_path / "c.json"))
    store.set_every("6 saatte bir")
    store.set_every("olmayan")
    assert channels.Store(str(tmp_path / "c.json")).every == "6 saatte bir"
    assert json.load(open(tmp_path / "c.json", encoding="utf-8"))["every"] == "6 saatte bir"


# ------------------------------------------------------------------------------ the watcher
def test_the_watcher_follows_looks_and_reports(tmp_path):
    answers = {"https://www.youtube.com/@kanal/videos": read()}
    store = channels.Store(str(tmp_path / "c.json"))
    w = channels.Watcher(store, read=lambda url: answers[url], first_look=0)
    w.follow("@kanal")
    w.start()
    news = []
    assert wait_for(lambda: news.extend(w.drain()) or any(n[0] == "followed" for n in news))
    assert ("followed", read(), "") in news
    answers["https://www.youtube.com/@kanal/videos"] = read(ids=(4, 3, 2, 1))
    news.clear()
    w.check_now()
    assert wait_for(lambda: news.extend(w.drain()) or any(n[0] == "checked" for n in news))
    assert [(k, n, [v["id"] for v in f]) for k, n, f in news if k == "new"] == [("new", "Kanal", ["kanal4"])]
    w.stop()


def test_a_channel_that_cannot_be_read_says_why(tmp_path):
    def broken(url):
        raise ConnectionError("ağ yok")
    w = channels.Watcher(channels.Store(str(tmp_path / "c.json")), read=broken, first_look=0)
    w.follow("@kanal")
    news = []
    assert wait_for(lambda: news.extend(w.drain()) or news)
    assert news[0][0] == "followed" and news[0][1] is None and "ağ yok" in news[0][2]
    w.follow("bir şarkı")
    news.clear()
    assert wait_for(lambda: news.extend(w.drain()) or news)
    assert news == [("followed", None, "Bu bir kanal linki değil")]
    w.stop()


def test_the_notification_text():
    one = [("new", "Kanal", [video(1)])]
    assert channels.announcement(one) == ("📺 Kanal: yeni video", "Video 1")
    assert channels.announcement([("new", "Kanal", [video(2), video(1)])]) == ("📺 Kanal: 2 yeni video", "Video 2")
    assert channels.announcement(one + [("new", "Öteki", [video(5)])]) == ("📺 2 yeni video", "Kanal, Öteki")


# ------------------------------------------------------------------------------ in the program
@pytest.mark.gui
def test_new_videos_are_announced_and_never_downloaded_by_themselves(make_app, monkeypatch):
    from app import notify
    toasts = []
    monkeypatch.setattr(notify, "toast", lambda title, body: toasts.append((title, body)))
    app = make_app()
    app.channel_store.follow(read())
    app.channel_watcher._out.put(("new", "Kanal", app.channel_store.update(read()["url"], read(ids=(5, 4, 3)))))
    app._drain_channels()
    assert toasts == [("📺 Kanal: 2 yeni video", "Video 5")]
    assert app.channels_btn.cget("text") == "📺 2"
    assert app.manager.items == []                                     # nothing was downloaded
    win = app.open_channels()
    assert [win.tree.item(i, "values")[0] for i in win.tree.get_children()] == ["Video 5", "Video 4"]
    assert win.channel_tree.item("0", "values")[0] == "Kanal"


@pytest.mark.gui
def test_picked_videos_are_downloaded_as_mp4_or_mp3(app):
    app.channel_store.follow(read())
    app.channel_store.update(read()["url"], read(ids=(6, 5, 4, 3)))
    win = app.open_channels()
    win.tree.selection_set(("0", "2"))
    win.download("audio")
    assert [(i.url, i.kind) for i in app.manager.items] == [
        ("https://www.youtube.com/watch?v=kanal6", "audio"), ("https://www.youtube.com/watch?v=kanal4", "audio")]
    assert [v["id"] for v in app.channel_store.new] == ["kanal5"]          # what was downloaded leaves the list
    win.tree.selection_set(("0",))
    win.download("video")
    assert app.manager.items[-1].kind == "video" and app.channel_store.new == []
    app._drain_channels()
    assert app.channels_btn.cget("text") == "📺"


@pytest.mark.gui
def test_following_and_unfollowing_from_the_window(app, monkeypatch):
    from tkinter import messagebox
    app.channel_watcher._read = lambda url: read(name="Yeni Kanal", url=url)
    app.channel_watcher._first = 0
    win = app.open_channels()
    win.entry.insert(0, "şarkı adı")
    win.follow()
    assert "kanal linki değil" in win.status.cget("text")
    win.entry.delete(0, "end")
    win.entry.insert(0, "@yenikanal")
    win.follow()
    assert win.follow_btn.cget("state") == "disabled"
    end = time.time() + 10
    while time.time() < end and not win.channel_tree.exists("0"):     # the answer comes from another thread
        app._drain_channels()
        app.update()
        time.sleep(0.05)
    assert win.channel_tree.item("0", "values")[0] == "Yeni Kanal" and "takip ediliyor" in win.status.cget("text")
    assert win.entry.get() == "" and win.follow_btn.cget("state") == "normal"
    win.channel_tree.selection_set("0")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    win.unfollow()
    assert app.channel_store.channels == [] and win.channel_tree.get_children() == ()


@pytest.mark.gui
def test_look_now_says_when_it_has_looked(app):
    app.channel_store.follow(read())
    app.channel_watcher._read = lambda url: read(ids=(9, 3, 2, 1))
    win = app.open_channels()
    win.check_now()
    assert win.check_btn.cget("state") == "disabled" and "bakıyorum" in win.status.cget("text")
    end = time.time() + 10
    while time.time() < end and "baktım" not in win.status.cget("text"):
        app._drain_channels()
        time.sleep(0.05)
    assert "Kanallara baktım" in win.status.cget("text") and win.check_btn.cget("state") == "normal"
    assert [v["id"] for v in app.channel_store.new] == ["kanal9"] and app.manager.items == []
