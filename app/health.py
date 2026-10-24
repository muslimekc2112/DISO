"""🩺 Is everything DISO needs in order? One check after the other (the window shows each as it comes): the
internet, YouTube, YouTube Music, GitHub, how old yt-dlp is, FFmpeg, Deno, aria2, the browser extension, the
download folder and its free room, DISO's own files and the proxy. A check that finds something wrong may name
a fix ("ffmpeg", "deno", "update", "extension", "folder") that the window offers as a button."""
import datetime
import os
import re
import shutil
import tempfile
from dataclasses import dataclass

import requests

from . import safefile
from .segmented_downloader import build_headers, check_connection, get_proxies, get_proxy
from .utils import app_data_dir, find_ffmpeg, human_size

OK, WARN, BAD, INFO = "ok", "warn", "bad", "info"
OLD_YTDLP_DAYS = 60           # YouTube changes often: an older yt-dlp may not cope any more
LOW_ROOM = 2 * 1024 ** 3      # bytes left in the download folder that are worth a warning
SITES = (("YouTube", "https://www.youtube.com/"), ("YouTube Music", "https://music.youtube.com/"),
         ("GitHub (güncellemeler)", "https://github.com/"))
FILES = (("settings.json", "Ayarlar"), ("playlists.json", "Çalma listeleri"), ("downloads.json", "İndirme listesi"),
         ("history.json", "İndirme geçmişi"), ("channels.json", "Takip edilen kanallar"))


@dataclass
class Check:
    name: str
    status: str               # OK / WARN / BAD / INFO
    detail: str = ""
    fix: str = ""             # what the window can do about it ("" = nothing)


def _reach(url, get=requests.get) -> str:
    """"" when the site answers, else why not."""
    try:
        r = get(url, headers=build_headers(), timeout=10, proxies=get_proxies(), stream=True)
        r.close()
        return "" if r.status_code < 500 else f"sunucu {r.status_code} dedi"
    except requests.RequestException as e:
        return type(e).__name__


def ytdlp_age(version: str, today=None):
    """Days since this yt-dlp came out ('2026.08.19' -> days), or None when it cannot be told."""
    m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", version or "")
    if not m:
        return None
    made = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return ((today or datetime.date.today()) - made).days


def run(folder, extension_seen=False, bridge_port=0, get=requests.get, online=check_connection):
    """Every check, one after the other (a generator: the window shows each one as soon as it is done)."""
    net, how = online()
    yield Check("İnternet bağlantısı", OK if net else BAD,
                f"var ({how.replace(' • ', ', ')})" if net else "yok gibi görünüyor: modemi ya da Wi-Fi'ı kontrol et")
    if net:
        for name, url in SITES:
            why = _reach(url, get)
            yield Check(name, OK if not why else WARN, "ulaşılabiliyor" if not why else f"ulaşılamadı ({why})")
    proxy = get_proxy()
    if proxy:
        through, _ = online(proxy=proxy)
        yield Check("Proxy", OK if through else BAD, f"{proxy} çalışıyor" if through
                    else f"{proxy} üzerinden internete çıkılamıyor: Ayarlar → Proxy", "" if through else "folder")

    from .about import ytdlp_version
    version = ytdlp_version()
    age = ytdlp_age(version)
    if not version:
        yield Check("yt-dlp", BAD, "yüklü değil ya da açılmıyor", "update")
    elif age is not None and age > OLD_YTDLP_DAYS:
        yield Check("yt-dlp", WARN, f"{version} ({age} gün önce çıktı): YouTube değişmiş olabilir, güncelle", "update")
    else:
        yield Check("yt-dlp", OK, version)

    ffmpeg = find_ffmpeg()
    yield Check("FFmpeg", OK if ffmpeg else WARN, ffmpeg or "yok: MP3 ve video birleştirme için lazım", "" if ffmpeg else "ffmpeg")
    from . import deno_setup
    deno = deno_setup.find()
    deno_version = deno_setup.version_of(deno) if deno else ""
    if not deno:
        yield Check("Deno", BAD, "yok: YouTube videolarının çoğu inmez", "deno")
    elif not deno_version:
        yield Check("Deno", BAD, f"çalışmıyor ({deno})", "deno")
    else:
        yield Check("Deno", OK, deno_version)
    from . import torrent
    aria2 = torrent.find_aria2()
    yield Check("aria2 (torrent)", OK if aria2 else INFO, aria2 or "ilk torrentte kendim indiririm (2.5 MB)")

    if extension_seen:
        yield Check("Tarayıcı eklentisi", OK, f"bağlandı (port {bridge_port})")
    else:
        yield Check("Tarayıcı eklentisi", INFO, "henüz hiç bağlanmadı: linke sağ tık → “DISO ile indir” için ekle",
                    "extension")

    yield _folder_check(folder)
    data = app_data_dir()
    broken = []
    for name, label in FILES:
        path = os.path.join(data, name)
        if not os.path.isfile(path):
            continue
        try:
            safefile._read(path)
        except (OSError, ValueError):
            broken.append(label)
    yield Check("DISO'nun dosyaları", OK if not broken else BAD,
                "hepsi sağlam" if not broken else f"bozuk: {', '.join(broken)} (açılışta son sağlam kopyası kullanılır)")


def _folder_check(folder) -> Check:
    if not folder or not os.path.isdir(folder):
        return Check("İndirme klasörü", BAD, f"yok: {folder or '—'}", "folder")
    try:
        fd, probe = tempfile.mkstemp(prefix=".diso-yazma-", dir=folder)
        os.close(fd)
        os.remove(probe)
    except OSError as e:
        return Check("İndirme klasörü", BAD, f"yazılamıyor ({e.strerror or e}): {folder}", "folder")
    free = shutil.disk_usage(folder).free
    if free < LOW_ROOM:
        return Check("İndirme klasörü", WARN, f"diskte yalnız {human_size(free)} boş yer var: {folder}", "folder")
    return Check("İndirme klasörü", OK, f"{human_size(free)} boş • {folder}")


def as_text(checks) -> str:
    marks = {OK: "✓", WARN: "⚠", BAD: "✗", INFO: "•"}
    return "\n".join(f"{marks.get(c.status, '?')} {c.name}: {c.detail}" for c in checks)
