"""👥 The small windows of the friends window: choosing songs to send (from a playlist, the last played, the last
downloaded), making a group, and a group's (or a friend's) info with what an admin can do. See app/social_ui.py."""
import tkinter as tk

import customtkinter as ctk

from . import look, social
from .logs import log
from .ui_common import fit_geometry, set_window_icon

ERROR_COLOR = ("#c0392b", "#ff7b72")
OK_COLOR = ("#1e8449", "#7ee2a8")


class _Dialog(ctk.CTkToplevel):
    def __init__(self, owner, title, width, height):
        super().__init__(owner)
        set_window_icon(self)
        self.owner, self.app = owner, owner.app
        self.title(f"DISO • {title}")
        fit_geometry(self, width, height)
        self.minsize(min(width, 380), min(height, 300))
        self.transient(owner)
        self.columnconfigure(0, weight=1)
        self.bind("<Escape>", lambda e: self.destroy())

    def status_line(self, row):
        self.status = ctk.CTkLabel(self, text="", wraplength=400, font=ctk.CTkFont(size=12))
        self.status.grid(row=row, column=0, padx=16, pady=(0, 4))

    def say(self, text, color=None):
        try:
            self.status.configure(text=text, text_color=color or ("gray20", "gray85"))
        except tk.TclError:
            pass


class SongPicker(_Dialog):
    """Songs to choose from; "Gönder" gives the chosen ones to on_pick(list of entries). An entry is
    (label, value); value is whatever the caller wants back (a track, a link)."""

    def __init__(self, owner, title, entries, on_pick, hint="", lists=None, on_list=None):
        super().__init__(owner, title, 520, 560)
        self.entries, self.on_pick, self.checks = entries, on_pick, []
        self.rowconfigure(2, weight=1)
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, pady=(14, 2))
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=14)
        top.columnconfigure(1, weight=1)
        if lists:                                                # a playlist to choose from
            self.list_menu = ctk.CTkOptionMenu(top, values=lists, width=170, command=lambda v: on_list(self, v))
            self.list_menu.grid(row=0, column=0, padx=(0, 8))
        self.filter = ctk.CTkEntry(top, placeholder_text="Ara…")
        self.filter.grid(row=0, column=1, sticky="ew")
        self.filter.bind("<KeyRelease>", lambda e: self._fill())
        self.box = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.box.grid(row=2, column=0, sticky="nsew", padx=10, pady=8)
        self.box.columnconfigure(0, weight=1)
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, pady=(0, 6))
        self.all_btn = ctk.CTkButton(foot, text="Hepsini seç", width=110, fg_color="transparent", border_width=1,
                                     text_color=("gray20", "gray85"), command=lambda: self._all(True))
        self.all_btn.pack(side="left", padx=4)
        self.none_btn = ctk.CTkButton(foot, text="Hiçbirini", width=90, fg_color="transparent", border_width=1,
                                      text_color=("gray20", "gray85"), command=lambda: self._all(False))
        self.none_btn.pack(side="left", padx=4)
        self.send_btn = ctk.CTkButton(foot, text="Gönder", width=120, command=self.send)
        self.send_btn.pack(side="left", padx=4)
        self.status_line(4)
        if hint:
            self.say(hint)
        self._fill()

    def set_entries(self, entries):
        self.entries = entries
        self._fill()

    def _fill(self):
        for w in self.box.winfo_children():
            w.destroy()
        self.checks = []
        words = self.filter.get().strip().lower()
        shown = [(l, v) for l, v in self.entries if not words or words in l.lower()][:300]
        if not shown:
            ctk.CTkLabel(self.box, text="Burada şarkı yok.", text_color="gray").grid(row=0, column=0, pady=20)
        for i, (label, value) in enumerate(shown):
            var = tk.BooleanVar(value=False)
            ctk.CTkCheckBox(self.box, text=label, variable=var).grid(row=i, column=0, sticky="w", padx=6, pady=2)
            self.checks.append((var, label, value))

    def _all(self, on):
        for var, _l, _v in self.checks:
            var.set(on)

    def send(self):
        chosen = [(label, value) for var, label, value in self.checks if var.get()]
        if not chosen:
            self.say("Önce göndermek istediklerini işaretle.", ERROR_COLOR)
            return
        self.on_pick(chosen)
        self.destroy()


