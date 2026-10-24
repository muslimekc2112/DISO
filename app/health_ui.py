"""🩺 The health check window: every check with ✓ / ⚠ / ✗, what it found, and a button to fix it where DISO
can (install FFmpeg or Deno, update, add the extension, pick another folder). The checks run on a worker
thread; each row appears as soon as its check is done."""
import queue
import threading
import tkinter as tk

import customtkinter as ctk

from . import health, look
from .ui_common import fit_geometry, set_window_icon

MARKS = {health.OK: ("✓", ("#2E7D32", "#66BB6A")), health.WARN: ("⚠", ("#E08600", "#FFB74D")),
         health.BAD: ("✗", ("#C62828", "#FF7070")), health.INFO: ("•", ("gray45", "gray65"))}
FIX_TEXTS = {"ffmpeg": "FFmpeg'i kur", "deno": "Deno'yu kur", "update": "Güncelle", "extension": "Eklentiyi ekle",
             "folder": "Ayarları aç"}


class HealthWindow(ctk.CTkToplevel):
    """run_checks() -> iterable of health.Check (called on a worker thread); fix(key) does a fix; report() is
    "🐞 Sorun bildir" with the results."""

    def __init__(self, parent, run_checks, fix, report):
        super().__init__(parent)
        set_window_icon(self)
        self._run, self._fix, self._report = run_checks, fix, report
        self.results = []
        self._answers = queue.Queue()
        self.running = False
        self.title("DISO • 🩺 Sağlık kontrolü")
        fit_geometry(self, 640, 600)
        self.minsize(520, 420)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 6))
        head.columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="🩺 Sağlık kontrolü", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w")
        self.summary = ctk.CTkLabel(head, text="", text_color=look.grey_text(), anchor="w")
        self.summary.grid(row=1, column=0, sticky="w")
        self.again_btn = ctk.CTkButton(head, text="🔄 Yeniden bak", width=120, command=self.start)
        self.again_btn.grid(row=0, column=1, rowspan=2)
        self.rows = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.rows.grid(row=1, column=0, sticky="nsew", padx=12)
        self.rows.columnconfigure(1, weight=1)
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=18, pady=(8, 16))
        foot.columnconfigure(0, weight=1)
        self.copy_btn = ctk.CTkButton(foot, text="📋 Sonuçları kopyala", width=150, fg_color="transparent", border_width=1,
                                      text_color=("gray20", "gray85"), command=self.copy)
        self.copy_btn.grid(row=0, column=1, padx=(0, 8))
        self.report_btn = ctk.CTkButton(foot, text="🐞 Sorun bildir", width=130, command=lambda: self._report(self.results))
        self.report_btn.grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(foot, text="Kapat", width=90, command=self.destroy).grid(row=0, column=3)
        self.bind("<Escape>", lambda e: self.destroy())
        try:
            self.transient(parent)
        except tk.TclError:
            pass
        self.start()

    def start(self):
        if self.running:
            return
        self.running = True
        self.results = []
        for child in self.rows.winfo_children():
            child.destroy()
        self.again_btn.configure(state="disabled")
        self.summary.configure(text="Bakıyorum…")

        def work():
            try:
                for check in self._run():
                    self._answers.put(check)
            except Exception as e:  # noqa: BLE001 - shown as a row
                self._answers.put(health.Check("Kontrol", health.BAD, f"yarıda kaldı: {e}"))
            self._answers.put(None)
        threading.Thread(target=work, daemon=True, name="health").start()
        self.after(100, self._take)

    def _take(self):
        try:
            while True:
                check = self._answers.get_nowait()
                if check is None:
                    self._done()
                    return
                self._add(check)
        except queue.Empty:
            pass
        try:
            self.after(100, self._take)
        except tk.TclError:
            pass

    def _add(self, check):
        self.results.append(check)
        row = len(self.results) - 1
        mark, colour = MARKS.get(check.status, MARKS[health.INFO])
        ctk.CTkLabel(self.rows, text=mark, width=26, text_color=colour,
                     font=ctk.CTkFont(size=18, weight="bold")).grid(row=row, column=0, sticky="n", padx=(4, 6), pady=6)
        box = ctk.CTkFrame(self.rows, fg_color="transparent")
        box.grid(row=row, column=1, sticky="ew", pady=4)
        ctk.CTkLabel(box, text=check.name, anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x")
        ctk.CTkLabel(box, text=check.detail, anchor="w", justify="left", wraplength=400,
                     text_color=look.grey_text()).pack(fill="x")
        if check.fix and check.status != health.OK:
            ctk.CTkButton(self.rows, text=FIX_TEXTS.get(check.fix, "Düzelt"), width=110,
                          command=lambda key=check.fix: self._fix(key)).grid(row=row, column=2, padx=(8, 4))

    def _done(self):
        self.running = False
        self.again_btn.configure(state="normal")
        bad = sum(c.status == health.BAD for c in self.results)
        warn = sum(c.status == health.WARN for c in self.results)
        if bad:
            text = f"✗ {bad} sorun" + (f", {warn} uyarı" if warn else "") + " — düğmeyle düzeltebileceklerin yanında"
        elif warn:
            text = f"⚠ {warn} uyarı, gerisi yolunda"
        else:
            text = "✓ Her şey yolunda"
        self.summary.configure(text=text)

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(health.as_text(self.results))
        self.summary.configure(text="📋 Sonuçlar kopyalandı")
