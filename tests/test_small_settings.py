# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Icons and toolbars, and launch feedback: the targets that set them and the dialogs that choose them."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from plasma_theme_studio import kconfig  # noqa: E402
from plasma_theme_studio.apply import status  # noqa: E402
from plasma_theme_studio.generators import generator_by_id  # noqa: E402
from plasma_theme_studio.generators.extras import LaunchFeedbackTarget, ToolbarsTarget  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID, Theme  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages import small_settings  # noqa: E402
from test_installed import start_from_something, tree  # noqa: E402


def theme_with(**values) -> Theme:
    return Theme({tuple(key.split("__")): value for key, value in values.items()})


def click(widget):
    """A click on the box of a check box (the middle of a wide one is empty space)."""
    QTest.mouseClick(
        widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(6, widget.height() // 2)
    )


# ---- the targets


def test_a_theme_that_sets_nothing_leaves_both_alone():
    for target in (ToolbarsTarget(), LaunchFeedbackTarget()):
        assert not target.wanted(Theme())
        assert target.values(Theme()) == {}
        assert target.changed_settings(Theme()) == []


def test_the_targets_are_registered_with_their_sections():
    assert isinstance(generator_by_id("toolbars"), ToolbarsTarget)
    assert isinstance(generator_by_id("launch_feedback"), LaunchFeedbackTarget)
    assert ToolbarsTarget.sections == ("toolbars",) and LaunchFeedbackTarget.sections == ("feedback",)


def test_the_toolbar_values_are_the_keys_the_kcm_writes():
    theme = theme_with(
        toolbars__main_style="TextUnderIcon", toolbars__icons_on_buttons=False, toolbars__icons_in_menus=True
    )
    assert ToolbarsTarget().values(theme) == {
        "main_style": "TextUnderIcon",
        "icons_on_buttons": "false",
        "icons_in_menus": "true",
    }


@pytest.mark.parametrize(
    ("kind", "busy", "blinking", "bouncing"),
    [
        ("none", "false", "false", "false"),
        ("static", "true", "false", "false"),
        ("blinking", "true", "true", "false"),
        ("bouncing", "true", "false", "true"),
    ],
)
def test_the_feedback_cursor_kinds_become_three_keys(kind, busy, blinking, bouncing):
    values = LaunchFeedbackTarget().values(theme_with(feedback__cursor=kind))
    assert (values["busy_cursor"], values["blinking"], values["bouncing"]) == (busy, blinking, bouncing)


def test_reload_writes_the_keys_and_tells_the_programs(home, desktop_runner):
    runner = desktop_runner
    target = ToolbarsTarget()
    theme = theme_with(toolbars__main_style="TextOnly", toolbars__icons_in_menus=False)
    assert not target.is_active(theme, runner)
    target.reload(theme, runner)
    assert runner.get("kdeglobals", ["Toolbar style"], "ToolButtonStyle") == "TextOnly"
    assert runner.get("kdeglobals", ["KDE"], "ShowIconsInMenuItems") == "false"
    assert target.is_active(theme, runner)
    sent = [" ".join(argv) for argv in runner.signals]
    assert any("styleChanged" in line for line in sent) and any("notifyChange" in line for line in sent)
    assert any("--notify" in argv for argv in runner.calls if argv[0] == "kwriteconfig6")


def test_feedback_reload_writes_klaunchrc(home, desktop_runner):
    runner = desktop_runner
    target = LaunchFeedbackTarget()
    theme = theme_with(feedback__cursor="blinking", feedback__cursor_timeout=12, feedback__taskbar=False)
    target.reload(theme, runner)
    assert runner.get("klaunchrc", ["FeedbackStyle"], "BusyCursor") == "true"
    assert runner.get("klaunchrc", ["BusyCursorSettings"], "Blinking") == "true"
    assert runner.get("klaunchrc", ["BusyCursorSettings"], "Timeout") == "12"
    assert runner.get("klaunchrc", ["FeedbackStyle"], "TaskbarButton") == "false"
    assert runner.get("klaunchrc", ["TaskbarButtonSettings"], "Timeout") == ""  # not asked for
    assert target.is_active(theme, runner)
    assert any("KLauncher" in " ".join(argv) for argv in runner.signals)


def test_undo_puts_back_the_values_and_removes_the_file_that_was_not_there(home, desktop_runner):
    runner = desktop_runner
    target = LaunchFeedbackTarget()
    before = target.capture_settings(runner)
    assert before["absent"] == ["klaunchrc"]
    target.reload(theme_with(feedback__cursor="none", feedback__taskbar_timeout=9), runner)
    assert kconfig.file_exists("klaunchrc")
    target.restore_settings(before, runner)
    assert not kconfig.file_exists("klaunchrc")


def test_undo_keeps_what_the_user_had(home, desktop_runner):
    runner = desktop_runner
    runner.set("kdeglobals", ["Toolbar style"], "ToolButtonStyle", "TextOnly")
    runner.set("kdeglobals", ["KDE"], "ShowIconsOnPushButtons", "false")
    target = ToolbarsTarget()
    before = target.capture_settings(runner)
    assert before["values"]["main_style"] == "TextOnly" and before["values"]["icons_in_menus"] is None
    target.reload(
        theme_with(
            toolbars__main_style="NoText", toolbars__icons_on_buttons=True, toolbars__icons_in_menus=False
        ),
        runner,
    )
    target.restore_settings(before, runner)
    assert runner.get("kdeglobals", ["Toolbar style"], "ToolButtonStyle") == "TextOnly"
    assert runner.get("kdeglobals", ["KDE"], "ShowIconsOnPushButtons") == "false"
    assert kconfig.user_value("kdeglobals", ["KDE"], "ShowIconsInMenuItems") is None


def test_a_missing_tool_is_said(home, desktop_runner):
    desktop_runner.missing.add("kwriteconfig6")
    assert "kwriteconfig6" in str(ToolbarsTarget().unavailable_reason(desktop_runner))


def test_the_overview_shows_both_in_the_parts_they_belong_to(home, desktop_runner):
    start_from_something(desktop_runner)
    theme = theme_with(toolbars__main_style="TextOnly", feedback__cursor="blinking")
    records = {record.key: record for record in status.parts_status(theme, desktop_runner)}
    assert records["app_style"].state == status.CHANGE
    assert "text only" in records["app_style"].theme
    assert records["pointers"].state == status.CHANGE
    assert "blinking" in records["pointers"].theme
    ToolbarsTarget().reload(theme, desktop_runner)
    LaunchFeedbackTarget().reload(theme, desktop_runner)
    records = {record.key: record for record in status.parts_status(theme, desktop_runner)}
    assert records["app_style"].state == status.SAME and records["pointers"].state == status.SAME
    left = {record.key: record for record in status.parts_status(Theme(), desktop_runner)}
    assert left["app_style"].state == status.LEAVE and left["pointers"].state == status.LEAVE


def test_an_apply_sets_them_and_the_undo_of_that_apply_takes_them_back(home, desktop_runner):
    from plasma_theme_studio import paths
    from plasma_theme_studio.apply import engine

    runner = desktop_runner
    start_from_something(runner)
    runner.set("kdeglobals", ["Toolbar style"], "ToolButtonStyle", "TextOnly")
    before = tree(paths.config_home()), tree(paths.data_home())
    theme = theme_with(
        toolbars__main_style="NoText", toolbars__icons_on_buttons=False, feedback__cursor="blinking"
    )
    plan = engine.build_plan(theme, runner)
    assert [
        t.generator.id for t in plan.wanted_targets if t.generator.id in ("toolbars", "launch_feedback")
    ] == [
        "toolbars",
        "launch_feedback",
    ]
    result = engine.apply(theme, runner)
    assert runner.get("kdeglobals", ["Toolbar style"], "ToolButtonStyle") == "NoText"
    assert runner.get("klaunchrc", ["BusyCursorSettings"], "Blinking") == "true"
    assert engine.restore(result.snapshot, runner, consume=True) == []
    assert (tree(paths.config_home()), tree(paths.data_home())) == before


# ---- the dialogs


@pytest.fixture
def window(app, home, desktop_runner):
    window = MainWindow(desktop_runner)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def test_the_toolbars_dialog_opens_on_the_desktop_and_leaving_stores_nothing(window):
    window.runner.set("kdeglobals", ["Toolbar style"], "ToolButtonStyle", "TextUnderIcon")
    dialog = small_settings.open_toolbars(window)
    assert dialog.isVisible() and dialog.leave.isChecked()
    assert dialog.controls["main_style"].currentData() == "TextUnderIcon"
    assert dialog.controls["main_style"].isEnabled()
    assert set(dialog.values().values()) == {None}
    steps = window.undo_stack.count()
    dialog.accept()
    assert window.undo_stack.count() == steps
    assert window.theme.get("toolbars", "main_style") is None


def test_a_change_selects_set_and_is_one_undo_step(window):
    dialog = small_settings.open_toolbars(window)
    steps = window.undo_stack.count()
    dialog.controls["other_style"].setCurrentIndex(dialog.controls["other_style"].findData("TextOnly"))
    assert dialog.own.isChecked()
    click(dialog.controls["icons_in_menus"])
    dialog.accept()
    assert window.theme.get("toolbars", "other_style") == "TextOnly"
    assert window.theme.get("toolbars", "icons_in_menus") is False
    assert window.undo_stack.count() == steps + 1
    window.undo_stack.undo()
    assert window.theme.get("toolbars", "other_style") is None


def test_choosing_leave_again_shows_the_desktop_and_stores_nothing(window):
    dialog = small_settings.open_toolbars(window)
    dialog.controls["main_style"].setCurrentIndex(dialog.controls["main_style"].findData("NoText"))
    assert dialog.own.isChecked()
    dialog.leave.setChecked(True)
    assert dialog.controls["main_style"].currentData() == "TextBesideIcon"
    assert set(dialog.values().values()) == {None}
    dialog.reject()
    assert window.theme.get("toolbars", "main_style") is None


def test_the_dialog_starts_on_the_values_of_the_theme(window):
    window.edit(FIELD_BY_ID[("feedback", "cursor")], "blinking")
    dialog = small_settings.open_launch_feedback(window)
    assert dialog.own.isChecked()
    assert dialog.controls["cursor"].currentData() == "blinking"
    dialog.reject()


def test_the_feedback_dialog_reads_the_desktop_keys(window):
    window.runner.set("klaunchrc", ["FeedbackStyle"], "BusyCursor", "false")
    window.runner.set("klaunchrc", ["TaskbarButtonSettings"], "Timeout", "8")
    dialog = small_settings.open_launch_feedback(window)
    assert dialog.controls["cursor"].currentData() == "none"
    assert dialog.controls["taskbar_timeout"].value() == 8
    dialog.controls["cursor"].setCurrentIndex(dialog.controls["cursor"].findData("bouncing"))
    dialog.controls["cursor_timeout"].setValue(20)
    dialog.accept()
    assert window.theme.get("feedback", "cursor") == "bouncing"
    assert window.theme.get("feedback", "cursor_timeout") == 20
    assert window.theme.get("feedback", "taskbar_timeout") == 8


def test_the_model_checks_the_values():
    from plasma_theme_studio.model.theme import ThemeError

    theme = Theme()
    with pytest.raises(ThemeError):
        theme.set("feedback", "cursor", "spinning")
    with pytest.raises(ThemeError):
        theme.set("feedback", "cursor_timeout", 0)
    with pytest.raises(ThemeError):
        theme.set("toolbars", "main_style", "Large")
    theme.set("toolbars", "icons_in_menus", False)
    assert theme.get("toolbars", "icons_in_menus") is False
