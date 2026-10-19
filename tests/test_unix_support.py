"""DISO on macOS and Linux: the music player (ffmpeg + SDL), where the data and the tools go, the FFmpeg
mirrors, the browsers' native host files, starting at log-in, finding the browsers, the language, the
notifications, and the setup scripts. Most of it runs on Windows too (the system is passed in)."""
import io
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile

import pytest

from app import extension_setup, ffmpeg_setup as ff, i18n, native_host, notify, player, startup, utils

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS = sys.platform.startswith("win")


# ------------------------------------------------------------------------------- the music player
def _sdl_or_skip():
    pytest.importorskip("pygame")
    if not utils.find_ffmpeg():
        pytest.skip("needs ffmpeg")
    os.environ["SDL_AUDIODRIVER"] = "dummy"          # no sound comes out of the tests
    from app import sdl_player
    try:
        return sdl_player.SdlBackend
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no SDL: {e}")


@pytest.fixture(scope="module")
def song(tmp_path_factory):
    if not utils.find_ffmpeg():
        pytest.skip("needs ffmpeg")
    path = str(tmp_path_factory.mktemp("sdl") / "song.opus")       # Opus: what MCI cannot play
    subprocess.run([utils.find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=duration=2",
                    "-c:a", "libopus", path], check=True, **utils.subprocess_flags())
    return path


def _wait(cond, timeout=6):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.02)
    return cond()


def test_the_sdl_player_plays_pauses_seeks_and_ends(song):
    backend = _sdl_or_skip()()
    try:
        assert backend.load(song) and 1900 < backend.length_ms() < 2200
        assert backend.position_ms() == 0 and not backend.finished()
        backend.set_volume(40)
        backend.play()
        assert _wait(lambda: backend.position_ms() > 300) and backend.is_playing()
        backend.pause()
        held = backend.position_ms()
        time.sleep(0.3)
        assert backend.position_ms() == held and not backend.finished()
        backend.resume()
        assert _wait(lambda: backend.position_ms() > held + 100)
        backend.seek(1700)
        assert 1650 <= backend.position_ms() <= 2000
        assert _wait(backend.finished, 4) and backend.position_ms() == backend.length_ms()
        backend.play()                                          # from the start again, as MCI does at the end
        assert _wait(lambda: 0 < backend.position_ms() < 1500)
        backend.stop()
        assert backend.position_ms() == 0 and not backend.finished()
    finally:
        backend.close()


def test_two_sdl_players_sound_at_once_and_a_file_without_sound_is_refused(song, tmp_path):
    cls = _sdl_or_skip()
    a, b = cls(), cls()
    try:
        assert a.load(song) and b.load(song)
        a.play()
        b.play()
        assert _wait(lambda: a.position_ms() > 200 and b.position_ms() > 200)
        text = tmp_path / "x.txt"
        text.write_text("not a song")
        assert not a.load(str(text)) and a.last_error
        assert a.position_ms() == 0 and a.length_ms() == 0
        a.play()                                                # nothing loaded: nothing happens
        assert not a.is_playing()
    finally:
        a.close()
        b.close()


def test_the_sdl_player_drives_the_controller_to_the_next_song(song):
    cls = _sdl_or_skip()
    c = player.Controller(cls(), spare=cls())
    c.set_tracks([{"path": song, "title": "a"}, {"path": song, "title": "b"}])
    c.play_index(0)
    assert c.state == "playing"
    assert _wait(lambda: (c.tick(), c.index)[1] == 1, 8)
    c.stop()


def test_each_system_gets_its_own_player(monkeypatch):
    made = []
    monkeypatch.setattr(player, "MciBackend", lambda alias: made.append(("mci", alias)))
    monkeypatch.setattr(player.sys, "platform", "win32")
    player.new_backend("x")
    assert made == [("mci", "x")] and player.needs_playable_copies()
    import app.sdl_player as sdl
    monkeypatch.setattr(sdl, "SdlBackend", lambda alias: made.append(("sdl", alias)))
    for system in ("linux", "darwin"):
        monkeypatch.setattr(player.sys, "platform", system)
        player.new_backend("y")
        assert not player.needs_playable_copies()
    assert made[1:] == [("sdl", "y"), ("sdl", "y")]


