"""🎉 "Yenilikler" (what came with this version, each with a "Dene" button) and 👋 the first-start tour (five
short steps; the part of the window a step talks about is outlined meanwhile)."""
import tkinter as tk

import customtkinter as ctk

from . import brand, look
from .ui_common import fit_geometry, set_if_changed, set_window_icon

# (icon, title, text, what "Dene" opens — see App.try_feature)
WHATS_NEW = [
    ("👤", "YouTube Music listelerin", "Google hesabınla bağlan; listelerin ve beğendiğin şarkılar gelsin, istediğini MP3 indir.",
     "google"),
    ("🌈", "Görselleştirici + şarkıyla akan sözler", "Çalan şarkı çubuk, dalga ya da halka olarak dans eder; sözler "
     "üstünden akar. Tam ekran da olur.", "visualizer"),
    ("✨", "Günün karışığı ve radyo", "En çok dinlediklerine benzeyen yeni şarkılar her gün hazır; bir şarkıya sağ tıklayıp "
     "onun radyosunu da açabilirsin.", "mix"),
    ("⏰", "Müzikli alarm", "Seçtiğin saatte sevdiğin listeyle, sesi yavaşça açılarak uyan.", "alarm"),
    ("📊", "Dinleme istatistiklerin", "Bu ay, bu yıl en çok neleri, kimleri, hangi saatlerde dinledin.", "stats"),
    ("🎛", "Daha kolay ekolayzır", "Bas, Orta, Tiz; değiştirirken müzik artık takılmıyor. Uzmanlar için Gelişmiş.", "eq"),
    ("📱", "Telefondan link gönder", "QR kodu okut, telefondaki linki yapıştır, bilgisayarda insin.", "phone"),
    ("🧲", "Torrent", "Torrent dosyası düğmesi; .torrent dosyaları ve magnet linkleri doğrudan DISO'da açılır.", "torrent"),
    ("❓", "Neden inmedi?", "Hata olursa anlaşılır bir sebep ve tek tıkla çözüm: ▶'e basman yeter.", None),
    ("⌨", "Kendi kısayolların", "Müzik çaların tuşlarını sen belirle; DISO arkadayken çalışanlar dahil.", "keys"),
    ("🛡", "Ekstralar", "Klasör izleme, bitince USB'ye kopyalama, virüs taraması, internet hız testi.", "extras"),
]

# (icon, title, text, the App attribute of the widget to outline or None)
TOUR = [
    ("👋", f"{brand.NAME}'ya hoş geldin!", "Video, müzik, dosya… Linki yukarıdaki kutuya yapıştır, ⬇ İndir'e bas. "
     "Gerisini ben hallederim.", "url_entry"),
    ("🎚", "Ne indirileceğini seç", "“Ne indirilecek” menüsünden MP4 video ya da MP3 müzik seç; kaliteyi yanındaki "
     "menülerden ayarla.", "kind_menu"),
    ("🎵", "Müzik çalar", "En alttaki düğmeyle müzik çalara geç: şarkı ara, indir, listelerini çal, sözleriyle dinle.",
     "mode_bar"),
    ("🧩", "Tarayıcıdan ve telefondan", "Tarayıcı eklentisiyle sağ tık → “DISO ile indir”. 📱 düğmesiyle telefondan "
     "link gönder.", "phone_btn"),
    ("⚙", "Hepsi bu kadar", "Ayarlar'da daha fazlası var; F1 kısayolları gösterir. Bir düğmenin ne yaptığını merak "
     "edersen üstünde bekle, söylerim. İyi eğlenceler!", None),
]


