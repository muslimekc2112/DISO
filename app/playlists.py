"""Saved playlists (%LOCALAPPDATA%\\DISO/playlists.json): several named lists of music files, each
in the order the user chose, plus the player's own small settings (volume, shuffle, repeat ...)."""
import os
import threading

from . import safefile
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
                  "level": False,                                           # 🔊 even volume (loudness.py)
                  "rename_pattern": "{sanatçı} - {şarkı}",                   # ✏ the file name pattern used last
                  "mini_top": True, "mini_place": "",                       # 🗗 the mini player: on top? where?
                  "eq_advanced": False,                                     # 🎛 the eight bands shown
                  "keys": {}, "global_keys": {},                            # ⌨ the user's shortcuts (hotkeys.py)
                  "vis_style": "Çubuklar", "vis_palette": "Mor",            # 🌈 the visualizer's picture and colours
                  "vis_lyrics": True,                                       # 🎤 ... with the lyrics flowing over it
                  "vis_auto_once": False,                                   # 🎨 the cover's colours were made the default
                  "alarm": {},                                              # ⏰ the music alarm (alarm.py)
                  "orders": {}, "own_orders": {},                           # ⇅ how each list is sorted; the user's own order
                  "speed": 1.0, "pitch": 0,                                 # ⏩ playing speed, semitones up / down
                  "ambient": True,                                          # 🎨 the window takes the colours of the cover
                  "searches": []}                                           # the last searches of "Şarkı bul"
FADE_CHOICES = (0, 3, 6, 10)
# ✨ smart lists: made from every other list, filled by themselves (they cannot be changed by hand)
SMART_MOST, SMART_NEW, SMART_NEVER = "⭐ En çok dinlenenler", "🆕 Son eklenenler", "💤 Hiç dinlenmeyenler"
SMART = (SMART_MOST, SMART_NEW, SMART_NEVER)
SMART_SIZE = 50                 # songs in "most played" and "recently added"
PLAYED_AFTER_MS = 30000         # a song counts as listened to after this much (a short one: after half of it)
MAX_SEARCHES = 15
SORT_KEYS = ("title", "artist", "time")
# ⇅ the ways a list can be ordered (ORDER_OWN: the order the user made, kept while another one is shown)
ORDER_OWN, ORDER_NEW_FIRST, ORDER_NEW_LAST, ORDER_AZ, ORDER_ZA, ORDER_POPULAR, ORDER_COLUMN = (
    "own", "new_first", "new_last", "az", "za", "popular", "column")
ORDERS = (ORDER_OWN, ORDER_NEW_FIRST, ORDER_NEW_LAST, ORDER_AZ, ORDER_ZA, ORDER_POPULAR)
_ALPHABET = "0123456789aâbcçdefgğhıiîjklmnoöprsştuüûvwxqyz"
_ALPHA = {ch: i for i, ch in enumerate(_ALPHABET)}


def alpha_key(text: str):
    """A–Z the Turkish way (Ç after C, Ğ after G, I before İ, Ö after O, Ş after S, Ü after U); other
    letters after the known ones, in their own order."""
    text = (text or "").replace("I", "ı").replace("İ", "i").lower().strip()
    return tuple((0, -1) if ch.isspace() else (0, _ALPHA[ch]) if ch in _ALPHA else (1, ord(ch)) for ch in text)


def track_for(path: str) -> dict:
    path = os.path.abspath(path)
    return {"path": path, "title": os.path.splitext(os.path.basename(path))[0]}


def is_smart(name) -> bool:
    return name in SMART


def file_key(path: str) -> str:
    """The same file, however its path is written."""
    return os.path.normcase(os.path.abspath(path))


def _clean_stats(data) -> dict:
    out = {}
    for key, s in (data.items() if isinstance(data, dict) else ()):
        if not (isinstance(key, str) and isinstance(s, dict)):
            continue
        entry = {}
        if isinstance(s.get("plays"), int) and not isinstance(s["plays"], bool) and s["plays"] > 0:
            entry["plays"] = s["plays"]
        for name in ("last", "first"):
            if isinstance(s.get(name), (int, float)) and not isinstance(s[name], bool):
                entry[name] = float(s[name])
        if entry:
            out[key] = entry
    return out


MAX_LOG = 20000           # listenings kept for the 📊 statistics (years of music)


