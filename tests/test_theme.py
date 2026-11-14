# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from plasma_theme_studio.model import theme as theme_module
from plasma_theme_studio.model.color import Color, contrast, readable_on
from plasma_theme_studio.model.theme import Theme, ThemeError, slugify


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
