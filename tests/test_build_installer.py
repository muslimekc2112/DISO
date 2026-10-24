"""The build script of the installer: the checked Deno download, the payload list, the version tab."""
import hashlib
import io
import json
import os
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_installer as bi  # noqa: E402
import version_info  # noqa: E402


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_net(routes):
    """An opener that answers from a dict {url fragment: bytes} and counts what was asked."""
    asked = []

    def opener(request, timeout=0):
        url = request.full_url
        asked.append(url)
        for fragment, body in routes.items():
            if fragment in url:
                if isinstance(body, Exception):
                    raise body
                return FakeResponse(body)
        raise OSError("no route " + url)

    opener.asked = asked
    return opener


def zip_with(name, data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, data)
    return buf.getvalue()


# ------------------------------------------------------------------------------ small parsers
def test_the_published_checksum_line_is_read_in_both_common_spellings():
    h = "ab" * 32
    assert bi.parse_sha256sum(f"{h} *deno.zip\n") == h and bi.parse_sha256sum(f"{h.upper()}  deno.zip") == h
    with pytest.raises(RuntimeError):
        bi.parse_sha256sum("no hash in here")


def test_a_hiccup_in_the_network_is_retried_but_not_forever():
    calls = []

    def flaky(request, timeout=0):
        calls.append(1)
        if len(calls) < 3:
            raise OSError("timed out")
        return FakeResponse(b"ok")

    assert bi._get("https://x/y", flaky, sleep=lambda s: None) == b"ok" and len(calls) == 3
    calls.clear()

    def dead(request, timeout=0):
        calls.append(1)
        raise OSError("down")

    with pytest.raises(OSError):
        bi._get("https://x/y", dead, attempts=3, sleep=lambda s: None)
    assert len(calls) == 3


def test_the_latest_version_comes_from_the_release_api():
    opener = fake_net({"releases/latest": json.dumps({"tag_name": "v9.8.7"}).encode()})
    assert bi.latest_deno_tag(opener) == "v9.8.7"


def test_the_version_tab_has_the_numbers_and_the_names():
    text = version_info.version_file_text("DISO Kurulumu", "Setup.exe", "1.2.3")
    assert "filevers=(1, 2, 3, 0)" in text and "StringStruct('FileVersion', '1.2.3.0')" in text
    assert "DISO Kurulumu" in text and "OriginalFilename', 'Setup.exe'" in text
    assert version_info.version_tuple("2") == (2, 0, 0, 0) and version_info.version_tuple("1.2.3.4.5") == (1, 2, 3, 4)
    assert version_info.version_tuple("garbage") == (0, 0, 0, 0)


def test_the_version_tab_is_read_back_by_pyinstaller(tmp_path):
    from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file
    path = version_info.write_version_file(str(tmp_path / "a" / "v.txt"), "Açıklama", "x.exe", "1.1.0")
    info = load_version_info_from_text_file(path)
    assert (info.ffi.fileVersionMS, info.ffi.fileVersionLS) == ((1 << 16) | 1, 0)     # 1.1.0.0, packed as Windows does
    strings = {s.name: s.val for table in info.kids[0].kids for s in table.kids}
    assert strings["FileDescription"] == "Açıklama" and strings["OriginalFilename"] == "x.exe"


# ------------------------------------------------------------------------------ the Deno download
def test_a_download_that_does_not_match_its_checksum_is_refused(tmp_path):
    archive = zip_with("deno.exe", b"MZ-fake")
    opener = fake_net({".sha256sum": ("0" * 64 + " *deno.zip").encode(), "deno-x86_64-pc-windows-msvc.zip": archive})
    with pytest.raises(RuntimeError, match="SHA-256"):
        bi.fetch_deno(cache=str(tmp_path), tag="v1.0.0", opener=opener)
    assert not os.path.exists(tmp_path / "deno-v1.0.0" / "deno.exe")
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".zip")]        # the bad file is not kept


def test_a_zip_without_deno_exe_is_refused(tmp_path):
    archive = zip_with("readme.txt", b"hello")
    good = hashlib.sha256(archive).hexdigest()
    opener = fake_net({".sha256sum": f"{good} *x".encode(), "deno-x86_64-pc-windows-msvc.zip": archive})
    with pytest.raises(RuntimeError, match="no deno.exe"):
        bi.fetch_deno(cache=str(tmp_path), tag="v1.0.0", opener=opener)


