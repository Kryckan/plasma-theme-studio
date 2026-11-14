# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Themes page: saved themes, color schemes and Global Themes in one library."""

import json

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QCoreApplication, QRect, QSize  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget  # noqa: E402

from plasma_theme_studio import paths  # noqa: E402
from plasma_theme_studio.model.theme import FIELD_BY_ID, Theme  # noqa: E402
from plasma_theme_studio.ui import library_view  # noqa: E402
from plasma_theme_studio.ui.banner import INFORMATION, WARNING  # noqa: E402
from plasma_theme_studio.ui.library_view import GlobalEntry, JustifiedFlow  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402

SCHEME = """[Colors:Window]
BackgroundNormal=46,52,64
ForegroundNormal=216,222,233
[Colors:Selection]
BackgroundNormal=136,192,208
[General]
Name=Nordic
"""

DEFAULTS = """[kdeglobals][General]
ColorScheme=Nordic
[kdeglobals][Icons]
Theme=Papirus
[kcminputrc][Mouse]
cursorTheme=Ghost
"""


def make_package(home, package_id, name, defaults=DEFAULTS, author="Someone"):
    folder = home / "system/share/plasma/look-and-feel" / package_id
    (folder / "contents").mkdir(parents=True)
    (folder / "metadata.json").write_text(
        json.dumps(
            {
                "KPlugin": {
                    "Name": name,
                    "Id": package_id,
                    "Description": f"{name} for tests",
                    "Authors": [{"Name": author}],
                }
            }
        )
    )
    (folder / "contents/defaults").write_text(defaults)


@pytest.fixture
def window(app, home, desktop_runner):
    colors = home / "system/share/color-schemes"
    colors.mkdir(parents=True, exist_ok=True)
    (colors / "Nordic.colors").write_text(SCHEME)
    make_package(home, "org.example.look", "Example Look")
    paths.themes_dir().mkdir(parents=True, exist_ok=True)
    Theme({("meta", "name"): "Mine"}).save(paths.themes_dir() / "mine.toml")
    window = MainWindow(desktop_runner)
    window.resize(1100, 720)
    window.show()
    window.show_page("themes")
    window.page("themes").reload()
    yield window
    window.undo_stack.setClean()
    window.close()


@pytest.fixture
def page(window):
    return window.page("themes")


def settle(page):
    page.summary.pool.waitForDone()
    QCoreApplication.processEvents()


def visible_titles(page):
    grid = page.library.grid
    return [
        entry.title
        for item_id, entry in page.library.entries.items()
        if (card := grid.card(item_id)) is not None and not card.isHidden()
    ]


def test_all_three_kinds_are_listed(page):
    kinds = {entry.is_global for entry in page.library.entries.values()}
    assert kinds == {True, False}
    assert "Example Look" in visible_titles(page)
    assert "Mine" in visible_titles(page) and "Nordic" in visible_titles(page)


def test_the_chips_filter_and_mirror_the_combo(page):
    library = page.library
    library.chips.button(2).click()
    assert library.grid.filter.currentIndex() == 2
    assert visible_titles(page) == ["Example Look"]
    library.chips.button(1).click()
    assert visible_titles(page) == ["Mine"]
    library.chips.button(3).click()
    assert "Example Look" not in visible_titles(page) and "Nordic" in visible_titles(page)
    library.grid.filter.setCurrentIndex(0)  # the other way round
    assert library.chips.current() == 0
    assert len(visible_titles(page)) == 3


def test_search_narrows_every_kind(page):
    page.library.search.setText("exam")
    assert visible_titles(page) == ["Example Look"]
    page.library.search.setText("")


def test_the_empty_states_say_something(window, page, home):
    page.library.chips.button(1).click()
    for _ in range(2):
        for path in paths.themes_dir().glob("*.toml"):
            path.unlink()
        window.reload_library()
        page.reload()
    assert visible_titles(page) == []
    assert page.library.grid.message.text() == "You have no saved themes yet."
    page.library.chips.button(0).click()


def test_the_labels_under_the_cards(page):
    words = {entry.title: page.library._kind_word(entry) for entry in page.library.entries.values()}
    assert words["Mine"] == "Saved theme"
    assert words["Example Look"] == "Global Theme"


def test_a_global_card_shows_what_it_sets(page):
    entry = page.library.select_global("org.example.look")
    assert isinstance(entry, GlobalEntry)
    assert page.library.edit_button.text() == "Load into the editor"
    settle(page)
    assert not page.strip.isHidden()
    assert page.strip_title.text() == "Example Look by Someone"
    texts = [label.text() for label in page.strip_sets.findChildren(type(page.strip_about))]
    assert any(text.startswith("Colors: Nordic") for text in texts)
    assert any(text.startswith("Icons: Papirus") for text in texts)
    assert any("(not installed)" in text and "Ghost" in text for text in texts)  # no such cursor theme


def test_the_strip_goes_with_the_selection(page):
    page.library.select_global("org.example.look")
    settle(page)
    page.library.select("Mine") or page.library.grid.set_selected(("theme", "mine"))
    page.library._update_buttons()
    assert page.strip.isHidden()


def test_load_into_the_editor_is_one_undo_step(window, page):
    entry = page.library.select_global("org.example.look")
    steps = window.undo_stack.count()
    page.library.edit_button.click()
    assert window.undo_stack.count() == steps + 1
    assert window.theme.get("colors", "window") == "#2e3440"
    assert window.theme.get("desktop", "icons") == "Papirus"
    assert window.banner.kind == WARNING  # the cursor theme is not installed
    assert "Ghost" in window.banner.text() or "Cursors" in window.banner.text()
    window.undo_stack.undo()
    assert window.theme.get("colors", "window") != "#2e3440"
    assert entry.title == "Example Look"


