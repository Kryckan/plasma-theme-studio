# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from plasma_theme_studio.apply import snapshot as snapshots  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID, Theme  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def window(app, home, runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(runner)
    window.build_pages()
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
    window.show_files()
    assert "255,0,0" in window.files_dialog.file_content.toPlainText()
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


def settle(window):
    """Bring every page in line with the theme, as showing each of them would."""
    window.refresh()
    window.build_pages()


@pytest.fixture
def nordic(home):
    folder = home / "system/share/color-schemes"
    folder.mkdir(parents=True)
    (folder / "Nordic.colors").write_text(
        "[Colors:Selection]\nBackgroundNormal=136,192,208\n[Colors:Window]\n"
        "BackgroundNormal=46,52,64\nForegroundNormal=216,222,233\n[General]\nName=Nordic\n"
    )


def click_theme(window, app, title, double=False):
    """Click a theme on the Themes page with the mouse, as a user does."""
    grid = window.library.grid
    app.processEvents()  # let the grid lay itself out
    card = next(card for card in grid.cards if card.title().startswith(title))
    grid.scroll.ensureWidgetVisible(card)
    app.processEvents()
    QTest.mouseClick(card, Qt.MouseButton.LeftButton)
    if double:
        QTest.mouseDClick(card, Qt.MouseButton.LeftButton)
    app.processEvents()


def test_switch_to_an_installed_scheme_and_back(nordic, window, runner):
    runner.known.add("Nordic")
    window.show_page("themes")
    entry = window.library.select("Nordic")
    assert entry.title == "Nordic" and window.apply_button.isEnabled()
    window.apply_button.click()
    assert runner.settings["ColorScheme"] == "Nordic"
    assert window.library.grid.in_use() == ("scheme", "Nordic")
    window.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert window.library.grid.in_use() != ("scheme", "Nordic")


def test_selecting_a_theme_with_one_click_is_enough_to_switch(nordic, window, app, runner):
    """The apply button acts on the theme that is selected on the Themes page,
    not on whatever happens to be open in the editor."""
    runner.known.add("Nordic")
    window.show_page("themes")
    click_theme(window, app, "Nordic")
    assert window.library.current().title == "Nordic"
    assert "Nordic" in window.apply_button.toolTip()

    QTest.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)
    assert runner.settings["ColorScheme"] == "Nordic"
    assert "Nordic" in window.banner.text()
    assert window.theme.name == "Nordic Copy"  # the editor follows the desktop
    assert window.current_key == "themes"


def test_apply_shortcut_action_also_uses_the_selected_theme(nordic, window, app, runner):
    runner.known.add("Nordic")
    window.show_page("themes")
    click_theme(window, app, "Nordic")
    window.apply_shown()
    assert runner.settings["ColorScheme"] == "Nordic"


def test_apply_button_names_what_it_applies(nordic, window, app):
    window.show_page("themes")
    click_theme(window, app, "Nordic")
    assert window.apply_button.toolTip() == "Apply “Nordic” to the desktop"
    window.show_page("overview")
    assert window.apply_button.toolTip() == "Apply “Breeze Light Copy” to the desktop"
    window.edit(FIELD_BY_ID[("meta", "name")], "R&D " + "x" * 40)
    window.refresh()
    assert window.apply_button.toolTip().startswith("Apply “R&D xxx")
    window.show_page("themes")
    assert window.apply_button.toolTip() == "Apply “Nordic” to the desktop"
    window.library.search.setText("zzz")
    assert not window.apply_button.isEnabled()
    assert window.apply_button.toolTip()


def test_on_the_other_pages_the_editor_theme_is_applied(nordic, window, app, runner):
    runner.known.add("Nordic")
    window.show_page("themes")
    click_theme(window, app, "Nordic")
    window.show_page("overview")
    QTest.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)
    assert runner.settings["ColorScheme"] == "BreezeLightCopy"


def test_double_click_or_enter_opens_a_copy_and_never_applies(nordic, window, app, runner):
    runner.known.add("Nordic")
    window.show_page("themes")
    click_theme(window, app, "Nordic", double=True)
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert window.theme.name == "Nordic Copy" and window.current_key == "overview"

    window.show_page("themes")
    window.new_theme("breeze-light")
    window.library.select("Nordic")
    window.library.grid.body.setFocus()
    QTest.keyClick(window.library.grid.body, Qt.Key.Key_Return)
    assert window.theme.name == "Nordic Copy"
    assert runner.settings["ColorScheme"] == "BreezeLight"


