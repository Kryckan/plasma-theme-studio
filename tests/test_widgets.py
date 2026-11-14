# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEvent, QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPalette  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QColorDialog, QScrollArea, QVBoxLayout, QWidget  # noqa: E402

from plasma_theme_studio.ui.widgets import (  # noqa: E402
    CHANGED,
    OFF,
    Card,
    CardGrid,
    ColorDots,
    DesktopBar,
    FlowLayout,
    InlineNote,
    NavList,
    PageHeader,
    Segmented,
)

K = Qt.Key


def make_grid(app, count=10, width=700, **kwargs):
    grid = CardGrid(**kwargs)
    grid.set_items([(f"k{i}", f"Item {i}", f"Note {i}") for i in range(count)])
    grid.resize(width, 500)
    grid.show()
    app.processEvents()
    app.processEvents()
    return grid


def per_row(grid):
    first = grid.cards[0].geometry().y()
    return len([c for c in grid.cards if c.geometry().y() == first])


def press(grid, *keys):
    for key in keys:
        QTest.keyClick(grid.body, key)


def test_keyboard_navigation(app):
    grid = make_grid(app)
    assert per_row(grid) == 3
    picked = []
    grid.selected.connect(picked.append)
    grid.set_selected("k0")
    grid.body.setFocus()
    press(grid, K.Key_Right, K.Key_Right, K.Key_Down, K.Key_Left, K.Key_Up, K.Key_End, K.Key_Home)
    assert picked == ["k1", "k2", "k5", "k4", "k1", "k9", "k0"]
    assert grid.selected_id() == "k0"
    press(grid, K.Key_Left, K.Key_Up)  # at the edges nothing moves and nothing is emitted
    assert len(picked) == 7
    press(grid, K.Key_PageDown)
    assert grid.selected_id() in ("k3", "k6", "k9")
    grid.close()


def test_down_from_a_short_last_row_stays_put_below_it(app):
    grid = make_grid(app)
    grid.set_selected("k9")
    grid.body.setFocus()
    press(grid, K.Key_Down)
    assert grid.selected_id() == "k9"
    grid.close()


def test_return_and_space_activate(app):
    grid = make_grid(app)
    activated = []
    grid.activated.connect(activated.append)
    grid.set_selected("k4")
    grid.body.setFocus()
    press(grid, K.Key_Return, K.Key_Space)
    assert activated == ["k4", "k4"]
    grid.close()


def test_click_selects_and_never_clears(app):
    grid = make_grid(app)
    picked = []
    grid.selected.connect(picked.append)
    QTest.mouseClick(grid.card("k2"), Qt.MouseButton.LeftButton)
    QTest.mouseClick(grid.card("k2"), Qt.MouseButton.LeftButton)
    assert picked == ["k2", "k2"]
    assert grid.card("k2").isChecked()
    assert [c.item_id for c in grid.cards if c.isChecked()] == ["k2"]
    grid.close()


def test_set_selected_is_quiet_and_exclusive(app):
    grid = make_grid(app)
    picked = []
    grid.selected.connect(picked.append)
    grid.set_selected("k1")
    grid.set_selected("k3")
    assert picked == []
    assert [c.item_id for c in grid.cards if c.isChecked()] == ["k3"]
    grid.set_selected(None)
    assert grid.selected_id() is None and not any(c.isChecked() for c in grid.cards)
    grid.close()


def test_search_filters_and_shows_no_match(app):
    grid = make_grid(app)
    grid.search.setText("item 7")
    assert [c.item_id for c in grid.visible_cards()] == ["k7"]
    assert grid.message.isHidden()
    grid.search.setText("zzz")
    assert grid.visible_cards() == []
    assert not grid.message.isHidden()
    assert "matches" in grid.message.text()
    assert grid.scroll.isHidden()
    grid.search.setText("note 3")  # the subtitle is searched too
    assert [c.item_id for c in grid.visible_cards()] == ["k3"]
    grid.search.clear()
    assert len(grid.visible_cards()) == 10
    grid.close()


def test_navigation_skips_hidden_and_disabled_cards(app):
    grid = make_grid(app)
    grid.set_item_enabled("k1", False)
    grid.set_selected("k0")
    grid.body.setFocus()
    press(grid, K.Key_Right)
    assert grid.selected_id() == "k2"
    grid.close()


def test_typing_goes_to_search_or_jumps(app):
    grid = make_grid(app)
    grid.set_selected("k0")
    grid.body.setFocus()
    QTest.keyClicks(grid.body, "7")
    assert grid.search.text() == "7"
    plain = make_grid(app, with_search=False)
    plain.set_items([("a", "Apple", ""), ("b", "Banana", ""), ("c", "Cherry", "")])
    plain.body.setFocus()
    QTest.keyClick(plain.body, K.Key_C)
    assert plain.selected_id() == "c"
    grid.close()
    plain.close()


