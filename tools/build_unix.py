"""Builds DISO for Linux or macOS (run it on that system; GitHub Actions does: .github/workflows/unix.yml).

    python tools/build_unix.py              the program, FFmpeg and Deno inside it, and the setup files:
        Linux  dist/DISO-<version>-linux-<arch>.deb       Debian / Ubuntu / Mint ... (double-click or apt install)
               dist/DISO-<version>-linux-<arch>.tar.gz    any distribution: unpack, run ./install.sh
        macOS  dist/DISO-<version>-macos-<arch>.dmg       drag DISO into Applications
    python tools/build_unix.py --skip-app   only the setup files, from the program built before

FFmpeg and Deno are downloaded once into build/cache and checked against the SHA-256 their publishers give.
"""
import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MAC = sys.platform == "darwin"
ARCH = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
CACHE = os.path.join(ROOT, "build", "cache")
WORK = os.path.join(ROOT, "build", "unix")
DIST = os.path.join(ROOT, "dist")
TOOLS = os.path.join(WORK, "tools")            # ffmpeg/ and deno/ that go inside the program
BUNDLE_ID = "com.iso.diso"
DENO_ASSET = f"deno-{'aarch64' if ARCH == 'arm64' else 'x86_64'}-{'apple-darwin' if MAC else 'unknown-linux-gnu'}.zip"
# the newest release, without asking GitHub's API (which allows few questions to a shared build machine)
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/" + DENO_ASSET
SCRIPTS = os.path.join(ROOT, "tools", "unix")  # install.sh, uninstall.sh, the macOS uninstaller


