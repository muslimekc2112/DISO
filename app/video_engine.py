"""
Video / audio layer.

yt-dlp is used ONLY to understand the page: it returns the real media URLs (with the
right headers/cookies). Our own multi-connection engine (segmented_downloader) then
downloads those URLs at full speed, and ffmpeg merges video+audio into an MP4 or
converts the audio to MP3.

If a site delivers the media in tiny fragments (HLS/DASH playlists) or the fast path
fails, we fall back to yt-dlp's own downloader with 16 parallel fragment downloads.
"""
import os
import re
import subprocess
import tempfile
import time

import requests

from . import updater
from .models import Item
from .logs import log
from .segmented_downloader import (LIMITER, TIMEOUT, DownloadStopped, build_headers, get_proxies,
                                   get_proxy)
from .utils import find_ffmpeg, media_folder, subprocess_flags

QUALITIES = ["En iyi", "2160p", "1440p", "1080p", "720p", "480p", "360p"]
BITRATES = ["320", "256", "192", "128"]
BROWSERS = ["Yok", "firefox", "chrome", "edge", "brave"]

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


LOOKUP_TIMEOUT = 15     # s: a request that hangs while a video is looked up is asked again sooner


class MissingFFmpeg(RuntimeError):
    pass


def _yt_dlp():
    updater.wait_ready()  # the startup update may still be replacing yt-dlp
    # imported lazily so the file downloader works even without yt-dlp; a broken update
    # is rolled back by load_yt_dlp
    return updater.load_yt_dlp()


def pretty_error(e) -> str:
    msg = _ANSI.sub("", str(e)).strip()
    msg = re.sub(r"^ERROR:\s*", "", msg)
    low = msg.lower()
    if "sign in to confirm" in low or "not a bot" in low or "login required" in low or "cookies" in low:
        msg += "\n→ 'Giriş çerezleri' menüsünden tarayıcını seç (giriş yaptığın tarayıcı)."
    elif "unsupported url" in low:
        msg += "\n→ Bu link ne bir video sayfası ne de indirilebilir bir dosya gibi duruyor."
    elif "no module named 'yt_dlp'" in low:
        msg = "yt-dlp kurulu değil: pip install -U yt-dlp"
    return msg[:600]


# ----------------------------------------------------------------------- yt-dlp options
def format_selector(kind: str, quality: str) -> str:
    if kind == "audio":
        return "bestaudio/best"
    digits = re.sub(r"\D", "", quality or "")
    if not digits:  # "En iyi"
        return "bv*+ba/b"
    h = int(digits)
    if h <= 1080:  # prefer H.264 + AAC: plays everywhere
        return (f"bv*[height<=?{h}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=?{h}]+ba/"
                f"b[height<=?{h}]/b")
    return f"bv*[height<=?{h}]+ba/b[height<=?{h}]/b"


def base_opts(cookies=None) -> dict:
    o = {
        "quiet": True, "no_warnings": True, "noprogress": True,
        "socket_timeout": 30, "retries": 10, "fragment_retries": 10, "extractor_retries": 3,
        "windowsfilenames": True, "noplaylist": True,
    }
    if cookies and cookies != "Yok":
        o["cookiesfrombrowser"] = (cookies.lower(),)
    if get_proxy():
        o["proxy"] = get_proxy()
    ff = find_ffmpeg()
    if ff:
        o["ffmpeg_location"] = os.path.dirname(ff)
    return o


def is_fast(f: dict) -> bool:
    """True if this format is ONE plain HTTP file (no HLS/DASH fragments)."""
    return bool(
        f.get("url")
        and f.get("protocol") in ("http", "https")
        and not f.get("fragments")
        and f.get("ext") != "mhtml"
        and not f.get("has_drm")
    )


