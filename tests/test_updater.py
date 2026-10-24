import hashlib
import importlib
import io
import json
import os
import sys
import threading
import zipfile

import pytest

from app import ffmpeg_setup as ff
from app import updater
from app.utils import app_data_dir, user_tools_dir
from test_ffmpeg_setup import make_zip, mirror


# ------------------------------------------------------------------------- helpers
def pkg_dir():
    return updater.packages_dir()


def write_pkg(root, module, body="VALUE = 1\n"):
    d = os.path.join(root, module)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "__init__.py"), "w", encoding="utf-8").write(body)
    open(os.path.join(d, "sub.py"), "w", encoding="utf-8").write("NAME = 'sub of ' + __name__\n")
    return d


def write_manifest(data):
    json.dump(data, open(os.path.join(pkg_dir(), "manifest.json"), "w"))


def read_manifest():
    return json.load(open(os.path.join(pkg_dir(), "manifest.json")))


def make_wheel(module, value):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{module}/__init__.py", f"VALUE = {value}\n")
        z.writestr(f"{module}/sub.py", "NAME = 'sub'\n")
        z.writestr(f"{module}-{value}.dist-info/METADATA", "Name: x\n")
    return buf.getvalue()


def forget(monkeypatch, *prefixes):
    """Make sure the named modules are not already imported (restored after the test)."""
    for name in list(sys.modules):
        if name.startswith(prefixes):
            monkeypatch.delitem(sys.modules, name, raising=False)


@pytest.fixture
def fake_pypi(server, monkeypatch):
    """yt-dlp is replaced by a tiny package 'fakepkg_x'; the server plays PyPI."""
    monkeypatch.setattr(updater, "PYPI_URL", server.pypi_url)
    monkeypatch.setattr(updater, "PACKAGES", {"yt-dlp": "fakepkg_x"})
    monkeypatch.setattr(updater, "bundled_version", lambda pkg: "1.0")
    monkeypatch.setattr(updater, "find_ffmpeg", lambda: None)

    def publish(version, value=None, sha=None, wheel=True):
        value = value if value is not None else version.split(".")[0]
        data = make_wheel("fakepkg_x", value)
        name = f"fakepkg_x-{version}-py3-none-any.whl"
        server.add(data, name=name)
        files = [{"packagetype": "bdist_wheel", "filename": name, "url": server.url("f", name),
                  "digests": {"sha256": sha or hashlib.sha256(data).hexdigest()}}]
        if not wheel:
            files = [{"packagetype": "sdist", "filename": "x.tar.gz", "url": "", "digests": {"sha256": ""}}]
        server.state.pypi["yt-dlp"] = {"info": {"version": version}, "urls": files}
        return name

    return publish


def installed_value():
    text = open(os.path.join(pkg_dir(), "fakepkg_x", "__init__.py")).read()
    return int(text.split("=")[1])


# --------------------------------------------------------------------------- versions
def test_version_comparison_is_numeric_not_textual():
    k = updater.version_key
    assert k("2026.8.19") == k("2026.08.19")
    assert k("0.10.0") > k("0.8.0")
    assert k("2026.8.19") > k("2025.11.12")
    assert k("") < k("0.0.1")


# ------------------------------------------------------------------------- PyPI answer
def test_fetch_release_picks_the_universal_wheel_and_its_digest(fake_pypi):
    fake_pypi("2.0")
    info = updater.fetch_release("yt-dlp")
    assert info["version"] == "2.0" and info["filename"].endswith("-py3-none-any.whl")
    assert len(info["sha256"]) == 64


def test_fetch_release_without_a_usable_wheel_is_an_error(fake_pypi):
    fake_pypi("2.0", wheel=False)
    with pytest.raises(Exception, match="uygun paket"):
        updater.fetch_release("yt-dlp")


