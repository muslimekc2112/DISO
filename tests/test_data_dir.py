"""Where the program keeps its data (%LOCALAPPDATA%\\DISO) and how what the earlier version kept in
~/.hizli_indirici comes along."""
import os
import shutil

import pytest

from app import brand, utils


def fill(folder):
    """What a used program leaves behind: settings, lists and a few downloaded tools."""
    (folder / "tools").mkdir(parents=True)
    (folder / "packages").mkdir()
    (folder / "settings.json").write_text('{"theme": "Açık"}', encoding="utf-8")
    (folder / "playlists.json").write_text('{"playlists": {"Çalma listem": []}}', encoding="utf-8")
    (folder / "downloads.json").write_text('{"items": []}', encoding="utf-8")
    (folder / "tools" / "ffmpeg.exe").write_bytes(b"MZ" * 1000)
    (folder / "packages" / "yt_dlp.txt").write_text("package", encoding="utf-8")


def tree(folder):
    return sorted(os.path.relpath(os.path.join(r, f), folder) for r, _, fs in os.walk(folder) for f in fs)


@pytest.fixture
def legacy(isolated_home):
    folder = isolated_home / ".hizli_indirici"
    fill(folder)
    return folder


def new_dir(isolated_home):
    return isolated_home / "AppData" / "Local" / "DISO"


# ------------------------------------------------------------------------------ the new place
def test_a_fresh_start_makes_the_folder_in_local_appdata(isolated_home):
    d = utils.app_data_dir()
    assert d == str(new_dir(isolated_home)) and os.path.isdir(d) and os.listdir(d) == []
    assert utils.app_data_dir() == d                                          # asking again changes nothing


def test_the_name_comes_from_the_one_place_that_names_the_program(isolated_home):
    assert os.path.basename(utils.app_data_dir()) == brand.DATA_DIR_NAME == brand.APP_ID == "DISO"


def test_without_the_environment_variable_the_usual_place_is_used(isolated_home, monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA")
    assert utils.app_data_dir() == str(isolated_home / "AppData" / "Local" / "DISO")


# ------------------------------------------------------------------------------ bringing the old data along
def test_the_old_folder_is_moved_with_everything_in_it(isolated_home, legacy):
    before = tree(legacy)
    d = utils.app_data_dir()
    assert d == str(new_dir(isolated_home)) and tree(d) == before
    assert not legacy.exists()                                                # moved, not copied
    assert (new_dir(isolated_home) / "settings.json").read_text(encoding="utf-8") == '{"theme": "Açık"}'
    assert (new_dir(isolated_home) / "tools" / "ffmpeg.exe").read_bytes() == b"MZ" * 1000


def test_it_happens_once_only(isolated_home, legacy):
    utils.app_data_dir()
    (isolated_home / ".hizli_indirici").mkdir()                                # an old folder appears again later ...
    (isolated_home / ".hizli_indirici" / "x.txt").write_text("late")
    d = utils.app_data_dir()
    assert d == str(new_dir(isolated_home)) and not os.path.exists(os.path.join(d, "x.txt"))   # ... and is not merged in
    assert (isolated_home / ".hizli_indirici" / "x.txt").read_text() == "late"


def test_when_both_exist_the_new_one_wins_and_the_old_is_left_alone(isolated_home, legacy):
    new_dir(isolated_home).mkdir(parents=True)
    (new_dir(isolated_home) / "settings.json").write_text('{"theme": "Koyu"}', encoding="utf-8")
    d = utils.app_data_dir()
    assert (new_dir(isolated_home) / "settings.json").read_text(encoding="utf-8") == '{"theme": "Koyu"}'
    assert (legacy / "settings.json").is_file() and d == str(new_dir(isolated_home))


def test_an_empty_old_folder_is_not_a_problem(isolated_home):
    (isolated_home / ".hizli_indirici").mkdir()
    d = utils.app_data_dir()
    assert os.path.isdir(d) and d == str(new_dir(isolated_home)) and not (isolated_home / ".hizli_indirici").exists()


def test_a_file_in_use_does_not_stop_it_the_data_is_copied_instead(isolated_home, legacy):
    before = tree(legacy)
    held = open(legacy / "settings.json", "rb")                                # the old program still has it open
    try:
        d = utils.app_data_dir()
    finally:
        held.close()
    assert d == str(new_dir(isolated_home))
    assert tree(d) == before                                                    # the new place has everything ...
    assert (new_dir(isolated_home) / "settings.json").read_text(encoding="utf-8") == '{"theme": "Açık"}'
    left = tree(legacy) if legacy.exists() else []
    assert set(left) <= {"settings.json"}                                       # ... the old one keeps at most the locked file


def test_if_nothing_can_be_moved_or_copied_the_old_folder_keeps_being_used(isolated_home, legacy, monkeypatch):
    def refuse(*a, **k):
        raise PermissionError("no")

    monkeypatch.setattr(utils.shutil, "move", refuse)
    monkeypatch.setattr(utils.shutil, "copytree", refuse)
    d = utils.app_data_dir()
    assert d == str(legacy) and (legacy / "playlists.json").is_file()           # nothing lost, nothing hidden
    assert not new_dir(isolated_home).exists()                                 # and no half-empty new folder to confuse


def test_a_copy_that_dies_half_way_is_removed(isolated_home, legacy, monkeypatch):
    def half(src, dst, **k):
        os.makedirs(dst, exist_ok=True)
        (dst if not isinstance(dst, str) else __import__("pathlib").Path(dst)).joinpath("settings.json").write_text("half")
        raise OSError("disk full")

    monkeypatch.setattr(utils.shutil, "move", lambda *a, **k: (_ for _ in ()).throw(PermissionError("busy")))
    monkeypatch.setattr(utils.shutil, "copytree", half)
    d = utils.app_data_dir()
    assert d == str(legacy) and not new_dir(isolated_home).exists()


def test_the_settings_are_found_in_the_new_place_after_the_move(isolated_home, legacy):
    from app.config import Config
    assert Config().get("theme") == "Açık"                                      # the old settings are in force
    assert os.path.dirname(Config().path) == str(new_dir(isolated_home))


def test_the_playlists_come_along(isolated_home, legacy):
    from app.playlists import PlaylistStore
    store = PlaylistStore()
    assert store.names() == ["Çalma listem"] and os.path.dirname(store.path) == str(new_dir(isolated_home))