class GroupDialog(_Dialog):
    """A new group: its name, what it is about, an emoji and the friends in it."""

    def __init__(self, owner, friends):
        super().__init__(owner, "Yeni grup", 460, 600)
        self.friends = friends
        self.rowconfigure(4, weight=1)
        ctk.CTkLabel(self, text="👥 Yeni grup", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, pady=(14, 6))
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=16)
        top.columnconfigure(1, weight=1)
        self.emoji = ctk.CTkEntry(top, width=48, justify="center", font=ctk.CTkFont(size=20))
        self.emoji.insert(0, "🎶")
        self.emoji.grid(row=0, column=0, padx=(0, 8))
        self.name = ctk.CTkEntry(top, placeholder_text="Grubun adı")
        self.name.grid(row=0, column=1, sticky="ew")
        self.about = ctk.CTkEntry(self, placeholder_text="Ne hakkında? (isteğe bağlı)")
        self.about.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        ctk.CTkLabel(self, text=f"Kimler olsun? (en fazla {social.MAX_GROUP - 1} arkadaş)", anchor="w",
                     text_color="gray").grid(row=3, column=0, sticky="w", padx=18)
        box = ctk.CTkScrollableFrame(self, fg_color="transparent")
        box.grid(row=4, column=0, sticky="nsew", padx=10, pady=4)
        self.vars = {}
        for uid, f in sorted(friends.items(), key=lambda i: i[1].get("name", "")):
            var = tk.BooleanVar(value=False)
            ctk.CTkCheckBox(box, text=f"{f.get('name') or f.get('username')}  (@{f.get('username', '')})",
                            variable=var).pack(anchor="w", padx=6, pady=2)
            self.vars[uid] = var
        if not friends:
            ctk.CTkLabel(box, text="Önce arkadaş eklemelisin; yine de yalnız başına grup kurabilirsin.",
                         text_color="gray", wraplength=360).pack(pady=20)
        self.make_btn = ctk.CTkButton(self, text="Grubu kur", width=160, command=self.make)
        self.make_btn.grid(row=5, column=0, pady=(6, 4))
        self.status_line(6)
        self.after(80, lambda: self.name.winfo_exists() and self.name.focus_set())

    def make(self):
        name = self.name.get().strip()
        if not name:
            self.say("Grubun bir adı olsun.", ERROR_COLOR)
            return
        people = [u for u, v in self.vars.items() if v.get()]
        about, emoji = self.about.get().strip(), self.emoji.get().strip() or "👥"    # (read here: not on the thread)
        self.make_btn.configure(state="disabled")
        self.owner.run(lambda: social.create_group(name, about, emoji, people), self.made, self.failed)

    def made(self, conv):
        self.owner.after_group(conv)
        self.destroy()

    def failed(self, error):
        self.make_btn.configure(state="normal")
        self.say(str(error), ERROR_COLOR)


