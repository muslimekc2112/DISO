"""👥 Friends, chats and groups: requests by user name, messages, songs recommended / liked, groups with their admins,
files in chats, the live connection, deleting the account. Several people on several "computers" (each with its own
data folder and session), and the pretend Supabase of tests/fake_supabase.py, which keeps the real database's rules."""
import json
import os
import time

import pytest
from supabase_support import cloud, ready  # noqa: F401 - the fixture

from app import account, playlists, social


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(social, "_seen_at", time.time())               # (no "I am here" write in every poll)


@pytest.fixture
def people(cloud, tmp_path, monkeypatch):
    """as_("ali") / as_("veli") / as_("can"): that person's computer (data folder and session) from now on."""
    homes = {}

    def as_(name):
        if name not in homes:
            homes[name] = tmp_path / name
            (homes[name] / "DISO").mkdir(parents=True)
        monkeypatch.setenv("LOCALAPPDATA", str(homes[name]))
        return name

    for name, first in (("ali", "Ali"), ("veli", "Veli"), ("can", "Can")):
        as_(name)
        ready(cloud, name, first, "Yılmaz")
    as_.cloud = cloud
    return as_


def uid(people, name):
    return people.cloud.uid_of(name)


def befriend(people, a="ali", b="veli"):
    people(a)
    social.request(b)
    people(b)
    social.poll()
    social.accept(uid(people, a))
    people(a)
    social.poll()


def first_poll(people, *names):
    """The first look of every computer (what was there before is not "new")."""
    for n in names:
        people(n)
        social.poll()


# ------------------------------------------------------------------------------ friends
def test_a_request_by_user_name_and_its_answer_make_friends_on_both_sides(people):
    first_poll(people, "veli", "ali")
    people("ali")
    with pytest.raises(social.SocialError, match="adında bir kullanıcı yok"):
        social.request("kimse")
    with pytest.raises(social.SocialError, match="Kendine"):
        social.request("ali")
    social.request("@Veli")                                              # (as typed: @ and capitals)
    assert list(social.load()["outgoing"].values())[0]["username"] == "veli"
    with pytest.raises(social.SocialError, match="zaten bir istek gönderdin"):
        social.request("veli")
    people("veli")
    came = social.poll()
    assert came[0]["kind"] == "request" and "Ali Yılmaz" in came[0]["text"]
    assert social.unread_count() == 1                                    # the waiting request
    assert list(social.requests_in()) == [uid(people, "ali")]
    social.accept(uid(people, "ali"))
    assert uid(people, "ali") in social.friends() and social.unread_count() == 0
    people("ali")
    came = social.poll()
    assert "kabul etti" in came[0]["text"] and uid(people, "veli") in social.friends()
    assert social.load()["outgoing"] == {}
    with pytest.raises(social.SocialError, match="Zaten arkadaşsınız"):
        social.request("veli")
    found = social.friends(refresh=True)
    assert found[uid(people, "veli")]["username"] == "veli" and "email" not in json.dumps(found)


def test_asking_each_other_is_a_yes_and_a_no_takes_the_request_away(people):
    people("ali")
    social.request("veli")
    people("veli")
    social.request("ali")                                                # Veli asks too, before looking
    assert uid(people, "ali") in social.friends()
    people("ali")
    social.poll()
    assert uid(people, "veli") in social.friends()
    social.unfriend(uid(people, "veli"))
    people("veli")
    social.poll()
    assert social.friends() == {}                                        # taken off on the other side too
    social.request("can")
    people("can")
    social.poll()
    social.decline(uid(people, "veli"))                                  # (no request from Veli: nothing happens)
    social.decline(uid(people, "ali"))
    people("ali")
    social.poll()
    assert social.load()["outgoing"] == {}                               # a "no": the request is just gone


def test_blocking_stops_requests_and_ends_the_friendship(people):
    befriend(people)
    people("veli")
    social.block(uid(people, "ali"))
    assert social.friends() == {} and list(social.blocked()) == [uid(people, "ali")]
    people("ali")
    with pytest.raises(social.SocialError, match="gönderemezsin"):
        social.request("veli")                                           # (the database refuses: blocked)
    social.poll()
    assert social.friends() == {}
    people("veli")
    social.unblock(uid(people, "ali"))
    assert social.blocked() == {}


