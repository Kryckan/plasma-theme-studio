# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

import pytest

from plasma_theme_studio import library
from plasma_theme_studio.apply import engine
from plasma_theme_studio.generators.colorscheme import ColorSchemeGenerator
from plasma_theme_studio.model.theme import Theme

OLD_STYLE = """[Colors:Selection]
BackgroundNormal=136,192,208,204
[Colors:View]
BackgroundNormal=#2e3440
ForegroundLink=129,161,193
[Colors:Window]
BackgroundNormal=46,52,64
ForegroundNormal=216,222,233
[General]
Name=Nordic
Name[sv]=Nordisk
[WM]
activeBackground=59,66,82
"""


def test_reads_schemes_from_home_and_system(home):
    system = home / "system/share/color-schemes"
    system.mkdir(parents=True)
    (system / "Nordic.colors").write_text(OLD_STYLE)
    (system / "Broken.colors").write_text("not a scheme")
    (system / "Shadowed.colors").write_text(OLD_STYLE.replace("Name=Nordic", "Name=System one"))
    user = home / ".local/share/color-schemes"
    user.mkdir(parents=True)
    (user / "Shadowed.colors").write_text(OLD_STYLE.replace("Name=Nordic", "Name=Mine"))

    schemes = {scheme.id: scheme for scheme in library.installed_schemes()}

    assert set(schemes) == {"Nordic", "Shadowed"}
    assert schemes["Shadowed"].name == "Mine" and schemes["Shadowed"].in_home
    nordic = schemes["Nordic"]
    assert nordic.colors["accent"] == "#88c0d0"  # the alpha value is dropped
    assert nordic.colors["view"] == "#2e3440"
    assert nordic.colors["header"] == "#3b4252"  # falls back to the title bar color
    assert "button" not in nordic.colors


def test_copy_of_a_scheme_gets_its_colors_and_a_new_name(home):
    path = home / "Nordic.colors"
    path.write_text(OLD_STYLE)
    theme = library.theme_from_scheme(library.read_scheme(path, in_home=False))
    assert theme.name == "Nordic Copy"
    assert theme.get("colors", "window") == "#2e3440"
    assert theme.get("colors", "button") == Theme().get("colors", "button")


def test_generated_schemes_round_trip(home, runner):
    theme = Theme.from_preset("breeze-dark")
    theme.set("colors", "accent", "#e9608c")
    engine.apply(theme, runner)
    (scheme,) = library.installed_schemes()
    assert scheme.made_here
    assert library.theme_from_scheme(scheme) == theme


def test_saved_themes_skip_unreadable_files(home):
    folder = home / ".local/share/plasma-theme-studio/themes"
    Theme().save(folder / "good.toml")
    (folder / "bad.toml").write_text("schema_version = 99\n")
    assert [saved.path.name for saved in library.saved_themes()] == ["good.toml"]


@pytest.mark.skipif(not Path("/usr/share/color-schemes").is_dir(), reason="no system color schemes")
def test_every_scheme_on_this_system_can_be_copied(home, monkeypatch):
    monkeypatch.setenv("XDG_DATA_DIRS", "/usr/share")
    generator = ColorSchemeGenerator()
    for scheme in library.installed_schemes():
        theme = library.theme_from_scheme(scheme)
        assert theme.problems() == []
        (file,) = generator.files(theme)
        assert generator.check_output(file) == []
