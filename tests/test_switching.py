# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Switching themes on the Themes page and then editing.

The rule these tests state: the editor always holds the theme the user last put
on the desktop from the Themes page, so an edit followed by apply changes that
theme and never brings an earlier one back. Unsaved edits are not lost silently.
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QCoreApplication, QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from plasma_theme_studio import paths  # noqa: E402
from plasma_theme_studio.apply import snapshot as snapshots  # noqa: E402
from plasma_theme_studio.generators import windowframe as wf  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID, Theme  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from test_desktop import calls  # noqa: E402
from test_panellayout import FakePlasmashell, panel  # noqa: E402
from test_windowframe import Kwin  # noqa: E402

LOCATION = FIELD_BY_ID[("panel_layout", "location")]
ACCENT = FIELD_BY_ID[("colors", "accent")]
DECORATION = FIELD_BY_ID[("window", "decoration")]
NORDIC_WINDOW = "46,52,64"


@pytest.fixture
def desk(app, home, runner, monkeypatch):
    """A desktop with one bottom panel and plain Breeze frames, a saved theme
    "Mine" (red accent), a saved theme "Other" (green accent), the scheme
    Nordic, and a window that has just started."""
    monkeypatch.setattr(wf, "_pause", lambda seconds: None)
    for folder in (paths.config_home(), paths.data_home()):
        folder.mkdir(parents=True, exist_ok=True)
    kwin = Kwin(runner)
    shell = FakePlasmashell(runner, [panel(161, location="bottom")])
    runner.handlers["qdbus6"] = lambda argv: kwin(argv) if argv[1] == "org.kde.KWin" else shell.run(argv)
    folder = home / "system/share/color-schemes"
    folder.mkdir(parents=True)
    (folder / "Nordic.colors").write_text(
        "[Colors:Selection]\nBackgroundNormal=136,192,208\n[Colors:Window]\n"
        f"BackgroundNormal={NORDIC_WINDOW}\nForegroundNormal=216,222,233\n[General]\nName=Nordic\n"
    )
    runner.known.add("Nordic")
    paths.themes_dir().mkdir(parents=True, exist_ok=True)
    Theme({("meta", "name"): "Mine", ("colors", "accent"): "#ff0000"}).save(paths.themes_dir() / "mine.toml")
    Theme({("meta", "name"): "Other", ("colors", "accent"): "#00ff00"}).save(
        paths.themes_dir() / "other.toml"
    )
    window = MainWindow(runner)
    window.build_pages()
    window.show()
    window.shell = shell
    window.paths = paths
    yield window
    window.undo_stack.setClean()
    window.close()


def use(window, title, how="apply"):
    """Select an entry on the Themes page and put it on the desktop, either with the
    button alone ("apply") or by clicking the card and then the button ("click")."""
    window.show_page("themes")
    entry = window.library.select(title)
    assert entry is not None, title
    if how == "click":
        grid = window.library.grid
        QCoreApplication.processEvents()  # let the grid lay itself out
        card = grid.card(grid.selected_id())
        grid.scroll.ensureWidgetVisible(card)
        QCoreApplication.processEvents()
        QTest.mouseClick(card, Qt.MouseButton.LeftButton)
        QTest.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)
    else:
        window.apply_button.click()
    QCoreApplication.processEvents()
    return entry


def press_apply_on_editor_tab(window):
    window.show_page("overview")
    window.apply_button.click()


def scheme_file(window, runner):
    return paths.color_schemes_dir() / f"{runner.settings['ColorScheme']}.colors"


def in_use(window):
    """The titles of the entries the Themes page marks as in use."""
    return [card.title() for card in window.library.grid.cards if card.in_use]


def last_file():
    return QSettings().value("last_file", "")


# ---- the reported bug: a panel edit after a switch brings the old theme back --------------------


@pytest.mark.parametrize("how", ["apply", "click"])
def test_saved_theme_then_panel_edit_keeps_the_switched_theme(desk, runner, how):
    use(desk, "Other", how)
    assert runner.settings["ColorScheme"] == "Other"
    desk.edit(LOCATION, "top")
    press_apply_on_editor_tab(desk)
    assert runner.settings["ColorScheme"] == "Other"  # not "BreezeLightCopy"
    assert desk.shell.state()["location"] == "top"
    assert desk.theme.get("colors", "accent") == "#00ff00"
    assert "0,255,0" in scheme_file(desk, runner).read_text()