def test_single_click_never_opens_or_applies(nordic, window, app, runner):
    window.show_page("themes")
    click_theme(window, app, "Nordic")
    assert window.library.current().title == "Nordic"
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert window.theme.name == "Breeze Light Copy" and window.current_key == "themes"


def test_a_search_that_hides_the_selection_disables_apply(nordic, window, app):
    window.show_page("themes")
    click_theme(window, app, "Nordic")
    assert window.apply_button.isEnabled()
    window.library.search.setText("zzz")
    assert window.library.current() is None
    assert not window.apply_button.isEnabled() and not window.library.edit_button.isEnabled()


def test_using_the_theme_that_is_in_use_says_so(window, home, runner):
    window.edit(FIELD_BY_ID[("meta", "name")], "Mine")
    assert window._save_to(home / ".local/share/plasma-theme-studio/themes/mine.toml")
    window.new_theme("breeze-dark")
    window.show_page("themes")
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
    window.show_page("themes")
    window.reload_library()
    app.processEvents()
    bar = window.library.grid.scroll.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    window.reload_library()
    app.processEvents()
    assert bar.value() == bar.maximum()


def test_selected_saved_theme_is_applied_with_its_unsaved_edits(window, home, runner):
    window.edit(FIELD_BY_ID[("meta", "name")], "Mine")
    assert window._save_to(home / ".local/share/plasma-theme-studio/themes/mine.toml")
    window.edit(FIELD_BY_ID[("colors", "accent")], "#ff0000")
    window.show_page("themes")
    window.library.select("Mine")
    window.apply_button.click()
    written = (home / ".local/share/color-schemes/Mine.colors").read_text()
    assert "255,0,0" in written


def test_edit_a_copy_of_an_installed_scheme(nordic, window):
    window.library.select("Nordic")
    window.library.edit_button.click()
    assert window.theme.name == "Nordic Copy"
    assert window.theme.get("colors", "window") == "#2e3440"
    assert window.current_key == "overview"
    assert window.path is None


def test_saved_themes_are_listed_and_can_be_used(window, home, runner):
    window.edit(FIELD_BY_ID[("meta", "name")], "Mine")
    assert window._save_to(home / ".local/share/plasma-theme-studio/themes/mine.toml")
    window.new_theme("breeze-dark")
    window.show_page("themes")
    entry = window.library.select("Mine")
    assert entry.is_saved_theme
    window.show_page("themes")
    window.library.search.setText("zzz")
    assert window.library.current() is None and not window.apply_button.isEnabled()
    window.library.search.clear()
    window.library.select("Mine")
    window.apply_button.click()
    assert runner.settings["ColorScheme"] == "Mine"
    # The scheme written for it does not show up as a second entry.
    titles = [card.title() for card in window.library.grid.cards]
    assert len([title for title in titles if title == "Mine"]) == 1
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
    assert window.current_key == "overview" and not window.preview.grab().isNull()

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


def test_the_shapes_page_says_where_its_values_go(window):
    text = window.notes["shape"].text()
    assert "starting point" in text and "Applications" in text and "Rofi" in text
    assert window.notes["colors"].text() == ""


def test_every_page_with_a_target_says_what_an_apply_does_with_it(window):
    for section in ("apps", "gtk", "rofi"):
        assert "only show in the preview" in window.notes[section].text()
    assert "keeps its own popups" in window.notes["popup"].text()
    for section in ("apps", "popup", "gtk", "rofi"):
        assert "does not apply these values" not in window.notes[section].text()
    window.edit(FIELD_BY_ID[("rofi", "style")], "generated")
    settle(window)
    assert "reads the theme when it starts" in window.notes["rofi"].text()


def test_the_values_of_a_part_that_is_left_as_it_is_are_turned_off(window):
    for style in ("apps", "gtk", "rofi"):
        for key in ("radius", "border_width"):
            assert not window.editors[(style, key)].isEnabled()
            assert "Leave as it is" in window.editors[(style, key)].toolTip()
        window.edit(FIELD_BY_ID[(style, "style")], "generated")
        settle(window)
        for key in ("radius", "border_width"):
            assert window.editors[(style, key)].isEnabled()
            assert window.editors[(style, key)].toolTip() == ""
    assert not window.editors[("popup", "radius")].isEnabled()
    window.edit(FIELD_BY_ID[("panel", "style")], "generated")
    settle(window)
    assert window.editors[("popup", "radius")].isEnabled()
    assert window.editors[("panel", "opacity")].isEnabled()
    window.undo_stack.undo()
    settle(window)
    assert not window.editors[("popup", "radius")].isEnabled()


