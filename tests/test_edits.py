# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The theme edits that follow an installed Global Theme or color scheme."""

import json

from plasma_theme_studio import library
from plasma_theme_studio.edits import theme_edits_from_color_scheme, theme_edits_from_global_theme
from plasma_theme_studio.model.theme import Theme
from plasma_theme_studio.pickers import kind

SCHEME = """[Colors:Window]
BackgroundNormal=46,52,64
ForegroundNormal=216,222,233
[General]
Name=Nordic
"""

DEFAULTS = """[kdeglobals][General]
ColorScheme=Nordic
font=Noto Sans,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1
fixed=Hack,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1
[kdeglobals][KDE]
widgetStyle=Fusion
[kdeglobals][Icons]
Theme=Papirus
[plasmarc][Theme]
name=breeze-dark
[kcminputrc][Mouse]
cursorTheme=Pop
cursorSize=32
[ksplashrc][KSplash]
Theme=org.kde.breeze.desktop
[kwinrc][org.kde.kdecoration2]
library=org.kde.kwin.aurorae
theme=kwin4_decoration_qml_plastik
"""


def package(home, defaults):
    folder = home / "system/share/plasma/look-and-feel/org.example.look"
    (folder / "contents").mkdir(parents=True)
    (folder / "metadata.json").write_text(
        json.dumps({"KPlugin": {"Name": "Example", "Id": "org.example.look"}})
    )
    (folder / "contents/defaults").write_text(defaults)
    return next(item for item in kind("global_theme").items() if item.id == "org.example.look")


def install_scheme(home):
    folder = home / "system/share/color-schemes"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Nordic.colors").write_text(SCHEME)


def test_a_global_theme_names_every_part_it_sets(app, desktop_runner, home):
    install_scheme(home)
    style = home / "system/share/plasma/desktoptheme/breeze-dark/metadata.json"
    style.write_text('{"KPlugin": {"Id": "breeze-dark", "Name": "Breeze Dark"}}')
    splash = home / "system/share/plasma/look-and-feel/org.kde.breeze.desktop/metadata.json"
    splash.write_text('{"KPlugin": {"Id": "org.kde.breeze.desktop", "Name": "Breeze"}}')
    edits, messages = theme_edits_from_global_theme(package(home, DEFAULTS))
    assert edits[("apps", "style")] == "installed" and edits[("apps", "style_id")] == "Fusion"
    assert edits[("panel", "style")] == "installed" and edits[("panel", "style_id")] == "breeze-dark"
    assert edits[("window", "decoration")] == "installed"
    assert edits[("window", "decoration_id")].endswith(":kwin4_decoration_qml_plastik")
    assert edits[("desktop", "icons")] == "Papirus"
    assert edits[("desktop", "cursors")] == "Pop" and edits[("desktop", "cursor_size")] == 32
    assert edits[("desktop", "splash")] == "org.kde.breeze.desktop"
    assert edits[("fonts", "general")] == "Noto Sans, 10" and edits[("fonts", "fixed")] == "Hack, 10"
    assert edits[("colors", "window")] == "#2e3440"
    theme = Theme()
    for (section, key), value in edits.items():
        theme.set(section, key, value)  # every edit is a field a theme accepts
    assert theme.problems() == []
    assert len(messages) == 1 and "Nordic" in messages[0]  # the scheme lacks most colors


def test_what_is_not_installed_is_left_alone_and_reported(app, desktop_runner, home):
    item = package(home, "[kdeglobals][Icons]\nTheme=Nowhere\n[kcminputrc][Mouse]\ncursorSize=9000\n")
    edits, messages = theme_edits_from_global_theme(item)
    assert edits == {}
    assert len(messages) == 2 and "Nowhere" in messages[0] and all(isinstance(m, str) for m in messages)


def test_a_color_scheme_gives_its_colors(home):
    install_scheme(home)
    scheme = next(s for s in library.installed_schemes() if s.id == "Nordic")
    edits, messages = theme_edits_from_color_scheme(scheme)
    assert edits[("colors", "window")] == "#2e3440" and edits[("colors", "text")] == "#d8dee9"
    assert all(section == "colors" for section, _key in edits)
    assert messages and "Nordic" in messages[0]
