# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Window Decorations, Plasma Style and Panel pages: every action a person can take on them."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from plasma_theme_studio.model.theme import FIELD_BY_ID  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages import panel as panel_module  # noqa: E402
from plasma_theme_studio.ui.pages.base import BREEZE_ADJUSTED, THIS_THEME  # noqa: E402
from plasma_theme_studio.ui.pages.decorations_buttons import ButtonBoard, TitlebarButtonsDialog  # noqa: E402
from plasma_theme_studio.ui.pages.panel_screen import ScreenChooser  # noqa: E402


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def click(widget, pos=None):
    if pos is None:
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    else:
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)


def page_of(window, key):
    window.show_page(key)
    window.refresh()
    return window.page(key)


# ---- Window Decorations


def test_the_border_size_is_chosen_in_the_top_row(window):
    page = page_of(window, "decorations")
    assert page.border_size is window.editors[("window", "border_size")]
    steps = window.undo_stack.count()
    page.border_size.choose("Large")
    assert window.theme.get("window", "border_size") == "Large"
    assert window.undo_stack.count() == steps + 1
    page.border_size.choose(None)
    assert window.theme.get("window", "border_size") is None


def test_the_border_tooltip_says_when_the_frame_draws_its_own_border(window):
    page = page_of(window, "decorations")
    click(page.grid.card(THIS_THEME))
    window.refresh()
    assert "draws its own border" in page.border_size.toolTip()
    click(page.grid.card(BREEZE_ADJUSTED))
    window.refresh()
    assert "draws its own border" not in page.border_size.toolTip()
    assert "any window decoration" in page.border_size.toolTip()


def test_the_frame_tuning_and_the_large_preview_show_for_this_theme_and_breeze_only(window):
    page = page_of(window, "decorations")
    assert not page.frame_box.isVisible()
    click(page.grid.card(THIS_THEME))
    window.refresh()
    assert page.frame_box.isVisible() and page.frame_preview.isVisible()
    assert window.editors[("window", "radius")].isEnabled()
    assert not page.frame_hint.isVisible()
    click(page.grid.card(BREEZE_ADJUSTED))
    window.refresh()
    assert page.frame_box.isVisible() and page.frame_hint.isVisible()
    assert not window.editors[("window", "radius")].isEnabled()
    other = next(i for i in page.grid.ids() if i not in (THIS_THEME, BREEZE_ADJUSTED))
    click(page.grid.card(other))
    window.refresh()
    assert not page.frame_box.isVisible()
    page.header.set_part_mode(False)
    page.header.part_mode_changed.emit(False)
    window.refresh()
    assert not page.frame_box.isVisible()


def test_the_breeze_preview_uses_the_corners_and_border_breeze_has(window):
    page = page_of(window, "decorations")
    window.edit(FIELD_BY_ID[("window", "radius")], 20)
    click(page.grid.card(BREEZE_ADJUSTED))
    window.refresh()
    shown = page.frame_preview.theme
    assert shown.get("window", "radius") == 5 and shown.get("window", "border_width") == 1
    assert window.theme.get("window", "radius") == 20  # only the picture is changed


def test_the_frame_values_edit_the_theme(window):
    page = page_of(window, "decorations")
    click(page.grid.card(THIS_THEME))
    window.refresh()
    steps = window.undo_stack.count()
    window.edit(FIELD_BY_ID[("window", "radius")], 12)
    assert window.theme.get("window", "radius") == 12
    assert window.undo_stack.count() > steps


def test_looking_at_the_three_pages_edits_nothing(window, app):
    for key in ("decorations", "plasma_style", "panel"):
        page_of(window, key)
        app.processEvents()
    assert window.undo_stack.count() == 0


# ---- the title bar buttons board


@pytest.fixture
def board(app):
    board = ButtonBoard("MSE", "HIAX")
    board.resize(600, 160)
    board.show()
    return board


def test_the_board_moves_a_button_within_its_side(board):
    board.select("left", 0)
    assert board.can_move(1) and not board.can_move(-1)
    board.move(1)
    assert board.text("left") == "SME" and board.selected == ("left", 1)
    board.move(-1)
    assert board.text("left") == "MSE"
    board.select("left", 2)
    board.move(1)  # at the end already
    assert board.text("left") == "MSE"


def test_the_board_adds_removes_and_never_repeats_a_button(board):
    board.select("left", 1)
    board.remove()
    assert board.text("left") == "ME" and "S" in board.pool()
    board.add("right")
    assert board.text("right") == "HIAXS"
    assert "S" not in board.pool()
    letters = board.text("left") + board.text("right")
    assert len(set(letters)) == len(letters)
    board.select("right", 0)
    board.add("left")
    assert board.text("left").endswith("H") and "H" not in board.text("right")
    board.select("pool", 0)
    assert not board.can_move(1) and not board.can_remove()


def test_the_spacer_can_be_added_again_and_again(board):
    board.select("pool", board.pool().index("_"))
    board.add("left")
    board.select("pool", board.pool().index("_"))
    board.add("left")
    assert board.text("left").count("_") == 2 and "_" in board.pool()


