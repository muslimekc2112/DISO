"""Saved playlists (%LOCALAPPDATA%\\DISO/playlists.json): several named lists of music files, each
in the order the user chose, plus the player's own small settings (volume, shuffle, repeat ...)."""
import json
import os
import threading

from .player import REPEAT_MODES, artist_and_title, is_audio, is_music
from .utils import app_data_dir

DEFAULT_NAME = "Çalma listem"
DOWNLOADS_NAME = "İndirilenler"            # where finished music downloads go when they came alone
MAX_NAME = 80
STATE_DEFAULTS = {"last": "", "volume": 80, "shuffle": False, "repeat": "Kapalı",
                  "resume_list": "", "resume_path": "", "resume_ms": 0,     # where the music stopped last time
                  "ask_list": "",                                           # the list picked last for a found song
                  "fade": 0,                                                # s of cross-fade between songs (0: none)
                  "eq": [0] * 8,                                            # 🎛 the equalizer, dB per band (equalizer.py)
                  "searches": []}                                           # the last searches of "Şarkı bul"
FADE_CHOICES = (0, 3, 6, 10)
MAX_SEARCHES = 15
SORT_KEYS = ("title", "artist", "time")


def track_for(path: str) -> dict:
    path = os.path.abspath(path)
    return {"path": path, "title": os.path.splitext(os.path.basename(path))[0]}


def same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def is_gone(path: str) -> bool:
    """The file was deleted. A file on a drive that is not there right now (a USB stick, a network
    share) is not gone: it comes back when the drive does."""
    if os.path.isfile(path):
        return False
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    return not drive or os.path.isdir(drive + os.sep)


def sort_key(track: dict, key: str):
    if key == "time":
        return track.get("duration") or 0
    artist, title = artist_and_title(track)
    if key == "artist":
        return ((artist or "￿").casefold(), title.casefold())
    return title.casefold()


def _clean_track(t):
    """A track from the file: keep what is valid, drop what has the wrong type."""
    if not (isinstance(t, dict) and isinstance(t.get("path"), str) and isinstance(t.get("title"), str)):
        return None
    out = {"path": t["path"], "title": t["title"]}
    for key in ("tag_title", "artist", "album"):
        if isinstance(t.get(key), str) and t[key]:
            out[key] = t[key]
    if isinstance(t.get("duration"), int) and not isinstance(t["duration"], bool) and t["duration"] > 0:
        out["duration"] = t["duration"]
    if t.get("probed") is True:
        out["probed"] = True
    if isinstance(t.get("added"), (int, float)) and not isinstance(t["added"], bool):
        out["added"] = float(t["added"])
    return out


