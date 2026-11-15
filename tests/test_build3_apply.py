# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply and undo: what KDE's daemons write in reaction is put back, a kdeglobals that did not exist is
removed again, and the accent and the night mode leave exactly the keys System Settings leaves."""

import dataclasses

import pytest

from plasma_theme_studio import kconfig, library, paths
from plasma_theme_studio.apply import engine, sidefiles
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.desktopparts import PARTS
from plasma_theme_studio.edits import theme_edits_from_color_scheme
from plasma_theme_studio.generators import ColorSchemeGenerator
from plasma_theme_studio.generators.colorscheme import FALLBACK_SCHEME
from plasma_theme_studio.generators.installed import AccentTarget
from plasma_theme_studio.model.theme import Theme

SCHEME = """[General]
Name=Nordic

[Colors:Window]
BackgroundNormal=46,52,64
ForegroundNormal=216,222,233

[Colors:Selection]
BackgroundNormal=136,192,208
"""


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(sidefiles.desktop, "pause", lambda seconds: None)


def everything_under(*roots):
    """Every file under the roots with its bytes, except the snapshots of the app itself."""
    found = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "plasma-theme-studio" not in path.parts:
                found[str(path)] = path.read_bytes()
            elif path.is_dir() and "plasma-theme-studio" not in path.parts:
                found[str(path)] = None
    return found


def state():
    return everything_under(paths.config_home(), paths.data_home())


def daemon_reacts(runner):
    """The desktop writes the GTK files, xsettingsd and the colors in kdeglobals after the colors changed."""
    original = runner.handlers["plasma-apply-colorscheme"]

    def tool(argv):
        result = original(argv)
        config = paths.config_home()
        written = {
            "gtk-3.0/colors.css": "@define-color accent_color #ff0000;\n",
            "gtk-3.0/settings.ini": "[Settings]\ngtk-theme-name=Breeze\n",
            "gtk-4.0/gtk.css": "@import 'colors.css';\n",
            "gtk-4.0/colors.css": "@define-color accent_color #ff0000;\n",
            "gtk-4.0/settings.ini": "[Settings]\ngtk-theme-name=Breeze\n",
            "gtk-3.0/assets/close.svg": "<svg/>\n",
            "xsettingsd/xsettingsd.conf": 'Net/ThemeName "Breeze"\n',
            "gtkrc-2.0": 'gtk-theme-name="Breeze"\n',
            "Trolltech.conf": "[Qt]\nstyle=Breeze\n",
        }
        for name, text in written.items():
            (config / name).parent.mkdir(parents=True, exist_ok=True)
            (config / name).write_text(text)
        (paths.config_home().parent / ".gtkrc-2.0").write_text('gtk-theme-name="Breeze"\n')
        runner.set("kdeglobals", ["Colors:Window"], "BackgroundNormal", "1,2,3")
        runner.set("kdeglobals", ["General"], "ColorSchemeHash", "abcdef")
        return result

    runner.handlers["plasma-apply-colorscheme"] = tool


def own_colors() -> Theme:
    theme = Theme.from_preset("breeze-light")
    theme.set("colors", "accent", "#ff0000")
    theme.set("meta", "name", "Mine")
    return theme


# ---- what the daemons write ------------------------------------------------------------


def test_undo_puts_back_what_the_daemons_wrote_and_removes_what_they_made(desktop_runner, use_generators):
    use_generators(ColorSchemeGenerator())
    daemon_reacts(desktop_runner)
    config = paths.config_home()
    (config / "gtk-3.0").mkdir(parents=True)
    (config / "gtk-3.0/colors.css").write_text("/* mine */\n")
    (config / "gtk-3.0/gtk.css").write_text("/* mine too */\n")
    (config / "kdeglobals").write_text("[KDE]\nwidgetStyle=Fusion\n\n[General]\nColorScheme=BreezeLight\n")
    before = state()
    result = engine.apply(own_colors(), desktop_runner)
    assert (config / "gtk-4.0/settings.ini").exists() and (config / "gtk-3.0/assets/close.svg").exists()
    assert state() != before
    assert engine.restore(result.snapshot, desktop_runner, consume=True) == []
    assert state() == before


def test_a_kdeglobals_that_did_not_exist_is_removed_again(desktop_runner, use_generators):
    use_generators(ColorSchemeGenerator())
    daemon_reacts(desktop_runner)
    before = state()
    assert not (paths.config_home() / "kdeglobals").exists()
    result = engine.apply(own_colors(), desktop_runner)
    assert (paths.config_home() / "kdeglobals").exists()
    assert engine.restore(result.snapshot, desktop_runner, consume=True) == []
    assert not (paths.config_home() / "kdeglobals").exists()
    assert state() == before


def test_the_snapshot_records_files_that_did_not_exist(desktop_runner):
    snapshot = snapshots.create("x", [], {})
    side = snapshot.side
    missing = {entry["path"]: entry for entry in side["files"]}
    assert missing[str(paths.config_home() / "gtk-3.0/colors.css")]["existed"] is False
    assert side["kdeglobals"] == {"existed": False, "text": ""}
    (paths.config_home() / "xsettingsd").mkdir(parents=True)
    (paths.config_home() / "xsettingsd/xsettingsd.conf").write_text("a\n")
    again = snapshots.create("y", [], {})
    entry = {e["path"]: e for e in again.side["files"]}[
        str(paths.config_home() / "xsettingsd/xsettingsd.conf")
    ]
    assert entry["existed"] is True
    assert (again.directory / "side" / entry["stored"]).read_text() == "a\n"


def test_a_snapshot_made_before_this_has_no_side_record_and_still_restores(desktop_runner):
    old = dataclasses.replace(snapshots.create("x", [], {}), side=None)
    (paths.config_home() / "gtk-3.0").mkdir(parents=True)
    (paths.config_home() / "gtk-3.0/colors.css").write_text("kept\n")
    assert engine.restore(old, desktop_runner) == []
    assert (paths.config_home() / "gtk-3.0/colors.css").read_text() == "kept\n"


def test_the_color_groups_are_put_back_and_the_rest_of_kdeglobals_is_left(desktop_runner):
    saved = "[General]\nColorScheme=Old\n\n[Colors:Window]\nBackgroundNormal=9,9,9\n\n[KDE]\nwidgetStyle=A\n"
    current = (
        "[Colors:Button]\nBackgroundNormal=1,1,1\n\n[Colors:Window]\nBackgroundNormal=1,2,3\n\n"
        "[General]\nColorScheme=New\nColorSchemeHash=zz\nfont=F\n\n[KDE]\nwidgetStyle=B\n"
    )
    text = sidefiles.put_back_colors(current, saved)
    assert "[Colors:Button]" not in text and "ColorSchemeHash" not in text
    assert "BackgroundNormal=9,9,9" in text and "ColorScheme=Old" in text
    assert "font=F" in text and "widgetStyle=B" in text  # not ours: the parts put those back


def test_a_scheme_that_was_not_named_before_is_not_named_after(desktop_runner, use_generators):
    use_generators(ColorSchemeGenerator())
    daemon_reacts(desktop_runner)
    desktop_runner.set("kdeglobals", ["KDE"], "widgetStyle", "Fusion")
    result = engine.apply(own_colors(), desktop_runner)
    engine.restore(result.snapshot, desktop_runner, consume=True)
    assert kconfig.user_value("kdeglobals", ["General"], "ColorScheme") is None
    assert kconfig.user_value("kdeglobals", ["Colors:Window"], "BackgroundNormal") is None
    assert kconfig.user_value("kdeglobals", ["KDE"], "widgetStyle") == "Fusion"


# ---- an installed scheme ----------------------------------------------------------------


@pytest.fixture
def nordic(home, runner, use_generators):
    system = home / "system/share/color-schemes"
    system.mkdir(parents=True)
    (system / "Nordic.colors").write_text(SCHEME)
    runner.known.add("Nordic")
    scheme = next(s for s in library.installed_schemes() if s.id == "Nordic")
    theme = Theme()
    for key, value in theme_edits_from_color_scheme(scheme)[0].items():
        theme.set(*key, value)
    return theme


def test_a_desktop_without_a_scheme_name_counts_as_breeze_light(runner, monkeypatch):
    runner.settings["ColorScheme"] = ""
    monkeypatch.setattr(
        "plasma_theme_studio.generators.colorscheme.scheme_name", lambda theme: FALLBACK_SCHEME
    )
    assert ColorSchemeGenerator().is_active(Theme(), runner)
    runner.settings["ColorScheme"] = "BreezeDark"
    assert not ColorSchemeGenerator().is_active(Theme(), runner)


def test_an_installed_scheme_does_not_clear_the_accent_of_the_desktop(nordic, desktop_runner):
    desktop_runner.set("kdeglobals", ["General"], "AccentColor", "1,2,3")
    target = AccentTarget()
    assert not target.wanted(nordic)  # the scheme is applied by name; its accent is not overridden here
    assert target.wanted(Theme())
    nordic.set("colors", "accent_from_wallpaper", True)
    assert target.wanted(nordic)


# ---- the accent -------------------------------------------------------------------------


def general(runner, key):
    return kconfig.user_value("kdeglobals", ["General"], key)


def test_a_picked_accent_leaves_the_keys_system_settings_leaves(desktop_runner):
    accent = PARTS["accent"]
    desktop_runner.set("kdeglobals", ["General"], "accentColorFromWallpaper", "true")
    accent.apply("#ff8000", desktop_runner)
    assert general(desktop_runner, "AccentColor") == "255,128,0"
    assert general(desktop_runner, "LastUsedCustomAccentColor") == "255,128,0"
    assert general(desktop_runner, "accentColorFromWallpaper") is None  # false is the default: no key


def test_following_the_wallpaper_sets_only_that_key(desktop_runner):
    accent = PARTS["accent"]
    accent.apply("wallpaper", desktop_runner)
    assert general(desktop_runner, "accentColorFromWallpaper") == "true"
    assert general(desktop_runner, "AccentColor") is None


def test_the_accent_from_the_scheme_removes_the_override_and_keeps_the_last_color(desktop_runner):
    accent = PARTS["accent"]
    accent.apply("#ff8000", desktop_runner)
    accent.clear(desktop_runner)
    assert general(desktop_runner, "AccentColor") is None
    assert general(desktop_runner, "accentColorFromWallpaper") is None
    assert general(desktop_runner, "LastUsedCustomAccentColor") == "255,128,0"  # System Settings keeps it


def test_an_accent_apply_is_undone_exactly(desktop_runner):
    desktop_runner.set("kdeglobals", ["General"], "ColorScheme", "BreezeLight")
    before = state()
    theme = Theme({("colors", "accent_from_wallpaper"): True})
    result = engine.apply(theme, desktop_runner)
    assert general(desktop_runner, "accentColorFromWallpaper") == "true"
    assert engine.restore(result.snapshot, desktop_runner, consume=True) == []
    assert state() == before


# ---- the night mode ---------------------------------------------------------------------


def test_the_night_mode_sets_one_key_and_off_removes_it(desktop_runner):
    night = PARTS["night_mode"]
    night.apply(True, desktop_runner)
    assert kconfig.user_value("kdeglobals", ["KDE"], "AutomaticLookAndFeel") == "true"
    night.apply(False, desktop_runner)
    assert kconfig.user_value("kdeglobals", ["KDE"], "AutomaticLookAndFeel") is None
    assert not (paths.config_home() / "kdeglobals").exists()  # nothing left, so no file


def test_undo_takes_back_what_plasma_switched_when_the_night_mode_went_on(desktop_runner):
    desktop_runner.set("kdeglobals", ["Icons"], "Theme", "breeze")
    before = state()
    theme = Theme({("desktop", "dark_at_night"): True})
    result = engine.apply(theme, desktop_runner)
    assert kconfig.user_value("kdeglobals", ["KDE"], "AutomaticLookAndFeel") == "true"
    # Plasma switches to the dark Global Theme at once when it is night
    config = paths.config_home()
    desktop_runner.set("kdeglobals", ["KDE"], "LookAndFeelPackage", "org.kde.breezedark.desktop")
    desktop_runner.set("kdeglobals", ["Icons"], "Theme", "breeze-dark")
    (config / "kdedefaults").mkdir()
    (config / "kdedefaults/kdeglobals").write_text("[Icons]\nTheme=breeze-dark\n")
    (config / "kdedefaults/package").write_text("org.kde.breezedark.desktop")
    assert engine.restore(result.snapshot, desktop_runner, consume=True) == []
    assert state() == before
    assert snapshots.list_snapshots() == []


def test_the_night_mode_is_undone_when_kdeglobals_did_not_exist(desktop_runner):
    before = state()
    result = engine.apply(Theme({("desktop", "dark_at_night"): True}), desktop_runner)
    assert (paths.config_home() / "kdeglobals").exists()
    assert engine.restore(result.snapshot, desktop_runner, consume=True) == []
    assert state() == before


def test_the_accent_and_the_night_mode_are_written_with_a_notice(desktop_runner):
    PARTS["accent"].apply("wallpaper", desktop_runner)
    PARTS["night_mode"].apply(True, desktop_runner)
    PARTS["night_mode"].apply(False, desktop_runner)
    written = [argv for argv in desktop_runner.calls if argv[0] == "kwriteconfig6"]
    assert len(written) == 3 and all("--notify" in argv for argv in written)


def test_a_desktop_without_a_scheme_name_takes_the_detour_to_read_breeze_light_again(desktop_runner):
    from plasma_theme_studio.generators.colorscheme import RELOAD_PLACEHOLDER, activate_scheme

    desktop_runner.set("kdeglobals", ["General"], "ColorScheme", "")
    desktop_runner.calls.clear()
    activate_scheme(FALLBACK_SCHEME, desktop_runner)
    names = [argv[-1] for argv in desktop_runner.calls if argv[0] == "kwriteconfig6"]
    assert RELOAD_PLACEHOLDER in names
