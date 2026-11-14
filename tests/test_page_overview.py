# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Overview page: the two cards, the list of parts, the recent applies, the links."""

from datetime import datetime, timedelta

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QLineEdit  # noqa: E402

from plasma_theme_studio.apply import snapshot as snapshots  # noqa: E402
from plasma_theme_studio.apply.status import BLOCKED, CHANGE, LEAVE, SAME, PartStatus  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages.overview import page_of, when_text  # noqa: E402


@pytest.fixture
def window(app, home, desktop_runner):
    window = MainWindow(desktop_runner)
    window.resize(1100, 720)
    window.show()
    window.show_page("overview")
    yield window
    window.undo_stack.setClean()
    window.close()


@pytest.fixture
def page(window):
    return window.page("overview")


translate = QCoreApplication.translate


def parts():
    return [
        PartStatus("colors", "Colors", "Breeze Light", "Studio", CHANGE),
        PartStatus("icons", "Icons", "Breeze", "Breeze", SAME),
        PartStatus("fonts", "Fonts", "Default", "Default", LEAVE),
        PartStatus("splash", "Splash Screen", "Breeze", "No such splash", BLOCKED),
    ]


def test_one_row_per_part_with_its_state(page):
    page.fill(parts())
    assert page.table.rowCount() == 4
    assert [row.state for row in page.table.rows] == [CHANGE, SAME, LEAVE, BLOCKED]
    assert "Breeze Light" in page.table.rows[0].values.text() and "Studio" in page.table.rows[0].values.text()
    assert page.table.rows[1].values.text() == "Breeze"  # nothing to arrow when it is already so
    assert page.table.rows[2].values.text() == "Default"
    assert page.table.message.isHidden()


def test_a_blocked_row_says_why(page):
    page.fill(parts())
    row = page.table.rows[3]
    assert "No such splash" in row.toolTip() and "Splash Screen" in row.toolTip()
    assert page.table.rows[0].toolTip() == ""


def test_a_click_opens_the_page_of_the_part(window, page):
    page.fill(parts())
    page.table.rows[1].click()
    assert window.page(page_of("icons")).isVisible()


def test_return_and_space_open_the_page_too(window, page):
    page.fill(parts())
    for key in (Qt.Key.Key_Return, Qt.Key.Key_Space):
        window.show_page("overview")
        row = page.table.rows[0]
        row.setFocus()
        QTest.keyClick(row, key)
        assert window.page(page_of("colors")).isVisible(), key


def test_the_rows_can_be_reached_with_the_keyboard(page):
    page.fill(parts())
    assert all(row.focusPolicy() == Qt.FocusPolicy.StrongFocus for row in page.table.rows)
    assert all(row.accessibleName() for row in page.table.rows)


def test_an_empty_status_is_a_sentence_not_an_empty_list(page):
    page.fill([])
    assert page.table.rowCount() == 0
    assert not page.table.message.isHidden() and page.table.message.text()


def test_an_unreadable_desktop_is_a_sentence(page):
    unreadable = translate("core", "Could not be read")
    page.fill([PartStatus("colors", "Colors", unreadable, "x", CHANGE)])
    assert page.table.rowCount() == 0 and page.table.message.text()


def test_rows_are_kept_while_the_parts_stay(page):
    page.fill(parts())
    first = page.table.rows[0]
    page.fill(parts()[:4])
    assert page.table.rows[0] is first


def test_the_cards_show_the_desktop_and_the_editor(window, page):
    window.edit(FIELD_BY_ID[("meta", "name")], "Studio Demo")
    page.refresh()
    assert page.editor_line.text() == "Studio Demo"
    assert page.desktop_line.text()


def test_name_and_author_are_editable(window, page):
    editors = page.findChildren(QLineEdit)
    assert len(editors) >= 2
    for editor, text in ((editors[0], "Typed name"), (editors[1], "Someone")):
        editor.selectAll()
        QTest.keyClicks(editor, text)
        QTest.keyClick(editor, Qt.Key.Key_Return)
    assert window.theme.get("meta", "name") == "Typed name"
    assert window.theme.get("meta", "author") == "Someone"
    window.undo_stack.undo()
    assert window.theme.get("meta", "author") != "Someone"


def test_recent_is_empty_at_first(page):
    assert not page.recent_empty.isHidden()
    assert page.recent_labels == []


def test_recent_lists_the_last_three_applies(window, page, home):
    for number in range(4):
        snapshots.create(f"Theme {number}", [], {})
    page.read_desktop()
    assert len(page.recent_labels) == 3
    assert page.recent_empty.isHidden()
    assert "Applied Theme 3" in page.recent_labels[0][1].text()


def test_when_text_is_plain(app):
    now = datetime(2026, 5, 10, 12, 0)
    assert "12:00" in when_text(now, now)
    assert when_text(now - timedelta(days=1), now) != when_text(now, now)
    assert when_text(now - timedelta(days=40), now)


def test_snapshots_and_files_buttons_open_their_dialogs(window, page, monkeypatch):
    seen = []
    monkeypatch.setattr(window, "show_snapshots", lambda: seen.append("snapshots"))
    monkeypatch.setattr(window, "show_files", lambda: seen.append("files"))
    page.snapshots_button.clicked.disconnect()
    page.files_button.clicked.disconnect()
    page.snapshots_button.clicked.connect(window.show_snapshots)
    page.files_button.clicked.connect(window.show_files)
    page.snapshots_button.click()
    page.files_button.click()
    assert seen == ["snapshots", "files"]
    assert page.files_button.text().startswith("Show the files")
