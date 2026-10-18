"""The windows of Setup and Uninstall, driven the way a person would (a hidden window, test places)."""
import os
import time

import pytest
from setup_support import Closer, make_payload

from app import look
from hizli_setup import core, ui, winapi

pytestmark = [pytest.mark.gui, pytest.mark.skipif(not winapi.WINDOWS, reason="Windows only")]


@pytest.fixture
def env(tmp_path):
    e = core.test_env(str(tmp_path / "dunya"))
    yield e
    core.delete_key_tree(e, e.reg_prefix.rstrip("\\"))


@pytest.fixture
def package(tmp_path):
    return make_payload(tmp_path / "paket")


@pytest.fixture
def windows():
    """Makes windows hidden and destroys them at the end; also keeps the look of the other tests."""
    made = []
    look.apply("Yeni")

    def make(cls, *a, **k):
        try:
            w = cls(*a, **k)
        except Exception as e:  # noqa: BLE001 - no display
            pytest.skip(f"no display: {e}")
        w.withdraw()
        made.append(w)
        return w

    yield make
    for w in made:
        try:
            w.destroy()
        except Exception:  # noqa: BLE001
            pass
    import gc
    gc.collect()
    gc.enable()
    look.apply("Klasik")


def pump(window, condition, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        window.update()
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def texts(window):
    """Every piece of text on the window (labels, buttons, switches)."""
    out = []

    def walk(w):
        for child in w.winfo_children():
            try:
                t = child.cget("text")
                if t:
                    out.append(str(t))
            except Exception:  # noqa: BLE001
                pass
            walk(child)

    walk(window)
    return out


def has_text(window, fragment):
    return any(fragment in t for t in texts(window))


def button(window, caption):
    def walk(w):
        for child in w.winfo_children():
            try:
                if child.cget("text") == caption and hasattr(child, "invoke"):
                    return child
            except Exception:  # noqa: BLE001
                pass
            found = walk(child)
            if found:
                return found
        return None

    return walk(window.buttons) or walk(window.body)


# ------------------------------------------------------------------------------ Setup
def test_the_first_page_offers_the_usual_folder_and_the_choices(windows, package, env):
    w = windows(ui.SetupWindow, str(package), env, closer=Closer())
    assert w.dir_var.get() == env.default_install_dir
    assert w.desktop_var.get() and w.menu_var.get() and w.launch_var.get() and not w.autostart_var.get()
    assert has_text(w, "kurulacak") and has_text(w, "Python ya da başka bir şey kurmana gerek yok")
    assert has_text(w, "herkes için kurulur") and button(w, "Kur") and button(w, "İptal")


def test_pressing_install_installs_and_shows_the_result(windows, package, env, tmp_path):
    w = windows(ui.SetupWindow, str(package), env, closer=Closer(), on_launch=lambda exe: pytest.fail("not asked"))
    target = tmp_path / "Benim Klasörüm"
    w.dir_var.set(str(target))
    w.launch_var.set(False)
    w.start_install()
    assert has_text(w, "Kuruluyor")
    assert pump(w, lambda: w.result is not None or w.exit_code == 2)
    assert w.exit_code == 0 and w.result.install_dir == str(target)
    assert (target / "DISO.exe").is_file() and os.path.isfile(os.path.join(env.start_menu_dir, core.SHORTCUT_NAME))
    assert pump(w, lambda: has_text(w, "Kurulum bitti, hazırız")) and button(w, "Bitir")
    assert core.find_existing(env) == (str(target), "1.2.0")


def test_the_switches_decide_what_is_made(windows, package, env, tmp_path):
    w = windows(ui.SetupWindow, str(package), env, closer=Closer())
    w.dir_var.set(str(tmp_path / "s"))
    w.desktop_var.set(False)
    w.menu_var.set(False)
    w.autostart_var.set(True)
    w.start_install()
    assert pump(w, lambda: w.result is not None)
    assert not os.path.exists(os.path.join(env.desktop_dir, core.SHORTCUT_NAME)) and not os.path.exists(env.start_menu_dir)
    assert core._read_value(env, env.run_key, "DISO")


def test_finishing_starts_the_program_only_when_asked(windows, package, env, tmp_path):
    started = []
    w = windows(ui.SetupWindow, str(package), env, closer=Closer(), on_launch=started.append)
    w.dir_var.set(str(tmp_path / "a"))
    w.start_install()
    assert pump(w, lambda: w.result is not None)
    w.finish()
    assert started == [str(tmp_path / "a" / "DISO.exe")]
    other = windows(ui.SetupWindow, str(package), env, closer=Closer(), on_launch=started.append)
    other.dir_var.set(str(tmp_path / "b"))
    other.launch_var.set(False)
    other.start_install()
    assert pump(other, lambda: other.result is not None)
    other.finish()
    assert started == [str(tmp_path / "a" / "DISO.exe")]


def test_a_bad_folder_is_explained_and_nothing_starts(windows, package, env):
    w = windows(ui.SetupWindow, str(package), env, closer=Closer())
    for bad in ("", "göreli\\yol", "C:\\", "C:\\a\\b?"):
        w.dir_var.set(bad)
        w.start_install()
        assert w.error.cget("text") and w.result is None and not hasattr(w, "bar")
    assert core.find_existing(env) == (None, None)


def test_a_failure_is_shown_with_a_way_back(windows, package, env, tmp_path):
    (package / "deno.exe").write_bytes(b"broken")
    w = windows(ui.SetupWindow, str(package), env, closer=Closer())
    w.dir_var.set(str(tmp_path / "f"))
    w.start_install()
    assert pump(w, lambda: w.exit_code == 2)
    assert pump(w, lambda: has_text(w, "Kurulumu yapamadım")) and has_text(w, "bozulmuş")
    assert has_text(w, "hiçbir değişiklik bırakmadım") and not (tmp_path / "f").exists()
    button(w, "Tekrar dene").invoke()
    assert button(w, "Kur") and w.exit_code == 1


def test_an_unexpected_error_is_shown_not_swallowed(windows, package, env, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("tuhaf bir şey")

    monkeypatch.setattr(core, "install", boom)
    w = windows(ui.SetupWindow, str(package), env, closer=Closer())
    w.dir_var.set(str(tmp_path / "u"))
    w.start_install()
    assert pump(w, lambda: w.exit_code == 2)
    assert pump(w, lambda: has_text(w, "Hoppala, beklenmedik") and has_text(w, "tuhaf bir şey"))


def test_a_broken_package_is_reported_on_the_first_page(windows, tmp_path, env):
    w = windows(ui.SetupWindow, str(tmp_path / "yok"), env, closer=Closer())
    assert has_text(w, "Kurulum paketi okunamadı") and button(w, "Kapat") and not button(w, "Kur")


def test_an_installed_copy_is_offered_an_update_in_its_own_folder(windows, tmp_path, env):
    old = make_payload(tmp_path / "v1", version="1.0.0", seed=b"1")
    core.install(old, core.Options(install_dir=str(tmp_path / "Kurulu Yer")), env, closer=Closer())
    new = make_payload(tmp_path / "v2", version="2.0.0", seed=b"2")
    w = windows(ui.SetupWindow, str(new), env, closer=Closer())
    assert w.dir_var.get() == str(tmp_path / "Kurulu Yer")
    assert has_text(w, "1.0.0 bu bilgisayarda kurulu") and has_text(w, "2.0.0 sürümüne güncelleyeceğim")
    w.start_install()
    assert pump(w, lambda: w.result is not None)
    assert core.find_existing(env) == (str(tmp_path / "Kurulu Yer"), "2.0.0")


def test_cancelling_leaves_everything_alone(windows, package, env):
    w = windows(ui.SetupWindow, str(package), env, closer=Closer())
    button(w, "İptal").invoke()
    assert w.exit_code == 1 and not os.path.exists(env.default_install_dir)
    with pytest.raises(Exception):
        w.winfo_exists() and w.update() or (_ for _ in ()).throw(Exception("gone"))


def test_the_window_cannot_be_closed_while_it_installs(windows, package, env, tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(ui.messagebox, "showinfo", lambda *a, **k: asked.append(a))
    w = windows(ui.SetupWindow, str(package), env, closer=Closer())
    w.dir_var.set(str(tmp_path / "k"))
    w.start_install()
    w._on_x()                                                        # the X button, mid-install
    assert asked and w.winfo_exists()
    assert pump(w, lambda: w.result is not None)


def test_closing_the_window_after_a_good_install_is_not_a_cancel(windows, package, env, tmp_path):
    started = []
    w = windows(ui.SetupWindow, str(package), env, closer=Closer(), on_launch=started.append)
    w.dir_var.set(str(tmp_path / "x"))
    w.start_install()
    assert pump(w, lambda: w.result is not None)
    w._on_x()
    assert w.exit_code == 0 and started == []                        # success stays success; nothing was launched


def test_closing_the_window_after_a_failure_keeps_the_failure(windows, package, env, tmp_path):
    (package / "deno.exe").write_bytes(b"broken")
    w = windows(ui.SetupWindow, str(package), env, closer=Closer())
    w.dir_var.set(str(tmp_path / "y"))
    w.start_install()
    assert pump(w, lambda: w.exit_code == 2)
    w._on_x()
    assert w.exit_code == 2


def test_browsing_fills_the_folder_field(windows, package, env, monkeypatch, tmp_path):
    w = windows(ui.SetupWindow, str(package), env, closer=Closer())
    monkeypatch.setattr(ui.filedialog, "askdirectory", lambda **k: str(tmp_path / "seçilen" / "klasör"))
    w.browse()
    assert w.dir_var.get() == os.path.normpath(str(tmp_path / "seçilen" / "klasör"))
    monkeypatch.setattr(ui.filedialog, "askdirectory", lambda **k: "")
    w.browse()
    assert w.dir_var.get() == os.path.normpath(str(tmp_path / "seçilen" / "klasör"))      # cancelled: unchanged


def test_the_progress_bar_follows_the_install(windows, package, env, tmp_path):
    w = windows(ui.SetupWindow, str(package), env, closer=Closer())
    w.dir_var.set(str(tmp_path / "p"))
    seen = []
    real = core.install

    def watching(payload, options, env_, progress=None, closer=None):
        def spy(f, t):
            seen.append((f, t))
            progress(f, t)
        return real(payload, options, env_, progress=spy, closer=closer)

    core.install = watching
    try:
        w.start_install()
        assert pump(w, lambda: w.result is not None)
    finally:
        core.install = real
    assert seen[0][0] == 0.0 and seen[-1][0] == 1.0 and len({t for _, t in seen}) >= 5


# ------------------------------------------------------------------------------ Uninstall
@pytest.fixture
def installed(package, env, tmp_path):
    target = tmp_path / "Kurulu"
    core.install(package, core.Options(install_dir=str(target)), env, closer=Closer())
    return target


def test_the_uninstaller_asks_first_and_offers_to_keep_the_data(windows, installed, env):
    w = windows(ui.UninstallWindow, str(installed), env, closer=Closer())
    assert has_text(w, "kaldırılsın mı") and has_text(w, str(installed)) and not w.data_var.get()
    assert has_text(w, "çalma listelerimi de sil") and button(w, "Kaldır") and button(w, "Vazgeç")


def test_removing_removes_and_reports(windows, installed, env):
    w = windows(ui.UninstallWindow, str(installed), env, closer=Closer())
    os.makedirs(env.user_data_dir)
    open(os.path.join(env.user_data_dir, "playlists.json"), "w").write("{}")
    w.start()
    assert has_text(w, "Kaldırılıyor")
    assert pump(w, lambda: w.result is not None)
    assert w.exit_code == 0 and not installed.exists() and core.find_existing(env) == (None, None)
    assert os.path.isfile(os.path.join(env.user_data_dir, "playlists.json"))
    assert pump(w, lambda: has_text(w, "Kaldırıldı")) and button(w, "Bitir")


def test_removing_with_the_data_switch_removes_the_data_too(windows, installed, env):
    w = windows(ui.UninstallWindow, str(installed), env, closer=Closer())
    os.makedirs(env.user_data_dir)
    open(os.path.join(env.user_data_dir, "playlists.json"), "w").write("{}")
    w.data_var.set(True)
    w.start()
    assert pump(w, lambda: w.result is not None)
    assert not os.path.exists(env.user_data_dir)


def test_the_switch_can_be_preset_from_the_command_line(windows, installed, env):
    assert windows(ui.UninstallWindow, str(installed), env, closer=Closer(), remove_data=True).data_var.get()


def test_files_that_stay_until_the_next_restart_are_listed(windows, installed, env, monkeypatch):
    monkeypatch.setattr(core.winapi, "delete_on_reboot", lambda p: True)
    w = windows(ui.UninstallWindow, str(installed), env, closer=Closer())
    exe = str(installed / "DISO.exe")
    held = open(exe, "rb")
    try:
        real_remove = core._remove_file
        core._remove_file = lambda path, retries=6, wait=0.4, sleep=time.sleep: real_remove(path, retries=1, wait=0)
        w.start()
        assert pump(w, lambda: w.result is not None)
    finally:
        core._remove_file = real_remove
        held.close()
    assert w.result.leftovers == [exe]
    assert pump(w, lambda: has_text(w, "yeniden başlayınca silinecek") and has_text(w, "DISO.exe"))


def test_giving_up_in_the_uninstaller_changes_nothing(windows, installed, env):
    w = windows(ui.UninstallWindow, str(installed), env, closer=Closer())
    button(w, "Vazgeç").invoke()
    assert w.exit_code == 1 and (installed / "DISO.exe").is_file() and core.find_existing(env)[0] == str(installed)


def test_a_failing_removal_is_shown(windows, installed, env, monkeypatch):
    def boom(*a, **k):
        raise core.SetupError("Bir dosya silinemedi")

    monkeypatch.setattr(core, "uninstall", boom)
    w = windows(ui.UninstallWindow, str(installed), env, closer=Closer())
    w.start()
    assert pump(w, lambda: w.exit_code == 2)
    assert pump(w, lambda: has_text(w, "Kaldırmayı tamamlayamadım") and has_text(w, "Bir dosya silinemedi"))


@pytest.mark.parametrize("which", ["setup", "uninstall"])
def test_both_windows_fit_on_a_small_screen(windows, package, env, installed, which):
    # one window per test: customtkinter ties its pictures to the first window of the process, and a real run has one
    for w in ([windows(ui.SetupWindow, str(package), env, closer=Closer())] if which == "setup"
              else [windows(ui.UninstallWindow, str(installed), env, closer=Closer())]):
        w.update_idletasks()
        size = w.geometry().split("+")[0]                           # "640x660"
        scale = float(w._get_window_scaling())                       # customtkinter sizes windows in scaled pixels
        width, height = (int(int(n) * scale) for n in size.split("x"))
        assert w.winfo_reqheight() <= height and w.winfo_reqwidth() <= width     # nothing is cut off
        assert height <= w.winfo_screenheight()
