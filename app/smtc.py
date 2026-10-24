"""DISO in Windows' own media panel (the box that opens with the volume keys, and the one in the
quick settings): the song's title, artist and cover, and its play / pause / next / previous buttons.

Windows calls this the "System Media Transport Controls". A desktop program gets them through a
MediaPlayer object whose own controls are switched off: we only use its panel, the sound still
comes from our MCI player. Everything runs on one thread of its own (WinRT calls and the cover
file are slow); the window only sends wishes and reads the pressed buttons. Without the winrt
packages (or on an old Windows) the class quietly does nothing."""
import asyncio
import os
import queue
import threading

from .logs import log

try:                                                     # noqa: SIM105 - the import itself is the test
    from winrt.windows.media import (MediaPlaybackStatus, MediaPlaybackType,
                                     SystemMediaTransportControlsButton)
    from winrt.windows.media.playback import MediaPlayer
    AVAILABLE = True
except Exception:  # noqa: BLE001 - no winrt: no panel
    AVAILABLE = False

BUTTONS = {"PLAY": "toggle", "PAUSE": "toggle", "NEXT": "next", "PREVIOUS": "previous", "STOP": "stop"}


class MediaOverlay:
    """show(track info) / status("playing" | "paused" | "stopped") / pressed queue / close()."""

    def __init__(self):
        self.pressed = queue.Queue()              # "toggle" / "next" / "previous" / "stop"
        self.available = AVAILABLE
        self._jobs = queue.Queue()
        self._thread = None
        self._shown = None                        # (title, artist, album, cover) last sent
        self._status = None
        if self.available:
            self._thread = threading.Thread(target=self._run, name="media-panel", daemon=True)
            self._thread.start()

    # ------------------------------------------------------------------ what the window calls
    def show(self, title, artist="", album="", cover=None):
        info = (title or "", artist or "", album or "", cover if cover and os.path.isfile(cover) else None)
        if self.available and info != self._shown:
            self._shown = info
            self._jobs.put(("show", info))

    def status(self, state):
        if self.available and state != self._status:
            self._status = state
            self._jobs.put(("status", state))

    def close(self):
        if self._thread is not None:
            self._jobs.put(None)
            self._thread.join(2)
            self._thread = None

    # ------------------------------------------------------------------ the panel's own thread
    def _run(self):
        try:
            player = MediaPlayer()
            player.command_manager.is_enabled = False          # its own commands off: the panel is ours
            smtc = player.system_media_transport_controls
            smtc.is_play_enabled = smtc.is_pause_enabled = True
            smtc.is_next_enabled = smtc.is_previous_enabled = smtc.is_stop_enabled = True
            names = {getattr(SystemMediaTransportControlsButton, k): v for k, v in BUTTONS.items()}
            token = smtc.add_button_pressed(lambda sender, args: self.pressed.put(names.get(args.button, "")))
        except Exception:  # noqa: BLE001 - no panel on this Windows; the player works without it
            log.exception("media panel unavailable")
            self.available = False
            return
        try:
            while True:
                job = self._jobs.get()
                if job is None:
                    break
                try:
                    if job[0] == "show":
                        asyncio.run(self._show(smtc, *job[1]))
                    else:
                        self._set_status(smtc, job[1])
                except Exception:  # noqa: BLE001 - one bad cover must not end the panel
                    log.exception("media panel update failed")
        finally:
            try:
                smtc.remove_button_pressed(token)
                smtc.is_enabled = False
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    async def _show(smtc, title, artist, album, cover):
        updater = smtc.display_updater
        updater.clear_all()
        updater.type = MediaPlaybackType.MUSIC
        props = updater.music_properties
        props.title, props.artist, props.album_title = title, artist, album
        if cover:
            from winrt.windows.storage import StorageFile
            from winrt.windows.storage.streams import RandomAccessStreamReference
            file = await StorageFile.get_file_from_path_async(os.path.abspath(cover))
            updater.thumbnail = RandomAccessStreamReference.create_from_file(file)
        updater.update()
        smtc.is_enabled = True

    @staticmethod
    def _set_status(smtc, state):
        smtc.is_enabled = state != "stopped"
        smtc.playback_status = {"playing": MediaPlaybackStatus.PLAYING, "paused": MediaPlaybackStatus.PAUSED,
                                "stopped": MediaPlaybackStatus.STOPPED}.get(state, MediaPlaybackStatus.STOPPED)