# --------------------------------------------------------------------------- updating
def test_update_downloads_verifies_installs_and_the_new_code_is_importable(fake_pypi, server):
    fake_pypi("2.0")
    u = updater.Updater()
    assert u.run(install=True) is True
    comp = u.components["yt-dlp"]
    assert (comp.status, comp.installed, comp.latest) == ("done", "2.0", "2.0")
    assert read_manifest()["yt-dlp"] == "2.0"
    assert updater.notices.get_nowait().startswith("yt-dlp 2.0")
    assert updater.ready.is_set()
    fakepkg = importlib.import_module("fakepkg_x")      # the import hook finds packages/
    assert fakepkg.VALUE == 2 and os.path.dirname(fakepkg.__file__).startswith(pkg_dir())
    assert importlib.import_module("fakepkg_x.sub").NAME == "sub"
    assert not os.path.exists(os.path.join(app_data_dir(), "update-tmp"))  # temp wheel removed


def test_checking_without_installing_changes_nothing(fake_pypi):
    fake_pypi("2.0")
    u = updater.Updater()
    u.run(install=False)
    comp = u.components["yt-dlp"]
    assert comp.status == "available" and comp.latest == "2.0"
    assert not os.path.exists(os.path.join(pkg_dir(), "fakepkg_x"))


def test_nothing_is_downloaded_when_already_current(fake_pypi, server):
    name = fake_pypi("1.0")                 # same as the "bundled" version
    u = updater.Updater()
    u.run(install=True)
    assert u.components["yt-dlp"].status == "current"
    assert server.hits(name) == 0


def test_a_wheel_with_the_wrong_checksum_is_refused(fake_pypi):
    fake_pypi("2.0", sha="0" * 64)
    u = updater.Updater()
    u.run(install=True)
    comp = u.components["yt-dlp"]
    assert comp.status == "error" and "SHA-256" in comp.message
    assert not os.path.exists(os.path.join(pkg_dir(), "fakepkg_x"))
    assert updater.ready.is_set()           # yt-dlp must never stay blocked after a failure


def test_pypi_unreachable_is_reported_and_does_not_block_startup(monkeypatch, fake_pypi):
    monkeypatch.setattr(updater, "PYPI_URL", "http://127.0.0.1:9/{}/json")
    u = updater.Updater()
    updater._started = True
    u._startup()
    assert u.components["yt-dlp"].status == "error" and "ulaşamadım" in u.components["yt-dlp"].message
    assert updater.ready.is_set()


