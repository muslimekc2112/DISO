"""👥 The friends window: on the left the friends (online, what they listen to now), the groups, the requests that came
and the ones sent, a box to ask someone by user name; on the right the chat with the chosen friend or group (bubbles,
replies, reactions, songs / playlists / pictures / files, "is typing…"), or the notifications. See app/social.py."""
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import account, look, social
from .logs import log
from .social_dialogs import GroupDialog, InfoDialog, SongPicker
from .ui_common import fit_geometry, set_window_icon

ERROR_COLOR = ("#c0392b", "#ff7b72")
OK_COLOR = ("#1e8449", "#7ee2a8")
ONLINE_COLOR = "#2F9E63"
CHATS, NOTES = "💬 Sohbetler", "🔔 Bildirimler"
REFRESH_EVERY = 60 * 1000      # ms: friends' online state / songs, while the window is open
TYPING_SHOWN = 4.0             # s: "is typing…" stays this long
TYPING_EVERY = 3.0             # s: how often my own typing is told
REACTIONS = ("👍", "❤", "😂", "😮", "😢", "🙏")
STATUSES = {"🟢 Çevrimiçi": "online", "🌙 Rahatsız etme": "busy", "⚪ Görünmez": "invisible"}
RECENT = 40                    # songs of "last played" / "last downloaded"


def when(seconds) -> str:
    return time.strftime("%d.%m %H:%M", time.localtime(seconds))


def clock(seconds) -> str:
    return time.strftime("%H:%M", time.localtime(seconds))


def size_text(n) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / (1024 * 1024):.1f} MB"


