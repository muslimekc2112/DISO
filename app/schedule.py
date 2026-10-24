"""
Download scheduler: decides when the queue may run.

The user picks a start time and, optionally, a stop time ("download at night, 02:00-07:00").
Everything here is plain functions on minutes-since-midnight, so it is easy to test.
"""
import re

_HHMM = re.compile(r"^\s*([01]?\d|2[0-3]):([0-5]\d)\s*$")


def parse_hhmm(text):
    """'07:30' -> 450 (minutes since midnight); None if it is not a valid 24-hour time."""
    m = _HHMM.match(text or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def format_hhmm(minutes) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def gate_should_be_open(now: int, start, stop) -> bool:
    """May new downloads start at minute `now`?

    * no start time: always yes
    * start only:    yes from the start time on (until midnight)
    * start < stop:  yes between them, e.g. 02:00-07:00
    * start > stop:  overnight window, e.g. 23:00-06:00
    * start == stop: treated as "no stop time"
    """
    if start is None:
        return True
    if stop is None or stop == start:
        return now >= start
    if start < stop:
        return start <= now < stop
    return now >= start or now < stop


def describe(start, stop) -> str:
    if start is None:
        return ""
    return f"{format_hhmm(start)}–{format_hhmm(stop)}" if stop not in (None, start) else f"{format_hhmm(start)}"
