"""👤 The DISO account window. Its pages: "signin" (e-mail + password), "signup" (name, surname, user name, e-mail,
password twice), "verify" (the mail with the link was sent: "Doğruladım"), "first" (the first sign-in of this
computer: bring the account's data here or send this computer's up, and download the lists' songs) and "account"
(who is signed in, sync now, download the missing songs, a new password, sign out). See app/account.py.

Also: the button at the top right of the windows (AccountButton) and the question at start (AccountOffer)."""
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

from . import account, look, sharing
from .logs import log
from .ui_common import fit_geometry, set_if_changed, set_window_icon

ERROR_COLOR = ("#c0392b", "#ff7b72")
OK_COLOR = ("#1e8449", "#7ee2a8")
LINK_COLOR = ("#1f6aa5", "#6cb6ff")
GMAIL_URL = "https://mail.google.com/"
NAME_LIMIT = 22              # characters of the name on the button at the top right
WIDTH, MIN_HEIGHT, BODY_PAD = 450, 300, 18      # the account window (its height follows the page)
AVATAR = 72


def when(seconds) -> str:
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(seconds))


def button_text() -> str:
    if account.signed_in():
        name = account.display_name()
        return "👤 " + (name if len(name) <= NAME_LIMIT else name[:NAME_LIMIT - 1] + "…")
    return "👤 Doğrula" if account.waiting() else "👤 Giriş yap"


def initials(name) -> str:
    parts = [p for p in name.split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


class AccountButton(ctk.CTkButton):
    """The account at the top right: the name when signed in, "Giriş yap" when not. Opens the account window."""

    def __init__(self, parent, app, **kw):
        super().__init__(parent, text=button_text(), command=app.open_account, height=kw.pop("height", 32),
                         fg_color=look.ACCENT_SOFT if look.is_new() else ("gray78", "gray28"),
                         text_color=look.ACCENT if look.is_new() else ("gray15", "gray90"),
                         hover_color=("gray70", "gray35"), **kw)
        self.refresh()

    def refresh(self):
        set_if_changed(self, text=button_text())


class AccountOffer(ctk.CTkToplevel):
    """At start, while there is no account: make one (or sign in). Asked again every start until "Bir daha
    gösterme"."""

    def __init__(self, app, on_never):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.title("DISO • Hesap")
        self.geometry("420x240")                 # (small: fits every screen; fit_geometry keeps 360 at least)
        self.resizable(False, False)
        self.columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="👤 Bir DISO hesabı aç", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, pady=(20, 6))
        ctk.CTkLabel(self, text="Ayarların, çalma listelerin, kanalların ve indirme geçmişin her bilgisayarında "
                                "seninle gelsin. Başka bir bilgisayarda giriş yapınca listelerindeki şarkıları da "
                                "tek tıkla indirirsin.", wraplength=360, justify="center", text_color="gray").grid(
            row=1, column=0, padx=24)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=2, column=0, pady=(16, 6))
        self.sign_up_btn = ctk.CTkButton(row, text="Hesap aç", width=130, command=lambda: self._go("signup"))
        self.sign_up_btn.pack(side="left", padx=6)
        self.sign_in_btn = ctk.CTkButton(row, text="Giriş yap", width=130, fg_color="transparent", border_width=1,
                                         text_color=("gray20", "gray85"), command=lambda: self._go("signin"))
        self.sign_in_btn.pack(side="left", padx=6)
        low = ctk.CTkFrame(self, fg_color="transparent")
        low.grid(row=3, column=0, pady=(4, 16))
        self.later_btn = ctk.CTkButton(low, text="Şimdi değil", width=110, fg_color="transparent",
                                       text_color=("gray30", "gray70"), hover=False, command=self.destroy)
        self.later_btn.pack(side="left", padx=4)
        self.never_btn = ctk.CTkButton(low, text="Bir daha gösterme", width=130, fg_color="transparent",
                                       text_color=("gray30", "gray70"), hover=False,
                                       command=lambda: (on_never(), self.destroy()))
        self.never_btn.pack(side="left", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())

    def _go(self, page):
        self.destroy()
        self.app.open_account(page)


