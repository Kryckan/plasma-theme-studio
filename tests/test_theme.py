# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import os
import stat

import pytest

from plasma_theme_studio.model import theme as theme_module
from plasma_theme_studio.model.color import Color, contrast, readable_on
from plasma_theme_studio.model.theme import Theme, ThemeError, slugify, write_atomic


def test_round_trip_keeps_every_value():
    theme = Theme.from_preset("breeze-dark")
    theme.set("meta", "name", 'Nörd "Tema"')
    theme.set("shadow", "strength", 0.5)
    assert Theme.from_toml(theme.to_toml()) == theme


def test_slug_is_ascii_camel_case():
    assert slugify("My Theme") == "MyTheme"
    assert slugify("blå natt 2") == "BlaNatt2"
    assert slugify("../../etc") == "Etc"
    assert slugify("日本") == ""


def test_missing_keys_get_defaults():
    theme = Theme.from_toml('schema_version = 1\n[colors]\naccent = "#F00"\n')
    assert theme.get("colors", "accent") == "#ff0000"
    assert theme.get("shape", "radius") == 5


@pytest.mark.parametrize(
    "body",
    [
        '[colors]\naccent = "blue"',
        "[colors]\nmystery = 1",
        "[extra]\nkey = 1",
        "[shape]\nradius = 99",
        "[shape]\nradius = 2.5",
        "[shape]\nradius = true",
        '[meta]\nname = "a\\nb"',
        '[meta]\nname = "!!!"',
    ],
)
def test_invalid_files_are_rejected(body):
    with pytest.raises(ThemeError):
        Theme.from_toml(f"schema_version = 1\n{body}\n")


def test_all_problems_are_reported_together():
    with pytest.raises(ThemeError) as caught:
        Theme.from_toml('schema_version = 1\n[colors]\naccent = "x"\ntext = "y"\n')
    assert len(caught.value.problems) == 2


@pytest.mark.parametrize("header", ["", "schema_version = 0", "schema_version = 99", 'schema_version = "1"'])
def test_bad_schema_versions_are_rejected(header):
    with pytest.raises(ThemeError):
        Theme.from_toml(header + "\n")


