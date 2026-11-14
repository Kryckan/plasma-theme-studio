# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The shell of the window: side bar, page stack, Desktop bar, files dialog, state."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from plasma_theme_studio.apply.status import CHANGE, LEAVE  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID  # noqa: E402
from plasma_theme_studio.ui import pages  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.widgets import CHANGED, OFF  # noqa: E402


@pytest.fixture
def window(app, home, runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(runner)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def test_the_side_bar_lists_every_page_under_its_group(window):
    assert window.nav.keys() == [spec.key for spec in pages.PAGES]
    assert window.nav.parent().width() == 236
    assert [str(caption) for caption, _keys in pages.GROUPS] == ["", "Library", "Basics", "Desktop", "Apps"]
    for _caption, keys in pages.GROUPS:
        assert keys and all(key in pages.SPECS for key in keys)
    assert window.current_key == "overview"


def test_pages_are_made_when_they_are_first_shown(window):
    assert window.pages["overview"].built
    assert "icons" not in window.pages or not window.pages["icons"].built
    window.show_page("icons")
    assert window.pages["icons"].built and window.current_key == "icons"


def test_going_to_a_page_never_edits(window):
    for key in window.nav.keys():
        window.show_page(key)
        assert window.current_key == key
    assert window.undo_stack.count() == 0 and not window.isWindowModified()


def test_editing_never_goes_to_another_page(window):
    window.show_page("shapes")
    window.edit(FIELD_BY_ID[("shape", "radius")], 12)
    window.edit(FIELD_BY_ID[("panel_layout", "location")], "top")
    window.refresh()
    assert window.current_key == "shapes"
    assert window.stack.currentWidget() is window.page("shapes")


def test_edit_many_is_one_step_of_the_undo_stack(window):
    radius = FIELD_BY_ID[("shape", "radius")]
    window.edit_many("Choose shape", {radius: 14, ("shape", "border_width"): 2})
    assert window.theme.get("shape", "radius") == 14 and window.theme.get("shape", "border_width") == 2
    assert window.undo_stack.count() == 1 and window.undo_stack.undoText() == "Choose shape"
    window.undo_stack.undo()
    assert window.theme.get("shape", "radius") != 14
    assert window.theme.get("shape", "border_width") != 2
    window.undo_stack.redo()
    assert window.theme.get("shape", "radius") == 14 and window.theme.get("shape", "border_width") == 2


def test_edit_many_changes_nothing_when_one_value_is_refused(window):
    window.edit_many("Choose", {("shape", "radius"): 14, ("meta", "name"): "bad\\name"})
    assert window.undo_stack.count() == 0 and window.theme.get("shape", "radius") != 14


def test_the_side_bar_marks_parts_that_would_change_and_parts_left_alone(window):
    window.update_status()
    assert window.statuses
    by_key = {part.key: part.state for part in window.statuses}
    for spec in pages.PAGES:
        parts = pages.parts_of(spec.key)
        states = [by_key[key] for key in parts if key in by_key]
        if CHANGE in states:
            assert window.nav.state(spec.key) == CHANGED
        elif states and all(state == LEAVE for state in states):
            assert window.nav.state(spec.key) == OFF
        else:
            assert window.nav.state(spec.key) == ""
    assert any(window.nav.state(key) == OFF for key in window.nav.keys())


def test_the_desktop_bar_is_always_there_and_says_what_an_apply_changes(window):
    window.update_status()
    assert window.desktop_bar.isVisible() and window.desktop_bar.status.text()
    for key in ("themes", "colors", "icons", "rofi"):
        window.show_page(key)
        assert window.desktop_bar.isVisible()
    assert window.apply_button is window.desktop_bar.apply_button
    assert window.undo_apply_button is window.desktop_bar.undo_button


def test_the_files_dialog_lists_what_an_apply_writes(window):
    assert not window.files_dialog.isVisible()
    window.desktop_bar.files_button.click()
    assert window.files_dialog.isVisible()
    assert window.files_dialog.files_list.count() > 0
    window.edit(FIELD_BY_ID[("colors", "accent")], "#ff0000")
    window.refresh()  # an open dialog follows the theme
    window.files_dialog.files_list.setCurrentRow(0)
    assert window.files_dialog.file_content.toPlainText()
    window.files_dialog.hide()


def test_the_page_and_geometry_are_remembered(app, home, runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    first = MainWindow(runner)
    first.show()
    first.show_page("fonts")
    first.resize(1010, 700)
    first.close()
    assert QSettings().value("window/page") == "fonts"
    assert QSettings().value("window/geometry") is not None
    second = MainWindow(runner)
    second.show()
    assert second.current_key == "fonts"
    assert second.undo_stack.count() == 0
    second.close()


def test_an_unknown_remembered_page_opens_the_overview(app, home, runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    QSettings().setValue("window/page", "no-such-page")
    window = MainWindow(runner)
    assert window.current_key == "overview"
    window.close()


def test_closing_with_unsaved_changes_asks_first(window, monkeypatch):
    asked = []

    def answer(parent, title, text, *args):
        asked.append(title)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(answer))
    window.edit(FIELD_BY_ID[("shape", "radius")], 12)
    assert window.isWindowModified()
    assert window.close() is False and asked and window.isVisible()
    window.undo_stack.setClean()
    assert window.close() is True


def test_the_window_paints_every_page(window, app):
    for key in window.nav.keys():
        window.show_page(key)
        app.processEvents()
        assert not window.grab().isNull()
    assert window.stack.count() == len(pages.PAGES)