def test_startup_sets_ready_even_if_the_check_crashes(monkeypatch):
    u = updater.Updater()
    monkeypatch.setattr(u, "run", lambda install=True: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        u._startup()
    assert updater.ready.is_set()


def test_only_one_check_runs_at_a_time(fake_pypi):
    fake_pypi("2.0")
    u = updater.Updater()
    assert u._lock.acquire(blocking=False)
    try:
        assert u.run(install=True) is False
    finally:
        u._lock.release()


def test_wait_ready_does_not_block_before_startup_and_waits_after(monkeypatch):
    import time
    t0 = time.time()
    updater.wait_ready(timeout=5)                       # nothing started: returns at once
    assert time.time() - t0 < 0.5
    updater._started = True
    threading.Timer(0.3, updater.ready.set).start()
    t0 = time.time()
    updater.wait_ready(timeout=5)
    assert 0.2 < time.time() - t0 < 3


# ------------------------------------------------------------------ backup and rollback
def test_a_second_update_keeps_the_first_copy_for_rollback(fake_pypi):
    fake_pypi("2.0")
    updater.Updater().run(install=True)
    fake_pypi("3.0")
    updater.Updater().run(install=True)
    assert installed_value() == 3
    assert read_manifest()["_previous"] == {"yt-dlp": "2.0"}
    backup = open(os.path.join(pkg_dir(), ".previous-fakepkg_x", "__init__.py")).read()
    assert backup.strip() == "VALUE = 2"


def test_rollback_restores_the_previous_copy_and_remembers_the_bad_version(fake_pypi):
    fake_pypi("2.0")
    updater.Updater().run(install=True)
    fake_pypi("3.0")
    u = updater.Updater()
    u.run(install=True)
    restored = updater.rollback("yt-dlp", "3.0", "kırık")
    assert restored == "2.0" and installed_value() == 2
    m = read_manifest()
    assert m["yt-dlp"] == "2.0" and m["_bad"] == {"yt-dlp": "3.0"}
    texts = [updater.notices.get_nowait() for _ in range(updater.notices.qsize())]
    assert any("3.0 çalışmadı" in t and "2.0 sürümüne" in t for t in texts)
    assert updater._active["yt-dlp"] == "2.0"
    comp = u.components["yt-dlp"]
    assert comp.status == "error" and "geri alındı" in comp.message and comp.installed == "2.0"


def test_a_version_that_was_rolled_back_is_not_installed_again_but_a_newer_one_is(fake_pypi, server):
    fake_pypi("2.0")
    updater.Updater().run(install=True)
    wheel3 = fake_pypi("3.0")
    updater.Updater().run(install=True)
    updater.rollback("yt-dlp", "3.0", "kırık")
    hits = server.hits(wheel3)
    u = updater.Updater()
    u.run(install=True)
    assert server.hits(wheel3) == hits                  # not downloaded again
    assert u.components["yt-dlp"].status == "current"
    assert "çalışmadı" in u.components["yt-dlp"].message
    fake_pypi("4.0")
    u.run(install=True)
    assert installed_value() == 4 and u.components["yt-dlp"].status == "done"


def test_rollback_without_a_previous_copy_falls_back_to_the_bundled_one(fake_pypi):
    fake_pypi("2.0")
    updater.Updater().run(install=True)
    assert "fakepkg_x" in updater._overrides
    restored = updater.rollback("yt-dlp", "2.0", "kırık")
    assert restored == ""
    assert not os.path.exists(os.path.join(pkg_dir(), "fakepkg_x"))
    assert "fakepkg_x" not in updater._overrides and "yt-dlp" not in updater._active
    assert "yt-dlp" not in read_manifest()


# ---------------------------------------------------------------------- import hook
def test_a_newer_downloaded_copy_wins_over_the_bundled_one(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    write_pkg(str(bundled), "fakepkg_a", "VALUE = 1\n")
    monkeypatch.syspath_prepend(str(bundled))
    forget(monkeypatch, "fakepkg_a")
    write_pkg(pkg_dir(), "fakepkg_a", "VALUE = 2\n")
    write_manifest({"fake-a": "2.0"})
    monkeypatch.setattr(updater, "PACKAGES", {"fake-a": "fakepkg_a"})
    monkeypatch.setattr(updater, "bundled_version", lambda pkg: "1.0")
    updater.activate()
    mod = importlib.import_module("fakepkg_a")
    assert mod.VALUE == 2
    assert importlib.import_module("fakepkg_a.sub").NAME == "sub of fakepkg_a.sub"
    assert sys.meta_path.count(updater._finder) == 1


def test_a_downloaded_copy_older_than_the_bundled_one_is_not_used(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    write_pkg(str(bundled), "fakepkg_b", "VALUE = 1\n")
    monkeypatch.syspath_prepend(str(bundled))
    forget(monkeypatch, "fakepkg_b")
    write_pkg(pkg_dir(), "fakepkg_b", "VALUE = 2\n")
    write_manifest({"fake-b": "1.0"})
    monkeypatch.setattr(updater, "PACKAGES", {"fake-b": "fakepkg_b"})
    monkeypatch.setattr(updater, "bundled_version", lambda pkg: "5.0")   # user upgraded with pip
    updater.activate()
    assert importlib.import_module("fakepkg_b").VALUE == 1
    assert updater._finder is None


def test_activate_ignores_a_manifest_entry_whose_folder_is_gone(monkeypatch):
    write_manifest({"fake-c": "9.0"})
    monkeypatch.setattr(updater, "PACKAGES", {"fake-c": "fakepkg_c"})
    updater.activate()
    assert updater._overrides == {} and updater._finder is None


def test_activate_with_nothing_downloaded_is_harmless():
    updater.activate()
    assert updater._overrides == {}


# ------------------------------------------------------------------- yt-dlp health check
class YtdlpWorld:
    """A fake 'bundled' yt_dlp on sys.path and helpers to plant a downloaded copy."""

    def __init__(self, tmp_path, monkeypatch):
        self.bundled = tmp_path / "bundled"
        working = ("MARK = '{}'\nclass YoutubeDL:\n    def __init__(self, *a, **k): pass\n"
                   "    def close(self): pass\n")
        write_pkg(str(self.bundled), "yt_dlp", working.format("bundled"))
        monkeypatch.syspath_prepend(str(self.bundled))
        forget(monkeypatch, "yt_dlp")
        self.working = working

    def plant(self, version, body, previous=None):
        write_pkg(pkg_dir(), "yt_dlp", body)
        manifest = {"yt-dlp": version}
        if previous:
            write_pkg(os.path.join(pkg_dir(), ".previous-x"), "yt_dlp", previous[1])
            os.replace(os.path.join(pkg_dir(), ".previous-x", "yt_dlp"),
                       os.path.join(pkg_dir(), ".previous-yt_dlp"))
            manifest["_previous"] = {"yt-dlp": previous[0]}
        write_manifest(manifest)
        updater.activate()


@pytest.fixture
def world(tmp_path, monkeypatch):
    return YtdlpWorld(tmp_path, monkeypatch)


def test_a_healthy_downloaded_yt_dlp_is_kept(world):
    world.plant("2099.1.1", world.working.format("downloaded"))
    mod = updater.load_yt_dlp()
    assert mod.MARK == "downloaded" and updater._active == {"yt-dlp": "2099.1.1"}
    assert updater._ytdlp_checked and updater.notices.empty()


def test_a_downloaded_yt_dlp_that_cannot_be_imported_is_rolled_back_to_the_bundled_one(world):
    world.plant("2099.1.1", "raise ImportError('boom')\n")
    mod = updater.load_yt_dlp()
    assert mod.MARK == "bundled" and updater._active == {}
    assert read_manifest()["_bad"] == {"yt-dlp": "2099.1.1"}
    assert "yerleşik" in updater.notices.get_nowait()


def test_a_broken_update_goes_back_to_the_previous_downloaded_copy(world):
    world.plant("2099.2.2", "raise ImportError('boom')\n",
                previous=("2099.1.1", world.working.format("previous")))
    mod = updater.load_yt_dlp()
    assert mod.MARK == "previous" and updater._active == {"yt-dlp": "2099.1.1"}
    assert read_manifest()["yt-dlp"] == "2099.1.1"


def test_a_yt_dlp_that_imports_but_cannot_start_is_rolled_back(world):
    world.plant("2099.1.1", "MARK = 'sick'\nclass YoutubeDL:\n    def __init__(self, *a, **k):\n"
                            "        raise RuntimeError('motor bozuk')\n")
    mod = updater.load_yt_dlp()
    assert mod.MARK == "bundled"


def test_a_broken_yt_dlp_ejs_is_rolled_back_but_yt_dlp_is_kept(world):
    world.plant("2099.1.1", world.working.format("downloaded"))
    write_pkg(pkg_dir(), "yt_dlp_ejs", "raise ImportError('ejs kırık')\n")
    write_manifest({**read_manifest(), "yt-dlp-ejs": "2099.1.1"})
    updater.activate()
    mod = updater.load_yt_dlp()
    assert mod.MARK == "downloaded"
    assert "yt-dlp-ejs" not in updater._active and "yt-dlp" in updater._active
    assert read_manifest()["_bad"] == {"yt-dlp-ejs": "2099.1.1"}


def test_with_nothing_downloaded_a_real_import_error_is_not_swallowed(tmp_path, monkeypatch):
    forget(monkeypatch, "yt_dlp")
    monkeypatch.setattr(sys, "path", [p for p in sys.path if "site-packages" not in p])
    monkeypatch.setitem(sys.modules, "yt_dlp", None)    # makes `import yt_dlp` fail
    with pytest.raises(ImportError):
        updater.load_yt_dlp()


# ---------------------------------------------------------------------------- FFmpeg
@pytest.fixture
def local_ffmpeg(server, monkeypatch):
    """FFmpeg mirror on the test server; the updater believes the tools folder's copy is on PATH."""
    monkeypatch.setattr(updater, "PACKAGES", {})
    state = {"zip": make_zip()}

    def publish():
        state["zip"] = make_zip()
        state["source"] = mirror(server, state["zip"])
        monkeypatch.setattr(ff, "FFMPEG_SOURCES", [state["source"]])
        return hashlib.sha256(state["zip"]).hexdigest()

    publish.state = state
    return publish


def test_ffmpeg_missing_is_reported_and_never_installed_automatically(monkeypatch, local_ffmpeg):
    local_ffmpeg()
    monkeypatch.setattr(updater, "find_ffmpeg", lambda: None)
    u = updater.Updater()
    u.run(install=True)
    assert u.components["ffmpeg"].status == "missing"
    assert not os.path.exists(os.path.join(user_tools_dir(), ff.TOOLS[0]))


def test_the_users_own_ffmpeg_is_never_touched(monkeypatch, tmp_path, local_ffmpeg):
    local_ffmpeg()
    own = tmp_path / ff.TOOLS[0]
    own.write_bytes(b"mine")
    monkeypatch.setattr(updater, "find_ffmpeg", lambda: str(own))
    u = updater.Updater()
    u.run(install=True)
    assert u.components["ffmpeg"].status == "manual"
    assert own.read_bytes() == b"mine"


def test_the_ffmpeg_diso_came_with_is_its_own_and_is_updated_when_the_mirror_has_a_newer_build(
        monkeypatch, tmp_path, local_ffmpeg):
    local_ffmpeg()
    bundled = tmp_path / "program" / "ffmpeg"
    bundled.mkdir(parents=True)
    (bundled / ff.TOOLS[0]).write_bytes(b"came with DISO")
    monkeypatch.setattr(ff, "bundled_ffmpeg_dirs", lambda: [str(bundled)])
    monkeypatch.setattr(ff, "ffmpeg_version", lambda path: "2026-09-24-git" if "program" in str(path) else "new")
    on_path = {"ffmpeg": str(bundled / ff.TOOLS[0])}
    monkeypatch.setattr(updater, "find_ffmpeg", lambda: on_path["ffmpeg"])
    u = updater.Updater()
    u.run(install=True)                                   # first look: as new as the mirror's build
    comp = u.components["ffmpeg"]
    assert comp.status == "current" and comp.installed == "2026-09-24-git" and comp.message == ""
    u.run(install=True)
    assert comp.status == "current"
    new = local_ffmpeg()                                  # later the mirror has a newer build
    u.run(install=False)
    assert comp.status == "available" and "Yeni FFmpeg" in comp.message
    u.run(install=True)
    assert comp.status == "done" and ff.read_info()["sha256"] == new
    assert os.path.isfile(os.path.join(user_tools_dir(), ff.TOOLS[0]))
    assert (bundled / ff.TOOLS[0]).read_bytes() == b"came with DISO"      # the program's files are not touched
    on_path["ffmpeg"] = os.path.join(user_tools_dir(), ff.TOOLS[0])    # the updated one is found first now
    u.run(install=True)
    assert comp.status == "current"


def test_the_updated_ffmpeg_comes_before_the_bundled_one_on_path():
    from app import utils
    dirs = utils.tool_dirs()
    assert dirs[0] == utils.user_tools_dir() and utils.bundled_ffmpeg_dirs()[0] in dirs[1:]


def test_ffmpeg_installed_by_the_app_is_current_when_the_mirror_has_nothing_newer(monkeypatch, server, local_ffmpeg):
    sha = local_ffmpeg()
    ff.ensure_ffmpeg(force=True)
    monkeypatch.setattr(updater, "find_ffmpeg", lambda: os.path.join(user_tools_dir(), ff.TOOLS[0]))
    u = updater.Updater()
    u.run(install=True)
    assert u.components["ffmpeg"].status == "current"
    assert ff.read_info()["sha256"] == sha


def test_a_newer_ffmpeg_build_is_installed_automatically(monkeypatch, local_ffmpeg):
    old = local_ffmpeg()
    ff.ensure_ffmpeg(force=True)
    monkeypatch.setattr(updater, "find_ffmpeg", lambda: os.path.join(user_tools_dir(), ff.TOOLS[0]))
    new = local_ffmpeg()                                  # the mirror now offers a different build
    assert new != old
    u = updater.Updater()
    u.run(install=True)
    assert u.components["ffmpeg"].status == "done"
    assert ff.read_info()["sha256"] == new
    assert "FFmpeg güncellendi" in [updater.notices.get_nowait() for _ in range(updater.notices.qsize())]


def test_check_only_reports_a_newer_ffmpeg_without_installing(monkeypatch, local_ffmpeg):
    old = local_ffmpeg()
    ff.ensure_ffmpeg(force=True)
    monkeypatch.setattr(updater, "find_ffmpeg", lambda: os.path.join(user_tools_dir(), ff.TOOLS[0]))
    local_ffmpeg()
    u = updater.Updater()
    u.run(install=False)
    assert u.components["ffmpeg"].status == "available"
    assert ff.read_info()["sha256"] == old


def test_ffmpeg_is_not_replaced_while_a_job_is_using_it(monkeypatch, local_ffmpeg):
    old = local_ffmpeg()
    ff.ensure_ffmpeg(force=True)
    monkeypatch.setattr(updater, "find_ffmpeg", lambda: os.path.join(user_tools_dir(), ff.TOOLS[0]))
    local_ffmpeg()
    u = updater.Updater()
    u.ffmpeg_busy = lambda: True
    u.run(install=True)
    assert u.components["ffmpeg"].status == "available" and "kullanıyor" in u.components["ffmpeg"].message
    assert ff.read_info()["sha256"] == old


def test_install_ffmpeg_button_installs_when_missing(monkeypatch, local_ffmpeg):
    sha = local_ffmpeg()
    u = updater.Updater()
    assert u.install_ffmpeg() is True
    assert u.components["ffmpeg"].status == "done" and ff.read_info()["sha256"] == sha


def test_failed_ffmpeg_update_is_reported(monkeypatch, server, local_ffmpeg):
    local_ffmpeg()
    monkeypatch.setattr(ff, "FFMPEG_SOURCES", [mirror(server, make_zip(), sha="0" * 64)])
    u = updater.Updater()
    u.install_ffmpeg()
    comp = u.components["ffmpeg"]
    assert comp.status == "error" and "SHA-256" in comp.message


# ------------------------------------------------------------------ downloads never wait for the check
def test_starting_the_updater_never_holds_downloads_back(monkeypatch):
    """The check runs on the network and can be slow: yt-dlp may be imported at once anyway."""
    gate = threading.Event()
    monkeypatch.delenv("HIZLI_NO_UPDATE", raising=False)
    monkeypatch.setattr(updater.Updater, "run", lambda self, install=True: gate.wait(10))
    updater.Updater().start()
    try:
        assert updater.ready.is_set()
        updater.wait_ready(timeout=0.01)                     # returns at once
    finally:
        gate.set()


def test_an_update_found_while_yt_dlp_is_in_use_waits_for_the_next_start(fake_pypi, monkeypatch):
    import types
    fake_pypi("2.0")
    monkeypatch.setitem(sys.modules, "fakepkg_x", types.ModuleType("fakepkg_x"))   # a download imported it
    u = updater.Updater()
    u.run(install=True)
    comp = u.components["yt-dlp"]
    assert comp.status == "available" and "bir dahaki açışında" in comp.message
    assert not os.path.exists(os.path.join(pkg_dir(), "fakepkg_x"))           # its files were not touched
    assert updater.ready.is_set()
    monkeypatch.delitem(sys.modules, "fakepkg_x")
    forget(monkeypatch, "fakepkg_x")
    updater.Updater().run(install=True)                                        # the next start installs it
    assert installed_value() == 2
