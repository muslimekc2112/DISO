"""👤 The YouTube Music window of the music player: connect the Google account, see its lists (liked songs
and playlists), download the ticked ones or all of them as MP3 (each into a playlist of the same name)."""
import io
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import google_account, tooltip
from .ui_common import fit_geometry, set_if_changed, set_window_icon

POLL_MS = 200
PHOTO = 44


class GoogleWindow(ctk.CTkToplevel):
    def __init__(self, music, account=None):
        """`music` is the MusicWindow (its app downloads: app.download_playlist(results, title))."""
        super().__init__(music)
        set_window_icon(self)
        self.music = music
        self.account = account or google_account.Account()
        self.title("DISO • YouTube Music")
        fit_geometry(self, 560, 620)
        self.minsize(480, 460)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.lists, self.checks = [], {}
        self._photo = None

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        head.columnconfigure(1, weight=1)
        self.photo_label = ctk.CTkLabel(head, text="👤", width=PHOTO, height=PHOTO, font=ctk.CTkFont(size=26))
        self.photo_label.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        self.name_label = ctk.CTkLabel(head, text="YouTube Music", anchor="w", font=ctk.CTkFont(size=20, weight="bold"))
        self.name_label.grid(row=0, column=1, sticky="ew")
        self.sub_label = ctk.CTkLabel(head, text="", anchor="w", text_color="gray")
        self.sub_label.grid(row=1, column=1, sticky="ew")
        self.out_btn = ctk.CTkButton(head, text="Çıkış yap", width=90, fg_color="transparent", border_width=1,
                                     text_color=("gray20", "gray85"), command=self.sign_out)
        self.out_btn.grid(row=0, column=2, rowspan=2, sticky="e")

        self.info = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=500)
        self.info.grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 6))
        self.body = ctk.CTkScrollableFrame(self)
        self.body.grid(row=2, column=0, sticky="nsew", padx=16, pady=6)
        self.body.columnconfigure(0, weight=1)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=16, pady=(6, 14))
        foot.columnconfigure(1, weight=1)
        self.connect_btn = ctk.CTkButton(foot, text="🔑 Google ile bağlan", height=36, command=self.connect)
        from . import extension_setup
        self._browsers = {extension_setup.NAMES.get(bid, bid): bid for bid in google_account.usable_browsers()}
        self.browser_menu = ctk.CTkOptionMenu(foot, values=list(self._browsers) or ["—"], width=150,
                                              command=self._pick_browser)
        current = next((n for n, b in self._browsers.items() if b == self.account.browser_id), None)
        if current:
            self.browser_menu.set(current)
        self.cancel_btn = ctk.CTkButton(foot, text="Vazgeç", width=90, height=36, fg_color="transparent",
                                        border_width=1, text_color=("gray20", "gray85"), command=self.cancel)
        self.all_box = ctk.CTkCheckBox(foot, text="Hepsini seç", command=self._tick_all)
        self.refresh_btn = ctk.CTkButton(foot, text="⟳", width=36, height=36, command=self.refresh)
        tooltip.set(self.refresh_btn, "Listeleri yenile")
        self.picked_btn = ctk.CTkButton(foot, text="⬇ Seçilenleri indir", height=36, command=self.download_picked)
        self.every_btn = ctk.CTkButton(foot, text="⬇ Hepsini indir", height=36, command=self.download_all)
        self.foot = foot
        self.bind("<Escape>", lambda e: self.destroy())
        self._show_state()
        if self.account.connected:
            self.refresh()
        self.after(POLL_MS, self._poll)

    # ------------------------------------------------------------------ what is shown
    def _show_state(self, waiting=False):
        for w in self.foot.winfo_children():
            w.grid_forget()
        connected = self.account.connected
        if not connected:
            self.out_btn.grid_remove()
            set_if_changed(self.name_label, text="YouTube Music")
            set_if_changed(self.sub_label, text="Bağlı değil")
            for w in self.body.winfo_children():
                w.destroy()
            if waiting:
                text = ("Açılan pencerede Google hesabına giriş yap. YouTube Music açılınca o pencereyi kapat; "
                        "gerisini ben hallederim.")
                self.cancel_btn.grid(row=0, column=2, sticky="e")
            elif not self.account.browser:
                text = "Bu bilgisayarda Edge ya da Chrome bulamadım; Google'a bağlanmak için biri gerekli."
            else:
                text = ("Google hesabınla bağlan: YouTube Music'teki listelerin ve beğendiğin şarkılar burada "
                        "görünür, istediklerini MP3 olarak indirirsin.\n\nŞifreni DISO'ya yazmazsın: tarayıcında "
                        "Google'ın kendi sayfasında giriş yaparsın (DISO'ya ayrılmış ayrı bir pencerede, bir kez). "
                        "Oturum bu bilgisayarda şifreli saklanır, \"Çıkış yap\" ile silinir.")
                self.connect_btn.grid(row=0, column=0, columnspan=2, sticky="ew")
                if len(self._browsers) > 1:
                    self.browser_menu.grid(row=0, column=2, padx=(8, 0))
            set_if_changed(self.info, text=text)
            return
        self.out_btn.grid()
        data = self.account.data or {}
        set_if_changed(self.name_label, text=data.get("name") or "YouTube Music")
        set_if_changed(self.sub_label, text=data.get("handle") or "Bağlı")
        self.all_box.grid(row=0, column=0, sticky="w")
        self.refresh_btn.grid(row=0, column=1, sticky="e", padx=6)
        self.picked_btn.grid(row=0, column=2, padx=(0, 6))
        self.every_btn.grid(row=0, column=3)
        self._load_photo(data.get("photo"))

    def _fill(self, lists):
        self.lists = lists
        for w in self.body.winfo_children():
            w.destroy()
        self.checks = {}
        for i, p in enumerate(lists):
            var = tk.BooleanVar(value=False)
            count = "" if p.get("count") is None else f"{p['count']} şarkı"
            row = ctk.CTkFrame(self.body, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=2)
            row.columnconfigure(0, weight=1)
            ctk.CTkCheckBox(row, text=("❤ " if p["id"] == google_account.LIKED else "📋 ") + p["title"],
                            variable=var, command=self._update_buttons).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(row, text=count, text_color="gray").grid(row=0, column=1, padx=8)
            self.checks[p["id"]] = var
        set_if_changed(self.info, text=f"{len(lists)} liste. İşaretle ve indir: her liste aynı adlı bir çalma "
                                       "listesine, sırasıyla MP3 olarak iner." if lists else "Hiç listen yok.")
        self._update_buttons()

    def picked(self):
        return [p for p in self.lists if self.checks.get(p["id"]) is not None and self.checks[p["id"]].get()]

    def _update_buttons(self):
        n = len(self.picked())
        self.picked_btn.configure(state="normal" if n else "disabled",
                                  text=f"⬇ Seçilenleri indir ({n})" if n else "⬇ Seçilenleri indir")
        self.every_btn.configure(state="normal" if self.lists else "disabled")
        self.all_box.select() if self.lists and n == len(self.lists) else self.all_box.deselect()

    def _tick_all(self):
        on = bool(self.all_box.get())
        for var in self.checks.values():
            var.set(on)
        self._update_buttons()

    def _load_photo(self, url):
        if not url or self._photo is not None:
            return

        def work():
            try:
                import requests
                from PIL import Image, ImageDraw
                img = Image.open(io.BytesIO(requests.get(url, timeout=10).content)).convert("RGBA")
                img = img.resize((PHOTO * 2, PHOTO * 2))
                mask = Image.new("L", img.size, 0)
                ImageDraw.Draw(mask).ellipse((0, 0, img.size[0], img.size[1]), fill=255)
                img.putalpha(mask)
                self._photo_pil = img
            except Exception:  # noqa: BLE001 - the 👤 stays
                self._photo_pil = None
        threading.Thread(target=work, daemon=True, name="google-photo").start()

    # ------------------------------------------------------------------ actions
    def _pick_browser(self, name):
        bid = self._browsers.get(name)
        if bid:
            self.account.use_browser(bid)

    def connect(self):
        try:
            self.account.connect()
        except FileNotFoundError:
            set_if_changed(self.info, text="Bu bilgisayarda Edge ya da Chrome bulamadım.")
            return
        self._show_state(waiting=True)

    def cancel(self):
        self.account.cancel()

    def refresh(self):
        set_if_changed(self.info, text="Listelerin getiriliyor…")
        self.account.library()

    def sign_out(self):
        if not messagebox.askyesno("DISO", "Google hesabından çıkış yapılsın mı?\nİndirdiğin şarkılar yerinde kalır.",
                                   parent=self):
            return
        self.account.sign_out()
        self.lists = []
        self._show_state()

    def download_picked(self):
        self._download(self.picked())

    def download_all(self):
        self._download(list(self.lists))

    def _download(self, items):
        if not items or self.account.busy:
            return
        set_if_changed(self.info, text=f"{len(items)} listenin şarkıları getiriliyor…")
        self.account.songs(items)

    def _poll(self):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        pil = getattr(self, "_photo_pil", None)
        if pil is not None and self._photo is None:
            self._photo = ctk.CTkImage(pil, size=(PHOTO, PHOTO))
            self.photo_label.configure(image=self._photo, text="")
        for what, result, error in self.account.drain():
            self._answer(what, result, error)
        self.after(POLL_MS, self._poll)

    def _answer(self, what, result, error):
        if what == "connected":
            if error is None:
                self._show_state()
                self.refresh()
                note = getattr(self.music, "note", None)
                if note:
                    note(f"👤 Google hesabına bağlandın: {result.get('name') or 'YouTube Music'}", 8)
            else:
                self._show_state()
                set_if_changed(self.info, text="Bağlanmadan vazgeçildi." if isinstance(error, InterruptedError) else
                               "Giriş yapılmamış görünüyor. Tekrar dene: açılan pencerede Google'a giriş yap, "
                               "YouTube Music açılınca pencereyi kapat.")
        elif what == "library":
            if error is None:
                self._fill(result)
            elif isinstance(error, PermissionError):
                self.account.sign_out()
                self._show_state()
                set_if_changed(self.info, text="Google oturumun sona ermiş; tekrar bağlan.")
            else:
                set_if_changed(self.info, text="Listelerine ulaşamadım: bağlantını kontrol et ve ⟳ ile tekrar dene.")
        elif what == "songs":
            download = getattr(self.music.app, "download_playlist", None)
            if error is not None or not download:
                set_if_changed(self.info, text="Listelerin şarkılarını alamadım: bağlantını kontrol et.")
                return
            started = 0
            for title, songs in result or []:
                if songs:
                    added, _name = download(songs, title)
                    started += added
            set_if_changed(self.info, text=f"⬇ {started} şarkı iniyor; bittikçe sırasıyla aynı adlı listelere giriyor."
                           if started else "Bu listelerin şarkıları zaten listelerinde ya da iniyor.")
