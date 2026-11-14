# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from plasma_theme_studio import cli
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply import snapshot as snapshots
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


def test_restore_with_an_id_undoes_the_applies_made_after_it(home, fake_system, capsys):
    path = home / "theme.toml"
    scheme = home / ".local/share/color-schemes/MyTheme.colors"
    theme = Theme()
    contents = []
    for accent in ("#3daee9", "#ff0000", "#0000ff"):
        theme.set("colors", "accent", accent)
        theme.save(path)
        assert cli.main(["apply", str(path)]) == 0
        contents.append(scheme.read_text())
    _newest, second, first = snapshots.list_snapshots()
    capsys.readouterr()

    assert cli.main(["restore", second.id]) == 0

    assert scheme.read_text() == contents[0]  # as it was just before the second apply
    assert [item.id for item in snapshots.list_snapshots()] == [first.id]
    out = capsys.readouterr().out
    assert "The desktop is back to how it was before My Theme was applied" in out
    assert "Run the command again to go back one more apply" in out
    assert cli.main(["restore", second.id]) == 1  # used up
    assert cli.main(["restore"]) == 0
    assert not scheme.exists()
    assert fake_system.settings["ColorScheme"] == "BreezeLight"


def test_restore_with_an_id_says_where_it_stopped(home, fake_system, capsys):
    first = engine.apply(Theme(), fake_system).snapshot
    engine.switch_color_scheme("BreezeDark", "Breeze Dark", fake_system)
    engine.switch_color_scheme("BreezeLight", "Breeze Light", fake_system)
    fake_system.known.discard("BreezeDark")  # Plasma cannot go back to it

    assert cli.main(["restore", first.id]) == 1

    captured = capsys.readouterr()
    assert "is back to how it was" not in captured.out
    assert "The undo stopped at the apply of Breeze Light (" in captured.err
    assert "The applies before it were left as they are." in captured.err
    assert "The snapshot is kept. Run the command again to try once more." in captured.err
    assert len(snapshots.list_snapshots()) == 3

    fake_system.known.add("BreezeDark")
    assert cli.main(["restore", first.id]) == 0
    assert "before My Theme was applied" in capsys.readouterr().out
    assert snapshots.list_snapshots() == []


def test_restore_without_snapshots_and_unknown_id(home, fake_system):
    assert cli.main(["restore"]) == 1
    assert cli.main(["restore", "nope"]) == 1


def test_version_and_usage(capsys):
    assert cli.main(["--version"]) == 0
    assert "0.1.0" in capsys.readouterr().out
    assert cli.main(["--bogus"]) == 2
