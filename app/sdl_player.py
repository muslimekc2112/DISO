"""Music playback on macOS and Linux: ffmpeg turns the file into plain sound, SDL (pygame) plays it.

Windows has MCI (player.MciBackend). Elsewhere nothing like it is built in, so: ffmpeg (which DISO has
anyway) decodes any file it knows into 16-bit stereo at 44.1 kHz, a small thread hands that to an SDL
mixer channel in short pieces, and the channel's own volume and pause do the rest. Every backend has a
channel of its own, so two can sound at once (cross-fade, preview). The methods are MciBackend's."""
import json
import os
import subprocess
import threading
import time

from .logs import log
from .utils import subprocess_flags

RATE, CHANNELS, SAMPLE_BYTES = 44100, 2, 2
FRAME = CHANNELS * SAMPLE_BYTES
PIECE_MS = 200                                   # how much sound is handed over at once
PIECE = RATE * FRAME * PIECE_MS // 1000
MAX_CHANNELS = 16

_mixer_lock = threading.Lock()
_channels_used = [0]


def _pygame():
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
    with _mixer_lock:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=RATE, size=-16, channels=CHANNELS, buffer=2048)
            pygame.mixer.set_num_channels(MAX_CHANNELS)
    return pygame


def _tool(name):
    from .tags import _tool as find
    return find(name)


def probe_length_ms(path: str) -> int:
    """The length of the file's sound in ms; 0 when it has no sound ffprobe can read."""
    ffprobe = _tool("ffprobe")
    if not ffprobe:
        return 0
    try:
        proc = subprocess.run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                               "stream=codec_name:format=duration", "-print_format", "json", path],
                              capture_output=True, timeout=30, stdin=subprocess.DEVNULL, **subprocess_flags())
        data = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
        if not data.get("streams"):
            return 0
        return max(1, int(float(data.get("format", {}).get("duration") or 0) * 1000))
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0


