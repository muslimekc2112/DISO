"""🎉 "Yenilikler" (what came with this version, each with a "Dene" button) and 👋 the first-start tour (five
short steps; the part of the window a step talks about is outlined meanwhile)."""
import tkinter as tk

import customtkinter as ctk

from . import brand, look
from .ui_common import fit_geometry, set_if_changed, set_window_icon

# (icon, title, text, what "Dene" opens — see App.try_feature)
WHATS_NEW = [
    ("👥", "Arkadaşlar", "Kullanıcı adıyla arkadaş ekle; e-postan hiç görünmez. Kimin çevrimiçi olduğunu, şu an ne "
     "dinlediğini gör.", "friends"),
    ("💬", "Mesajlaşma", "Arkadaşlarınla DISO içinden yazış; yeni mesaj bildirim olarak gelir.", "friends"),
    ("🎵", "Arkadaşa şarkı öner", "Şarkıya sağ tık → “Arkadaşa öner”. Arkadaşın tek tıkla indirir, beğenip "
     "beğenmediğini sana söyler.", "share_song"),
    ("👍", "Beğen / beğenme", "Çalan şarkıyı beğen ya da beğenme; beğendiklerin “❤ Beğendiklerim” listesinde "
     "toplanır, arkadaşların da görür.", "like"),
    ("🗑", "Hesabı sil", "İstersen hesabını ve hesapta tutulan her şeyi kalıcı olarak silebilirsin.", "account"),
]

