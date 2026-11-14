# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QProxyStyle, QStyle  # noqa: E402

from plasma_theme_studio.apply import snapshot as snapshots  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID, Theme  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402


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
    assert "Not put on the desktop: Shapes." in window.banner.text()


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
    assert "\nradius = 20\n" in window.theme.to_toml().split("[panel]")[1]
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


def click_theme(window, app, title, double=False):
    """Click a theme on the Themes tab with the mouse, as a user does."""
    themes = window.library.list
    app.processEvents()  # let the icon grid lay itself out
    item = next(
        themes.item(row) for row in range(themes.count()) if themes.item(row).text().startswith(title)
    )
    themes.scrollToItem(item)
    app.processEvents()
    spot = themes.visualItemRect(item).center()
    QTest.mouseClick(themes.viewport(), Qt.MouseButton.LeftButton, pos=spot)
    if double:
        QTest.mouseDClick(themes.viewport(), Qt.MouseButton.LeftButton, pos=spot)
    app.processEvents()


def test_switch_to_an_installed_scheme_and_back(nordic, window, runner):
    runner.known.add("Nordic")
    entry = window.library.select("Nordic")
    assert entry.title == "Nordic" and window.apply_button.isEnabled()
    window.apply_button.click()
    assert runner.settings["ColorScheme"] == "Nordic"
    assert "In use" in window.library.list.currentItem().text()
    window.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert "In use" not in window.library.list.currentItem().text()


def test_selecting_a_theme_with_one_click_is_enough_to_switch(nordic, window, app, runner):
    """The apply button acts on the theme that is selected on the Themes tab,
    not on whatever happens to be open in the editor."""
    runner.known.add("Nordic")
    assert window.tabs.currentWidget() is window.library
    click_theme(window, app, "Nordic")
    assert window.library.current().title == "Nordic"
    assert "Nordic" in window.apply_button.text()

    QTest.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)
    assert runner.settings["ColorScheme"] == "Nordic"
    assert "Nordic" in window.banner.text()
    assert window.theme.name == "Nordic Copy"  # the editor follows the desktop
    assert window.tabs.currentWidget() is window.library


def test_apply_shortcut_action_also_uses_the_selected_theme(nordic, window, app, runner):
    runner.known.add("Nordic")
    click_theme(window, app, "Nordic")
    window.apply_shown()
    assert runner.settings["ColorScheme"] == "Nordic"


def test_apply_button_names_what_it_applies(nordic, window, app):
    click_theme(window, app, "Nordic")
    assert window.apply_button.text() == "Apply “Nordic” to desktop"
    window.tabs.setCurrentWidget(window.preview)
    assert window.apply_button.text() == "Apply “Breeze Light Copy” to desktop"
    window.edit(FIELD_BY_ID[("meta", "name")], "R&D " + "x" * 40)
    window.refresh()
    assert window.apply_button.text().startswith("Apply “R&&D xxx") and "…" in window.apply_button.text()
    window.tabs.setCurrentWidget(window.library)
    assert window.apply_button.text() == "Apply “Nordic” to desktop"
    window.library.search.setText("zzz")
    assert window.apply_button.text() == "Apply to desktop" and not window.apply_button.isEnabled()
    assert window.apply_button.toolTip()


def test_on_the_other_tabs_the_editor_theme_is_applied(nordic, window, app, runner):
    runner.known.add("Nordic")
    click_theme(window, app, "Nordic")
    window.tabs.setCurrentWidget(window.preview)
    QTest.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)
    assert runner.settings["ColorScheme"] == "BreezeLightCopy"


def test_double_click_or_enter_switches_the_desktop(nordic, window, app, runner):
    runner.known.add("Nordic")
    click_theme(window, app, "Nordic", double=True)
    assert runner.settings["ColorScheme"] == "Nordic"
    assert window.theme.name == "Nordic Copy" and window.tabs.currentWidget() is window.library

    window.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert window.theme.name == "Breeze Light Copy"  # the editor went back with the desktop
    assert window.library.current().title == "Nordic"  # the selection stays where the user put it
    window.library.list.setFocus()
    QTest.keyClick(window.library.list, Qt.Key.Key_Return)
    assert runner.settings["ColorScheme"] == "Nordic"


def test_single_click_never_opens_or_applies_even_with_single_click_activation(nordic, window, app, runner):
    class SingleClick(QProxyStyle):
        def styleHint(self, hint, option=None, widget=None, data=None):
            if hint == QStyle.StyleHint.SH_ItemView_ActivateItemOnSingleClick:
                return 1
            return super().styleHint(hint, option, widget, data)

    style = SingleClick()
    window.library.list.setStyle(style)
    click_theme(window, app, "Nordic")
    assert window.library.current().title == "Nordic"
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert window.theme.name == "Breeze Light Copy" and window.tabs.currentWidget() is window.library


