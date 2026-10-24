"""👤 The DISO account window: sign in, make an account, ask for a new password; signed in: which account,
when it last synced, "sync now" and "sign out" (see app/account.py)."""
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import account
from .logs import log
from .ui_common import fit_geometry, set_if_changed, set_window_icon

ERROR_COLOR = ("#c0392b", "#ff7b72")
OK_COLOR = ("#1e8449", "#7ee2a8")


def when(seconds) -> str:
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(seconds))


class AccountWindow(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.busy = False
        self.title("DISO • Hesap")
        fit_geometry(self, 430, 480)
        self.resizable(False, False)
        self.columnconfigure(0, weight=1)
        self.bind("<Escape>", lambda e: self.destroy())
        self.body = None
        self.buttons = []
        self.show()

    def show(self):
        if self.body is not None:
            self.body.destroy()
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=0, column=0, sticky="nsew", padx=26, pady=18)
        self.body.columnconfigure(0, weight=1)
        ctk.CTkLabel(self.body, text="👤 DISO hesabı", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, pady=(0, 6))
        (self._signed_in_view if account.signed_in() else self._sign_in_view)(self.body)

    def _hint(self, box, text, row):
        ctk.CTkLabel(box, text=text, wraplength=370, justify="center", text_color="gray").grid(
            row=row, column=0, pady=(0, 12))

    def _status(self, box, row):
        self.status = ctk.CTkLabel(box, text="", wraplength=370, justify="center", font=ctk.CTkFont(size=12))
        self.status.grid(row=row, column=0, pady=(10, 0))

    def _sign_in_view(self, box):
        self._hint(box, "Ayarların, çalma listelerin, takip ettiğin kanallar ve indirme geçmişin her bilgisayarında "
                        "aynı olsun. Şarkılar ve videolar taşınmaz, yalnız DISO'nun kendi küçük dosyaları.", 1)
        ctk.CTkLabel(box, text="E-posta", anchor="w").grid(row=2, column=0, sticky="ew")
        self.email_entry = ctk.CTkEntry(box)
        self.email_entry.grid(row=3, column=0, sticky="ew", pady=(2, 8))
        ctk.CTkLabel(box, text="Şifre", anchor="w").grid(row=4, column=0, sticky="ew")
        self.password_entry = ctk.CTkEntry(box, show="•")
        self.password_entry.grid(row=5, column=0, sticky="ew", pady=(2, 12))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.grid(row=6, column=0)
        self.sign_in_btn = ctk.CTkButton(row, text="Giriş yap", width=130, command=self.sign_in)
        self.sign_in_btn.pack(side="left", padx=6)
        self.sign_up_btn = ctk.CTkButton(row, text="Hesap aç", width=130, fg_color="transparent", border_width=1,
                                         text_color=("gray20", "gray85"), command=lambda: self.sign_in(new=True))
        self.sign_up_btn.pack(side="left", padx=6)
        self.reset_btn = ctk.CTkButton(box, text="Şifremi unuttum", width=130, fg_color="transparent",
                                       text_color=("gray30", "gray70"), hover=False, command=self.reset)
        self.reset_btn.grid(row=7, column=0, pady=(8, 0))
        self._status(box, 8)
        self.buttons = [self.sign_in_btn, self.sign_up_btn, self.reset_btn]
        self.password_entry.bind("<Return>", lambda e: self.sign_in())
        self.email_entry.bind("<Return>", lambda e: self.password_entry.focus_set())
        self.after(80, self._focus_email)

    def _focus_email(self):
        try:
            self.email_entry.focus_set()
        except tk.TclError:
            pass

    def _signed_in_view(self, box):
        ctk.CTkLabel(box, text=f"{account.email()} ile giriş yapıldı", font=ctk.CTkFont(weight="bold"),
                     wraplength=370).grid(row=1, column=0, pady=(0, 4))
        last = account.last_sync()
        self.last_label = ctk.CTkLabel(box, text=f"Son eşitleme: {when(last)}" if last else "Henüz eşitlenmedi",
                                       text_color="gray")
        self.last_label.grid(row=2, column=0, pady=(0, 10))
        self._hint(box, "DISO açılırken başka bilgisayarda değişenler gelir; kapanırken ve 10 dakikada bir "
                        "buradakiler hesaba gider. Bu bilgisayara özel ayarlar (klasörler, USB, bağlantı noktası, "
                        "Windows'la başlatma) taşınmaz.", 3)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.grid(row=4, column=0)
        self.sync_btn = ctk.CTkButton(row, text="🔄 Şimdi eşitle", width=140, command=self.sync_now)
        self.sync_btn.pack(side="left", padx=6)
        self.sign_out_btn = ctk.CTkButton(row, text="Çıkış yap", width=110, fg_color="transparent", border_width=1,
                                          text_color=("gray20", "gray85"), command=self.sign_out)
        self.sign_out_btn.pack(side="left", padx=6)
        self._status(box, 5)
        self.buttons = [self.sync_btn, self.sign_out_btn]

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
                b.configure(state="normal")
        except tk.TclError:
            return
        if error is not None:
            if not account.signed_in() and getattr(self, "sync_btn", None) in self.buttons:   # the session ended
                self.app.account_changed()
                self.show()
            self._say(str(error), ERROR_COLOR)
            return
        self._say("")
        then(result)

    # ------------------------------------------------------------------ the buttons
    def sign_in(self, new=False):
        address, password = self.email_entry.get().strip(), self.password_entry.get()

        def work():
            (account.sign_up if new else account.sign_in)(address, password)
            return account.peek()
        self._run(work, self._signed_in)

    def _signed_in(self, look):
        self.app.account_changed()
        self.show()
        prefer = None
        if look["differ"]:
            text = (f"Bu hesapta başka bir bilgisayardan ({look['device'] or '?'}, {when(look['updated'])}) gelen "
                    "veriler var ve buradakilerden farklı.\n\nHesaptakileri bu bilgisayara alayım mı?\n\n"
                    "Evet: hesaptaki ayarlar, listeler, kanallar ve geçmiş buraya gelir (buradakiler yedek olarak "
                    "saklanır, DISO yeniden açılır).\nHayır: bu bilgisayardakiler hesaba yüklenir.")
            prefer = "account" if messagebox.askyesno("DISO", text, parent=self) else "here"
        self.sync_now(prefer)

    def sync_now(self, prefer=None):
        self.app.save_for_account()
        self._run(lambda: account.sync("now", prefer=prefer), self._synced)

    def _synced(self, done):
        self.app.account_changed()
        self.show()
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

    def sign_out(self):
        if not messagebox.askyesno("DISO", "Hesaptan çıkılsın mı?\n\nBu bilgisayardaki ayarların ve listelerin "
                                           "olduğu gibi kalır, yalnız artık eşitlenmez.", parent=self):
            return
        account.sign_out()
        self.app.account_changed()
        self.show()

    def reset(self):
        address = self.email_entry.get().strip()
        if not address:
            self._say("Önce e-posta adresini yaz.", ERROR_COLOR)
            return
        self._run(lambda: account.reset_password(address),
                  lambda _: self._say(f"Şifre yenileme bağlantısı {address} adresine gönderildi. E-postanı kontrol "
                                      "et (gereksiz klasörüne de bak).", OK_COLOR))