# ------------------------------------------------------------------------------- data and tools
def test_the_data_folder_of_each_system(monkeypatch, tmp_path):
    monkeypatch.setattr(utils.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(utils, "MAC", True)
    monkeypatch.setattr(utils, "WINDOWS", False)
    assert utils.local_appdata() == tmp_path / "Library" / "Application Support"
    monkeypatch.setattr(utils, "MAC", False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert utils.local_appdata() == tmp_path / ".local" / "share"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert utils.local_appdata() == tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", "relative/is/ignored")
    assert utils.local_appdata() == tmp_path / ".local" / "share"


def test_ffmpeg_comes_from_a_mirror_of_each_system():
    win = ff.platform_sources("windows", "AMD64")
    assert "gyan.dev" in win[0][0] and "win64" in win[1][0]
    linux, arm = ff.platform_sources("linux", "x86_64"), ff.platform_sources("linux", "aarch64")
    assert linux[0][0].endswith("linux64-gpl.tar.xz") and arm[0][0].endswith("linuxarm64-gpl.tar.xz")
    assert linux[0][1].endswith("checksums.sha256")
    mac = ff.platform_sources("macos", "arm64")
    assert mac[0][0].endswith("/macos/arm64/release/ffmpeg.zip") and mac[0][1] == ff.BESIDE
    assert mac[0][2] == [(mac[0][0].replace("ffmpeg.zip", "ffprobe.zip"), ff.BESIDE)]
    assert "/macos/amd64/" in ff.platform_sources("macos", "x86_64")[0][0]


def test_a_mirror_whose_latest_link_redirects_gives_the_checksum_of_that_build(server):
    data = b"a build" * 100
    archive = server.add(data, ".zip", name="ffmpeg.zip")
    import hashlib
    server.add(f"{hashlib.sha256(data).hexdigest()}  ffmpeg.zip\n".encode(), ".sha256", name="ffmpeg.zip.sha256")
    url = server.url("f", archive)
    assert ff.resolve(url, "https://elsewhere/sums") == (url, "https://elsewhere/sums")
    assert ff.resolve(url, ff.BESIDE) == (url, url + ".sha256")
    assert ff.fetch_expected_sha256(url, ff.BESIDE) == hashlib.sha256(data).hexdigest()


def _tar_xz(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_ffmpeg_comes_out_of_a_linux_tar_and_a_bare_mac_zip(tmp_path):
    ffmpeg, ffprobe = ff.TOOLS
    tar = tmp_path / "linux.tar.xz"
    tar.write_bytes(_tar_xz({f"ffmpeg-master/bin/{ffmpeg}": b"F", f"ffmpeg-master/bin/{ffprobe}": b"P",
                             f"ffmpeg-master/doc/{ffmpeg}": b"not this one"}))
    out = tmp_path / "out"
    out.mkdir()
    ff._extract(str(tar), str(out))
    assert (out / ffmpeg).read_bytes() == b"F" and (out / ffprobe).read_bytes() == b"P"
    assert sorted(os.listdir(out)) == sorted([ffmpeg, ffprobe])
    if not WINDOWS:
        assert os.access(out / ffmpeg, os.X_OK)
    flat = tmp_path / "ffprobe.zip"                        # macOS: one program per zip, at its top
    with zipfile.ZipFile(flat, "w") as z:
        z.writestr(ffprobe, b"P2")
    staged = ff._unpack(str(flat), str(out))
    assert list(staged) == [ffprobe]
    with pytest.raises(RuntimeError):                      # ffprobe alone is not an FFmpeg
        ff._commit(staged, str(out))
    assert (out / ffprobe).read_bytes() == b"P" and not os.path.exists(staged[ffprobe])


# ------------------------------------------------------------------------------- native host files
def test_the_native_host_folders_of_macos_and_linux(tmp_path):
    home = str(tmp_path)
    mac = native_host.host_dirs(home, mac=True)
    support = os.path.join(home, "Library", "Application Support")
    assert (os.path.join(support, "Google", "Chrome"), os.path.join(support, "Google", "Chrome", "NativeMessagingHosts"),
            False) in mac
    assert (os.path.join(support, "Mozilla"), os.path.join(support, "Mozilla", "NativeMessagingHosts"), True) in mac
    linux = native_host.host_dirs(home, mac=False, environ={})
    assert (os.path.join(home, ".config", "google-chrome"),
            os.path.join(home, ".config", "google-chrome", "NativeMessagingHosts"), False) in linux
    assert (os.path.join(home, ".mozilla"), os.path.join(home, ".mozilla", "native-messaging-hosts"), True) in linux
    assert native_host.host_dirs(home, mac=False, environ={"XDG_CONFIG_HOME": str(tmp_path / "c")})[0][0] == \
        str(tmp_path / "c" / "google-chrome")


def test_native_host_files_go_only_to_browsers_that_are_there_and_go_away_again(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    home = tmp_path
    (home / ".config" / "google-chrome").mkdir(parents=True)
    (home / ".mozilla").mkdir()
    exe = str(tmp_path / "opt" / "DISO" / "DISO")
    written = native_host.register_files(exe, home=str(home), mac=False)
    chrome = home / ".config" / "google-chrome" / "NativeMessagingHosts" / "com.iso.diso.json"
    firefox = home / ".mozilla" / "native-messaging-hosts" / "com.iso.diso.json"
    assert sorted(written) == sorted([str(chrome), str(firefox)])
    assert not (home / ".config" / "chromium").exists()               # no folders for browsers that are not there
    assert json.loads(chrome.read_text())["allowed_origins"] == [f"chrome-extension://{native_host.EXTENSION_ID}/"]
    assert json.loads(firefox.read_text())["allowed_extensions"] == [native_host.FIREFOX_ID]
    assert json.loads(chrome.read_text())["path"] == exe
    assert native_host.unregister_files(home=str(home), mac=False, inside=str(tmp_path / "elsewhere")) == []
    assert sorted(native_host.unregister_files(home=str(home), mac=False, inside=str(tmp_path / "opt"))) == \
        sorted(written)
    assert not chrome.exists() and not firefox.exists()


def test_from_source_the_browsers_start_a_small_script(tmp_path, monkeypatch):
    target = native_host._source_script(str(tmp_path), ["/usr/bin/python3", "/src/main.py"])
    text = open(target, encoding="utf-8").read()
    assert text.startswith("#!/bin/sh\n") and 'exec "/usr/bin/python3" "/src/main.py" "$@"' in text
    if not WINDOWS:
        assert os.access(target, os.X_OK)


@pytest.mark.skipif(WINDOWS, reason="macOS / Linux")
def test_the_app_registers_its_host_files_at_start(tmp_path, monkeypatch, isolated_home):
    monkeypatch.delenv("DISO_NO_NATIVE_HOST")
    monkeypatch.setattr(native_host, "app_command", lambda: ["/opt/diso/DISO"])
    browser = (isolated_home / "Library" / "Application Support" / "Google" / "Chrome" if sys.platform == "darwin"
               else isolated_home / ".config" / "google-chrome")
    browser.mkdir(parents=True)
    written = native_host.register_for_user()
    assert written and json.loads(open(written[0]).read())["path"] == "/opt/diso/DISO"


def test_the_host_starts_the_app_in_a_session_of_its_own(monkeypatch):
    calls = []
    monkeypatch.setattr(native_host.sys, "platform", "linux")
    assert native_host.launch(["/opt/diso/DISO"], popen=lambda cmd, **kw: calls.append((cmd, kw))) is True
    assert calls[0][0] == ["/opt/diso/DISO"] and calls[0][1]["start_new_session"] is True
    assert "creationflags" not in calls[0][1]

    def refuse(cmd, **kw):
        raise OSError("no")
    assert native_host.launch(["/opt/diso/DISO"], popen=refuse) is False


# ------------------------------------------------------------------------------- start at log-in
def test_start_at_log_in_on_macos_and_linux(tmp_path, monkeypatch):
    mac_entry = startup.entry_path(str(tmp_path), mac=True)
    assert mac_entry == os.path.join(str(tmp_path), "Library", "LaunchAgents", "com.iso.diso.plist")
    data = plistlib.loads(startup.entry_text(True, mac=True))
    assert data["Label"] == "com.iso.diso" and data["RunAtLoad"] and data["ProgramArguments"][-1] == "--minimized"
    assert startup.entry_path(str(tmp_path), mac=False, environ={}) == \
        os.path.join(str(tmp_path), ".config", "autostart", "DISO.desktop")
    text = startup.entry_text(False, mac=False).decode()
    assert text.startswith("[Desktop Entry]") and "Exec=" in text and "--minimized" not in text

    monkeypatch.setattr(startup, "_winreg", lambda: None)
    entry = tmp_path / "autostart" / "DISO.desktop"
    monkeypatch.setattr(startup, "entry_path", lambda: str(entry))
    assert startup.is_enabled() is False
    assert startup.set_enabled(True) is True and startup.is_enabled() and entry.is_file()
    assert startup.set_enabled(False) is True and not entry.exists() and startup.is_enabled() is False
    assert startup.set_enabled(False) is True                 # removing twice is fine


def test_the_windows_command_line_is_unchanged(monkeypatch):
    monkeypatch.setattr(startup.sys, "frozen", True, raising=False)
    monkeypatch.setattr(startup.sys, "executable", r"C:\Program Files\ISO\DISO\DISO.exe")
    assert startup.command() == r'"C:\Program Files\ISO\DISO\DISO.exe" --minimized'
    assert startup.command(False) == r'"C:\Program Files\ISO\DISO\DISO.exe"'


# ------------------------------------------------------------------------------- browsers, language, notices
def test_finding_the_browsers_of_linux_and_macos(tmp_path):
    on_path = {"google-chrome-stable": "/usr/bin/google-chrome-stable", "firefox": "/usr/bin/firefox",
               "chromium-browser": "/usr/bin/chromium-browser"}
    found = extension_setup.find_browsers(system="linux", which=on_path.get)
    assert found == {"chrome": "/usr/bin/google-chrome-stable", "firefox": "/usr/bin/firefox",
                     "chromium": "/usr/bin/chromium-browser"}
    there = {os.path.join("/Applications", extension_setup.MAC_APPS["brave"]),
             os.path.join(str(tmp_path), "Applications", extension_setup.MAC_APPS["edge"])}
    found = extension_setup.find_browsers(system="macos", exists=there.__contains__, home=str(tmp_path))
    assert list(found) == ["edge", "brave"]
    assert found["edge"].startswith(str(tmp_path))


def test_the_folder_opens_in_the_systems_own_file_manager(monkeypatch):
    calls = []
    monkeypatch.setattr(extension_setup.sys, "platform", "linux")
    assert extension_setup.open_for("chrome", "/usr/bin/google-chrome", "/data/ext",
                                    start=lambda exe, args: calls.append((exe, args)))
    assert calls == [("/usr/bin/google-chrome", ["chrome://extensions/"]), ("xdg-open", ["/data/ext"])]
    calls.clear()
    monkeypatch.setattr(extension_setup.sys, "platform", "darwin")
    extension_setup.open_for("firefox", "/Applications/Firefox.app/Contents/MacOS/firefox", "/data/ext",
                             start=lambda exe, args: calls.append((exe, args)))
    assert calls[1] == ("open", ["/data/ext"])


def test_the_language_of_macos_and_linux():
    assert i18n.system_language({"LANG": "tr_TR.UTF-8"}, mac=False) == "Türkçe"
    assert i18n.system_language({"LANGUAGE": "en_GB:tr", "LANG": "tr_TR.UTF-8"}, mac=False) == "English"
    assert i18n.system_language({}, mac=False) == "English"
    assert i18n.system_language({}, mac=True, apple_languages='(\n    "tr-TR",\n    "en-US"\n)') == "Türkçe"
    assert i18n.system_language({"LANG": "tr_TR"}, mac=True, apple_languages='(\n    "en-US"\n)') == "English"
    assert i18n.system_language({"LANG": "tr_TR"}, mac=True, apple_languages="") == "Türkçe"


def test_notifications_on_macos_and_linux(monkeypatch):
    cmd = notify.toast_command('Done "x"', "a\\b", system="darwin")
    assert cmd[:2] == ["osascript", "-e"]
    assert cmd[2] == 'display notification "a\\\\b" with title "Done \\"x\\""'
    monkeypatch.setattr(notify.shutil, "which", lambda name: "/usr/bin/notify-send" if name == "notify-send" else None)
    assert notify.toast_command("T", "B", system="linux") == ["notify-send", "--app-name=DISO", "T", "B"]
    monkeypatch.setattr(notify.shutil, "which", lambda name: None)
    assert notify.toast_command("T", "B", system="linux") is None


def test_an_old_libxft_gets_no_colour_fonts(tmp_path):
    from app import ui_common
    env = {}
    assert ui_common.guard_color_emoji(str(tmp_path), version=20306, environ=env) is False and env == {}
    assert ui_common.guard_color_emoji(str(tmp_path), version=20304, environ=env) is True
    conf = open(env["FONTCONFIG_FILE"], encoding="utf-8").read()
    assert "/etc/fonts/fonts.conf" in conf and '<patelt name="color"><bool>true</bool></patelt>' in conf
    if not sys.platform.startswith("linux"):
        assert ui_common.guard_color_emoji() is False          # nothing to do elsewhere


# ------------------------------------------------------------------------------- the setup scripts
SCRIPTS = os.path.join(ROOT, "tools", "unix")


def test_the_scripts_have_unix_line_ends_and_are_valid_sh():
    for name in ("install.sh", "uninstall.sh", "uninstall_macos.command"):
        data = open(os.path.join(SCRIPTS, name), "rb").read()
        assert b"\r\n" not in data and data.startswith(b"#!/bin/sh\n"), name
        if shutil.which("sh") and not WINDOWS:
            assert subprocess.run(["sh", "-n", os.path.join(SCRIPTS, name)]).returncode == 0, name


@pytest.mark.skipif(WINDOWS, reason="the Linux setup script")
def test_install_and_uninstall_for_this_user(tmp_path):
    pack = tmp_path / "DISO-x-linux"
    program = pack / "DISO"
    program.mkdir(parents=True)
    exe = program / "DISO"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    (program / "diso.png").write_bytes(b"png")
    shutil.copy(os.path.join(SCRIPTS, "install.sh"), pack / "install.sh")
    shutil.copy(os.path.join(SCRIPTS, "uninstall.sh"), program / "uninstall.sh")
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": os.environ["PATH"], "LANG": "tr_TR.UTF-8"}
    r = subprocess.run(["sh", str(pack / "install.sh"), "--yes", "--no-start"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    dest = home / ".local" / "opt" / "DISO"
    assert (dest / "DISO").is_file() and os.access(dest / "uninstall.sh", os.X_OK)
    assert os.readlink(home / ".local" / "bin" / "diso") == str(dest / "DISO")
    desktop = (home / ".local" / "share" / "applications" / "diso.desktop").read_text()
    assert f'Exec="{dest}/DISO" %U' in desktop and "Icon=diso" in desktop
    assert (home / ".local" / "share" / "applications" / "diso-uninstall.desktop").is_file()
    assert json.loads((home / ".local" / "share" / "DISO" / "settings.json").read_text()) == {"language": "Türkçe"}
    assert "kuruldu" in r.stdout

    chrome = home / ".config" / "google-chrome" / "NativeMessagingHosts"
    chrome.mkdir(parents=True)
    (chrome / "com.iso.diso.json").write_text(json.dumps({"path": str(dest / "DISO")}))
    other = home / ".config" / "chromium" / "NativeMessagingHosts"
    other.mkdir(parents=True)
    (other / "com.iso.diso.json").write_text(json.dumps({"path": "/opt/diso/DISO"}))    # the .deb copy's: kept
    r = subprocess.run(["sh", str(dest / "uninstall.sh"), "--yes"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not dest.exists() and not (home / ".local" / "bin" / "diso").exists()
    assert not (home / ".local" / "share" / "applications" / "diso.desktop").exists()
    assert not (chrome / "com.iso.diso.json").exists() and (other / "com.iso.diso.json").exists()
    assert (home / ".local" / "share" / "DISO" / "settings.json").exists()           # the records stay unless asked
    assert "Kayıtların duruyor" in r.stdout

    subprocess.run(["sh", str(pack / "install.sh"), "--yes", "--no-start", "--lang=en"], env=env, check=True,
                   capture_output=True)
    r = subprocess.run(["sh", str(dest / "uninstall.sh"), "--yes", "--data"], env=env, capture_output=True, text=True)
    assert r.returncode == 0 and not (home / ".local" / "share" / "DISO").exists()
    assert "records are removed" in r.stdout