@pytest.mark.parametrize("how", ["apply", "click"])
def test_scheme_then_panel_edit_keeps_the_switched_colors(desk, runner, how):
    use(desk, "Nordic", how)
    assert runner.settings["ColorScheme"] == "Nordic"
    desk.edit(LOCATION, "top")
    press_apply_on_editor_tab(desk)
    assert runner.settings["ColorScheme"] == "NordicCopy"
    assert NORDIC_WINDOW in scheme_file(desk, runner).read_text()
    assert desk.shell.state()["location"] == "top"


def test_saved_theme_then_color_edit_changes_that_theme(desk, runner):
    use(desk, "Other")
    desk.edit(ACCENT, "#123456")
    press_apply_on_editor_tab(desk)
    assert runner.settings["ColorScheme"] == "Other"
    text = scheme_file(desk, runner).read_text()
    assert "18,52,86" in text  # the new accent
    assert "BackgroundNormal=239,240,241" in text  # Breeze Light's window color, as "Other" has no own


def test_scheme_then_color_edit_changes_that_scheme(desk, runner):
    use(desk, "Nordic")
    desk.edit(ACCENT, "#123456")
    press_apply_on_editor_tab(desk)
    assert runner.settings["ColorScheme"] == "NordicCopy"
    text = scheme_file(desk, runner).read_text()
    assert "18,52,86" in text and NORDIC_WINDOW in text


def test_saved_theme_then_window_edit_keeps_the_switched_theme(desk, runner):
    use(desk, "Other")
    desk.edit(DECORATION, "breeze")
    press_apply_on_editor_tab(desk)
    assert runner.settings["ColorScheme"] == "Other"
    assert "kwin" in calls_of(runner)


def test_scheme_then_window_edit_keeps_the_switched_colors(desk, runner):
    use(desk, "Nordic")
    desk.edit(DECORATION, "breeze")
    press_apply_on_editor_tab(desk)
    assert runner.settings["ColorScheme"] == "NordicCopy"
    assert "kwin" in calls_of(runner)


def calls_of(runner):
    class Desk:  # the shape test_desktop.calls reads
        pass

    holder = Desk()
    holder.runner = runner
    return calls(holder)


# ---- what the editor holds right after a switch -------------------------------------------------


def test_the_editor_holds_the_saved_theme_that_was_switched_to(desk):
    use(desk, "Other")
    assert desk.theme.name == "Other"
    assert desk.theme.get("colors", "accent") == "#00ff00"
    assert desk.path is not None and desk.path.name == "other.toml"
    assert not desk.isWindowModified()
    assert desk.editors[("colors", "accent")].text.text() == "#00ff00"


def test_the_editor_holds_the_scheme_that_was_switched_to(desk):
    use(desk, "Nordic")
    assert desk.theme.get("colors", "window") == "#2e3440"
    assert desk.path is None
    assert desk.editors[("colors", "window")].text.text() == "#2e3440"


def test_stays_on_the_themes_tab_after_a_switch(desk):
    use(desk, "Other")
    assert desk.current_key == "themes"


def test_scheme_then_apply_without_any_edit_leaves_the_desktop_on_that_scheme(desk, runner):
    use(desk, "Nordic")
    press_apply_on_editor_tab(desk)
    assert runner.settings["ColorScheme"] == "NordicCopy"  # the theme the editor made of it
    assert NORDIC_WINDOW in scheme_file(desk, runner).read_text()


def test_saved_theme_then_apply_without_any_edit_changes_nothing(desk, runner):
    use(desk, "Other")
    count = len(snapshots.list_snapshots())
    press_apply_on_editor_tab(desk)
    assert runner.settings["ColorScheme"] == "Other"
    assert "already uses Other" in desk.banner.text()
    assert len(snapshots.list_snapshots()) == count


# ---- the apply button, the title, last_file and "In use" ----------------------------------------


def test_apply_button_names_the_switched_saved_theme_on_every_tab(desk):
    use(desk, "Other")
    assert desk.apply_button.toolTip() == "Apply “Other” to the desktop"
    for key in ("overview", "colors", "panel"):
        desk.show_page(key)
        assert desk.apply_button.toolTip() == "Apply “Other” to the desktop"
    desk.show_page("themes")
    assert desk.apply_button.toolTip() == "Apply “Other” to the desktop"