def resolve(url, kind, quality, cookies=None) -> dict:
    """Ask yt-dlp for the video info (title, chosen formats, direct URLs, headers)."""
    yt_dlp = _yt_dlp()
    opts = base_opts(cookies)
    opts.update({"format": format_selector(kind, quality), "skip_download": True,
                 "socket_timeout": LOOKUP_TIMEOUT})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise RuntimeError("Video bilgisini alamadım")
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise RuntimeError("Bu oynatma listesi bomboş")
            info = entries[0]
        for f in (info.get("requested_formats") or [info]):
            try:  # headers + cookies exactly as yt-dlp itself would send them
                try:
                    hdrs = ydl._calc_headers(f, True)
                except TypeError:
                    hdrs = ydl._calc_headers(f)
                f["_fast_headers"] = dict(hdrs)
            except Exception:
                f["_fast_headers"] = dict(f.get("http_headers") or {})
    return info


class PlaylistEntries(list):
    """The entries of a playlist [(url, title, seconds), ...] that also know the playlist's own name
    (empty for a single video). Slices and copies are plain lists: use `like()` to keep the name."""

    def __init__(self, entries=(), title=""):
        super().__init__(entries)
        self.title = title or ""

    def like(self, entries):
        return PlaylistEntries(entries, self.title)


def expand_playlist(url, cookies=None) -> list:
    """[(entry_url, title, duration_seconds), ...] for a playlist URL; one entry otherwise.
    The result is a PlaylistEntries: its .title is the playlist's name ("" for a single video)."""
    yt_dlp = _yt_dlp()
    opts = base_opts(cookies)
    opts.update({"extract_flat": "in_playlist", "skip_download": True, "noplaylist": False})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info or info.get("_type") != "playlist":
        return PlaylistEntries([(url, (info or {}).get("title") or "", (info or {}).get("duration") or 0)])
    out = []
    for e in info.get("entries") or []:
        if not e:
            continue
        u = e.get("webpage_url") or e.get("url") or ""
        if u and not u.startswith("http"):
            if (e.get("ie_key") or "").lower() == "youtube" or "youtube" in url:
                u = f"https://www.youtube.com/watch?v={e.get('id') or u}"
            else:
                continue
        if u:
            out.append((u, e.get("title") or "", e.get("duration") or 0))
    return PlaylistEntries(out or [(url, "", 0)], info.get("title") if isinstance(info.get("title"), str) else "")


# ---------------------------------------------------------------------------- ffmpeg
def run_ffmpeg(args, item: Item):
    ff = find_ffmpeg()
    if not ff:
        raise MissingFFmpeg("FFmpeg bulunamadı")
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, **subprocess_flags())
    item._proc = proc
    try:
        while True:
            try:
                _, err = proc.communicate(timeout=0.3)
                break
            except subprocess.TimeoutExpired:
                if item.stop_reason:
                    proc.kill()
                    proc.communicate()
                    raise DownloadStopped(item.stop_reason)
    finally:
        item._proc = None
    if proc.returncode != 0:
        if item.stop_reason:
            raise DownloadStopped(item.stop_reason)
        raise RuntimeError("ffmpeg: " + (err or b"").decode("utf-8", "replace").strip()[-400:])


def merge_to_mp4(video, audio, out, audio_codec, item):
    copy_audio = (audio_codec or "").lower().startswith(("mp4a", "aac"))
    args = ["-i", video, "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"]
    args += ["-c:a", "copy"] if copy_audio else ["-c:a", "aac", "-b:a", "192k"]
    args += ["-movflags", "+faststart", out]
    run_ffmpeg(args, item)