def test_the_board_drag_and_drop_by_place(board):
    board.place("pool", board.pool().index("B"), "left", 1)
    assert board.text("left") == "MBSE"
    board.place("right", 0, "left", 0)
    assert board.text("left") == "HMBSE" and board.text("right") == "IAX"
    board.place("left", 0, "pool", 0)
    assert "H" in board.pool()


def test_the_board_drag_with_the_mouse(board):
    items = {(zone, index): rect for zone, index, rect in board.items()}
    start = items[("left", 0)].center().toPoint()
    end = items[("right", 1)].center().toPoint()
    QTest.mousePress(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for step in range(1, 11):
        point = start + (end - start) * step / 10
        QTest.mouseMove(board, QPoint(int(point.x()), int(point.y())))
    QTest.mouseRelease(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    assert "M" not in board.text("left") and "M" in board.text("right")


def test_a_click_on_a_button_chooses_it(board):
    rect = next(r for zone, index, r in board.items() if (zone, index) == ("right", 2))
    click(board, rect.center().toPoint())
    assert board.selected == ("right", 2) and board.selected_letter() == "A"


def test_the_board_keys(board):
    board.select("left", 0)
    board.setFocus()
    QTest.keyClick(board, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    assert board.text("left") == "SME"
    QTest.keyClick(board, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
    assert board.text("left") == "MSE"
    QTest.keyClick(board, Qt.Key.Key_Right)
    assert board.selected == ("left", 1)
    QTest.keyClick(board, Qt.Key.Key_Delete)
    assert board.text("left") == "ME"


# ---- the dialog


def open_dialog(window):
    page = page_of(window, "decorations")
    click(page.buttons_button)
    dialog = page.buttons_dialog
    assert isinstance(dialog, TitlebarButtonsDialog) and dialog.isVisible()
    return page, dialog


def test_the_dialog_starts_from_the_desktop_and_leaving_stores_nothing(window):
    _page, dialog = open_dialog(window)
    assert dialog.leave.isChecked() and not dialog.board.isEnabled()
    assert dialog.values() == (None, None)
    dialog.accept()
    assert window.theme.get("window", "buttons_left") is None
    assert window.theme.get("window", "buttons_right") is None


def test_the_dialog_stores_both_sides_as_one_undo_step(window):
    _page, dialog = open_dialog(window)
    steps = window.undo_stack.count()
    dialog.leave.setChecked(False)
    assert dialog.board.isEnabled()
    dialog.board.select("left", 0)
    click(dialog.buttons["move_right"])
    click(dialog.buttons["remove"])
    dialog.board.select("pool", dialog.board.pool().index("B"))
    click(dialog.buttons["add_right"])
    assert dialog.buttons["add_left"].isEnabled()
    left, right = dialog.values()
    dialog.accept()
    assert window.theme.get("window", "buttons_left") == left
    assert window.theme.get("window", "buttons_right") == right
    assert right.endswith("B")
    assert window.undo_stack.count() == steps + 1
    window.undo_stack.undo()
    assert window.theme.get("window", "buttons_left") is None
    assert window.theme.get("window", "buttons_right") is None


def test_the_dialog_buttons_follow_the_choice(window):
    _page, dialog = open_dialog(window)
    dialog.leave.setChecked(False)
    assert not any(b.isEnabled() for b in dialog.buttons.values())
    dialog.board.select("left", 0)
    assert dialog.buttons["move_right"].isEnabled() and not dialog.buttons["move_left"].isEnabled()
    assert dialog.buttons["add_right"].isEnabled() and not dialog.buttons["add_left"].isEnabled()
    click(dialog.buttons["add_right"])
    assert "M" in dialog.board.text("right")


def test_the_defaults_button_and_cancel(window):
    _page, dialog = open_dialog(window)
    dialog.leave.setChecked(False)
    dialog.board.select("left", 0)
    dialog.board.remove()
    click(dialog.defaults)
    assert dialog.values() == ("MSE", "HIAX")
    dialog.reject()
    assert window.theme.get("window", "buttons_left") is None
    assert window.undo_stack.count() == 0


def test_the_dialog_starts_from_the_buttons_of_the_theme(window):
    window.edit_many(
        "Buttons",
        {FIELD_BY_ID[("window", "buttons_left")]: "M", FIELD_BY_ID[("window", "buttons_right")]: "X"},
    )
    _page, dialog = open_dialog(window)
    assert not dialog.leave.isChecked()
    assert dialog.values() == ("M", "X")
    dialog.reject()


# ---- Plasma Style


def test_the_style_values_show_for_this_theme_only_and_edit_it(window):
    page = page_of(window, "plasma_style")
    assert not page.style_box.isVisible()
    click(page.grid.card(THIS_THEME))
    window.refresh()
    assert page.style_box.isVisible() and page.style_preview.isVisible()
    for section in ("panel", "popup"):
        for key in ("radius", "border_width", "opacity"):
            assert ((section, key)) in window.editors
    steps = window.undo_stack.count()
    window.edit(FIELD_BY_ID[("popup", "radius")], 9)
    window.edit(FIELD_BY_ID[("panel", "radius")], 11)
    window.refresh()
    assert window.undo_stack.count() == steps + 2
    assert page.style_preview.theme.get("popup", "radius") == 9
    assert page.style_preview.theme.get("panel", "radius") == 11
    page.header.set_part_mode(False)
    page.header.part_mode_changed.emit(False)
    window.refresh()
    assert not page.style_box.isVisible()


# ---- Panel


def test_the_panel_switch_clears_all_seven_values_in_one_step_and_brings_them_back(window):
    page = page_of(window, "panel")
    page.settle()
    assert not page.is_set() and not page.form_box.isEnabled()
    steps = window.undo_stack.count()
    page.header.set_part_mode(True)
    page.header.part_mode_changed.emit(True)
    assert window.undo_stack.count() == steps + 1
    assert page.is_set() and page.form_box.isEnabled()
    assert all(window.theme.get("panel_layout", key) is not None for key in panel_module.FIELDS)

    window.editors[("panel_layout", "location")].choose("left")
    window.editors[("panel_layout", "alignment")].choose("left")
    steps = window.undo_stack.count()
    page.header.set_part_mode(False)
    page.header.part_mode_changed.emit(False)
    assert window.undo_stack.count() == steps + 1
    assert not page.is_set() and not page.form_box.isEnabled()
    assert all(window.theme.get("panel_layout", key) is None for key in panel_module.FIELDS)

    page.header.set_part_mode(True)
    page.header.part_mode_changed.emit(True)
    assert window.theme.get("panel_layout", "location") == "left"
    assert window.theme.get("panel_layout", "alignment") == "left"


def test_the_switch_starts_from_the_usual_panel_when_the_desktop_has_none(window):
    page = page_of(window, "panel")
    page.settle()
    assert page.desktop_layout is None
    page.header.set_part_mode(True)
    page.header.part_mode_changed.emit(True)
    for key, value in panel_module.USUAL.items():
        assert window.theme.get("panel_layout", key) == value


def test_the_switch_starts_from_what_the_desktop_has(window):
    page = page_of(window, "panel")
    page.settle()
    page.desktop_layout = panel_module.USUAL | {"location": "top", "height": 60}
    page.header.set_part_mode(True)
    page.header.part_mode_changed.emit(True)
    assert window.theme.get("panel_layout", "location") == "top"
    assert window.theme.get("panel_layout", "height") == 60


def test_the_desktop_is_asked_off_the_gui_thread(window, monkeypatch):
    from plasma_theme_studio.generators import panellayout

    state = {"found": True, "location": "left", "height": 52}
    monkeypatch.setattr(panellayout, "_read", lambda runner: state)
    monkeypatch.setattr(panellayout, "_live_state", lambda runner, s: (s, True))
    page = page_of(window, "panel")
    page.read_desktop()
    page.settle()
    assert page.desktop_layout is not None and page.desktop_layout["location"] == "left"
    assert window.undo_stack.count() == 0  # asking edits nothing


def test_layout_from_checks_what_the_desktop_says():
    layout = panel_module.layout_from({"location": "right", "height": 500, "hiding": "normal"})
    assert layout["location"] == "right" and layout["height"] == 120 and layout["visibility"] == "none"
    assert panel_module.layout_from({"location": "nowhere"}).get("location") != "nowhere"


def test_the_chooser_edges_set_the_location(window):
    page = page_of(window, "panel")
    page.header.set_part_mode(True)
    page.header.part_mode_changed.emit(True)
    window.refresh()
    chooser = page.chooser
    assert isinstance(chooser, ScreenChooser) and chooser.value() == "bottom"
    for edge in ("top", "left", "right", "bottom"):
        click(chooser, chooser.edge_rect(edge).center().toPoint())
        assert window.theme.get("panel_layout", "location") == edge
        window.refresh()
        assert chooser.value() == edge
    assert chooser.edge_at(chooser.screen_rect().center()) is None


def test_the_chooser_keys_and_the_form_follow_each_other(window):
    page = page_of(window, "panel")
    page.header.set_part_mode(True)
    page.header.part_mode_changed.emit(True)
    window.refresh()
    page.chooser.setFocus()
    QTest.keyClick(page.chooser, Qt.Key.Key_Left)
    assert window.theme.get("panel_layout", "location") == "left"
    window.editors[("panel_layout", "location")].choose("top")
    window.refresh()
    assert page.chooser.value() == "top"


def test_the_panel_preview_has_two_views(window):
    page = page_of(window, "panel")
    assert page.preview.mode == "desktop"
    page.mode_switch.button(1).click()
    assert page.preview.mode == "panel"
    page.mode_switch.button(0).click()
    assert page.preview.mode == "desktop"
    assert not page.preview.grab().isNull()


def test_the_panel_form_edits_the_height_and_the_note_follows(window):
    page = page_of(window, "panel")
    page.header.set_part_mode(True)
    page.header.part_mode_changed.emit(True)
    window.edit(FIELD_BY_ID[("panel_layout", "height")], 70)
    window.refresh()
    assert window.theme.get("panel_layout", "height") == 70
    assert page.preview.theme.get("panel_layout", "height") == 70
