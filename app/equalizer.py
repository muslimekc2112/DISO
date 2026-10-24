"""🎚 The equalizer of the music player: eight bands, ready-made settings, and the ffmpeg filter they make.

A flat equalizer changes nothing (and on Windows the song keeps playing with MCI, as always). Any other
setting makes the sound go through ffmpeg's "equalizer" filter (see player.SwitchingBackend); some
headroom is taken first and a limiter sits at the end, so boosted bands do not crackle."""

BANDS = [60, 150, 400, 1000, 2400, 6000, 10000, 15000]        # Hz, the middle of each band
LABELS = ["60 Hz", "150 Hz", "400 Hz", "1 kHz", "2.4 kHz", "6 kHz", "10 kHz", "15 kHz"]
LIMIT = 12                                                     # dB, up and down
# The simple view: three plainly named controls, each one moves a group of the bands above (in "Gelişmiş"
# the eight bands themselves). Its value is the middle of its bands; moving it moves them all alike.
SIMPLE = [("Bas", "Davul, bas gitar: kalın sesler", (0, 1)),
          ("Orta", "Ses ve çalgılar: şarkının gövdesi", (2, 3, 4)),
          ("Tiz", "Zil, nefes, parlaklık: ince sesler", (5, 6, 7))]
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


def simple_values(gains) -> list:
    """What the simple controls show for these gains: the middle (average) of each one's bands."""
    gains = clean(gains)
    return [int(round(sum(gains[i] for i in bands) / len(bands))) for _, _, bands in SIMPLE]


def set_simple(gains, which, value) -> list:
    """The gains with simple control `which` at `value`: its bands all move by the same amount, so the shape
    an expert gave them stays (as far as the limits allow)."""
    gains = clean(gains)
    bands = SIMPLE[which][2]
    shift = float(value) - sum(gains[i] for i in bands) / len(bands)
    return clean([g + shift if i in bands else g for i, g in enumerate(gains)])


# 🎤 karaoke: the voice of a song is usually in the middle (the same on both sides); taking the middle away
# takes it away. The bass is in the middle too, so below KARAOKE_KEEP Hz the sound stays as it is.
KARAOKE_KEEP = 160
KARAOKE = (f"asplit=2[kl][kh];[kl]lowpass=f={KARAOKE_KEEP}[klo];[kh]highpass=f={KARAOKE_KEEP},stereotools=mlev=0.06"
           f"[khi];[klo][khi]amix=inputs=2:normalize=0")


def sound_filter(gains, karaoke=False) -> str:
    """The whole -af text of the player: the karaoke (voice away) first, then the equalizer ("" = nothing)."""
    return ",".join(f for f in (KARAOKE if karaoke else "", ffmpeg_filter(gains)) if f)


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