def test_a_deno_that_does_not_run_is_refused_and_not_kept(tmp_path):
    archive = zip_with("deno.exe", b"this is not a program")
    good = hashlib.sha256(archive).hexdigest()
    opener = fake_net({".sha256sum": f"{good} *x".encode(), "deno-x86_64-pc-windows-msvc.zip": archive})
    with pytest.raises(RuntimeError, match="does not run"):
        bi.fetch_deno(cache=str(tmp_path), tag="v1.0.0", opener=opener)
    assert not (tmp_path / "deno-v1.0.0").exists()                              # nothing broken is left to be reused
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".zip")]
    with pytest.raises(RuntimeError):                                          # and asking again downloads again
        bi.fetch_deno(cache=str(tmp_path), tag="v1.0.0", opener=opener)
    assert len([u for u in opener.asked if u.endswith(".zip")]) == 2


def test_without_a_network_a_cached_deno_is_used(tmp_path):
    cached = tmp_path / "deno-v3.2.1"
    cached.mkdir()
    (cached / "deno.exe").write_bytes(b"MZ")
    opener = fake_net({"releases/latest": OSError("offline")})
    exe, tag = bi.fetch_deno(cache=str(tmp_path), opener=opener)
    assert tag == "v3.2.1" and exe == str(cached / "deno.exe")


def test_without_a_network_and_without_a_cache_the_build_stops_with_advice(tmp_path):
    with pytest.raises(RuntimeError, match="--deno-zip"):
        bi.fetch_deno(cache=str(tmp_path), opener=fake_net({"releases/latest": OSError("offline")}))


def test_a_cached_deno_is_not_downloaded_again(tmp_path):
    cached = tmp_path / "deno-v3.2.1"
    cached.mkdir()
    (cached / "deno.exe").write_bytes(b"MZ")
    opener = fake_net({})
    assert bi.fetch_deno(cache=str(tmp_path), tag="v3.2.1", opener=opener)[1] == "v3.2.1"
    assert opener.asked == []


# ------------------------------------------------------------------------------ the payload
def test_the_payload_lists_every_file_with_its_size_and_checksum(tmp_path):
    app, un, deno = tmp_path / "a.exe", tmp_path / "u.exe", tmp_path / "d.exe"
    app.write_bytes(b"A" * 1000)
    un.write_bytes(b"U" * 10)
    deno.write_bytes(b"D" * 100)
    folder = tmp_path / "payload"
    folder.mkdir()
    (folder / "stale.txt").write_text("from an earlier build")
    files = bi.make_payload(str(folder), str(app), str(un), str(deno), "1.2.3", "v2.0.0")
    data = json.loads((folder / "payload.json").read_text(encoding="utf-8"))
    assert data["version"] == "1.2.3" and data["deno"] == "v2.0.0" and data["files"] == files
    by_name = {f["name"]: f for f in files}
    assert by_name["deno.exe"]["dest"] == "deno/deno.exe" and by_name["DISO.exe"]["dest"] == "DISO.exe"
    for f in files:
        assert f["size"] == os.path.getsize(folder / f["name"]) and f["sha256"] == hashlib.sha256((folder / f["name"]).read_bytes()).hexdigest()
    assert not (folder / "stale.txt").exists()                               # an old build's leftovers are not packed


def test_a_payload_without_deno(tmp_path):
    app, un = tmp_path / "a.exe", tmp_path / "u.exe"
    app.write_bytes(b"A")
    un.write_bytes(b"U")
    files = bi.make_payload(str(tmp_path / "p"), str(app), str(un), None, "1.0.0")
    assert [f["name"] for f in files] == ["DISO.exe", "Uninstall.exe"]