class AccountWindow(ctk.CTkToplevel):
    def __init__(self, app, page=None):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.busy = False
        self.title("DISO • Hesap")
        fit_geometry(self, WIDTH, 620)
        self.resizable(False, False)
        self.columnconfigure(0, weight=1)
        self.bind("<Escape>", lambda e: self.destroy())
        self.body = None
        self.buttons = []
        self.page = None
        self.look = None                 # what peek() told about the account (the "first" page)
        self.show(page)

    def default_page(self):
        if account.signed_in():
            return "account"
        return "verify" if account.waiting() else "signin"

    def show(self, page=None):
        """Show a page; one that does not fit the state (signed in / waiting / out) gives way to the right one."""
        page = page or self.default_page()
        if page in ("signin", "signup") and (account.signed_in() or account.waiting()):
            page = self.default_page()
        if page in ("account", "first", "devices") and not account.signed_in():
            page = self.default_page()
        if page == "verify" and not account.waiting():
            page = self.default_page()
        if self.body is not None:
            self.body.destroy()
        self.page = page
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=0, column=0, sticky="nsew", padx=28, pady=BODY_PAD)
        self.body.columnconfigure(0, weight=1)
        self.buttons = []
        getattr(self, "_page_" + page)(self.body)
        self._fit()

    def _fit(self):
        """As tall as the page: no empty space under a short one."""
        try:
            self.update_idletasks()
            scale = float(self._get_window_scaling())
            height = int(self.body.winfo_reqheight() / scale) + 2 * BODY_PAD + 20
            self.geometry(f"{WIDTH}x{max(MIN_HEIGHT, height)}")
        except (tk.TclError, ValueError, AttributeError):
            pass

    # ------------------------------------------------------------------ small pieces
    def _title(self, box, text, row=0):
        ctk.CTkLabel(box, text=text, font=ctk.CTkFont(size=20, weight="bold")).grid(row=row, column=0, pady=(0, 6))

    def _hint(self, box, text, row, pady=(0, 12)):
        ctk.CTkLabel(box, text=text, wraplength=380, justify="center", text_color="gray").grid(
            row=row, column=0, pady=pady)

    def _field(self, box, label, row, show=None):
        ctk.CTkLabel(box, text=label, anchor="w").grid(row=row, column=0, sticky="ew")
        entry = ctk.CTkEntry(box, show=show) if show else ctk.CTkEntry(box)
        entry.grid(row=row + 1, column=0, sticky="ew", pady=(2, 8))
        return entry

    def _status(self, box, row):
        self.status = ctk.CTkLabel(box, text="", wraplength=380, justify="center", font=ctk.CTkFont(size=12))
        self.status.grid(row=row, column=0, pady=(10, 0))

    def _link(self, box, text, page, row):
        b = ctk.CTkButton(box, text=text, fg_color="transparent", hover=False, text_color=LINK_COLOR,
                          command=lambda: self.show(page))
        b.grid(row=row, column=0, pady=(6, 0))
        return b

    def _primary(self, parent, text, command, width=150):
        b = ctk.CTkButton(parent, text=text, width=width, command=command)
        self.buttons.append(b)
        return b

    def _plain(self, parent, text, command, width=130):
        b = ctk.CTkButton(parent, text=text, width=width, fg_color="transparent", border_width=1,
                          text_color=("gray20", "gray85"), command=command)
        self.buttons.append(b)
        return b

    def _focus(self, entry):
        def go():
            try:
                entry.focus_set()
            except tk.TclError:
                pass
        self.after(80, go)

    # ------------------------------------------------------------------ the pages
    def _page_signin(self, box):
        self._title(box, "👤 Giriş yap")
        self._hint(box, "DISO hesabınla giriş yap: ayarların, listelerin, kanalların ve geçmişin gelsin.", 1)
        self.email_entry = self._field(box, "E-posta", 2)
        self.password_entry = self._field(box, "Şifre", 4, show="•")
        self.sign_in_btn = self._primary(box, "Giriş yap", self.sign_in, width=200)
        self.sign_in_btn.grid(row=6, column=0, pady=(8, 0))
        self.reset_btn = ctk.CTkButton(box, text="Şifremi unuttum", fg_color="transparent", hover=False,
                                       text_color=("gray30", "gray70"), command=self.reset)
        self.reset_btn.grid(row=7, column=0, pady=(6, 0))
        self.buttons.append(self.reset_btn)
        self._link(box, "Hesabın yok mu? Hesap aç", "signup", 8)
        self._status(box, 9)
        self.email_entry.bind("<Return>", lambda e: self.password_entry.focus_set())
        self.password_entry.bind("<Return>", lambda e: self.sign_in())
        self._focus(self.email_entry)

    def _page_signup(self, box):
        self._title(box, "👤 Hesap aç")
        self._hint(box, "Bilgilerini yaz. Gmail adresine bir doğrulama bağlantısı göndereceğiz; hesabın ona "
                        "tıklayınca açılır.", 1, pady=(0, 8))
        names = ctk.CTkFrame(box, fg_color="transparent")
        names.grid(row=2, column=0, sticky="ew")
        names.columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(names, text="Ad", anchor="w").grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(names, text="Soyad", anchor="w").grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.first_entry = ctk.CTkEntry(names)
        self.first_entry.grid(row=1, column=0, sticky="ew", pady=(2, 8))
        self.last_entry = ctk.CTkEntry(names)
        self.last_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(2, 8))
        self.username_entry = self._field(box, "Kullanıcı adı", 3)
        self.email_entry = self._field(box, "Gmail", 5)
        self.password_entry = self._field(box, "Şifre (en az 6 karakter)", 7, show="•")
        self.password2_entry = self._field(box, "Şifre (tekrar)", 9, show="•")
        self.sign_up_btn = self._primary(box, "Hesap aç", self.sign_up, width=200)
        self.sign_up_btn.grid(row=11, column=0, pady=(6, 0))
        self._link(box, "Zaten hesabın var mı? Giriş yap", "signin", 12)
        self._status(box, 13)
        order = [self.first_entry, self.last_entry, self.username_entry, self.email_entry, self.password_entry,
                 self.password2_entry]
        for a, b in zip(order, order[1:]):
            a.bind("<Return>", lambda e, b=b: b.focus_set())
        self.password2_entry.bind("<Return>", lambda e: self.sign_up())
        self._focus(self.first_entry)

    def _page_verify(self, box):
        self._title(box, "📧 E-postanı doğrula")
        ctk.CTkLabel(box, text=account.email(), font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, pady=(0, 6))
        self._hint(box, "Bu adrese bir doğrulama bağlantısı gönderdik. Gmail'ini aç, DISO'dan gelen e-postadaki "
                        "bağlantıya tıkla, sonra buraya dönüp “Doğruladım” de. Gelmediyse gereksiz (spam) "
                        "klasörüne de bak.", 2)
        self.verified_btn = self._primary(box, "✔ Doğruladım", self.verified, width=200)
        self.verified_btn.grid(row=3, column=0, pady=(4, 0))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.grid(row=4, column=0, pady=(10, 0))
        self._plain(row, "📬 Gmail'i aç", lambda: webbrowser.open(GMAIL_URL), width=120).pack(side="left", padx=4)
        self.resend_btn = self._plain(row, "Tekrar gönder", self.resend, width=120)
        self.resend_btn.pack(side="left", padx=4)
        self.cancel_btn = self._plain(row, "Vazgeç", self.cancel, width=90)
        self.cancel_btn.pack(side="left", padx=4)
        self._status(box, 5)

    def _page_first(self, box):
        """The first sign-in of this computer: what happens with the data and the songs."""
        look_ = self.look or {}
        self._title(box, "☁ Hesabındaki veriler")
        device = look_.get("device") or "?"
        made = when(look_["updated"]) if look_.get("updated") else "?"
        self._hint(box, f"Hesabında başka bir bilgisayardan ({device}, {made}) gelen ayarlar, listeler, kanallar "
                        "ve indirme geçmişi var.", 1)
        self.choice = tk.StringVar(value="account")
        ctk.CTkRadioButton(box, text="Verileri bu bilgisayara aktar", variable=self.choice, value="account").grid(
            row=2, column=0, sticky="w", pady=4)
        if look_.get("differ"):
            ctk.CTkRadioButton(box, text="Bu bilgisayardakileri hesaba yükle (hesaptakiler değişir)",
                               variable=self.choice, value="here").grid(row=3, column=0, sticky="w", pady=4)
        songs = look_.get("songs", 0)
        self.songs_var = tk.BooleanVar(value=songs > 0)
        self.songs_box = ctk.CTkCheckBox(box, text=f"Listelerdeki şarkıları da indir ({songs} şarkı)",
                                         variable=self.songs_var)
        if songs:
            self.songs_box.grid(row=4, column=0, sticky="w", pady=(10, 4))
        self._hint(box, "Aktarınca buradaki eski dosyalar yedek olarak saklanır ve DISO yeniden açılır. Şarkılar "
                        "açılıştan sonra MP3 olarak inmeye başlar; listede yerlerini alırlar.", 5, pady=(10, 8))
        self.go_btn = self._primary(box, "Devam", self.first_go, width=200)
        self.go_btn.grid(row=6, column=0)
        self._status(box, 7)

    def _page_account(self, box):
        name = account.display_name()
        p = account.profile()
        circle = ctk.CTkFrame(box, width=AVATAR, height=AVATAR, corner_radius=AVATAR // 2,
                              fg_color=look.ACCENT if look.is_new() else ("gray60", "gray40"))
        circle.grid(row=0, column=0, pady=(4, 8))
        circle.grid_propagate(False)
        ctk.CTkLabel(circle, text=initials(name), text_color="white", fg_color="transparent",
                     font=ctk.CTkFont(size=26, weight="bold")).place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(box, text=name, font=ctk.CTkFont(size=20, weight="bold")).grid(row=1, column=0)
        who = " · ".join(x for x in ("@" + p["username"] if p.get("username") else "", account.email()) if x)
        ctk.CTkLabel(box, text=who, text_color="gray").grid(row=2, column=0, pady=(0, 4))
        last = account.last_sync()
        self.last_label = ctk.CTkLabel(box, text=f"Son eşitleme: {when(last)}" if last else "Henüz eşitlenmedi",
                                       text_color="gray", font=ctk.CTkFont(size=12))
        self.last_label.grid(row=3, column=0, pady=(0, 10))
        self._hint(box, "DISO açılırken başka bilgisayarda değişenler gelir; kapanırken ve 10 dakikada bir "
                        "buradakiler hesaba gider. Bu bilgisayara özel ayarlar (klasörler, USB, bağlantı noktası, "
                        "Windows'la başlatma) taşınmaz.", 4)
        self.sync_btn = self._primary(box, "🔄 Şimdi eşitle", self.sync_now, width=260)
        self.sync_btn.grid(row=5, column=0, pady=3)
        away = len(self.app.away_songs())
        self.songs_btn = self._plain(box, f"⬇ Listelerdeki eksik şarkıları indir ({away})" if away
                                     else "⬇ Listelerdeki bütün şarkılar burada", self.download_songs, width=260)
        self.songs_btn.grid(row=6, column=0, pady=3)
        if not away:
            self.songs_btn.configure(state="disabled")
        self.devices_btn = self._plain(box, "💻 Bağlı bilgisayarlar", self.show_devices, width=260)
        self.devices_btn.grid(row=7, column=0, pady=3)
        self.password_btn = self._plain(box, "🔑 Şifreyi değiştir", self.change_password, width=260)
        self.password_btn.grid(row=8, column=0, pady=3)
        self.sign_out_btn = self._plain(box, "Çıkış yap", self.sign_out, width=260)
        self.sign_out_btn.grid(row=9, column=0, pady=3)
        self._status(box, 10)

    def _page_devices(self, box):
        """💻 The computers signed in to the account; any other one can be signed out from here."""
        self._title(box, "💻 Bağlı bilgisayarlar")
        self._hint(box, "Hesabına giriş yapmış bilgisayarlar. Birinden çıkış yaptırırsan, o bilgisayardaki DISO "
                        "hesabı bir sonraki açılışında (ya da birkaç dakika içinde) unutur.", 1)
        self.device_rows = ctk.CTkFrame(box, fg_color="transparent")
        self.device_rows.grid(row=2, column=0, sticky="ew")
        self.device_rows.columnconfigure(0, weight=1)
        ctk.CTkLabel(self.device_rows, text="Bekle…", text_color="gray").grid(row=0, column=0)
        self.back_btn = self._plain(box, "‹ Hesabım", lambda: self.show("account"), width=140)
        self.back_btn.grid(row=3, column=0, pady=(12, 0))
        self._status(box, 4)
        self.after(10, lambda: self._run(account.devices, self._show_devices))

    # ------------------------------------------------------------------ work off the window's thread
    def _say(self, text, color=None):
        try:
            set_if_changed(self.status, text=text, text_color=color or ("gray20", "gray85"))
        except tk.TclError:
            pass

    def _run(self, work, then):
        """work() on its own thread (the internet may be slow); then(result) back on the window's."""
        if self.busy:
            return
        self.busy = True
        self._say("Bekle…")
        for b in self.buttons:
            b.configure(state="disabled")

        def job():
            try:
                result, error = work(), None
            except account.AccountError as e:
                result, error = None, e
            except Exception:  # noqa: BLE001 - shown in the window, the details go to the log
                log.exception("account work failed")
                result, error = None, account.AccountError("Beklenmedik bir hata oldu. Ayrıntısı günlükte.")
            self.app._ui_calls.put(lambda: self._done(then, result, error))
        threading.Thread(target=job, daemon=True, name="account").start()

    def _done(self, then, result, error):
        self.busy = False
        try:
            if not self.winfo_exists():
                return
            for b in self.buttons:
                if b.winfo_exists():
                    b.configure(state="normal")
        except tk.TclError:
            return
        self.app.account_changed()
        if error is not None:
            if self.page != self.default_page() and self.page in ("account", "first", "verify"):
                self.show()                      # the session ended meanwhile
            self._say(str(error), ERROR_COLOR)
            return
        self._say("")
        then(result)

    # ------------------------------------------------------------------ signing in / up
    def sign_in(self):
        address, password = self.email_entry.get().strip(), self.password_entry.get()

        def work():
            session = account.sign_in(address, password)
            return account.peek() if session.get("verified") else None
        self._run(work, self._signed_in)

    def sign_up(self):
        values = [e.get() for e in (self.first_entry, self.last_entry, self.username_entry, self.email_entry)]
        password, again = self.password_entry.get(), self.password2_entry.get()
        if password != again:
            self._say("İki şifre aynı değil.", ERROR_COLOR)
            return
        self._run(lambda: account.sign_up(*values, password), lambda _: self.show("verify"))

    def verified(self):
        def work():
            return account.peek() if account.check_verified() else False
        self._run(work, lambda look_: self._signed_in(look_) if look_ is not False else self._say(
            account.MESSAGES["NOT_VERIFIED"], ERROR_COLOR))

    def resend(self):
        self._run(account.send_verification,
                  lambda _: self._say("Bağlantıyı yeniden gönderdik. Gmail'ine bak.", OK_COLOR))

    def cancel(self):
        account.sign_out()
        self.app.account_changed()
        self.show("signup")

    def _signed_in(self, look_):
        """Signed in. The first time on this computer with data in the account: ask what to do with it."""
        if look_ is None:                                 # the e-mail is not confirmed yet
            self.show("verify")
            self._say(account.MESSAGES["NOT_VERIFIED"], ERROR_COLOR)
            return
        self.app.account_changed()
        if look_["files"] and account.first_time():
            self.look = look_
            self.show("first")
            return
        self.show("account")
        self.sync_now()

    def first_go(self):
        prefer, songs = self.choice.get(), bool(self.songs_var.get())
        self.app.save_for_account()

        def work():
            done = account.sync("now", prefer=prefer)
            if songs and done["waiting"]:
                account.ask_redownload()                  # after the restart, when the lists are in place
            return done
        self._run(work, lambda done: self._synced(done, songs_now=songs and not done["waiting"]))

    # ------------------------------------------------------------------ signed in
    def sync_now(self, prefer=None):
        self.app.save_for_account()
        self._run(lambda: account.sync("now", prefer=prefer), self._synced)

    def _synced(self, done, songs_now=False):
        self.show("account")
        if songs_now:
            self.app.download_away_songs()
        if done["waiting"]:
            if messagebox.askyesno("DISO", "Hesaptaki veriler alındı. Uygulanmaları için DISO yeniden açılmalı."
                                           "\n\nŞimdi yeniden açılsın mı?", parent=self):
                self.app.restart_for_account()
            else:
                self._say("Tamam, hesaptaki veriler DISO'yu bir dahaki açışında gelecek", OK_COLOR)
        elif done["up"]:
            self._say(f"✔ Eşitlendi: {len(done['up'])} dosya hesaba gitti", OK_COLOR)
        else:
            self._say("✔ Eşitlendi: her şey zaten aynı", OK_COLOR)

    def show_devices(self):
        self.show("devices")

    def _show_devices(self, found):
        for w in self.device_rows.winfo_children():
            w.destroy()
        self.device_buttons = {}
        for i, d in enumerate(found):
            row = ctk.CTkFrame(self.device_rows)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.columnconfigure(0, weight=1)
            name = d["name"] + ("  (bu bilgisayar)" if d["this"] else "")
            ctk.CTkLabel(row, text="💻 " + name, anchor="w", font=ctk.CTkFont(weight="bold")).grid(
                row=0, column=0, sticky="ew", padx=10, pady=(6, 0))
            seen = f"Son görülme: {when(d['seen'])}" if d["seen"] else ""
            ctk.CTkLabel(row, text=" · ".join(x for x in (seen, "DISO " + d["version"] if d["version"] else "") if x),
                         anchor="w", text_color="gray", font=ctk.CTkFont(size=11)).grid(
                row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
            if not d["this"]:
                b = ctk.CTkButton(row, text="Çıkış yaptır", width=110, fg_color="transparent", border_width=1,
                                  text_color=("gray20", "gray85"), command=lambda d=d: self.sign_out_device(d))
                b.grid(row=0, column=1, rowspan=2, padx=10)
                self.device_buttons[d["id"]] = b
        if not found:
            ctk.CTkLabel(self.device_rows, text="Henüz bir bilgisayar yok.", text_color="gray").grid(row=0, column=0)
        self._fit()

    def sign_out_device(self, d):
        if not messagebox.askyesno("DISO", f"“{d['name']}” bilgisayarı hesabından çıkarılsın mı?\n\nOradaki "
                                           "ayarlar ve listeler olduğu gibi kalır, yalnız artık eşitlenmez.",
                                   parent=self):
            return
        self._run(lambda: (account.sign_out_device(d["id"]), account.devices())[1], lambda found: (
            self._show_devices(found), self._say(f"“{d['name']}” çıkarıldı.", OK_COLOR)))

    def download_songs(self):
        n = self.app.download_away_songs()
        if n:
            self._say(f"⬇ {n} şarkı aranıp indirilecek; indirmelerde görünürler", OK_COLOR)

    def change_password(self):
        address = account.email()
        self._run(lambda: account.reset_password(address),
                  lambda _: self._say(f"Yeni şifre bağlantısı {address} adresine gönderildi.", OK_COLOR))

    def sign_out(self):
        if not messagebox.askyesno("DISO", "Hesaptan çıkılsın mı?\n\nBu bilgisayardaki ayarların ve listelerin "
                                           "olduğu gibi kalır, yalnız artık eşitlenmez.", parent=self):
            return
        self._run(account.leave, lambda _: self.show("signin"))

    def reset(self):
        address = self.email_entry.get().strip()
        if not address:
            self._say("Önce e-posta adresini yaz.", ERROR_COLOR)
            return
        self._run(lambda: account.reset_password(address),
                  lambda _: self._say(f"Şifre yenileme bağlantısı {address} adresine gönderildi. E-postanı kontrol "
                                      "et (gereksiz klasörüne de bak).", OK_COLOR))


class _Small(ctk.CTkToplevel):
    """A small window that does its internet work on a worker thread (like AccountWindow)."""

    def __init__(self, app, title):
        super().__init__(app)
        set_window_icon(self)
        self.app, self.busy = app, False
        self.title(f"DISO • {title}")
        self.geometry("440x330")
        self.resizable(False, False)
        self.columnconfigure(0, weight=1)
        self.bind("<Escape>", lambda e: self.destroy())

    def run(self, work, then, failed=None):
        if self.busy:
            return
        self.busy = True

        def job():
            try:
                result, error = work(), None
            except account.AccountError as e:
                result, error = None, e
            except Exception:  # noqa: BLE001 - shown in the window, the details go to the log
                log.exception("sharing failed")
                result, error = None, account.AccountError("Beklenmedik bir hata oldu. Ayrıntısı günlükte.")
            self.app._ui_calls.put(lambda: self._finish(then, failed, result, error))
        threading.Thread(target=job, daemon=True, name="sharing").start()

    def _finish(self, then, failed, result, error):
        self.busy = False
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if error is not None:
            (failed or (lambda e: None))(error)
        else:
            then(result)


class ShareWindow(_Small):
    """🔗 Sending a playlist: its songs are looked up, kept in the account, and the code / link is shown to copy."""

    def __init__(self, app, name, tracks):
        super().__init__(app, "Listeyi gönder")
        self.name = name
        ctk.CTkLabel(self, text=f"🔗 “{name}”", font=ctk.CTkFont(size=20, weight="bold"), wraplength=400).grid(
            row=0, column=0, pady=(18, 4))
        self.status = ctk.CTkLabel(self, text=f"{len(tracks)} şarkının linkleri bulunuyor… (biraz sürebilir)",
                                   text_color="gray", wraplength=400)
        self.status.grid(row=1, column=0, padx=20)
        self.code_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=34, weight="bold"),
                                       text_color=look.ACCENT if look.is_new() else ("#1F6AA5", "#6CB6FF"))
        self.code_label.grid(row=2, column=0, pady=(14, 2))
        self.link_label = ctk.CTkLabel(self, text="", text_color="gray")
        self.link_label.grid(row=3, column=0)
        self.hint = ctk.CTkLabel(self, text="", wraplength=400, justify="center", font=ctk.CTkFont(size=12))
        self.hint.grid(row=4, column=0, padx=20, pady=(8, 4))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=5, column=0, pady=(8, 16))
        self.copy_code_btn = ctk.CTkButton(row, text="📋 Kodu kopyala", width=130, state="disabled",
                                           command=lambda: self.copy(sharing.pretty(self.code)))
        self.copy_code_btn.pack(side="left", padx=4)
        self.copy_link_btn = ctk.CTkButton(row, text="📋 Linki kopyala", width=130, state="disabled",
                                           command=lambda: self.copy(sharing.link(self.code)))
        self.copy_link_btn.pack(side="left", padx=4)
        ctk.CTkButton(row, text="Kapat", width=80, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.destroy).pack(side="left", padx=4)
        self.code = None
        self.run(lambda: sharing.share(name, app.song_links(tracks)), self.shared, self.failed)

    def shared(self, code):
        self.code = code
        self.status.configure(text="Hazır! Bu kodu ya da linki arkadaşına gönder:")
        self.code_label.configure(text=sharing.pretty(code))
        self.link_label.configure(text=sharing.link(code))
        self.hint.configure(text="Arkadaşın DISO'da müzik çaların ⚙ menüsünden “Paylaşılan listeyi aç”a kodu yazar "
                                 "ya da linke tıklar; liste onda da oluşur, şarkılar MP3 olarak iner.")
        self.copy_code_btn.configure(state="normal")
        self.copy_link_btn.configure(state="normal")

    def failed(self, error):
        self.status.configure(text=str(error), text_color=ERROR_COLOR)

    def copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.hint.configure(text=f"📋 Kopyalandı: {text}", text_color=OK_COLOR)


