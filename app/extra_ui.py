"""Two small windows of the download side: the download history with its numbers (📊), and the list of
keyboard shortcuts (F1)."""
import datetime
import os
from tkinter import ttk

import customtkinter as ctk

from .i18n import tr
from .music_ui import style_table
from .ui_common import fit_geometry, set_window_icon
from .utils import human_size, open_in_file_manager

SHORTCUTS = [
    ("İndirme penceresi", [
        ("Ctrl + V", "Panodaki linkleri listeye ekle"),
        ("Enter", "Link kutusundaki linki indir"),
        ("Ctrl + F", "Listede ara"),
        ("Ctrl + A", "Hepsini seç"),
        ("Delete", "Seçilenleri listeden kaldır"),
        ("Çift tık", "Bitmiş dosyayı aç"),
        ("Ctrl + N", "Yeni indirme penceresi (Nostalji görünümü)"),
        ("F1", "Bu pencere"),
    ]),
    ("Müzik çalar", [
        ("Boşluk", "Çal / duraklat"),
        ("Enter / çift tık", "Seçili şarkıyı çal"),
        ("Ctrl + ↑ / ↓", "Seçili şarkıları yukarı / aşağı taşı"),
        ("Delete", "Seçili şarkıları listeden çıkar (dosyalar silinmez)"),
        ("Ctrl + A", "Listedeki her şeyi seç"),
        ("Ctrl + F", "Listede ara (Şarkı bul'dayken: arama kutusu)"),
        ("Ctrl + Z", "Karıştırmayı geri al"),
        ("↑ / ↓ + Enter", "Arama önerilerinden birini seç"),
        ("Sağ tık", "Sıradaki olarak çal, sıraya ekle, sözler, başka listeye ekle…"),
    ]),
    ("Her yerde", [
        ("⏯ ⏭ ⏮ (klavye)", "Müzik çalarken klavyenin medya tuşları DISO'yu yönetir"),
        ("Ses tuşları", "Windows'un ses panelinde çalan şarkı ve düğmeleri görünür"),
        ("Görev çubuğu", "Müzik penceresinin küçük önizlemesinde ⏮ ⏯ ⏭"),
        ("Esc", "Sözler penceresini ve küçük pencereleri kapat"),
    ]),
]


class ShortcutsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        set_window_icon(self)
        self.title("DISO • Klavye kısayolları")
        fit_geometry(self, 600, 640)
        self.minsize(460, 400)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text="⌨ Klavye kısayolları", font=ctk.CTkFont(size=22, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=12)
        body.columnconfigure(1, weight=1)
        row = 0
        self.rows = []
        for section, items in SHORTCUTS:
            ctk.CTkLabel(body, text=section, text_color="gray", font=ctk.CTkFont(size=13, weight="bold"),
                         anchor="w").grid(row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=(12, 4))
            row += 1
            for keys, what in items:
                ctk.CTkLabel(body, text=keys, corner_radius=8, fg_color=("gray85", "gray25"), height=26,
                             font=ctk.CTkFont(size=12, weight="bold")).grid(row=row, column=0, sticky="w",
                                                                            padx=(8, 12), pady=3, ipadx=8)
                ctk.CTkLabel(body, text=what, anchor="w", justify="left", wraplength=360).grid(
                    row=row, column=1, sticky="ew", pady=3)
                self.rows.append((keys, what))
                row += 1
        ctk.CTkButton(self, text="Kapat", width=100, command=self.destroy).grid(row=2, column=0, sticky="e",
                                                                                padx=20, pady=12)
        self.bind("<Escape>", lambda e: self.destroy())


def _when(ts) -> str:
    d = datetime.datetime.fromtimestamp(ts)
    today = datetime.date.today()
    if d.date() == today:
        return "Bugün " + d.strftime("%H:%M")
    if d.date() == today - datetime.timedelta(days=1):
        return "Dün " + d.strftime("%H:%M")
    return d.strftime("%d.%m.%Y %H:%M")


def speed_text(bytes_per_second) -> str:
    return f"{human_size(bytes_per_second)}/s" if bytes_per_second else "—"


