# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The targets for the parts that a theme names from what is installed."""

import pytest

from plasma_theme_studio import paths
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.model.theme import Theme

PLASTIK = "org.kde.kwin.aurorae:kwin4_decoration_qml_plastik"


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    from plasma_theme_studio import desktopparts as dp
    from plasma_theme_studio.generators import windowframe as wf

    monkeypatch.setattr(wf, "_pause", lambda seconds: None)
    keys = ["Breeze", "Union", "Oxygen", "kvantum-dark", "kvantum", "Windows", "Fusion"]
    monkeypatch.setattr(dp.AppStyle, "_qt_keys", staticmethod(lambda: keys))


def everything() -> Theme:
    """A theme that names every installed part."""
    return Theme(
        {
            ("apps", "style"): "installed",
            ("apps", "style_id"): "Fusion",
            ("panel", "style"): "installed",
            ("panel", "style_id"): "breeze-dark",
            ("window", "decoration"): "installed",
            ("window", "decoration_id"): PLASTIK,
            ("window", "border_size"): "Large",
            ("window", "buttons_left"): "MN",
            ("window", "buttons_right"): "IAX",
            ("desktop", "icons"): "Papirus",
            ("desktop", "cursors"): "Pop",
            ("desktop", "cursor_size"): 32,
            ("desktop", "splash"): "None",
            ("desktop", "sounds"): "oxygen",
            ("fonts", "general"): "Noto Sans, 11",
            ("fonts", "fixed"): "Hack, 10",
            ("fonts", "small"): "Noto Sans, 8",
            ("fonts", "toolbar"): "Noto Sans, 10",
            ("fonts", "menu"): "Noto Sans, 10",
            ("fonts", "window_title"): "Noto Sans, 10, 700",
        }
    )


def tree(root):
    """Every file under `root`. KConfig keeps the keys of a group in order of their names, the stand-in
    in order of writing, so the lines of a group are compared sorted."""
    found = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            blocks = path.read_text().split("\n\n")
            found[str(path.relative_to(root))] = sorted(tuple(sorted(block.splitlines())) for block in blocks)
    return found


def start_from_something(runner):
    """A desktop that has settings of its own for every part."""
    runner.set("plasmarc", ["Theme"], "name", "My Theme")
    runner.set("kdeglobals", ["KDE"], "widgetStyle", "Breeze")
    runner.set("kdeglobals", ["Icons"], "Theme", "breeze")
    runner.set("kcminputrc", ["Mouse"], "cursorTheme", "Qogir Dark")
    runner.set("kcminputrc", ["Mouse"], "cursorSize", "24")
    runner.set("kdeglobals", ["General"], "font", "Noto Sans,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1")
    runner.set("kdeglobals", ["Sounds"], "Theme", "ocean")
    runner.set("ksplashrc", ["KSplash"], "Theme", "org.kde.breeze.desktop")
    runner.set("kwinrc", ["org.kde.kdecoration2"], "ButtonsOnLeft", "M")
    runner.set("kdeglobals", ["General"], "AccentColor", "255,0,0")
    runner.set("kdeglobals", ["General"], "ColorScheme", "BreezeLight")
    runner.set("kdeglobals", ["Colors:Button"], "DecorationFocus", "255,0,0")  # the accent in the colors


def test_a_theme_naming_every_installed_part_is_applied_and_undone_exactly(desktop_runner, home):
    runner = desktop_runner
    start_from_something(runner)
    before = tree(paths.config_home()), tree(paths.data_home())
    theme = everything()
    plan = engine.build_plan(theme, runner)
    assert plan.blocking == []
    ids = [target.generator.id for target in plan.wanted_targets]
    for wanted in ("app_style", "decoration", "border_size", "buttons", "plasma_style", "icons", "cursors"):
        assert wanted in ids
    for wanted in ("cursor_size", "fonts", "splash", "sounds", "accent"):
        assert wanted in ids
    assert "apps" not in ids and "panel" not in ids and "window" not in ids  # the generated ones are not
    result = engine.apply(theme, runner)
    assert runner.get("plasmarc", ["Theme"], "name") == "breeze-dark"
    assert runner.get("kdeglobals", ["KDE"], "widgetStyle") == "Fusion"
    assert runner.get("kwinrc", ["org.kde.kdecoration2"], "theme") == "kwin4_decoration_qml_plastik"
    assert runner.get("kwinrc", ["org.kde.kdecoration2"], "BorderSize") == "Large"
    assert runner.get("kwinrc", ["org.kde.kdecoration2"], "ButtonsOnLeft") == "MN"
    assert runner.get("kdeglobals", ["Icons"], "Theme") == "Papirus"
    assert runner.get("kcminputrc", ["Mouse"], "cursorTheme") == "Pop"
    assert runner.get("kcminputrc", ["Mouse"], "cursorSize") == "32"
    assert runner.get("ksplashrc", ["KSplash"], "Engine") == "none"
    assert runner.get("kdeglobals", ["Sounds"], "Theme") == "oxygen"
    assert runner.get("kdeglobals", ["General"], "AccentColor") == ""
    assert engine.is_current(engine.build_plan(theme, runner), runner)
    failures = engine.restore(result.snapshot, runner, consume=True)
    assert failures == []
    after = tree(paths.config_home()), tree(paths.data_home())
    for was, now in zip(before, after, strict=True):
        for name in was.keys() | now.keys():
            assert now.get(name) == was.get(name), name
    assert not engine.is_current(engine.build_plan(theme, runner), runner)
    assert snapshots.list_snapshots() == []