class OpenSharedWindow(_Small):
    """📥 A friend's playlist: the code typed (or come with a link), what it holds shown, then made here."""

    def __init__(self, app):
        super().__init__(app, "Paylaşılan liste")
        ctk.CTkLabel(self, text="📥 Paylaşılan liste", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, pady=(18, 4))
        ctk.CTkLabel(self, text="Arkadaşının gönderdiği kodu yaz (ör. K7P2-QM4X).", text_color="gray").grid(
            row=1, column=0)
        self.code_entry = ctk.CTkEntry(self, width=200, justify="center", font=ctk.CTkFont(size=18, weight="bold"))
        self.code_entry.grid(row=2, column=0, pady=(10, 4))
        self.code_entry.bind("<Return>", lambda e: self.look_up())
        self.info = ctk.CTkLabel(self, text="", wraplength=400, justify="center")
        self.info.grid(row=3, column=0, padx=20, pady=(6, 4))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=4, column=0, pady=(8, 16))
        self.look_btn = ctk.CTkButton(row, text="🔍 Listeyi bul", width=130, command=self.look_up)
        self.look_btn.pack(side="left", padx=4)
        self.take_btn = ctk.CTkButton(row, text="⬇ Ekle ve indir", width=140, state="disabled", command=self.take)
        self.take_btn.pack(side="left", padx=4)
        ctk.CTkButton(row, text="Kapat", width=80, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.destroy).pack(side="left", padx=4)
        self.shared = None
        self.after(80, lambda: self.code_entry.winfo_exists() and self.code_entry.focus_set())

    def open_code(self, code):
        self.code_entry.delete(0, "end")
        self.code_entry.insert(0, sharing.pretty(code))
        self.look_up()

    def look_up(self):
        code = sharing.clean_code(self.code_entry.get())
        if not code:
            self.info.configure(text="Bu bir liste koduna benzemiyor (8 harf ve rakam).", text_color=ERROR_COLOR)
            return
        self.info.configure(text="Bekle…", text_color=("gray20", "gray85"))
        self.take_btn.configure(state="disabled")
        self.run(lambda: sharing.fetch(code), self.found,
                 lambda e: self.info.configure(text=str(e), text_color=ERROR_COLOR))

    def found(self, shared):
        self.shared = shared
        n = len(shared["songs"])
        if shared["by"]:
            text = f"“{shared['name']}” · {shared['by']} paylaştı\n{n} şarkı. Listeyi ekleyip şarkıları MP3 olarak indireyim mi?"
        else:
            text = f"“{shared['name']}”\n{n} şarkı. Listeyi ekleyip şarkıları MP3 olarak indireyim mi?"
        self.info.configure(text=text, text_color=("gray20", "gray85"))
        self.take_btn.configure(state="normal" if shared["songs"] else "disabled")

    def take(self):
        if self.shared:
            self.app.take_shared(self.shared)
            self.destroy()