def remux_to_mp4(src, out, item):
    try:
        run_ffmpeg(["-i", src, "-map", "0:v:0?", "-map", "0:a:0?", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], item)
    except DownloadStopped:
        raise
    except Exception:  # codec cannot live in MP4 -> re-encode video too
        run_ffmpeg(["-i", src, "-map", "0:v:0?", "-map", "0:a:0?", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", out], item)


def to_mp3(src, out, kbps, meta, item, cover=None):
    """Convert to MP3 with tags; `cover` is a JPEG that becomes the cover art."""
    if cover:
        args = ["-i", src, "-i", cover, "-map", "0:a:0", "-map", "1:v:0", "-codec:a", "libmp3lame",
                "-b:a", f"{kbps}k", "-c:v", "copy", "-id3v2_version", "3",
                "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)",
                "-disposition:v", "attached_pic"]
    else:
        args = ["-i", src, "-vn", "-map", "0:a:0", "-codec:a", "libmp3lame", "-b:a", f"{kbps}k",
                "-id3v2_version", "3"]
    for k, v in (meta or {}).items():
        if v:
            args += ["-metadata", f"{k}={v}"]
    args.append(out)
    run_ffmpeg(args, item)


# ----------------------------------------------------------------- subtitles / cover art
SUB_LANGS = {"Türkçe": "tr", "İngilizce": "en"}
_SUB_EXT_ORDER = ("srt", "vtt")


def _lang_key(keys, want):
    """The key of a subtitle dict that is `want` or a regional variant of it (en-US, en-GB)."""
    for k in keys:
        if k == want or k.lower().startswith(want + "-"):
            return k
    return None


def _best_subtitle(entries):
    usable = {e.get("ext"): e for e in entries or [] if e.get("url")}
    for ext in _SUB_EXT_ORDER:
        if ext in usable:
            return usable[ext]
    return None


def pick_subtitles(info: dict, choice: str) -> list:
    """Subtitles to save for `choice` (Yok / Türkçe / İngilizce / Tüm diller):
    [{"lang", "url", "ext"}, ...]. The uploader's own subtitles win over automatic captions;
    "Tüm diller" takes the uploader's own subtitles only."""
    if choice in (None, "", "Yok"):
        return []
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    out = []
    if choice == "Tüm diller":
        for lang, entries in manual.items():
            best = _best_subtitle(entries)
            if lang != "live_chat" and best:
                out.append({"lang": lang, "url": best["url"], "ext": best["ext"]})
        return out
    want = SUB_LANGS.get(choice)
    if not want:
        return []
    for source in (manual, auto):
        key = _lang_key(source, want)
        best = _best_subtitle(source.get(key)) if key else None
        if best:
            return [{"lang": want, "url": best["url"], "ext": best["ext"]}]
    return []


def original_subtitles(info: dict, skip=()) -> list:
    """When the wanted language cannot be had: the subtitle in the video's own language (the
    uploader's, else the automatic captions of what is spoken). Languages in `skip` are not taken."""
    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat"}
    auto = info.get("automatic_captions") or {}
    spoken = (info.get("language") or "").lower()
    order = []
    if spoken:
        order.append((manual, _lang_key(manual, spoken)))
    order += [(manual, k) for k in manual]
    order += [(auto, k) for k in auto if k.endswith("-orig")]
    if spoken:
        order.append((auto, _lang_key(auto, spoken)))
    for source, key in order:
        lang = (key or "").removesuffix("-orig")
        if not key or lang.split("-")[0].lower() in skip:
            continue
        best = _best_subtitle(source.get(key))
        if best:
            return [{"lang": lang, "url": best["url"], "ext": best["ext"]}]
    return []


def _download_small(url: str, headers=None, limit: int = 8 * 1024 * 1024) -> bytes:
    r = requests.get(url, headers=build_headers(headers), timeout=TIMEOUT, stream=True,
                     proxies=get_proxies())
    try:
        r.raise_for_status()
        data = bytearray()
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > limit:
                raise ValueError("dosya çok büyük")
        return bytes(data)
    finally:
        r.close()


SUB_RETRY_WAIT = 3.0       # s before asking again when YouTube says "too many requests"


def download_subtitles(item: Item, subs: list, base_path: str, sleep=time.sleep) -> list:
    """Save subtitles next to a video as '<video name>.<lang>.<ext>'. A subtitle that cannot
    be fetched is skipped (never fails the download); "too many requests" is asked once more.
    Returns the saved paths."""
    saved = []
    for sub in subs:
        path = f"{base_path}.{sub['lang']}.{sub['ext']}"
        for attempt in range(2):
            try:
                data = _download_small(sub["url"], item.request_headers())
                if not data.strip():
                    raise ValueError("boş altyazı")
                with open(path, "wb") as f:
                    f.write(data)
                saved.append(path)
                break
            except Exception as e:  # noqa: BLE001 - subtitles are a bonus
                busy = getattr(getattr(e, "response", None), "status_code", None) == 429
                if busy and attempt == 0:
                    sleep(SUB_RETRY_WAIT)
                    continue
                log.info("subtitle %s skipped: %s", sub["lang"], e)
                break
    return saved


_ISO3 = {"tr": "tur", "en": "eng", "de": "ger", "fr": "fre", "es": "spa", "it": "ita", "ru": "rus", "ar": "ara",
         "ja": "jpn", "ko": "kor", "pt": "por", "nl": "dut", "zh": "chi"}


def embed_subtitles(video: str, subs: list, item: Item) -> bool:
    """Put the saved subtitles into the MP4 as well (players then offer them by themselves); the
    files next to it stay. False (and the video untouched) when it cannot be done."""
    subs = [p for p in subs if p.lower().endswith((".srt", ".vtt"))]
    if not subs or not video.lower().endswith(".mp4") or not find_ffmpeg():
        return False
    tmp = video + ".subs.mp4"
    args = ["-i", video]
    for p in subs:
        args += ["-i", p]
    args += ["-map", "0:v?", "-map", "0:a?"]
    for i in range(len(subs)):
        args += ["-map", f"{i + 1}:0"]
    args += ["-c", "copy", "-c:s", "mov_text"]
    for i, p in enumerate(subs):
        lang = os.path.basename(p).rsplit(".", 2)[-2].split("-")[0].lower()
        args += [f"-metadata:s:s:{i}", f"language={_ISO3.get(lang, lang)}"]
    args += ["-movflags", "+faststart", tmp]
    try:
        run_ffmpeg(args, item)
        os.replace(tmp, video)
        return True
    except Exception as e:  # noqa: BLE001 - the subtitle files are still there
        log.info("subtitles not embedded: %s", e)
        return False
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def pick_thumbnail(info: dict) -> str:
    if info.get("thumbnail"):
        return info["thumbnail"]
    usable = [t for t in info.get("thumbnails") or [] if t.get("url")]
    return usable[-1]["url"] if usable else ""


COVER_MAX_BYTES = 90_000                              # well below the ~128 KB Windows can still read
COVER_STEPS = ((600, 3), (500, 6), (360, 10))          # (max width, JPEG quality) tried in order


def fetch_cover(info: dict, item: Item):
    """Download the thumbnail as a JPEG for MP3 cover art. Returns the temp file path, or
    None if there is no thumbnail / anything fails (the MP3 is made without a cover).
    Remove the result with discard_cover()."""
    url = pick_thumbnail(info)
    if not url:
        return None
    tmp = tempfile.mkdtemp(prefix="hizli-cover-")
    jpg = os.path.join(tmp, "cover.jpg")
    try:
        raw = os.path.join(tmp, "cover.raw")
        with open(raw, "wb") as f:
            f.write(_download_small(url, item.request_headers()))
        # YouTube sends WebP; MP3 players want JPEG. Windows' own MP3 reader cannot open a file whose
        # cover is bigger than ~128 KB, so the picture is kept small (a smaller, rougher one if needed)
        for width, quality in COVER_STEPS:
            run_ffmpeg(["-i", raw, "-frames:v", "1", "-q:v", str(quality), "-vf",
                        f"scale='min({width},iw)':-2", jpg], item)
            if os.path.getsize(jpg) <= COVER_MAX_BYTES:
                return jpg
        log.info("cover art skipped: still %d bytes", os.path.getsize(jpg))
        discard_cover(jpg)
        return None
    except DownloadStopped:
        discard_cover(jpg)
        raise
    except Exception as e:  # noqa: BLE001
        log.info("cover art skipped: %s", e)
        discard_cover(jpg)
        return None


def discard_cover(path):
    """Delete the temp folder of a cover made by fetch_cover (None is fine)."""
    if path:
        import shutil
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)


# -------------------------------------------------------------------------------- info
_HEIGHTS = [2160, 1440, 1080, 720, 480, 360]


def quality_for_height(height: int) -> str:
    """The option-bar quality that matches a video height (largest one that is not higher)."""
    for h in _HEIGHTS:
        if height >= h:
            return f"{h}p"
    return f"{_HEIGHTS[-1]}p"


def summarize_info(raw: dict) -> dict:
    """What the info window shows about a link, from a yt-dlp info dict."""
    best = {}
    for f in raw.get("formats") or []:
        h = f.get("height")
        if not h or (f.get("vcodec") or "none") == "none":
            continue
        entry = {"height": int(h), "fps": int(f.get("fps") or 0),
                 "codec": (f.get("vcodec") or "").split(".")[0],
                 "size": int(f.get("filesize") or f.get("filesize_approx") or 0), "ext": f.get("ext") or ""}
        old = best.get(entry["height"])
        if old is None or (entry["fps"], entry["size"]) > (old["fps"], old["size"]):
            best[entry["height"]] = entry
    audio = [f for f in raw.get("formats") or []
             if (f.get("vcodec") or "none") == "none" and (f.get("acodec") or "none") != "none"]
    audio_size = max((int(f.get("filesize") or f.get("filesize_approx") or 0) for f in audio), default=0)
    manual = sorted(k for k in (raw.get("subtitles") or {}) if k != "live_chat")
    return {
        "title": raw.get("title") or "",
        "uploader": raw.get("uploader") or raw.get("channel") or "",
        "duration": int(raw.get("duration") or 0),
        "thumbnail": pick_thumbnail(raw),
        "qualities": [best[h] for h in sorted(best, reverse=True)],
        "audio_size": audio_size,
        "subtitles": manual,
        "auto_subtitles": len(raw.get("automatic_captions") or {}),
        "is_playlist": raw.get("_type") == "playlist",
        "entries": len(raw.get("entries") or []),
    }


def fetch_info(url: str, cookies=None) -> dict:
    """Ask yt-dlp about a link (no download) and summarize it. Raises on any problem."""
    yt_dlp = _yt_dlp()
    opts = base_opts(cookies)
    opts.update({"skip_download": True})
    with yt_dlp.YoutubeDL(opts) as ydl:
        raw = ydl.extract_info(url, download=False)
    if raw is None:
        raise RuntimeError("Bu link hakkında bilgi alamadım")
    return summarize_info(raw)


# --------------------------------------------------------------------- yt-dlp fallback
def ydl_options(item: Item, hook=None) -> dict:
    """The yt-dlp options for downloading + post-processing one item with yt-dlp itself."""
    opts = base_opts(item.cookies)
    opts.update({
        "format": format_selector(item.kind, item.quality),
        "outtmpl": os.path.join(media_folder(item.folder, item.kind, item.sort_folders),
                                "%(title).150B.%(ext)s"),
        "concurrent_fragment_downloads": 16,
        "progress_hooks": [hook] if hook else [],
        "continuedl": True,
        "ratelimit": int(LIMITER.rate) or None,  # yt-dlp applies it per download
    })
    post = []
    if item.kind == "audio":
        post.append({"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                     "preferredquality": item.bitrate})
        if item.cover:
            opts["writethumbnail"] = True
            post += [{"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
                     {"key": "FFmpegMetadata", "add_metadata": True}, {"key": "EmbedThumbnail"}]
    else:
        # subtitles are fetched by DISO afterwards (jobs.save_subtitles): a subtitle YouTube refuses
        # must never make yt-dlp fail the whole video
        opts["merge_output_format"] = "mp4"
    if post:
        opts["postprocessors"] = post
    return opts


def ydl_download(item: Item):
    """Let yt-dlp download + post-process everything itself (16 parallel fragments)."""
    yt_dlp = _yt_dlp()
    from yt_dlp.utils import DownloadCancelled
    from .utils import human_size, human_eta

    def hook(d):
        if item.stop_reason:
            raise DownloadCancelled("stopped")
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            item.on_progress(done, total, d.get("speed") or 0, d.get("eta"), 0)
            item.message = f"yt-dlp • {human_size(item.speed)}/s • Kalan {human_eta(d.get('eta'))}"
        elif d.get("status") == "finished":
            item.fraction = 1.0

    opts = ydl_options(item, hook)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(item.url, download=True)
    except DownloadCancelled:
        raise DownloadStopped(item.stop_reason or "cancel")
    except Exception:
        if item.stop_reason:
            raise DownloadStopped(item.stop_reason)
        raise
    if info and info.get("_type") == "playlist":
        info = next((e for e in info.get("entries") or [] if e), info)
    rd = (info or {}).get("requested_downloads") or [{}]
    return rd[0].get("filepath") or (info or {}).get("filepath") or ""
