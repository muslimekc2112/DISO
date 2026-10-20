"""🎚 The equalizer of the music player: eight bands, ready-made settings, and the ffmpeg filter they make.

A flat equalizer changes nothing (and on Windows the song keeps playing with MCI, as always). Any other
setting makes the sound go through ffmpeg's "equalizer" filter (see player.SwitchingBackend); some
headroom is taken first and a limiter sits at the end, so boosted bands do not crackle."""

BANDS = [60, 150, 400, 1000, 2400, 6000, 10000, 15000]        # Hz, the middle of each band
LABELS = ["60", "150", "400", "1K", "2.4K", "6K", "10K", "15K"]
LIMIT = 12                                                     # dB, up and down
FLAT = "Düz"
CUSTOM = "Özel"
PRESETS = {
    FLAT: [0, 0, 0, 0, 0, 0, 0, 0],
    "Bas güçlü": [7, 5, 3, 0, 0, 0, 0, 0],
    "Tiz güçlü": [0, 0, 0, 0, 2, 4, 6, 7],
    "Vokal": [-3, -2, 0, 3, 5, 4, 1, -1],
    "Pop": [-1, 2, 4, 4, 2, 0, -1, -1],
    "Rock": [5, 3, -1, -2, 1, 3, 5, 5],
    "Elektronik": [6, 4, 0, -2, 1, 2, 4, 5],
    "Hip-hop": [6, 5, 2, 0, -1, 1, 2, 3],
    "Klasik müzik": [0, 0, 0, 0, -1, -2, -3, -4],
    "Akustik": [3, 2, 1, 1, 2, 3, 3, 2],
    "Gece (kısık bas)": [-6, -4, -2, 0, 0, 0, -1, -2],
}


def clean(gains) -> list:
    """Eight whole dB values within the limits (anything else becomes flat)."""
    try:
        out = [max(-LIMIT, min(LIMIT, int(round(float(g))))) for g in gains]
    except (TypeError, ValueError):
        return list(PRESETS[FLAT])
    return out if len(out) == len(BANDS) else list(PRESETS[FLAT])


def is_flat(gains) -> bool:
    return not any(clean(gains))


def preset_of(gains) -> str:
    """The name of the ready-made setting these gains are, or CUSTOM."""
    gains = clean(gains)
    return next((name for name, values in PRESETS.items() if values == gains), CUSTOM)


def ffmpeg_filter(gains) -> str:
    """The -af text for these gains ("" when flat: nothing to do)."""
    gains = clean(gains)
    if not any(gains):
        return ""
    parts = []
    headroom = max(0, max(gains))
    if headroom:
        parts.append(f"volume=-{headroom * 0.6:.1f}dB")          # room for what is boosted
    parts += [f"equalizer=f={f}:t=o:w=1.2:g={g}" for f, g in zip(BANDS, gains) if g]
    parts.append("alimiter=limit=0.97:level=0")                  # never louder than full scale
    return ",".join(parts)