def test_loading_twice_says_nothing_changed(window, page):
    entry = page.library.select_global("org.example.look")
    assert page.load_global(entry)
    steps = window.undo_stack.count()
    assert page.load_global(entry)
    assert window.undo_stack.count() == steps
    assert "already" in window.banner.text()


def test_a_package_that_sets_nothing_is_said_so(window, page, home):
    make_package(home, "org.example.empty", "Empty Look", defaults="")
    window.reload_library()
    page.reload()
    entry = page.library.select_global("org.example.empty")
    steps = window.undo_stack.count()
    assert page.load_global(entry)
    assert window.undo_stack.count() == steps
    assert window.banner.kind == INFORMATION and "sets none" in window.banner.text()


def test_apply_on_a_global_card_loads_then_applies_the_editor_theme(window, page, monkeypatch):
    asked = []

    def question(parent, title, text, *rest):
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", question)
    applied = []
    monkeypatch.setattr(window, "apply_theme", lambda: applied.append(window.theme.get("colors", "window")))
    page.library.select_global("org.example.look")
    window.use_entry(page.library.current())
    assert len(asked) == 1 and "editor" in asked[0] and "Example Look" in asked[0]
    assert applied == ["#2e3440"]  # the editor already held the package when it was applied
    assert not any("plasma-apply-lookandfeel" in call[0] for call in window.runner.calls)


def test_cancelling_the_question_changes_nothing(window, page, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr(window, "apply_theme", lambda: pytest.fail("applied"))
    page.library.select_global("org.example.look")
    steps = window.undo_stack.count()
    window.use_entry(page.library.current())
    assert window.undo_stack.count() == steps


def test_the_real_apply_never_runs_the_look_and_feel_tool(window, page, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    page.library.select_global("org.example.look")
    window.apply_button.click()
    QCoreApplication.processEvents()
    assert not any("plasma-apply-lookandfeel" in " ".join(call) for call in window.runner.calls)
    assert window.theme.get("desktop", "icons") == "Papirus"


def test_new_theme_from_the_desktop_is_one_undo_step(window, page):
    runner = window.runner
    runner.set("kdeglobals", ["General"], "ColorScheme", "Nordic")
    runner.set("kdeglobals", ["Icons"], "Theme", "Papirus")
    steps = window.undo_stack.count()
    page.new_button.click()
    assert window.undo_stack.count() == steps + 1
    assert window.theme.name == "My desktop"
    assert window.theme.get("colors", "window") == "#2e3440"
    assert window.theme.get("desktop", "icons") == "Papirus"
    assert "Nothing was applied" in window.banner.text()
    assert not any(call[0].startswith("plasma-apply") for call in runner.calls)


def test_undo_after_new_theme_from_the_desktop_brings_back_the_theme_in_the_editor(window, page):
    window.edit(FIELD_BY_ID[("shape", "radius")], 9)
    before = window.theme
    page.new_button.click()
    assert window.theme is not before and window.theme.name == "My desktop"
    window.undo_stack.undo()
    assert window.theme is before and window.theme.get("shape", "radius") == 9
    window.undo_stack.redo()
    assert window.theme.name == "My desktop"


def test_install_from_file_reuses_the_file_menu(window, page, monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: seen.append(a) or ("", ""))
    page.install_action.trigger()
    assert len(seen) == 1


def test_install_from_file_imports_an_archive(window, page, monkeypatch, tmp_path):
    from plasma_theme_studio import archive

    path = tmp_path / f"shared{archive.EXTENSION}"
    archive.export_theme(Theme({("meta", "name"): "Shared"}), path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    page.install_action.trigger()
    assert window.theme.name == "Shared"
    assert "Shared" in [e.title for e in page.library.entries.values()]


def test_open_in_system_settings_launches_the_module(window, page):
    page.settings_action.trigger()
    assert any("kcm_lookandfeel" in " ".join(call) for call in window.runner.launched)


def test_the_in_use_marks_follow_the_desktop(window, page):
    window.runner.set("kdeglobals", ["KDE"], "LookAndFeelPackage", "org.example.look")
    window.runner.set("kdeglobals", ["General"], "ColorScheme", "Nordic")
    page.reload()
    grid = page.library.grid
    assert grid.card(("global", "org.example.look")).in_use
    nordic = next(key for key, e in page.library.entries.items() if e.title == "Nordic")
    mine = next(key for key, e in page.library.entries.items() if e.title == "Mine")
    assert grid.card(nordic).in_use and not grid.card(mine).in_use


def test_a_global_picture_arrives_through_the_loader(window, page):
    card = page.library.grid.card(("global", "org.example.look"))
    assert not card.has_thumbnail()
    image = QImage(QSize(40, 30), QImage.Format.Format_RGB32)
    image.fill(0x336699)
    page.library._picture_ready("global_theme", "org.example.look", image)
    assert card.has_thumbnail()


def test_leaving_the_page_cancels_pictures_and_the_summary(window, page):
    page.library.select_global("org.example.look")
    window.show_page("overview")
    assert page.shown_package == ""


def test_the_justified_flow_fills_the_width(app):
    host = QWidget()
    flow = JustifiedFlow(host)
    for _ in range(7):
        child = QWidget(host)
        child.setFixedSize(180, 100)
        flow.addWidget(child)
    rect = QRect(0, 0, 1000, 600)
    flow.setGeometry(rect)
    xs = sorted({flow.itemAt(i).geometry().x() for i in range(7)})
    last = max(flow.itemAt(i).geometry().right() for i in range(7))
    assert len(xs) == 5 and last >= 1000 - 24  # five columns share the whole width
    assert library_view.JustifiedFlow is JustifiedFlow
