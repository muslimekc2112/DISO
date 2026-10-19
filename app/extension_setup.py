"""Putting DISO's extension into the user's browsers: which browsers there are, where the extension's
folder is, and a small window that walks the user through "Load unpacked" (browsers only install
extensions from their stores by themselves). Used by the app (Settings) and by the installer."""
import os
import shutil
import subprocess
import sys

import customtkinter as ctk

from .ui_common import fit_geometry, set_window_icon

# id, name shown, program, its extensions page
BROWSERS = (
    ("chrome", "Google Chrome", "chrome.exe", "chrome://extensions/"),
    ("edge", "Microsoft Edge", "msedge.exe", "edge://extensions/"),
    ("brave", "Brave", "brave.exe", "brave://extensions/"),
    ("opera", "Opera", "opera.exe", "opera://extensions"),
    ("vivaldi", "Vivaldi", "vivaldi.exe", "vivaldi://extensions/"),
    ("firefox", "Firefox", "firefox.exe", "about:debugging#/runtime/this-firefox"),
)
NAMES = {b[0]: b[1] for b in BROWSERS}
ADD_TO = {"chrome": "Chrome'a ekle", "edge": "Edge'e ekle", "brave": "Brave'e ekle", "opera": "Opera'ya ekle",
          "vivaldi": "Vivaldi'ye ekle", "firefox": "Firefox'a ekle"}
APP_PATHS = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
# where the browsers put themselves when App Paths says nothing ({pf}: Program Files, {pf86}, {local})
KNOWN_PLACES = {
    "chrome": [r"{pf}\Google\Chrome\Application\chrome.exe", r"{pf86}\Google\Chrome\Application\chrome.exe",
               r"{local}\Google\Chrome\Application\chrome.exe"],
    "edge": [r"{pf86}\Microsoft\Edge\Application\msedge.exe", r"{pf}\Microsoft\Edge\Application\msedge.exe"],
    "brave": [r"{pf}\BraveSoftware\Brave-Browser\Application\brave.exe",
              r"{local}\BraveSoftware\Brave-Browser\Application\brave.exe"],
    "opera": [r"{local}\Programs\Opera\opera.exe", r"{local}\Programs\Opera\launcher.exe", r"{pf}\Opera\opera.exe"],
    "vivaldi": [r"{local}\Vivaldi\Application\vivaldi.exe", r"{pf}\Vivaldi\Application\vivaldi.exe"],
    "firefox": [r"{pf}\Mozilla Firefox\firefox.exe", r"{pf86}\Mozilla Firefox\firefox.exe"],
}


def _app_path(exe_name):
    """The browser's program as Windows' "App Paths" knows it (machine-wide, then this user)."""
    try:
        import winreg
    except ImportError:
        return None
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, APP_PATHS + "\\" + exe_name) as key:
                value = str(winreg.QueryValueEx(key, "")[0]).strip().strip('"')
            if value:
                return value
        except OSError:
            continue
    return None


def find_browsers(app_path=_app_path, exists=os.path.isfile, environ=os.environ) -> dict:
    """{browser id: program path} of the browsers on this PC, in the order of BROWSERS."""
    places = {"pf": environ.get("ProgramFiles", r"C:\Program Files"),
              "pf86": environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
              "local": environ.get("LOCALAPPDATA", "")}
    found = {}
    for bid, _name, exe, _page in BROWSERS:
        candidates = [app_path(exe)] + [p.format(**places) for p in KNOWN_PLACES.get(bid, [])]
        for path in candidates:
            if path and exists(path):
                found[bid] = path
                break
    return found


