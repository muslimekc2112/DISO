import hashlib
import io
import os
import zipfile

import pytest

from app import ffmpeg_setup as ff
from app.segmented_downloader import DownloadError
from app.utils import user_tools_dir

FFMPEG, FFPROBE = ff.TOOLS          # ffmpeg.exe / ffprobe.exe on Windows, without .exe elsewhere


def make_zip(with_ffmpeg=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if with_ffmpeg:
            z.writestr(f"ffmpeg-9.0-essentials/bin/{FFMPEG}", b"fake-ffmpeg-binary")
            z.writestr(f"ffmpeg-9.0-essentials/bin/{FFPROBE}", b"fake-ffprobe-binary")
        z.writestr(f"ffmpeg-9.0-essentials/doc/{FFMPEG}", b"NOT the one in bin/")
        z.writestr("ffmpeg-9.0-essentials/README", os.urandom(16))  # every archive differs
    return buf.getvalue()


def mirror(server, zip_bytes, sha=None, style="bare"):
    """Put an archive and its checksum file on the test server. Returns (archive, sha_url)."""
    archive = server.add(zip_bytes, ".zip", name="ffmpeg-release-essentials.zip")
    real = hashlib.sha256(zip_bytes).hexdigest() if sha is None else sha
    if style == "bare":
        sums = real + "\n"
    else:  # BtbN style: many lines, one per archive
        sums = f"{'a' * 64}  other-build.zip\n{real}  {archive}\n{'b' * 64}  third.zip\n"
    sha_name = server.add(sums.encode(), ".sha256", name=f"{archive}.{style}.sha256")
    return server.url("f", archive), server.url("f", sha_name)


# ---------------------------------------------------------------------- checksum files
def test_sha256_of_a_file(tmp_path):
    p = tmp_path / "x"
    p.write_bytes(b"abc")
    assert ff.sha256_file(str(p)) == hashlib.sha256(b"abc").hexdigest()


def test_bare_hash_file_is_understood(server):
    data = make_zip()
    archive, sha_url = mirror(server, data, style="bare")
    assert ff.fetch_expected_sha256(archive, sha_url) == hashlib.sha256(data).hexdigest()


def test_checksum_list_picks_the_line_of_the_right_archive(server):
    data = make_zip()
    archive, sha_url = mirror(server, data, style="list")
    assert ff.fetch_expected_sha256(archive, sha_url) == hashlib.sha256(data).hexdigest()


def test_checksum_list_without_our_archive_is_an_error(server):
    sums = server.add(f"{'a' * 64}  something-else.zip\n".encode(), ".sha256")
    archive = server.add(make_zip(), ".zip")
    with pytest.raises(DownloadError):
        ff.fetch_expected_sha256(server.url("f", archive), server.url("f", sums))


def test_latest_release_uses_the_first_mirror_that_answers(server):
    data = make_zip()
    good = mirror(server, data)
    dead = ("http://127.0.0.1:9/a.zip", "http://127.0.0.1:9/a.zip.sha256")
    old = ff.FFMPEG_SOURCES
    try:
        ff.FFMPEG_SOURCES = [dead, good]
        sha, archive = ff.latest_release()
    finally:
        ff.FFMPEG_SOURCES = old
    assert sha == hashlib.sha256(data).hexdigest() and archive == good[0]


def test_latest_release_with_every_mirror_down_is_an_error():
    old = ff.FFMPEG_SOURCES
    try:
        ff.FFMPEG_SOURCES = [("http://127.0.0.1:9/a.zip", "http://127.0.0.1:9/a.sha256")]
        with pytest.raises(DownloadError):
            ff.latest_release()
    finally:
        ff.FFMPEG_SOURCES = old


# ------------------------------------------------------------------------- installing
def tools_files():
    return sorted(os.listdir(user_tools_dir()))


def test_install_verifies_unpacks_only_bin_and_records_what_it_installed(server):
    data = make_zip()
    ff.ensure_ffmpeg(sources=[mirror(server, data)], force=True)
    assert ff.last_error == ""
    assert open(os.path.join(user_tools_dir(), FFMPEG), "rb").read() == b"fake-ffmpeg-binary"
    assert open(os.path.join(user_tools_dir(), FFPROBE), "rb").read() == b"fake-ffprobe-binary"
    info = ff.read_info()
    assert info["sha256"] == hashlib.sha256(data).hexdigest()
    # no download archive or half-written .new files left behind
    assert tools_files() == sorted([FFMPEG, "ffmpeg.json", FFPROBE])


def test_install_works_with_a_btbn_style_checksum_list(server):
    ff.ensure_ffmpeg(sources=[mirror(server, make_zip(), style="list")], force=True)
    assert ff.last_error == "" and FFMPEG in tools_files()


def test_a_wrong_checksum_installs_nothing(server):
    ff.ensure_ffmpeg(sources=[mirror(server, make_zip(), sha="0" * 64)], force=True)
    assert "SHA-256" in ff.last_error
    assert tools_files() == []                       # not even the archive stays


def test_after_a_bad_mirror_the_next_one_is_tried(server):
    bad = mirror(server, make_zip(), sha="0" * 64)
    good_zip = make_zip()
    archive = server.add(good_zip, ".zip")
    sha = server.add((hashlib.sha256(good_zip).hexdigest() + "\n").encode(), ".sha256")
    ff.ensure_ffmpeg(sources=[bad, (server.url("f", archive), server.url("f", sha))], force=True)
    assert ff.last_error == "" and FFMPEG in tools_files()


def test_an_archive_without_ffmpeg_exe_is_an_error(server):
    ff.ensure_ffmpeg(sources=[mirror(server, make_zip(with_ffmpeg=False))], force=True)
    assert ff.last_error and FFMPEG not in tools_files()


def test_a_failed_update_keeps_the_working_ffmpeg(server):
    first = make_zip()
    ff.ensure_ffmpeg(sources=[mirror(server, first)], force=True)
    before = open(os.path.join(user_tools_dir(), FFMPEG), "rb").read()
    installed_sha = ff.read_info()["sha256"]
    assert installed_sha == hashlib.sha256(first).hexdigest()
    ff.ensure_ffmpeg(sources=[mirror(server, make_zip(), sha="1" * 64)], force=True)
    assert "SHA-256" in ff.last_error
    assert open(os.path.join(user_tools_dir(), FFMPEG), "rb").read() == before
    assert ff.read_info()["sha256"] == installed_sha     # the record still matches what is installed


def test_unreachable_mirror_is_reported_not_raised():
    ff.ensure_ffmpeg(sources=[("http://127.0.0.1:9/a.zip", "http://127.0.0.1:9/a.sha256")], force=True)
    assert ff.last_error


def test_is_managed_only_for_the_apps_own_tools_folder(tmp_path):
    assert ff.is_managed(os.path.join(user_tools_dir(), FFMPEG))
    assert not ff.is_managed(str(tmp_path / "ffmpeg.exe"))
    assert not ff.is_managed(None)


def test_read_info_without_a_record_is_empty():
    assert ff.read_info() == {}
