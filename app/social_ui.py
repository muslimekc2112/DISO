"""👥 The friends window: on the left the friends (online, what they listen to now), the requests that came and the
ones sent, a box to ask someone by user name; on the right the chat with the chosen friend, or the notifications
(songs recommended, liked, answered). See app/social.py."""
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import account, look, social
from .logs import log
from .ui_common import fit_geometry, set_window_icon

ERROR_COLOR = ("#c0392b", "#ff7b72")
OK_COLOR = ("#1e8449", "#7ee2a8")
ONLINE_COLOR = "#2F9E63"
CHATS, NOTES = "💬 Mesajlar", "🔔 Bildirimler"
REFRESH_EVERY = 60 * 1000      # ms: friends' online state / songs, while the window is open


def when(seconds) -> str:
    return time.strftime("%d.%m %H:%M", time.localtime(seconds))


class FriendsWindow(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.busy = 0
        self.title("DISO • Arkadaşlar")
        fit_geometry(self, 900, 600)
        self.minsize(760, 480)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.bind("<Escape>", lambda e: self.destroy())
        self.friends = social.friends()
        self.chosen = None                         # the friend whose chat is open
        self._build_left()
        self._build_right()
        self.show_left()
        self.show_notes() if not self.friends else self.choose(next(iter(self.friends)))
        self.refresh()

    # ------------------------------------------------------------------ the left side
    def _build_left(self):
        left = ctk.CTkFrame(self, width=300)
        left.grid(row=0, column=0, sticky="nsw", padx=(12, 6), pady=12)
        left.grid_propagate(False)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)
        me = social.me() if account.signed_in() else {"name": "", "username": ""}
        ctk.CTkLabel(left, text="👥 Arkadaşlar", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        ctk.CTkLabel(left, text=f"Sen: @{me['username']}" if me["username"] else "", text_color="gray",
                     anchor="w").grid(row=1, column=0, sticky="ew", padx=12)
        add = ctk.CTkFrame(left, fg_color="transparent")
        add.grid(row=2, column=0, sticky="ew", padx=8, pady=(8, 4))
        add.columnconfigure(0, weight=1)
        self.add_entry = ctk.CTkEntry(add, placeholder_text="Kullanıcı adı")
        self.add_entry.grid(row=0, column=0, sticky="ew")
        self.add_entry.bind("<Return>", lambda e: self.send_request())
        self.add_btn = ctk.CTkButton(add, text="➕ İstek", width=80, command=self.send_request)
        self.add_btn.grid(row=0, column=1, padx=(6, 0))
        self.add_status = ctk.CTkLabel(add, text="", font=ctk.CTkFont(size=11), wraplength=260, anchor="w",
                                       justify="left")
        self.add_status.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.left_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.left_list.grid(row=3, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.left_list.columnconfigure(0, weight=1)
        # 🔒 what friends may see of me
        cfg = self.app.cfg
        self.listening_var = ctk.BooleanVar(value=bool(cfg.get("share_listening")))
        ctk.CTkCheckBox(left, text="Dinlediğimi arkadaşlarım görsün", variable=self.listening_var,
                        font=ctk.CTkFont(size=12), command=self._set_listening).grid(
            row=4, column=0, sticky="w", padx=12, pady=(2, 2))
        self.likes_var = ctk.BooleanVar(value=bool(cfg.get("share_likes")))
        ctk.CTkCheckBox(left, text="Beğendiklerimi arkadaşlarıma bildir", variable=self.likes_var,
                        font=ctk.CTkFont(size=12),
                        command=lambda: cfg.set("share_likes", bool(self.likes_var.get()))).grid(
            row=5, column=0, sticky="w", padx=12, pady=(2, 10))

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
        heading(f"Arkadaşların ({len(self.friends)})")
        if not self.friends:
            ctk.CTkLabel(self.left_list, text="Henüz arkadaşın yok. Yukarıya bir kullanıcı adı yaz.",
                         text_color="gray", wraplength=250, justify="left").grid(row=row, column=0, sticky="w")
            row += 1
        for uid, f in sorted(self.friends.items(), key=lambda i: (not i[1].get("online"), i[1].get("name", ""))):
            self._friend_row(row, uid, f, data["unread"].get(uid, 0))
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

    def _set_listening(self):
        self.app.cfg.set("share_listening", bool(self.listening_var.get()))
        music = self.app.music
        playing = music.controller.current_track() if music is not None and music.controller.state != "stopped"             else None
        self.app._now_told = None
        self.app.music_now_playing(playing)                # shown / taken away at once

    def _friend_row(self, row, uid, f, unread):
        """One friend: a dot (online or not), the name, the unread count, the user name and the song or last seen."""
        chosen = uid == self.chosen
        card = ctk.CTkFrame(self.left_list, corner_radius=10,
                            fg_color=look.ACCENT_SOFT if chosen else "transparent", cursor="hand2")
        card.grid(row=row, column=0, sticky="ew", pady=1)
        card.columnconfigure(1, weight=1)
        dot = ctk.CTkLabel(card, text="●", width=16, text_color=ONLINE_COLOR if f.get("online") else "gray")
        dot.grid(row=0, column=0, padx=(8, 4), pady=(6, 0), sticky="n")
        name = ctk.CTkLabel(card, text=f.get("name") or f.get("username") or "?", anchor="w",
                            font=ctk.CTkFont(weight="bold"))
        name.grid(row=0, column=1, sticky="ew", pady=(6, 0))
        parts = [ctk.CTkLabel(card, text=f"@{f.get('username', '')}", anchor="w", text_color="gray",
                              font=ctk.CTkFont(size=11))]
        if f.get("now"):
            parts.append(ctk.CTkLabel(card, text=f"🎵 {f['now']}", anchor="w", font=ctk.CTkFont(size=11),
                                      text_color=look.ACCENT if look.is_new() else ("#1F6AA5", "#6CB6FF")))
        elif f.get("seen") and not f.get("online"):
            parts.append(ctk.CTkLabel(card, text=f"Son görülme: {when(f['seen'])}", anchor="w", text_color="gray",
                                      font=ctk.CTkFont(size=11)))
        for i, part in enumerate(parts):
            part.grid(row=i + 1, column=1, sticky="ew", pady=(0, 6 if i == len(parts) - 1 else 0))
        widgets = [card, dot, name, *parts]
        if unread:
            badge = ctk.CTkLabel(card, text=str(unread), width=22, height=22, corner_radius=11,
                                 fg_color=look.ACCENT if look.is_new() else "#1F6AA5", text_color="white",
                                 font=ctk.CTkFont(size=11, weight="bold"))
            badge.grid(row=0, column=2, padx=8, pady=(6, 0), sticky="n")
            widgets.append(badge)
        for w in widgets:
            w.bind("<Button-1>", lambda e, u=uid: self.choose(u))
            w.bind("<Button-3>", lambda e, u=uid: self._friend_menu(e, u))

    def _friend_menu(self, event, uid):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="💬 Mesaj yaz", command=lambda: self.choose(uid))
        menu.add_separator()
        menu.add_command(label="Arkadaşlıktan çıkar", command=lambda: self.remove(uid))
        menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------------ the right side
    def _build_right(self):
        right = ctk.CTkFrame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.tabs = ctk.CTkSegmentedButton(right, values=[CHATS, NOTES], command=self._tab)
        self.tabs.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))
        self.chat_box = ctk.CTkFrame(right, fg_color="transparent")
        self.chat_box.columnconfigure(0, weight=1)
        self.chat_box.rowconfigure(1, weight=1)
        self.chat_title = ctk.CTkLabel(self.chat_box, text="", anchor="w", font=ctk.CTkFont(size=16, weight="bold"))
        self.chat_title.grid(row=0, column=0, sticky="ew", padx=4)
        self.chat_text = ctk.CTkTextbox(self.chat_box, wrap="word", state="disabled")
        self.chat_text.grid(row=1, column=0, sticky="nsew", pady=6)
        send = ctk.CTkFrame(self.chat_box, fg_color="transparent")
        send.grid(row=2, column=0, sticky="ew")
        send.columnconfigure(0, weight=1)
        self.msg_entry = ctk.CTkEntry(send, placeholder_text="Mesaj yaz…")
        self.msg_entry.grid(row=0, column=0, sticky="ew")
        self.msg_entry.bind("<Return>", lambda e: self.send_message())
        self.send_btn = ctk.CTkButton(send, text="Gönder", width=90, command=self.send_message)
        self.send_btn.grid(row=0, column=1, padx=(6, 0))
        self.notes_box = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.notes_box.columnconfigure(0, weight=1)

    def _tab(self, which):
        if which == NOTES:
            self.show_notes()
        else:
            self.choose(self.chosen or next(iter(self.friends), None))

    def choose(self, uid):
        self.tabs.set(CHATS)
        self.notes_box.grid_remove()
        self.chat_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.chosen = uid if uid in self.friends else None
        f = self.friends.get(self.chosen) or {}
        self.chat_title.configure(text=(f"💬 {f.get('name') or f.get('username')}" if f
                                        else "Bir arkadaş seç (ya da önce birini ekle)"))
        self.show_chat()
        if self.chosen:
            social.mark_seen(self.chosen)
            self.app.social_changed(refresh_window=False)
            self.show_left()
            self.msg_entry.focus_set()

    def show_chat(self):
        chat = social.load()["chats"].get(self.chosen, []) if self.chosen else []
        name = (self.friends.get(self.chosen) or {}).get("name", "")
        self.chat_text.configure(state="normal")
        self.chat_text.delete("1.0", "end")
        for m in chat:
            who = "Sen" if m["me"] else (name or "O")
            self.chat_text.insert("end", f"{who}  ·  {when(m['at'])}\n{m['text']}\n\n")
        self.chat_text.configure(state="disabled")
        self.chat_text.see("end")
        state = "normal" if self.chosen else "disabled"
        self.msg_entry.configure(state=state)
        self.send_btn.configure(state=state)

    def show_notes(self):
        self.tabs.set(NOTES)
        self.chat_box.grid_remove()
        self.notes_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
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
                ctk.CTkButton(actions, text="⬇ İndir", width=70, command=lambda n=n: self.get_song(n)).pack(
                    side="left", padx=2)
                if n["kind"] == "recommend":
                    done = n.get("answered")
                    for v, t in ((1, "👍"), (-1, "👎")):
                        b = ctk.CTkButton(actions, text=t, width=36, command=lambda n=n, v=v: self.answer_song(n, v))
                        b.pack(side="left", padx=2)
                        if done:
                            b.configure(state="disabled")
        social.mark_seen()
        self.app.social_changed(refresh_window=False)

    # ------------------------------------------------------------------ doing
    def _run(self, work, then=None, failed=None):
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

    def refresh(self):
        """Friends' online state and songs (and the list itself) again; while the window is open."""
        def got(found):
            self.friends = found
            self.show_left()
            if self.chosen not in self.friends:
                self.chosen = None
        self._run(lambda: social.friends(refresh=True), got, lambda e: None)
        self._refresh_job = self.after(REFRESH_EVERY, self.refresh)

    def came_in(self):
        """Something came (see App._social_tick): the lists, the chat and the notes as they are now."""
        self._merge_friends()
        self.show_left()
        if self.tabs.get() == NOTES:
            self.show_notes()
        elif self.chosen:
            self.show_chat()
            social.mark_seen(self.chosen)

    def _merge_friends(self):
        """The friends as kept here now (one came, one went), with what is known of each (online, song)."""
        here = social.friends()
        self.friends = {uid: {**f, **{k: v for k, v in self.friends.get(uid, {}).items()
                                      if k in ("online", "now", "seen")}} for uid, f in here.items()}

    def send_request(self):
        name = self.add_entry.get().strip()
        if not name:
            return
        self.add_status.configure(text="Bekle…", text_color=("gray20", "gray85"))

        def sent(_uid):
            self.add_entry.delete(0, "end")
            self.add_status.configure(text=f"✔ @{name.lstrip('@').lower()} kullanıcısına istek gönderildi",
                                      text_color=OK_COLOR)
            self._merge_friends()
            self.show_left()
        self._run(lambda: social.request(name), sent,
                  lambda e: self.add_status.configure(text=str(e), text_color=ERROR_COLOR))

    def answer(self, uid, yes):
        def done(_):
            self.refresh_now()
            self.app.social_changed(refresh_window=False)
        self._run(lambda: social.accept(uid) if yes else social.decline(uid), done)

    def take_back(self, uid):
        self._run(lambda: social.cancel(uid), lambda _: self.show_left())

    def remove(self, uid):
        f = self.friends.get(uid) or {}
        if not messagebox.askyesno("DISO", f"{f.get('name') or f.get('username')} arkadaşlıktan çıkarılsın mı?",
                                   parent=self):
            return
        self._run(lambda: social.unfriend(uid), lambda _: self.refresh_now())

    def refresh_now(self):
        if getattr(self, "_refresh_job", None):
            self.after_cancel(self._refresh_job)
        self.refresh()

    def send_message(self):
        text = self.msg_entry.get().strip()
        if not text or not self.chosen:
            return
        self.msg_entry.delete(0, "end")
        uid = self.chosen
        self._run(lambda: social.message(uid, text), lambda _: self.show_chat(),
                  lambda e: (self.msg_entry.insert(0, text), self.app.notice(f"💬 Gönderilemedi: {e}", 8)))

    def get_song(self, n):
        song = n.get("song") or {}
        if song.get("url"):
            self.app.download_song({"url": song["url"], "title": social.song_name(song)})
            self.app.notice(f"⬇ İndiriliyor: {social.song_name(song)}", 6)

    def answer_song(self, n, value):
        self._run(lambda: social.feedback(n["id"], value), lambda _: self.show_notes())

    def destroy(self):
        job = getattr(self, "_refresh_job", None)
        if job:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        super().destroy()