class WhatsNewWindow(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.title(f"DISO • {brand.VERSION_LABEL} yenilikleri")
        fit_geometry(self, 620, 700)
        self.minsize(480, 420)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ctk.CTkLabel(self, text=f"🎉 {brand.NAME} {brand.VERSION_LABEL} ile neler geldi", anchor="w",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 2))
        ctk.CTkLabel(self, text="Merak ettiğin birine “Dene” de, hemen açayım.", text_color="gray", anchor="w").grid(
            row=1, column=0, sticky="ew", padx=20)
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=8)
        body.columnconfigure(0, weight=1)
        self.cards = []
        for i, (icon, title, text, action) in enumerate(WHATS_NEW):
            card = ctk.CTkFrame(body, corner_radius=12)
            card.grid(row=i, column=0, sticky="ew", pady=4)
            card.columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=26), width=48).grid(row=0, column=0, rowspan=2,
                                                                                  padx=(10, 4), pady=10)
            ctk.CTkLabel(card, text=title, anchor="w", font=ctk.CTkFont(size=15, weight="bold")).grid(
                row=0, column=1, sticky="ew", pady=(10, 0))
            ctk.CTkLabel(card, text=text, anchor="w", justify="left", wraplength=400, text_color="gray").grid(
                row=1, column=1, sticky="ew", pady=(0, 10))
            if action:
                ctk.CTkButton(card, text="Dene", width=70, command=lambda a=action: self.try_it(a)).grid(
                    row=0, column=2, rowspan=2, padx=12)
            self.cards.append((title, action))
        ctk.CTkButton(self, text="Harika, kapat", width=130, command=self.destroy).grid(row=3, column=0, pady=(4, 16))
        self.bind("<Escape>", lambda e: self.destroy())

    def try_it(self, action):
        self.app.try_feature(action)


class TourWindow(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        set_window_icon(self)
        self.app = app
        self.title(f"{brand.NAME} • Kısa tur")
        fit_geometry(self, 460, 330)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.columnconfigure(0, weight=1)
        self.step = 0
        self._outlined = None
        self.icon = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=40))
        self.icon.grid(row=0, column=0, pady=(18, 0))
        self.head = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=19, weight="bold"))
        self.head.grid(row=1, column=0, padx=20, pady=(4, 2))
        self.text = ctk.CTkLabel(self, text="", wraplength=400, justify="center")
        self.text.grid(row=2, column=0, padx=24, pady=(2, 8))
        self.dots = ctk.CTkLabel(self, text="", text_color="gray")
        self.dots.grid(row=3, column=0)
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=4, column=0, pady=(10, 16))
        self.skip_btn = ctk.CTkButton(foot, text="Atla", width=80, fg_color="transparent", border_width=1,
                                      text_color=("gray20", "gray85"), command=self.finish)
        self.skip_btn.pack(side="left", padx=6)
        self.back_btn = ctk.CTkButton(foot, text="‹ Geri", width=90, command=lambda: self.go(-1))
        self.back_btn.pack(side="left", padx=6)
        self.next_btn = ctk.CTkButton(foot, text="İleri ›", width=110, command=lambda: self.go(+1))
        self.next_btn.pack(side="left", padx=6)
        self.bind("<Escape>", lambda e: self.finish())
        self.bind("<Right>", lambda e: self.go(+1))
        self.bind("<Left>", lambda e: self.go(-1))
        self.protocol("WM_DELETE_WINDOW", self.finish)
        self.show()

    def show(self):
        icon, head, text, target = TOUR[self.step]
        set_if_changed(self.icon, text=icon)
        set_if_changed(self.head, text=head)
        set_if_changed(self.text, text=text)
        set_if_changed(self.dots, text="  ".join("●" if i == self.step else "○" for i in range(len(TOUR))))
        self.back_btn.configure(state="normal" if self.step else "disabled")
        self.next_btn.configure(text="Başla 🚀" if self.step == len(TOUR) - 1 else "İleri ›")
        self._outline(getattr(self.app, target, None) if target else None)

    def go(self, step):
        if self.step + step >= len(TOUR):
            self.finish()
            return
        self.step = max(0, self.step + step)
        self.show()

    def _outline(self, widget):
        """The part of the window this step talks about gets a coloured frame (taken away at the next step)."""
        old, self._outlined = self._outlined, None
        if old is not None:
            try:
                old[0].configure(border_width=old[1], border_color=old[2])
            except (tk.TclError, ValueError, AttributeError):
                pass
        if widget is None:
            return
        try:
            self._outlined = (widget, widget.cget("border_width"), widget.cget("border_color"))
            widget.configure(border_width=3, border_color=look.ACCENT)
        except (tk.TclError, ValueError, AttributeError):
            self._outlined = None

    def finish(self):
        self._outline(None)
        self.destroy()
