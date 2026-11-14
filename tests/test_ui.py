# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

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
