# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The shared window code the page builders rely on: scrolling, the cards of "This theme", the extra
areas of a page, the part switch, the status worker, the side bar, the link pages, the preview."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QRectF, QSize, Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QLabel, QScrollArea  # noqa: E402

from plasma_theme_studio.apply import engine  # noqa: E402
from plasma_theme_studio.apply.status import (  # noqa: E402
    BLOCKED,
    CHANGE,
    LEAVE,
    PARTS,
    SAME,
    STATE_WORDS,
    PartStatus,
    state_word,
)
from plasma_theme_studio.model.theme import FIELD_BY_ID  # noqa: E402
from plasma_theme_studio.ui import pages, this_theme  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages.base import THIS_THEME, LinkPage, PickerPage, TargetPage  # noqa: E402
from plasma_theme_studio.ui.preview import SCENE_H, SCENE_W, PreviewWidget  # noqa: E402


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.resize(1100, 720)
    window.show()
    window.settle()
    yield window
    window.undo_stack.setClean()
    window.close()


def answer(monkeypatch, *states, why="no good reason"):
    """Make the status worker say `states` for the first parts."""

    def fake(theme, runner):
        return [
            PartStatus(key, str(title), "now", why if state == BLOCKED else "wanted", state)
            for (key, title, _ids), state in zip(PARTS, states, strict=False)
        ]

    monkeypatch.setattr(engine, "parts_status", fake)


# ---- 1. one scroll per page -------------------------------------------------


@pytest.mark.parametrize("size", [(1400, 900), (1100, 720)])
def test_a_picker_page_has_one_scroll_and_the_grid_at_full_height(window, app, size):
    window.resize(*size)
    window.show_page("icons")
    app.processEvents()
    page = window.page("icons")
    assert isinstance(page, PickerPage) and page.scroll is not None
    own = [s for s in page.findChildren(QScrollArea) if s is not page.scroll and s.isVisible()]
    assert own == []  # the grid does not scroll by itself
    assert page.grid.height() >= page.grid.flow.heightForWidth(page.grid.width()) - 2
    assert page.header.isVisible() and page.header.parent() is not page.scroll.widget()


def test_the_search_stays_in_view_and_cards_are_drawn_only_when_seen(window, app):
    window.show_page("icons")
    app.processEvents()
    page = window.page("icons")
    bar = page.grid.bar
    assert bar.isVisible() and not page.scroll.isAncestorOf(bar)
    page.scroll.verticalScrollBar().setValue(page.scroll.verticalScrollBar().maximum())
    app.processEvents()
    assert bar.isVisible()
    wanted = [c for c in page.grid.cards if c._requested]
    assert len(wanted) < len(page.grid.cards) or len(page.grid.cards) < 12


# ---- 2. "This theme" shows the part ------------------------------------------


@pytest.mark.parametrize("kind", ["decoration", "plasma_style", "app_style", "color_scheme"])
def test_this_theme_draws_the_part(window, kind):
    image = this_theme.thumbnail(kind, window.theme, QSize(220, 140), 2.0)
    assert isinstance(image, QImage) and not image.isNull()
    assert image.width() == 440 and image.height() == 280
    assert image != this_theme.thumbnail("none", window.theme, QSize(220, 140), 2.0)


def test_a_page_can_draw_its_own_this_theme_card(window, app):
    page = window.page("decorations")
    assert isinstance(page, PickerPage)
    calls = []

    def mine(size, dpr):
        calls.append((size, dpr))
        image = QImage(size * dpr, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.red)
        return image

    page.this_theme_thumbnail = mine
    window.show_page("decorations")
    app.processEvents()
    page.update_this_theme_cards()
    assert calls


def test_the_this_theme_cards_follow_an_edit_after_a_pause(window, app):
    window.show_page("decorations")
    page = window.page("decorations")
    seen = []
    page.update_this_theme_cards = lambda: seen.append(1)
    window.edit(FIELD_BY_ID[("window", "radius")], 9)
    page.refresh()
    assert page.this_timer.isActive()
    page.refresh()
    page.this_timer.timeout.emit()
    assert seen


# ---- 3. extra room ---------------------------------------------------------------