def test_the_public_card_shows_the_name_and_the_song_never_the_e_mail(people):
    befriend(people)
    social.publish_me(now_playing="Tarkan - Kuzu Kuzu")
    c = social.card(uid(people, "ali"))
    assert c["username"] == "ali" and c["name"] == "Ali Yılmaz" and c["now"] == "Tarkan - Kuzu Kuzu"
    assert "@gmail.com" not in json.dumps(people.cloud.t["profiles"], ensure_ascii=False)
    people("veli")
    friend = social.friends(refresh=True)[uid(people, "ali")]
    assert friend["online"] and friend["now"] == "Tarkan - Kuzu Kuzu"
    people("ali")
    social.publish_me(status="invisible", now_playing="")
    people("veli")
    assert not social.friends(refresh=True)[uid(people, "ali")]["online"]


# ------------------------------------------------------------------------------ chats
def test_only_friends_can_talk_and_what_is_said_is_read_from_the_server(people):
    first_poll(people, "ali", "veli")
    people("ali")
    with pytest.raises(account.AccountError) as e:
        social.direct(uid(people, "veli"))                               # not friends yet
    assert e.value.code == "NOT_FRIENDS"
    befriend(people)
    social.message(uid(people, "veli"), "selam 👋")
    social.message(uid(people, "veli"), "naber")
    with pytest.raises(social.SocialError, match="Boş mesaj"):
        social.message(uid(people, "veli"), "   ")
    people("veli")
    came = social.poll()
    assert [c["text"] for c in came if c["kind"] == "message"] == ["💬 Ali Yılmaz: selam 👋", "💬 Ali Yılmaz: naber"]
    conv = social.direct(uid(people, "ali"))
    assert social.unread_count() == 2
    [chat] = social.conversations()
    assert chat["name"] == "Ali Yılmaz" and chat["kind"] == "direct" and chat["unread"] == 2 and chat["peer"] == uid(people, "ali")
    assert [m["body"] for m in social.messages(conv)] == ["selam 👋", "naber"]
    social.read(conv)
    assert social.unread_count() == 0 and social.conversations()[0]["unread"] == 0
    social.message(uid(people, "ali"), "iyi, sen?")
    assert [m["body"] for m in social.messages_after(conv, social.messages(conv)[1]["id"])] == ["iyi, sen?"]
    people("ali")
    assert social.poll()[0]["text"] == "💬 Veli Yılmaz: iyi, sen?"


def test_muted_chats_make_no_noise_and_old_messages_are_paged(people):
    befriend(people)
    first_poll(people, "veli")
    conv = social.direct(uid(people, "ali"))
    social.mute(conv, True)
    people("ali")
    for i in range(5):
        social.message(uid(people, "veli"), f"m{i}")
    people("veli")
    assert [c for c in social.poll() if c["kind"] == "message"] == []    # muted: no toast
    assert social.conversations()[0]["muted"] and social.conversations()[0]["unread"] == 5
    last = social.messages(conv, limit=2)
    assert [m["body"] for m in last] == ["m3", "m4"]
    assert [m["body"] for m in social.messages(conv, before=last[0]["id"], limit=2)] == ["m1", "m2"]
    assert [m["body"] for m in social.search(conv, "m3")] == ["m3"]


def test_a_recommended_song_its_answer_and_a_like(people):
    befriend(people)
    first_poll(people, "veli")
    people("ali")
    song = {"title": "Firuze", "artist": "Sezen Aksu", "url": "https://youtube.com/watch?v=f"}
    social.recommend(uid(people, "veli"), song)
    people("veli")
    came = social.poll()
    assert came[0]["text"] == "🎵 Ali Yılmaz sana bir şarkı öneriyor: Sezen Aksu - Firuze"
    note = social.load()["notes"][0]
    assert note["song"] == song and note["kind"] == "recommend"
    social.feedback(note["id"], 1)
    assert social.load()["notes"][0]["answered"] == 1
    social.tell_like({"title": "Kuzu Kuzu", "artist": "Tarkan", "url": "https://y/k"}, -1)
    people("ali")
    texts = [c["text"] for c in social.poll()]
    assert texts == ["👍 Veli Yılmaz önerdiğin şarkıyı beğendi: Sezen Aksu - Firuze",
                     "👎 Veli Yılmaz bu şarkıyı beğenmedi: Tarkan - Kuzu Kuzu"]
    assert social.poll() == []                                           # (read once)


