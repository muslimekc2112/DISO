"""📱 The window with the QR code that lets the phone send links to DISO (see phone_link)."""
import tkinter as tk

import customtkinter as ctk

from . import phone_link
from .ui_common import fit_geometry, set_if_changed, set_window_icon

QR_PX = 260


class PhoneWindow(ctk.CTkToplevel):
    def __init__(self, app, link):
        super().__init__(app)
        set_window_icon(self)
        self.app, self.link = app, link
        self.title("DISO • Telefondan link gönder")
        fit_geometry(self, 440, 600)
        self.resizable(False, False)
        self.columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="📱 Telefondan link gönder", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, pady=(18, 4))
        ctk.CTkLabel(self, text="Telefonun kamerasıyla bu kodu okut. Açılan sayfaya linki yapıştır, bilgisayarda "
                                "DISO indirsin. Telefon ve bilgisayar aynı Wi-Fi'de olmalı.",
                     wraplength=380, justify="center", text_color="gray").grid(row=1, column=0, padx=24)
        self.qr_label = ctk.CTkLabel(self, text="", width=QR_PX, height=QR_PX)
        self.qr_label.grid(row=2, column=0, pady=14)
        self.url_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12), text_color="gray")
        self.url_label.grid(row=3, column=0)
        ctk.CTkLabel(self, text="Windows izin sorarsa “Özel ağlarda izin ver” de. Bağlantıyı kapatınca bu kod "
                                "bir daha çalışmaz.", wraplength=380, justify="center", font=ctk.CTkFont(size=11),
                     text_color="gray").grid(row=4, column=0, padx=24, pady=(10, 4))
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=5, column=0, pady=(10, 16))
        self.toggle_btn = ctk.CTkButton(foot, text="", width=150, command=self.toggle)
        self.toggle_btn.pack(side="left", padx=6)
        ctk.CTkButton(foot, text="Kapat", width=90, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray85"), command=self.destroy).pack(side="left", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        self._image = None
        self.show()

    def show(self):
        if self.link.running:
            url = self.link.url()
            self._image = ctk.CTkImage(phone_link.qr_image(url), size=(QR_PX, QR_PX))
            self.qr_label.configure(image=self._image, text="")
            set_if_changed(self.url_label, text=url)
            self.toggle_btn.configure(text="Bağlantıyı kapat")
        else:
            set_if_changed(self.url_label, text="Bağlantı kapalı")
            self.toggle_btn.configure(text="Bağlantıyı aç")
            if self._image is not None:                 # the old code must not be read any more
                self.qr_label.grid_remove()

    def toggle(self):
        if self.link.running:
            self.link.stop()
        else:
            try:
                self.link.start()
            except OSError as e:
                set_if_changed(self.url_label, text=f"Açamadım: {e}")
                return
            self.qr_label.grid()
        try:
            self.show()
        except tk.TclError:
            pass
