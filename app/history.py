"""Everything that was downloaded, kept even after it leaves the download list (%LOCALAPPDATA%\\DISO\\history.json),
and the numbers made from it: how many, how much, how fast, from where."""
import os
import threading
import time
from urllib.parse import urlsplit

from . import safefile
from .utils import app_data_dir

MAX_ENTRIES = 3000
KIND_NAMES = {"video": "Video", "audio": "MP3", "file": "Dosya"}


def site_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    for prefix in ("www.", "m.", "music."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return {"youtu.be": "youtube.com"}.get(host, host)


def entry_for(item, now=None) -> dict:
    """What is remembered of a finished download."""
    now = time.time() if now is None else now
    path = item.final_path or ""
    try:
        size = os.path.getsize(path) if path else 0
    except OSError:
        size = 0
    size = size or int(item.total or item.done or 0)
    started = getattr(item, "started", 0) or 0
    seconds = max(0.0, now - started) if started else 0.0
    return {"title": item.display_name, "url": item.url, "kind": item.kind, "path": path, "size": size,
            "finished": now, "seconds": round(seconds, 1), "site": site_of(item.url)}


def _clean(e):
    if not (isinstance(e, dict) and isinstance(e.get("title"), str) and isinstance(e.get("finished"), (int, float))):
        return None
    out = {"title": e["title"], "finished": float(e["finished"])}
    for key in ("url", "kind", "path", "site"):
        out[key] = e[key] if isinstance(e.get(key), str) else ""
    for key in ("size", "seconds"):
        out[key] = e[key] if isinstance(e.get(key), (int, float)) and not isinstance(e.get(key), bool) and e[key] > 0 else 0
    return out


class History:
    def __init__(self, path=None):
        self.path = path or os.path.join(app_data_dir(), "history.json")
        self._lock = threading.Lock()
        self.entries = []                                   # newest first
        try:
            data = safefile.read_json(self.path)                  # a broken file comes back from its copy
            self.entries = [e for e in map(_clean, data.get("entries", [])) if e]
        except Exception:  # noqa: BLE001 - no history yet, or a broken file: start empty
            self.entries = []

    def save(self):
        with self._lock:
            try:
                safefile.write_json(self.path, {"entries": self.entries})
            except OSError:
                pass

    def record(self, items, now=None):
        new = [entry_for(it, now) for it in items]
        if new:
            self.entries = (new[::-1] + self.entries)[:MAX_ENTRIES]
            self.save()
        return new

    def clear(self):
        self.entries = []
        self.save()

    def find(self, text=""):
        words = text.casefold().split()
        if not words:
            return list(self.entries)
        return [e for e in self.entries if all(w in f"{e['title']} {e['site']} {e['url']}".casefold() for w in words)]

    def stats(self, now=None) -> dict:
        now = time.time() if now is None else now
        es = self.entries
        week = [e for e in es if now - e["finished"] <= 7 * 86400]
        timed = [e for e in es if e["seconds"] >= 1 and e["size"] > 0]
        speeds = [e["size"] / e["seconds"] for e in timed]
        sites = {}
        for e in es:
            if e["site"]:
                sites[e["site"]] = sites.get(e["site"], 0) + 1
        kinds = {}
        for e in es:
            name = KIND_NAMES.get(e["kind"], "Dosya")
            kinds[name] = kinds.get(name, 0) + 1
        fastest = max(timed, key=lambda e: e["size"] / e["seconds"]) if timed else None
        biggest = max(es, key=lambda e: e["size"]) if es else None
        return {
            "count": len(es), "size": sum(e["size"] for e in es),
            "week_count": len(week), "week_size": sum(e["size"] for e in week),
            "average_speed": (sum(e["size"] for e in timed) / sum(e["seconds"] for e in timed)) if timed else 0,
            "fastest": fastest, "fastest_speed": max(speeds) if speeds else 0,
            "biggest": biggest if biggest and biggest["size"] else None,
            "kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
            "sites": sorted(sites.items(), key=lambda kv: -kv[1])[:5],
        }