# (icon, title, text, the attribute of the widget to outline or None). The download window's tour comes at the
# first start; the music player's the first time the player is opened (never both at once).
DOWNLOAD_TOUR = [
    ("👋", f"{brand.NAME}'ya hoş geldin!", "Video, müzik, dosya, torrent… Hepsini buradan indirirsin; indirdiğin "
     "müzikleri de müzik çalarda dinlersin. Bu kısa tur indirme penceresini baştan sona gösterir. İstediğin an "
     "“Atla”ya basabilirsin; turu Ayarlar → Yedek ve yardım'dan yeniden açarsın.", None),
    ("🔗", "Linki buraya yapıştır", "YouTube, Instagram, TikTok, X ya da herhangi bir dosya linki. Birden fazla linki "
     "araya boşluk koyarak bir kerede yapıştırabilirsin. Enter'a basmak da indirmeyi başlatır.", "url_entry"),
    ("⬇", "İndir", "Linki yapıştırınca buna bas. DISO linkin ne olduğunu kendisi anlar: video mu, müzik mi, "
     "oynatma listesi mi, düz dosya mı.", "download_btn"),
    ("📋", "Hızlı düğmeler", "Soldan sağa: panodakini yapıştır, bir metin dosyasındaki bütün linkleri al, .torrent "
     "dosyası ekle, telefondan link gönder, bir linkin bilgilerine bak, indirme geçmişi, takip ettiğin kanallar. "
     "Bir düğmenin ne yaptığını unutursan üstünde bekle, söylerim.", "link_row"),
    ("🎚", "Ne indirilecek?", "“Otomatik” çoğu zaman doğru seçer. Yalnız ses istiyorsan MP3, görüntü istiyorsan "
     "MP4 seç. Yanlarında video kalitesi, MP3 kalitesi, bağlantı sayısı (hız), giriş çerezleri (giriş isteyen "
     "videolar için) ve altyazı var.", "options_frame"),
    ("📁", "Nereye insin?", "İndirilenler bu klasöre gider. “Klasör Seç” ile değiştir. “Türe göre klasör” açıksa "
     "videolar, müzikler, arşivler kendi klasörlerine ayrılır.", "folder_entry"),
    ("📊", "İndirmeler", "İnenler burada: ilerleme, hız ve kalan süre. Satıra sağ tıkla: duraklat, yeniden başlat, "
     "klasörde göster, sil, müzik listesine ekle… Çift tık dosyayı açar. Üstteki arama ve süzgeçle bulursun.",
     "list_frame"),
    ("▶", "Hepsini birden", "Hepsini başlat, hepsini duraklat, bitenleri temizle. Panoyu izle açıksa kopyaladığın "
     "her linki DISO kendisi yakalar.", "list_tools"),
    ("⚙", "Ayarlar", "Aynı anda kaç indirme, hız sınırı, zamanlayıcı (gece indir), bildirimler, Windows'la başlat, "
     "görünüm ve dil, yedek… Hepsi burada.", "settings_btn"),
    ("🧩", "Tarayıcıdan ve telefondan", "Tarayıcı eklentisini kurarsan sayfadaki videoya sağ tıklayıp “DISO ile "
     "indir” dersin; eklenti sayfadaki videoları kendisi de bulur. 📱 düğmesiyle telefondan link gönderirsin.",
     "phone_btn"),
    ("👤", "Hesabın", "Bir DISO hesabı açarsan ayarların, çalma listelerin, kanalların ve geçmişin her "
     "bilgisayarında aynı olur. Başka bir bilgisayarda listelerindeki şarkıları da tek tıkla indirirsin.",
     "account_btn"),
    ("🎵", "Müzik çalar", "En alttaki “Müzik çalar modu”na geç: şarkı ara, MP3 indir, listelerini çal, sözleriyle "
     "dinle. Orayı ilk açtığında ona da kısa bir tur var.", "mode_bar"),
    ("🚀", "Hazırsın!", "F1 bütün klavye kısayollarını gösterir. Bir sorun olursa Ayarlar → Sağlık kontrolü çoğunu "
     "tek tıkla düzeltir. İyi indirmeler!", None),
]
MUSIC_TOUR = [
    ("🎵", "Müzik çalara hoş geldin!", "İndirdiğin şarkıları burada dinlersin; internetten yenilerini bulup MP3 "
     "olarak indirirsin. Bu tur çaları baştan sona gösterir; “Atla” ile istediğin an çıkarsın.", None),
    ("📋", "Listelerim ve Şarkı bul", "“Listelerim” çalma listelerini gösterir. “Şarkı bul”a geçince YouTube "
     "Music'te ara: önizle, beğendiğini ⬇ ile MP3 indir. İnen şarkı hangi listeye gideceğini sorar.",
     "view_switch"),
    ("📂", "Çalma listesi", "Buradan liste seç; yanındaki ＋ yeni liste açar, ✎ adını değiştirir. Sağdaki menü "
     "sıralar: kendi sıran, A → Z, en çok dinlenen… Kendi sıran hep saklı kalır. ✨ akıllı listeler (en çok "
     "dinlenenler, son eklenenler) kendiliğinden dolar.", "list_bar"),
    ("🎶", "Şarkılar", "Çift tık çalar. Sürükleyerek sıra değiştir, sağ tıkla: başka listeye ekle, sözler, "
     "etiketleri düzenle, klasörde göster, sil. Alttaki düğmelerle dosya ya da bütün bir klasör eklersin.",
     "list_box"),
    ("▶", "Çalar", "⏮ önceki, ⏪5 / 5⏩ beş saniye sar, ▶ çal / duraklat, ⏭ sonraki, ⏹ durdur. Klavyede boşluk "
     "çalar / durdurur, ← → sarar, ↑ ↓ sesi açar ve kısar (basılı tutunca hızlanır).", "player_box"),
    ("〰", "Dalga çubuğu", "İlerleme çubuğu şarkının ses dalgasıdır: yüksek yerler uzun çubuk. İstediğin yere tıkla "
     "ya da sürükle, oraya atlar.", "seek"),
    ("⏩", "Hız, tekrar, uyku", "1x düğmesi çalma hızını 0.25x ile 4x arasında değiştirir (istersen perdeyle). "
     "Karışık, Tekrar (şarkı / liste) ve 😴 Uyku: seçtiğin sürede müzik yavaşça kısılıp durur.", "speed_btn"),
    ("🎛", "Ekolayzır", "Bas, orta, tiz; ya da “Gelişmiş” ile 8 bant. Ayar şarkı ortasında bile kesintisiz değişir.",
     "eq_btn"),
    ("🌌", "Görselleştirici", "Müziğe göre oynayan çubuklar, dalga ya da halka; ortada şarkının kapağı ritimle atar. "
     "🎤 ile sözler şarkıyla birlikte akar. Tam ekran yapabilirsin.", "vis_btn"),
    ("🗗", "Mini oynatıcı", "Küçük, hep üstte duran bir çalar: başka bir şeyle uğraşırken müziği yönet.", "mini_btn"),
    ("👤", "YouTube Music", "Google hesabınla bağlanırsan YouTube Music listelerini görür, istediklerini ya da "
     "hepsini indirirsin.", "google_btn"),
    ("⚙", "Daha fazlası", "⚙ menüsünde şarkılar arası geçiş, alarm, istatistikler, günlük karışık, kısayollar var. "
     "Turu Ayarlar → Yedek ve yardım'dan yeniden açarsın. Keyifli dinlemeler!", "menu_btn"),
]
TOUR = DOWNLOAD_TOUR


