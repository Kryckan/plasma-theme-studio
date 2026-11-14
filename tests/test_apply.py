# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import configparser

import pytest

from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.generators import MARKER, ApplyError
from plasma_theme_studio.generators.colorscheme import COLOR_GROUPS, FALLBACK_SCHEME, ColorSchemeGenerator
from plasma_theme_studio.model.theme import PRESETS, Theme


def scheme_path(home, slug="MyTheme"):
    return home / ".local/share/color-schemes" / f"{slug}.colors"


@pytest.mark.parametrize("preset", PRESETS)
def test_generated_scheme_is_complete(home, preset):
    theme = Theme.from_preset(preset)
    generator = ColorSchemeGenerator()
    (file,) = generator.files(theme)
    assert generator.check_output(file) == []
    assert file.content.startswith(MARKER)
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_string(file.content)
    for group in COLOR_GROUPS:
        assert len(parser[group]) == 12
    assert parser["General"]["ColorScheme"] == theme.slug
    assert parser["Colors:Window"]["BackgroundNormal"] == theme.color("window").kde
    assert parser["Colors:Selection"]["BackgroundNormal"] == theme.color("accent").kde


def test_check_output_catches_broken_content(home):
    generator = ColorSchemeGenerator()
    (file,) = generator.files(Theme())
    broken = type(file)(file.path, file.content.replace("61,174,233", "61,174,999"))
    assert generator.check_output(broken)
    assert generator.check_output(type(file)(file.path, "[General]\nName=x\n"))


def test_apply_writes_activates_and_undo_puts_everything_back(home, runner):
    result = engine.apply(Theme(), runner)

    assert scheme_path(home).exists()
    assert runner.settings["ColorScheme"] == "MyTheme"
    assert snapshots.latest().id == result.snapshot.id

    assert engine.restore(result.snapshot, runner, consume=True) == []
    assert not scheme_path(home).exists()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert snapshots.list_snapshots() == []


def test_applying_again_reloads_the_active_scheme(home, runner):
    theme = Theme()
    engine.apply(theme, runner)
    first = scheme_path(home).read_text()
    theme.set("colors", "accent", "#ff0000")

    second = engine.apply(theme, runner)

    assert runner.applied == ["MyTheme", "MyTheme"]
    assert runner.settings["ColorScheme"] == "MyTheme"
    assert "255,0,0" in scheme_path(home).read_text()

    engine.restore(second.snapshot, runner, consume=True)
    assert scheme_path(home).read_text() == first
    assert runner.applied == ["MyTheme", "MyTheme", "MyTheme"]


def test_failed_reload_rolls_back(home, runner):
    runner.schemes_dir = home / "nowhere"  # Plasma will not find the new scheme

    with pytest.raises(ApplyError):
        engine.apply(Theme(), runner)

    assert not scheme_path(home).exists()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert snapshots.list_snapshots() == []


def test_foreign_file_blocks_until_confirmed(home, runner):
    scheme_path(home).parent.mkdir(parents=True)
    scheme_path(home).write_text("[General]\nName=Hand made\n")

    with pytest.raises(engine.ApplyBlocked):
        engine.apply(Theme(), runner)
    assert scheme_path(home).read_text() == "[General]\nName=Hand made\n"

    result = engine.apply(Theme(), runner, replace_foreign=True)
    engine.restore(result.snapshot, runner)
    assert scheme_path(home).read_text() == "[General]\nName=Hand made\n"


def test_blocked_when_tools_are_missing_or_name_is_taken(home, runner):
    runner.missing.add("plasma-apply-colorscheme")
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(Theme(), runner)
    runner.missing.clear()

    system = home / "system/share/color-schemes"
    system.mkdir(parents=True)
    (system / "MyTheme.colors").write_text("")
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(Theme(), runner)
    assert runner.applied == []
    assert snapshots.list_snapshots() == []


def test_paths_outside_home_are_refused(home, runner, monkeypatch, tmp_path_factory):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path_factory.mktemp("elsewhere")))
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(Theme(), runner)


def test_custom_accent_gives_a_warning(home, runner):
    assert engine.build_plan(Theme(), runner).warnings == []
    runner.settings["AccentColor"] = "255,0,0"
    assert len(engine.build_plan(Theme(), runner).warnings) == 1


def test_plan_reports_file_states(home, runner):
    theme = Theme()
    state = lambda: engine.build_plan(theme).targets[0].files[0].state
    assert state() == engine.NEW
    engine.apply(theme, runner)
    assert state() == engine.UNCHANGED
    theme.set("colors", "accent", "#000000")
    assert state() == engine.CHANGED


def test_only_the_latest_snapshots_are_kept(home, runner, monkeypatch):
    monkeypatch.setattr(snapshots, "KEEP", 3)
    monkeypatch.setattr(snapshots.prune, "__defaults__", (3,))
    theme = Theme()
    for index in range(5):
        theme.set("shape", "radius", index)
        theme.set("colors", "accent", f"#0000{index}0")
        engine.apply(theme, runner)
    assert len(snapshots.list_snapshots()) == 3


def test_switching_to_an_installed_scheme_and_back(home, runner):
    snapshot = engine.switch_color_scheme("BreezeDark", "Breeze Dark", runner)
    assert runner.settings["ColorScheme"] == "BreezeDark"
    engine.restore(snapshot, runner, consume=True)
    assert runner.settings["ColorScheme"] == "BreezeLight"

    with pytest.raises(ApplyError):
        engine.switch_color_scheme("Missing", "Missing", runner)
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert snapshots.list_snapshots() == []


