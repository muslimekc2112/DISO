"""
The actual work for one list item:

  classify()   - "Auto" mode: decide whether a link is a plain file or a video page
  keep_files_as_they_are() - MP4 / MP3 chosen for a plain file (a zip ...): download it as it is
  run_file()   - plain file (zip/rar/7z/exe/iso/mp4 ...) with the multi-connection engine
  run_media()  - video / MP3: yt-dlp finds the URLs, our engine downloads them fast,
                 ffmpeg merges / converts. Falls back to yt-dlp's downloader if needed.
"""
import os
import threading
from urllib.parse import urlsplit

from . import video_engine as ve
from .ffmpeg_setup import ensure_ffmpeg
from .logs import log
from .models import DOWNLOADING, PROCESSING, RESOLVING, Item
from .segmented_downloader import (DownloadStopped, FastDownloader, TransientError, is_transient,
                                   probe)
from .utils import (category_folder, find_ffmpeg, human_size, media_folder, sanitize_filename,
                    unique_path)


def _check_stop(item: Item):
    if item.stop_reason:
        raise DownloadStopped(item.stop_reason)


_name_lock = threading.Lock()


def reserve_path(folder: str, filename: str) -> str:
    """unique_path() plus an empty '<path>.part' placeholder. unique_path treats a .part
    file as "taken", so a download that picks its name at the same moment gets another one."""
    with _name_lock:
        path = unique_path(folder, filename)
        open(path + ".part", "ab").close()
    return path


def release_path(path: str) -> None:
    try:
        os.remove(path + ".part")
    except OSError:
        pass


# ------------------------------------------------------------------------ auto detect
VIDEO_SITES = ("youtube.com", "youtu.be", "youtube-nocookie.com", "instagram.com", "tiktok.com", "x.com",
               "twitter.com", "facebook.com", "fb.watch", "vimeo.com", "dailymotion.com", "twitch.tv",
               "soundcloud.com", "reddit.com", "pinterest.com", "bilibili.com", "kick.com", "music.youtube.com")


def is_video_site(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in VIDEO_SITES)


def classify(item: Item):
    """Sets item.kind to 'file' or 'video' by looking at the server's answer. Links of well-known
    video sites are not asked (a request to their page only costs time)."""
    if is_video_site(item.url):
        item.kind = "video"
        return
    item.message = "Bu linkin ne olduğuna bakıyorum…"
    try:
        pr = probe(item.url, item.request_headers(), timeout=12)
    except Exception:
        item.kind = "video"  # pages that block plain requests are usually video sites
        return
    ct = (pr.content_type or "").lower()
    path = item.url.lower().split("?")[0]
    if path.endswith((".m3u8", ".mpd")) or "mpegurl" in ct or "dash+xml" in ct:
        item.kind = "video"
    elif ct.startswith(("text/html", "application/xhtml", "application/json", "text/xml")):
        item.kind = "video"
    else:
        item.kind = "file"
        item._probe = pr


