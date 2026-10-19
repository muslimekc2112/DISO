"""Builds dist/DISO-Setup-<version>.exe (e.g. DISO-Setup-0.11.0-beta.exe): one file that installs the program on a PC that has nothing.

What goes into it (the "payload"):
    DISO.exe + _internal/   the program as a folder (tools/build_exe.py --onedir; it carries Python, ffmpeg,
                            yt-dlp ...). A folder, not one exe: it starts at once instead of unpacking itself
                            into %TEMP% on every start
    Uninstall.exe       the remover (built here, small)
    deno.exe            the JavaScript runtime YouTube needs (downloaded once, checked against its published
                        SHA-256, then kept in build/cache)
    browser_extension/  the browser extension (the setup window guides the user to add it to their browsers)

    python tools/build_installer.py              builds everything that is missing or out of date
    python tools/build_installer.py --skip-app   use the existing build/app/DISO folder
    python tools/build_installer.py --no-deno    leave Deno out (YouTube may miss some formats)
    python tools/build_installer.py --deno-zip C:\\path\\deno.zip   use a Deno zip you already have
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from version_info import write_version_file  # noqa: E402

BUILD = os.path.join(ROOT, "build", "installer")
CACHE = os.path.join(ROOT, "build", "cache")
PAYLOAD = os.path.join(ROOT, "build", "payload")
DIST = os.path.join(ROOT, "dist")
APP_DIR = os.path.join(ROOT, "build", "app", "DISO")          # tools/build_exe.py --onedir puts it here
DENO_ASSET = "deno-x86_64-pc-windows-msvc.zip"
DENO_API = "https://api.github.com/repos/denoland/deno/releases/latest"
DENO_URL = "https://github.com/denoland/deno/releases/download/{tag}/" + DENO_ASSET


def setup_name(brand_module) -> str:
    """DISO-Setup-0.10.1-beta : the file name says which version it installs."""
    return f"DISO-Setup-{brand_module.VERSION}-{brand_module.CHANNEL}"


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def log(text):
    print(f"[installer] {text}", flush=True)


# ----------------------------------------------------------------------------------- deno
def _get(url, opener=urllib.request.urlopen, timeout=60, attempts=4, sleep=time.sleep):
    """Download a URL, trying again after a short wait (a build must not die of one network hiccup)."""
    req = urllib.request.Request(url, headers={"User-Agent": "DISO-build"})
    for attempt in range(1, attempts + 1):
        try:
            with opener(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if attempt == attempts:
                raise
            log(f"{url.rsplit('/', 1)[-1]}: {type(e).__name__}, trying again ({attempt}/{attempts - 1}) ...")
            sleep(2 * attempt)


def latest_deno_tag(opener=urllib.request.urlopen):
    return json.loads(_get(DENO_API, opener).decode("utf-8"))["tag_name"]


def parse_sha256sum(text):
    """'<hash> *file' (or '<hash>  file') -> the hash."""
    m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not m:
        raise RuntimeError("the published checksum could not be read")
    return m.group(1).lower()


def fetch_deno(cache=CACHE, tag=None, zip_path=None, opener=urllib.request.urlopen):
    """Path of a checked deno.exe (downloaded into the cache the first time). Returns (exe, version)."""
    os.makedirs(cache, exist_ok=True)
    if zip_path:
        archive, expected = zip_path, None
        tag = tag or "local"
    else:
        try:
            tag = tag or latest_deno_tag(opener)
        except Exception as e:  # noqa: BLE001 - offline or rate limited: use what is cached
            cached = sorted(d for d in os.listdir(cache) if d.startswith("deno-") and os.path.isfile(os.path.join(cache, d, "deno.exe")))
            if not cached:
                raise RuntimeError(f"Deno's version could not be looked up ({e}) and none is cached. "
                                   "Pass --deno-zip, or --no-deno.") from e
            tag = cached[-1][len("deno-"):]
            log(f"offline: using the cached Deno {tag}")
        archive = os.path.join(cache, f"{tag}-{DENO_ASSET}")
        expected = None
    folder = os.path.join(cache, f"deno-{tag}")
    exe = os.path.join(folder, "deno.exe")
    if os.path.isfile(exe) and not zip_path:
        return exe, tag
    if not zip_path:
        log(f"downloading Deno {tag} ...")
        expected = parse_sha256sum(_get(DENO_URL.format(tag=tag) + ".sha256sum", opener).decode("utf-8", "replace"))
        data = _get(DENO_URL.format(tag=tag), opener, timeout=600)
        with open(archive, "wb") as f:
            f.write(data)
    if expected and sha256(archive) != expected:
        os.remove(archive)
        raise RuntimeError("the Deno download does not match its published SHA-256 (damaged or tampered); not used")
    os.makedirs(folder, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        names = [n for n in z.namelist() if n.lower().endswith("deno.exe")]
        if not names:
            raise RuntimeError("the Deno archive has no deno.exe")
        with z.open(names[0]) as src, open(exe, "wb") as dst:
            shutil.copyfileobj(src, dst)
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60, creationflags=0x08000000)
        runs = out.returncode == 0 and "deno" in out.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        runs = False
    if not runs:
        shutil.rmtree(folder, ignore_errors=True)                  # a broken file must not stay in the cache
        if not zip_path and os.path.exists(archive):
            os.remove(archive)
        raise RuntimeError("the downloaded deno.exe does not run on this PC")
    return exe, tag


# ----------------------------------------------------------------------------------- payload
def app_entries(app):
    """(name in the payload, source, place in the install folder) for the program: one exe, or a whole
    PyInstaller folder (DISO.exe and _internal/...) whose files keep their places."""
    if os.path.isfile(app):
        return [("DISO.exe", app, "DISO.exe")]
    out = []
    for root, dirs, names in os.walk(app):
        dirs.sort()
        for n in sorted(names):
            src = os.path.join(root, n)
            rel = os.path.relpath(src, app).replace(os.sep, "/")
            out.append(("app/" + rel, src, rel))
    if not any(dest == "DISO.exe" for _, _, dest in out):
        raise RuntimeError(f"{app} has no DISO.exe")
    return out


def extension_entries(folder):
    """The browser extension, installed as the folder browser_extension next to DISO.exe (browsers load it
    from there)."""
    out = []
    for root, dirs, names in os.walk(folder):
        dirs.sort()
        for n in sorted(names):
            src = os.path.join(root, n)
            rel = os.path.relpath(src, folder).replace(os.sep, "/")
            out.append(("ext/" + rel, src, "browser_extension/" + rel))
    return out


def make_payload(folder, app, uninstaller, deno_exe, version, deno_version="", label="", extension=None):
    """Copy the files and write payload.json (name, destination, size, checksum of each).
    `app` is the program: dist/DISO.exe, or the folder build/app/DISO; `extension` the browser extension."""
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    entries = app_entries(app) + [("Uninstall.exe", uninstaller, "Uninstall.exe")]
    if deno_exe:
        entries.append(("deno.exe", deno_exe, "deno/deno.exe"))
    if extension:
        entries += extension_entries(extension)
    files = []
    for name, src, dest in entries:
        path = os.path.join(folder, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copy2(src, path)
        files.append({"name": name, "dest": dest, "size": os.path.getsize(path), "sha256": sha256(path)})
    with open(os.path.join(folder, "payload.json"), "w", encoding="utf-8") as f:
        json.dump({"version": version, "label": label or version, "deno": deno_version, "files": files}, f,
                  ensure_ascii=False, indent=2)
    return files


# ----------------------------------------------------------------------------------- pyinstaller
def pyinstaller(name, script, version_file, extra=(), dist=None):
    dist = dist or os.path.join(BUILD, "dist")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole",
           "--name", name, "--icon", os.path.join(ROOT, "assets", "icon.ico"), "--paths", ROOT,
           "--distpath", dist, "--workpath", os.path.join(BUILD, "work", name), "--specpath", os.path.join(BUILD, "spec"),
           "--version-file", version_file, "--collect-all", "customtkinter",
           "--add-data", os.path.join(ROOT, "assets") + os.pathsep + "assets", *extra, script]
    log("PyInstaller: " + name)
    subprocess.run(cmd, cwd=ROOT, check=True)
    return os.path.join(dist, name + ".exe")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-app", action="store_true")
    ap.add_argument("--no-deno", action="store_true")
    ap.add_argument("--deno-zip")
    args = ap.parse_args(argv)
    from app import __version__, __version_label__, brand

    if not (args.skip_app and os.path.isfile(os.path.join(APP_DIR, "DISO.exe"))):
        log("building the program itself (as a folder) ...")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_exe.py"), "--onedir"], cwd=ROOT, check=True)
    if not os.path.isfile(os.path.join(APP_DIR, "DISO.exe")):
        raise SystemExit("build/app/DISO/DISO.exe is missing")
    deno_exe, deno_version = (None, "") if args.no_deno else fetch_deno(zip_path=args.deno_zip)
    log(f"Deno: {deno_version or 'left out'}")

    versions = os.path.join(BUILD, "versions")
    uninstaller = pyinstaller("Uninstall", os.path.join(ROOT, "hizli_setup", "uninstall_main.py"),
                              write_version_file(os.path.join(versions, "uninstall.txt"), "DISO Kaldırıcı",
                                                 "Uninstall.exe", __version__, __version_label__))
    files = make_payload(PAYLOAD, APP_DIR, uninstaller, deno_exe, __version__, deno_version, __version_label__,
                         extension=os.path.join(ROOT, "browser_extension"))
    log(f"payload: {len(files)} files, {sum(f['size'] for f in files) / 1048576:.0f} MB")
    name = setup_name(brand)
    for old in glob.glob(os.path.join(DIST, "DISO-Kurulum*.exe")) + glob.glob(os.path.join(DIST, "DISO-Setup*.exe")):          # an older version's setup must not be mistaken for this one
        os.remove(old)
    built = pyinstaller(name, os.path.join(ROOT, "hizli_setup", "setup_main.py"),
                        write_version_file(os.path.join(versions, "setup.txt"), "DISO Setup",
                                           name + ".exe", __version__, __version_label__),
                        extra=("--add-data", PAYLOAD + os.pathsep + "payload"), dist=DIST)
    log(f"ready: {built}  ({os.path.getsize(built) / 1048576:.0f} MB)  sha256 {sha256(built)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
