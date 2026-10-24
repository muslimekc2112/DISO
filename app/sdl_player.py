"""Music playback on macOS and Linux: ffmpeg turns the file into plain sound, SDL (pygame) plays it.

Windows has MCI (player.MciBackend). Elsewhere nothing like it is built in, so: ffmpeg (which DISO has
anyway) decodes any file it knows into 16-bit stereo at 44.1 kHz, a small thread hands that to an SDL
mixer channel in short pieces, and the channel's own volume and pause do the rest. Every backend has a
channel of its own, so two can sound at once (cross-fade, preview). The methods are MciBackend's.

A new equalizer setting does not stop the sound: a second ffmpeg starts a little ahead with the new
filter, the first one is played up to exactly that moment, and the two are blended over a few ms there.

⏩ The playing speed (and pitch) is an ffmpeg filter too (tempo_filter); positions stay in the song's own
time, so a minute of sound at 2x is two minutes of the song."""
import json
import os
import subprocess
import threading
import time
from array import array

from .logs import log
from .utils import subprocess_flags

RATE, CHANNELS, SAMPLE_BYTES = 44100, 2, 2
FRAME = CHANNELS * SAMPLE_BYTES
PIECE_MS = 200                                   # how much sound is handed over at once
PIECE = RATE * FRAME * PIECE_MS // 1000
MAX_CHANNELS = 16
CHANGE_AHEAD = RATE * 200 // 1000                # frames: a new filter starts this far ahead (ffmpeg needs ~40 ms)
BLEND = RATE * 15 // 1000                        # frames: old and new sound are blended over this, so nothing clicks

MIN_SPEED, MAX_SPEED = 0.25, 4.0
MAX_PITCH = 12                                   # semitones up or down

_mixer_lock = threading.Lock()


def clean_tempo(speed, pitch=0):
    """(speed, pitch) inside what can be played: 0.25x–4x, ±12 semitones."""
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        speed = 1.0
    try:
        pitch = int(round(float(pitch)))
    except (TypeError, ValueError):
        pitch = 0
    speed = 1.0 if speed != speed else max(MIN_SPEED, min(MAX_SPEED, speed))     # (NaN)
    return round(speed, 2), max(-MAX_PITCH, min(MAX_PITCH, pitch))


def _atempo(factor) -> list:
    """atempo steps for any factor (one step only goes from 0.5 to 2 in older ffmpeg builds)."""
    steps = []
    while factor >= 2.0:
        steps.append("atempo=2.0")
        factor /= 2.0
    while factor <= 0.5:
        steps.append("atempo=0.5")
        factor /= 0.5
    if abs(factor - 1.0) > 1e-4:
        steps.append(f"atempo={factor:.6f}")
    return steps


def tempo_filter(speed=1.0, pitch=0) -> str:
    """The ffmpeg filter that plays at `speed` with the voice `pitch` semitones higher / lower ("" = as it is).
    The pitch moves by playing the sound faster (higher) and atempo takes that speed back out."""
    speed, pitch = clean_tempo(speed, pitch)
    if speed == 1.0 and pitch == 0:
        return ""
    steps = []
    factor = speed
    if pitch:
        rise = 2 ** (pitch / 12)
        steps += [f"aresample={RATE}", f"asetrate={RATE * rise:.3f}", f"aresample={RATE}"]
        factor = speed / rise
    return ",".join(steps + _atempo(factor))
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