def test_the_payload_made_here_is_accepted_by_the_installer(tmp_path):
    from hizli_setup import core
    app, un, deno = tmp_path / "a.exe", tmp_path / "u.exe", tmp_path / "d.exe"
    for p, b in ((app, b"A" * 5000), (un, b"U" * 500), (deno, b"D" * 800)):
        p.write_bytes(b)
    bi.make_payload(str(tmp_path / "payload"), str(app), str(un), str(deno), "1.0.0", "v1")
    env = core.test_env(str(tmp_path / "world"))
    try:
        result = core.install(str(tmp_path / "payload"), core.Options(install_dir=str(tmp_path / "dest")), env,
                              closer=lambda f: 0)
        assert (tmp_path / "dest" / "deno" / "deno.exe").read_bytes() == b"D" * 800 and result.version == "1.0.0"
    finally:
        core.delete_key_tree(env, env.reg_prefix.rstrip("\\"))


# ------------------------------------------------------------------------------ the name and the label
def test_the_setup_file_name_says_which_version_it_installs():
    from app import brand
    assert bi.setup_name(brand) == "DISO-Setup-1.4"


def test_the_payload_carries_the_label_the_registry_will_show(tmp_path):
    app, un = tmp_path / "a.exe", tmp_path / "u.exe"
    app.write_bytes(b"A")
    un.write_bytes(b"U")
    bi.make_payload(str(tmp_path / "p"), str(app), str(un), None, "0.10.0", label="0.10.0 beta")
    data = json.loads((tmp_path / "p" / "payload.json").read_text(encoding="utf-8"))
    assert data["version"] == "0.10.0" and data["label"] == "0.10.0 beta"
    bi.make_payload(str(tmp_path / "q"), str(app), str(un), None, "1.0.0")                 # no label: the number stands in
    assert json.loads((tmp_path / "q" / "payload.json").read_text(encoding="utf-8"))["label"] == "1.0.0"


def test_the_properties_tab_names_the_publisher_the_product_and_the_label(tmp_path):
    from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file
    path = version_info.write_version_file(str(tmp_path / "v.txt"), "DISO", "DISO.exe", "0.10.0", "0.10.0 beta")
    info = load_version_info_from_text_file(path)
    strings = {s.name: s.val for table in info.kids[0].kids for s in table.kids}
    assert strings["CompanyName"] == "ISO" and strings["ProductName"] == "DISO"
    assert strings["ProductVersion"] == "0.10.0 beta" and strings["FileVersion"] == "0.10.0.0"
    assert (info.ffi.fileVersionMS, info.ffi.fileVersionLS) == (10, 0)                    # 0.10 | 0.0 packed as Windows does