def log(text):
    print(f"[build-unix] {text}", flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _get(url, timeout=120, attempts=4):
    req = urllib.request.Request(url, headers={"User-Agent": "DISO-build"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), r.geturl()
        except Exception as e:  # noqa: BLE001 - one network hiccup must not end the build
            if attempt == attempts:
                raise
            log(f"{url.rsplit('/', 1)[-1]}: {type(e).__name__}, trying again ...")
            time.sleep(3 * attempt)


def _hash_in(text, name=None):
    for line in text.splitlines():
        m = re.search(r"\b([0-9a-fA-F]{64})\b", line)
        if m and (name is None or not line[m.end():].strip() or line[m.end():].strip().lstrip("*") == name):
            return m.group(1).lower()
    raise RuntimeError(f"no SHA-256 for {name or 'the file'}")


def _checked_download(url, sha_url, name, dest):
    """Download url to dest (cached), checked against the hash for `name` in sha_url."""
    if os.path.isfile(dest) and os.path.isfile(dest + ".ok"):
        return dest
    expected = _hash_in(_get(sha_url)[0].decode("utf-8", "replace"), name)
    log(f"downloading {url}")
    data, _ = _get(url, timeout=900)
    with open(dest, "wb") as f:
        f.write(data)
    if sha256(dest) != expected:
        os.remove(dest)
        raise RuntimeError(f"{os.path.basename(dest)} does not match its published SHA-256 (damaged or tampered)")
    open(dest + ".ok", "w").close()
    return dest


def _runs(exe, *args):
    try:
        return subprocess.run([exe, *args], capture_output=True, text=True, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ------------------------------------------------------------------------------- the tools inside
def fetch_ffmpeg() -> str:
    """ffmpeg + ffprobe of this system into build/unix/tools/ffmpeg (the same mirrors the app updates from)."""
    from app import ffmpeg_setup as ff
    target = os.path.join(TOOLS, "ffmpeg")
    if all(_runs(os.path.join(target, t), "-version") for t in ("ffmpeg", "ffprobe")):
        return target
    os.makedirs(target, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)
    archive, sha_url, *more = ff.platform_sources()[0]
    staged = {}
    for i, (part, part_sha) in enumerate([(archive, sha_url)] + list(more[0] if more else [])):
        part, part_sha = ff.resolve(part, part_sha)
        name = os.path.basename(part)
        tag = hashlib.sha1(part.encode()).hexdigest()[:10]
        dest = _checked_download(part, part_sha, name, os.path.join(CACHE, f"{tag}-{name}"))
        staged.update(ff._unpack(dest, target))
    ff._commit(staged, target)
    for t in ("ffmpeg", "ffprobe"):
        if not _runs(os.path.join(target, t), "-version"):
            raise RuntimeError(f"the downloaded {t} does not run here")
    log("FFmpeg: " + subprocess.run([os.path.join(target, "ffmpeg"), "-version"], capture_output=True,
                                    text=True).stdout.splitlines()[0])
    return target


def fetch_deno() -> str:
    target = os.path.join(TOOLS, "deno")
    exe = os.path.join(target, "deno")
    if _runs(exe, "--version"):
        return target
    os.makedirs(CACHE, exist_ok=True)
    dest = os.path.join(CACHE, DENO_ASSET)
    for stale in (dest, dest + ".ok"):                         # "latest" changes: always the newest one
        if os.path.exists(stale):
            os.remove(stale)
    _checked_download(DENO_URL, DENO_URL + ".sha256sum", None, dest)
    os.makedirs(target, exist_ok=True)
    with zipfile.ZipFile(dest) as z, z.open("deno") as src, open(exe, "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.chmod(exe, 0o755)
    if not _runs(exe, "--version"):
        raise RuntimeError("the downloaded deno does not run here")
    log("Deno: " + subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.splitlines()[0])
    return target


# ------------------------------------------------------------------------------- the program
def icns(png, out):
    """The macOS icon, from the PNG (Pillow writes .icns)."""
    from PIL import Image
    img = Image.open(png).convert("RGBA")
    img.save(out, format="ICNS", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)])
    return out


def pyinstaller_command(ffmpeg_dir, deno_dir) -> list:
    import importlib.util
    os.makedirs(WORK, exist_ok=True)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed", "--name", "DISO",
           "--distpath", os.path.join(WORK, "dist"), "--workpath", os.path.join(WORK, "work"),
           "--specpath", WORK, "--contents-directory", "_internal",
           "--collect-all", "customtkinter", "--collect-all", "yt_dlp", "--collect-all", "certifi",
           "--hidden-import", "PIL._tkinter_finder",           # ImageTk needs it outside Windows (the logo, covers)
           "--add-data", f"{os.path.join(ROOT, 'assets')}:assets",
           "--add-data", f"{os.path.join(ROOT, 'browser_extension')}:browser_extension",
           "--add-binary", f"{os.path.join(ffmpeg_dir, 'ffmpeg')}:ffmpeg",
           "--add-binary", f"{os.path.join(ffmpeg_dir, 'ffprobe')}:ffmpeg",
           "--add-binary", f"{os.path.join(deno_dir, 'deno')}:deno"]
    for pkg in ("yt_dlp_ejs", "ytmusicapi", "pygame"):
        if importlib.util.find_spec(pkg):
            cmd += ["--collect-all", pkg]
    if MAC:
        cmd += ["--icon", icns(os.path.join(ROOT, "assets", "icon.png"), os.path.join(WORK, "DISO.icns")),
                "--osx-bundle-identifier", BUNDLE_ID]
    else:
        cmd += ["--hidden-import", "pystray._xorg", "--icon", os.path.join(ROOT, "assets", "icon.png")]
    return cmd + [os.path.join(ROOT, "main.py")]


def build_app() -> str:
    ffmpeg_dir, deno_dir = fetch_ffmpeg(), fetch_deno()
    cmd = pyinstaller_command(ffmpeg_dir, deno_dir)
    log(" ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)
    app = app_path()
    if MAC:
        _fill_info_plist(app)
    return app


def app_path() -> str:
    return os.path.join(WORK, "dist", "DISO.app" if MAC else "DISO")


def _fill_info_plist(app):
    from app import brand
    path = os.path.join(app, "Contents", "Info.plist")
    with open(path, "rb") as f:
        info = plistlib.load(f)
    info.update({"CFBundleName": brand.NAME, "CFBundleDisplayName": brand.NAME,
                 "CFBundleShortVersionString": brand.VERSION, "CFBundleVersion": brand.VERSION,
                 "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "11.0",
                 "NSHumanReadableCopyright": f"© {brand.PUBLISHER}", "LSApplicationCategoryType":
                 "public.app-category.utilities"})
    with open(path, "wb") as f:
        plistlib.dump(info, f)
    # the Info.plist changed after PyInstaller signed the bundle: sign it again (ad hoc: no Apple account)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", app], check=True)


# ------------------------------------------------------------------------------- setup files
def base_name() -> str:
    from app import brand
    return f"DISO-{brand.VERSION}-{brand.CHANNEL}-{'macos' if MAC else 'linux'}-{ARCH}"


def _desktop_entry(exec_path, icon) -> str:
    return ("[Desktop Entry]\nType=Application\nName=DISO\nGenericName=Download manager\n"
            "GenericName[tr]=İndirme yöneticisi\nComment=Download files, videos and music\n"
            "Comment[tr]=Dosya, video ve müzik indir\n"
            f"Exec={exec_path} %U\nIcon={icon}\nTerminal=false\nCategories=Network;FileTransfer;AudioVideo;\n"
            "StartupWMClass=DISO\n")


def make_tar(app) -> str:
    """Any Linux: DISO-…-linux-x86_64.tar.gz with the program and install.sh (installs for this user)."""
    name = base_name()
    stage = os.path.join(WORK, "tar", name)
    shutil.rmtree(os.path.dirname(stage), ignore_errors=True)
    os.makedirs(stage)
    shutil.copytree(app, os.path.join(stage, "DISO"), symlinks=True)
    shutil.copyfile(os.path.join(ROOT, "assets", "icon.png"), os.path.join(stage, "DISO", "diso.png"))
    for script in ("install.sh", "uninstall.sh"):
        dest = os.path.join(stage, script if script == "install.sh" else os.path.join("DISO", script))
        shutil.copyfile(os.path.join(SCRIPTS, script), dest)
        os.chmod(dest, 0o755)
    for doc in ("README.md", "README.tr.md", "LICENSE"):
        shutil.copyfile(os.path.join(ROOT, doc), os.path.join(stage, doc))
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, name + ".tar.gz")
    with tarfile.open(out, "w:gz") as tf:
        tf.add(stage, arcname=name)
    return out


def make_deb(app) -> str:
    """Debian / Ubuntu: /opt/diso, /usr/bin/diso, the menu entry, the icon and the browsers' host files."""
    from app import brand, native_host
    stage = os.path.join(WORK, "deb", "root")
    shutil.rmtree(os.path.dirname(stage), ignore_errors=True)
    shutil.copytree(app, os.path.join(stage, "opt", "diso"), symlinks=True)
    os.makedirs(os.path.join(stage, "usr", "bin"))
    os.symlink("/opt/diso/DISO", os.path.join(stage, "usr", "bin", "diso"))
    apps = os.path.join(stage, "usr", "share", "applications")
    os.makedirs(apps)
    with open(os.path.join(apps, "diso.desktop"), "w", encoding="utf-8") as f:
        f.write(_desktop_entry("/opt/diso/DISO", "diso"))
    icons = os.path.join(stage, "usr", "share", "icons", "hicolor", "256x256", "apps")
    os.makedirs(icons)
    from PIL import Image
    Image.open(os.path.join(ROOT, "assets", "icon.png")).convert("RGBA").resize((256, 256)).save(
        os.path.join(icons, "diso.png"))
    # every user's browsers can start DISO from the first moment (DISO also writes its own per user)
    for folder, firefox in (("etc/opt/chrome/native-messaging-hosts", False), ("etc/chromium/native-messaging-hosts", False),
                            ("etc/opt/edge/native-messaging-hosts", False),
                            ("etc/opt/brave.com/brave/native-messaging-hosts", False),
                            ("usr/lib/mozilla/native-messaging-hosts", True)):
        os.makedirs(os.path.join(stage, folder), exist_ok=True)
        with open(os.path.join(stage, folder, native_host.HOST_NAME + ".json"), "w", encoding="utf-8") as f:
            json.dump(native_host.host_manifest("/opt/diso/DISO", firefox), f, indent=2)
    docs = os.path.join(stage, "usr", "share", "doc", "diso")
    os.makedirs(docs)
    shutil.copyfile(os.path.join(ROOT, "LICENSE"), os.path.join(docs, "copyright"))
    size = sum(os.path.getsize(os.path.join(d, n)) for d, _, names in os.walk(stage) for n in names
               if not os.path.islink(os.path.join(d, n))) // 1024
    control = os.path.join(stage, "DEBIAN")
    os.makedirs(control)
    arch = "arm64" if ARCH == "arm64" else "amd64"
    with open(os.path.join(control, "control"), "w", encoding="utf-8") as f:
        f.write(f"Package: diso\nVersion: {brand.VERSION}~{brand.CHANNEL}\nArchitecture: {arch}\n"
                f"Maintainer: {brand.PUBLISHER} <noreply@github.com>\nInstalled-Size: {size}\n"
                "Section: net\nPriority: optional\n"
                f"Homepage: {brand.HOME_URL}\n"
                "Description: DISO - download manager\n"
                " Fast downloads in parts, videos and music from YouTube and other sites,\n"
                " a music player and a browser extension. Comes with FFmpeg and Deno.\n")
    with open(os.path.join(control, "postinst"), "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\nset -e\ncommand -v update-desktop-database >/dev/null 2>&1 && "
                "update-desktop-database -q /usr/share/applications || true\n"
                "command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor "
                "|| true\nexit 0\n")
    os.chmod(os.path.join(control, "postinst"), 0o755)
    for d, dirs, names in os.walk(stage):
        for n in dirs:
            os.chmod(os.path.join(d, n), 0o755)
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, base_name() + ".deb")
    subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", stage, out], check=True)
    return out