def _view_is_find(music, _start):
    from .music_ui import VIEW_FIND
    return music.view_switch.get() == VIEW_FIND


# 👉 the steps you try yourself (by the part they point at): what to do, and how the tour sees it was done. The
# tour then goes on by itself; "İleri" works all the same.
TRY = {
    "url_entry": ("Dene: yukarıdaki kutuya bir link yapıştır (Ctrl+V).", None,
                  lambda app, _start: bool(app.url_entry.get().strip())),
    "download_btn": ("Dene: ⬇ İndir'e bas.", lambda app: len(app.manager.items),
                     lambda app, start: len(app.manager.items) > start),
    "view_switch": ("Dene: “Şarkı bul”a tıkla.", None, _view_is_find),
}
TRY_EVERY = 250                # ms: how often the tour looks whether it was done
TRY_DONE_WAIT = 1100           # ms: "✔ Harika!" stays this long before the next step
GAP = 14                       # px between the tour window and the part it talks about
TOUR_WIDTH = 470


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
    """A tour: one step at a time, the part of `owner` (the download window or the music player) it talks about
    outlined, the tour window next to it. on_done(finished) when it closes: finished = it was walked to the end or
    skipped (not just closed by a mode switch)."""

    def __init__(self, owner, steps=DOWNLOAD_TOUR, title="Kısa tur", on_done=None):
        super().__init__(owner)
        set_window_icon(self)
        self.owner, self.steps, self.on_done = owner, steps, on_done
        self.title(f"{brand.NAME} • {title}")
        fit_geometry(self, TOUR_WIDTH, 360)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.columnconfigure(0, weight=1)
        self.step = 0
        self._outlined = None
        self.count = ctk.CTkLabel(self, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.count.grid(row=0, column=0, pady=(10, 0))
        self.icon = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=38))
        self.icon.grid(row=1, column=0, pady=(2, 0))
        self.head = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=19, weight="bold"))
        self.head.grid(row=2, column=0, padx=20, pady=(2, 2))
        self.text = ctk.CTkLabel(self, text="", wraplength=410, justify="center")
        self.text.grid(row=3, column=0, padx=24, pady=(2, 8))
        self.try_label = ctk.CTkLabel(self, text="", text_color=look.ACCENT if look.is_new() else ("#1F6AA5", "#6CB6FF"),
                                      font=ctk.CTkFont(weight="bold"), wraplength=410)
        self.dots = ctk.CTkLabel(self, text="", text_color="gray")
        self.dots.grid(row=4, column=0)
        self._try_job = None
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=6, column=0, pady=(10, 16))
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
        icon, head, text, target = self.steps[self.step]
        set_if_changed(self.count, text=f"{self.step + 1} / {len(self.steps)}")
        set_if_changed(self.icon, text=icon)
        set_if_changed(self.head, text=head)
        set_if_changed(self.text, text=text)
        set_if_changed(self.dots, text=" ".join("●" if i == self.step else "○" for i in range(len(self.steps))))
        self.back_btn.configure(state="normal" if self.step else "disabled")
        self.next_btn.configure(text="Başla 🚀" if self.step == len(self.steps) - 1 else "İleri ›")
        widget = getattr(self.owner, target, None) if target else None
        self._outline(widget)
        self._start_try(target if widget is not None else None)
        self._fit()
        self._place_near(widget)

    def _fit(self):
        """As tall as this step's text needs (no empty space under a short one)."""
        try:
            self.update_idletasks()
            scale = float(self._get_window_scaling())
            self.geometry(f"{TOUR_WIDTH}x{int(tk.Toplevel.winfo_reqheight(self) / scale) + 4}")
        except (tk.TclError, ValueError, AttributeError):
            pass

    def _start_try(self, target):
        """A step you try yourself: "👉 Dene: …", then "✔ Harika!" and on to the next one when it was done."""
        if self._try_job is not None:
            self.after_cancel(self._try_job)
            self._try_job = None
        what = TRY.get(target)
        if what is None:
            self.try_label.grid_remove()
            return
        text, start, _done = what
        self.try_label.configure(text="👉 " + text)
        self.try_label.grid(row=4, column=0, pady=(0, 6))
        self.dots.grid(row=5, column=0)
        try:
            self._try_start = start(self.owner) if start else None
        except Exception:  # noqa: BLE001 - then it is only told, not watched
            return
        step = self.step
        self._try_job = self.after(TRY_EVERY, lambda: self._watch_try(step, target))

    def _watch_try(self, step, target):
        self._try_job = None
        if self.step != step or not self.winfo_exists():
            return
        try:
            done = TRY[target][2](self.owner, self._try_start)
        except Exception:  # noqa: BLE001 - not watched any more
            return
        if not done:
            self._try_job = self.after(TRY_EVERY, lambda: self._watch_try(step, target))
            return
        self.try_label.configure(text="✔ Harika!")
        self._try_job = self.after(TRY_DONE_WAIT, lambda: self.step == step and self.go(+1))

    def go(self, step):
        if self.step + step >= len(self.steps):
            self.finish()
            return
        self.step = max(0, self.step + step)
        self.show()

    def _outline(self, widget):
        """The part of the window this step talks about gets a coloured frame (taken away at the next step)."""
        old, self._outlined = self._outlined, None
        if old is not None:
            try:
                old[0].configure(**{"border_width": old[1], old[3]: old[2]})
            except (tk.TclError, ValueError, AttributeError):
                pass
        if widget is None:
            return
        # most widgets have a border colour; a segmented button draws its border in its fg_color
        for option in ("border_color", "fg_color"):
            try:
                self._outlined = (widget, widget.cget("border_width"), widget.cget(option), option)
                widget.configure(**{"border_width": 3, option: look.ACCENT})
                return
            except (tk.TclError, ValueError, AttributeError):
                self._outlined = None

    def _place_near(self, widget):
        """Under the part it talks about (or above it, or beside), never off the screen; in the middle of the
        window when the step talks about the whole of it."""
        try:
            self.update_idletasks()
            w, h = self.winfo_width(), self.winfo_height()
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            if widget is not None and widget.winfo_viewable():
                x0, y0 = widget.winfo_rootx(), widget.winfo_rooty()
                ww, wh = widget.winfo_width(), widget.winfo_height()
                x = x0 + ww // 2 - w // 2
                if y0 + wh + GAP + h <= sh - 40:
                    y = y0 + wh + GAP
                elif y0 - GAP - h >= 0:
                    y = y0 - GAP - h
                else:
                    y = max(0, min(y0, sh - h - 40))
                    x = x0 + ww + GAP if x0 + ww + GAP + w <= sw else x0 - GAP - w
            else:
                o = self.owner
                x = o.winfo_rootx() + o.winfo_width() // 2 - w // 2
                y = o.winfo_rooty() + o.winfo_height() // 2 - h // 2
            x, y = max(0, min(x, sw - w)), max(0, min(y, sh - h - 40))
            tk.Toplevel.wm_geometry(self, f"+{int(x)}+{int(y)}")      # (a place on the screen: real pixels)
        except (tk.TclError, ValueError, AttributeError):
            pass

    def finish(self, finished=True):
        if self._try_job is not None:
            try:
                self.after_cancel(self._try_job)
            except tk.TclError:
                pass
            self._try_job = None
        self._outline(None)
        if self.on_done is not None:
            try:
                self.on_done(finished)
            except Exception:  # noqa: BLE001 - the tour closes anyway
                pass
        self.destroy()