def _clean_log(data) -> list:
    out = []
    for e in data if isinstance(data, list) else ():
        if (isinstance(e, dict) and isinstance(e.get("t"), (int, float)) and not isinstance(e["t"], bool)
                and isinstance(e.get("title"), str)):
            out.append({"t": float(e["t"]), "k": str(e.get("k") or ""), "title": e["title"],
                        "artist": str(e.get("artist") or ""),
                        "ms": int(e["ms"]) if isinstance(e.get("ms"), int) and e["ms"] > 0 else 0})
    return out[-MAX_LOG:]


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
    if t.get("away") is True and not os.path.isfile(t["path"]):     # 👤 came from another computer, not here yet
        out["away"] = True
    if isinstance(t.get("added"), (int, float)) and not isinstance(t["added"], bool):
        out["added"] = float(t["added"])
    return out


class PlaylistStore:
    def __init__(self, path=None):
        self.path = path or os.path.join(app_data_dir(), "playlists.json")
        self._lock = threading.RLock()
        self.lists = {}                       # name -> [track, ...]   (dict keeps the order)
        self.state = dict(STATE_DEFAULTS)
        self.stats = {}                       # file_key -> {"plays": n, "last": time, "first": time added}
        self.log = []                         # every listening: {"t", "k", "title", "artist", "ms"} (📊)
        self._load()
        if not any(not is_smart(n) for n in self.lists):
            self.lists = {DEFAULT_NAME: [], **self.lists}
        self.refresh_smart()
        if self.state["last"] not in self.lists:
            self.state["last"] = next(iter(self.lists))

    # ------------------------------------------------------------------ files
    def _load(self):
        try:
            data = safefile.read_json(self.path)                  # a broken file comes back from its copy
            lists = data.get("playlists", {})
        except Exception:
            return
        if not isinstance(lists, dict):
            return
        for name, tracks in lists.items():
            if isinstance(name, str) and name.strip() and isinstance(tracks, list):
                self.lists[name] = [t for t in map(_clean_track, tracks) if t]
        self.stats = _clean_stats(data.get("stats"))
        self.log = _clean_log(data.get("log"))
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
        self.state["orders"] = {n: m for n, m in self.state["orders"].items()
                                if isinstance(n, str) and m in ORDERS + (ORDER_COLUMN,)}
        self.state["own_orders"] = {n: [k for k in keys if isinstance(k, str)]
                                    for n, keys in self.state["own_orders"].items()
                                    if isinstance(n, str) and isinstance(keys, list)}
        from .sdl_player import clean_tempo
        speed = self.state["speed"] if not isinstance(self.state["speed"], bool) else 1.0
        self.state["speed"], self.state["pitch"] = clean_tempo(speed, self.state["pitch"])

    def save(self):
        with self._lock:
            try:
                safefile.write_json(self.path, {"playlists": self.lists, "state": self.state, "stats": self.stats,
                                                 "log": self.log},
                                    indent=2)
            except OSError:
                pass

    # ------------------------------------------------------------------ lists
    def names(self):
        """The user's lists in their order, then the smart ones."""
        return self.user_names() + [n for n in SMART if n in self.lists]

    def user_names(self):
        """The lists a song can be put into (not the smart ones)."""
        return [n for n in self.lists if not is_smart(n)]

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
        if is_smart(old):
            return old
        """Returns the new name (the old one if the wanted one is empty or the same)."""
        wanted = (wanted or "").strip()
        if old not in self.lists or not wanted or wanted == old:
            return old
        name = self.unique_name(wanted)
        self.lists = {(name if k == old else k): v for k, v in self.lists.items()}   # keeps the order
        if self.state["last"] == old:
            self.state["last"] = name
        for key in ("orders", "own_orders"):
            if old in self.state[key]:
                self.state[key] = {(name if k == old else k): v for k, v in self.state[key].items()}
        self.save()
        return name

    def delete(self, name: str) -> str:
        """Removes a list and returns the name to show next. The last list is emptied, not removed."""
        if is_smart(name):
            return name
        if name in self.lists:
            if len(self.user_names()) == 1:
                self.lists[name] = []
            else:
                names = self.user_names()
                after = names[max(0, names.index(name) - 1)] if names.index(name) > 0 else names[1]
                del self.lists[name]
                if self.state["last"] == name:
                    self.state["last"] = after
            self._forget_order(name)
        self.save()
        return self.state["last"] if self.state["last"] in self.lists else next(iter(self.lists))

    # ------------------------------------------------------------------ tracks
    def add(self, name: str, paths) -> int:
        """Append the audio files among `paths`. The same file may be in a list twice (the user's call)."""
        if is_smart(name):
            return 0
        added = [track_for(p) for p in paths if is_audio(p) and os.path.isfile(p)]
        self.lists.setdefault(name, []).extend(added)
        self._seen(t["path"] for t in added)
        if added:
            self._keep_order(name)
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
        if is_smart(name):
            return
        tracks = self.lists.get(name, [])
        for i in sorted(set(indexes), reverse=True):
            if 0 <= i < len(tracks):
                del tracks[i]
        self.save()

    def clear(self, name: str) -> None:
        if name in self.lists and not is_smart(name):
            self.lists[name] = []
            self.save()

    def move(self, name: str, indexes, offset: int):
        """Move the selected tracks up (-1) or down (+1) as a block. Returns their new indexes."""
        tracks = self.lists.get(name, [])
        picked = sorted(i for i in set(indexes) if 0 <= i < len(tracks))
        if not picked or is_smart(name):
            return picked
        order = picked if offset < 0 else picked[::-1]
        moved = set(picked)
        self._forget_order(name)                           # moved by hand: this is the user's own order now
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
            self._remember_own(name)
            self.lists[name].sort(key=lambda t: sort_key(t, key), reverse=reverse)
            self.state["orders"] = dict(self.state["orders"], **{name: ORDER_COLUMN})
            self.save()

    # ------------------------------------------------------------------ ⇅ ordering a list
    def order_of(self, name) -> str:
        return self.state["orders"].get(name, ORDER_OWN)

    def _remember_own(self, name):
        """Before the list is first put in another order: keep the user's own one, to go back to."""
        if self.order_of(name) == ORDER_OWN:
            self.state["own_orders"] = dict(self.state["own_orders"],
                                            **{name: [file_key(t["path"]) for t in self.lists.get(name, [])]})

    def _forget_order(self, name):
        """The list's order as it is now is the user's own (moved / shuffled by hand, or the list is gone)."""
        if name in self.state["orders"] or name in self.state["own_orders"]:
            self.state["orders"] = {n: m for n, m in self.state["orders"].items() if n != name}
            self.state["own_orders"] = {n: k for n, k in self.state["own_orders"].items() if n != name}

    def _keep_order(self, name):
        """New songs in a sorted list go to their place in that order."""
        mode = self.order_of(name)
        if mode not in (ORDER_OWN, ORDER_COLUMN):
            self._arrange(name, mode)

    def _arrange(self, name, mode):
        tracks = self.lists.get(name, [])
        if mode == ORDER_OWN:
            own = {k: i for i, k in enumerate(self.state["own_orders"].get(name, []))}
            last = len(own)                                 # added since: after the rest, as they came
            tracks.sort(key=lambda t: own.get(file_key(t["path"]), last))
        elif mode in (ORDER_NEW_FIRST, ORDER_NEW_LAST):
            tracks.sort(key=self._added_time, reverse=mode == ORDER_NEW_FIRST)
        elif mode in (ORDER_AZ, ORDER_ZA):
            tracks.sort(key=lambda t: alpha_key(artist_and_title(t)[1] or t["title"]), reverse=mode == ORDER_ZA)
        elif mode == ORDER_POPULAR:
            def popular(t):
                s = self.stats.get(file_key(t["path"]), {})
                return (-s.get("plays", 0), -s.get("last", 0))
            tracks.sort(key=popular)

    def order(self, name: str, mode: str) -> bool:
        """⇅ Show the list in this order: own (the user's), newest first / last, A–Z, Z–A, most played first.
        The user's own order is kept and comes back with ORDER_OWN. False: not possible (a smart list)."""
        if name not in self.lists or is_smart(name) or mode not in ORDERS:
            return False
        if mode != ORDER_OWN:
            self._remember_own(name)
        self._arrange(name, mode)
        if mode == ORDER_OWN:
            self._forget_order(name)
        else:
            self.state["orders"] = dict(self.state["orders"], **{name: mode})
        self.save()
        return True

    def shuffle(self, name: str, rng=None) -> list:
        """Put the list in a random order for good; returns the old order (for undo)."""
        import random
        tracks = self.lists.get(name, [])
        before = list(tracks)
        if len(tracks) > 1:
            self._forget_order(name)
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
        """The files of every list that were deleted (see is_gone). Safe to call from any thread. A song that came
        with the account from another computer ("away": its file is not here yet) is not deleted: it waits."""
        with self._lock:
            paths = {t["path"] for tracks in self.lists.values() for t in tracks if not t.get("away")}
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

    def rename_paths(self, moves) -> int:
        """✏ Files were renamed ([(old, new)]): every list (and what is counted about them) follows. Returns how
        many tracks changed."""
        new_of = {file_key(old): new for old, new in moves}
        changed = 0
        with self._lock:
            for tracks in self.lists.values():
                for t in tracks:
                    new = new_of.get(file_key(t["path"]))
                    if new:
                        t["path"] = os.path.abspath(new)
                        t["title"] = os.path.splitext(os.path.basename(new))[0]
                        t.pop("away", None)                           # 👤 the song came: it is here now
                        changed += 1
            for old, new in moves:
                stat = self.stats.pop(file_key(old), None)
                if stat is not None:
                    self.stats[file_key(new)] = stat
            if self.state["own_orders"]:                              # ⇅ the user's own orders follow too
                self.state["own_orders"] = {n: [file_key(new_of[k]) if k in new_of else k for k in keys]
                                            for n, keys in self.state["own_orders"].items()}
            resume = self.state.get("resume_path")
            if resume and file_key(resume) in new_of:                 # "Kaldığın yer" follows its song
                self.state["resume_path"] = os.path.abspath(new_of[file_key(resume)])
        if changed:
            self.save()
        return changed

    def copy_to(self, name: str, tracks) -> int:
        """Put these tracks (with what is known about them) into another list; ones already there are skipped."""
        if is_smart(name):
            return 0
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
        if is_smart(name):
            name = self.unique_name(name)
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
        self._seen([path], added)
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
        self._keep_order(name)
        self.save()
        return True

    # ------------------------------------------------------------------ ✨ smart lists
    def _seen(self, paths, when=None):
        """Remember when these files came into DISO (for "recently added"); kept when already known."""
        import time
        now = time.time() if when is None else float(when)
        for path in paths:
            self.stats.setdefault(file_key(path), {}).setdefault("first", now)

    def count_play(self, path, when=None, track=None):
        """The song was listened to (see PLAYED_AFTER_MS); `track` gives its name for the 📊 statistics."""
        import time
        now = time.time() if when is None else float(when)
        key = file_key(path)
        s = self.stats.setdefault(key, {})
        s["plays"] = s.get("plays", 0) + 1
        s["last"] = now
        s.setdefault("first", now)
        artist, title = artist_and_title(track or self._track_by_key(key) or
                                         {"title": os.path.splitext(os.path.basename(path))[0]})
        self.log.append({"t": now, "k": key, "title": title, "artist": artist,
                         "ms": int((track or self._track_by_key(key) or {}).get("duration") or 0)})
        del self.log[:-MAX_LOG]
        self.save()

    def _track_by_key(self, key):
        for tracks in self.lists.values():
            for t in tracks:
                if file_key(t["path"]) == key:
                    return t
        return None

    def summary(self, since=0.0, until=None) -> dict:
        """📊 What was listened to between two times (seconds since 1970): {"plays", "ms", "songs":
        [(title, artist, plays)], "artists": [(artist, plays, ms)], "hours": [24 counts], "days": n,
        "streak": the most days in a row}. Listenings from before the log are counted for "all time"
        (since=0) from the songs' play counts."""
        import datetime
        entries = [e for e in self.log if e["t"] >= since and (until is None or e["t"] < until)]
        songs, artists, hours, days = {}, {}, [0] * 24, set()
        for e in entries:
            key = (e["title"], e["artist"])
            songs[key] = songs.get(key, 0) + 1
            a = artists.setdefault(e["artist"] or "?", [0, 0])
            a[0] += 1
            a[1] += e["ms"]
            when = datetime.datetime.fromtimestamp(e["t"])
            hours[when.hour] += 1
            days.add(when.date())
        plays, ms = len(entries), sum(e["ms"] for e in entries)
        if not since:                                    # counted before there was a log: add them
            logged = {}
            for e in self.log:
                logged[e["k"]] = logged.get(e["k"], 0) + 1
            for key, s in self.stats.items():
                extra = s.get("plays", 0) - logged.get(key, 0)
                track = self._track_by_key(key) if extra > 0 else None
                if not track:
                    continue
                artist, title = artist_and_title(track)
                songs[(title, artist)] = songs.get((title, artist), 0) + extra
                a = artists.setdefault(artist or "?", [0, 0])
                a[0] += extra
                a[1] += extra * int(track.get("duration") or 0)
                plays += extra
                ms += extra * int(track.get("duration") or 0)
        streak = best = 0
        previous = None
        for day in sorted(days):
            streak = streak + 1 if previous is not None and (day - previous).days == 1 else 1
            best = max(best, streak)
            previous = day
        return {"plays": plays, "ms": ms,
                "songs": sorted(((t, a, n) for (t, a), n in songs.items()), key=lambda x: (-x[2], x[0].casefold())),
                "artists": sorted(((a, n, m) for a, (n, m) in artists.items() if a != "?"),
                                  key=lambda x: (-x[1], x[0].casefold())),
                "hours": hours, "days": len(days), "streak": best}

    def plays(self, path) -> int:
        return self.stats.get(file_key(path), {}).get("plays", 0)

    def _added_time(self, track) -> float:
        known = self.stats.get(file_key(track["path"]), {}).get("first") or track.get("added")
        if known:
            return float(known)
        try:
            return os.path.getmtime(track["path"])        # from before DISO counted: when the file was made
        except OSError:
            return 0.0

    def refresh_smart(self, only=None):
        """Fill the smart lists again from every other list (each song once, files that are still there).
        They always come after the user's own lists."""
        library = {}
        for name, tracks in self.lists.items():
            if not is_smart(name):
                for t in tracks:
                    key = file_key(t["path"])
                    if key not in library and os.path.isfile(t["path"]):
                        library[key] = t

        def stat(key, what):
            return self.stats.get(key, {}).get(what, 0)
        newest = sorted(library, key=lambda k: -self._added_time(library[k]))
        made = {
            SMART_MOST: sorted((k for k in library if stat(k, "plays")),
                               key=lambda k: (-stat(k, "plays"), -stat(k, "last")))[:SMART_SIZE],
            SMART_NEW: newest[:SMART_SIZE],
            SMART_NEVER: [k for k in newest if not stat(k, "plays")],
        }
        old = {name: self.lists.pop(name) for name in SMART if name in self.lists}
        for name in SMART:
            if only is None or name == only:
                self.lists[name] = [{k: v for k, v in library[key].items() if k != "added"} for key in made[name]]
            else:
                self.lists[name] = old.get(name, [])

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