def test_restore_to_undoes_every_apply_made_after_the_snapshot(home, runner):
    theme = Theme()
    first = engine.apply(theme, runner).snapshot
    theme.set("colors", "accent", "#ff0000")
    engine.apply(theme, runner)
    engine.switch_color_scheme("BreezeDark", "Breeze Dark", runner)

    reached, failures = engine.restore_to(first, runner)

    assert (reached.id, failures) == (first.id, [])
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert not scheme_path(home).exists()
    assert snapshots.list_snapshots() == []


def test_restore_to_leaves_the_older_snapshots_for_later(home, runner):
    theme = Theme()
    first = engine.apply(theme, runner).snapshot
    original = scheme_path(home).read_text()
    theme.set("colors", "accent", "#ff0000")
    second = engine.apply(theme, runner).snapshot
    engine.switch_color_scheme("BreezeDark", "Breeze Dark", runner)

    reached, failures = engine.restore_to(second, runner)

    assert (reached.id, failures) == (second.id, [])
    assert runner.settings["ColorScheme"] == "MyTheme"
    assert scheme_path(home).read_text() == original
    assert [item.id for item in snapshots.list_snapshots()] == [first.id]


def test_restore_to_stops_at_the_apply_that_cannot_be_undone(home, runner):
    first = engine.apply(Theme(), runner).snapshot
    engine.switch_color_scheme("BreezeDark", "Breeze Dark", runner)
    last = engine.switch_color_scheme("BreezeLight", "Breeze Light", runner)
    runner.known.discard("BreezeDark")  # Plasma cannot go back to it

    reached, failures = engine.restore_to(first, runner)

    assert reached.id == last.id and failures
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert scheme_path(home).exists()
    assert len(snapshots.list_snapshots()) == 3  # kept for one more try, the older ones untouched

    runner.known.add("BreezeDark")
    reached, failures = engine.restore_to(first, runner)

    assert (reached.id, failures) == (first.id, [])
    assert not scheme_path(home).exists()
    assert snapshots.list_snapshots() == []


def test_restore_to_a_snapshot_that_is_gone_changes_nothing(home, runner):
    first = engine.apply(Theme(), runner).snapshot
    engine.switch_color_scheme("BreezeDark", "Breeze Dark", runner)
    snapshots.delete(first)

    reached, failures = engine.restore_to(first, runner)

    assert reached is None
    assert [str(failure) for failure in failures] == [f"There is no snapshot called {first.id}."]
    assert runner.settings["ColorScheme"] == "BreezeDark"
    assert len(snapshots.list_snapshots()) == 1


def test_restore_to_stops_before_a_snapshot_that_cannot_be_read(home, runner):
    first = engine.apply(Theme(), runner).snapshot
    broken = engine.switch_color_scheme("BreezeDark", "Breeze Dark", runner)
    engine.switch_color_scheme("BreezeLight", "Breeze Light", runner)
    (broken.directory / "manifest.json").write_text("{bad")

    reached, failures = engine.restore_to(first, runner)

    assert reached is None
    assert broken.id in str(failures[0]) and "cannot be read" in str(failures[0])
    assert runner.settings["ColorScheme"] == "BreezeDark"  # the newest apply was undone, nothing older
    assert scheme_path(home).exists()
    assert [item.id for item in snapshots.list_snapshots()] == [first.id]

    # Undo goes on without the one that cannot be read.
    reached, failures = engine.restore_to(snapshots.latest(), runner)

    assert (reached.id, failures) == (first.id, [])
    assert not scheme_path(home).exists()


def test_a_snapshot_folder_that_cannot_be_written_to_is_reported_like_any_failure(home, runner, monkeypatch):
    snapshot = engine.switch_color_scheme("BreezeDark", "Breeze Dark", runner)
    runner.known.discard("BreezeLight")  # Plasma cannot go back to it

    def refuse(snapshot):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(snapshots, "mark_tried", refuse)

    reached, failures = engine.restore_to(snapshot, runner)

    assert reached.id == snapshot.id
    assert len(failures) == 2 and "Permission denied" in str(failures[1])


def test_is_current_only_when_written_and_active(home, runner):
    theme = Theme()
    assert not engine.is_current(engine.build_plan(theme), runner)
    engine.apply(theme, runner)
    assert engine.is_current(engine.build_plan(theme), runner)
    runner.settings["ColorScheme"] = "BreezeDark"
    assert not engine.is_current(engine.build_plan(theme), runner)


def test_undo_without_a_recorded_scheme_goes_to_plasmas_own(home, runner):
    """A desktop that had no color scheme set uses Breeze Light, so that is what undo picks."""
    runner.settings["ColorScheme"] = ""
    result = engine.apply(Theme(), runner)
    assert result.snapshot.settings["colors"]["color_scheme"] in ("", None)
    assert runner.settings["ColorScheme"] == "MyTheme"

    assert engine.restore(result.snapshot, runner, consume=True) == []

    assert runner.settings["ColorScheme"] == FALLBACK_SCHEME == "BreezeLight"
    assert not scheme_path(home).exists()


def test_a_command_whose_output_is_not_text_does_not_stop_the_apply(home):
    from plasma_theme_studio.apply.runner import SystemRunner

    result = SystemRunner().run(["/usr/bin/printf", "caf\\351 \\377\\n"])
    assert result.returncode == 0
    assert result.stdout.startswith("caf") and result.stdout.endswith("\n")