def test_filter_combo(app):
    grid = make_grid(app, count=0)
    grid.set_items([("a", "A", "", "mine"), ("b", "B", "", "system"), ("c", "C", "", "mine")])
    grid.set_filters([("mine", "Mine"), ("system", "System")])
    assert not grid.filter.isHidden()
    grid.filter.setCurrentIndex(1)
    assert [c.item_id for c in grid.visible_cards()] == ["a", "c"]
    grid.filter.setCurrentIndex(0)
    assert len(grid.visible_cards()) == 3
    grid.close()


def test_empty_state(app):
    grid = CardGrid(empty_text="No icon themes are installed.")
    grid.resize(400, 300)
    grid.show()
    assert grid.message.text() == "No icon themes are installed."
    assert grid.search.isHidden()
    grid.set_items([("a", "A", "")])
    assert grid.message.isHidden() and not grid.search.isHidden()
    grid.close()


def test_thumbnail_before_and_after_the_card_is_shown(app):
    grid = CardGrid()
    red = QImage(10, 10, QImage.Format.Format_RGB32)
    red.fill(QColor("red"))
    grid.set_items([("a", "A", ""), ("b", "B", "")])
    grid.set_thumbnail("a", red)  # before the grid is shown
    grid.resize(500, 300)
    assert grid.card("a")._pixmap is None  # no pixmap until it is needed
    wanted = []
    grid.thumbnail_requested.connect(wanted.append)
    grid.show()
    app.processEvents()
    app.processEvents()
    assert grid.card("a")._pixmap is not None
    assert wanted == ["b"]  # only the card without a thumbnail asks for one
    blue = QImage(10, 10, QImage.Format.Format_RGB32)
    blue.fill(QColor("blue"))
    grid.set_thumbnail("b", blue)  # after it is shown
    image = grid.card("b").grab().toImage()
    assert image.pixelColor(30, 30) == QColor("blue")
    # a thumbnail that arrived early survives a new list
    grid.set_items([("b", "B", ""), ("c", "C", "")])
    assert grid.card("b").has_thumbnail() and not grid.card("c").has_thumbnail()
    grid.close()


def test_in_use_and_selected_together(app):
    grid = make_grid(app, count=3)
    grid.set_in_use("k1")
    grid.set_selected("k1")
    card = grid.card("k1")
    assert card.isChecked() and card.in_use
    assert "In use" in card.accessibleDescription() and "Selected" in card.accessibleDescription()
    grid.set_in_use("k2")
    assert not card.in_use and grid.card("k2").in_use and not grid.card("k2").isChecked()
    assert card.grab().toImage().size().width() > 0
    # both marks survive replacing the cards
    grid.set_items([("k1", "One", ""), ("k2", "Two", "")])
    assert grid.card("k1").isChecked() and grid.card("k2").in_use
    grid.close()


def test_card_actions(app):
    grid = make_grid(app, count=3)
    removed, menus = [], []
    grid.remove_requested.connect(removed.append)
    grid.menu_requested.connect(lambda i, pos: menus.append(i))
    grid.set_item_action("k0", "remove", "Remove")
    grid.set_item_action("k1", "menu")
    grid.set_selected("k0")
    card = grid.card("k0")
    QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=card._action_rect().center().toPoint())
    assert removed == ["k0"]
    grid.body.setFocus()
    press(grid, K.Key_Delete)
    assert removed == ["k0", "k0"]
    grid.set_selected("k1")
    other = grid.card("k1")
    QTest.mouseClick(other, Qt.MouseButton.LeftButton, pos=other._action_rect().center().toPoint())
    assert menus == ["k1"]
    grid.close()


def test_two_hundred_cards_make_no_pixmaps_until_shown(app):
    grid = CardGrid()
    grid.set_items([(f"i{n}", f"Item {n}", "") for n in range(200)])
    for n in range(200):
        grid.set_thumbnail(f"i{n}", QImage(176, 110, QImage.Format.Format_RGB32))
    assert all(c._pixmap is None for c in grid.cards)
    grid.resize(900, 500)
    grid.show()
    app.processEvents()
    made = [c for c in grid.cards if c._pixmap is not None]
    assert 0 < len(made) < 60  # the cards in view only
    grid.close()


