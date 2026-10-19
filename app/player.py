"""Music playback: the Windows MCI backend (sdl_player.SdlBackend on macOS / Linux) and the queue /
controller on top of it.

Nothing here knows about downloads or windows. `Controller` drives any backend that has the
methods of `MciBackend`, so the tests use a fake one and the real one is tested on its own."""
import ctypes
import os
import random
import sys
import threading
import time

try:
    from ctypes import wintypes
except (ImportError, ValueError):  # not Windows
    wintypes = None

from .logs import log

AUDIO_EXTENSIONS = (".mp3", ".wav", ".wma", ".m4a", ".aac", ".mp4")
REPEAT_MODES = ("Kapalı", "Liste", "Tek")      # off / whole list / one track
_ALIAS = "hizli_music"


# what a finished download must be to go into a playlist by itself (a .mp4 is more likely a video)
MUSIC_EXTENSIONS = (".mp3", ".wav", ".wma", ".m4a", ".aac")


def is_audio(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in AUDIO_EXTENSIONS


def is_music(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in MUSIC_EXTENSIONS


def artist_and_title(track: dict):
    """(artist, title) to show. A title written 'Artist - Song' (usual for YouTube music) is split,
    unless the tags name another artist that the title also mentions."""
    title = track.get("tag_title") or track["title"]
    artist = track.get("artist") or ""
    for sep in (" - ", " – ", " — "):
        if sep in title:
            left, right = (p.strip() for p in title.split(sep, 1))
            if left and right and (not artist or artist.casefold() in left.casefold()
                                   or artist.casefold() not in title.casefold()):
                return left, right
            break
    return artist, title


def track_label(track: dict) -> str:
    """What to show for a track: 'Artist – Title' from its tags, else the file name."""
    artist, title = artist_and_title(track)
    return f"{artist} – {title}" if artist else title


def new_backend(alias=_ALIAS):
    """The player of this system: Windows' MCI, elsewhere ffmpeg + SDL. Raises OSError / AttributeError
    when there is none."""
    if sys.platform.startswith("win"):
        return MciBackend(alias)
    from .sdl_player import SdlBackend
    return SdlBackend(alias)


def needs_playable_copies() -> bool:
    """Only MCI refuses files that are fine (see playable.py); ffmpeg reads them all."""
    return sys.platform.startswith("win")


class MciBackend:
    """Plays one file at a time with winmm's MCI (no extra package; mp3, wav, wma, aac / m4a)."""

    def __init__(self, alias=_ALIAS):
        self.alias = alias           # each player has its own MCI name: two can sound at once (cross-fade, preview)
        self._lock = threading.RLock()
        self._open = False
        self._playing = False        # play was started and the user did not stop / pause it
        self._volume = 80
        self.last_error = ""
        winmm = ctypes.WinDLL("winmm")
        self._send = winmm.mciSendStringW
        self._send.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HANDLE]
        self._send.restype = wintypes.DWORD
        self._error = winmm.mciGetErrorStringW
        self._error.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.UINT]

    @staticmethod
    def available() -> bool:
        try:
            ctypes.WinDLL("winmm").mciSendStringW
            return True
        except (OSError, AttributeError):
            return False

    # ------------------------------------------------------------------ low level
    def _cmd(self, text, want_text=False):
        """Run an MCI command. Returns the answer text, or None when MCI refused (see last_error)."""
        buf = ctypes.create_unicode_buffer(256)
        code = self._send(text, buf, 255, None)
        if code:
            msg = ctypes.create_unicode_buffer(256)
            self._error(code, msg, 255)
            self.last_error = msg.value
            return None
        self.last_error = ""
        return buf.value if want_text else ""

    def _int(self, what):
        answer = self._cmd(f"status {self.alias} {what}", True)
        try:
            return int(answer)
        except (TypeError, ValueError):
            return 0

    # ------------------------------------------------------------------ the backend API
    def load(self, path: str) -> bool:
        with self._lock:
            self.close()
            kind = "waveaudio" if path.lower().endswith(".wav") else "mpegvideo"
            if self._cmd(f'open "{path}" type {kind} alias {self.alias}') is None:
                return False
            self._open = True
            self._cmd(f"set {self.alias} time format milliseconds")
            self.set_volume(self._volume)
            return True

    def play(self):
        with self._lock:
            if self._open and self._cmd(f"play {self.alias}") is not None:
                self._playing = True

    def pause(self):
        with self._lock:
            if self._open:
                self._cmd(f"pause {self.alias}")
                self._playing = False

    def resume(self):
        with self._lock:
            if self._open and self._cmd(f"resume {self.alias}") is not None:
                self._playing = True

    def stop(self):
        with self._lock:
            self._playing = False
            if self._open:
                self._cmd(f"stop {self.alias}")
                self._cmd(f"seek {self.alias} to start")

    def close(self):
        with self._lock:
            self._playing = False
            if self._open:
                self._cmd(f"close {self.alias}")
                self._open = False

    def position_ms(self) -> int:
        with self._lock:
            return self._int("position") if self._open else 0

    def length_ms(self) -> int:
        with self._lock:
            return self._int("length") if self._open else 0

    def seek(self, ms: int):
        """Jump to ms (keeps playing if it was playing)."""
        with self._lock:
            if not self._open:
                return
            was_playing = self._playing
            self._cmd(f"seek {self.alias} to {max(0, int(ms))}")
            if was_playing:
                self._cmd(f"play {self.alias}")

    def set_volume(self, percent: int):
        with self._lock:
            self._volume = max(0, min(100, int(percent)))
            if self._open:
                self._cmd(f"setaudio {self.alias} volume to {self._volume * 10}")

    def is_playing(self) -> bool:
        with self._lock:
            return self._open and self._cmd(f"status {self.alias} mode", True) == "playing"

    def finished(self) -> bool:
        """True once a track that was playing has run to its end."""
        with self._lock:
            if not (self._open and self._playing):
                return False
            if self._cmd(f"status {self.alias} mode", True) != "stopped":
                return False
            return True


