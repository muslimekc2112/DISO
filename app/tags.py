"""Reads what is inside a music file (title, artist, album, length, cover picture) with ffprobe /
ffmpeg, on a background thread, and remembers the answers so a file is read only once.

The window never waits for this: it asks with `request()` and picks up the answers from
`results` a few times a second."""
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading

from .logs import log
from .utils import app_data_dir, find_ffmpeg, subprocess_flags

TIMEOUT = 20
COVER_SIZE = 360                    # the cover is kept at most this many pixels wide
_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_TAG_LINE = re.compile(r"^\s{2,}(title|artist|album|album_artist)\s*:\s*(.+?)\s*$", re.I | re.M)


def _tool(name):
    """ffprobe / ffmpeg: the one on the PATH, or the one next to ffmpeg."""
    found = shutil.which(name)
    if found:
        return found
    ff = find_ffmpeg()
    if ff:
        for ext in (".exe", ""):
            candidate = os.path.join(os.path.dirname(ff), name + ext)
            if os.path.isfile(candidate):
                return candidate
    return None


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL,
                          **subprocess_flags())


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def _clean(value):
    value = (value or "").strip().replace("\x00", "")
    return value[:200]


def _from_probe(data: dict) -> dict:
    fmt = data.get("format") or {}
    tags = {str(k).lower(): v for k, v in (fmt.get("tags") or {}).items()}
    for stream in data.get("streams") or []:                       # some formats keep tags per stream
        for k, v in (stream.get("tags") or {}).items():
            if not tags.get(str(k).lower()):                       # an empty tag does not hide a filled one
                tags[str(k).lower()] = v
    try:
        seconds = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        seconds = 0.0
    cover = any((s.get("disposition") or {}).get("attached_pic") for s in data.get("streams") or [])
    return {"duration": int(seconds * 1000) if seconds > 0 else 0,
            "title": _clean(tags.get("title")),
            "artist": _clean(tags.get("artist") or tags.get("album_artist")),
            "album": _clean(tags.get("album")),
            "cover": bool(cover)}


def _from_ffmpeg_text(text: str) -> dict:
    """The same facts from the text `ffmpeg -i file` prints, for a machine that has no ffprobe."""
    out = {"duration": 0, "title": "", "artist": "", "album": "", "cover": "Video: " in text and "attached pic" in text}
    m = _DURATION.search(text)
    if m:
        out["duration"] = int((int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) * 1000)
    seen = {}
    for key, value in _TAG_LINE.findall(text):
        seen.setdefault(key.lower(), value)
    out["title"] = _clean(seen.get("title"))
    out["artist"] = _clean(seen.get("artist") or seen.get("album_artist"))
    out["album"] = _clean(seen.get("album"))
    return out


def probe(path: str) -> dict:
    """{"duration": ms, "title", "artist", "album", "cover": bool} of a file; {} if it cannot be read."""
    ffprobe = _tool("ffprobe")
    try:
        if ffprobe:
            proc = _run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
            if proc.returncode == 0:
                return _from_probe(json.loads(_text(proc.stdout) or "{}"))
        ffmpeg = _tool("ffmpeg")
        if ffmpeg:
            proc = _run([ffmpeg, "-hide_banner", "-i", path])      # exits with 1: it has nothing to write to
            info = _from_ffmpeg_text(_text(proc.stderr))
            if info["duration"] or info["title"] or info["artist"]:
                return info
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        log.info("cannot read tags of %s: %s", path, e)
    return {}


def covers_dir() -> str:
    d = os.path.join(app_data_dir(), "covers")
    os.makedirs(d, exist_ok=True)
    return d


def _signature(path: str):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [int(st.st_mtime), st.st_size]


def cover_file(path: str) -> str:
    """Where the cover of this file is (or would be) kept."""
    sig = _signature(path) or [0, 0]
    key = hashlib.sha1(f"{os.path.abspath(path)}|{sig[0]}|{sig[1]}".encode("utf-8")).hexdigest()
    return os.path.join(covers_dir(), key + ".jpg")


