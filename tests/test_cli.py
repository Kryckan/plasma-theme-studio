# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from plasma_theme_studio import cli
from plasma_theme_studio.model.theme import Theme


@pytest.fixture
def fake_system(runner, monkeypatch):
    monkeypatch.setattr(cli, "SystemRunner", lambda: runner)
    monkeypatch.setattr(cli, "_load_translation", lambda: None)
    return runner


def test_validate(home, fake_system, capsys):
    good, bad = home / "good.toml", home / "bad.toml"
    Theme().save(good)
    bad.write_text('schema_version = 1\n[colors]\naccent = "nope"\n')
    assert cli.main(["validate", str(good)]) == 0
    assert cli.main(["validate", str(bad)]) == 1
    assert "colors.accent" in capsys.readouterr().err
    assert cli.main(["validate", str(home / "missing.toml")]) == 1


def test_apply_then_restore(home, fake_system, capsys):
    path = home / "theme.toml"
    Theme().save(path)
    scheme = home / ".local/share/color-schemes/MyTheme.colors"

    assert cli.main(["apply", str(path)]) == 0
    assert scheme.exists()
    assert cli.main(["restore", "--list"]) == 0
    assert "My Theme" in capsys.readouterr().out

    assert cli.main(["restore"]) == 0
    assert not scheme.exists()
    assert fake_system.settings["ColorScheme"] == "BreezeLight"
    assert cli.main(["restore"]) == 1  # the snapshot was used up


def test_repeated_restore_steps_back_through_applies(home, fake_system):
    path = home / "theme.toml"
    scheme = home / ".local/share/color-schemes/MyTheme.colors"
    theme = Theme()
    theme.save(path)
    assert cli.main(["apply", str(path)]) == 0
    first = scheme.read_text()
    theme.set("colors", "accent", "#ff0000")
    theme.save(path)
    assert cli.main(["apply", str(path)]) == 0

    assert cli.main(["restore"]) == 0
    assert scheme.read_text() == first
    assert cli.main(["restore"]) == 0
    assert not scheme.exists()
    assert fake_system.settings["ColorScheme"] == "BreezeLight"


def test_restore_without_snapshots_and_unknown_id(home, fake_system):
    assert cli.main(["restore"]) == 1
    assert cli.main(["restore", "nope"]) == 1


def test_version_and_usage(capsys):
    assert cli.main(["--version"]) == 0
    assert "0.1.0" in capsys.readouterr().out
    assert cli.main(["--bogus"]) == 2
