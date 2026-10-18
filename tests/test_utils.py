import os

from app import utils


# ------------------------------------------------------------------------ file names
def test_sanitize_replaces_characters_windows_forbids():
    assert utils.sanitize_filename('a<b>c:"d"/e\\f|g?h*i') == "a_b_c__d__e_f_g_h_i"


def test_sanitize_avoids_reserved_windows_names():
    assert utils.sanitize_filename("con.txt") == "_con.txt"
    assert utils.sanitize_filename("NUL") == "_NUL"
    assert utils.sanitize_filename("com3") == "_com3"


def test_sanitize_strips_trailing_dots_and_spaces_and_never_returns_empty():
    assert utils.sanitize_filename("name. ") == "name"
    assert utils.sanitize_filename("  ") == "download"
    assert utils.sanitize_filename(None) == "download"


def test_sanitize_shortens_long_names_but_keeps_the_extension():
    name = utils.sanitize_filename("x" * 300 + ".mp4", maxlen=150)
    assert len(name) == 150 and name.endswith(".mp4")


def test_unique_path_numbers_taken_names_including_part_files(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert utils.unique_path(str(tmp_path), "a.txt") == str(tmp_path / "a (1).txt")
    (tmp_path / "a (1).txt.part").write_text("x")  # a download in progress also blocks the name
    assert utils.unique_path(str(tmp_path), "a.txt") == str(tmp_path / "a (2).txt")
    assert utils.unique_path(str(tmp_path), "free.txt") == str(tmp_path / "free.txt")


# ------------------------------------------------------------------------ formatting
def test_human_size():
    assert utils.human_size(0) == "0 B"
    assert utils.human_size(1536) == "1.5 KB"
    assert utils.human_size(5 * 1024 ** 3) == "5.0 GB"
    assert utils.human_size(None) == "0 B"


def test_human_eta():
    assert utils.human_eta(None) == "--:--"
    assert utils.human_eta(0) == "--:--"
    assert utils.human_eta(float("inf")) == "--:--"
    assert utils.human_eta(75) == "01:15"
    assert utils.human_eta(3725) == "1:02:05"


# ------------------------------------------------------------------------------ URLs
def test_is_url_and_normalize():
    assert utils.is_url("https://example.com/a")
    assert utils.is_url("www.example.com/a")           # gets https:// added
    assert utils.normalize_url("  www.x.com ") == "https://www.x.com"
    assert not utils.is_url("ftp://example.com/a")
    assert not utils.is_url("http://")
    assert not utils.is_url("just some text")


def test_extract_urls_finds_links_in_any_text_without_repeats():
    text = "bak https://x.com/a?b=1, ve www.foo.org/p; sonra https://x.com/a?b=1 yine"
    assert utils.extract_urls(text) == ["https://x.com/a?b=1", "https://www.foo.org/p"]


def test_extract_urls_drops_brackets_that_are_not_part_of_the_link():
    assert utils.extract_urls("(bkz https://y.net/z).") == ["https://y.net/z"]
    assert utils.extract_urls("[https://y.net/z]") == ["https://y.net/z"]
    # a bracket that belongs to the link stays
    assert utils.extract_urls("https://en.wikipedia.org/wiki/Foo_(bar)") == [
        "https://en.wikipedia.org/wiki/Foo_(bar)"]


def test_extract_urls_on_empty_input():
    assert utils.extract_urls("") == []
    assert utils.extract_urls(None) == []
    assert utils.extract_urls("no links here") == []


def test_urls_from_file_reads_utf8_with_bom_and_turkish_codepage(tmp_path):
    a = tmp_path / "a.txt"
    a.write_bytes("﻿https://a.com/1\nhttps://b.com/çay\n".encode("utf-8"))
    assert utils.urls_from_file(str(a)) == ["https://a.com/1", "https://b.com/çay"]
    b = tmp_path / "b.txt"
    b.write_bytes("http://c.com/şeker\n".encode("cp1254"))
    assert utils.urls_from_file(str(b)) == ["http://c.com/şeker"]


def test_urls_from_file_missing_file_gives_empty_list(tmp_path):
    assert utils.urls_from_file(str(tmp_path / "nope.txt")) == []


# ------------------------------------------------------------------------------ paths
def test_app_data_dir_lives_in_local_appdata(isolated_home):
    d = utils.app_data_dir()
    assert os.path.isdir(d)
    assert d == str(isolated_home / "AppData" / "Local" / "DISO")
    assert utils.user_tools_dir().startswith(d)


def test_setup_environment_puts_existing_tool_folders_on_path(monkeypatch, tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    monkeypatch.setattr(utils, "tool_dirs", lambda: [str(tools), str(tmp_path / "missing")])
    monkeypatch.setenv("PATH", "X")
    utils.setup_environment()
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tools)
    assert str(tmp_path / "missing") not in os.environ["PATH"]