class InfoDialog(_Dialog):
    """A group's info (members, what an admin may do) or a friend's (mute, block, unfriend)."""

    def __init__(self, owner, conv):
        super().__init__(owner, conv["name"], 480, 640)
        self.conv = conv
        self.rowconfigure(4, weight=1)
        group = conv["kind"] == "group"
        self.admin = group and conv["role"] == "admin"
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        head.columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text=conv.get("emoji") if group else "👤", font=ctk.CTkFont(size=34), width=56).grid(
            row=0, column=0, rowspan=2)
        ctk.CTkLabel(head, text=conv["name"], anchor="w", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=1, sticky="ew")
        ctk.CTkLabel(head, text=conv.get("about") or ("Grup" if group else "Arkadaşın"), anchor="w",
                     text_color="gray", wraplength=330, justify="left").grid(row=1, column=1, sticky="ew")
        if self.admin:
            self.name = ctk.CTkEntry(self, placeholder_text="Grubun adı")
            self.name.insert(0, conv["name"])
            self.name.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 2))
            self.about = ctk.CTkEntry(self, placeholder_text="Ne hakkında?")
            self.about.insert(0, conv.get("about", ""))
            self.about.grid(row=2, column=0, sticky="ew", padx=16, pady=2)
            self.admins_only = tk.BooleanVar(value=bool(conv.get("only_admins")))
            ctk.CTkCheckBox(self, text="📢 Yalnız yöneticiler yazabilsin", variable=self.admins_only,
                            command=self._save_info).grid(row=3, column=0, sticky="w", padx=18, pady=2)
            self.name.bind("<Return>", lambda e: self._save_info())
            self.about.bind("<Return>", lambda e: self._save_info())
        self.muted = tk.BooleanVar(value=bool(conv.get("muted")))
        self.box = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.box.grid(row=4, column=0, sticky="nsew", padx=10, pady=6)
        self.box.columnconfigure(0, weight=1)
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=5, column=0, pady=(0, 6))
        ctk.CTkCheckBox(foot, text="🔕 Sessize al", variable=self.muted, command=self._mute).pack(side="left", padx=8)
        if group:
            if self.admin:
                ctk.CTkButton(foot, text="➕ Üye ekle", width=100, command=self.add_member).pack(side="left", padx=4)
            ctk.CTkButton(foot, text="Gruptan çık", width=100, fg_color="transparent", border_width=1,
                          text_color=ERROR_COLOR, command=self.leave).pack(side="left", padx=4)
            if self.admin:
                ctk.CTkButton(foot, text="🗑 Grubu sil", width=100, fg_color="transparent", border_width=1,
                              text_color=ERROR_COLOR, command=self.delete).pack(side="left", padx=4)
        else:
            ctk.CTkButton(foot, text="Arkadaşlıktan çıkar", width=140, fg_color="transparent", border_width=1,
                          text_color=ERROR_COLOR, command=self.unfriend).pack(side="left", padx=4)
            ctk.CTkButton(foot, text="⛔ Engelle", width=90, fg_color="transparent", border_width=1,
                          text_color=ERROR_COLOR, command=self.block).pack(side="left", padx=4)
        self.status_line(6)
        if group:
            self.load_members()

    # ------------------------------------------------------------------ members
    def load_members(self):
        self.owner.run(lambda: social.group_members(self.conv["id"]), self.show_members, lambda e: self.say(str(e), ERROR_COLOR))

    def show_members(self, members):
        for w in self.box.winfo_children():
            w.destroy()
        self.members = members
        mine = self.owner.me_uid
        for i, m in enumerate(members):
            row = ctk.CTkFrame(self.box)
            row.grid(row=i, column=0, sticky="ew", pady=2)
            row.columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=f"{m['name']}  (@{m['username']})" + ("  · sen" if m["uid"] == mine else ""),
                         anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=6)
            if m["role"] == "admin":
                ctk.CTkLabel(row, text="Yönetici", text_color=look.ACCENT, font=ctk.CTkFont(size=11, weight="bold")).grid(
                    row=0, column=1, padx=6)
            if self.admin and m["uid"] != mine:
                ctk.CTkButton(row, text="Yöneticilikten al" if m["role"] == "admin" else "Yönetici yap", width=110,
                              height=26, fg_color="transparent", border_width=1, text_color=("gray20", "gray85"),
                              command=lambda m=m: self._role(m)).grid(row=0, column=2, padx=2)
                ctk.CTkButton(row, text="✖", width=30, height=26, fg_color="transparent", border_width=1,
                              text_color=ERROR_COLOR, command=lambda m=m: self._remove(m)).grid(row=0, column=3, padx=(2, 8))

    def _role(self, m):
        self.owner.run(lambda: social.group_role(self.conv["id"], m["uid"], m["role"] != "admin"),
                       lambda _: self.load_members(), lambda e: self.say(str(e), ERROR_COLOR))

    def _remove(self, m):
        self.owner.run(lambda: social.group_remove(self.conv["id"], m["uid"]), lambda _: self.load_members(),
                       lambda e: self.say(str(e), ERROR_COLOR))

    def add_member(self):
        here = {m["uid"] for m in getattr(self, "members", [])}
        candidates = {u: f for u, f in self.owner.friends.items() if u not in here}
        if not candidates:
            self.say("Eklenecek arkadaşın kalmadı.", ERROR_COLOR)
            return
        menu = tk.Menu(self, tearoff=0)
        for u, f in sorted(candidates.items(), key=lambda i: i[1].get("name", "")):
            menu.add_command(label=f.get("name") or f.get("username"), command=lambda u=u: self.owner.run(
                lambda: social.group_add(self.conv["id"], u), lambda _: self.load_members(),
                lambda e: self.say(str(e), ERROR_COLOR)))
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    # ------------------------------------------------------------------ the rest
    def _save_info(self):
        fields = {"name": self.name.get().strip() or self.conv["name"], "about": self.about.get().strip(),
                  "only_admins": bool(self.admins_only.get())}
        self.owner.run(lambda: social.group_update(self.conv["id"], **fields),
                       lambda _: (self.say("✔ Kaydedildi", OK_COLOR), self.owner.refresh_now()),
                       lambda e: self.say(str(e), ERROR_COLOR))

    def _mute(self):
        on = bool(self.muted.get())
        self.owner.run(lambda: social.mute(self.conv["id"], on), lambda _: self.owner.refresh_now())

    def leave(self):
        self.owner.run(lambda: social.group_leave(self.conv["id"]), lambda _: self._gone(), lambda e: self.say(str(e), ERROR_COLOR))

    def delete(self):
        from tkinter import messagebox
        if messagebox.askyesno("DISO", f"“{self.conv['name']}” grubu herkes için silinsin mi? Bu geri alınamaz.",
                               parent=self):
            self.owner.run(lambda: social.group_delete(self.conv["id"]), lambda _: self._gone(),
                           lambda e: self.say(str(e), ERROR_COLOR))

    def unfriend(self):
        self.owner.run(lambda: social.unfriend(self.conv["peer"]), lambda _: self._gone(), lambda e: self.say(str(e), ERROR_COLOR))

    def block(self):
        from tkinter import messagebox
        if messagebox.askyesno("DISO", f"{self.conv['name']} engellensin mi? Arkadaşlığınız biter, birbirinize "
                                       "yazamazsınız.", parent=self):
            self.owner.run(lambda: social.block(self.conv["peer"]), lambda _: self._gone(),
                           lambda e: self.say(str(e), ERROR_COLOR))

    def _gone(self):
        self.owner.after_leave(self.conv["id"])
        self.destroy()
