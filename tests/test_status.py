# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the status of the parts says, and that it agrees with an apply."""

from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply.status import PartStatus, parts_status
from plasma_theme_studio.model.theme import Theme
from test_installed import everything, quiet, start_from_something  # noqa: F401


def by_key(records):
    return {record.key: record for record in records}


def test_every_part_has_a_record_and_a_theme_that_names_nothing_leaves_them(desktop_runner):
    records = parts_status(Theme(), desktop_runner)
    assert [r.key for r in records] == [
        "colors", "app_style", "plasma_style", "panel", "decoration", "borders",
        "icons", "pointers", "fonts", "splash", "sounds", "gtk", "rofi",
    ]  # fmt: skip
    assert all(isinstance(r, PartStatus) and r.title and r.desktop and r.theme for r in records)
    states = {r.key: r.state for r in records}
    assert states["icons"] == states["fonts"] == states["splash"] == "leave"
    assert states["colors"] == "change"


def test_the_named_parts_change_and_then_are_the_same(desktop_runner):
    start_from_something(desktop_runner)
    theme = everything()
    records = by_key(parts_status(theme, desktop_runner))
    for key in ("app_style", "plasma_style", "decoration", "borders", "icons", "pointers", "fonts"):
        assert records[key].state == "change", key
    assert records["icons"].desktop == "breeze"
    assert records["icons"].theme == "Papirus"
    assert "Pop" in records["pointers"].theme and "32" in records["pointers"].theme
    engine.apply(theme, desktop_runner)
    after = by_key(parts_status(theme, desktop_runner))
    for key in ("app_style", "plasma_style", "decoration", "borders", "icons", "pointers", "fonts"):
        assert after[key].state == "same", key
        assert after[key].desktop == after[key].theme or key in ("fonts", "borders", "pointers"), key
    assert after["icons"].desktop == "Papirus"


def test_it_agrees_with_is_current(desktop_runner):
    theme = everything()
    engine.apply(theme, desktop_runner)
    states = {r.state for r in parts_status(theme, desktop_runner) if r.key not in ("colors", "gtk", "rofi")}
    assert states <= {"same", "leave"}


def test_it_never_raises(desktop_runner, monkeypatch):
    from plasma_theme_studio import desktopparts

    def broken(self, runner):
        raise RuntimeError("no")

    monkeypatch.setattr(desktopparts.Icons, "current", broken)
    records = by_key(parts_status(everything(), desktop_runner))
    assert records["icons"].state in ("change", "same", "leave")
    assert len(records) == 13