def test_fit_grid_height_follows_its_content(app):
    page = QWidget()
    lay = QVBoxLayout(page)
    grid = CardGrid(fit=True)
    grid.set_items([(f"k{i}", f"Item {i}", "") for i in range(7)])
    lay.addWidget(grid)
    lay.addStretch(1)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(page)
    scroll.resize(700, 300)
    scroll.show()
    app.processEvents()
    wide = grid.height()
    scroll.resize(420, 300)
    app.processEvents()
    app.processEvents()
    assert grid.height() > wide  # fewer per row: more rows, taller
    assert grid.height() >= grid.flow.heightForWidth(grid.width())
    assert page.height() >= grid.height()  # the page grows with it, so the scroll area scrolls
    scroll.close()


def test_flow_layout_height_for_width(app):
    host = QWidget()
    flow = FlowLayout(host, h=10, v=10)
    flow.setContentsMargins(0, 0, 0, 0)
    for _ in range(6):
        w = QWidget(host)
        w.setFixedSize(100, 40)
        flow.addWidget(w)
    assert flow.hasHeightForWidth()
    assert flow.heightForWidth(1000) == 40
    assert flow.heightForWidth(220) == 40 * 3 + 2 * 10  # two per row, three rows
    assert flow.heightForWidth(220) == flow.heightForWidth(215)
    assert flow.heightForWidth(110) == 6 * 40 + 5 * 10
    flow.setContentsMargins(5, 5, 5, 5)
    assert flow.heightForWidth(1000) == 50


def test_flow_layout_mirrors_in_right_to_left(app):
    host = QWidget()
    flow = FlowLayout(host, h=10, v=10)
    flow.setContentsMargins(0, 0, 0, 0)
    widgets = []
    for _ in range(2):
        w = QWidget(host)
        w.setFixedSize(100, 40)
        flow.addWidget(w)
        widgets.append(w)
    host.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    host.resize(500, 100)
    flow.setGeometry(host.rect())
    assert widgets[0].geometry().right() == 499
    assert widgets[1].geometry().right() < widgets[0].geometry().left()


def test_nav_list_skips_captions(app):
    nav = NavList()
    nav.add_group("LIBRARY")
    nav.add_page("themes", "Themes")
    nav.add_group("BASICS")
    nav.add_page("colors", "Colors", state=CHANGED)
    nav.add_page("fonts", "Fonts", state=OFF)
    changes = []
    nav.current_changed.connect(changes.append)
    nav.resize(240, 400)
    nav.show()
    nav.set_current("themes")
    QTest.keyClick(nav, K.Key_Down)
    QTest.keyClick(nav, K.Key_Down)
    QTest.keyClick(nav, K.Key_Up)
    QTest.keyClick(nav, K.Key_Up)
    QTest.keyClick(nav, K.Key_Up)  # a caption is above: nothing happens
    assert changes == ["themes", "colors", "fonts", "colors", "themes"]
    assert nav.current_key() == "themes"
    assert nav.keys() == ["themes", "colors", "fonts"]
    assert nav.state("colors") == CHANGED
    nav.set_state("colors", "")
    assert nav.state("colors") == ""
    assert "left as it is" in nav._item("fonts").data(Qt.ItemDataRole.AccessibleTextRole)
    assert nav.grab().width() > 0
    nav.close()


def test_segmented_is_exclusive(app):
    seg = Segmented(["One", "Two", "Three"], current=1)
    seg.show()
    chosen = []
    seg.changed.connect(chosen.append)
    assert seg.current() == 1
    QTest.mouseClick(seg.button(2), Qt.MouseButton.LeftButton)
    assert seg.current() == 2 and chosen == [2]
    assert [seg.button(i).isChecked() for i in range(3)] == [False, False, True]
    QTest.mouseClick(seg.button(2), Qt.MouseButton.LeftButton)  # the checked one stays checked
    assert seg.button(2).isChecked()
    seg.set_current(0)
    assert seg.current() == 0 and chosen == [2, 2]
    seg.setFocus()
    QTest.keyClick(seg, K.Key_Right)
    assert seg.current() == 1
    seg.close()


def test_page_header_switch(app):
    header = PageHeader("Icons", "Icon themes")
    switch = header.add_part_switch()
    header.set_hint("Writes the icon theme.")
    header.show()
    modes = []
    header.part_mode_changed.connect(modes.append)
    assert header.part_mode()
    QTest.mouseClick(switch.button(0), Qt.MouseButton.LeftButton)
    assert modes == [False] and not header.part_mode()
    header.set_part_mode(True)
    assert modes == [False] and header.part_mode()
    header.set_subtitle("")
    assert header.subtitle.isHidden()
    header.close()
    header.deleteLater()