# ------------------------------------------------------------------------------ the program as a folder
def app_folder(root):
    """A pretend PyInstaller folder: DISO.exe and _internal/ with files a few levels deep."""
    files = {"DISO.exe": b"E" * 3000, "_internal/python315.dll": b"P" * 2000,
             "_internal/yt_dlp/extractor/youtube.py": b"Y" * 500, "_internal/ffmpeg/ffmpeg.exe": b"F" * 4000,
             "_internal/customtkinter/assets/themes/blue.json": b"{}"}
    for rel, data in files.items():
        p = root.joinpath(*rel.split("/"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return files


def test_a_program_folder_is_packed_file_by_file_keeping_its_places(tmp_path):
    app = tmp_path / "DISO"
    expected = app_folder(app)
    un = tmp_path / "u.exe"
    un.write_bytes(b"U")
    files = bi.make_payload(str(tmp_path / "p"), str(app), str(un), None, "1.0.0")
    dests = {f["dest"]: f for f in files}
    assert set(dests) == set(expected) | {"Uninstall.exe"}
    for rel, data in expected.items():
        f = dests[rel]
        assert f["name"] == "app/" + rel and (tmp_path / "p").joinpath(*f["name"].split("/")).read_bytes() == data
        assert f["sha256"] == hashlib.sha256(data).hexdigest()


def test_a_folder_without_the_program_in_it_is_refused(tmp_path):
    (tmp_path / "bos" / "_internal").mkdir(parents=True)
    (tmp_path / "bos" / "_internal" / "x.dll").write_bytes(b"x")
    with pytest.raises(RuntimeError, match="DISO.exe"):
        bi.app_entries(str(tmp_path / "bos"))


def test_a_program_folder_installs_and_uninstalls_without_a_trace(tmp_path):
    from hizli_setup import core
    app = tmp_path / "DISO"
    expected = app_folder(app)
    un = tmp_path / "u.exe"
    un.write_bytes(b"U" * 50)
    bi.make_payload(str(tmp_path / "payload"), str(app), str(un), None, "2.0.0")
    env = core.test_env(str(tmp_path / "world"))
    dest = tmp_path / "Program Files" / "ISO" / "DISO"
    try:
        core.install(str(tmp_path / "payload"), core.Options(install_dir=str(dest)), env, closer=lambda f: 0)
        for rel, data in expected.items():
            assert dest.joinpath(*rel.split("/")).read_bytes() == data
        manifest = core.read_manifest(str(dest))
        assert os.path.join("_internal", "yt_dlp") in manifest["dirs"]                # the folders in between too
        core.uninstall(str(dest), env, closer=lambda f: 0)
        assert not (tmp_path / "Program Files" / "ISO").exists()                      # nothing left, not even empty folders
    finally:
        core.delete_key_tree(env, env.reg_prefix.rstrip("\\"))


def test_the_browser_extension_is_installed_next_to_diso_and_removed_with_it(tmp_path):
    from hizli_setup import core
    ext = os.path.join(ROOT, "browser_extension")
    app = tmp_path / "DISO"
    app_folder(app)
    un = tmp_path / "u.exe"
    un.write_bytes(b"U")
    files = bi.make_payload(str(tmp_path / "payload"), str(app), str(un), None, "2.0.0", extension=ext)
    assert {"browser_extension/manifest.json", "browser_extension/_locales/tr/messages.json"} <= {f["dest"] for f in files}
    env = core.test_env(str(tmp_path / "world"))
    dest = tmp_path / "Program Files" / "ISO" / "DISO"
    try:
        core.install(str(tmp_path / "payload"), core.Options(install_dir=str(dest)), env, closer=lambda f: 0)
        installed = dest / "browser_extension" / "manifest.json"
        assert installed.read_bytes() == open(os.path.join(ext, "manifest.json"), "rb").read()
        core.uninstall(str(dest), env, closer=lambda f: 0)
        assert not (tmp_path / "Program Files" / "ISO").exists()
    finally:
        core.delete_key_tree(env, env.reg_prefix.rstrip("\\"))


def test_a_failed_install_of_a_program_folder_takes_its_new_folders_back(tmp_path, monkeypatch):
    from hizli_setup import core
    app = tmp_path / "DISO"
    app_folder(app)
    un = tmp_path / "u.exe"
    un.write_bytes(b"U")
    bi.make_payload(str(tmp_path / "payload"), str(app), str(un), None, "2.0.0")
    env = core.test_env(str(tmp_path / "world"))
    real = core._replace
    calls = []

    def failing(src, dst, *a, **k):
        calls.append(dst)
        if len(calls) == 4:
            raise PermissionError("held by something")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(core, "_replace", failing)
    dest = tmp_path / "Yeni"
    try:
        with pytest.raises(core.SetupError):
            core.install(str(tmp_path / "payload"), core.Options(install_dir=str(dest)), env, closer=lambda f: 0)
        assert not dest.exists()                                                     # every folder it made went again
    finally:
        core.delete_key_tree(env, env.reg_prefix.rstrip("\\"))


def test_the_folders_a_list_of_files_needs():
    from hizli_setup import core
    assert core.all_dirs(["DISO.exe", "deno/deno.exe", "_internal/a/b/c.py", "_internal/x.dll"]) == \
        sorted(["deno", "_internal", os.path.join("_internal", "a"), os.path.join("_internal", "a", "b")])


def test_updating_a_one_file_install_to_the_folder_version_leaves_nothing_old(tmp_path):
    """The PCs that have 0.10.0 as one big DISO.exe get the folder version over it."""
    from hizli_setup import core
    from setup_support import make_payload as old_payload
    env = core.test_env(str(tmp_path / "world"))
    dest = tmp_path / "DISO"
    try:
        core.install(str(old_payload(tmp_path / "eski", version="0.10.0")), core.Options(install_dir=str(dest)), env,
                     closer=lambda f: 0)
        app = tmp_path / "yeni-app"
        expected = app_folder(app)
        un = tmp_path / "u.exe"
        un.write_bytes(b"U" * 70)
        bi.make_payload(str(tmp_path / "yeni"), str(app), str(un), None, "0.11.0")
        core.install(str(tmp_path / "yeni"), core.Options(install_dir=str(dest)), env, closer=lambda f: 0)
        assert dest.joinpath("DISO.exe").read_bytes() == expected["DISO.exe"]
        assert not (dest / "deno").exists()                                         # the old version's file is gone
        assert not [p for p in dest.rglob("*") if p.name.endswith((".old", ".new"))]
        assert core.find_existing(env) == (str(dest), "0.11.0")
        core.uninstall(str(dest), env, closer=lambda f: 0)
        assert not dest.exists()
    finally:
        core.delete_key_tree(env, env.reg_prefix.rstrip("\\"))


# ------------------------------------------------------------------------------ the packed payload (a small setup)
def test_a_packed_payload_is_one_small_archive_and_installs_the_same(tmp_path):
    from hizli_setup import core
    app = tmp_path / "DISO"
    expected = app_folder(app)
    big = os.urandom(200_000)
    (app / "_internal" / "ffmpeg" / "ffmpeg.exe").write_bytes(big + b"ffmpeg")
    (app / "_internal" / "ffmpeg" / "ffprobe.exe").write_bytes(big + b"ffprobe")      # nearly the same program
    expected["_internal/ffmpeg/ffmpeg.exe"] = big + b"ffmpeg"
    expected["_internal/ffmpeg/ffprobe.exe"] = big + b"ffprobe"
    un = tmp_path / "u.exe"
    un.write_bytes(b"U" * 50)
    payload = tmp_path / "payload"
    filters = [{"id": __import__("lzma").FILTER_LZMA2, "preset": 1, "dict_size": 4 << 20}]
    files = bi.make_payload(str(payload), str(app), str(un), None, "2.0.0", packed=True, filters=filters)
    assert sorted(os.listdir(payload)) == ["payload.json", "payload.tar.xz"]
    archive = json.loads((payload / "payload.json").read_text(encoding="utf-8"))["archive"]
    assert archive["size"] == os.path.getsize(payload / "payload.tar.xz") < 300_000      # ffprobe costs nearly nothing
    assert sum(f["size"] for f in files) > 400_000
    env = core.test_env(str(tmp_path / "world"))
    dest = tmp_path / "Program Files" / "ISO" / "DISO"
    seen = []
    try:
        core.install(str(payload), core.Options(install_dir=str(dest)), env, closer=lambda f: 0,
                     progress=lambda part, text: seen.append(part))
        for rel, data in expected.items():
            assert dest.joinpath(*rel.split("/")).read_bytes() == data
        assert seen == sorted(seen) and seen[-1] == 1.0                                   # the bar only goes forward
        core.uninstall(str(dest), env, closer=lambda f: 0)
        assert not (tmp_path / "Program Files" / "ISO").exists()
    finally:
        core.delete_key_tree(env, env.reg_prefix.rstrip("\\"))


def test_a_damaged_packed_payload_is_refused_before_anything_is_touched(tmp_path):
    from hizli_setup import core
    app = tmp_path / "a.exe"
    app.write_bytes(b"A" * 5000)
    un = tmp_path / "u.exe"
    un.write_bytes(b"U" * 500)
    payload = tmp_path / "payload"
    bi.make_payload(str(payload), str(app), str(un), None, "1.0.0", packed=True,
                    filters=[{"id": __import__("lzma").FILTER_LZMA2, "preset": 1}])
    raw = bytearray((payload / "payload.tar.xz").read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    (payload / "payload.tar.xz").write_bytes(bytes(raw))
    env = core.test_env(str(tmp_path / "world"))
    try:
        with pytest.raises(core.SetupError, match="bozulmuş"):
            core.install(str(payload), core.Options(install_dir=str(tmp_path / "dest")), env, closer=lambda f: 0)
        assert not (tmp_path / "dest").exists()
    finally:
        core.delete_key_tree(env, env.reg_prefix.rstrip("\\"))
