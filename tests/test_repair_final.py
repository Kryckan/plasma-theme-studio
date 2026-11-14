# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Repairs after the three checkers: pictures that must not hang or fill the memory, the install
check, undo steps, the installed color scheme an apply names, and the status of a new desktop theme."""

import os
import struct
import threading
import zlib

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QMessageBox  # noqa: E402

from plasma_theme_studio import images, kconfig, library, palette, paths  # noqa: E402
from plasma_theme_studio.apply import engine  # noqa: E402
from plasma_theme_studio.edits import theme_edits_from_color_scheme  # noqa: E402
from plasma_theme_studio.generators import ColorSchemeGenerator  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID, Theme  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages import colors_wallpaper as wallpaper_page  # noqa: E402
from plasma_theme_studio.ui.pages import themes_global  # noqa: E402

SCHEME = """[General]
Name=Nordic

[Colors:Window]
BackgroundNormal=46,52,64
ForegroundNormal=216,222,233
ForegroundInactive=120,120,120

[Colors:View]
BackgroundNormal=40,44,52
ForegroundNormal=216,222,233

[Colors:Selection]
BackgroundNormal=136,192,208
"""


def png_header(width, height) -> bytes:
    """The signature and the header chunk of a PNG that claims `width` x `height`; no pixels follow."""
    body = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + body
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(body)) + chunk + struct.pack(">I", zlib.crc32(chunk))


def within(seconds, function):
    """The result of `function()`, or fail when it does not return in time (a blocked read)."""
    result = []
    thread = threading.Thread(target=lambda: result.append(function()), daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), "blocked"
    return result[0]


# ---- pictures ---------------------------------------------------------------


def test_a_pipe_as_the_chosen_picture_does_not_block(app, tmp_path):
    pipe = tmp_path / "pipe.png"
    os.mkfifo(pipe)
    job = wallpaper_page.WallpaperJob(1, pipe, 1.0, None)
    found = within(5, job.work)
    assert found.result is None and found.thumbnail is None
    assert "cannot be read" in found.reason
    assert images.read_image(pipe).isNull()
    assert within(5, lambda: palette.extract(pipe)).ok is False


@pytest.mark.parametrize("size", [(100000, 100000), (7000, 7000), (60000, 60000)])
def test_a_picture_that_claims_to_be_huge_is_not_decoded(app, tmp_path, size):
    path = tmp_path / "huge.png"
    path.write_bytes(png_header(*size))  # a header only: nothing of the size is ever built
    assert images.open_reader(path) is None or images.read_image(path).isNull()
    assert images.read_image(path).isNull()
    assert palette.extract(path).ok is False
    found = wallpaper_page.WallpaperJob(1, path, 1.0, None).work()
    assert found.result is None and found.thumbnail is None and found.reason


def test_the_decode_limit_is_set_by_the_app(app, tmp_path):
    from PySide6.QtGui import QImage, QImageReader

    QImageReader.setAllocationLimit(1000)
    path = tmp_path / "small.png"
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0xFF336699)
    image.save(str(path))
    assert not images.read_image(path).isNull()
    assert QImageReader.allocationLimit() == images.ALLOCATION_LIMIT_MB


# ---- install from file ------------------------------------------------------


@pytest.fixture
def window(app, home, desktop_runner):
    window = MainWindow(desktop_runner)
    window.resize(1100, 720)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def test_install_validates_the_bytes_it_writes(window, home, monkeypatch):
    source = home / "elsewhere" / "Dusk.colors"
    source.parent.mkdir()
    source.write_text(SCHEME.replace("Nordic", "Dusk"))

    def forbidden(*args):
        raise AssertionError("the file was read a second time")

    monkeypatch.setattr(library, "read_scheme", forbidden)
    window.show_page("colors")
    assert window.page("colors").install_from_file(str(source))
    assert (home / ".local/share/color-schemes/Dusk.colors").read_text() == source.read_text()


def test_installing_over_a_system_scheme_asks(window, home, monkeypatch):
    system = home / "system/share/color-schemes"
    system.mkdir(parents=True)
    (system / "Nordic.colors").write_text(SCHEME)
    source = home / "Nordic.colors"
    source.write_text(SCHEME)
    asked = []

    def ask(*args, **kwargs):
        asked.append(args[2])
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(ask))
    window.show_page("colors")
    assert window.page("colors").install_from_file(str(source)) is False
    assert asked and "came with the system" in asked[0]
    assert not (home / ".local/share/color-schemes/Nordic.colors").exists()


def test_the_home_data_folder_is_never_a_system_folder(home, monkeypatch):
    monkeypatch.setenv("XDG_DATA_DIRS", f"{paths.data_home()}:{home / 'system/share'}")
    assert paths.data_home() not in paths.system_data_dirs()
    folder = paths.color_schemes_dir()
    folder.mkdir(parents=True)
    (folder / "Mine.colors").write_text(SCHEME)
    assert ColorSchemeGenerator().problems(Theme({("meta", "name"): "Mine"})) == []


def test_the_name_clash_message_says_which_file(home):
    system = home / "system/share/color-schemes"
    system.mkdir(parents=True)
    (system / "Mine.colors").write_text(SCHEME)
    problems = ColorSchemeGenerator().problems(Theme({("meta", "name"): "Mine"}))
    assert str(system / "Mine.colors") in str(problems[0])


# ---- undo steps -------------------------------------------------------------


def test_two_quick_clicks_on_a_card_are_two_undo_steps(window):
    window.edit(FIELD_BY_ID[("desktop", "icons")], "Papirus")
    window.edit(FIELD_BY_ID[("desktop", "icons")], "breeze")
    assert window.undo_stack.count() == 2
    window.edit(FIELD_BY_ID[("panel_layout", "floating")], True)
    window.edit(FIELD_BY_ID[("panel_layout", "floating")], False)
    assert window.undo_stack.count() == 4


def test_dragging_a_slider_is_still_one_undo_step(window):
    for value in (6, 7, 8, 9):
        window.edit(FIELD_BY_ID[("shape", "radius")], value)
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert window.theme.get("shape", "radius") == 5


# ---- the status of the window ------------------------------------------------


def test_a_change_of_the_desktop_makes_an_older_status_answer_out_of_date(window):
    generation = window.status_generation
    window.reload_library()
    assert window.status_generation > generation


def test_an_answer_for_a_page_that_is_gone_is_not_an_error(app):
    class Gone:
        def emit(self, *args):
            raise RuntimeError("Internal C++ object already deleted")

    class Answer:
        ready = Gone()

    themes_global._Job(1, None, Answer()).run()


# ---- an installed color scheme is applied by name ----------------------------------


@pytest.fixture
def nordic(home, runner, use_generators):
    system = home / "system/share/color-schemes"
    system.mkdir(parents=True)
    (system / "Nordic.colors").write_text(SCHEME)
    runner.known.add("Nordic")
    use_generators(ColorSchemeGenerator())
    scheme = next(s for s in library.installed_schemes() if s.id == "Nordic")
    theme = Theme()
    for key, value in theme_edits_from_color_scheme(scheme)[0].items():
        theme.set(*key, value)
    return theme


def test_a_theme_with_the_colors_of_an_installed_scheme_applies_that_scheme(nordic, runner, home):
    result = engine.apply(nordic, runner)
    assert runner.settings["ColorScheme"] == "Nordic"
    assert not list(paths.color_schemes_dir().glob("*")) if paths.color_schemes_dir().exists() else True
    assert result.plan.wanted_targets[0].files == []
    assert engine.is_current(engine.build_plan(nordic, runner), runner)


def test_a_changed_color_is_written_as_a_scheme_of_its_own(nordic, runner):
    nordic.set("colors", "accent", "#ff0000")
    nordic.set("meta", "name", "Mine")
    engine.apply(nordic, runner)
    assert runner.settings["ColorScheme"] == "Mine"
    assert (paths.color_schemes_dir() / "Mine.colors").exists()


def test_an_exported_package_carries_its_own_scheme(nordic):
    from plasma_theme_studio import globaltheme

    nordic.set("meta", "name", "Mine")
    assert any(path.name == "Mine.colors" for path in globaltheme._plan(nordic))


# ---- a part the desktop already has is left alone ---------------------------------


def test_a_desktop_without_a_named_scheme_uses_breeze_light(window, desktop_runner, home):
    from plasma_theme_studio.ui.pages.themes_desktop import theme_edits_from_desktop

    system = home / "system/share/color-schemes"
    system.mkdir(parents=True)
    (system / "BreezeLight.colors").write_text(SCHEME.replace("Nordic", "Breeze Light"))
    desktop_runner.settings["ColorScheme"] = ""  # Plasma writes no name for its own scheme
    found, messages = theme_edits_from_desktop(desktop_runner)
    assert found[("colors", "scheme_id")] == "BreezeLight"
    assert not any("color scheme" in message for message in messages)


# ---- dark mode at night -----------------------------------------------------


def test_the_dark_mode_switch_is_an_edit_and_applies_to_kdeglobals(window, desktop_runner):
    window.show_page("themes")
    page = window.page("themes")
    assert not page.night.isChecked()
    page.night.setChecked(True)
    assert window.theme.get("desktop", "dark_at_night") is True and window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert window.theme.get("desktop", "dark_at_night") is None
    window.edit(FIELD_BY_ID[("desktop", "dark_at_night")], True)
    engine.apply(window.theme, desktop_runner)
    assert kconfig.effective_value(desktop_runner, "kdeglobals", ["KDE"], "AutomaticLookAndFeel") == "true"


def test_the_switch_shows_what_the_desktop_has_while_the_theme_leaves_it(window, desktop_runner):
    desktop_runner.set("kdeglobals", ["KDE"], "AutomaticLookAndFeel", "true")
    window.show_page("themes")
    page = window.page("themes")
    page.read_desktop()
    assert page.night.isChecked()
    assert window.theme.get("desktop", "dark_at_night") is None


def test_the_save_button_saves_the_editor_theme(window, monkeypatch):
    window.show_page("themes")
    saved = []
    monkeypatch.setattr(window, "save_as", lambda: saved.append(True) or True)
    window.page("themes").save_button.click()
    assert saved