class PlaylistStore:
    def __init__(self, path=None):
        self.path = path or os.path.join(app_data_dir(), "playlists.json")
        self._lock = threading.RLock()
        self.lists = {}                       # name -> [track, ...]   (dict keeps the order)
        self.state = dict(STATE_DEFAULTS)
        self._load()
        if not self.lists:
            self.lists[DEFAULT_NAME] = []
        if self.state["last"] not in self.lists:
            self.state["last"] = next(iter(self.lists))

    # ------------------------------------------------------------------ files
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            lists = data.get("playlists", {})
        except Exception:
            return
        if not isinstance(lists, dict):
            return
        for name, tracks in lists.items():
            if isinstance(name, str) and name.strip() and isinstance(tracks, list):
                self.lists[name] = [t for t in map(_clean_track, tracks) if t]
        saved = data.get("state", {})
        if isinstance(saved, dict):
            for key, default in STATE_DEFAULTS.items():
                if isinstance(saved.get(key), type(default)):
                    self.state[key] = saved[key]
        self.state["volume"] = max(0, min(100, self.state["volume"]))
        self.state["resume_ms"] = max(0, self.state["resume_ms"])
        if self.state["fade"] not in FADE_CHOICES:
            self.state["fade"] = 0
        from .equalizer import clean
        self.state["eq"] = clean(self.state["eq"])
        self.state["searches"] = [q for q in self.state["searches"] if isinstance(q, str) and q.strip()][:MAX_SEARCHES]
        if self.state["repeat"] not in REPEAT_MODES:
            self.state["repeat"] = "Kapalı"

    def save(self):
        with self._lock:
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"playlists": self.lists, "state": self.state}, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            except OSError:
                pass

    # ------------------------------------------------------------------ lists
    def names(self):
        return list(self.lists)

    def tracks(self, name):
        return self.lists.get(name, [])

    def unique_name(self, wanted: str) -> str:
        base = (wanted or "").strip() or "Yeni liste"
        name, n = base, 2
        while name in self.lists:
            name, n = f"{base} ({n})", n + 1
        return name

    def create(self, wanted: str) -> str:
        name = self.unique_name(wanted)
        self.lists[name] = []
        self.save()
        return name

    def rename(self, old: str, wanted: str) -> str:
        """Returns the new name (the old one if the wanted one is empty or the same)."""
        wanted = (wanted or "").strip()
        if old not in self.lists or not wanted or wanted == old:
            return old
        name = self.unique_name(wanted)
        self.lists = {(name if k == old else k): v for k, v in self.lists.items()}   # keeps the order
        if self.state["last"] == old:
            self.state["last"] = name
        self.save()
        return name

    def delete(self, name: str) -> str:
        """Removes a list and returns the name to show next. The last list is emptied, not removed."""
        if name in self.lists:
            if len(self.lists) == 1:
                self.lists[name] = []
            else:
                names = self.names()
                after = names[max(0, names.index(name) - 1)] if names.index(name) > 0 else names[1]
                del self.lists[name]
                if self.state["last"] == name:
                    self.state["last"] = after
        self.save()
        return self.state["last"] if self.state["last"] in self.lists else next(iter(self.lists))

    # ------------------------------------------------------------------ tracks
    def add(self, name: str, paths) -> int:
        """Append the audio files among `paths`. The same file may be in a list twice (the user's call)."""
        added = [track_for(p) for p in paths if is_audio(p) and os.path.isfile(p)]
        self.lists.setdefault(name, []).extend(added)
        if added:
            self.save()
        return len(added)

    def add_folder(self, name: str, folder: str, recursive=True) -> int:
        found = []
        if recursive:
            for root, dirs, files in os.walk(folder):
                dirs.sort()
                found += [os.path.join(root, f) for f in sorted(files, key=str.lower)]
        else:
            found = [os.path.join(folder, f) for f in sorted(os.listdir(folder), key=str.lower)]
        return self.add(name, found)

    def remove(self, name: str, indexes) -> None:
        tracks = self.lists.get(name, [])
        for i in sorted(set(indexes), reverse=True):
            if 0 <= i < len(tracks):
                del tracks[i]
        self.save()

    def clear(self, name: str) -> None:
        if name in self.lists:
            self.lists[name] = []
            self.save()

    def move(self, name: str, indexes, offset: int):
        """Move the selected tracks up (-1) or down (+1) as a block. Returns their new indexes."""
        tracks = self.lists.get(name, [])
        picked = sorted(i for i in set(indexes) if 0 <= i < len(tracks))
        if not picked:
            return []
        order = picked if offset < 0 else picked[::-1]
        moved = set(picked)
        for i in order:
            j = i + offset
            if 0 <= j < len(tracks) and j not in moved:
                tracks[i], tracks[j] = tracks[j], tracks[i]
                moved.discard(i)
                moved.add(j)
        self.save()
        return sorted(moved)

    def sort(self, name: str, key: str, reverse=False) -> None:
        """Put the list in order of title / artist / length (stable: equal ones keep their order)."""
        if name in self.lists and key in SORT_KEYS:
            self.lists[name].sort(key=lambda t: sort_key(t, key), reverse=reverse)
            self.save()

    def shuffle(self, name: str, rng=None) -> list:
        """Put the list in a random order for good; returns the old order (for undo)."""
        import random
        tracks = self.lists.get(name, [])
        before = list(tracks)
        if len(tracks) > 1:
            while tracks == before:                        # a 'shuffle' that changes nothing looks broken
                (rng or random).shuffle(tracks)
            self.save()
        return before

    def set_order(self, name: str, tracks) -> None:
        """Bring back an earlier order (the undo of a shuffle); tracks removed since then stay removed."""
        if name not in self.lists:
            return
        now = {id(t) for t in self.lists[name]}
        kept = [t for t in tracks if id(t) in now]
        self.lists[name] = kept + [t for t in self.lists[name] if id(t) not in {id(k) for k in kept}]
        self.save()

    def missing_paths(self) -> set:
        """The files of every list that were deleted (see is_gone). Safe to call from any thread."""
        with self._lock:
            paths = {t["path"] for tracks in self.lists.values() for t in tracks}
        return {p for p in paths if is_gone(p)}

    def prune(self, paths) -> dict:
        """Take the tracks of these (deleted) files out of every list: {list name: how many}. A file
        that came back in the meantime stays."""
        gone = {os.path.normcase(os.path.abspath(p)) for p in paths if is_gone(p)}
        removed = {}
        if not gone:
            return removed
        with self._lock:
            for name, tracks in self.lists.items():
                keep = [t for t in tracks if os.path.normcase(os.path.abspath(t["path"])) not in gone]
                if len(keep) != len(tracks):
                    removed[name] = len(tracks) - len(keep)
                    self.lists[name] = keep
        if removed:
            self.save()
        return removed

    def copy_to(self, name: str, tracks) -> int:
        """Put these tracks (with what is known about them) into another list; ones already there are skipped."""
        name = self.ensure(name)
        added = 0
        for t in tracks:
            if not self.has_path(name, t["path"]):
                self.lists[name].append({k: v for k, v in t.items() if k != "added"})
                added += 1
        if added:
            self.save()
        return added

    # ------------------------------------------------------------------ tags and downloads
    def apply_tags(self, infos, persist=True) -> bool:
        """infos: {path: {"title", "artist", "album", "duration"}} as read from the files. Every track
        with such a path, in any list, learns it. Returns True when something changed. With
        persist=False the caller writes the file later (answers keep arriving for a while)."""
        wanted = {os.path.normcase(os.path.abspath(p)): info for p, info in infos.items()}
        changed = False
        for tracks in self.lists.values():
            for t in tracks:
                info = wanted.get(os.path.normcase(os.path.abspath(t["path"])))
                if info is None:
                    continue
                new = {"probed": True}
                if info.get("title"):
                    new["tag_title"] = info["title"]
                if info.get("artist"):
                    new["artist"] = info["artist"]
                if info.get("album"):
                    new["album"] = info["album"]
                if info.get("duration"):
                    new["duration"] = int(info["duration"])
                if any(t.get(k) != v for k, v in new.items()):
                    t.update(new)
                    changed = True
        if changed and persist:
            self.save()
        return changed

    def ensure(self, name: str) -> str:
        """The list with exactly this name (made if it does not exist yet)."""
        name = " ".join((name or "").split())[:MAX_NAME].strip() or DOWNLOADS_NAME
        if name not in self.lists:
            self.lists[name] = []
            self.save()
        return name

    def has_path(self, name: str, path: str) -> bool:
        return any(same_file(t["path"], path) for t in self.lists.get(name, []))

    def add_download(self, name: str, path: str, added: float) -> bool:
        """A finished download goes into a list by itself. A file already in the list is not added
        twice. Downloads that finish in a different order than they were started still land in the
        order they were started in (a playlist keeps its order). Returns True if it was added."""
        if not (is_music(path) and os.path.isfile(path)):
            return False
        name = self.ensure(name)
        if self.has_path(name, path):
            return False
        track = track_for(path)
        track["added"] = float(added)
        tracks = self.lists[name]
        for i, t in enumerate(tracks):
            if "added" in t and t["added"] > track["added"]:
                tracks.insert(i, track)
                break
        else:
            tracks.append(track)
        self.save()
        return True

    def total_ms(self, name: str):
        """(sum of the known lengths, True when every track's length is known)."""
        tracks = self.lists.get(name, [])
        known = [t["duration"] for t in tracks if t.get("duration")]
        return sum(known), len(known) == len(tracks)

    def remember_search(self, query: str) -> None:
        """The newest search first; the same one twice is kept once."""
        query = " ".join((query or "").split())
        if not query:
            return
        rest = [q for q in self.state["searches"] if q.casefold() != query.casefold()]
        self.set_state(searches=[query] + rest[:MAX_SEARCHES - 1])

    # ------------------------------------------------------------------ player settings
    def set_state(self, _persist=True, **values):
        """Change player settings. _persist=False keeps them in memory only (the caller saves later,
        e.g. while a slider is being dragged)."""
        changed = False
        for key, value in values.items():
            if key in self.state and self.state[key] != value:
                self.state[key] = value
                changed = True
        if changed and _persist:
            self.save()
