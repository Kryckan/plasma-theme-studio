# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Application Style, GTK Apps, Rofi and Fonts pages: every action a person can take."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QFontDialog  # noqa: E402

from plasma_theme_studio import desktopparts  # noqa: E402
from plasma_theme_studio.generators import kvantum  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID  # noqa: E402
from plasma_theme_studio.ui import style_preview  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages.apps_fonts import FontRow, qfont_of, spec_of  # noqa: E402
from plasma_theme_studio.ui.pages.base import THIS_THEME  # noqa: E402


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.resize(1400, 900)
    window.show()
    window.settle()
    yield window
    window.undo_stack.setClean()
    window.close()


def settle(window, app):
    window.refresh()
    app.processEvents()


# ---- Application Style -----------------------------------------------------------------------


def test_the_application_style_page_has_the_cards_and_the_action(window):
    window.show_page("app_style")
    page = window.page("app_style")
    assert page.grid.ids()[0] == THIS_THEME
    assert page.configure_button.text() == "Configure Icons and Toolbars in System Settings…"
    assert page.configure_button in page.header.findChildren(type(page.configure_button))


def test_configure_icons_and_toolbars_opens_the_style_module(window):
    window.show_page("app_style")
    window.page("app_style").configure_button.click()
    assert window.runner.launched == [["systemsettings", "kcm_style"]]
    assert not window.banner.isVisible()


def test_configure_says_so_when_system_settings_is_missing(window):
    window.runner.missing |= {"systemsettings", "kcmshell6"}
    window.show_page("app_style")
    window.page("app_style").configure_button.click()
    assert window.runner.launched == []
    assert window.banner.isVisible() and "System Settings is not installed" in window.banner.text()


def test_the_card_this_theme_and_an_installed_style_set_the_part(window, app):
    window.show_page("app_style")
    page = window.page("app_style")
    QTest.mouseClick(page.grid.card(THIS_THEME), Qt.MouseButton.LeftButton)
    assert window.theme.get("apps", "style") == "generated"
    other = next(i for i in page.grid.ids() if i != THIS_THEME)
    QTest.mouseClick(page.grid.card(other), Qt.MouseButton.LeftButton)
    assert window.theme.get("apps", "style") == "installed"
    assert window.theme.get("apps", "style_id").casefold() == other.casefold()
    settle(window, app)
    page.draw_sample()
    assert page.stack.currentWidget() is page.sentence
    assert page.items[other].name in page.sentence.text()


def test_the_sample_is_a_sentence_when_the_style_is_left_as_it_is(window, app):
    window.show_page("app_style")
    page = window.page("app_style")
    page.header.part_mode_changed.emit(False)
    settle(window, app)
    assert window.theme.get("apps", "style") == "unchanged"
    assert page.stack.currentWidget() is page.sentence
    assert "left as it is" in page.sentence.text()


def test_the_values_of_this_theme_reach_the_theme_and_the_sample(window, app, monkeypatch):
    monkeypatch.setattr(style_preview, "plugin_available", lambda: False)
    window.show_page("app_style")
    page = window.page("app_style")
    QTest.mouseClick(page.grid.card(THIS_THEME), Qt.MouseButton.LeftButton)
    editor = window.editors[("apps", "radius")]
    editor.same.setChecked(False)
    editor.number.box.setValue(9)
    editor.number.box.editingFinished.emit()
    assert window.theme.get("apps", "radius") == 9
    settle(window, app)
    assert page.timer.isActive()
    page.timer.timeout.emit()
    assert page.stack.currentWidget() is page.style_preview
    assert "Kvantum is not installed" in page.style_preview.message  # a plain sentence, no crash


def test_a_note_says_what_to_install_when_kvantum_is_missing(window, monkeypatch):
    monkeypatch.setattr(kvantum, "plugin_installed", lambda: False)
    window.runner.missing.add("kvantummanager")
    window.show_page("app_style")
    page = window.page("app_style")
    window.refresh()
    assert not page.kvantum_note.isHidden()
    assert "kvantum" in page.kvantum_note.text() and "qt6-style-kvantum" in page.kvantum_note.text()
    window.runner.missing.discard("kvantummanager")
    window.refresh()
    assert page.kvantum_note.isHidden()


def test_the_values_sit_beside_the_sample_only_when_there_is_room(window, app):
    window.show_page("app_style")
    page = window.page("app_style")
    window.resize(1400, 900)
    app.processEvents()
    assert page.beside.direction().name == "LeftToRight"
    window.resize(1100, 720)
    app.processEvents()
    assert page.beside.direction().name == "TopToBottom"
    assert page.scroll.horizontalScrollBar().maximum() == 0


# ---- GTK Apps and Rofi ----------------------------------------------------------------------