def test_apply_button_names_the_switched_scheme_on_the_editor_tabs(desk):
    use(desk, "Nordic")
    assert desk.apply_button.toolTip() == "Apply “Nordic” to the desktop"  # the Themes page: the selection
    desk.show_page("overview")
    assert "Nordic" in desk.apply_button.toolTip()
    assert "Breeze Light Copy" not in desk.apply_button.toolTip()


def test_window_title_names_the_switched_theme(desk):
    use(desk, "Other")
    assert desk.windowTitle().startswith("Other (other.toml)")
    use(desk, "Nordic")
    assert "Nordic" in desk.windowTitle() and "Breeze Light Copy" not in desk.windowTitle()


def test_last_file_follows_the_switched_saved_theme(desk):
    use(desk, "Other")
    assert last_file() == str(paths.themes_dir() / "other.toml")


def test_in_use_marks_exactly_the_switched_theme_after_each_step(desk, runner, monkeypatch):
    # The edit below leaves unsaved changes; the second switch may ask about them.
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    )
    assert in_use(desk) == []
    use(desk, "Other")
    assert in_use(desk) == ["Other"]
    desk.edit(LOCATION, "top")
    press_apply_on_editor_tab(desk)
    assert in_use(desk) == ["Other"]  # not a "Breeze Light Copy" that appeared by itself
    use(desk, "Nordic")
    assert in_use(desk) == ["Nordic"]
    desk.edit(LOCATION, "left")
    press_apply_on_editor_tab(desk)
    assert in_use(desk) == ["Nordic Copy"]


def test_undo_after_a_switch_and_an_edit_apply_goes_back_one_step_at_a_time(desk, runner):
    use(desk, "Other")
    desk.edit(LOCATION, "top")
    press_apply_on_editor_tab(desk)
    desk.undo_last_apply()
    assert desk.shell.state()["location"] == "bottom"
    assert runner.settings["ColorScheme"] == "Other"
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"


# ---- the entry that is the file open in the editor ----------------------------------------------


def open_mine_with_unsaved_edit(window):
    assert window.open_path(paths.themes_dir() / "mine.toml")
    window.edit(ACCENT, "#0000ff")
    assert window.isWindowModified()


def test_the_open_file_is_applied_with_its_unsaved_edits_and_they_stay(desk, runner):
    open_mine_with_unsaved_edit(desk)
    use(desk, "Mine")
    assert "0,0,255" in scheme_file(desk, runner).read_text()
    assert desk.theme.get("colors", "accent") == "#0000ff"
    assert desk.isWindowModified()
    assert desk.path.name == "mine.toml"
    assert in_use(desk) == ["Mine"]


def test_edit_after_applying_the_open_file_keeps_its_unsaved_edits(desk, runner):
    open_mine_with_unsaved_edit(desk)
    use(desk, "Mine")
    desk.edit(LOCATION, "top")
    press_apply_on_editor_tab(desk)
    assert runner.settings["ColorScheme"] == "Mine"
    assert "0,0,255" in scheme_file(desk, runner).read_text()


# ---- switching while the editor has unsaved changes ---------------------------------------------


@pytest.fixture
def asked(monkeypatch):
    """Records the "Unsaved changes" question and answers it with `answer`."""
    box = {"count": 0, "answer": QMessageBox.StandardButton.Cancel}

    def warning(parent, title, text, buttons, default=None):
        box["count"] += 1
        return box["answer"]

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(warning))
    return box


@pytest.mark.parametrize("target", ["Other", "Nordic"])
def test_switching_with_unsaved_edits_asks_and_cancel_changes_nothing(desk, runner, asked, target):
    open_mine_with_unsaved_edit(desk)
    use(desk, target)
    assert asked["count"] == 1
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme.get("colors", "accent") == "#0000ff" and desk.path.name == "mine.toml"
    assert desk.isWindowModified()


@pytest.mark.parametrize("target", ["Other", "Nordic"])
def test_switching_with_unsaved_edits_and_discard_loads_the_new_theme(desk, runner, asked, target):
    open_mine_with_unsaved_edit(desk)
    asked["answer"] = QMessageBox.StandardButton.Discard
    use(desk, target)
    assert asked["count"] == 1
    assert runner.settings["ColorScheme"] in (target, f"{target}Copy")
    assert "Mine" not in desk.theme.name and not desk.isWindowModified()
    assert (paths.themes_dir() / "mine.toml").read_text().count("#0000ff") == 0