class Controller:
    """The play queue: which track is current, next / previous, shuffle and repeat, the "play next"
    line (songs from any list that come before the rest of the list) and cross-fading between songs.

    Cross-fade needs a second backend (`spare`): near the end of a song the next one starts on it, the
    volumes slide over `fade_ms`, then the two swap roles.

    A file the backend cannot open is handed to `prepare` (a playable.Preparer): state is "preparing"
    until its playable copy is made, then that copy plays."""

    def __init__(self, backend, rng=None, spare=None, clock=time.monotonic, prepare=None):
        self.backend = backend
        self.spare = spare            # second player for cross-fades (None: no cross-fade)
        self.prepare = prepare        # makes playable copies (None: a file MCI refuses is skipped)
        self.tracks = []              # list of {"path": ..., "title": ...}
        self.index = -1               # position in self.tracks, -1 = nothing loaded
        self.state = "stopped"        # stopped / playing / paused / preparing
        self.shuffle = False
        self.repeat = "Kapalı"
        self.error = ""               # set when the last track could not be played
        self.queue = []               # "Sıradaki olarak çal" / "Sıraya ekle": tracks played before the list goes on
        self.extra = None             # the queued track that plays now (it is not in self.tracks)
        self.volume = 80
        self.fade_ms = 0              # 0: no cross-fade
        self._fade = None             # (start, old backend) while two songs sound together
        self._clock = clock
        self._rng = rng or random.Random()
        self._history = []            # indexes already played (for "previous" in shuffle mode)
        self._played = set()          # indexes played in this shuffle round

    # ------------------------------------------------------------------ volume
    def set_volume(self, percent):
        self.volume = max(0, min(100, int(percent)))
        if self._fade is None:
            self.backend.set_volume(self.volume)

    # ------------------------------------------------------------------ queue
    def set_tracks(self, tracks, keep_current=False):
        """Replace the list. With keep_current the playing track stays current if it is still in it."""
        current = self.current_path() if keep_current and self.extra is None else None
        self.tracks = list(tracks)
        self._history, self._played = [], set()
        if self.extra is not None and keep_current:
            self.index = min(self.index, len(self.tracks) - 1)
        elif current and current in [t["path"] for t in self.tracks]:
            self.index = [t["path"] for t in self.tracks].index(current)
            self._played.add(self.index)
        else:
            if self.state != "stopped" or self.index >= 0:
                self.stop()
            self.index = -1

    def play_next(self, tracks):
        """'Sıradaki olarak çal': these come right after the song that plays now."""
        self.queue[0:0] = [dict(t) for t in tracks]

    def add_to_queue(self, tracks):
        """'Sıraya ekle': these come after what is already lined up."""
        self.queue += [dict(t) for t in tracks]

    def current_path(self):
        t = self.current_track()
        return t["path"] if t else None

    def current_track(self):
        if self.extra is not None:
            return self.extra
        return self.tracks[self.index] if 0 <= self.index < len(self.tracks) else None

    def current_title(self):
        t = self.current_track()
        return track_label(t) if t else ""

    def _pick_next(self, automatic):
        n = len(self.tracks)
        if n == 0:
            return None
        if automatic and self.repeat == "Tek" and self.index >= 0 and self.extra is None:
            return self.index
        if self.shuffle:
            left = [i for i in range(n) if i not in self._played and i != self.index]
            if not left:
                if self.repeat == "Liste" or not automatic:
                    self._played = set()
                    left = [i for i in range(n) if i != self.index] or [self.index if self.index >= 0 else 0]
                else:
                    return None
            return self._rng.choice(left)
        nxt = self.index + 1
        if nxt >= n:
            return 0 if (self.repeat == "Liste" or not automatic) else None
        return nxt

    def _next_target(self, automatic):
        """("queue", track) / ("list", index) / None: what plays after the current song."""
        if automatic and self.repeat == "Tek" and self.extra is not None:
            return ("queue", self.extra)
        while self.queue:
            track = self.queue[0]
            if os.path.isfile(track["path"]):
                return ("queue", track)
            self.queue.pop(0)                       # a lined-up file that was deleted meanwhile
        i = self._pick_next(automatic)
        return None if i is None else ("list", i)

    # ------------------------------------------------------------------ transport
    def _load(self, backend, path):
        """Open path (or the playable copy made of it): True, False, or "wait" while a copy is made."""
        if not os.path.isfile(path):
            return False
        copy = self.prepare.ready(path) if self.prepare is not None else None
        if copy and backend.load(copy):
            return True
        if backend.load(path):
            return True
        if self.prepare is None or copy or self.prepare.failed(path):
            return False
        self.prepare.request(path)
        return "wait"

    def _start(self, backend, path):
        opened = self._load(backend, path)
        if opened is True:
            backend.set_volume(self.volume)
            backend.play()
        return opened

    def play_index(self, i) -> bool:
        """Start track i. If it cannot be opened, the next ones are tried (at most one round)."""
        self._end_fade()
        n = len(self.tracks)
        skipped = None
        for step in range(n):
            j = (i + step) % n
            path = self.tracks[j]["path"]
            started = self._start(self.backend, path)
            if started:
                if self.index >= 0 and self.index != j and self.extra is None:
                    self._history.append(self.index)
                self.extra = None
                self.index = j
                self._played.add(j)
                self.state = "playing" if started is True else "preparing"
                self.error = f"Çalamadım, sıradakine geçtim: {skipped}" if skipped else ""
                return True
            skipped = skipped or track_label(self.tracks[j])
            self.error = f"Çalamadım: {track_label(self.tracks[j])}"
            log.info("cannot play %s", path)
        self.backend.close()
        self.state = "stopped"
        return False

    def play_queued(self, track) -> bool:
        self._end_fade()
        if self.queue and self.queue[0] is track:
            self.queue.pop(0)
        started = self._start(self.backend, track["path"])
        if started:
            self.extra = track
            self.state = "playing" if started is True else "preparing"
            self.error = ""
            return True
        self.error = f"Çalamadım: {track_label(track)}"
        log.info("cannot play %s", track["path"])
        return False

    def toggle(self):
        """Play / pause. With nothing loaded, start at the first track."""
        if self.state == "preparing":                 # nothing sounds yet: "pause" means "never mind"
            self.stop()
        elif self.state == "playing":
            self._end_fade()
            self.backend.pause()
            self.state = "paused"
        elif self.state == "paused":
            self.backend.resume()
            self.state = "playing"
        elif self.tracks:
            self.play_index(self.index if self.index >= 0 else 0)

    def stop(self):
        self._end_fade()
        self.backend.stop()
        self.backend.close()
        self.extra = None
        self.state = "stopped"

    def next(self, automatic=False) -> bool:
        target = self._next_target(automatic)
        if target is None:
            self.stop()
            return False
        kind, what = target
        if kind == "queue":
            return self.play_queued(what) or self.next(automatic)
        return self.play_index(what)

    def previous(self, position_ms=0):
        """After the first 3 seconds 'previous' restarts the track, as players usually do."""
        self._end_fade()
        if self.state != "stopped" and position_ms > 3000:
            self.backend.seek(0)
            return True
        if self.extra is not None:                    # back from a lined-up song: to where the list was
            return self.play_index(self.index if self.index >= 0 else 0)
        if self.shuffle and self._history:
            left = self.index
            ok = self.play_index(self._history.pop())
            if self._history and self._history[-1] == left:   # going back must not make a loop
                self._history.pop()
            return ok
        if not self.tracks:
            return False
        i = self.index - 1 if self.index > 0 else len(self.tracks) - 1
        return self.play_index(i)

    def seek_fraction(self, fraction):
        self._end_fade()
        length = self.backend.length_ms()
        if self.state != "stopped" and length > 0:
            self.backend.seek(int(length * max(0.0, min(1.0, fraction))))

    # ------------------------------------------------------------------ cross-fade
    @property
    def fading(self) -> bool:
        return self._fade is not None

    def _maybe_start_fade(self):
        if not (self.fade_ms and self.spare is not None and self._fade is None and self.state == "playing"):
            return False
        length = self.backend.length_ms()
        if length < self.fade_ms * 3:                 # a very short song is not faded
            return False
        if length - self.backend.position_ms() > self.fade_ms:
            return False
        target = self._next_target(True)
        if target is None:
            return False
        kind, what = target
        track = what if kind == "queue" else self.tracks[what]
        if self._load(self.spare, track["path"]) is not True:     # "wait": the copy is made meanwhile
            return False
        self.spare.set_volume(0)
        self.spare.play()
        old = self.backend
        self.backend, self.spare = self.spare, old      # the new song is "the" song from now on
        if kind == "queue":
            if self.queue and self.queue[0] is what:
                self.queue.pop(0)
            self.extra = what
        else:
            if self.index >= 0 and self.index != what and self.extra is None:
                self._history.append(self.index)
            self.extra = None
            self.index = what
            self._played.add(what)
        self._fade = (self._clock(), old)
        return True

    def _step_fade(self):
        start, old = self._fade
        part = min(1.0, (self._clock() - start) * 1000 / max(1, self.fade_ms))
        self.backend.set_volume(int(self.volume * part))
        old.set_volume(int(self.volume * (1 - part)))
        if part >= 1.0 or old.finished():
            self._end_fade()

    def _end_fade(self):
        """Finish a cross-fade at once: the old song goes, the new one is at full volume."""
        if self._fade is None:
            return
        _, old = self._fade
        self._fade = None
        old.stop()
        old.close()
        self.backend.set_volume(self.volume)

    def tick(self):
        """Called a few times a second: moves on when the track has ended (or fades into the next)."""
        if self.state == "preparing":
            self._check_prepared()
            return
        if self.state != "playing":
            return
        if self._fade is not None:
            self._step_fade()
            return
        if self._maybe_start_fade():
            return
        if self.backend.finished():
            self.next(automatic=True)

    def _check_prepared(self):
        """While "preparing": play the copy once it is there, or go on to the next song if none comes."""
        track = self.current_track()
        if track is None:
            self.stop()
            return
        path = track["path"]
        copy = self.prepare.ready(path)
        if copy and self.backend.load(copy):
            self.backend.set_volume(self.volume)
            self.backend.play()
            self.state = "playing"
            return
        if copy or self.prepare.failed(path) or not self.prepare.busy(path):
            self.state = "stopped"
            log.info("cannot play %s", path)
            moved = self.next(automatic=True)
            self.error = (f"Çalamadım, sıradakine geçtim: {track_label(track)}" if moved
                          else f"Çalamadım: {track_label(track)}")

    def position_ms(self):
        return self.backend.position_ms() if self.state not in ("stopped", "preparing") else 0

    def length_ms(self):
        return self.backend.length_ms() if self.state not in ("stopped", "preparing") else 0
