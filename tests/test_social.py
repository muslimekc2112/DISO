"""👥 Friends: requests by user name, messages, songs recommended / liked, what a friend listens to, deleting the
account. Two people on two "computers" (each with its own data folder) and the pretend Firebase of test_account,
which keeps the real database's rules: a request anyone may leave, the rest only a friend."""
import json
import os
import time

import pytest
from test_account import FakeFirebase

from app import account, playlists, social


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeFirebase()
    monkeypatch.setattr(account, "_call", fake)
    monkeypatch.setattr(social, "_seen_at", time.time())               # (no "I am here" write in every poll)
    return fake


@pytest.fixture
def people(cloud, tmp_path, monkeypatch):
    """as_("ali") / as_("veli"): that person's computer (data folder and session) from now on."""
    homes = {}

    def as_(name):
        if name not in homes:
            homes[name] = tmp_path / name
            (homes[name] / "DISO").mkdir(parents=True)
        monkeypatch.setenv("LOCALAPPDATA", str(homes[name]))
        return name

    for name, first in (("ali", "Ali"), ("veli", "Veli")):
        as_(name)
        account.sign_up(first, "Yılmaz", name, f"{name}@gmail.com", "gizli123")
        cloud.confirm(f"{name}@gmail.com")
        assert account.check_verified()
    return as_


def uid_of(name, cloud):
    return cloud.usernames[name]


def befriend(people, cloud):
    people("ali")
    social.request("veli")
    people("veli")
    social.poll()
    social.accept(uid_of("ali", cloud))
    people("ali")
    social.poll()


# ------------------------------------------------------------------------------ friends
def test_a_request_by_user_name_and_its_answer_make_friends_on_both_sides(people, cloud):
    people("ali")
    with pytest.raises(social.SocialError, match="adında bir kullanıcı yok"):
        social.request("kimse")
    with pytest.raises(social.SocialError, match="Kendine"):
        social.request("ali")
    social.request("@Veli")                                              # (as typed: @ and capitals)
    assert list(social.load()["outgoing"].values())[0]["username"] == "veli"
    people("veli")
    came = social.poll()
    assert came[0]["kind"] == "request" and "Ali Yılmaz" in came[0]["text"]
    assert social.unread_count() == 1                                    # the waiting request
    social.accept(uid_of("ali", cloud))
    assert uid_of("ali", cloud) in social.friends() and social.unread_count() == 0
    people("ali")
    came = social.poll()
    assert "kabul etti" in came[0]["text"] and uid_of("veli", cloud) in social.friends()
    assert social.load()["outgoing"] == {} and f"users/{uid_of('ali', cloud)}/outgoing/{uid_of('veli', cloud)}" \
        not in cloud.store
    with pytest.raises(social.SocialError, match="Zaten arkadaşsınız"):
        social.request("veli")


def test_asking_each_other_is_a_yes_and_a_no_takes_the_request_away(people, cloud):
    people("ali")
    social.request("veli")
    people("veli")
    social.request("ali")                                                # Veli asks too, before looking
    came = social.poll()                                                 # Ali's request comes: friends
    assert came[0]["kind"] == "accepted" and uid_of("ali", cloud) in social.friends()
    people("ali")
    social.poll()
    assert uid_of("veli", cloud) in social.friends()
    # a "no": the one who asked is not told in words, the request just goes
    cloud.usernames["ayse"] = "u9"
    social.unfriend(uid_of("veli", cloud))
    people("veli")
    social.poll()
    assert social.friends() == {}                                        # taken off on the other side too


def test_right_after_saying_yes_a_message_goes_before_the_other_side_looked(people, cloud):
    people("ali")
    social.request("veli")
    people("veli")
    social.poll()
    social.accept(uid_of("ali", cloud))
    social.message(uid_of("ali", cloud), "hoş geldin")                  # Ali's DISO has not looked yet
    people("ali")
    came = social.poll()                                                 # "accepted" first, then the message
    assert [c["kind"] for c in came] == ["accepted", "message"] and came[1]["text"] == "💬 Veli Yılmaz: hoş geldin"


def test_only_friends_can_send_anything_but_a_request(people, cloud):
    people("ali")
    with pytest.raises(account.AccountError, match="izin vermedi"):
        social.message(uid_of("veli", cloud), "selam")                   # the rules: not friends
    befriend(people, cloud)
    social.message(uid_of("veli", cloud), "selam 👋")
    people("veli")
    came = social.poll()
    assert came[0]["kind"] == "message" and came[0]["text"] == "💬 Ali Yılmaz: selam 👋"
    assert social.unread_count() == 1
    social.mark_seen(uid_of("ali", cloud))
    assert social.unread_count() == 0
    social.message(uid_of("ali", cloud), "naber")
    chat = social.load()["chats"][uid_of("ali", cloud)]
    assert [(m["me"], m["text"]) for m in chat] == [(False, "selam 👋"), (True, "naber")]


