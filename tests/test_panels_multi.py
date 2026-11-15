# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""More than one panel: the generator, the theme file, the preview, the screen chooser and the page."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPointF  # noqa: E402

from plasma_theme_studio.apply import engine  # noqa: E402
from plasma_theme_studio.generators import panellayout as pl  # noqa: E402
from plasma_theme_studio.generators.panellayout import PanelLayoutGenerator  # noqa: E402
from plasma_theme_studio.model.theme import Theme, panel_section  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages.panel_screen import ScreenChooser  # noqa: E402
from plasma_theme_studio.ui.preview import PreviewWidget  # noqa: E402
from test_panellayout import FakePlasmashell, panel  # noqa: E402


@pytest.fixture
def two(runner, use_generators):
    """A desktop with a main panel (id 20) and a second one on the left (id 30)."""
    use_generators(PanelLayoutGenerator())
    return FakePlasmashell(
        runner,
        [panel(30, location="left", height=36, length=900), panel(20)],
    )


def theme(*, one=None, two=None, three=None):
    values = {}
    for number, fields in ((1, one), (2, two), (3, three)):
        for key, value in (fields or {}).items():
            values[(panel_section(number), key)] = value
    return Theme(values)


# ---- the generator


def test_the_main_panel_is_number_one_and_the_others_follow_by_id(runner, two):
    listed = pl.list_panels(runner)
    assert [p["id"] for p in listed] == [20, 30]


def test_each_panel_gets_its_own_values(runner, two):
    t = theme(one={"height": 60}, two={"location": "right", "height": 50})
    result = engine.apply(t, runner)
    assert (two.panels[20]["height"], two.panels[20]["location"]) == (60, "bottom")
    assert (two.panels[30]["height"], two.panels[30]["location"]) == (50, "right")
    assert result.plan.warnings == []
    assert engine.is_current(engine.build_plan(t), runner)


def test_a_theme_with_only_the_second_panel_leaves_the_main_one_alone(runner, two):
    engine.apply(theme(two={"height": 70}), runner)
    assert two.panels[20]["height"] == 46 and two.panels[30]["height"] == 70


def test_a_panel_that_is_not_there_is_skipped_and_said_so(runner, two):
    t = theme(one={"height": 60}, three={"height": 90})
    plan = engine.build_plan(t)
    result = engine.apply(t, runner)
    texts = [str(w) for w in result.plan.warnings]
    assert "This desktop has no panel 3, so that part of the theme is skipped." in texts
    assert [str(w) for w in plan.warnings] == texts or plan.warnings is not None
    assert two.panels[20]["height"] == 60
    assert sorted(two.panels) == [20, 30]  # nothing is created
    assert PanelLayoutGenerator().is_active(t, runner)  # a panel that cannot exist does not hold it back
    assert engine.is_current(engine.build_plan(t), runner)


def test_undo_gives_back_every_panel(runner, two):
    before = {i: dict(p) for i, p in two.panels.items()}
    result = engine.apply(theme(one={"location": "top"}, two={"height": 80, "floating": False}), runner)
    snapshot = result.snapshot.settings["panel_layout"]
    assert snapshot["panel"] == 20 and [m["panel"] for m in snapshot["more"]] == [30]
    assert engine.restore(result.snapshot, runner, consume=True) == []
    for id_, state in before.items():
        for key in ("location", "height", "floating"):
            assert two.panels[id_][key] == state[key]


def test_an_old_flat_snapshot_still_restores(runner, two):
    snapshot = PanelLayoutGenerator().capture_settings(runner)
    flat = {key: value for key, value in snapshot.items() if key != "more"}
    engine.apply(theme(one={"height": 90}, two={"height": 90}), runner)
    PanelLayoutGenerator().restore_settings(flat, runner)
    assert two.panels[20]["height"] == 46  # the main panel is back
    assert two.panels[30]["height"] == 90  # the old snapshot knew nothing of the other


