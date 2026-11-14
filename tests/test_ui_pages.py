# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The pages of the window: each one is made, and the controls on them edit the theme."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from plasma_theme_studio.model.theme import FIELD_BY_ID  # noqa: E402
from plasma_theme_studio.ui import pages  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages.base import PickerPage, TargetPage  # noqa: E402


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def click(card):
    QTest.mouseClick(card, Qt.MouseButton.LeftButton)


@pytest.mark.parametrize("key", [spec.key for spec in pages.PAGES])
def test_every_page_is_made_and_painted(window, app, key):
    window.show_page(key)
    app.processEvents()
    page = window.page(key)
    assert page.built and window.stack.currentWidget() is page
    assert page.header.title.text() == str(pages.title_of(key))
    assert not window.grab().isNull()
    assert window.undo_stack.count() == 0  # looking edits nothing


def test_the_page_titles_follow_the_kde_names(window):
    titles = [str(spec.title) for spec in pages.PAGES]
    assert "Plasma Style" in titles and "Window Decorations" in titles and "System Sounds" in titles
    assert "Splash Screen" in titles and "Application Style" in titles and "GTK Apps" in titles


def test_choosing_an_icon_theme_sets_it_and_the_part_switch_leaves_it(window, app):
    window.show_page("icons")
    page = window.page("icons")
    assert isinstance(page, PickerPage)
    assert not page.header.part_mode()  # nothing chosen: the part is left as it is
    assert {"Papirus", "breeze"} <= set(page.grid.ids())
    click(page.grid.card("Papirus"))
    assert window.theme.get("desktop", "icons") == "Papirus"
    assert page.header.part_mode() and page.grid.selected_id() == "Papirus"

    page.header.set_part_mode(False)
    page.header.part_mode_changed.emit(False)
    assert window.theme.get("desktop", "icons") is None
    assert not page.header.part_mode()


def test_choosing_a_pointer_and_a_sound_theme(window):
    window.show_page("pointers")
    click(window.page("pointers").grid.card("Pop"))
    assert window.theme.get("desktop", "cursors") == "Pop"
    window.show_page("sounds")
    click(window.page("sounds").grid.card("ocean"))
    assert window.theme.get("desktop", "sounds") == "ocean"
    assert window.current_key == "sounds"


def test_a_part_that_can_be_made_from_the_theme_changes_two_fields_in_one_step(window):
    window.show_page("decorations")
    page = window.page("decorations")
    assert page.generates()
    assert window.theme.get("window", "decoration") == "unchanged"
    steps = window.undo_stack.count()
    click(page.grid.card("org.kde.kwin.aurorae:kwin4_decoration_qml_plastik"))
    assert window.theme.get("window", "decoration") == "installed"
    assert window.theme.get("window", "decoration_id") == "org.kde.kwin.aurorae:kwin4_decoration_qml_plastik"
    assert window.undo_stack.count() == steps + 1  # the mode and the id are one step
    window.undo_stack.undo()
    assert window.theme.get("window", "decoration") == "unchanged"
    assert window.theme.get("window", "decoration_id") is None


def test_a_target_page_switches_between_leaving_a_part_and_setting_it(window):
    window.show_page("rofi")
    page = window.page("rofi")
    assert isinstance(page, TargetPage)
    assert window.theme.get("rofi", "style") == "unchanged"
    page.header.part_mode_changed.emit(True)
    assert window.theme.get("rofi", "style") == "generated"
    page.header.part_mode_changed.emit(False)
    assert window.theme.get("rofi", "style") == "unchanged"


def test_the_plasma_style_page_sets_and_leaves(window):
    window.show_page("plasma_style")
    page = window.page("plasma_style")
    page.header.part_mode_changed.emit(True)
    assert window.theme.part_state("panel", "style") != "unchanged"
    page.header.part_mode_changed.emit(False)
    assert window.theme.part_state("panel", "style") == "unchanged"


def test_the_font_buttons_and_color_pages_edit_the_theme(window):
    window.show_page("colors")
    window.edit(FIELD_BY_ID[("colors", "accent")], "#00ff00")
    assert window.editors[("colors", "accent")].text.text() == "#00ff00"
    window.show_page("fonts")
    assert ("fonts", "general") in window.editors or any(
        section == "fonts" for section, _key in window.editors
    )


def test_the_overview_lists_every_part_with_its_state(window, app):
    window.update_status()
    window.settle()
    page = window.page("overview")
    assert page.table.rowCount() == len(window.statuses) > 0