def extract_cover(path: str):
    """Save the picture inside the file as a small JPEG. Returns its path, or None if there is none."""
    target = cover_file(path)
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        return target
    ffmpeg = _tool("ffmpeg")
    if not ffmpeg:
        return None
    tmp = target + ".part.jpg"
    try:
        proc = _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", path, "-an", "-map", "0:v:0",
                     "-frames:v", "1", "-vf", f"scale='min({COVER_SIZE},iw)':-2", "-c:v", "mjpeg", "-q:v", "3",
                     "-f", "image2", tmp])
        if proc.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, target)
            return target
    except (OSError, subprocess.SubprocessError) as e:
        log.info("cannot take the cover of %s: %s", path, e)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return None


class TagReader:
    """Asks for tags and covers in the background.

    request(path)        -> later results gets ("tags", path, info)
    request_cover(path)  -> later results gets ("cover", path, image path or None)
    """

    def __init__(self, cache_path=None, read=probe, cover=extract_cover):
        self.cache_path = cache_path or os.path.join(app_data_dir(), "tags_cache.json")
        self.results = queue.Queue()
        self._read, self._cover = read, cover
        self._jobs = queue.Queue()
        self._pending = set()
        self._lock = threading.Lock()
        self._dirty = False
        self._stop = False
        self._cache = self._load()
        self._thread = threading.Thread(target=self._work, daemon=True, name="tag-reader")
        self._thread.start()

    # ------------------------------------------------------------------ cache
    def _load(self):
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001 - a missing or damaged cache is simply empty
            return {}

    def save(self):
        with self._lock:
            if not self._dirty:
                return
            data, self._dirty = dict(self._cache), False
        tmp = self.cache_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.cache_path)
        except OSError:
            pass

    def cached(self, path: str):
        """The remembered tags of a file if it has not changed since, else None."""
        entry = self._cache.get(os.path.abspath(path))
        if entry and entry.get("sig") == _signature(path):
            return entry["info"]
        return None

    # ------------------------------------------------------------------ asking
    def request(self, path: str):
        info = self.cached(path)
        if info is not None:
            self.results.put(("tags", path, info))
            return
        self._enqueue(("tags", path))

    def request_cover(self, path: str):
        self._enqueue(("cover", path))

    def _enqueue(self, job):
        with self._lock:
            if job in self._pending or self._stop:
                return
            self._pending.add(job)
        self._jobs.put(job)

    def _work(self):
        while True:
            job = self._jobs.get()
            if job is None or self._stop:
                return
            kind, path = job
            try:
                if kind == "tags":
                    info = self._read(path) if os.path.isfile(path) else {}
                    sig = _signature(path)
                    if sig is not None:
                        with self._lock:
                            self._cache[os.path.abspath(path)] = {"sig": sig, "info": info}
                            self._dirty = True
                    self.results.put(("tags", path, info))
                else:
                    self.results.put(("cover", path, self._cover(path) if os.path.isfile(path) else None))
            except Exception:  # noqa: BLE001 - one bad file must not stop the reader
                log.exception("tag reader failed for %s", path)
                self.results.put((kind, path, {} if kind == "tags" else None))
            finally:
                with self._lock:
                    self._pending.discard(job)
                if self._jobs.empty():
                    self.save()

    def drain(self):
        """All answers that arrived so far: [(kind, path, value), ...]."""
        out = []
        while True:
            try:
                out.append(self.results.get_nowait())
            except queue.Empty:
                return out

    def stop(self):
        """Stop now: what is still waiting is dropped (asked again next time), the file being read finishes."""
        self._stop = True
        while True:
            try:
                self._jobs.get_nowait()
            except queue.Empty:
                break
        self._jobs.put(None)
        self._thread.join(timeout=1)
        self.save()


