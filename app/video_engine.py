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

from . import updater
from .models import Item
from .segmented_downloader import LIMITER, DownloadStopped
from .utils import find_ffmpeg, subprocess_flags

QUALITIES = ["En iyi", "2160p", "1440p", "1080p", "720p", "480p", "360p"]
BITRATES = ["320", "256", "192", "128"]
BROWSERS = ["Yok", "firefox", "chrome", "edge", "brave"]

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


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
        msg += "\n→ Bu bağlantı bir video sayfası / indirilebilir dosya değil."
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
    opts.update({"format": format_selector(kind, quality), "skip_download": True})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise RuntimeError("Video bilgisi alınamadı")
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise RuntimeError("Oynatma listesi boş")
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


def expand_playlist(url, cookies=None) -> list:
    """[(entry_url, title), ...] for a playlist URL; a single [(url, title)] otherwise."""
    yt_dlp = _yt_dlp()
    opts = base_opts(cookies)
    opts.update({"extract_flat": "in_playlist", "skip_download": True, "noplaylist": False})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info or info.get("_type") != "playlist":
        return [(url, (info or {}).get("title") or "")]
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
            out.append((u, e.get("title") or ""))
    return out or [(url, "")]


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


def to_mp3(src, out, kbps, meta, item):
    args = ["-i", src, "-vn", "-map", "0:a:0", "-codec:a", "libmp3lame", "-b:a", f"{kbps}k",
            "-id3v2_version", "3"]
    for k, v in (meta or {}).items():
        if v:
            args += ["-metadata", f"{k}={v}"]
    args.append(out)
    run_ffmpeg(args, item)


# --------------------------------------------------------------------- yt-dlp fallback
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

    opts = base_opts(item.cookies)
    opts.update({
        "format": format_selector(item.kind, item.quality),
        "outtmpl": os.path.join(item.folder, "%(title).150B.%(ext)s"),
        "concurrent_fragment_downloads": 16,
        "progress_hooks": [hook],
        "continuedl": True,
        "ratelimit": int(LIMITER.rate) or None,  # yt-dlp applies it per download
    })
    if item.kind == "audio":
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                                   "preferredquality": item.bitrate}]
    else:
        opts["merge_output_format"] = "mp4"
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
