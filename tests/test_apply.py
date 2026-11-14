# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import configparser

import pytest

from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.generators import MARKER, ApplyError
from plasma_theme_studio.generators.colorscheme import COLOR_GROUPS, ColorSchemeGenerator
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


def test_is_current_only_when_written_and_active(home, runner):
    theme = Theme()
    assert not engine.is_current(engine.build_plan(theme), runner)
    engine.apply(theme, runner)
    assert engine.is_current(engine.build_plan(theme), runner)
    runner.settings["ColorScheme"] = "BreezeDark"
    assert not engine.is_current(engine.build_plan(theme), runner)