# ------------------------------------------------------------------ 🏷 writing tags (the tag editor)
FIELDS = ("title", "artist", "album", "date", "genre")
COVER_FORMATS = (".mp3", ".m4a", ".mp4", ".aac", ".flac")     # files that can carry a cover picture
KEEP, REMOVE = "keep", "remove"                              # cover: as it is / take it out (else a picture file)


def read_fields(path: str) -> dict:
    """{field: text} of FIELDS as written in the file now ("" when missing)."""
    ffprobe = _tool("ffprobe")
    tags = {}
    if ffprobe:
        try:
            proc = _run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
            data = json.loads(_text(proc.stdout) or "{}")
            for part in [data.get("format") or {}] + list(data.get("streams") or []):
                for k, v in (part.get("tags") or {}).items():
                    tags.setdefault(str(k).lower(), v)
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            log.info("cannot read tags of %s: %s", path, e)
    out = {f: _clean(tags.get(f)) for f in FIELDS}
    out["date"] = out["date"] or _clean(tags.get("year"))
    return out


def _cover_jpeg(picture: str, target: str) -> str:
    """The chosen picture as a JPEG of at most 800 pixels (what every player shows)."""
    from PIL import Image
    with Image.open(picture) as im:
        im = im.convert("RGB")
        im.thumbnail((800, 800))
        im.save(target, "JPEG", quality=90)
    return target


def write_args(path: str, out: str, fields: dict, cover=KEEP, picture="") -> list:
    """ffmpeg arguments (without the program) that copy `path` to `out` with these tags. The sound is
    copied as it is (nothing is converted)."""
    ext = os.path.splitext(path)[1].lower()
    args = ["-y", "-hide_banner", "-loglevel", "error", "-i", path]
    if cover not in (KEEP, REMOVE):
        args += ["-i", picture]
    if cover == KEEP:
        args += ["-map", "0"]
    else:
        args += ["-map", "0:a"]
        if cover not in (KEEP, REMOVE):
            args += ["-map", "1:0", "-disposition:v:0", "attached_pic"]
    args += ["-c", "copy", "-map_metadata", "0"]
    ogg = ext in (".ogg", ".oga", ".opus")                     # Ogg keeps its tags on the sound stream
    for f in FIELDS:
        if f in fields:
            args += ["-metadata:s:a:0" if ogg else "-metadata", f"{f}={_clean(fields[f])}"]
    if ext == ".mp3":
        args += ["-id3v2_version", "3"]
    return args + [out]


def write_tags(path: str, fields: dict, cover=KEEP) -> None:
    """🏷 Write title / artist / album / year / genre (and the cover: KEEP, REMOVE or a picture file) into
    the file. A copy is made next to it and put in its place only when ffmpeg made it well, so the song is
    never left half written. Raises OSError with the reason when it cannot be done."""
    ffmpeg = _tool("ffmpeg")
    if not ffmpeg:
        raise OSError("FFmpeg yok")
    if cover not in (KEEP, REMOVE) and os.path.splitext(path)[1].lower() not in COVER_FORMATS:
        cover = KEEP
    folder, name = os.path.split(os.path.abspath(path))
    stem, ext = os.path.splitext(name)
    out = os.path.join(folder, f".{stem}.diso-tags{ext}")
    picture = os.path.join(folder, f".{stem}.diso-cover.jpg")
    try:
        if cover not in (KEEP, REMOVE):
            _cover_jpeg(cover, picture)
        proc = _run([ffmpeg] + write_args(path, out, fields, cover, picture))
        if proc.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
            raise OSError(_text(proc.stderr).strip().splitlines()[-1] if proc.stderr.strip() else "FFmpeg yazamadı")
        os.replace(out, path)
    except subprocess.SubprocessError as e:
        raise OSError(str(e)) from e
    finally:
        for leftover in (out, picture):
            try:
                os.remove(leftover)
            except OSError:
                pass