class FriendsWindow(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.busy = 0
        self.title("DISO • Arkadaşlar")
        fit_geometry(self, 1000, 660)
        self.minsize(820, 500)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.bind("<Escape>", lambda e: self.destroy())
        self.me_uid = (account.load() or {}).get("uid", "")
        self.friends = social.friends()
        self.convs = []                    # [{"id", "kind", "name", ...}] (the last look)
        self.requests = {}                 # {uid: card}
        self.names = {self.me_uid: "Sen"}
        self.names.update({u: f.get("name") or f.get("username") or "?" for u, f in self.friends.items()})
        self.chosen = None                 # the conversation open on the right (its dict)
        self.msgs, self.reads = [], {}
        self.reply = None                  # the message being answered
        self.typing_at = {}                # {conv: (uid, until)}
        self._typed_at = 0.0
        self._refresh_job = None
        self._build_left()
        self._build_right()
        self.show_left()
        self.show_notes() if not self.friends and not social.load()["groups"] else self._show_chats_placeholder()
        self.refresh()

    # ------------------------------------------------------------------ work off the window's thread
    def run(self, work, then=None, failed=None):
        """work() on its own thread (the internet may be slow); then(result) back on the window's."""
        self.busy += 1

        def job():
            try:
                result, error = work(), None
            except account.AccountError as e:
                result, error = None, e
            except Exception:  # noqa: BLE001
                log.exception("friends")
                result, error = None, account.AccountError("Beklenmedik bir hata oldu. Ayrıntısı günlükte.")
            self.app._ui_calls.put(lambda: self._done(then, failed, result, error))
        threading.Thread(target=job, daemon=True, name="friends").start()

    def _done(self, then, failed, result, error):
        self.busy -= 1
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if error is not None:
            (failed or (lambda e: self.app.notice(f"👥 {e}", 8)))(error)
        elif then:
            then(result)

    # ------------------------------------------------------------------ the left side
    def _build_left(self):
        left = ctk.CTkFrame(self, width=320)
        left.grid(row=0, column=0, sticky="nsw", padx=(12, 6), pady=12)
        left.grid_propagate(False)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(4, weight=1)
        head = ctk.CTkFrame(left, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        head.columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="👥 Arkadaşlar", anchor="w", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w")
        self.more_btn = ctk.CTkButton(head, text="⋯", width=32, height=28, fg_color="transparent",
                                      text_color=("gray20", "gray85"), hover_color=look.ACCENT_SOFT,
                                      command=self._more_menu)
        self.more_btn.grid(row=0, column=1)
        me = social.me() if account.signed_in() else {"username": ""}
        ctk.CTkLabel(left, text=f"Sen: @{me['username']}" if me["username"] else "", text_color="gray", anchor="w").grid(
            row=1, column=0, sticky="ew", padx=14)
        self.status_menu = ctk.CTkOptionMenu(left, values=list(STATUSES), width=170, height=26,
                                             command=self._set_status)
        self.status_menu.set("🟢 Çevrimiçi")
        self.status_menu.grid(row=2, column=0, sticky="w", padx=12, pady=(2, 2))
        add = ctk.CTkFrame(left, fg_color="transparent")
        add.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 2))
        add.columnconfigure(0, weight=1)
        self.add_entry = ctk.CTkEntry(add, placeholder_text="Kullanıcı adı")
        self.add_entry.grid(row=0, column=0, sticky="ew")
        self.add_entry.bind("<Return>", lambda e: self.send_request())
        self.add_btn = ctk.CTkButton(add, text="➕ İstek", width=76, command=self.send_request)
        self.add_btn.grid(row=0, column=1, padx=(6, 0))
        self.group_btn = ctk.CTkButton(add, text="👥 Grup", width=70, command=self.new_group)
        self.group_btn.grid(row=0, column=2, padx=(6, 0))
        self.add_status = ctk.CTkLabel(add, text="", font=ctk.CTkFont(size=11), wraplength=290, anchor="w",
                                       justify="left")
        self.add_status.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.left_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.left_list.grid(row=4, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.left_list.columnconfigure(0, weight=1)
        cfg = self.app.cfg                                             # 🔒 what friends may see of me
        self.listening_var = ctk.BooleanVar(value=bool(cfg.get("share_listening")))
        ctk.CTkCheckBox(left, text="Dinlediğimi arkadaşlarım görsün", variable=self.listening_var,
                        font=ctk.CTkFont(size=12), command=self._set_listening).grid(
            row=5, column=0, sticky="w", padx=12, pady=(2, 2))
        self.likes_var = ctk.BooleanVar(value=bool(cfg.get("share_likes")))
        ctk.CTkCheckBox(left, text="Beğendiklerimi arkadaşlarıma bildir", variable=self.likes_var,
                        font=ctk.CTkFont(size=12),
                        command=lambda: cfg.set("share_likes", bool(self.likes_var.get()))).grid(
            row=6, column=0, sticky="w", padx=12, pady=(2, 10))

    def show_left(self):
        for w in self.left_list.winfo_children():
            w.destroy()
        data = social.load()
        row = 0

        def heading(text):
            nonlocal row
            ctk.CTkLabel(self.left_list, text=text, anchor="w", text_color="gray",
                         font=ctk.CTkFont(size=12, weight="bold")).grid(row=row, column=0, sticky="ew", pady=(8, 2))
            row += 1

        if data["requests"]:
            heading(f"Gelen istekler ({len(data['requests'])})")
            for uid, r in data["requests"].items():
                box = ctk.CTkFrame(self.left_list)
                box.grid(row=row, column=0, sticky="ew", pady=2)
                box.columnconfigure(0, weight=1)
                ctk.CTkLabel(box, text=f"{r.get('name') or r.get('username')}\n@{r.get('username', '')}", anchor="w",
                             justify="left").grid(row=0, column=0, sticky="ew", padx=8, pady=4)
                ctk.CTkButton(box, text="✔", width=34, command=lambda u=uid: self.answer(u, True)).grid(
                    row=0, column=1, padx=2)
                ctk.CTkButton(box, text="✖", width=34, fg_color="transparent", border_width=1,
                              text_color=("gray20", "gray85"), command=lambda u=uid: self.answer(u, False)).grid(
                    row=0, column=2, padx=(2, 6))
                row += 1
        groups = [c for c in self.convs if c["kind"] == "group"]
        by_peer = {c["peer"]: c for c in self.convs if c["kind"] == "direct"}
        if groups:
            heading(f"Gruplar ({len(groups)})")
            for c in sorted(groups, key=lambda c: (-self._unread(c["id"]), c["name"].lower())):
                self._chat_row(row, c["id"], c["emoji"], c["name"], "Grup" + (" · yönetici" if c["role"] == "admin" else ""),
                               self._unread(c["id"]), c["id"] == (self.chosen or {}).get("id"), None, c)
                row += 1
        heading(f"Arkadaşların ({len(self.friends)})")
        if not self.friends:
            ctk.CTkLabel(self.left_list, text="Henüz arkadaşın yok. Yukarıya bir kullanıcı adı yaz.",
                         text_color="gray", wraplength=270, justify="left").grid(row=row, column=0, sticky="w")
            row += 1
        for uid, f in sorted(self.friends.items(), key=lambda i: (not i[1].get("online"), i[1].get("name", "").lower())):
            conv = by_peer.get(uid)
            cid = (conv or {}).get("id") or data["direct"].get(uid)
            sub = f"@{f.get('username', '')}"
            if f.get("now"):
                sub += f"\n🎵 {f['now']}"
            elif f.get("seen") and not f.get("online"):
                sub += f"\nSon görülme: {when(f['seen'])}"
            self._chat_row(row, cid, None, f.get("name") or f.get("username") or "?", sub, self._unread(cid),
                           bool(self.chosen) and self.chosen.get("peer") == uid, f, conv, uid)
            row += 1
        if data["outgoing"]:
            heading("Gönderdiğin istekler")
            for uid, o in data["outgoing"].items():
                box = ctk.CTkFrame(self.left_list, fg_color="transparent")
                box.grid(row=row, column=0, sticky="ew")
                box.columnconfigure(0, weight=1)
                ctk.CTkLabel(box, text=f"⏳ @{o.get('username', '')}", anchor="w", text_color="gray").grid(
                    row=0, column=0, sticky="ew", padx=4)
                ctk.CTkButton(box, text="Geri al", width=60, height=24, fg_color="transparent",
                              text_color=("gray30", "gray70"), command=lambda u=uid: self.take_back(u)).grid(
                    row=0, column=1)
                row += 1

    @staticmethod
    def _unread(cid):
        return social.load()["unread"].get(cid, 0) if cid else 0

    def _chat_row(self, row, cid, emoji, name, sub, unread, chosen, friend, conv=None, uid=None):
        """One friend or group: a dot or an emoji, the name, the unread count, and what is worth a line."""
        card = ctk.CTkFrame(self.left_list, corner_radius=10, fg_color=look.ACCENT_SOFT if chosen else "transparent",
                            cursor="hand2")
        card.grid(row=row, column=0, sticky="ew", pady=1)
        card.columnconfigure(1, weight=1)
        online = bool(friend and friend.get("online"))
        mark = ctk.CTkLabel(card, text=emoji or "●", width=22,
                            text_color=("gray20", "gray85") if emoji else (ONLINE_COLOR if online else "gray"),
                            font=ctk.CTkFont(size=16 if emoji else 12))
        mark.grid(row=0, column=0, padx=(8, 4), pady=(6, 0), sticky="n")
        title = ctk.CTkLabel(card, text=name, anchor="w", font=ctk.CTkFont(weight="bold"))
        title.grid(row=0, column=1, sticky="ew", pady=(6, 0))
        lines = sub.split("\n")
        labels = [ctk.CTkLabel(card, text=t, anchor="w", font=ctk.CTkFont(size=11), text_color=(
            look.ACCENT if t.startswith("🎵") and look.is_new() else "gray")) for t in lines]
        for i, lab in enumerate(labels):
            lab.grid(row=i + 1, column=1, sticky="ew", pady=(0, 6 if i == len(labels) - 1 else 0))
        widgets = [card, mark, title, *labels]
        if unread:
            badge = ctk.CTkLabel(card, text=str(unread), width=22, height=22, corner_radius=11,
                                 fg_color=look.ACCENT if look.is_new() else "#1F6AA5", text_color="white",
                                 font=ctk.CTkFont(size=11, weight="bold"))
            badge.grid(row=0, column=2, padx=8, pady=(6, 0), sticky="n")
            widgets.append(badge)
        for w in widgets:
            w.bind("<Button-1>", lambda e, c=cid, u=uid, cv=conv: self.choose(c, u, cv))
            if friend is not None:
                w.bind("<Button-3>", lambda e, u=uid: self._friend_menu(e, u))

    def _friend_menu(self, event, uid):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="💬 Mesaj yaz", command=lambda: self.choose(None, uid, None))
        menu.add_command(label="ⓘ Bilgi", command=lambda: self.choose(None, uid, None, info=True))
        menu.tk_popup(event.x_root, event.y_root)

    def _more_menu(self):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="⛔ Engellediklerim…", command=self.show_blocked)
        menu.add_command(label="🔔 Bildirimler", command=self.show_notes)
        menu.tk_popup(self.more_btn.winfo_rootx(), self.more_btn.winfo_rooty() + 30)

    def show_blocked(self):
        def got(found):
            menu = tk.Menu(self, tearoff=0)
            if not found:
                menu.add_command(label="Kimseyi engellemedin", state="disabled")
            for uid, c in found.items():
                menu.add_command(label=f"Engeli kaldır: {c.get('name')} (@{c.get('username')})",
                                 command=lambda u=uid: self.run(lambda: social.unblock(u), lambda _: self.app.notice(
                                     "Engel kaldırıldı", 6)))
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        self.run(social.blocked, got)

    def _set_status(self, label):
        status = STATUSES.get(label, "online")
        self.run(lambda: social.publish_me(status=status), None, lambda e: None)

    def _set_listening(self):
        self.app.cfg.set("share_listening", bool(self.listening_var.get()))
        music = self.app.music
        playing = music.controller.current_track() if music is not None and music.controller.state != "stopped" \
            else None
        self.app._now_told = None
        self.app.music_now_playing(playing)                # shown / taken away at once

    # ------------------------------------------------------------------ the right side
    def _build_right(self):
        right = ctk.CTkFrame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        self.tabs = ctk.CTkSegmentedButton(right, values=[CHATS, NOTES], command=self._tab)
        self.tabs.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))
        self.chat_box = ctk.CTkFrame(right, fg_color="transparent")
        self.chat_box.columnconfigure(0, weight=1)
        self.chat_box.rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self.chat_box, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=4)
        head.columnconfigure(0, weight=1)
        self.chat_title = ctk.CTkLabel(head, text="", anchor="w", font=ctk.CTkFont(size=16, weight="bold"))
        self.chat_title.grid(row=0, column=0, sticky="ew")
        self.chat_sub = ctk.CTkLabel(head, text="", anchor="w", text_color="gray", font=ctk.CTkFont(size=11))
        self.chat_sub.grid(row=1, column=0, sticky="ew")
        self.search_btn = ctk.CTkButton(head, text="🔍", width=34, height=28, fg_color="transparent",
                                        text_color=("gray20", "gray85"), hover_color=look.ACCENT_SOFT,
                                        command=self.toggle_search)
        self.search_btn.grid(row=0, column=1, rowspan=2, padx=2)
        self.info_btn = ctk.CTkButton(head, text="⋮", width=34, height=28, fg_color="transparent",
                                      text_color=("gray20", "gray85"), hover_color=look.ACCENT_SOFT,
                                      font=ctk.CTkFont(size=18, weight="bold"), command=self.chat_menu)
        self.info_btn.grid(row=0, column=2, rowspan=2, padx=2)
        self.search_entry = ctk.CTkEntry(head, placeholder_text="Bu sohbette ara…")
        self.search_entry.bind("<Return>", lambda e: self.do_search())
        self.msg_box = ctk.CTkScrollableFrame(self.chat_box, fg_color="transparent")
        self.msg_box.grid(row=1, column=0, sticky="nsew", pady=4)
        self.msg_box.columnconfigure(0, weight=1)
        self.typing_label = ctk.CTkLabel(self.chat_box, text="", anchor="w", text_color="gray",
                                         font=ctk.CTkFont(size=11, slant="italic"))
        self.typing_label.grid(row=2, column=0, sticky="ew", padx=8)
        self.reply_bar = ctk.CTkFrame(self.chat_box, fg_color=look.ACCENT_SOFT, corner_radius=8)
        self.reply_label = ctk.CTkLabel(self.reply_bar, text="", anchor="w", wraplength=480, justify="left")
        self.reply_label.grid(row=0, column=0, sticky="ew", padx=8, pady=4)
        self.reply_bar.columnconfigure(0, weight=1)
        ctk.CTkButton(self.reply_bar, text="✖", width=26, height=22, fg_color="transparent",
                      text_color=("gray20", "gray85"), command=self.cancel_reply).grid(row=0, column=1, padx=4)
        send = ctk.CTkFrame(self.chat_box, fg_color="transparent")
        send.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        send.columnconfigure(1, weight=1)
        self.plus_btn = ctk.CTkButton(send, text="➕", width=40, command=self.plus_menu)
        self.plus_btn.grid(row=0, column=0, padx=(0, 6))
        self.msg_entry = ctk.CTkEntry(send, placeholder_text="Mesaj yaz…")
        self.msg_entry.grid(row=0, column=1, sticky="ew")
        self.msg_entry.bind("<Return>", lambda e: self.send_message())
        self.msg_entry.bind("<Key>", self._typed, add="+")
        self.send_btn = ctk.CTkButton(send, text="Gönder", width=84, command=self.send_message)
        self.send_btn.grid(row=0, column=2, padx=(6, 0))
        self.notes_box = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.notes_box.columnconfigure(0, weight=1)
        self.placeholder = ctk.CTkLabel(right, text="Soldan bir arkadaşını ya da grubunu seç.\n\nYeni biriyle "
                                                    "konuşmak için kullanıcı adını yazıp ➕ İstek de.",
                                        text_color="gray", justify="center")

    def _show_chats_placeholder(self):
        self.tabs.set(CHATS)
        self.notes_box.grid_remove()
        self.chat_box.grid_remove()
        self.placeholder.grid(row=2, column=0)

    def _tab(self, which):
        if which == NOTES:
            self.show_notes()
        elif self.chosen:
            self._show_chat()
        else:
            self._show_chats_placeholder()

    # ------------------------------------------------------------------ choosing a chat
    def choose(self, cid, uid=None, conv=None, info=False):
        """Open a chat: a conversation id, or a friend (the chat of two is made the first time)."""
        self.cancel_reply()
        self.close_search()
        if cid is None and uid is not None:
            cid = social.load()["direct"].get(uid)
        if cid is None and uid is not None:
            f = self.friends.get(uid) or {}
            self.run(lambda: social.direct(uid), lambda c: (self.refresh_now(), self.choose(c, uid, None, info)),
                     lambda e: self.app.notice(f"💬 {f.get('name', '')}: {e}", 8))
            return
        found = next((c for c in self.convs if c["id"] == cid), None) or conv or {
            "id": cid, "kind": "direct", "name": (self.friends.get(uid) or {}).get("name", "?"), "emoji": "👤",
            "about": "", "only_admins": False, "role": "member", "muted": False, "peer": uid, "unread": 0}
        self.chosen = found
        self.msgs, self.reads = [], {}
        self._show_chat()
        self.run(lambda: self._load(found["id"]), lambda got: self._loaded(found["id"], got),
                 lambda e: self.chat_sub.configure(text=str(e), text_color=ERROR_COLOR))
        if info:
            self.open_info()
        self.show_left()

    def _load(self, cid):
        msgs = social.messages(cid)
        marks = social.read_marks(cid) if self.chosen and self.chosen["kind"] == "direct" else {}
        missing = {m["sender"] for m in msgs if m["sender"] and m["sender"] not in self.names}
        missing |= {m["body"].partition(":")[2] for m in msgs if m["kind"] == "system" and ":" in m["body"]} - set(self.names)
        cards = social.profiles(missing) if missing else {}
        return msgs, marks, {u: c["name"] for u, c in cards.items()}

    def _loaded(self, cid, got):
        if not self.chosen or self.chosen["id"] != cid:
            return
        msgs, marks, names = got
        self.names.update(names)
        self.msgs, self.reads = msgs, marks
        self.render()
        self.run(lambda: social.read(cid), lambda _: (self.app.social_changed(refresh_window=False), self.show_left()),
                 lambda e: None)

    def _show_chat(self):
        self.tabs.set(CHATS)
        self.placeholder.grid_remove()
        self.notes_box.grid_remove()
        self.chat_box.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        c = self.chosen
        self.chat_title.configure(text=(f"{c['emoji']} " if c["kind"] == "group" else "") + c["name"])
        self._sub()
        can_write = not (c["kind"] == "group" and c.get("only_admins") and c["role"] != "admin")
        for w in (self.msg_entry, self.send_btn, self.plus_btn):
            w.configure(state="normal" if can_write else "disabled")
        self.msg_entry.configure(placeholder_text="Mesaj yaz…" if can_write else "Bu grupta yalnız yöneticiler yazabilir")

    def _sub(self):
        c = self.chosen
        if not c:
            return
        mine = self.typing_at.get(c["id"])
        if mine and mine[1] > time.time():
            self.chat_sub.configure(text=f"{self.names.get(mine[0], 'Biri')} yazıyor…", text_color=OK_COLOR)
            return
        if c["kind"] == "group":
            self.chat_sub.configure(text=c.get("about") or "Grup", text_color="gray")
            return
        f = self.friends.get(c["peer"]) or {}
        text = ("● çevrimiçi" if f.get("online") else (f"Son görülme: {when(f['seen'])}" if f.get("seen") else ""))
        if f.get("now"):
            text += f"   🎵 {f['now']}"
        self.chat_sub.configure(text=text.strip(), text_color=ONLINE_COLOR if f.get("online") else "gray")

    # ------------------------------------------------------------------ the messages
    def render(self):
        for w in self.msg_box.winfo_children():
            w.destroy()
        if not self.msgs:
            ctk.CTkLabel(self.msg_box, text="Henüz mesaj yok. İlk mesajı sen yaz 👋", text_color="gray").grid(row=0, column=0, pady=30)
        for i, m in enumerate(self.msgs):
            self._bubble(i, m)
        self._to_end()

    def _to_end(self):
        self.update_idletasks()
        try:
            self.msg_box._parent_canvas.yview_moveto(1.0)
        except tk.TclError:
            pass

    def _bubble(self, i, m):
        group = self.chosen and self.chosen["kind"] == "group"
        mine = m["sender"] == self.me_uid
        row = ctk.CTkFrame(self.msg_box, fg_color="transparent")
        row.grid(row=i, column=0, sticky="ew")
        row.columnconfigure(0 if not mine else 1, weight=1)
        if m["kind"] == "system":
            text = social.system_text(m["body"], self.names)
            if text:
                ctk.CTkLabel(row, text=text, text_color="gray", font=ctk.CTkFont(size=11)).grid(row=0, column=0, columnspan=2, pady=4)
            return
        accent = look.ACCENT if look.is_new() else "#1F6AA5"
        holder = ctk.CTkFrame(row, corner_radius=14, fg_color=accent if mine else look.CARD_HIGH)
        holder.grid(row=0, column=1 if mine else 0, sticky="e" if mine else "w", padx=8, pady=3)
        ink = ("white", "white") if mine else look.TEXT
        grey = ("#E8D8EF", "#E8D8EF") if mine else "gray"
        widgets = [row, holder]
        r = 0

        def add(w, **grid):
            nonlocal r
            w.grid(row=r, column=0, sticky="w", padx=grid.pop("padx", 12), pady=grid.pop("pady", (0, 0)), **grid)
            widgets.append(w)
            r += 1
        if group and not mine:
            add(ctk.CTkLabel(holder, text=self.names.get(m["sender"], "?"), text_color=accent if not mine else grey,
                             font=ctk.CTkFont(size=11, weight="bold")), pady=(6, 0))
        if m.get("reply_to"):
            quoted = next((x for x in self.msgs if x["id"] == m["reply_to"]), None)
            if quoted:
                add(ctk.CTkLabel(holder, text="↩ " + self.names.get(quoted["sender"], "?") + ": " +
                                 (quoted["body"] or "…")[:60], text_color=grey, font=ctk.CTkFont(size=11),
                                 anchor="w"), pady=(6, 0))
        if m["deleted"]:
            add(ctk.CTkLabel(holder, text="🚫 Bu mesaj silindi", text_color=grey, font=ctk.CTkFont(slant="italic")),
                pady=(6, 6))
        else:
            self._content(holder, m, mine, ink, grey, add)
        stamp = clock(m["at"]) + (("  " + ("✓✓" if self._seen(m) else "✓")) if mine and not group else "")
        add(ctk.CTkLabel(holder, text=stamp, text_color=grey, font=ctk.CTkFont(size=10)), pady=(0, 4))
        if m["reactions"]:
            chips = ctk.CTkFrame(row, fg_color="transparent")
            chips.grid(row=1, column=1 if mine else 0, sticky="e" if mine else "w", padx=12)
            for emoji, users in m["reactions"].items():
                chip = ctk.CTkLabel(chips, text=f"{emoji} {len(users)}", corner_radius=10, height=20,
                                    fg_color=look.ACCENT_SOFT if self.me_uid in users else look.CARD_HIGH,
                                    font=ctk.CTkFont(size=11))
                chip.pack(side="left", padx=2)
                chip.bind("<Button-1>", lambda e, m=m, em=emoji: self.toggle_reaction(m, em))
        for w in widgets:
            w.bind("<Button-3>", lambda e, m=m: self._message_menu(e, m))

    def _seen(self, m) -> bool:
        return any(u != self.me_uid and t >= m["at"] for u, t in self.reads.items())

    def _content(self, holder, m, mine, ink, grey, add):
        kind, p = m["kind"], m.get("payload") or {}
        if kind == "song" and isinstance(p, dict):
            add(ctk.CTkLabel(holder, text="🎵 " + social.song_name(p), text_color=ink, anchor="w", wraplength=380,
                             justify="left", font=ctk.CTkFont(weight="bold")), pady=(8, 2))
            actions = ctk.CTkFrame(holder, fg_color="transparent")
            ctk.CTkButton(actions, text="⬇ İndir", width=74, height=26, command=lambda: self.get_song(p)).pack(side="left", padx=(0, 4))
            if not mine:
                for v, t in ((1, "👍"), (-1, "👎")):
                    ctk.CTkButton(actions, text=t, width=34, height=26, command=lambda v=v, m=m: self.answer_song(m, v)).pack(
                        side="left", padx=2)
            add(actions, pady=(0, 6))
        elif kind == "playlist" and isinstance(p, dict):
            songs = p.get("songs") or []
            add(ctk.CTkLabel(holder, text=f"📋 {p.get('name') or m['body']}  ·  {len(songs)} şarkı", text_color=ink,
                             anchor="w", font=ctk.CTkFont(weight="bold")), pady=(8, 2))
            add(ctk.CTkButton(holder, text="⬇ Listeyi ekle ve indir", width=170, height=26,
                              command=lambda: self.app.take_shared({"name": p.get("name") or m["body"], "songs": songs})),
                pady=(0, 6))
        elif kind in ("image", "file") and isinstance(p, dict):
            add(ctk.CTkLabel(holder, text=("🖼 " if kind == "image" else "📎 ") + str(p.get("name", "dosya")) +
                             f"  ·  {size_text(int(p.get('size') or 0))}", text_color=ink, anchor="w", wraplength=380,
                             justify="left"), pady=(8, 2))
            actions = ctk.CTkFrame(holder, fg_color="transparent")
            ctk.CTkButton(actions, text="⬇ Kaydet", width=80, height=26, command=lambda: self.save_file(p)).pack(side="left", padx=(0, 4))
            ctk.CTkButton(actions, text="Aç", width=50, height=26, fg_color="transparent", border_width=1,
                          text_color=ink, command=lambda: self.save_file(p, open_it=True)).pack(side="left", padx=2)
            add(actions, pady=(0, 6))
        else:
            add(ctk.CTkLabel(holder, text=m["body"], text_color=ink, anchor="w", justify="left", wraplength=420),
                pady=(6, 2))

    def _message_menu(self, event, m):
        if m["deleted"]:
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="↩ Yanıtla", command=lambda: self.start_reply(m))
        react = tk.Menu(menu, tearoff=0)
        for emoji in REACTIONS:
            react.add_command(label=emoji, command=lambda em=emoji: self.toggle_reaction(m, em))
        menu.add_cascade(label="😊 Tepki ver", menu=react)
        if m["kind"] == "text":
            menu.add_command(label="📋 Kopyala", command=lambda: (self.clipboard_clear(), self.clipboard_append(m["body"])))
        if m["kind"] == "song" and isinstance(m.get("payload"), dict):
            menu.add_command(label="⬇ Şarkıyı indir", command=lambda: self.get_song(m["payload"]))
        if m["sender"] == self.me_uid:
            menu.add_separator()
            menu.add_command(label="🗑 Sil (herkesten)", command=lambda: self.delete_message(m))
        menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------------ sending
    def send_message(self):
        text = self.msg_entry.get().strip()
        c = self.chosen
        if not text or not c:
            return
        self.msg_entry.delete(0, "end")
        reply = self.reply["id"] if self.reply else None
        self.cancel_reply()
        payload = self._mentions(text) if c["kind"] == "group" else None
        self.run(lambda: social.send(c["id"], text, payload=payload, reply_to=reply), self._sent,
                 lambda e: (self.msg_entry.insert(0, text), self.app.notice(f"💬 Gönderilemedi: {e}", 8)))

    def _mentions(self, text):
        """@user names in a group message: the ones who are in the group are told."""
        import re
        names = {f.get("username"): u for u, f in self.friends.items() if f.get("username")}
        found = [names[w] for w in re.findall(r"@([a-z0-9._]{3,20})", text.lower()) if w in names]
        return {"mentions": found} if found else None

    def _sent(self, made):
        if made and self.chosen and made.get("conv") == self.chosen["id"] and all(m["id"] != made["id"] for m in self.msgs):
            self.msgs.append(made)
            self.render()

    def _typed(self, event=None):
        if self.chosen and time.time() - self._typed_at > TYPING_EVERY and self.app.live is not None:
            self._typed_at = time.time()
            self.app.live.typing(self.chosen["id"])

    def start_reply(self, m):
        self.reply = m
        label = social.song_name(m["payload"]) if m["kind"] == "song" else (m["body"] or "…")
        self.reply_label.configure(text=f"↩ {self.names.get(m['sender'], '?')}: {label[:90]}")
        self.reply_bar.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        self.msg_entry.focus_set()

    def cancel_reply(self):
        self.reply = None
        self.reply_bar.grid_remove()

    def toggle_reaction(self, m, emoji):
        mine = self.me_uid in m["reactions"].get(emoji, [])
        self.run(lambda: social.unreact(m["id"]) if mine else social.react(m["id"], emoji), lambda _: self.reload_chat())

    def delete_message(self, m):
        if messagebox.askyesno("DISO", "Bu mesaj herkesten silinsin mi?", parent=self):
            self.run(lambda: social.delete_message(m["id"]), lambda _: self.reload_chat())

    def reload_chat(self):
        if self.chosen:
            cid = self.chosen["id"]
            self.run(lambda: self._load(cid), lambda got: self._loaded(cid, got))

    # ------------------------------------------------------------------ ➕: songs, a playlist, a picture, a file
    def plus_menu(self):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="🎵 Müzik listemden şarkı…", command=self.pick_from_list)
        menu.add_command(label="🕘 Son dinlenenler…", command=self.pick_played)
        menu.add_command(label="⬇ Son indirilenler…", command=self.pick_downloaded)
        menu.add_command(label="📋 Bir çalma listesinin hepsi…", command=self.pick_playlist)
        menu.add_separator()
        menu.add_command(label="🖼 Resim gönder…", command=lambda: self.pick_file(True))
        menu.add_command(label="📁 Bilgisayardan dosya gönder…", command=lambda: self.pick_file(False))
        menu.tk_popup(self.plus_btn.winfo_rootx(), self.plus_btn.winfo_rooty() - 130)

    def _tracks_entries(self, tracks):
        from .player import artist_and_title
        out = []
        for t in tracks:
            artist, title = artist_and_title(t)
            out.append((f"{artist} - {title}" if artist else title, t))
        return out

    def pick_from_list(self):
        store = self.app._store()
        names = store.names()

        def fill(dialog, name):
            dialog.set_entries(self._tracks_entries(store.tracks(name)))
        SongPicker(self, "Müzik listemden şarkı", self._tracks_entries(store.tracks(names[0])), self.send_tracks,
                   lists=names, on_list=fill)

    def pick_played(self):
        store, seen, tracks = self.app._store(), set(), []
        for e in reversed(store.log):
            key = e.get("k")
            if key in seen:
                continue
            seen.add(key)
            t = store._track_by_key(key) or {"path": key, "title": e.get("title", ""), "artist": e.get("artist", "")}
            tracks.append({**t, "title": t.get("title") or e.get("title", ""), "artist": t.get("artist") or e.get("artist", "")})
            if len(tracks) >= RECENT:
                break
        SongPicker(self, "Son dinlenenler", self._tracks_entries(tracks), self.send_tracks)

    def pick_downloaded(self):
        """The last downloads (music and video): their link is known from the history, nothing to look up."""
        entries = []
        for e in reversed(self.app.history.entries):
            if e.get("url") and len(entries) < RECENT:
                title = e.get("title") or os.path.basename(e.get("path", "")) or e["url"]
                entries.append((title, {"title": title, "artist": "", "url": e["url"]}))
        SongPicker(self, "Son indirilenler", entries, self.send_links)

    def pick_playlist(self):
        store = self.app._store()
        names = [n for n in store.user_names() if store.tracks(n)]
        if not names:
            self.app.notice("Gönderilecek çalma listesi yok", 6)
            return
        menu = tk.Menu(self, tearoff=0)
        for n in names:
            menu.add_command(label=f"{n}  ({len(store.tracks(n))})", command=lambda n=n: self.send_playlist(n))
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def send_tracks(self, chosen):
        """Songs of the music player: their links are found (the download history, else YouTube Music), then sent."""
        c, tracks = self.chosen, [v for _l, v in chosen]
        if not c:
            return
        self.app.notice(f"🔎 {len(tracks)} şarkının linki bulunuyor…", 6)
        self.run(lambda: [social.send(c["id"], social.song_name(s), "song", s) for s in self.app.song_links(tracks)],
                 lambda sent: (self.app.notice(f"🎵 {len(sent)} şarkı gönderildi" if sent else
                                               "Bu şarkıların linkini bulamadım", 6), self.reload_chat()))

    def send_links(self, chosen):
        c = self.chosen
        if not c:
            return
        self.run(lambda: [social.send(c["id"], social.song_name(v), "song", v) for _l, v in chosen],
                 lambda sent: (self.app.notice(f"🎵 {len(sent)} şarkı gönderildi", 6), self.reload_chat()))

    def send_playlist(self, name):
        c, tracks = self.chosen, list(self.app._store().tracks(name))
        if not c:
            return
        self.app.notice(f"🔎 “{name}” listesinin linkleri bulunuyor…", 8)
        self.run(lambda: social.send_playlist(c["id"], name, self.app.song_links(tracks)),
                 lambda _: (self.app.notice(f"📋 “{name}” gönderildi", 6), self.reload_chat()))

    def pick_file(self, picture):
        c = self.chosen
        if not c:
            return
        types = [("Resimler", "*.png *.jpg *.jpeg *.gif *.webp *.bmp")] if picture else [("Hepsi", "*.*")]
        path = filedialog.askopenfilename(parent=self, title="Resim seç" if picture else "Dosya seç", filetypes=types)
        if not path:
            return
        self.app.notice(f"⬆ Gönderiliyor: {os.path.basename(path)}", 8)
        self.run(lambda: social.upload(c["id"], path), lambda _: (self.app.notice("✔ Gönderildi", 5), self.reload_chat()),
                 lambda e: self.app.notice(f"📎 Gönderemedim: {e}", 10))

    def save_file(self, payload, open_it=False):
        from .utils import default_download_dir
        self.run(lambda: social.download(payload, os.path.join(default_download_dir(), "DISO arkadaş dosyaları")),
                 lambda path: (self.app.notice(f"⬇ Kaydedildi: {path}", 8), open_it and os.startfile(path)),
                 lambda e: self.app.notice(f"📎 İndiremedim: {e}", 10))

    def get_song(self, song):
        if song.get("url"):
            self.app.download_song({"url": song["url"], "title": social.song_name(song)})
            self.app.notice(f"⬇ İndiriliyor: {social.song_name(song)}", 6)

    def answer_song(self, m, value):
        self.run(lambda: social.feedback_song(m["sender"], m.get("payload"), value),
                 lambda _: self.app.notice("👍 Cevabın gönderildi" if value > 0 else "👎 Cevabın gönderildi", 5))

    # ------------------------------------------------------------------ search, info
    def toggle_search(self):
        if self.search_entry.winfo_manager():
            self.close_search()
            self.reload_chat()
        elif self.chosen:
            self.search_entry.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
            self.search_entry.focus_set()

    def close_search(self):
        self.search_entry.grid_remove()
        self.search_entry.delete(0, "end")

    def do_search(self):
        text, c = self.search_entry.get().strip(), self.chosen
        if text and c:
            self.run(lambda: social.search(c["id"], text), lambda found: (setattr(self, "msgs", found), self.render()))

    def chat_menu(self):
        c = self.chosen
        if not c:
            return
        group = c["kind"] == "group"
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="👥 Grup bilgisi ve üyeler" if group else "👤 Kişi bilgisi", command=self.open_info)
        menu.add_command(label="🔍 Sohbette ara", command=self.toggle_search)
        menu.add_separator()
        muted = bool(c.get("muted"))
        menu.add_command(label="🔔 Sesi aç" if muted else "🔕 Sessize al", command=lambda: self.mute_chat(not muted))
        menu.add_command(label="🔄 Sohbeti yenile", command=self.reload_chat)
        if group:
            menu.add_separator()
            menu.add_command(label="➕ Gruba kişi ekle", command=self.open_info)
            menu.add_command(label="🚪 Gruptan çık", command=self.open_info)
        else:
            menu.add_separator()
            menu.add_command(label="🚫 Engelle / arkadaşlıktan çıkar", command=self.open_info)
        x = self.info_btn.winfo_rootx() + self.info_btn.winfo_width()
        y = self.info_btn.winfo_rooty() + self.info_btn.winfo_height()
        try:
            menu.tk_popup(x - 150, y)
        finally:
            menu.grab_release()

    def mute_chat(self, on):
        c = self.chosen
        if c:
            c["muted"] = on
            self.run(lambda: social.mute(c["id"], on), lambda _: self.refresh_now())

    def open_info(self):
        if self.chosen:
            InfoDialog(self, self.chosen)

    def new_group(self):
        GroupDialog(self, self.friends)

    def after_group(self, conv):
        self.refresh_now()
        self.choose(conv)

    def after_leave(self, cid):
        if self.chosen and self.chosen["id"] == cid:
            self.chosen = None
            self._show_chats_placeholder()
        self.refresh_now()

    # ------------------------------------------------------------------ notifications
    def show_notes(self):
        self.tabs.set(NOTES)
        self.chat_box.grid_remove()
        self.placeholder.grid_remove()
        self.notes_box.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        for w in self.notes_box.winfo_children():
            w.destroy()
        notes = social.load()["notes"]
        if not notes:
            ctk.CTkLabel(self.notes_box, text="Henüz bildirim yok. Arkadaşların şarkı önerince, beğenince burada "
                                              "görünür.", text_color="gray", wraplength=420).grid(row=0, column=0)
        for i, n in enumerate(notes[:80]):
            box = ctk.CTkFrame(self.notes_box)
            box.grid(row=i, column=0, sticky="ew", pady=3)
            box.columnconfigure(0, weight=1)
            ctk.CTkLabel(box, text=n["text"], anchor="w", justify="left", wraplength=420,
                         font=ctk.CTkFont(weight="normal" if n.get("seen") else "bold")).grid(
                row=0, column=0, sticky="ew", padx=10, pady=(6, 0))
            ctk.CTkLabel(box, text=when(n["at"]), anchor="w", text_color="gray", font=ctk.CTkFont(size=11)).grid(
                row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
            if n.get("song") and n["kind"] in ("recommend", "like"):
                actions = ctk.CTkFrame(box, fg_color="transparent")
                actions.grid(row=0, column=1, rowspan=2, padx=8)
                ctk.CTkButton(actions, text="⬇ İndir", width=70, command=lambda n=n: self.get_song(n["song"])).pack(
                    side="left", padx=2)
                if n["kind"] == "recommend":
                    for v, t in ((1, "👍"), (-1, "👎")):
                        b = ctk.CTkButton(actions, text=t, width=36, command=lambda n=n, v=v: self.answer_note(n, v))
                        b.pack(side="left", padx=2)
                        if n.get("answered"):
                            b.configure(state="disabled")
            if n.get("conv"):
                ctk.CTkButton(box, text="Sohbete git", width=90, height=24, fg_color="transparent", border_width=1,
                              text_color=("gray20", "gray85"), command=lambda n=n: self.choose(n["conv"])).grid(
                    row=2, column=0, sticky="w", padx=10, pady=(0, 6))
        social.mark_seen()
        self.app.social_changed(refresh_window=False)

    def answer_note(self, n, value):
        self.run(lambda: social.feedback(n["id"], value), lambda _: self.show_notes())

    # ------------------------------------------------------------------ the lists, from the server
    def refresh(self):
        """The friends' state, the chats and the requests again (and every REFRESH_EVERY while the window is open)."""
        def work():
            return social.friends(refresh=True), social.conversations(), social.requests_in()

        def got(result):
            self.friends, self.convs, self.requests = result
            self.names.update({u: f.get("name") or f.get("username") or "?" for u, f in self.friends.items()})
            if self.chosen:
                self.chosen = next((c for c in self.convs if c["id"] == self.chosen["id"]), self.chosen)
                self._sub()
            self.show_left()
            self.app.social_changed(refresh_window=False)
        self.run(work, got, lambda e: None)
        self._refresh_job = self.after(REFRESH_EVERY, self.refresh)

    def refresh_now(self):
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
        self.refresh()

    def came_in(self):
        """Something came (see App._social_came): the lists as the news left them, and what is new in the open chat."""
        self.friends = social.friends()
        self.show_left()
        if self.tabs.get() == NOTES:
            self.show_notes()
        elif self.chosen and self.msgs is not None:
            cid, last = self.chosen["id"], max((m["id"] for m in self.msgs), default=0)
            self.run(lambda: social.messages_after(cid, last), lambda news: self._news(cid, news), lambda e: None)

    def _news(self, cid, news):
        if not self.chosen or self.chosen["id"] != cid or not news:
            return
        self.msgs += [m for m in news if all(x["id"] != m["id"] for x in self.msgs)]
        self.render()
        if any(m["sender"] != self.me_uid for m in news):
            self.run(lambda: social.read(cid), lambda _: self.app.social_changed(refresh_window=False), lambda e: None)

    def typing(self, conv, uid):
        """Someone is typing in a chat (told by the live connection)."""
        self.typing_at[conv] = (uid, time.time() + TYPING_SHOWN)
        if self.chosen and self.chosen["id"] == conv:
            self._sub()
            self.after(int(TYPING_SHOWN * 1000) + 200, self._sub)

    # ------------------------------------------------------------------ the requests
    def send_request(self):
        name = self.add_entry.get().strip()
        if not name:
            return
        self.add_status.configure(text="Bekle…", text_color=("gray20", "gray85"))

        def sent(_uid):
            self.add_entry.delete(0, "end")
            self.add_status.configure(text=f"✔ @{name.lstrip('@').lower()} kullanıcısına istek gönderildi",
                                      text_color=OK_COLOR)
            self.friends = social.friends()
            self.show_left()
        self.run(lambda: social.request(name), sent,
                 lambda e: self.add_status.configure(text=str(e), text_color=ERROR_COLOR))

    def answer(self, uid, yes):
        self.run(lambda: social.accept(uid) if yes else social.decline(uid),
                 lambda _: (self.refresh_now(), self.app.social_changed(refresh_window=False)))

    def take_back(self, uid):
        self.run(lambda: social.cancel(uid), lambda _: self.show_left())

    def destroy(self):
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
        super().destroy()