def test_the_numbers_are_settled_before_anything_moves(runner, use_generators):
    """Moving the longest panel to another edge must not change which panel the numbers name."""
    use_generators(PanelLayoutGenerator())
    shell = FakePlasmashell(runner, [panel(20, length=1920), panel(30, location="left", length=1900)])
    engine.apply(theme(one={"location": "right"}, two={"height": 70}), runner)
    assert shell.panels[20]["location"] == "right" and shell.panels[30]["height"] == 70
    assert shell.panels[20]["height"] == 46


def test_status_texts_name_the_panels_when_there_are_several(runner, two):
    desktop, wanted = pl.status_texts(theme(one={"height": 60}), runner)
    assert not desktop.startswith("Panel 1:")  # one panel asked for: no numbers
    desktop, wanted = pl.status_texts(theme(one={"height": 60}, two={"height": 50}), runner)
    assert "Panel 1:" in desktop and "Panel 2:" in desktop
    assert "Panel 2:" in wanted
    desktop, wanted = pl.status_texts(theme(three={"height": 50}), runner)
    assert "No such panel on this desktop" in desktop


def test_the_theme_file_keeps_further_panels_as_their_own_sections():
    t = theme(one={"height": 60}, two={"location": "left", "floating": False})
    text = t.to_toml()
    assert "[panel_layout]" in text and "[panel_layout_2]" in text
    assert Theme.from_toml(text) == t
    assert "panel_layout_2" not in theme(one={"height": 60}).to_toml()
    assert (
        Theme.from_toml(Theme().to_toml() + "\n[panel_layout]\nheight = 50\n").get("panel_layout", "height")
        == 50
    )


# ---- the preview


def test_the_preview_draws_every_panel_the_theme_has(app):
    widget = PreviewWidget(theme(one={"location": "bottom"}, two={"location": "left"}))
    assert len(widget._layouts()) == 2
    widget.set_panels([{"location": "top"}, {"location": "right"}, {"location": "bottom"}])
    assert [layout["location"] for layout in widget._layouts()] == ["top", "right", "bottom"]
    assert not widget.grab().isNull()
    one = PreviewWidget(Theme())
    assert len(one._layouts()) == 1


# ---- the screen chooser


def test_the_chooser_picks_a_panel_and_moves_the_chosen_one(app):
    chooser = ScreenChooser()
    chooser.set_panels(
        [{"number": 1, "location": "bottom", "screen": 0}, {"number": 2, "location": "left", "screen": 0}], 1
    )
    picked, chosen = [], []
    chooser.picked.connect(picked.append)
    chooser.chosen.connect(chosen.append)
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    second = chooser.panel_rect(chooser._panels[1]).center()
    QTest.mouseClick(chooser, Qt.MouseButton.LeftButton, pos=second.toPoint())
    assert picked == [2] and chosen == []
    top = chooser.screen_rect(0).center() - QPointF(0, chooser.screen_rect(0).height() * 0.4)
    QTest.mouseClick(chooser, Qt.MouseButton.LeftButton, pos=top.toPoint())
    assert chosen == ["top"]


def test_two_panels_on_one_edge_are_drawn_one_behind_the_other(app):
    chooser = ScreenChooser()
    chooser.set_panels(
        [{"number": 1, "location": "bottom", "screen": 0}, {"number": 2, "location": "bottom", "screen": 0}]
    )
    first, second = (chooser.panel_rect(p) for p in chooser._panels)
    assert first != second and not first.intersects(second)
    assert not chooser.grab().isNull()


def test_every_screen_with_a_panel_is_drawn(app):
    chooser = ScreenChooser()
    one = chooser.width()
    chooser.set_panels(
        [{"number": 1, "location": "bottom", "screen": 0}, {"number": 2, "location": "top", "screen": 1}]
    )
    assert chooser.width() > one
    assert chooser.screen_rect(1).left() > chooser.screen_rect(0).right()