def test_the_banner_does_not_call_shapes_unapplied_when_a_part_follows_them(window):
    from plasma_theme_studio.apply import engine
    from plasma_theme_studio.ui.main_window import left_out_sections

    theme = Theme({("shape", "radius"): 12, ("rofi", "style"): "generated"})
    assert "shape" not in left_out_sections(engine.build_plan(theme))
    assert "shape" in left_out_sections(engine.build_plan(Theme({("shape", "radius"): 12})))


def test_the_drawn_preview_follows_apps_and_popup_values(window):
    window.edit(FIELD_BY_ID[("apps", "radius")], 0)
    window.edit(FIELD_BY_ID[("popup", "radius")], 20)
    window.edit(FIELD_BY_ID[("popup", "opacity")], 0.5)
    for location in ("top", "bottom", "left", "right"):
        window.edit(FIELD_BY_ID[("panel_layout", "location")], location)
        assert not window.preview.grab().isNull()


def test_the_application_style_sample_is_made_when_the_page_is_shown(window):
    window.edit(FIELD_BY_ID[("apps", "style")], "generated")
    window.refresh()
    page = window.page("app_style")
    assert window.style_preview.shows_sample is False  # not made while the page is hidden
    window.show_page("app_style")
    assert window.style_preview.message or window.style_preview.shows_sample
    window.edit(FIELD_BY_ID[("apps", "radius")], 3)
    window.refresh()
    assert page.timer.isActive()
    page.timer.timeout.emit()
    assert not window.grab().isNull()


def test_export_and_import_from_the_file_menu(window, home, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    shown = []
    monkeypatch.setattr(window, "_show_problems", lambda title, lines: shown.append((title, list(lines))))
    target = home / "out.ptstheme"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    window.edit(FIELD_BY_ID[("rofi", "radius")], 5)
    window.export_theme()
    assert target.read_bytes().startswith(b"PK") and shown == []

    window.undo_stack.setClean()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(target), "")))
    window.import_theme()
    assert window.theme.get("rofi", "radius") == 5
    assert window.theme.name == "Breeze Light Copy 2" or window.path is not None
    assert window.path is not None and window.path.is_file()

    bad = home / "bad.ptstheme"
    bad.write_bytes(b"PK\x03\x04 broken")
    assert window.import_path(bad) is False
    assert shown and "could not be imported" in shown[0][0]


def test_export_as_global_theme_from_the_file_menu(window, home, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    shown = []
    monkeypatch.setattr(window, "_show_problems", lambda title, lines: shown.append((title, list(lines))))
    folder = home / "global"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(folder)))
    window.export_global_theme()
    assert (folder / "install.sh").exists() and shown == []
    assert "Exported" in window.banner.text() if hasattr(window.banner, "text") else True
    window.export_global_theme()  # the folder is full now
    assert shown and "not be exported" in shown[0][0]
    titles = [action.text() for action in window.menuBar().actions()[0].menu().actions()]
    assert any("Import Theme" in t for t in titles) and any("Global Theme" in t for t in titles)


def test_new_pages_follow_what_they_inherit(window):
    assert window.editors[("popup", "radius")].same.text() == "Same as Panel"
    assert window.editors[("gtk", "window_radius")].same.text() == "Same as Windows"
    assert window.editors[("apps", "radius")].same.text() == "Same as Shapes"
    window.edit(FIELD_BY_ID[("shape", "radius")], 11)
    # popup.radius follows panel.radius, which follows shape.radius
    assert window.editors[("popup", "radius")].number.box.value() == 11
    window.edit(FIELD_BY_ID[("panel", "opacity")], 0.6)
    assert window.editors[("popup", "opacity")].number.box.value() == 0.6
    assert window.theme.resolved("gtk", "window_radius") == 11
    assert not window.grab().isNull()


def test_optional_font_text(window):
    font = window.editors[("rofi", "font")]
    assert font.same.isChecked() and not font.text.isEnabled()
    font.same.setChecked(False)
    font.text.setText("Inter 11")
    font.text.textEdited.emit("Inter 11")
    assert window.theme.get("rofi", "font") == "Inter 11"
    assert Theme.from_toml(window.theme.to_toml()) == window.theme
    font.same.setChecked(True)
    assert window.theme.get("rofi", "font") is None
    assert "font" not in window.theme.to_toml()


def test_export_adds_the_extension_to_a_name_with_another_suffix(window, home, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(home / "my.theme"), ""))
    )
    window.export_theme()
    assert (home / "my.theme.ptstheme").is_file() and not (home / "my.theme").exists()