@pytest.mark.parametrize("key", ["gtk", "rofi"])
def test_the_target_pages_have_a_preview_that_is_drawn(window, app, key):
    window.show_page(key)
    page = window.page(key)
    app.processEvents()
    assert page.sample.isVisible() and page.sample.mapTo(page, page.sample.rect().topLeft()).x() > 600
    assert not page.sample.grab().isNull()
    assert "Undo last apply" in page.written.text()


def test_the_gtk_preview_follows_the_values(window, app):
    window.show_page("gtk")
    page = window.page("gtk")
    before = page.sample.grab().toImage()
    window.edit(FIELD_BY_ID[("gtk", "window_radius")], 0)
    window.edit(FIELD_BY_ID[("gtk", "radius")], 20)
    settle(window, app)
    square = page.sample.grab().toImage()
    assert square != before
    window.edit(FIELD_BY_ID[("gtk", "border_width")], 4)
    settle(window, app)
    assert page.sample.grab().toImage() != square
    window.edit(FIELD_BY_ID[("colors", "accent")], "#ff0000")
    settle(window, app)
    assert page.sample.theme.get("colors", "accent") == "#ff0000"


def test_the_rofi_preview_follows_radius_border_opacity_and_font(window, app):
    window.show_page("rofi")
    page = window.page("rofi")
    seen = [page.sample.grab().toImage()]
    for field, value in (
        ("radius", 20),
        ("border_width", 4),
        ("opacity", 0.4),
        ("font", "Serif 18"),
    ):
        window.edit(FIELD_BY_ID[("rofi", field)], value)
        settle(window, app)
        image = page.sample.grab().toImage()
        assert image != seen[-1], field
        seen.append(image)


def test_the_preview_says_when_it_is_only_a_preview(window, app):
    window.show_page("gtk")
    page = window.page("gtk")
    assert window.theme.get("gtk", "style") == "unchanged"
    window.refresh()
    assert "Only a preview" in page.sample_hint.text()
    page.header.part_mode_changed.emit(True)
    assert window.theme.get("gtk", "style") == "generated"
    window.refresh()
    assert "Nothing reaches the desktop" in page.sample_hint.text()


def test_the_rofi_switch_and_values_edit_the_theme(window, app):
    window.show_page("rofi")
    page = window.page("rofi")
    page.header.part_mode_changed.emit(True)
    assert window.theme.get("rofi", "style") == "generated"
    font = window.editors[("rofi", "font")]
    font.same.setChecked(False)
    font.text.setText("Inter 11")
    font.text.textEdited.emit("Inter 11")
    assert window.theme.get("rofi", "font") == "Inter 11"


# ---- Fonts ----------------------------------------------------------------------------------


KEYS = ("general", "fixed", "small", "toolbar", "menu", "window_title")


def desktop_fonts(window):
    desktopparts.PARTS["fonts"].apply(
        {
            "font": "Hack,11,-1,5,400,0,0,0,0,0,0,0,0,0,0,1",
            "fixed": "Hack,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1",
            "small": "Hack,8,-1,5,400,0,0,0,0,0,0,0,0,0,0,1",
        },
        window.runner,
    )
    window.page("fonts").read_desktop()


def test_the_fonts_page_has_a_row_per_role(window):
    window.show_page("fonts")
    page = window.page("fonts")
    assert list(page.rows) == list(KEYS)
    for key, row in page.rows.items():
        assert window.editors[("fonts", key)] is row
        assert row.leave.isChecked() and row.value is None
        assert row.sample.text().startswith("The quick brown fox")
        assert row.choose.accessibleName().startswith("Choose ")


def test_a_row_left_as_it_is_shows_the_desktops_font_dimmed(window):
    window.show_page("fonts")
    desktop_fonts(window)
    row = window.page("fonts").rows["general"]
    assert row.text.text() == "" and row.text.placeholderText() == "Hack, 11 pt"
    assert row.sample.font().family() == "Hack" and row.sample.font().pointSizeF() == 11
    assert row.sample.foregroundRole() == row.palette().ColorRole.PlaceholderText


def test_unchecking_leave_as_it_is_starts_from_the_desktops_font(window, app):
    window.show_page("fonts")
    desktop_fonts(window)
    page = window.page("fonts")
    row = page.rows["small"]
    row.leave.click()
    assert window.theme.get("fonts", "small") == "Hack, 8"
    assert not row.leave.isChecked() and row.text.text() == "Hack, 8 pt"
    assert row.sample.foregroundRole() == row.palette().ColorRole.Text
    assert page.header.part_mode() is True
    row.leave.click()
    assert window.theme.get("fonts", "small") is None and row.leave.isChecked()
    assert page.header.part_mode() is False