def test_older_files_are_migrated_and_backed_up(tmp_path, monkeypatch):
    def rename_window(data):
        data["colors"]["window"] = data["colors"].pop("window_background")
        return data

    monkeypatch.setattr(theme_module, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(theme_module, "MIGRATIONS", {1: rename_window})
    path = tmp_path / "old.toml"
    original = 'schema_version = 1\n[colors]\nwindow_background = "#111111"\n'
    path.write_text(original)

    theme = Theme.load(path)

    assert theme.get("colors", "window") == "#111111"
    assert (tmp_path / "old.toml.v1.bak").read_text() == original
    assert "schema_version = 2" in path.read_text()


def test_save_leaves_no_temporary_files(tmp_path):
    path = tmp_path / "themes" / "a.toml"
    Theme().save(path)
    assert [p.name for p in path.parent.iterdir()] == ["a.toml"]
    assert Theme.load(path) == Theme()


def test_color_helpers():
    assert Color.parse("#abc").hex == "#aabbcc"
    assert Color.parse("#3daee9").kde == "61,174,233"
    assert not Color.is_valid("#12345")
    assert not Color.is_valid(123)
    assert round(contrast(Color(0, 0, 0), Color(255, 255, 255))) == 21
    assert readable_on(Color(20, 20, 20)) == Color(255, 255, 255)


def test_choices_switches_and_values_left_alone_survive_a_round_trip():
    theme = Theme()
    assert theme.get("panel_layout", "location") is None  # the panel is left where it is
    assert "[panel_layout]" not in theme.to_toml()

    theme.set("window", "decoration", "generated")
    theme.set("panel_layout", "location", "top")
    theme.set("panel_layout", "floating", False)
    theme.set("panel_layout", "height", 60)
    text = theme.to_toml()

    assert 'decoration = "generated"' in text
    assert '[panel_layout]\nlocation = "top"\nheight = 60\nfloating = false\n' in text
    assert Theme.from_toml(text) == theme

    theme.set("panel_layout", "location", None)
    assert "location" not in theme.to_toml()


@pytest.mark.parametrize(
    "section, key, value",
    [
        ("window", "decoration", "fancy"),
        ("window", "decoration", None),  # this choice always has a value
        ("panel_layout", "location", "middle"),
        ("panel_layout", "location", 1),
        ("panel_layout", "floating", "yes"),
        ("panel_layout", "floating", 1),
        ("panel_layout", "height", 500),
    ],
)
def test_values_outside_what_a_field_offers_are_refused(section, key, value):
    with pytest.raises(ThemeError):
        Theme().set(section, key, value)
    if value is not None:  # a key that is missing from a file gets its default
        with pytest.raises(ThemeError):
            Theme.from_data({"schema_version": 1, section: {key: value}})


def test_a_replaced_file_keeps_its_permissions(tmp_path):
    path = tmp_path / "private.conf"
    path.write_text("old\n")
    path.chmod(0o600)

    write_atomic(path, "new\n")

    assert path.read_text() == "new\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["private.conf"]  # no temporary file is left


@pytest.mark.parametrize(("mask", "mode"), [(0o022, 0o644), (0o077, 0o600), (0o002, 0o664)])
def test_a_new_file_gets_the_permissions_of_any_new_file(tmp_path, mask, mode):
    old = os.umask(mask)
    try:
        write_atomic(tmp_path / "sub" / "new.conf", b"data")
        assert os.umask(mask) == mask  # asking for the mask does not change it
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "sub" / "new.conf").stat().st_mode) == mode


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "1e999"])
@pytest.mark.parametrize(("section", "key"), [("panel_layout", "height"), ("shadow", "strength")])
def test_a_number_that_is_no_number_is_refused_like_any_other_bad_value(tmp_path, section, key, value):
    path = tmp_path / "odd.toml"
    path.write_text(f'schema_version = 1\n[meta]\nname = "Odd"\n[{section}]\n{key} = {value}\n')
    with pytest.raises(ThemeError) as caught:
        Theme.load(path)
    assert f"{section}.{key} must be a" in str(caught.value)


def test_a_file_kept_somewhere_else_is_written_there_and_the_link_stays(tmp_path):
    kept = tmp_path / "dotfiles" / "theme.toml"
    kept.parent.mkdir()
    kept.write_text("old\n")
    kept.chmod(0o600)
    link = tmp_path / "themes" / "theme.toml"
    link.parent.mkdir()
    link.symlink_to(kept)

    write_atomic(link, "new\n")

    assert link.is_symlink() and kept.read_text() == "new\n"
    assert stat.S_IMODE(kept.stat().st_mode) == 0o600
    assert [p.name for p in link.parent.iterdir()] == ["theme.toml"]
    assert [p.name for p in kept.parent.iterdir()] == ["theme.toml"]


def test_a_link_that_leads_nowhere_gets_its_file(tmp_path):
    link = tmp_path / "theme.toml"
    link.symlink_to(tmp_path / "elsewhere" / "theme.toml")

    write_atomic(link, "new\n")

    assert link.is_symlink() and (tmp_path / "elsewhere" / "theme.toml").read_text() == "new\n"


def test_saving_a_theme_through_a_link_keeps_the_link(tmp_path):
    kept = tmp_path / "dotfiles" / "rose.toml"
    kept.parent.mkdir()
    Theme({("meta", "name"): "Rose"}).save(kept)
    link = tmp_path / "rose.toml"
    link.symlink_to(kept)

    theme = Theme.load(link)
    theme.set("shape", "radius", 9)
    theme.save(link)

    assert link.is_symlink() and Theme.load(kept).get("shape", "radius") == 9


def test_new_fields_default_and_inherit():
    theme = Theme()
    assert (
        theme.get("apps", "style") == theme.get("gtk", "style") == theme.get("rofi", "style") == "unchanged"
    )
    assert theme.resolved("popup", "radius") == theme.resolved("shape", "radius")
    theme.set("panel", "radius", 9)
    theme.set("panel", "opacity", 0.5)
    assert theme.resolved("popup", "radius") == 9 and theme.resolved("popup", "opacity") == 0.5
    theme.set("window", "radius", 3)
    assert theme.resolved("gtk", "window_radius") == 3
    assert theme.get("rofi", "opacity") == 1.0 and theme.get("rofi", "font") is None
    assert "font" not in theme.to_toml() and "[popup]" not in theme.to_toml()


