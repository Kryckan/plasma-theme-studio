# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the checkers found in the window: the Overview opened late, pictures lost when a page is
left, the empty groups of the Themes page, cards that cannot be drawn, dimmed cards."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSettings, QSize  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from plasma_theme_studio.ui import pages  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.widgets import Card  # noqa: E402


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def test_the_overview_opened_after_another_page_shows_the_parts(app, home, desktop_runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    QSettings().setValue("window/page", "colors")
    window = MainWindow(desktop_runner)
    window.show()
    window.update_status()
    window.settle()
    assert window.statuses and "overview" not in window.pages
    window.show_page("overview")
    assert window.page("overview").table.rowCount() == len(window.statuses)
    window.undo_stack.setClean()
    window.close()


def test_the_overview_has_the_name_and_the_author_of_the_theme(window):
    window.show_page("overview")
    name = window.editors[("meta", "name")]
    name.set_value("Nordic Night")
    name.changed.emit("Nordic Night")
    assert window.theme.name == "Nordic Night"
    assert ("meta", "author") in window.editors


def test_pictures_still_to_come_are_asked_for_again_when_a_page_is_shown_again(window, app):
    window.show_page("icons")
    page = window.page("icons")
    app.processEvents()
    cards = [card for card in page.grid.cards if not card.has_thumbnail()]
    assert cards
    for card in cards:
        card._requested = True  # as a card that asked and was cancelled
    page.leave()
    assert all(not card._requested for card in cards)


def test_a_card_whose_picture_cannot_be_made_says_so(window, app):
    window.show_page("icons")
    page = window.page("icons")
    card = next(card for card in page.grid.cards if not card.has_thumbnail())
    page._thumbnail_ready("icons", card.item_id, QImage())
    assert card.no_preview
    assert not card.grab().isNull()


def test_the_group_my_themes_with_no_theme_says_so_and_keeps_its_size(window, app):
    window.show_page("themes")
    app.processEvents()
    grid = window.library.grid
    grid.set_items([("scheme", "Some scheme", "", "schemes")])
    grid.filter.setCurrentIndex(grid.filter.findData("mine"))
    app.processEvents()
    assert not grid.visible_cards()
    assert grid.message.isVisible()
    assert grid.message.text().startswith("A theme is a set of colors")
    assert grid.message.height() >= 96


def test_a_dimmed_card_keeps_its_words_as_they_are(app):
    def words(dimmed: bool) -> QImage:
        card = Card("a", "Papirus", "Icon theme", QSize(176, 64))
        card.resize(card.sizeHint())
        card.set_dimmed(dimmed)
        image = card.grab().toImage()
        return image.copy(10, 8 + 64 + 2, image.width() - 20, image.height() - 8 - 64 - 8)

    assert words(True) == words(False)


def test_applying_a_theme_with_unsaved_changes_says_what_happens_to_them(window, monkeypatch):
    seen = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(
            lambda parent, title, text, *a, **k: seen.append(text) or QMessageBox.StandardButton.Cancel
        ),
    )
    window.edit_many("Change", {("shape", "radius"): 11})
    assert not window._discard_ok("Applying “X” replaces the theme. Save first?")
    assert seen == ["Applying “X” replaces the theme. Save first?"]


def test_the_page_parts_the_side_bar_uses_are_the_ones_the_pages_declare(window):
    window.build_pages()
    for spec in pages.PAGES:
        assert pages.parts_of(spec.key) == window.page(spec.key).parts


def test_the_side_bar_is_marked_without_importing_the_pages(monkeypatch):
    import sys

    name = "plasma_theme_studio.ui.pages.pointers"
    monkeypatch.delitem(sys.modules, name, raising=False)
    assert pages.parts_of("pointers") == ("pointers",)
    assert name not in sys.modules


def test_a_font_left_as_it_is_shows_the_font_the_desktop_has(window):
    window.show_page("fonts")
    from plasma_theme_studio import desktopparts

    desktopparts.PARTS["fonts"].apply({"font": "Hack,11,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"}, window.runner)
    window.page("fonts").read_desktop()
    assert window.editors[("fonts", "general")].text.placeholderText() == "Hack, 11 pt"
