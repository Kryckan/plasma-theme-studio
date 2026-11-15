# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The "Follow the palette" switch of the Colors page: offered or explained, one snapshot, off, Undo."""

import json

import pytest

pytest.importorskip("PySide6.QtWidgets")

# The fixtures of the Colors page tests are used here as they are.
# ruff: noqa: F811

from plasma_theme_studio import follow  # noqa: E402
from plasma_theme_studio.apply import snapshot as snapshots  # noqa: E402
from plasma_theme_studio.ui.banner import INFORMATION, WARNING  # noqa: E402
from plasma_theme_studio.ui.pages.colors_import import ImportColorsDialog  # noqa: E402
from test_page_colors import WAL, answer, page, schemes, window  # noqa: E402, F401


@pytest.fixture(autouse=True)
def plasma(monkeypatch, home):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")
    runtime = home / "run"
    runtime.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))


@pytest.fixture
def wal(home):
    path = home / ".cache/wal/colors.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(WAL))
    return path


def test_off_by_default_and_explained_when_there_is_nothing_to_follow(window, page, desktop_runner):
    desktop_runner.missing = {"wal", "matugen"}
    page.refresh()
    box = page.follow_row.box
    assert box.text() == "Follow the palette"
    assert not box.isChecked() and not box.isEnabled()
    assert "pywal or matugen" in page.follow_row.note.text()
    assert not follow.is_on() and snapshots.list_snapshots() == []


def test_offered_when_a_palette_file_exists(window, page, wal):
    page.refresh()
    box = page.follow_row.box
    assert box.isEnabled() and not box.isChecked()
    assert snapshots.list_snapshots() == []  # looking changes nothing


def test_switching_on_and_off_is_one_snapshot_and_back(window, page, wal, home):
    before = (home / ".config/kdeglobals").read_bytes() if (home / ".config/kdeglobals").exists() else None
    page.follow_row.box.setChecked(True)
    assert follow.is_on() and window.banner.kind != WARNING
    assert len(snapshots.list_snapshots()) == 1
    assert page.follow_row.box.isChecked()
    assert str(wal) in page.follow_row.note.text()
    page.follow_row.box.setChecked(False)
    assert not follow.is_on() and snapshots.list_snapshots() == []
    assert window.banner.kind == INFORMATION
    after = (home / ".config/kdeglobals").read_bytes() if (home / ".config/kdeglobals").exists() else None
    assert after == before


def test_undo_last_apply_switches_it_off_and_the_page_shows_it(window, page, wal):
    page.follow_row.box.setChecked(True)
    assert window.undo_apply_button.isEnabled()
    window.undo_last_apply()
    assert not follow.is_on()
    assert not page.follow_row.box.isChecked()


def test_a_refused_switch_on_says_why_and_stays_off(window, page, wal, monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    page.follow_row.box.setChecked(True)
    assert window.banner.kind == WARNING
    assert not follow.is_on() and snapshots.list_snapshots() == []
    page.refresh()
    assert not page.follow_row.box.isChecked()


def test_the_mapping_chosen_in_the_import_dialog_is_followed(window, page, wal, monkeypatch):
    def choose_color1_for_the_accent(self):
        slot = next(
            i
            for i in range(self.choosers["accent"].count())
            if self.choosers["accent"].itemData(i) == "#8a5a4b"
        )
        self.choosers["accent"].setCurrentIndex(slot)
        return 1

    monkeypatch.setattr(ImportColorsDialog, "exec", choose_color1_for_the_accent)
    assert page.import_colors(str(wal))
    assert page.follow_row.choice is not None
    source, overrides, variant = page.follow_row.choice
    assert source.path == wal and overrides.get("accent") == "color1" and variant == "dark"
    page.follow_row.box.setChecked(True)
    assert follow.load_state().overrides == {"accent": "color1"}