def test_switching_with_unsaved_edits_and_save_keeps_them_in_the_file(desk, runner, asked):
    open_mine_with_unsaved_edit(desk)
    asked["answer"] = QMessageBox.StandardButton.Save
    use(desk, "Other")
    assert "#0000ff" in (paths.themes_dir() / "mine.toml").read_text().lower()
    assert runner.settings["ColorScheme"] == "Other"
    assert desk.theme.name == "Other"


def test_switching_with_a_clean_editor_does_not_ask(desk, asked):
    use(desk, "Other")
    use(desk, "Nordic")
    assert asked["count"] == 0


# ---- a switch that does not happen, and one that is not needed ----------------------------------


@pytest.fixture
def problems(desk, monkeypatch):
    shown = []
    monkeypatch.setattr(desk, "_show_problems", lambda title, lines: shown.append(title))
    return shown


def test_a_scheme_switch_that_fails_leaves_the_editor_alone(desk, runner, problems):
    held = desk.theme
    runner.known.discard("Nordic")  # Plasma does not find it
    use(desk, "Nordic")
    assert problems == ["The desktop could not be switched. Nothing was changed."]
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme is held and desk.path is None
    assert not last_file() and snapshots.list_snapshots() == []


def test_a_theme_switch_that_fails_leaves_the_editor_alone(desk, runner, problems, home):
    held = desk.theme
    runner.schemes_dir = home / "nowhere"  # Plasma does not find what the apply wrote
    use(desk, "Other")
    assert problems == ["The apply failed. Everything was put back as it was."]
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme is held and desk.path is None
    assert not last_file() and snapshots.list_snapshots() == []


def test_choosing_the_theme_the_desktop_has_already_still_brings_it_into_the_editor(desk, runner):
    use(desk, "Other")
    assert desk.open_path(paths.themes_dir() / "mine.toml")
    use(desk, "Other")
    assert "already uses Other" in desk.banner.text()
    assert desk.theme.name == "Other" and desk.path.name == "other.toml"
    assert len(snapshots.list_snapshots()) == 1


def test_the_banner_of_a_scheme_switch_names_the_new_theme(desk):
    use(desk, "Nordic")
    assert desk.banner.text().endswith(
        "Changes you make in the editor go into Nordic Copy, a new theme that is not saved yet."
    )


# ---- undoing a switch -----------------------------------------------------------------------------


def test_undoing_a_switch_to_a_saved_theme_brings_the_editor_back(desk, runner):
    assert desk.open_path(paths.themes_dir() / "mine.toml")
    use(desk, "Other")
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme.name == "Mine" and desk.path.name == "mine.toml"
    assert desk.editors[("colors", "accent")].text.text() == "#ff0000"
    assert last_file() == str(paths.themes_dir() / "mine.toml")
    assert desk.banner.text().endswith("The editor holds Mine again.")
    assert not desk.isWindowModified()


def test_undoing_a_switch_to_a_scheme_brings_the_unsaved_theme_back(desk, runner):
    held = desk.theme
    use(desk, "Nordic")
    assert desk.theme is not held
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme is held and desk.path is None
    assert "The editor holds Breeze Light Copy again." in desk.banner.text()


def test_the_file_the_next_start_opens_goes_back_with_the_editor(desk):
    assert not last_file()
    use(desk, "Other")
    assert last_file()
    desk.undo_last_apply()
    assert desk.path is None and not last_file()


def test_two_switches_are_undone_one_at_a_time(desk, runner):
    use(desk, "Other")
    use(desk, "Nordic")
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "Other"
    assert desk.theme.name == "Other" and desk.path.name == "other.toml"
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme.name == "Breeze Light Copy" and desk.path is None


def test_restoring_the_snapshot_of_the_first_switch_takes_the_editor_all_the_way_back(desk, runner):
    use(desk, "Other")
    use(desk, "Nordic")
    desk._restore(snapshots.list_snapshots()[-1])
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme.name == "Breeze Light Copy"
    assert snapshots.list_snapshots() == []


def test_an_apply_from_the_editor_is_undone_before_the_switch_is(desk, runner):
    use(desk, "Other")
    desk.edit(LOCATION, "top")
    assert desk.save()
    press_apply_on_editor_tab(desk)
    desk.undo_last_apply()
    assert desk.theme.name == "Other"  # only the panel went back
    assert "editor holds" not in desk.banner.text()
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme.name == "Breeze Light Copy"


def test_the_editor_stays_when_it_has_changes_that_are_not_saved(desk, runner):
    use(desk, "Other")
    desk.edit(LOCATION, "top")
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme.name == "Other" and desk.theme.get("panel_layout", "location") == "top"
    assert desk.isWindowModified()
    assert "editor holds" not in desk.banner.text()


