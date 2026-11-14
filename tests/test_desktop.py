# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every target together, as the app registers them: colors, window frame, panel
style and panel position, against stand-ins for KWin, plasmashell and the
style tool. Through the engine, the window and the command line."""

import hashlib
from types import SimpleNamespace

import pytest

from plasma_theme_studio import cli, generators, kconfig, paths
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.generators import ApplyError
from plasma_theme_studio.generators import windowframe as wf
from plasma_theme_studio.generators.plasmastyle import style_id
from plasma_theme_studio.model.theme import FIELD_BY_ID, Theme
from test_panellayout import FakePlasmashell, panel
from test_plasmastyle import fake_style_tool
from test_windowframe import Kwin

KWIN = ("kwinrc", ["org.kde.kdecoration2"])


@pytest.fixture
def desktop(home, runner, monkeypatch):
    """A desktop with one panel at the bottom, Breeze frames and Breeze Light colors."""
    monkeypatch.setattr(wf, "_pause", lambda seconds: None)
    for folder in (paths.config_home(), paths.data_home()):
        folder.mkdir(parents=True)  # every home has them
    kwin = Kwin(runner)
    shell = FakePlasmashell(runner, [panel(161)])
    fake_style_tool(runner)
    runner.handlers["qdbus6"] = lambda argv: kwin(argv) if argv[1] == "org.kde.KWin" else shell.run(argv)
    return SimpleNamespace(runner=runner, kwin=kwin, shell=shell, home=home)


def rounded(**values):
    """A theme that uses every target; keys are written "section__key"."""
    base = {
        ("meta", "name"): "Rounded",
        ("window", "decoration"): "generated",
        ("window", "radius"): 14,
        ("window", "border_width"): 2,
        ("shadow", "size"): 32,
        ("panel", "style"): "generated",
        ("panel", "radius"): 20,
        ("panel_layout", "location"): "top",
        ("panel_layout", "floating"): False,
    }
    base.update({tuple(key.split("__")): value for key, value in values.items()})
    return Theme(base)


def system_state(desktop):
    """Everything an apply may touch: the files outside the app's own folder,
    the color scheme in use and the panel."""
    own = paths.snapshots_dir().parent
    files = {
        str(path.relative_to(desktop.home)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(desktop.home.rglob("*"))
        if path.is_file() and own not in path.parents
    }
    folders = sorted(
        str(path.relative_to(desktop.home))
        for path in desktop.home.rglob("*")
        if path.is_dir() and own not in path.parents and path != own
    )
    return files, folders, desktop.runner.settings["ColorScheme"], desktop.shell.state()


def calls(desktop, *programs):
    """The reload steps in the order they ran."""
    steps = []
    for argv in desktop.runner.calls:
        if argv[0] == "qdbus6" and argv[1] == "org.kde.KWin" and argv[-1] == "reconfigure":
            steps.append("kwin")
        elif argv[0] == "qdbus6" and argv[1] == "org.kde.plasmashell" and '"op": "write"' in argv[-1]:
            steps.append("panel layout")
        elif argv[0] == "plasma-apply-desktoptheme":
            steps.append("panel style")
        elif argv[0] == "plasma-apply-colorscheme":
            steps.append("colors")
    return steps


# ---- the registered targets ----------------------------------------------------------


def test_the_app_registers_every_target_in_the_order_they_are_applied():
    assert [generator.id for generator in generators.GENERATORS] == [
        "colors",
        "window",
        "panel",
        "panel_layout",
    ]
    assert generators.section_generators("shadow") == [generators.generator_by_id("window")]
    assert generators.section_generators("shape") == []


def test_a_new_theme_only_changes_the_colors(desktop):
    plan = engine.build_plan(Theme(), desktop.runner)
    assert [target.generator.id for target in plan.wanted_targets] == ["colors"]
    assert plan.blocking == []

    result = engine.apply(Theme(), desktop.runner)

    assert set(result.snapshot.settings) == {"colors"}
    assert calls(desktop) == ["colors"]
    assert desktop.shell.scripts == [] and desktop.kwin.reconfigured == 0
    assert list(paths.config_home().iterdir()) == []


# ---- the engine ------------------------------------------------------------------------


def test_everything_is_put_on_the_desktop_and_undo_takes_it_all_back(desktop):
    theme = rounded()
    before = system_state(desktop)
    plan = engine.build_plan(theme, desktop.runner)
    assert plan.blocking == []
    assert [target.generator.id for target in plan.wanted_targets] == [
        "colors",
        "window",
        "panel",
        "panel_layout",
    ]
    assert not engine.is_current(plan, desktop.runner)

    result = engine.apply(theme, desktop.runner)

    assert desktop.runner.settings["ColorScheme"] == "Rounded"
    folder = wf.frame_folder(theme)
    assert (paths.data_home() / "aurorae/themes" / folder / "decoration.svg").exists()
    assert kconfig.user_value(*KWIN, "library") == wf.AURORAE_LIBRARY
    assert kconfig.user_value(*KWIN, "theme") == wf.AURORAE_THEME_PREFIX + folder
    assert (paths.data_home() / "plasma/desktoptheme" / style_id(theme) / "metadata.json").exists()
    assert kconfig.user_value("plasmarc", ["Theme"], "name") == style_id(theme)
    panel_now = desktop.shell.state()
    assert (panel_now["location"], panel_now["floating"]) == ("top", False)
    assert (panel_now["height"], panel_now["alignment"]) == (46, "center")  # not in the theme

    # The style is in place before the panel is moved.
    assert calls(desktop) == ["colors", "kwin", "panel style", "panel layout"]
    assert set(result.snapshot.settings) == {"colors", "window", "panel", "panel_layout"}
    assert engine.is_current(engine.build_plan(theme), desktop.runner)

    assert engine.restore(result.snapshot, desktop.runner, consume=True) == []

    assert system_state(desktop) == before
    assert desktop.kwin.reconfigured == 2
    assert not engine.is_current(engine.build_plan(theme), desktop.runner)
    assert snapshots.list_snapshots() == []


def test_undo_goes_back_one_apply_at_a_time(desktop):
    start = system_state(desktop)
    first, second = rounded(), rounded(window__radius=6, panel__radius=4, panel_layout__location="left")
    one = engine.apply(first, desktop.runner)
    after_first = system_state(desktop)

    two = engine.apply(second, desktop.runner)

    # The folders of the first look are gone; each look has a folder of its own.
    assert wf.frame_folder(first) != wf.frame_folder(second) and style_id(first) != style_id(second)
    assert [p.name for p in (paths.data_home() / "aurorae/themes").iterdir()] == [wf.frame_folder(second)]
    assert [p.name for p in (paths.data_home() / "plasma/desktoptheme").iterdir()] == [style_id(second)]
    assert desktop.shell.state()["location"] == "left"

    assert engine.restore(two.snapshot, desktop.runner, consume=True) == []
    assert system_state(desktop) == after_first
    assert engine.is_current(engine.build_plan(first), desktop.runner)

    assert engine.restore(one.snapshot, desktop.runner, consume=True) == []
    assert system_state(desktop) == start


def test_only_the_parts_a_theme_asks_for_are_touched(desktop):
    theme = Theme({("window", "decoration"): "breeze", ("shadow", "size"): 48, ("panel", "radius"): 20})
    result = engine.apply(theme, desktop.runner)

    assert set(result.snapshot.settings) == {"colors", "window"}
    assert calls(desktop) == ["colors", "kwin"]
    assert desktop.shell.scripts == [] and desktop.runner.calls_to_tool == []
    assert kconfig.user_value("breezerc", ["Common"], "ShadowSize") == "ShadowLarge"
    assert not (paths.data_home() / "plasma").exists()
    assert not (paths.config_home() / "plasmarc").exists()


def test_a_panel_that_refuses_its_place_rolls_back_every_target_before_it(desktop):
    before = system_state(desktop)
    desktop.shell.ignore = {"location"}

    with pytest.raises(ApplyError, match="panel"):
        engine.apply(rounded(), desktop.runner)

    assert system_state(desktop) == before
    assert calls(desktop)[:4] == ["colors", "kwin", "panel style", "panel layout"]
    assert desktop.kwin.reconfigured == 2  # once to switch, once to go back
    assert snapshots.list_snapshots() == []


def test_a_style_plasma_refuses_leaves_the_panel_where_it_is(desktop):
    before = system_state(desktop)
    desktop.runner.handlers["plasma-apply-desktoptheme"] = lambda argv: Result(255, "", "Could not find it")

    with pytest.raises(ApplyError):
        engine.apply(rounded(), desktop.runner)

    assert system_state(desktop) == before
    assert desktop.shell.writes == []  # the later target never ran
    assert desktop.runner.settings["ColorScheme"] == "BreezeLight"


def test_a_frame_kwin_does_not_reload_leaves_plasma_alone(desktop):
    before = system_state(desktop)
    desktop.kwin.fail = True

    with pytest.raises(ApplyError, match="KWin"):
        engine.apply(rounded(), desktop.runner)

    assert system_state(desktop) == before
    assert desktop.runner.calls_to_tool == [] and desktop.shell.writes == []


def test_without_plasmashell_nothing_is_changed_at_all(desktop):
    before = system_state(desktop)
    desktop.shell.down = True

    with pytest.raises((engine.ApplyBlocked, ApplyError)):
        engine.apply(rounded(), desktop.runner)

    assert system_state(desktop) == before
    assert calls(desktop) == []
    assert snapshots.list_snapshots() == []


@pytest.mark.parametrize(
    ("missing", "wanted"),
    [("qdbus6", "window"), ("plasma-apply-desktoptheme", "panel"), ("kwriteconfig6", "window")],
)
def test_a_missing_tool_blocks_the_whole_apply(desktop, missing, wanted):
    before = system_state(desktop)
    desktop.runner.missing.add(missing)
    if missing == "qdbus6":
        desktop.runner.missing.add("busctl")

    plan = engine.build_plan(rounded(), desktop.runner)
    blocked = [target.generator.id for target in plan.targets if target.problems]
    assert wanted in blocked
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(rounded(), desktop.runner)

    assert system_state(desktop) == before
    assert calls(desktop) == []


def test_the_plan_names_every_setting_that_changes_besides_the_files(desktop):
    plan = engine.build_plan(rounded())
    settings = {target.generator.id: [str(text) for text in target.settings] for target in plan.targets}
    assert settings["colors"] == []
    assert "kwinrc" in settings["window"][0]
    assert settings["panel"] == []  # its command says it all
    assert "position and shape of the panel" in settings["panel_layout"][0]
    commands = [target.reload_command for target in plan.wanted_targets]
    assert commands[0].startswith("plasma-apply-colorscheme ")
    assert commands[1] == "qdbus6 org.kde.KWin /KWin reconfigure"
    assert commands[2] == f"plasma-apply-desktoptheme {style_id(rounded())}"
    assert all(commands)

    plain = engine.build_plan(Theme())
    assert [target.settings for target in plain.targets] == [[], [], [], []]


def test_a_theme_file_with_every_part_survives_saving(desktop):
    path = desktop.home / "rounded.toml"
    rounded().save(path)
    loaded = Theme.load(path)
    assert loaded == rounded()
    assert wf.frame_folder(loaded) == wf.frame_folder(rounded())
    assert style_id(loaded) == style_id(rounded())


# ---- the window --------------------------------------------------------------------------


@pytest.fixture
def window(app, desktop, monkeypatch):
    from plasma_theme_studio.ui.main_window import MainWindow

    window = MainWindow(desktop.runner)
    window.problems = []
    # The message box would wait for an answer that nobody gives.
    monkeypatch.setattr(
        MainWindow, "_show_problems", lambda self, title, problems: self.problems.append((title, problems))
    )
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def listed_files(window):
    return [window.files_list.item(row).text() for row in range(window.files_list.count())]


def test_the_window_shows_what_a_generated_frame_writes_and_changes(window):
    assert "left as it is" in window.notes["window"].text()
    assert "choose a window frame on the Windows page" in window.notes["shadow"].text()
    assert "kwinrc" not in window.files_info.text()
    assert not any("aurorae" in line for line in listed_files(window))

    window.editors[("window", "decoration")].choose("generated")
    window.refresh()

    assert any(line.split(" — ")[0].endswith("/decoration.svg") for line in listed_files(window))
    assert "left as it is" not in window.notes["window"].text()
    summary = window.files_info.text()
    assert "qdbus6 org.kde.KWin /KWin reconfigure" in summary
    assert "It also changes which window frame KWin uses and its border size (kwinrc)." in summary
    assert summary.endswith("Nothing else on the system is changed.")

    window.editors[("window", "decoration")].choose("breeze")
    window.refresh()
    assert not any("aurorae" in line for line in listed_files(window))
    assert "Breeze fixes the corner radius" in window.notes["window"].text()
    assert "breezerc" in window.files_info.text()


def test_the_window_shows_the_panel_parts_too(window):
    assert "plasma-apply-desktoptheme" not in window.files_info.text()
    window.editors[("panel", "style")].choose("generated")
    window.editors[("panel_layout", "location")].choose("left")
    window.refresh()

    assert any("panel-background.svg" in line for line in listed_files(window))
    summary = window.files_info.text()
    assert f"plasma-apply-desktoptheme {style_id(window.theme)}" in summary
    assert "the position and shape of the panel" in summary


def test_apply_and_undo_through_the_window(window, desktop):
    before = system_state(desktop)
    window.editors[("window", "decoration")].choose("generated")
    window.edit(FIELD_BY_ID[("window", "radius")], 16)
    window.editors[("panel", "style")].choose("generated")
    window.editors[("panel_layout", "location")].choose("top")

    window.apply_theme()

    assert window.problems == []
    assert "Applied" in window.banner.text()
    assert "Not put on the desktop" not in window.banner.text()
    folder = wf.frame_folder(window.theme)
    assert kconfig.user_value(*KWIN, "theme") == wf.AURORAE_THEME_PREFIX + folder
    assert kconfig.user_value("plasmarc", ["Theme"], "name") == style_id(window.theme)
    assert desktop.shell.state()["location"] == "top"
    assert window.undo_apply_button.isEnabled()

    window.apply_theme()
    assert "nothing changed" in window.banner.text()
    assert len(snapshots.list_snapshots()) == 1

    window.undo_last_apply()

    assert window.problems == []
    assert system_state(desktop) == before
    assert "back to how it was" in window.banner.text()
    assert not window.undo_apply_button.isEnabled()


def test_a_changed_radius_reaches_the_desktop_on_the_next_apply(window, desktop):
    """The report that started this: a new window radius did not go through."""
    window.editors[("window", "decoration")].choose("generated")
    window.edit(FIELD_BY_ID[("window", "radius")], 6)
    window.apply_theme()
    first = kconfig.user_value(*KWIN, "theme")

    window.edit(FIELD_BY_ID[("window", "radius")], 18)
    window.apply_theme()

    second = kconfig.user_value(*KWIN, "theme")
    assert "Applied" in window.banner.text() and second != first
    (folder,) = (paths.data_home() / "aurorae/themes").iterdir()
    assert second == wf.AURORAE_THEME_PREFIX + folder.name
    assert desktop.kwin.reconfigured == 2


def test_window_values_without_a_frame_are_named_as_left_out(window, desktop):
    window.edit(FIELD_BY_ID[("window", "radius")], 18)
    window.edit(FIELD_BY_ID[("shadow", "size")], 60)
    window.edit(FIELD_BY_ID[("panel", "radius")], 18)

    window.apply_theme()

    text = window.banner.text()
    assert "Not put on the desktop: " in text
    left_out = text.split("Not put on the desktop: ")[1].split(".")[0].split(", ")
    assert len(left_out) == 3  # windows, shadow and panel, by the names of their pages
    assert desktop.kwin.reconfigured == 0 and desktop.runner.calls_to_tool == []

    window.editors[("window", "decoration")].choose("generated")
    window.apply_theme()
    left_out = window.banner.text().split("Not put on the desktop: ")[1].split(".")[0].split(", ")
    assert len(left_out) == 1  # the panel


def test_a_failed_apply_through_the_window_puts_everything_back(window, desktop):
    before = system_state(desktop)
    window.editors[("window", "decoration")].choose("generated")
    window.editors[("panel_layout", "location")].choose("top")
    desktop.shell.ignore = {"location"}

    window.apply_theme()

    ((title, problems),) = window.problems
    assert title == "The apply failed. Everything was put back as it was."
    assert len(problems) == 1
    assert system_state(desktop) == before
    assert not window.undo_apply_button.isEnabled()


def test_a_missing_tool_is_said_before_anything_is_tried(window, desktop):
    window.editors[("panel", "style")].choose("generated")
    desktop.runner.missing.add("plasma-apply-desktoptheme")

    window.apply_theme()

    ((title, problems),) = window.problems
    assert title == "The theme cannot be applied. Nothing was changed."
    assert any("plasma-apply-desktoptheme" in str(problem) for problem in problems)
    assert desktop.runner.settings["ColorScheme"] == "BreezeLight"


def tired_kwin(desktop):
    """KWin reloads once, for the apply. After that it still answers, but takes no more
    reloads, so a frame cannot be put back."""

    class Tired(Kwin):
        def __call__(self, argv):
            if argv[-1] != "supportInformation" and self.reconfigured >= 1:
                self.fail = True
                self.report = "Decoration\n==========\nPlugin: org.kde.breeze\nTheme: Breeze\n\n"
            return super().__call__(argv)

    desktop.kwin.__class__ = Tired


def rested_kwin(desktop):
    desktop.kwin.__class__ = Kwin
    desktop.kwin.fail, desktop.kwin.report = False, None


def test_a_rollback_that_is_not_complete_is_not_called_complete(window, desktop):
    before = system_state(desktop)
    window.editors[("window", "decoration")].choose("generated")
    window.editors[("panel_layout", "location")].choose("top")
    desktop.shell.ignore = {"location"}  # the apply fails at the panel, after the frame
    tired_kwin(desktop)

    window.apply_theme()

    ((title, (problem,)),) = window.problems
    assert title == "The apply failed, and not everything could be put back."
    assert "could not be asked to reload" in str(problem)
    assert "The snapshot is kept" in str(problem)
    assert len(snapshots.list_snapshots()) == 1
    assert window.undo_apply_button.isEnabled()

    rested_kwin(desktop)
    window.problems.clear()
    window.undo_last_apply()

    assert window.problems == []
    assert system_state(desktop) == before
    assert snapshots.list_snapshots() == []


def test_an_undo_that_fails_through_the_window_can_be_tried_once_more(window, desktop):
    window.editors[("window", "decoration")].choose("generated")
    window.apply_theme()
    tired_kwin(desktop)

    window.undo_last_apply()

    ((title, problems),) = window.problems
    assert title == "Some things could not be put back."
    assert str(problems[-1]) == "The snapshot is kept, so Undo last apply can try once more."
    assert window.undo_apply_button.isEnabled()

    window.problems.clear()
    window.undo_last_apply()

    ((title, problems),) = window.problems
    assert len(problems) == 1 and "snapshot is kept" not in str(problems[0])
    assert not window.undo_apply_button.isEnabled()


def test_a_restore_from_the_list_stops_at_the_apply_it_cannot_undo(window, desktop):
    window.editors[("panel_layout", "location")].choose("top")
    window.apply_theme()
    oldest = snapshots.latest()
    window.editors[("window", "decoration")].choose("generated")
    window.apply_theme()
    tired_kwin(desktop)

    window._restore(oldest)

    ((title, problems),) = window.problems
    assert title == "Some things could not be put back."
    assert str(problems[-2]).startswith("The undo stopped at the apply of ")
    assert str(problems[-2]).endswith(". The applies before it were left as they are.")
    assert str(problems[-1]) == "The snapshot is kept, so Undo last apply can try once more."
    assert desktop.shell.state()["location"] == "top"  # the older apply was not touched
    assert len(snapshots.list_snapshots()) == 2

    rested_kwin(desktop)
    window.problems.clear()
    window._restore(oldest)

    assert window.problems == []
    assert desktop.shell.state()["location"] == "bottom"
    assert snapshots.list_snapshots() == []


def test_the_summary_shows_commands_as_they_are(window):
    """The panel command has "<script>" in it, which a label would take for a tag
    and cut the text there."""
    from PySide6.QtCore import Qt

    window.editors[("panel_layout", "location")].choose("top")
    window.refresh()

    assert window.files_info.textFormat() == Qt.TextFormat.PlainText
    summary = window.files_info.text()
    assert "<script>" in summary
    assert summary.endswith("Nothing else on the system is changed.")


def test_each_page_says_only_what_concerns_it(window):
    from PySide6.QtCore import Qt

    assert window.note_rows["colors"].isHidden()  # nothing to say: no empty row
    assert not window.note_rows["window"].isHidden() and not window.note_rows["shadow"].isHidden()
    assert window.notes["shadow"].text() != window.notes["window"].text()
    for note in window.notes.values():
        assert note.isEnabled()  # readable, not greyed out
        assert note.textFormat() == Qt.TextFormat.PlainText

    window.editors[("window", "decoration")].choose("breeze")
    window.refresh()
    assert "shadow" not in window.notes["window"].text()
    assert "shadow" in window.notes["shadow"].text() and "radius" not in window.notes["shadow"].text()

    window.editors[("window", "decoration")].choose("generated")
    window.refresh()
    assert (
        window.notes["shadow"].text()
        == "The generated window frame draws this shadow, the same on all sides."
    )


# ---- the command line -----------------------------------------------------------------------


@pytest.fixture
def command_line(desktop, monkeypatch):
    monkeypatch.setattr(cli, "SystemRunner", lambda: desktop.runner)
    monkeypatch.setattr(cli, "_load_translation", lambda: None)
    return desktop


def test_the_command_line_applies_every_part_and_restores_it(command_line, capsys):
    desktop = command_line
    path = desktop.home / "rounded.toml"
    rounded(window__radius=24, window__border_width=1).save(path)
    before = system_state(desktop)

    assert cli.main(["apply", str(path)]) == 0

    out = capsys.readouterr().out
    assert "Applied Rounded." in out
    assert "Note: " in out and "corner" in out  # what the generated frame cannot do
    assert kconfig.user_value(*KWIN, "library") == wf.AURORAE_LIBRARY
    assert desktop.shell.state()["location"] == "top"

    assert cli.main(["restore"]) == 0
    assert system_state(desktop) == before


def test_the_command_line_reports_a_rolled_back_apply(command_line, capsys):
    desktop = command_line
    path = desktop.home / "rounded.toml"
    rounded().save(path)
    before = system_state(desktop)
    desktop.kwin.fail = True

    assert cli.main(["apply", str(path)]) == 1

    assert "rolled back" in capsys.readouterr().err
    assert system_state(desktop) == before


def test_the_command_line_says_when_not_everything_was_put_back(command_line, capsys):
    desktop = command_line
    path = desktop.home / "rounded.toml"
    rounded().save(path)
    desktop.shell.ignore = {"location"}
    tired_kwin(desktop)

    assert cli.main(["apply", str(path)]) == 1

    err = capsys.readouterr().err
    assert "The apply failed, and not everything could be put back:" in err
    assert "rolled back" not in err
    assert "The snapshot is kept" in err

    assert cli.main(["restore"]) == 1  # the rollback did not count as a try
    err = capsys.readouterr().err
    assert "Some settings could not be switched back:" in err
    assert "The snapshot is kept. Run the command again to try once more." in err

    assert cli.main(["restore"]) == 1
    assert "Run the command again to try once more" not in capsys.readouterr().err
    assert snapshots.list_snapshots() == []


def test_a_restore_that_fails_on_the_command_line_can_be_run_again(command_line, capsys):
    desktop = command_line
    path = desktop.home / "rounded.toml"
    rounded().save(path)
    before = system_state(desktop)
    assert cli.main(["apply", str(path)]) == 0
    tired_kwin(desktop)

    assert cli.main(["restore"]) == 1
    assert "The snapshot is kept. Run the command again to try once more." in capsys.readouterr().err

    rested_kwin(desktop)
    assert cli.main(["restore"]) == 0
    assert system_state(desktop) == before


def test_the_command_line_does_nothing_when_the_desktop_already_has_the_theme(command_line, capsys):
    desktop = command_line
    path = desktop.home / "rounded.toml"
    rounded().save(path)
    assert cli.main(["apply", str(path)]) == 0
    capsys.readouterr()
    state = system_state(desktop)
    reloads = len(calls(desktop))

    assert cli.main(["apply", str(path)]) == 0

    assert "The desktop already uses Rounded. Nothing was changed." in capsys.readouterr().out
    assert len(snapshots.list_snapshots()) == 1
    assert system_state(desktop) == state and len(calls(desktop)) == reloads

    rounded(window__radius=6).save(path)  # a change is applied as before
    assert cli.main(["apply", str(path)]) == 0
    assert "Applied Rounded." in capsys.readouterr().out
    assert len(snapshots.list_snapshots()) == 2


# ---- from one theme to the next --------------------------------------------------------------------


def test_a_theme_with_colors_only_leaves_the_frame_and_panel_of_the_one_before(desktop):
    """ "Leave as it is" means just that: nothing of the earlier theme is taken away
    while KWin and Plasma still use it."""
    first = rounded()
    engine.apply(first, desktop.runner)

    engine.apply(Theme({("meta", "name"): "Plain"}), desktop.runner)

    folder = wf.frame_folder(first)
    assert (paths.data_home() / "aurorae/themes" / folder / "decoration.svg").exists()
    assert kconfig.user_value(*KWIN, "theme") == wf.AURORAE_THEME_PREFIX + folder
    assert (paths.data_home() / "plasma/desktoptheme" / style_id(first) / "metadata.json").exists()
    assert kconfig.user_value("plasmarc", ["Theme"], "name") == style_id(first)
    assert desktop.shell.state()["location"] == "top"
    assert desktop.runner.settings["ColorScheme"] == "Plain"


def test_a_color_scheme_switch_and_its_undo_leave_the_other_parts_alone(desktop):
    engine.apply(rounded(), desktop.runner)
    state = system_state(desktop)

    snapshot = engine.switch_color_scheme("BreezeDark", "Breeze Dark", desktop.runner)

    assert desktop.runner.settings["ColorScheme"] == "BreezeDark"
    assert list(snapshot.settings) == ["colors"]
    assert engine.restore(snapshot, desktop.runner, consume=True) == []
    assert system_state(desktop) == state


def test_a_theme_applied_again_after_a_scheme_switch_brings_all_of_it_back(desktop):
    engine.apply(rounded(), desktop.runner)
    engine.switch_color_scheme("BreezeDark", "Breeze Dark", desktop.runner)
    moved = rounded(panel_layout__location="left")

    engine.apply(moved, desktop.runner)

    assert desktop.runner.settings["ColorScheme"] == "Rounded"
    assert desktop.shell.state()["location"] == "left"
    assert engine.is_current(engine.build_plan(moved, desktop.runner), desktop.runner)


def test_one_changed_panel_value_keeps_the_colors_of_the_same_theme(desktop):
    theme = rounded()
    engine.apply(theme, desktop.runner)
    scheme = paths.color_schemes_dir() / f"{theme.slug}.colors"
    before = scheme.read_text()

    engine.apply(rounded(panel_layout__location="left"), desktop.runner)

    assert scheme.read_text() == before
    assert desktop.runner.settings["ColorScheme"] == "Rounded"
    assert desktop.shell.state()["location"] == "left"