def wanted_ids(theme, runner):
    return [t.generator.id for t in engine.build_plan(theme, runner).wanted_targets]


def test_a_theme_naming_something_not_installed_gives_a_problem_and_changes_nothing(desktop_runner, home):
    runner = desktop_runner
    start_from_something(runner)
    before = tree(paths.config_home()), tree(paths.data_home())
    theme = Theme(
        {
            ("apps", "style"): "installed",
            ("apps", "style_id"): "NoSuchStyle",
            ("desktop", "icons"): "Papirus",
            ("desktop", "cursors"): "NoSuchPointers",
            ("window", "decoration"): "installed",
            ("window", "decoration_id"): "org.kde.kwin.aurorae:nothing_here",
        }
    )
    blocking = [str(problem) for problem in engine.build_plan(theme, runner).blocking]
    assert len(blocking) == 3
    assert any("NoSuchStyle" in text for text in blocking)
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(theme, runner)
    assert (tree(paths.config_home()), tree(paths.data_home())) == before
    assert runner.get("kdeglobals", ["Icons"], "Theme") == "breeze"  # the icons were fine, and left alone
    assert snapshots.list_snapshots() == []


def test_installed_without_a_name_is_left_alone_and_said(desktop_runner):
    theme = Theme({("apps", "style"): "installed", ("panel", "style"): "installed"})
    plan = engine.build_plan(theme, desktop_runner)
    assert plan.blocking == []
    ids = [t.generator.id for t in plan.wanted_targets]
    assert "app_style" not in ids and "plasma_style" not in ids and "apps" not in ids
    notes = [str(note) for t in plan.targets for note in t.notes]
    assert sum("none is chosen" in note for note in notes) == 2


def test_the_generated_and_the_installed_variants_are_never_both_wanted(desktop_runner):
    for mode in ("unchanged", "generated", "installed"):
        theme = Theme(
            {
                ("apps", "style"): mode,
                ("apps", "style_id"): "Fusion",
                ("panel", "style"): mode,
                ("panel", "style_id"): "breeze-dark",
                ("window", "decoration"): "installed" if mode == "installed" else mode,
                ("window", "decoration_id"): PLASTIK,
            }
        )
        ids = wanted_ids(theme, desktop_runner)
        for generated, installed in (
            ("apps", "app_style"),
            ("panel", "plasma_style"),
            ("window", "decoration"),
        ):
            assert not (generated in ids and installed in ids), (mode, generated)
            assert (installed in ids) == (mode == "installed"), (mode, installed)
        assert ("window" in ids) == (mode == "generated")


def test_an_installed_choice_removes_what_was_generated_before(desktop_runner, home):
    runner = desktop_runner
    generated = Theme({("window", "decoration"): "generated", ("panel", "style"): "generated"})
    engine.apply(generated, runner)
    frames = paths.data_home() / "aurorae/themes"
    assert any(frames.iterdir())
    installed = Theme(
        {
            ("window", "decoration"): "installed",
            ("window", "decoration_id"): PLASTIK,
            ("panel", "style"): "installed",
            ("panel", "style_id"): "breeze-dark",
        }
    )
    result = engine.apply(installed, runner)
    assert not frames.exists() or not any(frames.iterdir())
    assert runner.get("plasmarc", ["Theme"], "name") == "breeze-dark"
    assert not any((paths.data_home() / "plasma/desktoptheme").glob("*"))
    engine.restore(result.snapshot, runner, consume=True)
    assert any(frames.iterdir())  # the generated frame is back, with its files


def test_a_frame_made_here_follows_the_colors_unless_a_decoration_is_named(desktop_runner):
    runner = desktop_runner
    engine.apply(Theme({("window", "decoration"): "generated"}), runner)
    assert "window" in wanted_ids(Theme(), runner)  # unchanged: the frame in use gets the colors
    named = Theme({("window", "decoration"): "installed", ("window", "decoration_id"): PLASTIK})
    assert "window" not in wanted_ids(named, runner)
    unnamed = Theme({("window", "decoration"): "installed"})
    assert "window" in wanted_ids(unnamed, runner)  # installed without a name is unchanged


def test_a_missing_tool_is_a_problem_of_that_target_only(desktop_runner):
    desktop_runner.missing = {"plasma-apply-cursortheme"}
    theme = Theme({("desktop", "icons"): "Papirus", ("desktop", "cursors"): "Pop"})
    plan = engine.build_plan(theme, desktop_runner)
    problems = {t.generator.id: t.problems for t in plan.wanted_targets}
    assert problems["icons"] == [] and len(problems["cursors"]) == 1
    assert "plasma-apply-cursortheme" in str(problems["cursors"][0])


def test_the_accent_is_cleared_only_when_it_was_set(desktop_runner):
    assert "accent" not in wanted_ids(Theme(), desktop_runner)
    desktop_runner.set("kdeglobals", ["General"], "AccentColor", "1,2,3")
    assert "accent" in wanted_ids(Theme(), desktop_runner)
    follow = Theme({("colors", "accent_from_wallpaper"): True})
    engine.apply(follow, desktop_runner)
    assert desktop_runner.get("kdeglobals", ["General"], "accentColorFromWallpaper") == "true"
    assert engine.is_current(engine.build_plan(follow, desktop_runner), desktop_runner)
