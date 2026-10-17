import customtkinter as ctk

from app.utils import setup_environment

setup_environment()  # makes ffmpeg / deno folders visible before anything else starts

from app import updater  # noqa: E402
from app.ui import App  # noqa: E402

if __name__ == "__main__":
    updater.activate()  # a newer yt-dlp from packages/ must win before anything imports yt_dlp
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    App().mainloop()