# ------------------------------------------------------------------ .m3u files
def write_m3u(tracks, target: str) -> int:
    """Save tracks as an .m3u / .m3u8 list (UTF-8) that other players and phones read. A song in the list's
    folder (or below it) is written relative to it, so the folder can be copied as a whole; the others
    with their full path. Returns how many songs were written."""
    base = os.path.dirname(os.path.abspath(target))
    lines = ["#EXTM3U"]
    for t in tracks:
        path = os.path.abspath(t["path"])
        artist, title = artist_and_title(t)
        seconds = int((t.get("duration") or 0) / 1000) or -1
        lines.append(f"#EXTINF:{seconds},{artist + ' - ' if artist else ''}{title}")
        try:
            rel = os.path.relpath(path, base)
        except ValueError:                                  # another drive
            rel = path
        lines.append(path if rel.startswith("..") or os.path.isabs(rel) else rel)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, target)
    return len(tracks)


def read_m3u(source: str) -> list:
    """The music files an .m3u / .m3u8 / .pls list names, in order (relative paths are read from the
    list's folder, file:/// addresses too). Lines that are not files on this computer are left out."""
    from urllib.parse import unquote, urlsplit
    raw = open(source, "rb").read()
    for codec in ("utf-8-sig", "cp1254", "latin-1"):        # old players wrote the Windows code page
        try:
            text = raw.decode(codec)
            break
        except UnicodeDecodeError:
            continue
    base = os.path.dirname(os.path.abspath(source))
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("file") and "=" in line and source.lower().endswith(".pls"):
            line = line.split("=", 1)[1].strip()            # File1=C:\music\a.mp3
        if not line or line.startswith("#") or "=" in line and source.lower().endswith(".pls"):
            continue
        if line.lower().startswith("file:"):
            parts = urlsplit(line)
            line = unquote(parts.path)
            if parts.netloc:                                # file://server/share/a.mp3
                line = f"\\{parts.netloc}{line}"
            elif len(line) > 2 and line[0] == "/" and line[2] == ":":
                line = line[1:]                             # file:///C:/music/a.mp3
        elif "://" in line:
            continue                                        # an internet radio, not a file
        path = os.path.normpath(os.path.join(base, line))
        if is_audio(path) and os.path.isfile(path):
            out.append(path)
    return out
