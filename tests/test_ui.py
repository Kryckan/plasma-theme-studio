# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from plasma_theme_studio.apply import snapshot as snapshots  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID, Theme  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, home, runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(runner)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def test_edit_undo_redo_and_preview(window, app):
    accent = FIELD_BY_ID[("colors", "accent")]
    window.edit(accent, "#ff0000")
    window.refresh()
    assert window.theme.get("colors", "accent") == "#ff0000"
    assert window.isWindowModified()
    assert "255,0,0" in window.file_content.toPlainText()
    assert window.editors[accent.id].text.text() == "#ff0000"

    window.undo_stack.undo()
    assert window.theme.get("colors", "accent") == "#3daee9"
    window.undo_stack.redo()
    assert window.theme.get("colors", "accent") == "#ff0000"
    assert not window.grab().isNull()


def test_invalid_edit_is_refused(window):
    name = FIELD_BY_ID[("meta", "name")]
    window.edit(name, "bad\\name")
    assert window.theme.name == "Breeze Light Copy"
    assert window.undo_stack.count() == 0


def test_unusable_name_disables_apply(window):
    window.edit(FIELD_BY_ID[("meta", "name")], "!!!")
    window.refresh()
    assert not window.apply_button.isEnabled()
    assert window.notice.text()


def test_low_contrast_is_pointed_out(window):
    window.edit(FIELD_BY_ID[("colors", "text")], "#eeeeee")
    window.refresh()
    assert "contrast" in window.notice.text()
    assert window.apply_button.isEnabled()


def test_apply_and_undo_last_apply(window, home, runner):
    scheme = home / ".local/share/color-schemes/BreezeLightCopy.colors"
    assert not window.undo_apply_button.isEnabled()
    window.apply_theme()
    assert scheme.exists()
    assert runner.settings["ColorScheme"] == "BreezeLightCopy"
    assert window.undo_apply_button.isEnabled()

    window.undo_last_apply()
    assert not scheme.exists()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert not window.undo_apply_button.isEnabled()


def test_save_and_open(window, home):
    path = home / "saved.toml"
    window.edit(FIELD_BY_ID[("shape", "radius")], 12)
    assert window._save_to(path)
    assert not window.isWindowModified()
    window.new_theme("breeze-dark")
    assert window.theme.get("colors", "window") == "#202326"
    assert window.open_path(path)
    assert window.theme == Theme.load(path)
    assert window.editors[("shape", "radius")].box.value() == 12


def test_applying_twice_says_nothing_changed(window):
    window.apply_theme()
    assert window.banner.isVisible() and "Applied" in window.banner.text()
    window.apply_theme()
    assert "nothing changed" in window.banner.text()
    assert len(snapshots.list_snapshots()) == 1


def test_apply_says_when_shapes_are_left_out(window):
    window.edit(FIELD_BY_ID[("shape", "radius")], 12)
    window.apply_theme()
    assert "Only the colors were applied" in window.banner.text()


def test_window_and_panel_follow_shapes_until_overridden(window):
    radius = window.editors[("panel", "radius")]
    assert radius.same.isChecked() and not radius.number.isEnabled()
    window.edit(FIELD_BY_ID[("shape", "radius")], 9)
    assert window.theme.resolved("panel", "radius") == 9
    assert radius.number.box.value() == 9

    radius.same.setChecked(False)
    radius.number.box.setValue(20)
    assert window.theme.get("panel", "radius") == 20
    assert window.theme.resolved("window", "radius") == 9
    assert "[panel]\nradius = 20" in window.theme.to_toml()
    assert Theme.from_toml(window.theme.to_toml()) == window.theme

    radius.same.setChecked(True)
    assert window.theme.get("panel", "radius") is None
    assert "radius" not in window.theme.to_toml().split("[panel]")[1]
    assert not window.grab().isNull()


@pytest.fixture
def nordic(home):
    folder = home / "system/share/color-schemes"
    folder.mkdir(parents=True)
    (folder / "Nordic.colors").write_text(
        "[Colors:Selection]\nBackgroundNormal=136,192,208\n[Colors:Window]\n"
        "BackgroundNormal=46,52,64\nForegroundNormal=216,222,233\n[General]\nName=Nordic\n"
    )


def test_switch_to_an_installed_scheme_and_back(nordic, window, runner):
    runner.known.add("Nordic")
    entry = window.library.select("Nordic")
    assert entry.title == "Nordic" and window.library.use_button.isEnabled()
    window.library.use_button.click()
    assert runner.settings["ColorScheme"] == "Nordic"
    assert "In use" in window.library.list.currentItem().text()
    window.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert "In use" not in window.library.list.currentItem().text()


def test_edit_a_copy_of_an_installed_scheme(nordic, window):
    window.library.select("Nordic")
    window.library.edit_button.click()
    assert window.theme.name == "Nordic Copy"
    assert window.theme.get("colors", "window") == "#2e3440"
    assert window.tabs.currentWidget() is window.preview
    assert window.path is None


def test_saved_themes_are_listed_and_can_be_used(window, home, runner):
    window.edit(FIELD_BY_ID[("meta", "name")], "Mine")
    assert window._save_to(home / ".local/share/plasma-theme-studio/themes/mine.toml")
    window.new_theme("breeze-dark")
    entry = window.library.select("Mine")
    assert entry.is_saved_theme
    window.library.search.setText("zzz")
    assert window.library.current() is None and not window.library.use_button.isEnabled()
    window.library.search.clear()
    window.library.select("Mine")
    window.library.use_button.click()
    assert runner.settings["ColorScheme"] == "Mine"
    # The scheme written for it does not show up as a second entry.
    titles = [window.library.list.item(row).text() for row in range(window.library.list.count())]
    assert len([title for title in titles if title.startswith("Mine")]) == 1
    window.library.edit_button.click()
    assert window.theme.name == "Mine" and window.path.name == "mine.toml"