def test_messages_can_be_deleted_and_answered_with_a_reaction(people):
    befriend(people)
    people("ali")
    conv = social.direct(uid(people, "veli"))
    sent = social.message(uid(people, "veli"), "yanlış mesaj")
    people("veli")
    social.react(sent["id"], "👍")
    social.react(sent["id"], "❤")                                        # (one reaction each: the second replaces)
    assert social.messages(conv)[0]["reactions"] == {"❤": [uid(people, "veli")]}
    social.unreact(sent["id"])
    assert social.messages(conv)[0]["reactions"] == {}
    people("ali")
    social.delete_message(sent["id"])
    gone = social.messages(conv)[0]
    assert gone["deleted"] and gone["body"] == ""
    people("can")
    with pytest.raises(account.AccountError):
        social.react(sent["id"], "👍")                                    # not in this chat: refused


def test_a_message_of_a_non_friend_is_refused_by_the_database(people):
    befriend(people)
    people("ali")
    conv = social.direct(uid(people, "veli"))
    social.unfriend(uid(people, "veli"))
    with pytest.raises(social.SocialError, match="artık arkadaş değilsiniz"):
        social.send(conv, "hâlâ yazıyorum")                              # the chat of two is closed
    people("can")
    with pytest.raises(account.AccountError):
        social.send(conv, "ben de yazayım")                              # not a member at all
    assert social.messages(conv) == []                                   # (and sees nothing of it)


# ------------------------------------------------------------------------------ groups
def make_group(people, **kw):
    befriend(people, "ali", "veli")
    befriend(people, "ali", "can")
    people("ali")
    return social.create_group("Müzik Kulübü", "her gün bir şarkı", "🎶",
                               [uid(people, "veli"), uid(people, "can")], **kw)


def test_a_group_has_admins_members_and_rules(people):
    conv = make_group(people)
    people("ali")
    members = social.group_members(conv)
    assert [(m["name"], m["role"]) for m in members] == [("Ali Yılmaz", "admin"), ("Veli Yılmaz", "member"),
                                                         ("Can Yılmaz", "member")]
    assert [c["name"] for c in social.conversations()] == ["Müzik Kulübü"]
    people("veli")
    with pytest.raises(account.AccountError) as e:
        social.group_add(conv, uid(people, "can"))                       # a member cannot add
    assert e.value.code == "NOT_ADMIN"
    with pytest.raises(account.AccountError) as e:
        social.group_remove(conv, uid(people, "can"))
    assert e.value.code == "NOT_ADMIN"
    social.group_update(conv, name="benim grubum")                       # (nothing happens: not an admin)
    assert social.conversations()[0]["name"] == "Müzik Kulübü"
    social.send(conv, "herkese selam")
    people("ali")
    social.group_role(conv, uid(people, "veli"), True)                   # Veli is an admin now
    social.group_update(conv, only_admins=True, about="duyurular")
    people("can")
    with pytest.raises(social.SocialError, match="yalnız yöneticiler"):
        social.send(conv, "ben de yazayım")                              # 📢 only the admins write
    people("veli")
    social.send(conv, "duyuru: cuma buluşuyoruz")
    people("ali")
    social.group_role(conv, uid(people, "veli"), False)
    social.group_remove(conv, uid(people, "can"))
    assert [m["name"] for m in social.group_members(conv)] == ["Ali Yılmaz", "Veli Yılmaz"]
    people("can")
    assert social.conversations() == []                                  # removed: the group is gone from his list
    assert social.messages(conv) == []


def test_a_group_takes_only_friends_and_leaving_hands_the_group_over(people):
    befriend(people, "ali", "veli")
    people("ali")
    conv = social.create_group("Üçlü", "", "👥", [uid(people, "veli"), uid(people, "can")])   # Can: not a friend
    assert [m["name"] for m in social.group_members(conv)] == ["Ali Yılmaz", "Veli Yılmaz"]
    with pytest.raises(account.AccountError) as e:
        social.group_add(conv, uid(people, "can"))
    assert e.value.code == "NOT_FRIENDS"
    with pytest.raises(account.AccountError) as e:
        social.create_group("   ", "", "👥", [])
    assert e.value.code == "NO_NAME"
    social.group_leave(conv)                                             # the only admin leaves
    people("veli")
    assert [(m["name"], m["role"]) for m in social.group_members(conv)] == [("Veli Yılmaz", "admin")]
    social.group_delete(conv)
    assert social.conversations() == []


