import sys
import threading

if __name__ == "__main__":
    from app import native_host
    if native_host.is_host_call(sys.argv[1:]):        # started by the browser extension: only start the app
        sys.exit(native_host.main(sys.argv[1:]))

from app.utils import setup_environment

setup_environment()  # makes ffmpeg / deno folders visible before anything else starts

from app import updater  # noqa: E402


def main(argv) -> int:
    updater.activate()  # a newer yt-dlp from packages/ must win before anything imports yt_dlp

    if "--selftest" in argv:  # check the installation without opening the window
        from app import selftest
        i = argv.index("--selftest")
        return selftest.run(argv[i + 1] if i + 1 < len(argv) else None)

    from app import bridge
    from app.config import Config

    from app import restart
    port = Config().get("bridge_port")
    # started by "restart now": wait until the old window has really gone
    restart.wait_for_previous(lambda: bridge.ping_existing(port))
    from app import backup
    backup.apply_pending()                # a backup chosen in the settings comes in now, before anything reads

    # One window only: if the app already runs, wake it up and leave.
    if bridge.ping_existing(Config().get("bridge_port")):
        bridge.show_existing(Config().get("bridge_port"))
        return 0

    import customtkinter as ctk
    from app.ui import App

    from app import i18n, look
    cfg = Config()
    if "language" not in cfg.saved:       # the first start: Windows' own language (Turkish, or else English)
        cfg.set("language", i18n.windows_language())
    i18n.set_language(cfg.get("language"))   # the interface language; before the first window exists
    from app import native_host
    threading.Thread(target=_register_host, args=(native_host,), daemon=True, name="native-host").start()
    look.apply(Config().get("look"))      # colours and shapes; before the first window exists
    app = App(minimized="--minimized" in argv)
    app.mainloop()
    if app.restart_requested:
        restart.relaunch([a for a in argv if a != "--minimized"])
    return 0


def _register_host(native_host):
    """The browser extension may start this copy of DISO when it is closed (see app/native_host.py), and a
    portable DISO.exe brings the extension's folder up to date (the browser loads it from there)."""
    from app.logs import log
    try:
        native_host.register_for_user()
    except Exception:  # noqa: BLE001 - only the "open DISO from the browser" part is missing then
        log.exception("could not register the browser's native host")
    try:
        from app import extension_setup
        extension_setup.extension_folder()
    except Exception:  # noqa: BLE001 - the browser keeps the extension it has
        log.exception("could not bring the extension's folder up to date")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