def make_dmg(app) -> str:
    """macOS: a disk image with DISO.app, a link to Applications and the uninstaller."""
    from app import brand
    stage = os.path.join(WORK, "dmg", "DISO")
    shutil.rmtree(os.path.dirname(stage), ignore_errors=True)
    os.makedirs(stage)
    subprocess.run(["ditto", app, os.path.join(stage, "DISO.app")], check=True)       # keeps the signature
    os.symlink("/Applications", os.path.join(stage, "Applications"))
    uninstaller = os.path.join(stage, "Uninstall DISO.command")
    shutil.copyfile(os.path.join(SCRIPTS, "uninstall_macos.command"), uninstaller)
    os.chmod(uninstaller, 0o755)
    shutil.copyfile(os.path.join(SCRIPTS, "READ_ME_macos.txt"), os.path.join(stage, "READ ME - BENİ OKU.txt"))
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, base_name() + ".dmg")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run(["hdiutil", "create", "-volname", f"DISO {brand.VERSION_LABEL}", "-srcfolder", stage, "-ov",
                    "-format", "UDZO", "-fs", "HFS+", out], check=True)
    return out


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-app", action="store_true")
    args = ap.parse_args(argv)
    if sys.platform.startswith("win"):
        log("this builds for Linux / macOS; on Windows use tools/build_installer.py")
        return 2
    app = app_path() if args.skip_app else build_app()
    outs = [make_dmg(app)] if MAC else [make_deb(app), make_tar(app)]
    for out in outs:
        log(f"{out}  {os.path.getsize(out) / 1e6:.1f} MB  sha256 {sha256(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
