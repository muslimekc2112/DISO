"""The name, the publisher and the version of the program: the one place they are written down.
Everything else (window titles, the installer, the registry entries, the about window) reads them from here."""

NAME = "DISO"                         # what the user sees
PUBLISHER = "ISO"                     # the folder it installs under: C:\\Program Files\\ISO\\DISO
APP_ID = "DISO"                       # in file names, the registry, locks; the browser extension looks for it
EXE_NAME = APP_ID + ".exe"

VERSION = "1.2.0"                     # numbers only (Windows and Chrome want that)
CHANNEL = ""                          # "beta" before 1.0; empty: a finished release
_SHORT = VERSION[:-2] if VERSION.count(".") == 2 and VERSION.endswith(".0") else VERSION     # 1.0.0 -> 1.0
VERSION_LABEL = f"{_SHORT} {CHANNEL}" if CHANNEL else _SHORT          # what the user sees: 1.0
FILE_LABEL = VERSION_LABEL.replace(" ", "-")   # in file names: DISO-Setup-1.0.exe

HOME_URL = "https://github.com/muslimekc2112/DISO"
CONTACT_URL = HOME_URL + "/issues/new"          # "Contact us": a new issue on GitHub

DATA_DIR_NAME = APP_ID                         # %LOCALAPPDATA%\\DISO: settings, playlists, downloads list, tools
LEGACY_DATA_DIR_NAMES = (".hizli_indirici",)    # where earlier versions kept them (in the user's home folder)
LEGACY_APP_IDS = ("HizliIndirici",)             # earlier names of the program in the registry and in shortcuts