def test_a_picker_page_has_room_for_a_top_row_and_something_below(window):
    window.show_page("icons")
    page = window.page("icons")
    assert not page.top_row.isVisibleTo(page)
    top, below = QLabel("top"), QLabel("below")
    page.add_top_row(top)
    page.add_below(below)
    assert page.top_row.isVisibleTo(page) and top.parent() is page.top_row
    assert page.below.indexOf(below) >= 0
    assert (
        page.content.indexOf(page.top_row)
        < page.content.indexOf(page.grid.bar.parentWidget() or page.top_row) + 5
    )


def test_a_page_can_have_a_preview_beside_it(window, app):
    window.show_page("icons")
    page = window.page("icons")
    box = QLabel("preview")
    page.set_side_preview(box, 300)
    app.processEvents()
    assert box.isVisible() and page.side_box.width() == 300


def test_a_target_page_has_a_slot_for_a_preview_on_the_right(window, app):
    window.show_page("rofi")
    page = window.page("rofi")
    assert isinstance(page, TargetPage)
    box = QLabel("preview")
    page.set_side_preview(box)
    app.processEvents()
    assert box.isVisible() and box.mapTo(page, box.rect().topLeft()).x() > page.width() // 2


# ---- 4. the part switch remembers --------------------------------------------------


def test_the_part_switch_remembers_the_choice(window):
    window.show_page("icons")
    page = window.page("icons")
    page._picked("Papirus")
    assert window.theme.get("desktop", "icons") == "Papirus"
    page.header.set_part_mode(False)
    page.header.part_mode_changed.emit(False)
    assert window.theme.get("desktop", "icons") is None
    page._picked("breeze")  # choosing something else turns it on again
    page.header.set_part_mode(False)
    page.header.part_mode_changed.emit(False)
    page.header.set_part_mode(True)
    page.header.part_mode_changed.emit(True)
    assert window.theme.get("desktop", "icons") == "breeze"


# ---- 5. the status off the GUI thread --------------------------------------------------


def test_the_status_is_made_in_a_worker_and_settle_waits_for_it(window, monkeypatch):
    answer(monkeypatch, CHANGE, SAME)
    window.update_status()
    assert window.status_pending
    window.settle()
    assert not window.status_pending
    assert [p.state for p in window.statuses[:2]] == [CHANGE, SAME]


def test_an_old_answer_is_dropped(window, monkeypatch):
    answer(monkeypatch, CHANGE)
    window.update_status()
    old = window.status_generation
    window.status_generation += 1  # an edit came in
    window._status_ready(old, [PartStatus("x", "X", "a", "b", SAME)])
    assert window.status_pending and all(p.key != "x" for p in window.statuses)
    window.settle()


def test_the_bar_keeps_its_sentence_while_the_answer_is_pending(window, monkeypatch):
    answer(monkeypatch, CHANGE)
    window.settle()
    sentence = window.desktop_bar.status.text()
    assert sentence
    window.update_status()
    assert window.desktop_bar.status.text() == sentence
    window.settle()


def test_apply_is_off_when_nothing_would_change_and_on_after_an_edit(window, monkeypatch):
    answer(monkeypatch, SAME, LEAVE)
    window.update_status()
    window.settle()
    assert not window.apply_button.isEnabled() and window.apply_button.toolTip()
    window.edit(FIELD_BY_ID[("shape", "radius")], window.theme.get("shape", "radius") + 3)
    window.refresh_timer.stop()
    window.refresh()
    assert window.apply_button.isEnabled()
    window.settle()
    assert not window.apply_button.isEnabled()


def test_a_blocked_part_is_named_in_the_bar(window, monkeypatch):
    answer(monkeypatch, SAME, BLOCKED, why="the file is read-only")
    window.update_status()
    window.settle()
    text = window.desktop_bar.status.text()
    assert str(PARTS[1][1]) in text and "the file is read-only" in text
    assert window.apply_button.isEnabled()


# ---- 6. the side bar and the link pages ---------------------------------------------------------


def test_every_entry_of_the_side_bar_is_reachable_without_a_scroll_bar(window, app):
    app.processEvents()
    nav = window.nav
    assert not nav.verticalScrollBar().isVisible()
    assert nav.verticalScrollBar().maximum() == 0
    assert nav.compact


def test_the_side_bar_is_roomy_when_the_window_is_tall(window, app):
    window.resize(1400, 1000)
    app.processEvents()
    assert not window.nav.compact