def test_deselecting_with_ctrl_click_disables_apply(nordic, window, app):
    click_theme(window, app, "Nordic")
    themes = window.library.list
    spot = themes.visualItemRect(themes.currentItem()).center()
    QTest.mouseClick(themes.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, spot)
    assert window.library.current() is None
    assert not window.apply_button.isEnabled() and not window.library.edit_button.isEnabled()


def test_using_the_theme_that_is_in_use_says_so(window, home, runner):
    window.edit(FIELD_BY_ID[("meta", "name")], "Mine")
    assert window._save_to(home / ".local/share/plasma-theme-studio/themes/mine.toml")
    window.new_theme("breeze-dark")
    window.tabs.setCurrentWidget(window.library)
    window.library.select("Mine")
    window.apply_button.click()
    count = len(snapshots.list_snapshots())
    window.apply_button.click()
    assert "already uses Mine." in window.banner.text() and "Change a color" not in window.banner.text()
    assert len(snapshots.list_snapshots()) == count


def test_reloading_the_themes_keeps_the_scroll_position(home, window, app):
    folder = home / "system/share/color-schemes"
    folder.mkdir(parents=True)
    for index in range(40):
        (folder / f"Scheme{index:02}.colors").write_text(
            "[Colors:Window]\nBackgroundNormal=46,52,64\nForegroundNormal=216,222,233\n"
            f"[General]\nName=Scheme {index:02}\n"
        )
    window.reload_library()
    app.processEvents()
    bar = window.library.list.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    window.reload_library()
    app.processEvents()
    assert bar.value() == bar.maximum()


def test_selected_saved_theme_is_applied_with_its_unsaved_edits(window, home, runner):
    window.edit(FIELD_BY_ID[("meta", "name")], "Mine")
    assert window._save_to(home / ".local/share/plasma-theme-studio/themes/mine.toml")
    window.edit(FIELD_BY_ID[("colors", "accent")], "#ff0000")
    window.tabs.setCurrentWidget(window.library)
    window.library.select("Mine")
    window.apply_button.click()
    written = (home / ".local/share/color-schemes/Mine.colors").read_text()
    assert "255,0,0" in written


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
    window.tabs.setCurrentWidget(window.library)
    window.library.search.setText("zzz")
    assert window.library.current() is None and not window.apply_button.isEnabled()
    window.library.search.clear()
    window.library.select("Mine")
    window.apply_button.click()
    assert runner.settings["ColorScheme"] == "Mine"
    # The scheme written for it does not show up as a second entry.
    titles = [window.library.list.item(row).text() for row in range(window.library.list.count())]
    assert len([title for title in titles if title.startswith("Mine")]) == 1
    window.library.edit_button.click()
    assert window.theme.name == "Mine" and window.path.name == "mine.toml"


def test_panel_position_is_chosen_from_named_values(window):
    location = window.editors[("panel_layout", "location")]
    assert location.currentText() == "Leave as it is"
    assert "[panel_layout]" not in window.theme.to_toml()

    location.choose("top")
    window.editors[("panel_layout", "floating")].choose(False)
    assert window.theme.get("panel_layout", "location") == "top"
    assert '[panel_layout]\nlocation = "top"\nfloating = false\n' in window.theme.to_toml()
    assert Theme.from_toml(window.theme.to_toml()) == window.theme
    assert window.tabs.currentWidget() is window.preview and not window.preview.grab().isNull()

    window.undo_stack.undo()
    window.undo_stack.undo()
    assert window.theme.get("panel_layout", "location") is None
    assert location.currentText() == "Leave as it is"


def test_panel_thickness_is_left_alone_until_it_gets_a_value(window):
    height = window.editors[("panel_layout", "height")]
    assert height.same.text() == "Leave as it is" and height.same.isChecked()

    height.same.setChecked(False)
    assert window.theme.get("panel_layout", "height") == 44  # Plasma's own default
    height.number.box.setValue(60)
    assert window.theme.get("panel_layout", "height") == 60

    height.same.setChecked(True)
    assert window.theme.get("panel_layout", "height") is None


def test_the_preview_draws_every_panel_position(window):
    for location in ("top", "bottom", "left", "right"):
        for values in ({}, {"length_mode": "fill", "floating": False, "height": 120, "alignment": "right"}):
            theme = Theme({("panel_layout", "location"): location})
            for key, value in values.items():
                theme.set("panel_layout", key, value)
            window.preview.set_theme(theme)
            panel, vertical, attached = window.preview._panel_geometry()
            assert vertical == (location in ("left", "right")) and attached == bool(values)
            assert 0 <= panel.left() and panel.right() <= 760 and 0 <= panel.top() and panel.bottom() <= 520
            assert not window.preview.grab().isNull()


def test_the_shapes_page_says_what_is_not_applied(window):
    assert "cannot change the shape of buttons and fields" in window.notes["shape"].text()
    assert window.notes["colors"].text() == ""
