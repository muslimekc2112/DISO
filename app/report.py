"""🐞 "Sorun bildir": what is needed to understand a problem, in one zip on the Desktop, ready to drop into a new
issue on GitHub (whose page is opened with the versions already written in it).

In it: the versions and the health check (bilgi.txt), the log (links shortened to their site, so what was
downloaded does not show), the settings (a proxy password hidden) and the states of the downloads (no links,
no names). Never in it: the playlists, the history, cookies, the downloaded files."""
import json
import os
import re
import time
import zipfile
from urllib.parse import quote

from . import brand
from .logs import crash_path, log_path
from .utils import app_data_dir

_URL = re.compile(r"(https?|magnet|file):(//)?([^/\s?#\"']*)[^\s\"'<>]*", re.I)
_PROXY_LOGIN = re.compile(r"(\w+://)[^@/\s]+@")


def hide_links(text: str) -> str:
    """'https://site.com/a/b?c=1' -> 'https://site.com/…' (a magnet or a file link loses all but its kind)."""
    def short(m):
        scheme, host = m.group(1).lower(), m.group(3)
        if scheme in ("magnet", "file"):
            return f"{scheme}:…"
        return f"{scheme}://{host}/…"
    return _URL.sub(short, text or "")


def clean_settings(data: dict) -> dict:
    out = dict(data or {})
    if out.get("proxy"):
        out["proxy"] = _PROXY_LOGIN.sub(r"\1***@", str(out["proxy"]))
    out.pop("restart_view", None)
    return out


def downloads_text(items) -> str:
    lines = []
    for it in items:
        host = hide_links(it.url)
        note = it.error or it.message or ""
        lines.append(f"{it.state:<11} {it.kind:<6} {host}  {hide_links(note)}".rstrip())
    return "\n".join(lines) or "(liste boş)"


def desktop() -> str:
    """The user's Desktop (also when Windows keeps it in OneDrive), else the home folder."""
    try:
        from hizli_setup import winapi
        place = winapi.known_folder(winapi.FOLDER_DESKTOP)
        if place and os.path.isdir(place):
            return place
    except Exception:  # noqa: BLE001 - not Windows, or the shell does not answer
        pass
    home = os.path.expanduser("~")
    return os.path.join(home, "Desktop") if os.path.isdir(os.path.join(home, "Desktop")) else home


def make(facts_text: str, health_text: str, settings: dict, items, folder=None, now=time.time) -> str:
    """Write the zip; returns its path."""
    folder = folder or desktop()
    stamp = time.strftime("%Y%m%d-%H%M", time.localtime(now()))
    path = os.path.join(folder, f"DISO-sorun-raporu-{stamp}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bilgi.txt", f"{facts_text}\n\nSağlık kontrolü\n{health_text}\n")
        z.writestr("ayarlar.json", json.dumps(clean_settings(settings), ensure_ascii=False, indent=2))
        z.writestr("indirmeler.txt", downloads_text(items))
        base = log_path()
        for n, name in enumerate((base, base + ".1", base + ".2")):
            try:
                with open(name, encoding="utf-8", errors="replace") as f:
                    z.writestr(os.path.basename(name), hide_links(f.read()))
            except OSError:
                if n == 0:
                    z.writestr("diso.log", "(günlük dosyası yok)")
        try:
            with open(crash_path(), encoding="utf-8", errors="replace") as f:
                z.writestr("crash.log", hide_links(f.read()))
        except OSError:
            pass                                          # (no crash recorded: nothing to add)
        z.writestr("NOT.txt", "Bu dosyada çalma listelerin, geçmişin, çerezlerin ve indirdiğin dosyalar YOK.\n"
                              "Linkler yalnız site adıyla duruyor. Göndermeden önce açıp bakabilirsin.\n"
                              f"Veri klasörü: {app_data_dir()}\n")
    return path


def crash_tail(limit=1800) -> str:
    """The end of crash.log (where the program died last), with the user's folder name left out; "" if none."""
    try:
        with open(crash_path(), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return ""
    home = os.path.expanduser("~")
    return hide_links(text.replace(home, "~")).strip()[-limit:]


def issue_url(facts_text: str, zip_name: str) -> str:
    """The new issue page with the versions written in (the user adds what happened and drops the zip)."""
    first = facts_text.splitlines()
    body = ("**Ne oldu?** (adım adım: ne yaptın, ne bekledin, ne oldu)\n\n\n\n"
            f"**Rapor:** masaüstündeki `{zip_name}` dosyasını buraya sürükleyip bırak.\n\n"
            "```\n" + "\n".join(first[:12]) + "\n```\n")
    crash = crash_tail()
    if crash:
        body += "\n**Çökme kaydı** (crash.log'un sonu):\n```\n" + crash + "\n```\n"
    return f"{brand.CONTACT_URL}?title={quote('Sorun: ')}&body={quote(body)}"