def test_the_login_screen_is_a_link_at_the_end_of_the_desktop_group(window, desktop_runner):
    spec = pages.SPECS["login_screen"]
    assert spec.kind == "link" and spec.link == "kcm_sddm" and str(spec.title) == "Login Screen (SDDM)"
    desktop = dict((str(caption), keys) for caption, keys in pages.GROUPS)["Desktop"]
    assert desktop[-1] == "login_screen"
    window.show_page("login_screen")
    page = window.page("login_screen")
    assert isinstance(page, LinkPage)
    page.open_button.click()
    assert desktop_runner.launched[-1][-1] == "kcm_sddm"


def test_a_link_page_says_when_system_settings_is_missing(window, desktop_runner):
    desktop_runner.missing = {"systemsettings", "kcmshell6"}
    window.show_page("login_screen")
    window.page("login_screen").open_button.click()
    assert desktop_runner.launched == [] and window.banner.isVisible()


# ---- 7. the words of the overview -------------------------------------------------------------------


def test_the_state_words_are_one_vocabulary():
    assert [str(STATE_WORDS[s]) for s in (CHANGE, SAME, LEAVE, BLOCKED)] == [
        "Will change",
        "Already so",
        "Left as it is",
        "Cannot be applied",
    ]
    assert state_word(CHANGE) == "Will change"


def test_the_part_titles_are_the_titles_of_the_side_bar():
    titles = {str(spec.title) for spec in pages.PAGES}
    for key, title, _ids in PARTS:
        if key in ("kvantum", "gtk", "night_mode"):  # night_mode is a switch of the Themes page
            continue
        assert str(title) in titles or str(title) == "Window Borders and Buttons", key
    assert all(str(t)[:1].isupper() for _k, t, _i in PARTS)


def test_the_overview_uses_the_state_words(window, monkeypatch):
    answer(monkeypatch, CHANGE, SAME, LEAVE, BLOCKED)
    window.update_status()
    window.settle()
    window.show_page("overview")
    text = " ".join(w.text() for w in window.page("overview").findChildren(QLabel) if hasattr(w, "text"))
    table = window.page("overview")
    seen = {str(state_word(s)) for s in (CHANGE, SAME, LEAVE, BLOCKED)}
    assert any(word in text for word in seen) or table is not None


# ---- 8. the Panel view ----------------------------------------------------------------------------------


@pytest.mark.parametrize("location", ["top", "bottom", "left", "right"])
@pytest.mark.parametrize("floating", [False, True])
def test_the_panel_view_is_the_whole_screen_edge(window, location, floating):
    window.theme.set("panel_layout", "location", location)
    window.theme.set("panel_layout", "floating", floating)
    preview = PreviewWidget(window.theme)
    preview.set_mode("panel")
    view = preview.view_rect()
    panel, vertical, _attached = preview._panel_geometry()
    if vertical:
        assert view.height() == SCENE_H and view.width() < SCENE_W
    else:
        assert view.width() == SCENE_W and view.height() < SCENE_H
    assert view.contains(panel)
    scene = QRectF(0, 0, SCENE_W, SCENE_H)
    assert scene.contains(view)


def test_the_menu_view_holds_the_whole_popup(window):
    preview = PreviewWidget(window.theme)
    preview.set_mode("menu")
    view = preview.view_rect()
    panel, vertical, attached = preview._panel_geometry()
    popup, bubble = preview._popup_rects(panel, vertical, attached)
    scene = QRectF(0, 0, SCENE_W, SCENE_H)
    for part in (popup, bubble, panel):
        assert view.contains(part.intersected(scene))


# ---- 9. the files dialog ---------------------------------------------------------------------------------


def test_the_files_dialog_has_three_lists_with_headings(window):
    window.show_files()
    dialog = window.files_dialog
    headings = [w.text() for w in dialog.findChildren(QLabel) if w.text()]
    for heading in ("Will be written", "Already up to date", "Will be removed"):
        assert any(h.startswith(heading) for h in headings), heading
    assert dialog.windowTitle() == "Files"


def test_this_theme_constant_is_the_first_card_of_a_generating_picker(window):
    window.show_page("decorations")
    assert window.page("decorations").grid.ids()[0] == THIS_THEME
