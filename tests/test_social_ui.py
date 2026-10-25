"""👥 The friends window: its lists, the chat (every kind of message), sending, replying, reacting, searching, the ➕
menu, groups and their info window. The people and the pretend Supabase are those of test_social.py."""
import time
from tkinter import messagebox

from supabase_support import cloud  # noqa: F401 - the fixture
from test_social import befriend, first_poll, make_group, people, quiet, uid  # noqa: F401 - the fixtures

from app import social, social_dialogs, social_ui


def run_until(app, done, seconds=10):
    deadline = time.time() + seconds
    while not done() and time.time() < deadline:
        app._drain_ui_calls()
        app.update()
        time.sleep(0.02)
    assert done()


def idle(app, win):
    run_until(app, lambda: win.busy == 0)
    app._drain_ui_calls()
    app.update()


def settle(app, win):
    idle(app, win)
    idle(app, win)


def texts(widget):
    """Every text shown inside a widget."""
    out = []
    for w in widget.winfo_children():
        try:
            out.append(w.cget("text"))
        except Exception:  # noqa: BLE001
            pass
        out += texts(w)
    return out


def dialog(win, kind):
    return [w for w in win.winfo_children() if isinstance(w, kind)][-1]


def test_the_window_lists_friends_and_groups_and_the_chat_shows_every_kind_of_message(app, people):
    conv = make_group(people)
    people("ali")
    social.message(uid(people, "veli"), "selam")
    social.recommend(uid(people, "veli"), {"title": "Firuze", "artist": "Sezen Aksu", "url": "https://y/f"})
    social.send_playlist(conv, "Gece", [{"title": "a", "url": "https://y/a"}, {"title": "b", "url": "https://y/b"}])
    sent = social.message(uid(people, "veli"), "silinecek")
    social.react(sent["id"], "👍")
    social.delete_message(sent["id"])
    win = app.open_friends()
    idle(app, win)
    shown = texts(win.left_list)
    assert any("Müzik Kulübü" in t for t in shown) and any("Veli Yılmaz" in t for t in shown)
    assert any("Can Yılmaz" in t for t in shown)
    win.choose(None, uid(people, "veli"))
    settle(app, win)
    chat = texts(win.msg_box)
    assert "selam" in chat and any("Sezen Aksu - Firuze" in t for t in chat) and "🚫 Bu mesaj silindi" in chat
    assert any(t.endswith("✓") or t.endswith("✓✓") for t in chat)                        # my messages' ticks
    win.choose(conv)
    settle(app, win)
    assert any("Gece  ·  2 şarkı" in t for t in texts(win.msg_box))
    assert any("Grup oluşturuldu" in t for t in texts(win.msg_box))
    win.destroy()


def test_sending_from_the_window_replying_reacting_deleting_and_searching(app, people, monkeypatch):
    befriend(people)
    people("ali")
    win = app.open_friends()
    idle(app, win)
    win.choose(None, uid(people, "veli"))
    settle(app, win)
    win.msg_entry.insert(0, "merhaba")
    win.send_message()
    idle(app, win)
    assert "merhaba" in texts(win.msg_box) and win.msg_entry.get() == ""
    first = win.msgs[0]
    win.start_reply(first)
    assert "merhaba" in win.reply_label.cget("text")
    win.msg_entry.insert(0, "cevap")
    win.send_message()
    idle(app, win)
    assert win.reply is None and win.msgs[1]["reply_to"] == first["id"]
    assert any(t.startswith("↩ Sen: merhaba") for t in texts(win.msg_box))
    win.toggle_reaction(first, "❤")
    settle(app, win)
    assert "❤ 1" in texts(win.msg_box)
    win.toggle_reaction(win.msgs[0], "❤")
    settle(app, win)
    assert "❤ 1" not in texts(win.msg_box)
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    win.delete_message(win.msgs[0])
    settle(app, win)
    assert "🚫 Bu mesaj silindi" in texts(win.msg_box)
    win.toggle_search()
    win.search_entry.insert(0, "cevap")
    win.do_search()
    idle(app, win)
    assert [m["body"] for m in win.msgs] == ["cevap"]
    win.toggle_search()
    settle(app, win)
    assert len(win.msgs) == 2
    win.destroy()