def test_group_messages_mentions_and_system_lines(people):
    conv = make_group(people)
    first_poll(people, "veli", "can")
    people("ali")
    social.send(conv, "@veli bak bu şarkıya", payload={"mentions": [uid(people, "veli")]})
    social.recommend_conv(conv, {"title": "Firuze", "artist": "Sezen Aksu", "url": "https://y/f"})
    people("veli")
    came = social.poll()
    assert came[0]["text"] == "💬 Müzik Kulübü · Ali Yılmaz: @veli bak bu şarkıya" and came[0]["mention"]
    assert any("seni Müzik Kulübü grubunda andı" in n["text"] for n in social.load()["notes"])
    assert came[1]["kind"] == "recommend"
    names = {uid(people, "ali"): "Ali", uid(people, "can"): "Can"}
    assert social.system_text("added:" + uid(people, "can"), names) == "Can gruba eklendi"
    assert social.system_text("created", names) == "Grup oluşturuldu"


# ------------------------------------------------------------------------------ files in chats
def test_files_go_through_the_bucket_to_the_members_only(people, tmp_path):
    befriend(people)
    people("ali")
    conv = social.direct(uid(people, "veli"))
    picture = tmp_path / "kapak.png"
    picture.write_bytes(b"\x89PNG" + b"x" * 100)
    sent = social.upload(conv, str(picture))
    assert sent["kind"] == "image" and sent["payload"]["name"] == "kapak.png" and sent["payload"]["size"] == 104
    document = tmp_path / "not defteri.txt"
    document.write_bytes(b"merhaba")
    assert social.upload(conv, str(document))["kind"] == "file"
    people("veli")
    got = social.download(social.messages(conv)[0]["payload"], str(tmp_path / "indirilen"))
    assert open(got, "rb").read() == picture.read_bytes() and os.path.basename(got) == "kapak.png"
    assert os.path.basename(social.download(social.messages(conv)[0]["payload"], str(tmp_path / "indirilen"))) \
        == "kapak (2).png"                                               # (a name taken: another one)
    people("can")
    with pytest.raises(account.AccountError):
        social.download(sent["payload"], str(tmp_path / "x"))            # not in this chat: refused
    big = tmp_path / "büyük.bin"
    big.write_bytes(b"0")
    people("ali")
    old = social.MAX_FILE
    social.MAX_FILE = 0
    try:
        with pytest.raises(social.SocialError, match="Dosya çok büyük"):
            social.upload(conv, str(big))
    finally:
        social.MAX_FILE = old


# ------------------------------------------------------------------------------ 🗑 deleting the account
def test_deleting_the_account_tells_the_friends_and_takes_its_files(people, tmp_path):
    befriend(people)
    people("ali")
    conv = social.direct(uid(people, "veli"))
    social.message(uid(people, "veli"), "görüşürüz")
    upload = tmp_path / "a.txt"
    upload.write_bytes(b"x")
    social.upload(conv, str(upload))
    assert people.cloud.files
    first_poll(people, "veli")
    people("ali")
    account.delete_account("gizli123")
    assert not account.signed_in() and people.cloud.files == {} and "ali@gmail.com" not in people.cloud.users
    people("veli")
    came = social.poll()
    assert came[0]["text"] == "Ali Yılmaz DISO hesabını sildi" and social.friends() == {}
    assert [m["sender"] for m in social.messages(conv)] == [None, None]  # what was said stays, without a name
    people("ali")
    ready(people.cloud, "ali", "Ali", "Yeni", password="gizli456")       # the name and e-mail are free again


# ------------------------------------------------------------------------------ 🔴 the live connection
class FakeSocket:
    """A pretend live connection: what the server would say is given as a list; then it is quiet."""

    def __init__(self, incoming):
        self.incoming, self.sent, self.closed = list(incoming), [], False

    def send(self, text):
        self.sent.append(json.loads(text))

    def recv(self, timeout=None):
        if self.incoming:
            item = self.incoming.pop(0)
            if isinstance(item, Exception):
                raise item
            return json.dumps(item)
        raise TimeoutError

    def close(self):
        self.closed = True


