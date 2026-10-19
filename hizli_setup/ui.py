"""The windows of the installer and the uninstaller (same look as the program itself)."""
import gc
import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app import brand, extension_setup, look
from app.ui_common import logo_image, set_if_changed
from app.utils import resource_path

from . import core, winapi

log = logging.getLogger("hizli_setup")
CREATE_NO_WINDOW = 0x08000000
DETACHED = 0x00000008 | 0x00000200


def launch(exe_path):
    """Start the installed program as a separate program that runs as the normal user (we may be running
    as administrator, and it must not share our temporary files)."""
    ok = winapi.launch_unelevated(exe_path)
    if not ok:
        log.error("could not start %s", exe_path)
    return ok


class _Window(ctk.CTk):
    """A small fixed-size window: header, one page at a time, a row of buttons."""

    def __init__(self, title, subtitle):
        super().__init__()
        # Garbage collection must run on this (the window's) thread only: a Tk object finalized on the
        # worker thread calls into Tcl from the wrong thread and both threads freeze. poll() collects.
        gc.disable()
        self._polls = 0
        self.title(title)
        self.exit_code = 1
        self.finished = False                    # a result (good or bad) is on the screen
        self._closing_blocked = False
        w = 640
        h = min(660, max(480, self.winfo_screenheight() - 90))          # tall enough for the options, never taller than the screen
        self.geometry(f"{w}x{h}+{max(0, (self.winfo_screenwidth() - w) // 2)}+{max(0, (self.winfo_screenheight() - h) // 3)}")
        self.resizable(False, False)
        ico = resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(ico):
            try:
                self.iconbitmap(ico)
            except tk.TclError:
                pass
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 6))
        head.columnconfigure(1, weight=1)
        self._logo = logo_image(60)                              # kept on self: a picture nobody holds disappears
        ctk.CTkLabel(head, text="" if self._logo else "⚡", image=self._logo, width=64, height=64).grid(
            row=0, column=0, rowspan=2, padx=(0, 16))
        titlebox = ctk.CTkFrame(head, fg_color="transparent")
        titlebox.grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(titlebox, text=core.DISPLAY_NAME, font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        ctk.CTkLabel(titlebox, text=brand.CHANNEL.upper(), width=48, height=22, corner_radius=8,
                     fg_color=look.ACCENT_SOFT if look.is_new() else ("gray78", "gray28"),
                     text_color=look.ACCENT if look.is_new() else ("gray20", "gray85"),
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(10, 0), pady=(8, 0))
        ctk.CTkLabel(head, text=subtitle, text_color="gray").grid(row=1, column=1, sticky="nw")
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=28, pady=8)
        self.body.columnconfigure(0, weight=1)
        self.buttons = ctk.CTkFrame(self, fg_color="transparent")
        self.buttons.grid(row=2, column=0, sticky="ew", padx=28, pady=(6, 24))
        self.buttons.columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self._on_x)
        self._events = queue.Queue()

    # ---- pages
    def clear(self):
        for frame in (self.body, self.buttons):
            for child in frame.winfo_children():
                child.destroy()

    def add_buttons(self, *specs):
        """specs: (text, command, primary) from left to right; they sit at the right edge."""
        for i, (text, command, primary) in enumerate(specs, start=1):
            btn = ctk.CTkButton(self.buttons, text=text, width=130, height=38, command=command,
                                fg_color=None if primary else ("gray70", "gray30"),
                                text_color=None if primary else ("gray10", "gray90"))
            btn.grid(row=0, column=i, padx=(8, 0))
            yield btn

    def progress_page(self, title, first_text):
        self.clear()
        ctk.CTkLabel(self.body, text=title, font=ctk.CTkFont(size=20, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", pady=(20, 6))
        self.status = ctk.CTkLabel(self.body, text=first_text, anchor="w", text_color="gray")
        self.status.grid(row=1, column=0, sticky="ew")
        self.bar = ctk.CTkProgressBar(self.body, height=14)
        self.bar.set(0)
        self.bar.grid(row=2, column=0, sticky="ew", pady=18)
        ctk.CTkLabel(self.body, text="Bitene kadar pencereyi kapatma, az kaldı.", text_color="gray", anchor="w").grid(
            row=3, column=0, sticky="ew")
        self._closing_blocked = True

    def finish_page(self, ok, title, text, details=""):
        self._closing_blocked = False
        self.finished = True
        self.clear()
        ctk.CTkLabel(self.body, text=("✓  " if ok else "✖  ") + title, anchor="w", font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=look.STATE_DONE if ok else look.STATE_ERROR).grid(row=0, column=0, sticky="ew", pady=(24, 8))
        ctk.CTkLabel(self.body, text=text, anchor="w", justify="left", wraplength=560).grid(row=1, column=0, sticky="ew")
        if details:
            ctk.CTkLabel(self.body, text=details, anchor="w", justify="left", wraplength=560, text_color="gray").grid(
                row=2, column=0, sticky="ew", pady=(10, 0))

    # ---- thread -> window
    def run_in_thread(self, work):
        """Run work(progress) away from the window; its answer comes back through poll()."""
        def runner():
            try:
                self._events.put(("done", work(lambda f, t: self._events.put(("progress", (f, t))))))
            except core.SetupError as e:
                log.error("setup error: %s", e)
                self._events.put(("error", str(e)))
            except BaseException as e:  # noqa: BLE001 - shown to the user, never a silent death
                log.exception("unexpected error")
                self._events.put(("error", f"Hoppala, beklenmedik bir şey oldu: {type(e).__name__}: {e}"))

        threading.Thread(target=runner, daemon=True, name="setup-work").start()
        self.after(60, self.poll)

    def poll(self):
        self._polls += 1
        if self._polls % 20 == 0:
            gc.collect()
        try:
            while True:
                kind, data = self._events.get_nowait()
                if kind == "progress":
                    fraction, text = data
                    self.bar.set(max(0.0, min(1.0, fraction)))
                    set_if_changed(self.status, text=text)
                else:
                    self.on_result(kind, data)
                    return
        except queue.Empty:
            pass
        self.after(60, self.poll)

    def on_result(self, kind, data):
        raise NotImplementedError

    def destroy(self):
        gc.collect()
        try:
            super().destroy()
        finally:
            gc.enable()

    def _on_x(self):
        if self._closing_blocked:
            messagebox.showinfo(core.DISPLAY_NAME, "İşlem sürüyor, bitmesini bekle.", parent=self)
            return
        self.cancel()

    def cancel(self):
        if not self.finished:                    # closing after a result keeps that result's exit code
            self.exit_code = 1
        self.destroy()


class SetupWindow(_Window):
    def __init__(self, payload_dir, env, closer=winapi.close_programs_in, preset_dir=None, on_launch=launch,
                 browsers=None, start=winapi.start_as_user):
        super().__init__(f"{core.DISPLAY_NAME} Kurulumu", f"Sürüm {brand.VERSION_LABEL} • Kurulum")
        self.payload_dir, self.env, self.closer, self.on_launch = payload_dir, env, closer, on_launch
        self.browsers = extension_setup.find_browsers() if browsers is None else dict(browsers)
        self.browser_vars = {b: tk.BooleanVar(value=True) for b in self.browsers}     # which ones get the extension
        self.start = start
        self.guide = None
        self.result = None
        existing_dir, existing_version = core.find_existing(env)
        self.existing = (existing_dir, existing_version)
        self.dir_var = tk.StringVar(value=preset_dir or existing_dir or env.default_install_dir)
        self.desktop_var = tk.BooleanVar(value=True)
        self.menu_var = tk.BooleanVar(value=True)
        self.autostart_var = tk.BooleanVar(value=False)
        self.launch_var = tk.BooleanVar(value=True)
        self.options_page()

    def options_page(self):
        self.clear()
        try:
            data = core.load_payload(self.payload_dir)
            self.version = str(data.get("version", ""))
            need = int(sum(f["size"] for f in data["files"]) / (1 << 20))
        except core.SetupError as e:
            self.finish_page(False, "Kurulum paketi okunamadı", str(e))
            list(self.add_buttons(("Kapat", self.cancel, True)))
            return
        old_dir, old_version = self.existing
        if old_dir:
            intro = f"DISO {old_version or ''} bu bilgisayarda kurulu; {self.version} sürümüne güncelleyeceğim."
        else:
            intro = f"DISO {self.version} bu bilgisayara kurulacak. Python ya da başka bir şey kurmana gerek yok, her şey içinde."
        ctk.CTkLabel(self.body, text=intro, anchor="w", justify="left", wraplength=570).grid(row=0, column=0, sticky="ew", pady=(10, 14))
        ctk.CTkLabel(self.body, text="Kurulum klasörü", anchor="w", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, sticky="ew")
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", pady=(4, 2))
        row.columnconfigure(0, weight=1)
        self.dir_entry = ctk.CTkEntry(row, textvariable=self.dir_var, height=36)
        self.dir_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(row, text="Gözat…", width=96, height=36, command=self.browse).grid(row=0, column=1, padx=(8, 0))
        self.hint = ctk.CTkLabel(self.body, text=f"Yaklaşık {need} MB yer kaplar. Bu bilgisayardaki herkes için kurulur.", anchor="w", text_color="gray")
        self.hint.grid(row=3, column=0, sticky="ew")
        for i, (text, var) in enumerate((("Masaüstüne kısayol koy", self.desktop_var),
                                         ("Başlat menüsüne kısayol koy", self.menu_var),
                                         ("Windows açılınca kendiliğinden başlasın (tepside)", self.autostart_var),
                                         ("Kurulum bitince uygulamayı aç", self.launch_var)), start=4):
            ctk.CTkSwitch(self.body, text=text, variable=var).grid(row=i, column=0, sticky="w", pady=(10 if i == 4 else 4, 0))
        if self.browsers:
            ctk.CTkLabel(self.body, text="🧩 Tarayıcı eklentisi: linke sağ tık → “DISO ile indir” (IDM gibi). Hangilerine?",
                         anchor="w", justify="left", wraplength=570).grid(row=8, column=0, sticky="ew", pady=(12, 2))
            box = ctk.CTkFrame(self.body, fg_color="transparent")
            box.grid(row=9, column=0, sticky="w")
            for n, (bid, var) in enumerate(self.browser_vars.items()):
                ctk.CTkCheckBox(box, text=extension_setup.NAMES[bid], variable=var, width=150).grid(
                    row=n // 3, column=n % 3, sticky="w", padx=(0, 8), pady=2)
        self.error = ctk.CTkLabel(self.body, text="", anchor="w", justify="left", wraplength=570, text_color=look.STATE_ERROR)
        self.error.grid(row=10, column=0, sticky="ew", pady=(12, 0))
        self.install_btn = list(self.add_buttons(("Kur", self.start_install, True), ("İptal", self.cancel, False)))[0]

    def browse(self):
        chosen = filedialog.askdirectory(parent=self, title="Kurulum klasörünü seç", initialdir=self._guess_dir())
        if chosen:
            self.dir_var.set(os.path.normpath(chosen))

    def _guess_dir(self):
        d = self.dir_var.get().strip().strip('"')
        while d and not os.path.isdir(d):
            parent = os.path.dirname(d)
            if parent == d:
                return None
            d = parent
        return d or None

    def start_install(self):
        try:
            target = core.resolve_install_dir(self.dir_var.get())
        except core.SetupError as e:
            self.error.configure(text=str(e))
            return
        options = core.Options(install_dir=target, desktop_shortcut=bool(self.desktop_var.get()),
                               start_menu=bool(self.menu_var.get()), autostart=True if self.autostart_var.get() else None,
                               browsers=self.chosen_browsers())
        self.progress_page("Kuruluyor…", "Hazırlanıyor…")
        list(self.add_buttons())
        self.run_in_thread(lambda progress: core.install(self.payload_dir, options, self.env, progress=progress, closer=self.closer))

    def on_result(self, kind, data):
        if kind == "done":
            self.result = data
            self.exit_code = 0
            self.finish_page(True, "Kurulum bitti, hazırız", f"DISO {data.version} kuruldu.\n{data.install_dir}",
                             "\n".join(data.warnings))
            if self.chosen_browsers() and os.path.isdir(self.extension_dir()):
                list(self.add_buttons(("🧩 Eklentiyi ekle", self.open_guide, False), ("Bitir", self.finish, True)))
                self.open_guide()
            else:
                list(self.add_buttons(("Bitir", self.finish, True)))
        else:
            self.exit_code = 2
            self.finish_page(False, "Kurulumu yapamadım", data, "Bilgisayarında hiçbir değişiklik bırakmadım.")
            list(self.add_buttons(("Kapat", self.cancel, True), ("Tekrar dene", self.options_page_again, False)))

    def chosen_browsers(self):
        return tuple(b for b, var in self.browser_vars.items() if var.get())

    def extension_dir(self):
        return os.path.join(self.result.install_dir, "browser_extension") if self.result else ""

    def open_guide(self):
        """The steps that put the extension into the browsers the user picked."""
        try:
            if self.guide is not None and self.guide.winfo_exists():
                self.guide.lift()
                return
        except tk.TclError:
            pass
        chosen = self.chosen_browsers()
        self.guide = extension_setup.ExtensionGuide(self, browsers={b: self.browsers[b] for b in chosen},
                                                    folder=self.extension_dir(), start=self.start)

    def options_page_again(self):
        self.exit_code = 1
        self.finished = False
        self.options_page()

    def finish(self):
        if self.result is not None and self.launch_var.get():
            self.on_launch(self.result.exe_path)
        self.destroy()


class UninstallWindow(_Window):
    def __init__(self, install_dir, env, closer=winapi.close_programs_in, remove_data=False, keep=()):
        super().__init__(f"{core.DISPLAY_NAME} - Kaldır", "Kaldırma sihirbazı")
        self.install_dir, self.env, self.closer, self.keep = install_dir, env, closer, keep
        self.data_var = tk.BooleanVar(value=remove_data)
        self.result = None
        self.confirm_page()

    def confirm_page(self):
        self.clear()
        ctk.CTkLabel(self.body, text=f"{core.DISPLAY_NAME} bu bilgisayardan kaldırılsın mı?", anchor="w",
                     font=ctk.CTkFont(size=20, weight="bold"), wraplength=570, justify="left").grid(row=0, column=0, sticky="ew", pady=(20, 8))
        ctk.CTkLabel(self.body, text=f"Uygulama dosyaları, kısayollar ve kayıt girdileri silinir.\n{self.install_dir}", anchor="w",
                     justify="left", wraplength=570, text_color="gray").grid(row=1, column=0, sticky="ew")
        ctk.CTkSwitch(self.body, text="Ayarlarımı ve çalma listelerimi de sil",
                      variable=self.data_var).grid(row=2, column=0, sticky="w", pady=(22, 2))
        ctk.CTkLabel(self.body, text="Kapalı bırakırsan ayarların, çalma listelerin ve müzik çalardan bulup indirdiğin "
                                     "şarkılar kalır; DISO'yu tekrar kurarsan olduğu gibi gelir. Açarsan bunlar da "
                                     "silinir. İndirme klasörüne indirdiklerine hiç dokunmam.", anchor="w",
                     justify="left", wraplength=570, text_color="gray").grid(row=3, column=0, sticky="ew")
        list(self.add_buttons(("Kaldır", self.start, True), ("Vazgeç", self.cancel, False)))

    def start(self):
        remove = bool(self.data_var.get())
        self.progress_page("Kaldırılıyor…", "Hazırlanıyor…")
        list(self.add_buttons())
        self.run_in_thread(lambda progress: core.uninstall(self.install_dir, self.env, remove_data=remove,
                                                           progress=progress, closer=self.closer, keep=self.keep))

    def on_result(self, kind, data):
        if kind == "done":
            self.result = data
            self.exit_code = 0
            note = ""
            if data.leftovers:
                note = "Şu dosyalar kullanımda olduğu için bilgisayar yeniden başlayınca silinecek:\n" + "\n".join(data.leftovers[:6])
            self.finish_page(True, "Kaldırıldı", f"{core.DISPLAY_NAME} bu bilgisayardan kaldırıldı. Görüşmek üzere!", note)
            list(self.add_buttons(("Bitir", self.destroy, True)))
        else:
            self.exit_code = 2
            self.finish_page(False, "Kaldırmayı tamamlayamadım", data)
            list(self.add_buttons(("Kapat", self.cancel, True)))