def test_new_messages_come_into_the_open_chat_and_typing_is_shown(app, people, monkeypatch):
    befriend(people)
    first_poll(people, "ali")
    people("ali")
    win = app.open_friends()
    idle(app, win)
    win.choose(None, uid(people, "veli"))
    settle(app, win)
    people("veli")
    social.message(uid(people, "ali"), "yeni mesaj")
    people("ali")
    came = social.poll()
    monkeypatch.setattr(app, "focus_displayof", lambda: win)                           # (the window is in front)
    app._social_came(came)
    settle(app, win)
    assert "yeni mesaj" in texts(win.msg_box) and social.load()["unread"] == {}         # read: it is open
    win.typing(win.chosen["id"], uid(people, "veli"))
    assert win.chat_sub.cget("text") == "Veli Yılmaz yazıyor…"
    app._social_came([{"kind": "groups", "text": ""}])                                 # (only the lists changed)
    win.destroy()


def test_the_plus_menu_sends_songs_a_playlist_and_files(app, people, monkeypatch, tmp_path):
    befriend(people)
    people("ali")
    win = app.open_friends()
    idle(app, win)
    win.choose(None, uid(people, "veli"))
    settle(app, win)
    song = tmp_path / "Sezen Aksu - Firuze.mp3"
    song.write_bytes(b"x")
    store = app._store()
    store.add(store.ensure("Gece"), [str(song)])
    app.history.entries.append({"path": str(song), "url": "https://youtube.com/watch?v=firuze", "title": "Firuze"})
    win.pick_from_list()                                       # the playlist's songs; the chosen go with their links
    picker = dialog(win, social_dialogs.SongPicker)
    picker.set_entries(win._tracks_entries(store.tracks("Gece")))
    assert [label for label, _v in picker.entries] == ["Sezen Aksu - Firuze"]
    picker.checks[0][0].set(True)
    picker.send()
    settle(app, win)
    assert any("Sezen Aksu - Firuze" in t for t in texts(win.msg_box))
    win.pick_downloaded()                                      # the last downloads: their links are known
    picker = dialog(win, social_dialogs.SongPicker)
    assert [label for label, _v in picker.entries] == ["Firuze"]
    picker.send()
    assert "işaretle" in picker.status.cget("text")
    picker.destroy()
    win.send_playlist("Gece")
    settle(app, win)
    assert any("Gece  ·  1 şarkı" in t for t in texts(win.msg_box))
    picture = tmp_path / "kapak.png"
    picture.write_bytes(b"x" * 10)
    monkeypatch.setattr(social_ui.filedialog, "askopenfilename", lambda **k: str(picture))
    win.pick_file(True)
    settle(app, win)
    assert any("kapak.png" in t for t in texts(win.msg_box)) and len(people.cloud.files) == 1
    win.destroy()


def test_making_a_group_and_running_it_from_the_info_window(app, people):
    befriend(people, "ali", "veli")
    befriend(people, "ali", "can")
    people("ali")
    win = app.open_friends()
    idle(app, win)
    win.new_group()
    box = dialog(win, social_dialogs.GroupDialog)
    box.make()
    assert "bir adı olsun" in box.status.cget("text")
    box.name.insert(0, "Dinleme Grubu")
    box.vars[uid(people, "veli")].set(True)
    box.make()
    settle(app, win)
    assert win.chosen, box.status.cget("text")
    assert win.chosen["name"] == "Dinleme Grubu" and win.chosen["role"] == "admin"
    win.open_info()
    info = dialog(win, social_dialogs.InfoDialog)
    settle(app, win)
    assert [m["name"] for m in info.members] == ["Ali Yılmaz", "Veli Yılmaz"]
    info.name.delete(0, "end")
    info.name.insert(0, "Yeni Ad")
    info.admins_only.set(True)
    info._save_info()
    settle(app, win)
    assert win.chosen["name"] == "Yeni Ad" and win.chosen["only_admins"]
    info._role(info.members[1])
    settle(app, win)
    assert [m["role"] for m in info.members] == ["admin", "admin"]
    info.destroy()
    win.destroy()


def test_the_recommend_menu_lists_friends_and_groups_and_sends_into_a_chat(app, people, monkeypatch):
    conv = make_group(people)
    people("ali")
    social.conversations()                                              # (the groups are noted for the menu)
    items = app.recommend_items([{"path": "x.mp3", "title": "x"}])
    labels = [i[0] for i in items if i]
    assert "Veli Yılmaz" in labels and "🎶 Müzik Kulübü" in labels and labels[-1] == "👥 Arkadaşlar…"
    monkeypatch.setattr(app, "song_links", lambda tracks: [{"title": "x", "artist": "", "url": "https://y/x"}])
    next(i for i in items if i and i[0] == "🎶 Müzik Kulübü")[1]()
    run_until(app, lambda: social.messages(conv)[-1]["kind"] == "song")
