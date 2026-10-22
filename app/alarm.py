"""⏰ The music alarm: at the set time (on the chosen days) a playlist starts, its volume rising slowly from
very low — waking up to music. DISO must be running (it can be in the tray) and the computer awake.

The setting is kept with the player's (PlaylistStore.state["alarm"]); due() is asked every few seconds."""
import datetime

DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
FADES = {"Hemen": 0, "30 saniyede": 30, "1 dakikada": 60, "3 dakikada": 180, "5 dakikada": 300}
START_VOLUME = 5
DEFAULT = {"on": False, "time": "07:30", "days": [0, 1, 2, 3, 4], "list": "", "fade": 60, "shuffle": False,
           "last": ""}


def clean(data) -> dict:
    out = dict(DEFAULT)
    if isinstance(data, dict):
        if isinstance(data.get("on"), bool):
            out["on"] = data["on"]
        if parse_time(data.get("time")):
            out["time"] = data["time"]
        days = data.get("days")
        if isinstance(days, list) and all(isinstance(d, int) and 0 <= d <= 6 for d in days):
            out["days"] = sorted(set(days))
        for key in ("list", "last"):
            if isinstance(data.get(key), str):
                out[key] = data[key]
        if data.get("fade") in FADES.values():
            out["fade"] = data["fade"]
        if isinstance(data.get("shuffle"), bool):
            out["shuffle"] = data["shuffle"]
    return out


def parse_time(text):
    """(hour, minute) of "07:30", or None."""
    try:
        h, m = str(text).split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    return (h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


def due(alarm, now=None) -> bool:
    """Is it time to ring (once per day, within the minute after the set time)?"""
    if not alarm.get("on") or not alarm.get("days"):
        return False
    now = now or datetime.datetime.now()
    hm = parse_time(alarm.get("time"))
    if hm is None or now.weekday() not in alarm["days"]:
        return False
    at = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    return at <= now < at + datetime.timedelta(minutes=2) and alarm.get("last") != now.date().isoformat()


def next_ring(alarm, now=None):
    """The datetime of the next ring (None when off)."""
    if not alarm.get("on") or not alarm.get("days"):
        return None
    now = now or datetime.datetime.now()
    hm = parse_time(alarm.get("time"))
    if hm is None:
        return None
    for ahead in range(8):
        day = (now + datetime.timedelta(days=ahead)).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if day.weekday() in alarm["days"] and day > now and not (ahead == 0 and alarm.get("last") == now.date().isoformat()):
            return day
    return None


def when_text(at, now=None) -> str:
    """"bugün 07:30" / "yarın 07:30" / "Cum 07:30"."""
    if at is None:
        return "kapalı"
    now = now or datetime.datetime.now()
    days = (at.date() - now.date()).days
    word = "bugün" if days == 0 else "yarın" if days == 1 else DAYS[at.weekday()]
    return f"{word} {at.strftime('%H:%M')}"


def volume_at(seconds, fade, target) -> int:
    """The volume this many seconds after ringing: from START_VOLUME up to the target over `fade` seconds."""
    if fade <= 0 or seconds >= fade:
        return int(target)
    return int(START_VOLUME + (target - START_VOLUME) * max(0.0, seconds) / fade)
