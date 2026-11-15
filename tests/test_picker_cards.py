# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The picker pages' cards: read in the background, the full width, a badge that hides nothing, chips."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QCoreApplication, QRect  # noqa: E402
from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.widgets import JustifiedFlow, Segmented  # noqa: E402


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.resize(1100, 720)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def test_the_cards_arrive_from_the_worker(window, pickers_in_background):
    window.show_page("icons")
    page = window.page("icons")
    page.wait_items()
    QCoreApplication.processEvents()
    assert not page.items_loading
    assert page.desktop_state is not None


def test_the_pointer_size_chooser_is_in_the_always_visible_bar(window):
    window.show_page("pointers")
    page = window.page("pointers")
    assert page.size_box.parent() is page.grid.bar
    assert page.size_box.isVisibleTo(page)


def test_cards_share_the_whole_width(app):
    host = QWidget()
    flow = JustifiedFlow(host)
    for _ in range(9):
        child = QWidget(host)
        child.setFixedSize(200, 100)
        flow.addWidget(child)
    flow.setGeometry(QRect(0, 0, 1100, 800))
    rights = [flow.itemAt(i).geometry().right() for i in range(9)]
    assert max(rights) >= 1100 - 30  # no dead strip at the right edge


def test_the_chip_is_readable_checked_and_not(app):
    chips = Segmented(["One", "Two"], name="Kinds")
    chips.show()
    chips.set_current(1)
    assert chips.current() == 1
    pixmap = chips.grab()
    assert not pixmap.isNull()
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#202428"))
    chips.setPalette(palette)
    assert not chips.grab().isNull()


def test_the_empty_my_themes_offers_the_two_buttons(app):
    from plasma_theme_studio.ui.library_view import LibraryView

    view = LibraryView()
    seen = []
    view.new_requested.connect(lambda: seen.append("new"))
    view.save_requested.connect(lambda: seen.append("save"))
    view.mine_new.click()
    view.mine_save.click()
    assert seen == ["new", "save"]