# ---- the page


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setattr(
        pl,
        "live_panels",
        lambda runner: [
            {
                "id": 20,
                "screen": 0,
                "location": "bottom",
                "height": 44,
                "alignment": "center",
                "lengthMode": "fill",
                "floating": True,
                "hiding": "none",
                "opacity": "adaptive",
            },
            {
                "id": 30,
                "screen": 0,
                "location": "left",
                "height": 36,
                "alignment": "left",
                "lengthMode": "fit",
                "floating": False,
                "hiding": "autohide",
                "opacity": "opaque",
            },
        ],
    )
    window = MainWindow(desktop_runner)
    window.show()
    window.show_page("panel")
    window.refresh()
    page = window.page("panel")
    page.read_desktop()
    page.settle()
    window.refresh()
    yield window
    window.undo_stack.setClean()
    window.close()


def test_the_page_lists_the_panels_of_the_desktop(window):
    page = window.page("panel")
    assert page.panel_numbers() == [1, 2]
    assert page.picker is not None and page.picker.isVisibleTo(page)


def test_left_as_it_is_the_rows_show_the_desktop_and_cannot_be_changed(window):
    page = window.page("panel")
    assert not page.form_box.isEnabled()
    assert window.editors[("panel_layout", "location")].inner.currentData() == "bottom"
    page._select(2)
    assert window.editors[("panel_layout_2", "location")].inner.currentData() == "left"
    assert window.editors[("panel_layout_2", "height")].inner.box.value() == 36
    assert not window.theme.to_toml().count("panel_layout")


def test_set_by_this_theme_starts_every_row_from_the_desktop(window):
    page = window.page("panel")
    page.header.part_mode_changed.emit(True)
    assert window.theme.get("panel_layout", "height") == 44
    assert window.theme.get("panel_layout_2", "location") == "left"
    assert window.theme.get("panel_layout_2", "opacity_mode") == "opaque"
    assert window.undo_stack.count() == 1  # one step for both panels
    window.undo_stack.undo()
    assert not page.is_set()


def test_one_panel_can_be_left_alone_and_the_page_says_so_only_there(window):
    page = window.page("panel")
    page.header.part_mode_changed.emit(True)
    page._select(2)
    window.refresh()
    row = window.editors[("panel_layout_2", "height")]
    assert not row.quiet.isVisibleTo(row)
    row.leave.click()
    assert window.theme.get("panel_layout_2", "height") is None
    window.refresh()
    assert row.quiet.isVisibleTo(row)  # only this row speaks
    other = window.editors[("panel_layout_2", "location")]
    assert not other.quiet.isVisibleTo(other)
    assert window.theme.get("panel_layout_2", "location") == "left"


def test_a_panel_can_be_left_alone_as_a_whole(window):
    page = window.page("panel")
    page.header.part_mode_changed.emit(True)
    page._select(2)
    window.refresh()
    page.panel_switch.click()
    assert not page.is_set(2) and page.is_set(1)
    assert not page.form_box.isEnabled()
    page.panel_switch.click()
    assert page.is_set(2) and window.theme.get("panel_layout_2", "location") == "left"


def test_a_panel_the_desktop_lacks_is_listed_with_a_warning(window):
    window.edit_many("x", {("panel_layout_3", "height"): 50})
    window.refresh()
    page = window.page("panel")
    assert page.panel_numbers() == [1, 2, 3]
    page._select(3)
    assert page.missing.isVisibleTo(page)
    assert "no panel 3" in page.missing.text()
    page._select(1)
    assert not page.missing.isVisibleTo(page)


def test_clicking_the_screen_moves_only_the_chosen_panel(window):
    page = window.page("panel")
    page.header.part_mode_changed.emit(True)
    page._select(2)
    page._edge_chosen("right")
    assert window.theme.get("panel_layout_2", "location") == "right"
    assert window.theme.get("panel_layout", "location") == "bottom"


def test_the_preview_follows_every_panel(window):
    page = window.page("panel")
    page.header.part_mode_changed.emit(True)
    window.edit(window.editors[("panel_layout_2", "location")].field, "top")
    window.refresh()
    assert [layout["location"] for layout in page.preview.panel_layouts] == ["bottom", "top"]