def test_new_fields_round_trip_and_limits():
    theme = Theme({("popup", "opacity"): 0.4, ("rofi", "font"): "Inter 11", ("gtk", "style"): "generated"})
    assert Theme.from_toml(theme.to_toml()) == theme
    for section, key, value in (
        ("popup", "opacity", 0.1),
        ("rofi", "opacity", 0.2),
        ("popup", "border_width", 5),
        ("gtk", "window_radius", 25),
        ("rofi", "style", "breeze"),
    ):
        with pytest.raises(ThemeError):
            Theme().set(section, key, value)


def test_a_theme_from_before_the_new_sections_loads_unchanged():
    theme = Theme.from_toml('schema_version = 1\n\n[panel]\nstyle = "generated"\n')
    assert theme.get("rofi", "style") == "unchanged"


NAMED_PARTS = {
    ("apps", "style"): "installed",
    ("apps", "style_id"): "Fusion",
    ("panel", "style"): "installed",
    ("panel", "style_id"): "breeze-dark",
    ("window", "decoration"): "installed",
    ("window", "decoration_id"): "org.kde.kwin.aurorae:kwin4_decoration_qml_plastik",
    ("window", "border_size"): "Large",
    ("window", "buttons_left"): "MN",
    ("window", "buttons_right"): "IAX",
    ("desktop", "icons"): "Papirus",
    ("desktop", "cursors"): "Pop",
    ("desktop", "cursor_size"): 32,
    ("desktop", "splash"): "None",
    ("desktop", "sounds"): "oxygen",
    ("fonts", "general"): "Noto Sans, 11",
    ("fonts", "window_title"): "Noto Sans, 10, 700",
    ("colors", "accent_from_wallpaper"): True,
}


def test_the_installed_parts_round_trip_and_default_to_nothing():
    assert Theme.from_toml(Theme(NAMED_PARTS).to_toml()) == Theme(NAMED_PARTS)
    plain = Theme()
    for section, key in NAMED_PARTS:
        assert plain.get(section, key) in (None, "unchanged", False), (section, key)
    assert "[desktop]" not in plain.to_toml() and "[fonts]" not in plain.to_toml()
    assert (
        Theme.from_toml('schema_version = 1\n[window]\ndecoration = "breeze"\n').get("desktop", "icons")
        is None
    )


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("window", "decoration", "fancy"),
        ("window", "border_size", "Gigantic"),
        ("window", "buttons_left", "MM"),
        ("window", "buttons_right", "Q"),
        ("desktop", "cursor_size", 7),
        ("desktop", "cursor_size", 257),
        ("desktop", "icons", ""),
        ("fonts", "general", "no size"),
        ("panel", "style", "breeze"),
        ("apps", "style", "fancy"),
        ("colors", "accent_from_wallpaper", "yes"),
    ],
)
def test_the_installed_parts_refuse_values_outside_what_they_offer(section, key, value):
    with pytest.raises(ThemeError):
        Theme().set(section, key, value)


def test_installed_without_an_id_is_unchanged_and_is_said():
    theme = Theme({("apps", "style"): "installed", ("window", "decoration"): "installed"})
    assert theme.part_state("apps", "style") == theme.part_state("window", "decoration") == "unchanged"
    assert theme.unnamed_parts() == [("apps", "style"), ("window", "decoration")]
    assert theme.part_state("window", "decoration") == "unchanged"
    named = Theme({("apps", "style"): "installed", ("apps", "style_id"): "Fusion"})
    assert named.part_state("apps", "style") == "installed" and named.unnamed_parts() == []


def test_an_old_file_loads_unchanged_and_a_new_one_is_still_schema_one():
    old = Theme.from_toml('schema_version = 1\n\n[window]\ndecoration = "generated"\n')
    assert old.get("window", "border_size") is None and old.get("fonts", "general") is None
    assert old.part_state("window", "decoration") == "generated"
    assert "schema_version = 1" in Theme(NAMED_PARTS).to_toml()