class HistoryWindow(ctk.CTkToplevel):
    """📊 Everything downloaded (also what was cleared from the list since), and its numbers."""

    def __init__(self, parent, history):
        super().__init__(parent)
        set_window_icon(self)
        self.history = history
        self.title("DISO • İndirme geçmişi")
        fit_geometry(self, 900, 680)
        self.minsize(660, 480)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ctk.CTkLabel(self, text="📊 İndirme geçmişi", font=ctk.CTkFont(size=22, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(16, 6))

        self.cards = ctk.CTkFrame(self, fg_color="transparent")
        self.cards.grid(row=1, column=0, sticky="ew", padx=16)
        self.card_labels = {}
        for i, key in enumerate(("total", "week", "speed", "fastest")):
            self.cards.columnconfigure(i, weight=1)
            box = ctk.CTkFrame(self.cards, corner_radius=12)
            box.grid(row=0, column=i, sticky="nsew", padx=4, pady=4)
            big = ctk.CTkLabel(box, text="", font=ctk.CTkFont(size=20, weight="bold"), anchor="w")
            big.pack(fill="x", padx=12, pady=(10, 0))
            small = ctk.CTkLabel(box, text="", text_color="gray", anchor="w", justify="left", wraplength=190)
            small.pack(fill="x", padx=12, pady=(0, 10))
            self.card_labels[key] = (big, small)
        self.more_label = ctk.CTkLabel(self.cards, text="", text_color="gray", anchor="w", justify="left")
        self.more_label.grid(row=1, column=0, columnspan=4, sticky="ew", padx=8, pady=(2, 6))

        box = ctk.CTkFrame(self)
        box.grid(row=2, column=0, sticky="nsew", padx=16, pady=(4, 4))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        self.search = ctk.CTkEntry(box, placeholder_text="🔎 Geçmişte ara (ad, site…)")
        self.search.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 0))
        self.search.bind("<KeyRelease>", lambda e: self.refresh())
        style_table(self)
        self.tree = ttk.Treeview(box, columns=("when", "title", "kind", "size", "speed"), show="headings",
                                 selectmode="browse", style="Music.Treeview")
        for name, text, width, anchor, stretch in (("when", "Ne zaman", 130, "w", False),
                                                   ("title", "Ne indi", 360, "w", True),
                                                   ("kind", "Tür", 70, "center", False),
                                                   ("size", "Boyut", 90, "e", False),
                                                   ("speed", "Hız", 100, "e", False)):
            self.tree.heading(name, text=text, anchor=anchor)
            self.tree.column(name, width=width, minwidth=50, anchor=anchor, stretch=stretch)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=8)
        bar = ctk.CTkScrollbar(box, command=self.tree.yview)
        bar.grid(row=1, column=1, sticky="ns", pady=8, padx=(0, 4))
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.bind("<Double-Button-1>", lambda e: self.reveal())
        self.empty = ctk.CTkLabel(box, text="Henüz bir şey indirmedin. İlk indirmen bittiğinde burada görünür.",
                                  text_color="gray")

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 14))
        foot.columnconfigure(1, weight=1)
        ctk.CTkButton(foot, text="📂 Klasörde göster", width=150, command=self.reveal).grid(row=0, column=0)
        self.clear_btn = ctk.CTkButton(foot, text="Geçmişi temizle", width=130, fg_color="transparent",
                                       border_width=1, text_color=("gray20", "gray85"), command=self.clear)
        self.clear_btn.grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(foot, text="Kapat", width=100, command=self.destroy).grid(row=0, column=3)
        self.bind("<Escape>", lambda e: self.destroy())
        self.shown = []
        self.refresh()

    def refresh(self):
        s = self.history.stats()
        self._card("total", f"{s['count']} indirme", f"toplam {human_size(s['size'])}")
        self._card("week", f"{s['week_count']} bu hafta", human_size(s["week_size"]) if s["week_size"] else "son 7 günde")
        self._card("speed", speed_text(s["average_speed"]), "ortalama hız")
        fastest = s["fastest"]
        self._card("fastest", speed_text(s["fastest_speed"]),
                   f"en hızlısı: {fastest['title'][:40]}" if fastest else "en hızlı indirme")
        parts = []
        if s["kinds"]:
            parts.append(" • ".join(f"{k}: {v}" for k, v in s["kinds"].items()))
        if s["sites"]:
            parts.append("En çok: " + ", ".join(f"{site} ({n})" for site, n in s["sites"]))
        if s["biggest"]:
            parts.append(f"En büyük: {s['biggest']['title'][:40]} ({human_size(s['biggest']['size'])})")
        self.more_label.configure(text="\n".join(parts))
        self.tree.delete(*self.tree.get_children())
        self.shown = self.history.find(self.search.get())[:1000]
        for i, e in enumerate(self.shown):
            speed = e["size"] / e["seconds"] if e["seconds"] >= 1 and e["size"] else 0
            self.tree.insert("", "end", iid=str(i), values=(
                tr(_when(e["finished"])), e["title"], tr({"video": "Video", "audio": "MP3"}.get(e["kind"], "Dosya")),
                human_size(e["size"]) if e["size"] else "", speed_text(speed) if speed else ""))
        if self.history.entries:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

    def _card(self, key, big, small):
        b, s = self.card_labels[key]
        b.configure(text=big)
        s.configure(text=small)

    def selected(self):
        sel = self.tree.selection()
        return self.shown[int(sel[0])] if sel and int(sel[0]) < len(self.shown) else None

    def reveal(self):
        e = self.selected()
        if e and e["path"] and os.path.exists(e["path"]):
            open_in_file_manager(e["path"])

    def clear(self):
        from tkinter import messagebox
        if self.history.entries and messagebox.askyesno(
                "DISO", "İndirme geçmişi silinsin mi?\nİndirdiğin dosyalar silinmez.", parent=self):
            self.history.clear()
            self.refresh()