def test_inline_note(app):
    note = InlineNote("Long " * 80, "warning", action_text="Fix")
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.addWidget(note)
    lay.addStretch(1)
    page.resize(300, 600)
    page.show()
    app.processEvents()
    assert note.label.wordWrap()
    assert note.label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert note.height() > 80  # wrapped over several lines
    clicks = []
    note.action_triggered.connect(lambda: clicks.append(1))
    QTest.mouseClick(note.action, Qt.MouseButton.LeftButton)
    assert clicks == [1]
    assert InlineNote("x").action.isHidden()
    page.close()


def test_desktop_bar(app):
    bar = DesktopBar()
    bar.show()
    bar.set_status("6 parts will change when you apply.", pending=True)
    assert bar.pending() and "6 parts" in bar.status.text()
    assert bar.apply_button.isDefault()
    assert bar.snapshots_button.text() == "Snapshots…"
    assert bar.undo_button.text() == "Undo last apply"
    assert bar.apply_button.text() == "Apply to Desktop"
    bar.close()


def test_color_dots(app, monkeypatch):
    dots = ColorDots(["#2b6a99", "#4fa3d9", "#e0b05a"])
    dots.show()
    picked = []
    dots.picked.connect(picked.append)
    dots.set_current("#4fa3d9")
    assert dots.current().name() == "#4fa3d9" and picked == []
    swatch = dots._all()[2]
    QTest.mouseClick(swatch, Qt.MouseButton.LeftButton)
    assert [c.name() for c in picked] == ["#e0b05a"]
    assert [b.isChecked() for b in dots._all()].count(True) == 1
    monkeypatch.setattr(QColorDialog, "getColor", lambda *a, **k: QColor("#123456"))
    dots.custom_button.click()
    assert picked[-1].name() == "#123456" and dots.current().name() == "#123456"
    assert [b.isChecked() for b in dots._all()].count(True) == 1
    dots.set_current(None)
    assert dots.current() is None
    dots.close()


def dark_palette():
    p = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#31363b"),
        (QPalette.ColorRole.WindowText, "#eff0f1"),
        (QPalette.ColorRole.Base, "#232629"),
        (QPalette.ColorRole.Text, "#eff0f1"),
        (QPalette.ColorRole.Button, "#31363b"),
        (QPalette.ColorRole.ButtonText, "#eff0f1"),
        (QPalette.ColorRole.Highlight, "#3daee9"),
        (QPalette.ColorRole.HighlightedText, "#232629"),
    ):
        p.setColor(role, QColor(color))
    return p


def test_widgets_survive_a_palette_change(app):
    host = QWidget()
    lay = QVBoxLayout(host)
    grid = CardGrid(fit=True)
    grid.set_items([("a", "A", "x"), ("b", "B", "")])
    grid.set_selected("a")
    grid.set_in_use("b")
    nav = NavList()
    nav.add_group("G")
    nav.add_page("p", "Page", state=CHANGED)
    seg = Segmented(["One", "Two"])
    dots = ColorDots(["#2b6a99", "#4fa3d9"])
    dots.set_current("#4fa3d9")
    bar = DesktopBar()
    for w in (grid, nav, seg, dots, bar, InlineNote("Text", "positive"), PageHeader("T", "S")):
        lay.addWidget(w)
    host.resize(600, 800)
    host.show()
    app.processEvents()
    before = grid.card("a").grab().toImage().pixelColor(2, 40)
    old = app.palette()
    try:
        app.setPalette(dark_palette())
        for w in host.findChildren(QWidget):
            QCoreApplicationSend(w)
        app.processEvents()
        after = grid.card("a").grab().toImage().pixelColor(2, 40)
        assert before != after
        for w in (grid.card("a"), nav, seg.button(0), dots, bar):
            assert not w.grab().isNull()
    finally:
        app.setPalette(old)
    host.close()


def QCoreApplicationSend(widget):
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.sendEvent(widget, QEvent(QEvent.Type.PaletteChange))


def test_card_size_follows_thumbnail_size(app):
    card = Card("a", "A", "", QSize(176, 64))
    assert card.sizeHint().width() == 176 + 16
    assert card.sizeHint().height() < Card("b", "B", "", QSize(176, 110)).sizeHint().height()


def test_item_text_is_never_rich_text(app):
    from PySide6.QtCore import Qt

    grid = CardGrid(empty_text="<b>none</b>")
    header = PageHeader("<b>Icons", "<i>themes")
    plain = Qt.TextFormat.PlainText
    assert grid.message.textFormat() == plain
    assert header.title.textFormat() == plain and header.subtitle.textFormat() == plain