class SdlBackend:
    """Plays one file at a time (anything ffmpeg can read)."""

    def __init__(self, alias=""):
        try:
            pg = _pygame()
            with _mixer_lock:
                number = _channels_used[0] % MAX_CHANNELS
                _channels_used[0] += 1
            self._channel = pg.mixer.Channel(number)
        except Exception as e:  # noqa: BLE001 - no pygame or no sound device: the caller says so
            raise OSError(f"no sound output: {e}") from e
        self._pg = pg
        self.alias = alias
        self._lock = threading.RLock()
        self._path = None
        self._length = 0
        self._volume = 80
        self._proc = None
        self._gen = 0                 # every start / stop makes the feeding thread of the last one quit
        self._base = 0                # where in the song the running decoder started (ms)
        self._began = None            # monotonic time the first piece of it started to sound
        self._paused_at = None
        self._paused_for = 0.0
        self._eof = False
        self._playing = False         # play was started and the user did not stop / pause it
        self.last_error = ""

    @staticmethod
    def available() -> bool:
        try:
            _pygame()
            return True
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------ the decoder
    def _start_decoder(self, at_ms):
        self._stop_decoder()
        ffmpeg = _tool("ffmpeg")
        if not ffmpeg:
            self.last_error = "ffmpeg not found"
            return False
        args = [ffmpeg, "-nostdin", "-v", "error"]
        if at_ms > 0:
            args += ["-ss", f"{at_ms / 1000:.3f}"]
        args += ["-i", self._path, "-vn", "-f", "s16le", "-acodec", "pcm_s16le", "-ac", str(CHANNELS),
                 "-ar", str(RATE), "pipe:1"]
        try:
            self._proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, **subprocess_flags())
        except OSError as e:
            self.last_error = str(e)
            return False
        self._gen += 1
        self._base, self._began, self._paused_at, self._paused_for, self._eof = at_ms, None, None, 0.0, False
        threading.Thread(target=self._feed, args=(self._gen, self._proc), daemon=True, name="sdl-feed").start()
        return True

    def _stop_decoder(self):
        self._gen += 1
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.kill()
                proc.stdout.close()
                proc.wait(2)
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
        self._channel.stop()

    def _feed(self, gen, proc):
        """Hands the decoded sound to the channel, one piece while the one before it sounds."""
        try:
            while True:
                data = self._read(proc.stdout)
                if gen != self._gen:
                    return
                if not data:
                    with self._lock:
                        if gen == self._gen:
                            self._eof = True
                    return
                sound = self._pg.mixer.Sound(buffer=data)
                while True:
                    with self._lock:
                        if gen != self._gen:
                            return
                        handed = False
                        if not self._channel.get_busy():
                            self._channel.play(sound)
                            self._channel.set_volume(self._volume / 100)    # play() sets it back to full
                            handed = True
                        elif self._channel.get_queue() is None:
                            self._channel.queue(sound)
                            handed = True
                        if handed:
                            if self._began is None:
                                self._began = time.monotonic()
                            break
                    time.sleep(0.02)
        except Exception:  # noqa: BLE001 - the song just ends
            log.exception("music decoder stopped")
            with self._lock:
                if gen == self._gen:
                    self._eof = True

    @staticmethod
    def _read(stream):
        out = b""
        while len(out) < PIECE:
            try:
                block = stream.read(PIECE - len(out))
            except (OSError, ValueError):
                break
            if not block:
                break
            out += block
        return out[:len(out) - len(out) % FRAME]

    # ------------------------------------------------------------------ the backend API
    def load(self, path: str) -> bool:
        with self._lock:
            self.close()
            length = probe_length_ms(path) if os.path.isfile(path) else 0
            if not length:
                self.last_error = "no sound in this file"
                return False
            self._path, self._length, self._base = path, length, 0
            self.last_error = ""
            return True

    def play(self):
        with self._lock:
            if self._path is None:
                return
            if self._paused_at is not None and self._proc is not None:
                self.resume()
                return
            at = self.position_ms()
            if at >= self._length:
                at = 0
            if self._start_decoder(at):
                self._playing = True

    def pause(self):
        with self._lock:
            if self._path is not None and self._paused_at is None:
                self._channel.pause()
                self._paused_at = time.monotonic()
                self._playing = False

    def resume(self):
        with self._lock:
            if self._path is None:
                return
            if self._proc is None:
                self.play()
                return
            if self._paused_at is not None:
                self._paused_for += time.monotonic() - self._paused_at
                self._paused_at = None
            self._channel.unpause()
            self._channel.set_volume(self._volume / 100)
            self._playing = True

    def stop(self):
        with self._lock:
            self._playing = False
            self._stop_decoder()
            self._base, self._began, self._paused_at, self._paused_for, self._eof = 0, None, None, 0.0, False

    def close(self):
        with self._lock:
            self.stop()
            self._path, self._length = None, 0

    def position_ms(self) -> int:
        with self._lock:
            if self._path is None:
                return 0
            if self._began is None:
                return min(self._base, self._length)
            now = self._paused_at if self._paused_at is not None else time.monotonic()
            return min(self._length, self._base + int((now - self._began - self._paused_for) * 1000))

    def length_ms(self) -> int:
        with self._lock:
            return self._length

    def seek(self, ms: int):
        """Jump to ms (keeps playing if it was playing)."""
        with self._lock:
            if self._path is None:
                return
            ms = max(0, min(int(ms), self._length))
            if self._playing:
                self._start_decoder(ms)
            else:
                self._stop_decoder()
                self._base, self._began, self._paused_at, self._paused_for, self._eof = ms, None, None, 0.0, False

    def set_volume(self, percent: int):
        with self._lock:
            self._volume = max(0, min(100, int(percent)))
            self._channel.set_volume(self._volume / 100)

    def is_playing(self) -> bool:
        with self._lock:
            return self._playing and self._proc is not None and not self.finished()

    def finished(self) -> bool:
        """True once a track that was playing has run to its end."""
        with self._lock:
            if not (self._path and self._playing and self._eof):
                return False
            return not self._channel.get_busy() and self._channel.get_queue() is None