def test_the_live_connection_joins_and_tells_when_something_changes(people):
    people("ali")
    changes, typing = [], []
    socket = FakeSocket([{"topic": "realtime:diso", "event": "phx_reply", "payload": {"status": "ok"}},
                         {"event": "postgres_changes", "payload": {"data": {}}},
                         {"event": "broadcast", "payload": {"event": "typing", "payload": {"conv": "c1", "uid": "u9"}}},
                         {"event": "broadcast", "payload": {"event": "typing",
                                                            "payload": {"conv": "c1", "uid": uid(people, "ali")}}},
                         {"event": "phx_close", "payload": {}}])
    live = social.Live(lambda: changes.append(1), lambda c, u: typing.append((c, u)), connect=lambda url: socket)
    with pytest.raises(OSError):
        live._connection(account.load())
    assert len(changes) == 2 and typing == [("c1", "u9")]               # (one on joining, one for the change; not mine)
    join = socket.sent[0]
    assert join["event"] == "phx_join" and join["payload"]["access_token"] and socket.closed
    assert {c["table"] for c in join["payload"]["config"]["postgres_changes"]} == set(social.LIVE_TABLES)


def test_the_live_connection_comes_back_and_typing_goes_out(people, monkeypatch):
    people("ali")
    monkeypatch.setattr(social, "LIVE_RETRY", 0)
    sockets = [FakeSocket([{"topic": "realtime:diso", "event": "phx_reply", "payload": {"status": "ok"}},
                           {"event": "phx_error", "payload": {}}]),
               FakeSocket([{"topic": "realtime:diso", "event": "phx_reply", "payload": {"status": "ok"}}])]
    live = social.Live(lambda: None, connect=lambda url: sockets.pop(0) if sockets else (_ for _ in ()).throw(OSError("no")))
    seen = []
    original = live._handle

    def watch(message):
        original(message)
        if len(seen) < 1 and live.connected and not sockets:
            seen.append(1)
            live.typing("conv-1")
            live.stopped.set()
    live._handle = watch
    live.run()
    assert seen and not live.connected                                   # (it was connected; the loop ended)


def test_polling_slows_down_while_the_live_connection_is_there(app, people):
    befriend(people)
    assert app._social_delay() == social.POLL_EVERY
    app.live = type("Live", (), {"connected": True})()
    assert app._social_delay() == social.LIVE_POLL_EVERY
    app.live = None


# ------------------------------------------------------------------------------ 👍 / 👎
def test_a_rating_is_kept_with_the_song_and_fills_the_liked_list(tmp_path):
    song = tmp_path / "a.mp3"
    song.write_bytes(b"x")
    store = playlists.PlaylistStore(str(tmp_path / "p.json"))
    store.add(store.ensure("Gece"), [str(song)])
    assert store.rate(str(song), 1) == 1 and store.rating(str(song)) == 1
    assert [t["path"] for t in store.tracks(playlists.SMART_LIKED)] == [os.path.abspath(str(song))]
    assert store.rate(str(song), 1) == 0                                 # the same again: taken back
    assert store.tracks(playlists.SMART_LIKED) == []
    store.rate(str(song), -1)
    assert playlists.PlaylistStore(str(tmp_path / "p.json")).rating(str(song)) == -1


def test_play_counts_and_ratings_follow_the_songs_to_another_computer(cloud, tmp_path):
    from supabase_support import read, write
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    song = os.path.join(a, account.MUSIC_DIR_NAME, "s.mp3")
    os.makedirs(os.path.dirname(song))
    open(song, "wb").close()
    key = playlists.file_key(song)
    write(a, "playlists.json", {"playlists": {"Gece": [{"path": song, "title": "s"}]},
                                "stats": {key: {"plays": 3, "rating": 1}}})
    ready(cloud)
    account.sync("up", folder=a)
    account.sync("start", folder=b)
    there = playlists.file_key(os.path.join(b, account.MUSIC_DIR_NAME, "s.mp3"))
    assert playlists._clean_stats(read(b, "playlists.json")["stats"]) == {there: {"plays": 3, "rating": 1}}
