# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Undo, restoring an older snapshot and applying again: the editor and the desktop stay in step."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QMessageBox  # noqa: E402

from plasma_theme_studio import paths  # noqa: E402
from plasma_theme_studio.apply import snapshot as snapshots  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def window(app, home, runner, monkeypatch):
    window = MainWindow(runner)
    window.problems = []
    monkeypatch.setattr(window, "_show_problems", lambda title, problems: window.problems.append(title))
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


@pytest.fixture
def nordic(home, runner):
    folder = home / "system/share/color-schemes"
    folder.mkdir(parents=True)
    (folder / "Nordic.colors").write_text(
        "[Colors:Selection]\nBackgroundNormal=136,192,208\n[Colors:Window]\n"
        "BackgroundNormal=46,52,64\nForegroundNormal=216,222,233\n[General]\nName=Nordic\n"
    )
    runner.known.add("Nordic")


def test_a_scheme_is_not_called_in_use_after_the_desktop_changed_elsewhere(nordic, window, runner):
    """What the desktop uses is asked for at the switch, not remembered from before."""
    window.tabs.setCurrentWidget(window.library)
    window.library.select("Nordic")
    window.apply_button.click()
    assert runner.settings["ColorScheme"] == "Nordic"
    # The user changes the scheme in System Settings while the app stays open.
    runner.settings["ColorScheme"] = "BreezeDark"
    window.apply_button.click()
    assert "already uses" not in window.banner.text()
    assert runner.settings["ColorScheme"] == "Nordic"


def test_restoring_an_older_snapshot_undoes_the_applies_after_it_too(window, runner):
    scheme = paths.color_schemes_dir() / "BreezeLightCopy.colors"
    window.apply_theme()
    window.edit(FIELD_BY_ID[("colors", "accent")], "#ff0000")
    window.apply_theme()
    window.edit(FIELD_BY_ID[("colors", "accent")], "#0000ff")
    window.apply_theme()
    newest, middle, oldest = snapshots.list_snapshots()

    window._restore(middle)

    assert runner.settings["ColorScheme"] == "BreezeLightCopy"
    assert "255,0,0" not in scheme.read_text() and "0,0,255" not in scheme.read_text()
    assert [item.id for item in snapshots.list_snapshots()] == [oldest.id]
    assert f"{middle.created_at:%H:%M:%S}" in window.banner.text()

    # Undo goes on from there. It does not put back what was rolled away from.
    window.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert not scheme.exists()
    assert not window.undo_apply_button.isEnabled()


def test_edit_and_apply_after_an_undo_puts_the_editor_theme_on_the_desktop_again(window, runner):
    """Apply, look, undo, change, apply: the theme in the editor is what apply applies."""
    window.apply_theme()
    window.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert window.theme.name == "Breeze Light Copy"  # an undo of an apply leaves the editor alone
    window.edit(FIELD_BY_ID[("colors", "accent")], "#ff0000")
    window.apply_theme()
    assert runner.settings["ColorScheme"] == "BreezeLightCopy"
    assert "255,0,0" in (paths.color_schemes_dir() / "BreezeLightCopy.colors").read_text()


def test_the_scheme_written_from_the_editor_theme_is_applied_with_the_edits(window, runner, monkeypatch):
    """On the Themes tab the theme in the editor shows as the scheme an apply
    wrote from it. Choosing that one must not swap the editor for a plain copy."""
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: pytest.fail("asked")))
    held = window.theme
    window.apply_theme()
    window.edit(FIELD_BY_ID[("colors", "accent")], "#ff0000")
    window.tabs.setCurrentWidget(window.library)
    assert window.library.select("BreezeLightCopy").title == "Breeze Light Copy"

    window.apply_button.click()

    assert window.theme is held and window.isWindowModified()
    assert runner.settings["ColorScheme"] == "BreezeLightCopy"
    assert "255,0,0" in (paths.color_schemes_dir() / "BreezeLightCopy.colors").read_text()


def test_undo_of_a_scheme_switch_marks_the_right_theme_in_use(nordic, window, runner):
    window.tabs.setCurrentWidget(window.library)
    window.library.select("Nordic")
    window.apply_button.click()
    window.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert window.library.active == "BreezeLight"
    assert "In use" not in window.library.list.currentItem().text()


def test_failed_apply_rolls_back_and_leaves_editor_and_desktop_in_step(window, runner, home):
    window.apply_theme()
    count = len(snapshots.list_snapshots())
    window.edit(FIELD_BY_ID[("colors", "accent")], "#ff0000")
    runner.handlers["plasma-apply-colorscheme"] = lambda argv: __import__(
        "plasma_theme_studio.apply.runner", fromlist=["Result"]
    ).Result(1, "", "boom")
    window.apply_theme()
    assert window.problems
    assert runner.settings["ColorScheme"] == "BreezeLightCopy"
    assert window.theme.get("colors", "accent") == "#ff0000"  # edits kept
    assert len(snapshots.list_snapshots()) <= count + 1


def test_apply_after_undo_says_so_not_already_current(window, runner):
    window.apply_theme()
    window.undo_last_apply()
    window.apply_theme()
    assert runner.settings["ColorScheme"] == "BreezeLightCopy"
    assert "already uses" not in window.banner.text()
