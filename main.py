import sys

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

    # One window only: if the app already runs, wake it up and leave.
    if bridge.ping_existing(Config().get("bridge_port")):
        bridge.show_existing(Config().get("bridge_port"))
        return 0

    import customtkinter as ctk
    from app.ui import App

    ctk.set_default_color_theme("blue")
    App(minimized="--minimized" in argv).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
