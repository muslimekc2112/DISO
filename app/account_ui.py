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

from . import account, look
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
        if page in ("account", "first") and not account.signed_in():
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
        self.password_btn = self._plain(box, "🔑 Şifreyi değiştir", self.change_password, width=260)
        self.password_btn.grid(row=7, column=0, pady=3)
        self.sign_out_btn = self._plain(box, "Çıkış yap", self.sign_out, width=260)
        self.sign_out_btn.grid(row=8, column=0, pady=3)
        self._status(box, 9)

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
        account.sign_out()
        self.app.account_changed()
        self.show("signin")

    def reset(self):
        address = self.email_entry.get().strip()
        if not address:
            self._say("Önce e-posta adresini yaz.", ERROR_COLOR)
            return
        self._run(lambda: account.reset_password(address),
                  lambda _: self._say(f"Şifre yenileme bağlantısı {address} adresine gönderildi. E-postanı kontrol "
                                      "et (gereksiz klasörüne de bak).", OK_COLOR))