def _blend(old: bytes, new: bytes) -> bytes:
    """`new` fades in while `old` (the sound it takes the place of) fades out: no click where they meet."""
    size = min(len(old), len(new)) // FRAME * FRAME
    if not size:
        return new
    a, b = array("h", old[:size]), array("h", new[:size])
    frames = size // FRAME
    for i in range(len(b)):
        share = (i // CHANNELS + 1) / (frames + 1)
        b[i] = int(a[i] + (b[i] - a[i]) * share)
    return b.tobytes() + new[size:]


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
        self._filter = ""             # ffmpeg -af (the equalizer); "" = the sound as it is
        self._refilter = False        # the filter changed while playing: the feeding thread changes over
        self._next_proc = None        # the decoder with the new filter, until it takes over
        self._hold = False            # cue(): the first piece waits for go()
        self._speed, self._pitch = 1.0, 0     # ⏩ set_tempo()
        self._run_speed = 1.0         # the speed of the running decoder (its sound per second of the song)
        self._ready = False           # ... and it is there
        self.last_error = ""

    @staticmethod
    def available() -> bool:
        try:
            _pygame()
            return True
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------ the decoder
    def _spawn(self, at_frame, af):
        """An ffmpeg that decodes the song from this frame on through this filter (None: it did not start)."""
        ffmpeg = _tool("ffmpeg")
        if not ffmpeg:
            self.last_error = "ffmpeg not found"
            return None
        args = [ffmpeg, "-nostdin", "-v", "error"]
        if at_frame > 0:
            args += ["-ss", f"{at_frame / RATE:.6f}"]
        args += ["-i", self._path, "-vn"]
        af = ",".join(f for f in (af, tempo_filter(self._speed, self._pitch)) if f)
        if af:
            args += ["-af", af]
        args += ["-f", "s16le", "-acodec", "pcm_s16le", "-ac", str(CHANNELS), "-ar", str(RATE), "pipe:1"]
        try:
            return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, **subprocess_flags())
        except OSError as e:
            self.last_error = str(e)
            return None

    @staticmethod
    def _kill(proc):
        if proc is not None:
            try:
                proc.kill()
                proc.stdout.close()
                proc.wait(2)
            except (OSError, subprocess.SubprocessError, ValueError):
                pass

    def _start_decoder(self, at_ms, hold=False):
        self._stop_decoder()
        at_frame = at_ms * RATE // 1000
        proc = self._spawn(at_frame, self._filter)
        if proc is None:
            return False
        self._proc = proc
        self._gen += 1
        self._base, self._began, self._paused_at, self._paused_for, self._eof = at_ms, None, None, 0.0, False
        self._hold, self._ready = hold, False
        self._run_speed = self._speed
        threading.Thread(target=self._feed, args=(self._gen, proc, at_frame, self._speed), daemon=True,
                         name="sdl-feed").start()
        return True

    def _stop_decoder(self):
        self._gen += 1
        procs = (self._proc, self._next_proc)
        self._proc = self._next_proc = None
        self._refilter = self._hold = False
        for proc in procs:
            self._kill(proc)
        self._channel.stop()

    def _feed(self, gen, proc, at, speed=1.0):
        """Hands the decoded sound to the channel, one piece while the one before it sounds. `at` is the frame
        of the song the next piece starts with (a piece of sound is `speed` times as much of the song). When the filter changes, a decoder with the new one starts at
        `switch` (a little ahead), this one is read up to exactly there, and the new one goes on from it."""
        nxt = switch = None
        tail = b""                    # the old sound just after `switch`: the new one is blended into it
        try:
            while True:
                with self._lock:
                    if gen != self._gen:
                        return
                    refilter, self._refilter = self._refilter, False
                    af = self._filter
                if refilter:                                   # (again before it took over: the newest wins)
                    self._kill(nxt)
                    switch = at + CHANGE_AHEAD if switch is None else switch
                    nxt = self._spawn(switch, af)
                    with self._lock:
                        if gen != self._gen:
                            self._kill(nxt)
                            return
                        self._next_proc = nxt
                    if nxt is None:
                        switch = None                          # ffmpeg did not start: the old setting plays on
                if switch is not None and at >= switch:
                    tail = self._read(proc.stdout, BLEND * FRAME)
                    with self._lock:
                        if gen != self._gen:
                            return
                        self._proc, self._next_proc = nxt, None
                    self._kill(proc)
                    proc, nxt, switch = nxt, None, None
                    continue
                ahead = PIECE if switch is None else min(PIECE, max(1, int((switch - at) / speed)) * FRAME)
                data = self._read(proc.stdout, ahead)
                if gen != self._gen:
                    return
                if not data:
                    with self._lock:
                        if gen == self._gen:
                            self._eof = True
                            self._next_proc = None
                    self._kill(nxt)
                    return
                if tail:
                    data, tail = _blend(tail, data), b""
                at += len(data) // FRAME * speed
                if not self._hand(gen, data):
                    return
        except Exception:  # noqa: BLE001 - the song just ends
            log.exception("music decoder stopped")
            with self._lock:
                if gen == self._gen:
                    self._eof = True

    def _hand(self, gen, data) -> bool:
        """Gives one piece to the channel as soon as it has room for it (False: this decoder was stopped)."""
        sound = self._pg.mixer.Sound(buffer=data)
        with self._lock:
            if gen == self._gen:
                self._ready = True
        while True:
            with self._lock:
                if gen != self._gen:
                    return False
                handed = False
                if self._hold:
                    pass                                       # cue(): waits for go()
                elif not self._channel.get_busy():
                    self._channel.play(sound)
                    self._channel.set_volume(self._volume / 100)    # play() sets it back to full
                    handed = True
                elif self._channel.get_queue() is None:
                    self._channel.queue(sound)
                    handed = True
                if handed:
                    if self._began is None:
                        self._began = time.monotonic()
                    return True
                holding = self._hold
            time.sleep(0.003 if holding else 0.02)

    @staticmethod
    def _read(stream, size=PIECE):
        out = b""
        while len(out) < size:
            try:
                block = stream.read(size - len(out))
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
            if self._hold:
                self.go()
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
            return min(self._length, self._base + int((now - self._began - self._paused_for) * 1000 * self._run_speed))

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

    def set_filter(self, text: str):
        """The equalizer's ffmpeg filter; a song that plays goes on with it without a gap (see _feed)."""
        with self._lock:
            text = text or ""
            if text == self._filter:
                return
            self._filter = text
            if self._path is None or self._eof:
                return                               # (at the very end: the last pieces just play out)
            if self._hold:
                self._start_decoder(self._base, hold=True)
            elif self._playing and self._proc is not None and self._paused_at is None:
                self._refilter = True                # the feeding thread changes over to a new decoder
            elif self._proc is not None or self._playing:
                self.seek(self.position_ms())        # paused: the decoder starts again there, with the new filter

    def set_tempo(self, speed=1.0, pitch=0):
        """⏩ Play faster / slower (and higher / lower). A playing song goes on from the same moment."""
        with self._lock:
            speed, pitch = clean_tempo(speed, pitch)
            if (speed, pitch) == (self._speed, self._pitch):
                return
            at = self.position_ms()
            self._speed, self._pitch = speed, pitch
            if self._path is None or self._eof:
                return
            if self._hold:
                self._start_decoder(self._base, hold=True)
            elif self._playing and self._proc is not None and self._paused_at is None:
                self._start_decoder(at)
            elif self._proc is not None or self._playing:
                self.seek(at)

    def cue(self, ms: int) -> bool:
        """Get ready to play from ms: the decoder starts, and its first piece waits for go(). So this one can
        take over from another player at exactly the right moment (see player.SwitchingBackend)."""
        with self._lock:
            if self._path is None:
                return False
            return self._start_decoder(max(0, min(int(ms), self._length)), hold=True)

    def ready(self) -> bool:
        """After cue(): the first piece is decoded (or the song is over there), go() sounds at once."""
        with self._lock:
            return self._ready or self._eof or self._proc is None

    def go(self):
        with self._lock:
            if self._hold:
                self._hold = False
                self._playing = True

    def is_playing(self) -> bool:
        with self._lock:
            return self._playing and self._proc is not None and not self.finished()

    def finished(self) -> bool:
        """True once a track that was playing has run to its end."""
        with self._lock:
            if not (self._path and self._playing and self._eof):
                return False
            return not self._channel.get_busy() and self._channel.get_queue() is None