def test_choose_opens_a_font_dialog_and_takes_the_font(window, app):
    window.show_page("fonts")
    page = window.page("fonts")
    family = QFontDatabase.families()[0]
    QTest.mouseClick(page.rows["menu"].choose, Qt.MouseButton.LeftButton)
    dialog = page.font_dialog
    assert isinstance(dialog, QFontDialog) and dialog.isVisible()
    assert dialog.testOption(QFontDialog.FontDialogOption.DontUseNativeDialog)
    font = QFont(family)
    font.setPointSize(13)
    dialog.setCurrentFont(font)
    dialog.accept()
    value = window.theme.get("fonts", "menu")
    assert value is not None and value.startswith(family + ", ")
    assert page.rows["menu"].text.text().startswith(family)
    assert window.theme.get("fonts", "general") is None


def test_cancelling_the_font_dialog_changes_nothing(window):
    window.show_page("fonts")
    page = window.page("fonts")
    page.rows["toolbar"].choose.click()
    page.font_dialog.reject()
    assert window.theme.get("fonts", "toolbar") is None


def test_the_fixed_width_dialog_offers_fixed_width_fonts_only(window):
    window.show_page("fonts")
    page = window.page("fonts")
    page.rows["fixed"].choose.click()
    assert page.font_dialog.testOption(QFontDialog.FontDialogOption.MonospacedFonts)
    page.font_dialog.reject()
    page.rows["general"].choose.click()
    assert not page.font_dialog.testOption(QFontDialog.FontDialogOption.MonospacedFonts)
    page.font_dialog.reject()


def test_the_weight_and_slant_of_a_chosen_font_are_kept(window):
    window.show_page("fonts")
    page = window.page("fonts")
    window.edit(FIELD_BY_ID[("fonts", "window_title")], "Hack, 12, 700, italic")
    window.refresh()
    row = page.rows["window_title"]
    assert row.text.text() == "Hack, 12 pt, Bold, Italic"
    font = qfont_of(page.effective("window_title"))
    assert font.italic() and font.weight().value == 700
    assert spec_of(font).short() == "Hack, 12, 700, italic"


def test_the_switch_on_top_clears_all_fonts_as_one_undo_step(window):
    window.show_page("fonts")
    page = window.page("fonts")
    for key in KEYS:
        window.edit(FIELD_BY_ID[("fonts", key)], f"Hack, {9 + KEYS.index(key)}")
    window.undo_stack.setClean()
    count = window.undo_stack.count()
    page.header.part_mode_changed.emit(False)
    assert all(window.theme.get("fonts", key) is None for key in KEYS)
    assert window.undo_stack.count() == count + 1
    assert all(page.rows[key].leave.isChecked() for key in KEYS)
    window.undo_stack.undo()
    assert all(window.theme.get("fonts", key) is not None for key in KEYS)
    window.undo_stack.redo()
    page.header.part_mode_changed.emit(True)  # the fonts there were come back
    assert window.theme.get("fonts", "fixed") == "Hack, 10"
    assert window.theme.get("fonts", "window_title") == "Hack, 14"


def test_the_switch_on_starts_from_the_desktops_fonts(window):
    window.show_page("fonts")
    desktop_fonts(window)
    page = window.page("fonts")
    page.header.part_mode_changed.emit(True)
    assert window.theme.get("fonts", "general") == "Hack, 11"
    assert all(window.theme.get("fonts", key) for key in KEYS)
    assert page.header.part_mode() is True


def test_use_one_family_for_all_keeps_the_sizes_and_the_fixed_font(window):
    window.show_page("fonts")
    page = window.page("fonts")
    window.edit_many(
        "Set",
        {
            ("fonts", "general"): "Noto Sans, 11",
            ("fonts", "fixed"): "Hack, 10",
            ("fonts", "small"): "Hack, 8",
            ("fonts", "menu"): "Hack, 12, 700",
        },
    )
    count = window.undo_stack.count()
    page.one_family.click()
    get = lambda key: window.theme.get("fonts", key)  # noqa: E731
    assert get("general") == "Noto Sans, 11"
    assert get("small") == "Noto Sans, 8"
    assert get("menu") == "Noto Sans, 12, 700"
    assert get("fixed") == "Hack, 10"
    assert get("toolbar") and get("toolbar").startswith("Noto Sans, ")
    assert get("window_title") and get("window_title").startswith("Noto Sans, ")
    assert window.undo_stack.count() == count + 1
    window.undo_stack.undo()
    assert get("small") == "Hack, 8" and get("toolbar") is None


def test_a_font_row_takes_a_value_it_cannot_read(window):
    row = FontRow("general", "General", "General font")
    row.set_value("not a font")
    assert row.text.text() == "not a font" and not row.leave.isChecked()
    row.set_value(None)
    assert row.leave.isChecked() and row.text.text() == ""