def test_the_editor_stays_when_it_holds_another_theme_by_now(desk, runner):
    use(desk, "Other")
    assert desk.open_path(paths.themes_dir() / "mine.toml")
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme.name == "Mine"


def test_changes_discarded_at_the_switch_do_not_come_back_with_the_undo(desk, runner, asked):
    open_mine_with_unsaved_edit(desk)
    asked["answer"] = QMessageBox.StandardButton.Discard
    use(desk, "Other")
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme.name == "Other" and not desk.isWindowModified()


def test_the_editor_stays_when_the_file_it_held_is_gone(desk):
    assert desk.open_path(paths.themes_dir() / "mine.toml")
    use(desk, "Other")
    (paths.themes_dir() / "mine.toml").unlink()
    desk.undo_last_apply()
    assert desk.theme.name == "Other"


def test_an_undo_that_fails_leaves_the_editor_until_it_works(desk, runner, monkeypatch):
    problems = []
    monkeypatch.setattr(desk, "_show_problems", lambda title, lines: problems.append(title))
    use(desk, "Other")
    runner.known.discard("BreezeLight")  # Plasma cannot go back to it
    desk.undo_last_apply()
    assert problems == ["Some things could not be put back."]
    assert desk.theme.name == "Other"
    runner.known.add("BreezeLight")
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert desk.theme.name == "Breeze Light Copy"


def test_a_switch_whose_snapshot_was_removed_as_too_old_is_not_taken_for_undone(desk, runner, monkeypatch):
    monkeypatch.setattr(snapshots.prune, "__defaults__", (2,))
    use(desk, "Other")
    for accent in ("#111111", "#222222", "#333333"):
        desk.edit(ACCENT, accent)
        assert desk.save()
        press_apply_on_editor_tab(desk)
    assert len(snapshots.list_snapshots()) == 2
    desk.undo_last_apply()
    assert runner.settings["ColorScheme"] == "Other"
    assert desk.theme.name == "Other"


# ---- a frame made by this app follows the scheme ------------------------------------------------


def generated_frame_theme():
    return Theme(
        {
            ("meta", "name"): "Framed",
            ("window", "decoration"): "generated",
            ("window", "radius"): 12,
            ("window", "border_width"): 3,
            ("shadow", "size"): 20,
        }
    )


def test_a_scheme_switch_recolors_a_generated_frame_and_one_undo_brings_both_back(desk, runner):
    from plasma_theme_studio.apply import engine

    engine.apply(generated_frame_theme(), runner)
    root = paths.data_home() / "aurorae/themes"
    before = sorted(p.name for p in root.iterdir())
    kwinrc = (paths.config_home() / "kwinrc").read_text()

    use(desk, "Nordic")

    after = sorted(p.name for p in root.iterdir())
    assert runner.settings["ColorScheme"] == "Nordic"
    assert len(after) == 1 and after != before
    assert wf.frame_in_use_shape() == (12, 3, 20, 0.35)
    assert "#2e3440" in (root / after[0] / "decoration.svg").read_text()  # Nordic's window color

    desk.undo_last_apply()

    assert runner.settings["ColorScheme"] == "Framed"
    assert sorted(p.name for p in root.iterdir()) == before
    assert (paths.config_home() / "kwinrc").read_text() == kwinrc


def test_a_scheme_switch_without_a_frame_of_ours_writes_no_frame(desk, runner):
    use(desk, "Nordic")
    assert runner.settings["ColorScheme"] == "Nordic"
    assert not (paths.data_home() / "aurorae").exists()


def test_a_scheme_switch_still_works_when_the_frame_cannot_be_recolored(desk, runner):
    from plasma_theme_studio.apply import engine

    engine.apply(generated_frame_theme(), runner)
    root = paths.data_home() / "aurorae/themes"
    before = sorted(p.name for p in root.iterdir())
    nordic = desk.library.select("Nordic").theme
    blocker = root / wf.frame_folder(nordic) / "decoration.svg"
    blocker.parent.mkdir()
    blocker.write_text("not ours")

    use(desk, "Nordic")

    assert runner.settings["ColorScheme"] == "Nordic"
    assert sorted(p.name for p in root.iterdir()) == sorted([*before, blocker.parent.name])
    assert blocker.read_text() == "not ours"
    assert wf.frame_in_use_shape() == (12, 3, 20, 0.35)  # the old frame is still the one in use