# a direct link with one of these is something yt-dlp / FFmpeg can turn into MP4 / MP3
MEDIA_EXTENSIONS = (".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".ts", ".3gp", ".mpg", ".mpeg",
                    ".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".oga", ".opus", ".wma", ".m3u8", ".mpd")


def is_plain_file_link(url: str) -> bool:
    """A link whose name says it is an archive, a program, a document or a picture (never a video page)."""
    from urllib.parse import unquote

    from .utils import category_for
    if is_video_site(url):
        return False
    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    return category_for(name) in ("Arşiv", "Program", "Belge", "Resim")


def keep_files_as_they_are(item: Item):
    """MP4 / MP3 was chosen, but the link is a plain file (a zip, an exe, a pdf ...): it is downloaded
    as it is, not handed to yt-dlp to be "converted". Video sites, pages and sound / video files keep
    the choice; when the server cannot be asked the choice is kept too."""
    if is_video_site(item.url):
        return
    path = item.url.lower().split("?")[0].split("#")[0]
    if path.endswith(MEDIA_EXTENSIONS):
        return
    item.message = "Bu linkin ne olduğuna bakıyorum…"
    try:
        pr = probe(item.url, item.request_headers(), timeout=12)
    except Exception:  # noqa: BLE001 - a page that blocks plain requests: let yt-dlp try it
        item.message = ""
        return
    item.message = ""
    ct = (pr.content_type or "").lower()
    if (ct.startswith(("text/html", "application/xhtml", "application/json", "text/xml", "video/", "audio/"))
            or "mpegurl" in ct or "dash+xml" in ct or (pr.filename or "").lower().endswith(MEDIA_EXTENSIONS)):
        return
    log.info("%s is a plain file (%s), downloading it as it is instead of as %s", item.url, ct, item.kind)
    item.kind = "file"
    item._probe = pr


# ------------------------------------------------------------------------------- file
def run_file(item: Item):
    os.makedirs(item.folder, exist_ok=True)
    pr = item._probe
    headers = item.request_headers()
    if not item.dest:
        pr = pr or probe(item.url, headers)
        target = category_folder(item.folder, pr.filename) if item.sort_folders else item.folder
        os.makedirs(target, exist_ok=True)
        item.dest = reserve_path(target, pr.filename)  # the placeholder becomes the .part file
        item.title = os.path.basename(item.dest)
    item._probe = None
    fd = FastDownloader(item.url, item.dest, item.connections, headers=headers,
                        on_progress=item.on_progress, probe_result=pr)
    item.attach(fd)
    _check_stop(item)
    item.state = DOWNLOADING
    item.message = ""
    item.final_path = fd.run()
    if not fd.resumable:
        item.message = "Sunucu parçalı indirmeye izin vermiyor, tek bağlantıyla devam"


# ------------------------------------------------------------------------------ media
def _get_ffmpeg(item: Item, required: bool) -> bool:
    if find_ffmpeg():
        return True
    item.message = "FFmpeg indiriliyor (tek seferlik, ~90 MB)…"
    ensure_ffmpeg(progress=lambda d, t: setattr(
        item, "message", f"FFmpeg indiriliyor… {human_size(d)} / {human_size(t) if t else '?'}"))
    if find_ffmpeg():
        return True
    if required:
        raise ve.MissingFFmpeg(
            "FFmpeg bulunamadı ve otomatik kurulamadı. ffmpeg.exe'yi 'ffmpeg' klasörüne koy "
            "(https://www.gyan.dev/ffmpeg/builds/) ve ▶ ile devam et — indirilen parça korunuyor.")
    return False


def _remove_parts(paths):
    for p in paths:
        FastDownloader.cleanup(p)
        try:
            os.remove(p)
        except OSError:
            pass


def _fast_media(item: Item, info: dict, fmts: list, stem: str) -> str:
    folder = item.folder
    sizes = [int(f.get("filesize") or f.get("filesize_approx") or 0) for f in fmts]
    known = all(sizes)
    weights = sizes if known else [1] * len(fmts)
    wsum = float(sum(weights))
    item.total = sum(sizes) if known else 0

    parts, completed = [], 0.0
    for i, f in enumerate(fmts):
        # item.id in the name: two videos with the same title must not share temp files
        path = os.path.join(folder, f"{stem}.{item.id}.f{i}.{f.get('ext') or 'bin'}")
        if path not in item.temp_files:
            item.temp_files.append(path)
        # a part that was fully downloaded before (resume after a crash while merging)
        if known and os.path.exists(path) and not os.path.exists(path + ".part") \
                and os.path.getsize(path) == sizes[i]:
            parts.append(path)
            completed += weights[i]
            continue
        if os.path.exists(path) and not os.path.exists(path + ".part"):
            os.remove(path)

        def cb(done, total, speed, eta, conns, i=i, base=completed):
            frac = (done / total) if total else 0.0
            overall = (base + weights[i] * frac) / wsum
            item.fraction = overall
            item.done = int(overall * item.total) if item.total else done
            item.speed, item.conns = speed, conns
            if item.total and speed > 0:
                item.eta = max(0.0, (item.total - item.done) / speed)
            else:
                item.eta = eta

        fd = FastDownloader(f["url"], path, item.connections,
                            headers=f.get("_fast_headers") or f.get("http_headers"), on_progress=cb)
        item.attach(fd)
        _check_stop(item)
        fd.run()
        completed += weights[i]
        parts.append(path)

    item._fd = None
    return _finish_media(item, info, fmts, parts, stem)


def _finish_media(item: Item, info: dict, fmts: list, parts: list, stem: str) -> str:
    reserved = []   # output names held by placeholders while ffmpeg works
    try:
        return _finish_media_body(item, info, fmts, parts, stem, reserved)
    finally:
        for path in reserved:
            release_path(path)


def _reserve(reserved: list, folder: str, filename: str) -> str:
    path = reserve_path(folder, filename)
    reserved.append(path)
    return path


def _finish_media_body(item: Item, info: dict, fmts: list, parts: list, stem: str, reserved: list) -> str:
    folder = media_folder(item.folder, item.kind, item.sort_folders)
    os.makedirs(folder, exist_ok=True)
    item.state, item.speed, item.eta, item.fraction = PROCESSING, 0.0, None, 1.0
    _check_stop(item)

    def ext_of(p):
        return os.path.splitext(p)[1].lstrip(".") or "bin"

    if item.kind == "audio":
        _get_ffmpeg(item, required=True)
        out = _reserve(reserved, folder, stem + ".mp3")
        tmp_out = out + ".tmp.mp3"
        item.message = "MP3'e çeviriyorum…"
        meta = {"title": info.get("track") or info.get("title"),
                "artist": info.get("artist") or info.get("uploader") or info.get("channel")}
        cover = ve.fetch_cover(info, item) if item.cover else None
        try:
            ve.to_mp3(parts[-1], tmp_out, item.bitrate, meta, item, cover=cover)
            os.replace(tmp_out, out)
        finally:
            ve.discard_cover(cover)
            if os.path.exists(tmp_out):
                os.remove(tmp_out)
    elif len(parts) == 1 and ext_of(parts[0]) == "mp4":
        out = _reserve(reserved, folder, stem + ".mp4")
        os.replace(parts[0], out)
    elif len(parts) == 1:
        if _get_ffmpeg(item, required=False):
            out = _reserve(reserved, folder, stem + ".mp4")
            tmp_out = out + ".tmp.mp4"
            item.message = "MP4'e çeviriyorum…"
            try:
                ve.remux_to_mp4(parts[0], tmp_out, item)
                os.replace(tmp_out, out)
            finally:
                if os.path.exists(tmp_out):
                    os.remove(tmp_out)
        else:  # no ffmpeg: keep the file as it is
            out = _reserve(reserved, folder, f"{stem}.{ext_of(parts[0])}")
            os.replace(parts[0], out)
            item.message = "FFmpeg yok, dosyayı olduğu gibi kaydettim"
            _remove_parts(parts)
            return out
    else:
        _get_ffmpeg(item, required=True)
        out = _reserve(reserved, folder, stem + ".mp4")
        tmp_out = out + ".tmp.mp4"
        item.message = "Video ile sesi birleştiriyorum…"
        try:
            ve.merge_to_mp4(parts[0], parts[1], tmp_out, fmts[1].get("acodec"), item)
            os.replace(tmp_out, out)
        finally:
            if os.path.exists(tmp_out):
                os.remove(tmp_out)
    _remove_parts([p for p in parts if os.path.exists(p) or os.path.exists(p + ".part.json")])
    item.temp_files = []
    item.message = ""
    return out


def _ydl_fallback(item: Item) -> str:
    item.state = DOWNLOADING
    _get_ffmpeg(item, required=(item.kind == "audio"))
    path = ve.ydl_download(item)
    item.message = ""
    return path


def save_subtitles(item: Item, info: dict, path: str) -> list:
    """The chosen subtitles next to the video (and inside it). When YouTube refuses the wanted
    language (its translations are often 'too many requests'), the video's own language is kept
    instead and the message says so. Never fails the download."""
    item.state, item.message = PROCESSING, "Altyazılar indiriliyor…"
    base = os.path.splitext(path)[0]
    subs = ve.pick_subtitles(info, item.subs)
    saved = ve.download_subtitles(item, subs, base) if subs else []
    note = ""
    want = ve.SUB_LANGS.get(item.subs)
    if not saved and want:
        other = ve.original_subtitles(info, skip={want})
        saved = ve.download_subtitles(item, other, base) if other else []
        if saved:
            note = (f"{item.subs} altyazıyı YouTube vermedi; videonun kendi dilindeki "
                    f"({other[0]['lang']}) altyazıyı kaydettim")
    if saved:
        item.message = "Altyazı videoya ekleniyor…"
        ve.embed_subtitles(path, saved, item)
    if note:
        item.message = note
    elif saved:
        item.message = f"{len(saved)} altyazı kaydedildi" + (" (videonun içinde de var)" if path.lower().endswith(".mp4") else "")
    else:
        item.message = "Bu videoda istediğin dilde altyazı bulamadım"
    return saved


def run_media(item: Item):
    os.makedirs(item.folder, exist_ok=True)
    item.state = RESOLVING
    item.message = "Video bilgisini alıyorum…"
    try:
        info = ve.resolve(item.url, item.kind, item.quality, item.cookies)
    except Exception as e:
        _check_stop(item)
        raise (TransientError if is_transient(e) else RuntimeError)(ve.pretty_error(e))
    _check_stop(item)

    title = info.get("title") or info.get("id") or "video"
    item.title = title
    stem = sanitize_filename(title, 120)
    fmts = info.get("requested_formats") or [info]

    if all(ve.is_fast(f) for f in fmts):
        try:
            item.state = DOWNLOADING
            item.message = ""
            path = _fast_media(item, info, fmts, stem)
        except (DownloadStopped, ve.MissingFFmpeg):
            raise
        except Exception as e:
            _check_stop(item)
            item.message = f"Hızlı motor takıldı ({str(e)[:80]}), yt-dlp devralıyor…"
            path = _ydl_fallback(item)
    else:
        path = _ydl_fallback(item)
    item.final_path = path or ""
    if item.kind == "video" and item.subs != "Yok" and path and os.path.exists(path):
        save_subtitles(item, info, path)
