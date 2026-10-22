"""🌈 The music visualizer's sound analysis: a song is decoded once in the background (ffmpeg, mono, 22 kHz)
and turned into a spectrum for every 1/30 s — 64 bands from deep bass to treble, on a log scale like the ear
hears them — plus the loudness of each moment (for the "beat" glow). The window then only looks up the
frame of the playing position, so the picture follows any player (MCI or the equalizer's) exactly.

Colour themes for the pictures are here too (PALETTES)."""
import subprocess
import threading
from collections import OrderedDict

from .logs import log
from .utils import find_ffmpeg, subprocess_flags

RATE = 22050
FPS = 30
HOP = RATE // FPS                 # samples between two frames
WINDOW = 2048
BANDS = 64
LOW_HZ, HIGH_HZ = 40, 11000
KEEP = 4                          # analysed songs kept in memory (the one playing, the ones before / after)

PALETTES = {
    "Mor": ["#3B1E5A", "#7B3FA0", "#B35EC9", "#E58BD9", "#FFD1F3"],
    "Gün batımı": ["#2B1055", "#A4206A", "#F2545B", "#F9A03F", "#FFE66D"],
    "Okyanus": ["#03256C", "#1768AC", "#06BEE1", "#5EF2D5", "#E0FFFB"],
    "Neon": ["#0B0F2B", "#00F5D4", "#00BBF9", "#F15BB5", "#FEE440"],
}


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def blend(palette, t) -> str:
    """The colour at t (0..1) along a palette."""
    stops = [_hex(c) for c in palette]
    t = max(0.0, min(1.0, float(t))) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    f = t - i
    a, b = stops[i], stops[i + 1]
    return "#%02x%02x%02x" % tuple(int(a[k] + (b[k] - a[k]) * f) for k in range(3))


def band_edges():
    """The FFT bins where each of the BANDS starts (log spaced), at least one bin each."""
    import numpy as np
    freqs = np.geomspace(LOW_HZ, HIGH_HZ, BANDS + 1)
    bins = np.clip((freqs / (RATE / 2) * (WINDOW // 2)).astype(int), 1, WINDOW // 2)
    for i in range(1, len(bins)):
        bins[i] = max(bins[i], bins[i - 1] + 1)
    return np.minimum(bins, WINDOW // 2)


def analyse_samples(samples):
    """(spectrum frames: n × BANDS uint8, loudness: n uint8) of mono float samples at RATE."""
    import numpy as np
    samples = np.asarray(samples, dtype=np.float32)
    if len(samples) < WINDOW:
        samples = np.pad(samples, (0, WINDOW - len(samples)))
    n = 1 + (len(samples) - WINDOW) // HOP
    window = np.hanning(WINDOW).astype(np.float32)
    edges = band_edges()
    out = np.zeros((n, BANDS), dtype=np.float32)
    level = np.zeros(n, dtype=np.float32)
    step = 512                                          # frames at a time: little memory, numpy speed
    for start in range(0, n, step):
        idx = np.arange(start, min(n, start + step))[:, None] * HOP + np.arange(WINDOW)[None, :]
        chunk = samples[idx]
        level[start:start + len(chunk)] = np.sqrt(np.mean(chunk * chunk, axis=1))
        mag = np.abs(np.fft.rfft(chunk * window, axis=1))
        sums = np.add.reduceat(mag, edges[:-1], axis=1) / np.diff(np.append(edges, edges[-1] + 1))[:BANDS]
        out[start:start + len(chunk)] = 20 * np.log10(sums + 1e-6)
    top = np.percentile(out, 99.5) if out.size else 0
    out = np.clip((out - (top - 60)) / 60, 0, 1)        # 60 dB of range under the loud parts
    peak = np.percentile(level, 99) if level.size else 1
    level = np.clip(level / (peak or 1), 0, 1)
    return (out * 255).astype(np.uint8), (level * 255).astype(np.uint8)


def decode(path, ffmpeg=None):
    """The song as mono float samples at RATE (numpy array)."""
    import numpy as np
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg")
    r = subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-i", path, "-vn", "-ac", "1", "-ar", str(RATE),
                        "-f", "f32le", "pipe:1"], capture_output=True, timeout=600, **subprocess_flags())
    if r.returncode != 0 and not r.stdout:
        raise OSError(r.stderr.decode("utf-8", "replace")[-300:])
    return np.frombuffer(r.stdout, dtype=np.float32)


class Analyzer:
    """want(path) starts the analysis in the background (once per song); get(path) gives
    (frames, loudness) when it is ready, else None."""

    def __init__(self, decode_fn=None):
        self._decode = decode_fn or decode
        self._done = OrderedDict()
        self._busy = set()
        self._lock = threading.Lock()

    def get(self, path):
        with self._lock:
            got = self._done.get(path)
            if got is not None:
                self._done.move_to_end(path)
            return got

    def busy(self, path) -> bool:
        with self._lock:
            return path in self._busy

    def want(self, path):
        if not path:
            return
        with self._lock:
            if path in self._done or path in self._busy:
                return
            self._busy.add(path)
        threading.Thread(target=self._work, args=(path,), daemon=True, name="visualizer").start()

    def _work(self, path):
        try:
            result = analyse_samples(self._decode(path))
        except Exception as e:  # noqa: BLE001 - the picture just stays quiet
            log.info("visualizer could not read %s: %s", path, e)
            result = None
        with self._lock:
            self._busy.discard(path)
            if result is not None:
                self._done[path] = result
                while len(self._done) > KEEP:
                    self._done.popitem(last=False)


def frame_at(result, ms):
    """(bands 0..1 list, loudness 0..1) at this moment of the song."""
    frames, level = result
    if not len(frames):
        return [0.0] * BANDS, 0.0
    i = max(0, min(len(frames) - 1, int(ms * FPS / 1000)))
    return [v / 255 for v in frames[i]], level[i] / 255
