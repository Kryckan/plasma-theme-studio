# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Light and dark variants: the model and its file, the conversion, the apply with Plasma's own
switch at night (and its undo), the command line and the editor."""

import json

import pytest

pytest.importorskip("PySide6.QtWidgets")

from plasma_theme_studio import cli, kconfig, paths  # noqa: E402
from plasma_theme_studio.apply import engine, sidefiles  # noqa: E402
from plasma_theme_studio.apply import snapshot as snapshots  # noqa: E402
from plasma_theme_studio.generators import GENERATORS  # noqa: E402
from plasma_theme_studio.generators.variants import NightVariantsTarget, package_id  # noqa: E402
from plasma_theme_studio.model.color import Color, contrast  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID, VARIANT_KEYS, Theme, ThemeError  # noqa: E402
from plasma_theme_studio.model.variants import convert  # noqa: E402
from plasma_theme_studio.palette import to_oklch  # noqa: E402

LIGHT_COLORS = ("window", "view", "button", "header")


def both(**values) -> Theme:
    theme = Theme(
        {("desktop", "dark_at_night"): True, **{tuple(k.split("__")): v for k, v in values.items()}}
    )
    theme.add_variant()
    return theme


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(sidefiles.desktop, "pause", lambda seconds: None)


def state():
    found = {}
    for root in (paths.config_home(), paths.data_home()):
        for path in sorted(root.rglob("*")):
            if "plasma-theme-studio" in path.parts:
                continue
            found[str(path)] = path.read_bytes() if path.is_file() else None
    return found


# ---- the model -------------------------------------------------------------------------------


def test_a_theme_has_one_variant_until_the_other_is_added():
    theme = Theme()
    assert not theme.has_both and theme.variants == ("light",) and theme.main_variant == "light"
    assert "[variant]" not in theme.to_toml() and "[colors_other]" not in theme.to_toml()
    assert theme.for_variant("dark") is None
    assert theme.add_variant() == "dark"
    assert theme.has_both and theme.variants == ("light", "dark") and theme.add_variant() == ""


def test_a_dark_theme_gets_a_light_variant():
    theme = Theme.from_preset("breeze-dark")
    assert theme.main_variant == "dark"
    assert theme.add_variant() == "light"
    theme.show("light")
    assert theme.color("window").luminance > 0.5
    assert contrast(theme.color("text"), theme.color("window")) >= 4.5


def test_the_conversion_keeps_the_hues_and_the_text_readable():
    theme = Theme({("colors", "accent"): "#e93a9a"})
    light = {key: theme.get("colors", key) for key in VARIANT_KEYS if key != "scheme_id"}
    dark = convert(light, "dark")
    for key in LIGHT_COLORS:
        assert to_oklch(Color.parse(dark[key]))[0] < 0.4
    # the same hue, lightness turned around
    for key in ("accent", "link", "negative", "positive"):
        before, after = (
            to_oklch(Color.parse(light[key])),
            to_oklch(Color.parse(dark[key])),
        )
        assert abs(((before[2] - after[2] + 180) % 360) - 180) < 12
    for surface in LIGHT_COLORS:
        for text in ("text", "text_muted"):
            floor = 4.5 if text == "text" else 3.0
            assert contrast(Color.parse(dark[text]), Color.parse(dark[surface])) >= floor


def test_converting_there_and_back_gives_the_colors_again_within_rounding():
    theme = Theme()
    light = {key: theme.get("colors", key) for key in LIGHT_COLORS}
    back = convert(convert(light, "dark"), "light")
    for key in LIGHT_COLORS:
        a, b = theme.color(key), Color.parse(back[key])
        assert abs(a.luminance - b.luminance) < 0.03


def test_the_editor_reads_and_writes_the_variant_that_is_shown():
    theme = both()
    main = {key: theme.get("colors", key) for key in VARIANT_KEYS}
    theme.show("dark")
    assert theme.get("colors", "window") != main["window"] and theme.shown_variant == "dark"
    theme.set("colors", "accent", "#ff0000")
    assert theme.get("colors", "accent") == "#ff0000" and theme.color("accent").hex == "#ff0000"
    theme.show("light")
    assert {key: theme.get("colors", key) for key in VARIANT_KEYS} == main
    # shapes and everything else are shared
    theme.show("dark")
    theme.set("shape", "radius", 9)
    theme.show("light")
    assert theme.get("shape", "radius") == 9 and theme.resolved("apps", "radius") == 9


def test_the_file_is_additive_and_stays_schema_version_1():
    theme = both()
    text = theme.to_toml()
    assert text.startswith("schema_version = 1\n")
    assert '[variant]\nmain = "light"' in text and "[colors_other]" in text
    assert Theme.from_toml(text) == theme and Theme.from_toml(text).main_variant == "light"
    # the view is not saved
    theme.show("dark")
    assert theme.to_toml() == text


def test_a_file_without_variants_loads_and_saves_as_before(tmp_path):
    old = 'schema_version = 1\n[meta]\nname = "Old"\n[colors]\naccent = "#112233"\n'
    theme = Theme.from_toml(old)
    assert not theme.has_both and theme.get("colors", "accent") == "#112233"
    assert "[variant]" not in theme.to_toml()


def test_a_second_variant_missing_colors_are_made_for_it():
    text = Theme().to_toml() + '\n[variant]\nmain = "light"\n\n[colors_other]\nwindow = "#101010"\n'
    theme = Theme.from_toml(text)
    theme.show("dark")
    assert theme.get("colors", "window") == "#101010"
    assert theme.color("text").luminance > 0.5  # made by the conversion, readable on the dark window


def test_a_wrong_variant_table_is_reported():
    base = Theme().to_toml()
    for extra in (
        '\n[variant]\nmain = "grey"\n\n[colors_other]\nwindow = "#101010"\n',
        '\n[variant]\nmain = "light"\ncolor = 1\n\n[colors_other]\nwindow = "#101010"\n',
        '\n[colors_other]\nwindow = "nope"\n',
        '\n[colors_other]\nshadow = "#101010"\n',
    ):
        with pytest.raises(ThemeError):
            Theme.from_toml(base + extra)


def test_removing_a_variant_leaves_the_other_one():
    theme = both()
    dark = theme.colors_of("dark")
    theme.remove_variant("light")  # the main one goes: the dark one is all the theme has
    assert (
        not theme.has_both
        and theme.main_variant == "dark"
        and theme.get("colors", "window") == dark["window"]
    )
    theme = both()
    theme.remove_variant("dark")
    assert not theme.has_both and theme.main_variant == "light"


def test_copies_are_independent_and_the_view_is_not_part_of_equality():
    theme = both()
    other = theme.copy()
    other.show("dark")
    assert other == theme
    other.set("colors", "accent", "#00ff00")
    assert other != theme and theme.get("colors", "accent") != "#00ff00"
    single = theme.for_variant("dark")
    assert not single.has_both and single.get("colors", "window") == theme.colors_of("dark")["window"]


def test_the_variants_have_names_of_their_own_for_the_color_scheme():
    theme = both()
    assert theme.scheme_slug == "MyTheme"
    theme.show("dark")
    assert theme.scheme_slug == "MyThemeDark"
    assert theme.scheme_title == "My Theme Dark"


# ---- the apply -------------------------------------------------------------------------------


def files_of(theme):
    return {
        file.path.relative_to(paths.data_home()).as_posix(): file.content
        for g in GENERATORS
        for file in g.files(theme)
    }


def test_the_night_target_is_wanted_only_for_two_variants_and_the_switch():
    target = NightVariantsTarget()
    assert target.wanted(both())
    assert not target.wanted(Theme({("desktop", "dark_at_night"): True}))
    single = Theme()
    single.add_variant()
    assert not target.wanted(single)  # the switch is not on
    assert target.files(single) == []


def test_both_variants_are_installed_as_global_themes_for_the_switch(desktop_runner):
    theme = both()
    engine.apply(theme, desktop_runner)
    light, dark = package_id(theme, "light"), package_id(theme, "dark")
    root = paths.data_home() / "plasma/look-and-feel"
    for variant, pid in (("light", light), ("dark", dark)):
        meta = json.loads((root / pid / "metadata.json").read_text())
        assert meta["KPackageStructure"] == "Plasma/LookAndFeel" and meta["KPlugin"]["Id"] == pid
        defaults = (root / pid / "contents/defaults").read_text()
        scheme = theme.copy()
        scheme.show(variant)
        assert f"[kdeglobals][General]\nColorScheme={scheme.scheme_slug}\n" in defaults
        assert "ksplashrc" not in defaults  # the switch changes the colors, not the splash screen
        assert (paths.color_schemes_dir() / f"{scheme.scheme_slug}.colors").exists()
    keys = {
        name: kconfig.user_value("kdeglobals", ["KDE"], name)
        for name in (
            "AutomaticLookAndFeel",
            "DefaultLightLookAndFeel",
            "DefaultDarkLookAndFeel",
            "LookAndFeelPackage",
        )
    }
    assert keys == {
        "AutomaticLookAndFeel": "true",
        "DefaultLightLookAndFeel": light,
        "DefaultDarkLookAndFeel": dark,
        "LookAndFeelPackage": light,
    }
    assert desktop_runner.get("kdeglobals", ["General"], "ColorScheme") == theme.scheme_slug


def test_the_package_of_the_variant_in_use_is_the_one_the_desktop_names(desktop_runner):
    theme = both()
    theme.show("dark")
    engine.apply(theme, desktop_runner)
    assert kconfig.user_value("kdeglobals", ["KDE"], "LookAndFeelPackage") == package_id(theme, "dark")
    plan = engine.build_plan(theme, desktop_runner)
    assert engine.is_current(plan, desktop_runner)


def test_undo_puts_everything_back_exactly(desktop_runner):
    desktop_runner.set("kdeglobals", ["KDE"], "LookAndFeelPackage", "org.kde.breeze.desktop")
    before = state()
    theme = both()
    result = engine.apply(theme, desktop_runner)
    assert state() != before
    assert engine.restore(result.snapshot, desktop_runner, consume=True) == []
    assert state() == before
    assert snapshots.list_snapshots() == []


def test_the_other_variant_is_a_change_of_the_colors_only(desktop_runner):
    theme = Theme()
    theme.add_variant()  # the switch is off: nothing but the colors differs
    engine.apply(theme, desktop_runner)
    theme.show("dark")
    changed = {part.key for part in engine.parts_status(theme, desktop_runner) if part.state == "change"}
    assert changed == {"colors"}
    first = {part.key: part for part in engine.parts_status(theme, desktop_runner)}["colors"]
    assert "light variant" in first.desktop and "dark variant" in first.theme
    result = engine.apply(theme, desktop_runner)
    assert desktop_runner.get("kdeglobals", ["General"], "ColorScheme") == theme.scheme_slug
    assert engine.restore(result.snapshot, desktop_runner, consume=True) == []
    assert desktop_runner.get("kdeglobals", ["General"], "ColorScheme") == Theme().scheme_slug


def test_without_the_switch_no_global_themes_are_installed(desktop_runner):
    theme = Theme()
    theme.add_variant()
    engine.apply(theme, desktop_runner)
    assert not (paths.data_home() / "plasma/look-and-feel").exists()
    assert kconfig.user_value("kdeglobals", ["KDE"], "DefaultDarkLookAndFeel") is None


def test_the_packages_of_another_theme_are_removed_and_come_back_with_undo(desktop_runner):
    first = both()
    engine.apply(first, desktop_runner)
    second = both(meta__name="Second")
    before = state()
    result = engine.apply(second, desktop_runner)
    root = paths.data_home() / "plasma/look-and-feel"
    assert {p.name for p in root.iterdir()} == {package_id(second, "light"), package_id(second, "dark")}
    assert engine.restore(result.snapshot, desktop_runner, consume=True) == []
    assert state() == before


def test_the_page_says_what_follows_the_switch_and_what_waits_for_the_next_apply():
    theme = both(window__decoration="generated", apps__style="generated")
    notes = " ".join(str(note) for note in NightVariantsTarget().notes(theme))
    assert "The colors and the panel and popup style follow" in notes
    assert "the window frame" in notes and "the application style" in notes and "keep" in notes
    assert "the GTK files" not in notes
    assert NightVariantsTarget().notes(Theme()) == []


# ---- the command line ------------------------------------------------------------------------


def test_the_command_line_applies_a_variant_and_says_which_one_is_on_the_desktop(
    home, desktop_runner, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "SystemRunner", lambda: desktop_runner)
    monkeypatch.setattr(cli, "_load_translation", lambda: None)
    theme = Theme()
    theme.add_variant()
    path = home / "theme.toml"
    theme.save(path)
    assert cli.main(["apply", str(path), "--variant", "dark"]) == 0
    assert desktop_runner.get("kdeglobals", ["General"], "ColorScheme") == "MyThemeDark"
    capsys.readouterr()
    assert cli.main(["status", str(path), "--variant", "dark"]) == 0
    assert "Variant on the desktop: dark" in capsys.readouterr().out
    assert cli.main(["apply", str(path), "--variant", "light"]) == 0
    capsys.readouterr()
    assert cli.main(["status", str(path)]) == 0
    assert "Variant on the desktop: light" in capsys.readouterr().out


def test_a_variant_the_theme_does_not_have_is_reported(home, desktop_runner, monkeypatch, capsys):
    monkeypatch.setattr(cli, "SystemRunner", lambda: desktop_runner)
    monkeypatch.setattr(cli, "_load_translation", lambda: None)
    path = home / "theme.toml"
    Theme().save(path)
    before = state()
    assert cli.main(["apply", str(path), "--variant", "dark"]) == 1
    assert "no dark variant" in capsys.readouterr().err
    assert state() == before


# ---- the editor ------------------------------------------------------------------------------


@pytest.fixture
def window(app, home, runner, monkeypatch):
    from plasma_theme_studio.ui.main_window import MainWindow

    window = MainWindow(runner)
    window.build_pages()
    monkeypatch.setattr(window, "_show_problems", lambda title, problems: None)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def accent(window):
    return window.theme.get("colors", "accent")


def test_adding_a_variant_is_one_undo_step_and_the_switch_follows(window):
    window.show_page("colors")
    page = window.page("colors")
    assert page.variants.add_button.isVisibleTo(page) and not window.variant_switch.isVisibleTo(window)
    page.variants.add_button.click()
    assert window.theme.has_both and window.theme.shown_variant == "dark"
    assert window.variant_switch.isVisibleTo(window) and window.variant_switch.current() == 1
    assert page.variants.switch.current() == 1 and page.variants.remove_button.isVisibleTo(page)
    window.undo_stack.undo()
    assert not window.theme.has_both and page.variants.add_button.isVisibleTo(page)
    window.undo_stack.redo()
    assert window.theme.has_both and window.theme.shown_variant == "dark"


def test_the_switch_changes_what_every_page_shows_and_is_not_an_undo_step(window):
    window.add_variant()
    steps = window.undo_stack.count()
    dark_window = window.theme.get("colors", "window")
    window.variant_switch.chosen.emit("light")
    assert window.theme.shown_variant == "light" and window.theme.get("colors", "window") != dark_window
    assert window.page("colors").variants.switch.current() == 0
    assert window.undo_stack.count() == steps
    window.show_page("colors")
    assert window.editors[("colors", "window")].text.text() == window.theme.get("colors", "window")
    window.variant_switch.chosen.emit("dark")
    assert window.theme.get("colors", "window") == dark_window


def test_an_edit_belongs_to_the_variant_it_was_made_in_and_undo_goes_back_to_it(window):
    window.add_variant()  # dark shown
    window.edit(FIELD_BY_ID[("colors", "accent")], "#ff0000")
    window.show_variant("light")
    light_accent = accent(window)
    assert light_accent != "#ff0000"
    window.undo_stack.undo()  # the edit was made in the dark variant
    assert window.theme.shown_variant == "dark" and accent(window) != "#ff0000"
    assert window.theme.colors_of("light")["accent"] == light_accent
    window.undo_stack.redo()
    assert accent(window) == "#ff0000" and window.theme.shown_variant == "dark"


def test_removing_a_variant_is_undoable(window):
    window.add_variant()
    window.remove_variant("dark")
    assert not window.theme.has_both and not window.variant_switch.isVisibleTo(window)
    window.undo_stack.undo()
    assert window.theme.has_both


def test_apply_puts_the_shown_variant_on_the_desktop(window, runner):
    window.add_variant()
    window.show_variant("dark")
    window.apply_theme()
    assert runner.settings["ColorScheme"] == window.theme.scheme_slug
    assert window.theme.scheme_slug != Theme().slug
    window.show_variant("light")
    window.settle()
    assert {s.key: s.state for s in window.statuses}["colors"] == "change"


def test_a_card_of_a_theme_with_both_variants_shows_both(app):
    from plasma_theme_studio.ui.library_view import thumbnail

    theme = both()
    image = thumbnail(theme, 1.0).toImage()
    width, height = image.width(), image.height()
    top_left, bottom_right = image.pixelColor(12, 22), image.pixelColor(width - 14, height - 12)
    assert top_left.lightnessF() > bottom_right.lightnessF() + 0.2
    single = thumbnail(Theme(), 1.0).toImage()
    assert (
        single.pixelColor(12, 22).lightnessF() > 0.5
        and single.pixelColor(width - 14, height - 12).lightnessF() > 0.5
    )