def test_a_recommended_song_and_its_answer(people, cloud):
    befriend(people, cloud)
    song = {"title": "Firuze", "artist": "Sezen Aksu", "url": "https://youtube.com/watch?v=f"}
    social.recommend(uid_of("veli", cloud), song)
    people("veli")
    came = social.poll()
    assert came[0]["text"] == "🎵 Ali Yılmaz sana bir şarkı öneriyor: Sezen Aksu - Firuze"
    note = social.load()["notes"][0]
    assert note["song"] == song
    social.feedback(note["id"], 1)
    assert social.load()["notes"][0]["answered"] == 1
    people("ali")
    came = social.poll()
    assert came[0]["text"] == "👍 Veli Yılmaz önerdiğin şarkıyı beğendi: Sezen Aksu - Firuze"


def test_a_like_is_told_to_every_friend(people, cloud):
    befriend(people, cloud)
    social.tell_like({"title": "Kuzu Kuzu", "artist": "Tarkan", "url": "https://y/k"}, -1)
    people("veli")
    assert social.poll()[0]["text"] == "👎 Ali Yılmaz bu şarkıyı beğenmedi: Tarkan - Kuzu Kuzu"


def test_the_public_card_shows_the_name_and_the_song_never_the_e_mail(people, cloud):
    befriend(people, cloud)
    social.publish_me(now_playing="Tarkan - Kuzu Kuzu")
    card = social.card(uid_of("ali", cloud))
    assert card["username"] == "ali" and card["name"] == "Ali Yılmaz" and card["now"] == "Tarkan - Kuzu Kuzu"
    assert "ali@gmail.com" not in json.dumps(cloud.store, ensure_ascii=False)
    people("veli")
    friend = social.friends(refresh=True)[uid_of("ali", cloud)]
    assert friend["online"] and friend["now"] == "Tarkan - Kuzu Kuzu"


# ------------------------------------------------------------------------------ 🗑 deleting the account
def test_deleting_the_account_takes_everything_and_tells_the_friends(people, cloud, tmp_path):
    befriend(people, cloud)
    ali = uid_of("ali", cloud)
    social.publish_me()
    from app import sharing
    sharing.share("Gece", [{"title": "x", "url": "https://y/x"}])
    with pytest.raises(account.AccountError, match="Şifre yanlış"):
        account.delete_account("yanlis99")
    assert account.signed_in()
    account.delete_account("gizli123")
    assert not account.signed_in() and "ali@gmail.com" not in cloud.users and "ali" not in cloud.usernames
    assert not [k for k in cloud.store if ali in k.split("/")[:2]] and cloud.shared == {}
    people("veli")
    came = social.poll()
    assert came[0]["text"] == "Ali Yılmaz DISO hesabını sildi" and social.friends() == {}
    people("ali")
    account.sign_up("Ali", "Yeni", "ali", "ali@gmail.com", "gizli456")   # the name and e-mail are free again


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
    again = playlists.PlaylistStore(str(tmp_path / "p.json"))
    assert again.rating(str(song)) == -1


def test_play_counts_and_ratings_follow_the_songs_to_another_computer(cloud, tmp_path):
    from test_account import ready, write, read
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
    stats = read(b, "playlists.json")["stats"]
    there = playlists.file_key(os.path.join(b, account.MUSIC_DIR_NAME, "s.mp3"))
    assert stats == {os.path.join(b, account.MUSIC_DIR_NAME, "s.mp3"): {"plays": 3, "rating": 1}} or \
        playlists._clean_stats(stats) == {there: {"plays": 3, "rating": 1}}


# ------------------------------------------------------------------------------ the windows
def test_the_friends_window_the_badge_and_the_song_menu(app, people, cloud, monkeypatch):
    from app import account_ui, notify
    from app.social_ui import FriendsWindow
    befriend(people, cloud)
    people("veli")
    social.message(uid_of("ali", cloud), "selam")
    people("ali")
    social.mark_seen()                                                   # (the "accepted" note: read)
    came = social.poll()
    toasts = []
    monkeypatch.setattr(notify, "toast", lambda title, body, path=None: toasts.append(body))
    app.cfg.set("notify_toast", True)
    monkeypatch.setattr(app, "focus_displayof", lambda: None)            # DISO is behind other windows
    app._social_came(came)
    assert toasts == ["💬 Veli Yılmaz: selam"] and account_ui.button_text().endswith("🔔 1")
    items = app.recommend_items([{"path": "x.mp3", "title": "x"}])
    assert items[0][0] == "Veli Yılmaz" and items[-1][0] == "👥 Arkadaşlar…"
    win = app.open_friends()
    assert isinstance(win, FriendsWindow) and win.chosen == uid_of("veli", cloud)
    assert "selam" in win.chat_text.get("1.0", "end")
    assert account_ui.button_text() == "👤 Ali Yılmaz"                  # read: the number goes
    win.msg_entry.insert(0, "naber")
    win.send_message()
    deadline = time.time() + 5
    while win.busy and time.time() < deadline:
        app._drain_ui_calls()
        app.update()
        time.sleep(0.02)
    assert ("u2", "message") in cloud.sent and "naber" in win.chat_text.get("1.0", "end")
    win.show_notes()
    win.destroy()