def extension_folder(data_dir=None, frozen=None, executable=None, bundled=None) -> str:
    """A folder of the extension that stays where it is (a browser keeps loading it from there):
    next to an installed DISO.exe; from source the project's own folder; a portable exe copies the
    one it carries into the data folder (its own files vanish when it closes)."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    if frozen:
        beside = os.path.join(os.path.dirname(executable), "browser_extension")
        if os.path.isfile(os.path.join(beside, "manifest.json")):
            return beside
    from .utils import app_data_dir, resource_path
    bundled = bundled or resource_path("browser_extension")
    if not frozen:
        return bundled
    target = os.path.join(data_dir or app_data_dir(), "browser_extension")
    if _manifest_text(target) != _manifest_text(bundled):          # missing, or an older version
        # written over in place (the browser may be reading it right now); the manifest last, so a copy
        # cut short is tried again at the next start
        shutil.copytree(bundled, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("manifest.json"))
        shutil.copyfile(os.path.join(bundled, "manifest.json"), os.path.join(target, "manifest.json"))
    return target


def firefox_folder(folder, data_dir=None) -> str:
    """Firefox needs a manifest of its own (background scripts instead of Chrome's service worker, its
    add-on id): a copy of the extension with manifest.firefox.json as its manifest.json, made fresh."""
    from .utils import app_data_dir
    target = os.path.join(data_dir or app_data_dir(), "browser_extension_firefox")
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(folder, target, ignore=shutil.ignore_patterns("manifest.json", "manifest.firefox.json", "sw.js"))
    shutil.copyfile(os.path.join(folder, "manifest.firefox.json"), os.path.join(target, "manifest.json"))
    return target


def _manifest_text(folder):
    try:
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _start(exe, args=()):
    subprocess.Popen([exe, *args], close_fds=True, creationflags=0x00000008 | 0x00000200,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def open_for(browser, program, folder, start=_start) -> bool:
    """Open the browser's extensions page and the extension's folder next to it."""
    page = next(b[3] for b in BROWSERS if b[0] == browser)
    try:
        if start(program, [page]) is False:
            return False
        start("explorer.exe", [os.path.normpath(folder)])
        return True
    except OSError:
        return False


# ------------------------------------------------------------------------------- the window
STEPS = ("1. Aşağıdan tarayıcını seç: eklentiler sayfası ve eklenti klasörü açılır, klasörün yolu panoya kopyalanır.\n"
         "2. Eklentiler sayfasında sağ üstteki “Geliştirici modu”nu aç.\n"
         "3. “Paketlenmemiş öğe yükle”ye bas, açılan pencerenin adres çubuğuna Ctrl+V ile yolu yapıştır ve "
         "“Klasör seç”e bas. (Ya da açılan klasörü eklentiler sayfasının üstüne sürükleyip bırak.)\n"
         "4. Hazır! Bir linke sağ tıkla → “DISO ile indir”. DISO kapalıysa kendisi açılır.")
FIREFOX_NOTE = ("Firefox: about:debugging sayfasında “Geçici eklenti yükle”ye bas ve klasördeki manifest.json "
                "dosyasını seç. Firefox imzasız eklentileri kalıcı kurmadığı için Firefox kapanınca eklenti de kalkar.")


OFFER_TEXT = ("DISO'nun tarayıcı eklentisiyle indirmek çok daha kolay: bir linke sağ tıkla, “DISO ile indir”i seç; "
              "indirme hemen DISO'da başlasın. DISO kapalıysa eklenti onu kendisi açar.\n\n"
              "Chrome, Edge, Brave, Opera, Vivaldi ve Firefox'ta çalışır. Eklemek bir dakika sürer; ne yapacağını "
              "adım adım göstereceğim.")


class ExtensionOffer(ctk.CTkToplevel):
    """'Shall we add DISO to your browser?' - asked once the app runs, until the extension is in a browser."""

    def __init__(self, parent, on_add, on_later, on_never):
        super().__init__(parent)
        self.title("DISO • Tarayıcı eklentisi")
        self.resizable(False, False)
        self.transient(parent)
        set_window_icon(self)
        self.columnconfigure(0, weight=1)
        self.answer = None
        ctk.CTkLabel(self, text="🧩 DISO'yu tarayıcına ekleyelim mi?", font=ctk.CTkFont(size=20, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 8))
        ctk.CTkLabel(self, text=OFFER_TEXT, anchor="w", justify="left", wraplength=480).grid(
            row=1, column=0, sticky="ew", padx=26)
        ctk.CTkLabel(self, text="İstediğin zaman Ayarlar → Tarayıcıya ekle'den de ekleyebilirsin.", anchor="w",
                     text_color="gray", font=ctk.CTkFont(size=11)).grid(row=2, column=0, sticky="ew", padx=26, pady=(10, 0))
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=22, pady=(16, 20))
        foot.columnconfigure(0, weight=1)
        self.never_btn = ctk.CTkButton(foot, text="Bir daha sorma", width=120, fg_color="transparent", border_width=1,
                                       text_color=("gray20", "gray80"), command=lambda: self._answer("never", on_never))
        self.never_btn.grid(row=0, column=0, sticky="w")
        self.later_btn = ctk.CTkButton(foot, text="Sonra hatırlat", width=120, fg_color=("gray70", "gray30"),
                                       text_color=("gray10", "gray90"), command=lambda: self._answer("later", on_later))
        self.later_btn.grid(row=0, column=1, padx=8)
        self.add_btn = ctk.CTkButton(foot, text="🧩 Eklentiyi ekle", width=150, command=lambda: self._answer("add", on_add))
        self.add_btn.grid(row=0, column=2)
        self.protocol("WM_DELETE_WINDOW", lambda: self._answer("later", on_later))     # the X is "later", not "never"
        self.after(150, self.lift)

    def _answer(self, answer, action):
        self.answer = answer
        self.destroy()
        action()


class ExtensionGuide(ctk.CTkToplevel):
    """'Add DISO to your browser': a button per browser, and the steps."""

    def __init__(self, parent, browsers=None, folder=None, start=_start, only=None):
        super().__init__(parent)
        self.title("DISO • Tarayıcı eklentisi")
        w, h = fit_geometry(self, 640, 580)
        self.minsize(min(520, w), min(460, h))
        self.transient(parent)
        set_window_icon(self)
        self.start = start
        self.folder = folder or extension_folder()
        found = find_browsers() if browsers is None else browsers
        self.browsers = {b: p for b, p in found.items() if only is None or b in only}
        self.columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="🧩 DISO'yu tarayıcına ekle", font=ctk.CTkFont(size=20, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 4))
        ctk.CTkLabel(self, text="Linke sağ tıkla → “DISO ile indir”: indirme hemen DISO'da başlar. İstersen tarayıcının "
                                "kendi indirmelerini de DISO alır. DISO kapalıysa kendisi açılır.", anchor="w", justify="left",
                     wraplength=570, text_color="gray").grid(row=1, column=0, sticky="ew", padx=24)
        ctk.CTkLabel(self, text=STEPS, anchor="w", justify="left", wraplength=570).grid(
            row=2, column=0, sticky="ew", padx=24, pady=(14, 8))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=3, column=0, sticky="ew", padx=20, pady=4)
        self.buttons = {}
        if not self.browsers:
            ctk.CTkLabel(row, text="Bu bilgisayarda desteklenen bir tarayıcı bulamadım (Chrome, Edge, Brave, Opera, "
                                   "Vivaldi, Firefox).", text_color="gray", wraplength=560, justify="left").pack(anchor="w")
        for i, (bid, program) in enumerate(self.browsers.items()):
            b = ctk.CTkButton(row, text="🧩 " + ADD_TO[bid], width=180,
                              command=lambda bid=bid, program=program: self.add_to(bid, program))
            b.grid(row=i // 3, column=i % 3, padx=4, pady=4, sticky="w")
            self.buttons[bid] = b
        self.status = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=570, text_color="gray")
        self.status.grid(row=4, column=0, sticky="ew", padx=24, pady=(6, 0))
        if "firefox" in self.browsers:
            ctk.CTkLabel(self, text=FIREFOX_NOTE, anchor="w", justify="left", wraplength=570, text_color="gray",
                         font=ctk.CTkFont(size=11)).grid(row=5, column=0, sticky="ew", padx=24, pady=(8, 0))
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=6, column=0, sticky="ew", padx=24, pady=(14, 18))
        foot.columnconfigure(0, weight=1)
        ctk.CTkLabel(foot, text=self.folder, anchor="w", text_color="gray", font=ctk.CTkFont(size=11),
                     wraplength=420, justify="left").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(foot, text="Kapat", width=100, command=self.destroy).grid(row=0, column=1)
        self.after(150, self.lift)

    def add_to(self, browser, program):
        folder = self.folder
        if browser == "firefox":
            try:
                folder = firefox_folder(self.folder)
            except OSError:
                self.status.configure(text="Firefox için eklenti klasörünü hazırlayamadım.")
                return
        self.clipboard_clear()
        self.clipboard_append(folder)
        if open_for(browser, program, folder, start=self.start):
            self.status.configure(text="Eklentiler sayfası açıldı, klasörün yolu panoya kopyalandı. Şimdi 2. ve 3. adım.")
        else:
            self.status.configure(text="Tarayıcıyı açamadım; klasörün yolu panoya kopyalandı, eklentiler sayfasını elle aç.")
