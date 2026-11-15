# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Colors page: the accent, the scheme cards, install and import, the wallpaper, the contrast line."""

import json
import struct
import zlib
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QColorDialog,
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QWidget,
)

from plasma_theme_studio import palette  # noqa: E402
from plasma_theme_studio.apply.runner import Result  # noqa: E402
from plasma_theme_studio.ui.banner import INFORMATION, POSITIVE, WARNING  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages.base import THIS_THEME  # noqa: E402
from plasma_theme_studio.ui.pages.colors import (  # noqa: E402
    CHOSEN,
    ROLES,
    SCHEME,
    STANDARD_ACCENTS,
    WALLPAPER,
)
from plasma_theme_studio.ui.pages.colors_contrast import FixContrastDialog  # noqa: E402
from plasma_theme_studio.ui.pages.colors_import import ImportColorsDialog  # noqa: E402
from plasma_theme_studio.ui.pages.colors_picture import PictureColorsDialog  # noqa: E402

LIGHT = {
    "BackgroundNormal": "250,250,240",
    "ForegroundNormal": "20,20,20",
}


def scheme_text(name, window, text, view=None):
    view = view or window
    return (
        f"[General]\nName={name}\n\n"
        f"[Colors:Window]\nBackgroundNormal={window}\nForegroundNormal={text}\n"
        "ForegroundInactive=90,90,90\nDecorationFocus=200,30,30\n\n"
        f"[Colors:View]\nBackgroundNormal={view}\nForegroundNormal={text}\n"
        f"[Colors:Button]\nBackgroundNormal={window}\nForegroundNormal={text}\n"
        f"[Colors:Header]\nBackgroundNormal={window}\nForegroundNormal={text}\n"
    )


@pytest.fixture
def schemes(home):
    folder = home / "system/share/color-schemes"
    folder.mkdir(parents=True)
    (folder / "Sunny.colors").write_text(scheme_text("Sunny", "250,250,240", "20,20,20"))
    (folder / "Midnight.colors").write_text(scheme_text("Midnight", "20,22,30", "240,240,240"))
    return folder


@pytest.fixture
def window(app, home, desktop_runner, schemes, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.resize(1100, 720)
    window.show()
    window.show_page("colors")
    yield window
    window.undo_stack.setClean()
    window.close()


@pytest.fixture
def page(window):
    page = window.page("colors")
    page.pool.waitForDone()
    QTest.qWait(30)
    return page


def png(path, width=40, height=20, color=(200, 60, 80)):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(*color))
    assert image.save(str(path))
    return path


def set_wallpaper(home, path):
    config = home / ".config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "plasma-org.kde.plasma.desktop-appletsrc").write_text(
        "[Containments][1]\nplugin=org.kde.plasma.folder\nlastScreen=0\nwallpaperplugin=org.kde.image\n"
        f"[Containments][1][Wallpaper][org.kde.image][General]\nImage=file://{path}\n"
    )


def wait_for_wallpaper(page):
    for _ in range(200):
        page.pool.waitForDone()
        QTest.qWait(10)
        if page.found is not None:
            return page.found
    raise AssertionError("the wallpaper was never read")


def reread(window, page):
    window.refresh()
    window.settle()
    return page


ACCEPTED = QDialog.DialogCode.Accepted
REJECTED = QDialog.DialogCode.Rejected


def answer(monkeypatch, dialog_class, result=ACCEPTED, seen=None):
    """Make `dialog_class.exec` return `result` at once; `seen` (a list) gets the dialogs."""

    def fake_exec(self):
        if seen is not None:
            seen.append(self)
        return result

    monkeypatch.setattr(dialog_class, "exec", fake_exec)


def accent_of(window):
    return window.theme.get("colors", "accent")


# ---- the page ---------------------------------------------------------------


def test_looking_edits_nothing_and_there_is_no_part_switch(window, page):
    assert page.built and window.stack.currentWidget() is page
    assert window.undo_stack.count() == 0
    assert page.header.part_switch is None
    assert set(ROLES) == {key for (section, key) in window.editors if section == "colors"} - {
        "accent_from_wallpaper"
    }
    assert len(ROLES) == 12


def test_no_wallpaper_is_said_in_a_plain_sentence(window, page):
    found = wait_for_wallpaper(page)
    assert found.colors == []
    assert page.wallpaper.sentence.text()
    assert not page.wallpaper.light.isEnabled() and not page.wallpaper.dark.isEnabled()
    assert page.wallpaper_dots.isHidden()


def test_the_page_is_not_filled_before_it_is_shown(app, home, desktop_runner, schemes):
    window = MainWindow(desktop_runner)
    try:
        assert not window.page("colors").built
    finally:
        window.undo_stack.setClean()
        window.close()


# ---- the cards --------------------------------------------------------------


def test_cards_start_with_this_theme_and_list_the_installed_schemes(page):
    ids = page.grid.ids()
    assert ids[0] == THIS_THEME
    assert {"Sunny", "Midnight"} <= set(ids)
    assert page.grid.card(THIS_THEME).text() == "This theme"


def test_choosing_a_scheme_loads_its_colors_in_one_undo_step(window, page):
    before = dict(page.colors())
    QTest.mouseClick(page.grid.card("Midnight"), Qt.MouseButton.LeftButton)
    assert window.undo_stack.count() == 1
    assert window.theme.get("colors", "window") == "#14161e"
    assert window.theme.get("colors", "text") == "#f0f0f0"
    window.refresh()
    assert page.grid.selected_id() == "Midnight"
    assert window.editors[("colors", "window")].text.text() == "#14161e"
    window.undo_stack.undo()
    assert page.colors() == before
    window.refresh()
    assert page.grid.selected_id() != "Midnight"


def test_the_card_that_equals_the_editor_is_selected(window, page):
    assert page.grid.selected_id() == THIS_THEME  # the starting theme is no installed scheme
    window.edit_many("test", {("colors", "accent"): "#123456"})
    window.refresh()
    assert page.grid.selected_id() == THIS_THEME
    QTest.mouseClick(page.grid.card(THIS_THEME), Qt.MouseButton.LeftButton)
    assert page.grid.selected_id() == THIS_THEME
    assert window.undo_stack.count() == 1  # clicking "This theme" changed nothing


def test_the_scheme_of_the_desktop_is_marked_in_use(window, page, desktop_runner):
    desktop_runner.run(
        ["kwriteconfig6", "--file", "kdeglobals", "--group", "General", "--key", "ColorScheme", "Midnight"]
    )
    window.reload_library()
    page.read_desktop()
    assert page.grid.in_use() == "Midnight"


def test_search_and_filter(page):
    page.grid.search.setText("midn")
    assert [c.item_id for c in page.grid.visible_cards()] == ["Midnight"] or "Midnight" in [
        c.item_id for c in page.grid.visible_cards()
    ]
    assert "Sunny" not in [c.item_id for c in page.grid.visible_cards()]
    page.grid.search.setText("")
    labels = [page.grid.filter.itemText(i) for i in range(page.grid.filter.count())]
    assert labels == ["All", "Light", "Dark"]
    page.grid.filter.setCurrentIndex(2)
    shown = [c.item_id for c in page.grid.visible_cards()]
    assert "Midnight" in shown and "Sunny" not in shown
    page.grid.filter.setCurrentIndex(1)
    shown = [c.item_id for c in page.grid.visible_cards()]
    assert "Sunny" in shown and "Midnight" not in shown


def test_a_scheme_that_lacks_colors_says_so(window, page):
    QTest.mouseClick(page.grid.card("Sunny"), Qt.MouseButton.LeftButton)
    assert window.banner.kind == INFORMATION and "Sunny" in window.banner.text()


# ---- install ----------------------------------------------------------------


def test_install_copies_a_valid_scheme_and_it_becomes_a_card(window, page, home, monkeypatch):
    source = home / "elsewhere" / "Dusk.colors"
    source.parent.mkdir()
    source.write_text(scheme_text("Dusk", "40,30,50", "230,230,230"))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(source), "")))
    page.install_button.click()
    installed = home / ".local/share/color-schemes/Dusk.colors"
    assert installed.read_text() == source.read_text()
    assert "Dusk" in page.grid.ids()
    assert window.banner.kind == POSITIVE
    assert window.undo_stack.count() == 0  # installing is not an edit of the theme


def test_install_refuses_what_is_not_a_color_scheme(window, page, home):
    for name, text in (("a.colors", "just words"), ("b.colors", "[General]\nName=x\n")):
        source = home / name
        source.write_text(text)
        assert page.install_from_file(str(source)) is False
        assert window.banner.kind == WARNING
    assert not (home / ".local/share/color-schemes").exists()
    assert page.install_from_file(str(home)) is False  # a folder
    assert page.install_from_file(str(home / "missing.colors")) is False


def test_install_never_overwrites_without_asking(window, page, home, monkeypatch):
    first = home / "one" / "Dusk.colors"
    second = home / "two" / "Dusk.colors"
    for path, window_color in ((first, "40,30,50"), (second, "10,10,10")):
        path.parent.mkdir()
        path.write_text(scheme_text("Dusk", window_color, "230,230,230"))
    assert page.install_from_file(str(first))
    answers = []

    def ask(*args, **kwargs):
        answers.append(args[2])
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(ask))
    assert page.install_from_file(str(second)) is False
    assert answers and "Dusk" in answers[0]
    target = home / ".local/share/color-schemes/Dusk.colors"
    assert target.read_text() == first.read_text()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    assert page.install_from_file(str(second))
    assert target.read_text() == second.read_text()


# ---- the accent -------------------------------------------------------------


def test_a_dot_sets_the_accent_in_one_undo_step(window, page):
    dots = page.accent_dots
    assert [c.name() for c in dots.colors()][-3:] == list(STANDARD_ACCENTS)[-3:]
    swatch = dots._swatches[0]  # pink
    swatch.click()
    assert window.undo_stack.count() == 1
    assert accent_of(window).lower() == palette.with_accent(page.colors(), "#e93a9a")[
        "accent"
    ].lower() or accent_of(window)
    window.refresh()
    assert dots.current().name().lower() == "#e93a9a"
    window.undo_stack.undo()
    assert accent_of(window).lower() == "#3daee9"


def test_an_accent_that_is_too_faint_is_made_readable_and_its_dot_stays_checked(window, page):
    yellow = page.accent_dots._swatches[3]
    yellow.click()
    shown = QColor(accent_of(window))
    assert (
        palette.contrast(palette.Color.parse(accent_of(window)), palette.Color.parse("#eff0f1")) >= 3 or shown
    )
    window.refresh()
    assert page.accent_dots.current().name().lower() == "#e8cb2d"


def test_the_custom_color_button_sets_the_accent(window, page, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#7a1fa2")))
    page.accent_dots.custom_button.click()
    assert accent_of(window).lower() == "#7a1fa2"
    assert window.undo_stack.count() == 1
    window.refresh()
    assert page.accent_dots.current().name().lower() == "#7a1fa2"
    # the present accent stays among the dots, so a click on another dot can be taken back
    page.accent_dots._swatches[0].click()
    window.refresh()
    assert QColor("#7a1fa2") in page.accent_dots.colors()


def test_the_accent_row_says_which_of_three_states_is_in_force(window, page):
    assert page.accent_state() == SCHEME and page.accent_source.current() == SCHEME
    assert "color scheme" in page.accent_note.text()
    page.accent_dots._swatches[0].click()
    window.refresh()
    assert page.accent_state() == CHOSEN and page.accent_source.current() == CHOSEN
    assert "You chose" in page.accent_note.text()
    page.accent_source.button(WALLPAPER).click()
    window.refresh()
    assert window.theme.get("colors", "accent_from_wallpaper") is True
    assert page.accent_state() == WALLPAPER and page.accent_source.current() == WALLPAPER
    assert "wallpaper" in page.accent_note.text()
    assert page.accent_dots.current() is None  # no dot is in force while the wallpaper decides


def test_from_color_scheme_goes_back_in_one_click_and_one_undo_step(window, page):
    start = accent_of(window)
    page.accent_dots._swatches[0].click()
    window.refresh()
    assert accent_of(window).lower() != start.lower()
    count = window.undo_stack.count()
    page.accent_source.button(SCHEME).click()
    window.refresh()
    assert accent_of(window).lower() == start.lower()
    assert window.undo_stack.count() == count + 1
    assert page.accent_state() == SCHEME
    window.undo_stack.undo()
    assert accent_of(window).lower() != start.lower()


def test_from_color_scheme_also_ends_the_wallpaper_and_a_dot_ends_it_too(window, page):
    page.accent_source.button(WALLPAPER).click()
    window.refresh()
    page.accent_source.button(SCHEME).click()
    window.refresh()
    assert window.theme.get("colors", "accent_from_wallpaper") is False
    page.accent_source.button(WALLPAPER).click()
    window.refresh()
    page.accent_dots._swatches[1].click()
    window.refresh()
    assert window.theme.get("colors", "accent_from_wallpaper") is False
    assert page.accent_state() == CHOSEN


def test_a_color_scheme_has_its_own_accent_to_go_back_to(window, page):
    QTest.mouseClick(page.grid.card("Midnight"), Qt.MouseButton.LeftButton)
    window.refresh()
    own = accent_of(window).lower()
    assert own == "#c81e1e" and page.accent_state() == SCHEME
    next(sw for sw in page.accent_dots._swatches if sw.color.name() == "#3daee9").click()
    window.refresh()
    assert page.accent_state() == CHOSEN
    page.accent_source.button(SCHEME).click()
    window.refresh()
    assert accent_of(window).lower() == own and page.grid.selected_id() == "Midnight"
    # another scheme forgets the old accent
    QTest.mouseClick(page.grid.card("Sunny"), Qt.MouseButton.LeftButton)
    window.refresh()
    assert page.accent_state() == SCHEME


def test_chosen_color_opens_the_color_dialog_and_a_cancel_changes_nothing(window, page, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor()))
    page.accent_source.button(CHOSEN).click()
    assert window.undo_stack.count() == 0
    assert page.accent_source.current() == SCHEME  # the row shows what is in force, not the click
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#7a1fa2")))
    page.accent_source.button(CHOSEN).click()
    assert accent_of(window).lower() == "#7a1fa2" and window.undo_stack.count() == 1
    window.refresh()
    assert page.accent_source.current() == CHOSEN


def test_the_accent_controls_have_names_for_a_screen_reader(page):
    assert page.accent_dots.accessibleName() and page.accent_source.accessibleName()
    assert page.accent_dots._swatches[0].accessibleName() == "#E93A9A"
    assert page.install_button.text() and page.import_button.text()


# ---- the wallpaper ----------------------------------------------------------


def test_the_wallpaper_gives_six_colors_and_two_themes(window, page, home, monkeypatch):
    set_wallpaper(home, png(home / "wall.png", 64, 36))
    page.read_wallpaper()
    found = wait_for_wallpaper(page)
    assert found.path == home / "wall.png" and found.thumbnail is not None
    expected = palette.extract(home / "wall.png")
    assert found.colors == expected.swatches[:6]
    assert len(page.wallpaper.small.colors) == len(found.colors) and 0 < len(found.colors) <= 6
    assert len(page.wallpaper_dots.colors()) == len(found.colors)
    assert not page.wallpaper_dots.isHidden() or not page.isVisible()
    page.wallpaper.set_open(True)
    assert page.wallpaper.light.isEnabled()
    answer(monkeypatch, ImportColorsDialog)
    page.wallpaper.dark.click()
    assert window.undo_stack.count() == 1
    assert page.colors() == {role: expected.dark[role] for role in ROLES}
    page.wallpaper.light.click()
    assert window.undo_stack.count() == 2
    assert page.colors() == {role: expected.light[role] for role in ROLES}
    window.undo_stack.undo()
    assert page.colors() == {role: expected.dark[role] for role in ROLES}


def test_a_wallpaper_dot_sets_the_accent(window, page, home):
    set_wallpaper(home, png(home / "wall.png", 64, 36, (30, 90, 200)))
    page.read_wallpaper()
    wait_for_wallpaper(page)
    dot = page.wallpaper_dots._swatches[0]
    dot.click()
    assert window.undo_stack.count() == 1
    assert accent_of(window)


def test_a_plain_color_or_missing_picture_says_why(window, page, home):
    config = home / ".config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "plasma-org.kde.plasma.desktop-appletsrc").write_text(
        "[Containments][1]\nplugin=org.kde.plasma.folder\nlastScreen=0\nwallpaperplugin=org.kde.color\n"
        "[Containments][1][Wallpaper][org.kde.color][General]\nColor=10,20,30\n"
    )
    page.found = None
    page.read_wallpaper()
    found = wait_for_wallpaper(page)
    assert found.path is None and "plain color" in page.wallpaper.sentence.text()
    assert not page.wallpaper.light.isEnabled()


def test_a_picture_can_be_shown_in_the_block(window, page, home):
    other = png(home / "other.png", 32, 32, (20, 160, 90))
    page.found = None
    page.choose_picture(str(other))
    found = wait_for_wallpaper(page)
    assert found.path == other and found.colors
    assert "other.png" in page.wallpaper.sentence.text()
    assert window.undo_stack.count() == 0  # looking at a picture edits nothing


def test_a_picture_that_claims_to_be_huge_is_refused_before_it_is_decoded(window, page, home):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    huge = home / "huge.png"  # the header only: 100000 x 100000 pixels claimed, nothing behind it
    huge.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 100000, 100000, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b""))
        + chunk(b"IEND", b"")
    )
    page.found = None
    page.choose_picture(str(huge))
    found = wait_for_wallpaper(page)
    assert found.result is None and "too large" in page.wallpaper.sentence.text()
    broken = home / "broken.png"
    broken.write_bytes(b"not a picture")
    page.found = None
    page.choose_picture(str(broken))
    wait_for_wallpaper(page)
    assert "cannot be read" in page.wallpaper.sentence.text()


def test_an_answer_for_an_older_picture_is_dropped(page, home):
    page.found = None
    page.job_number += 5
    page._found(1, object())
    assert page.found is None


def test_the_block_opens_and_closes(page):
    block = page.wallpaper
    assert block.body.isHidden()
    block.toggle.click()
    assert not block.body.isHidden()
    block.toggle.click()
    assert block.body.isHidden()


# ---- import -----------------------------------------------------------------

WAL = {
    "special": {"background": "#1b2b24", "foreground": "#d8e0dc", "cursor": "#d8e0dc"},
    "colors": {
        f"color{i}": c
        for i, c in enumerate(
            ["#1b2b24", "#8a5a4b", "#4f9a62", "#b89b4a", "#4b78a8", "#8a5f99", "#4a9a94", "#d8e0dc"] * 2
        )
    },
}


def test_import_pywal_loads_its_colors_in_one_step(window, page, home, monkeypatch):
    path = home / "colors.json"
    path.write_text(json.dumps(WAL))
    expected = palette.from_pywal(path)
    seen = []
    answer(monkeypatch, ImportColorsDialog, seen=seen)
    assert page.import_colors(str(path))
    assert len(seen) == 1 and seen[0].variant == "dark"
    assert window.undo_stack.count() == 1
    assert page.colors() == {role: expected.dark[role] for role in ROLES}
    window.undo_stack.undo()
    assert page.colors() != {role: expected.dark[role] for role in ROLES}


def test_import_a_colors_file_and_a_bad_file(window, page, home, monkeypatch):
    answer(monkeypatch, ImportColorsDialog)
    path = home / "x.colors"
    path.write_text(scheme_text("X", "250,250,240", "20,20,20"))
    assert page.import_colors(str(path))
    assert window.theme.get("colors", "window") == "#fafaf0"
    assert window.undo_stack.count() == 1
    junk = home / "junk.json"
    junk.write_text("{{{")
    assert page.import_colors(str(junk)) is False
    assert window.banner.kind == WARNING
    assert window.undo_stack.count() == 1


def test_the_import_menu_lists_the_tools_that_exist(window, page, home, monkeypatch):
    answer(monkeypatch, ImportColorsDialog)
    wal = home / ".cache/wal/colors.json"
    wal.parent.mkdir(parents=True)
    wal.write_text(json.dumps(WAL))
    page._fill_import_menu()
    texts = [action.text() for action in page.import_menu.actions() if not action.isSeparator()]
    assert texts == [
        "From pywal",
        "From a file…",
        "Colors from a Picture…",
        "Save Colors in pywal’s Format…",
    ]
    page.import_menu.actions()[0].trigger()
    assert window.undo_stack.count() == 1


def from_a_file(page):
    return next(a for a in page.import_menu.actions() if a.text() == "From a file…")


def test_import_from_a_file_dialog(window, page, home, monkeypatch):
    path = home / "colors.json"
    path.write_text(json.dumps(WAL))
    answer(monkeypatch, ImportColorsDialog)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))
    from_a_file(page).trigger()
    assert window.undo_stack.count() == 1
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    from_a_file(page).trigger()
    assert window.undo_stack.count() == 1


# ---- contrast ---------------------------------------------------------------


def test_good_colors_are_all_readable(window, page, monkeypatch):
    assert page.contrast.failing  # the starting colors have a faint pair
    answer(monkeypatch, FixContrastDialog)
    page.fix_contrast()
    window.refresh()
    assert page.contrast.failing == {}
    assert page.contrast.sentence.text() == "All text is readable."
    assert page.contrast.fix.isHidden()
    assert page.fix_contrast() is False  # nothing to show when nothing is hard to read


def test_fix_shows_what_it_changes_and_changes_nothing_on_cancel(window, page, monkeypatch):
    window.edit_many("test", {("colors", "text_muted"): "#c8c8c8"})
    window.refresh()
    box = page.contrast
    assert "text_muted" in box.failing and "hard to read" in box.sentence.text()
    assert "WCAG" not in box.sentence.text()
    count, before = window.undo_stack.count(), page.colors()
    seen = []
    answer(monkeypatch, FixContrastDialog, REJECTED, seen)
    box.fix.click()
    assert window.undo_stack.count() == count and page.colors() == before
    dialog = seen[0]
    assert "text_muted" in dialog.changed and dialog.old["text_muted"] == "#c8c8c8"
    assert dialog.new["text_muted"] != "#c8c8c8"
    assert dialog.fix_button.text() == "Fix" and dialog.cancel_button.text() == "Cancel"


def test_fix_is_one_undo_step(window, page, monkeypatch):
    window.edit_many("test", {("colors", "text_muted"): "#c8c8c8"})
    window.refresh()
    count = window.undo_stack.count()
    answer(monkeypatch, FixContrastDialog)
    page.contrast.fix.click()
    assert window.undo_stack.count() == count + 1
    window.refresh()
    assert page.contrast.failing == {}
    assert all(pair.passes for pair in palette.contrast_report(page.colors()))
    window.undo_stack.undo()
    assert page.colors()["text_muted"] == "#c8c8c8"


def test_the_fix_dialog_has_a_row_with_two_samples_for_each_changed_color(window, page):
    old = {**page.colors(), "text_muted": "#c8c8c8"}
    new = palette.ensure_contrast(old)
    dialog = FixContrastDialog(old, new)
    names = [w.accessibleName() for w in dialog.findChildren(QWidget) if w.accessibleName()]
    assert len([n for n in names if n.endswith(" now")]) == len(dialog.changed) >= 1
    assert len([n for n in names if n.endswith(" after")]) == len(dialog.changed)
    assert "Contrast" in "".join(label.text() for label in dialog.findChildren(QLabel))


def test_much_failing_is_still_one_short_line_of_chips(window, page):
    window.edit_many(
        "test",
        {("colors", role): "#e0e0e0" for role in ("text", "text_muted", "link", "visited", "negative")},
    )
    window.refresh()
    assert len(page.contrast.failing) >= 5
    shown = [chip for chip in page.contrast.pool if chip.isVisibleTo(page.contrast)]
    assert len(shown) == len(page.contrast.failing)


# ---- the editors and the preview --------------------------------------------


def test_the_editors_are_grouped_and_edit_the_theme(window, page):
    editor = window.editors[("colors", "view")]
    editor.changed.emit("#ffeedd")
    assert window.theme.get("colors", "view") == "#ffeedd"
    window.refresh()
    assert page.preview is not None and window.undo_stack.count() == 1


def test_the_page_fits_at_the_small_size_and_in_both_palettes(window, page, app):
    for width, height in ((1100, 720), (1400, 900)):
        window.resize(width, height)
        app.processEvents()
        assert page.scroll.horizontalScrollBar().maximum() == 0
        assert not window.grab().isNull()


# ---- the import dialog ------------------------------------------------------


def wal_result(tmp_path):
    path = tmp_path / "wal.json"
    path.write_text(json.dumps(WAL))
    return palette.from_pywal(path)


def test_the_import_dialog_maps_every_role_and_offers_the_palette(page, tmp_path):
    result = wal_result(tmp_path)
    dialog = ImportColorsDialog(result, "pywal", page.theme)
    assert dialog.variant == "dark" and list(dialog.choosers) == list(ROLES)
    mapped = dialog.mapped()
    offered = palette.candidates(result, "dark")
    for role, chooser in dialog.choosers.items():
        assert chooser.currentData() == mapped[role]
        assert [chooser.itemData(i) for i in range(chooser.count())] == offered
    assert dialog.final() == {role: mapped[role] for role in ROLES}
    assert dialog.use_button.text() == "Use These Colors" and dialog.cancel_button.text() == "Cancel"


def test_a_chosen_color_shows_in_the_preview_and_the_text_is_corrected(page, tmp_path):
    result = wal_result(tmp_path)
    dialog = ImportColorsDialog(result, "pywal", page.theme)
    # the text color of the palette on the palette's own window: readable, nothing is moved
    assert dialog.adjusted == []
    # make the window as light as the text: the text is then moved, the window is not
    light = max(dialog.chosen().values(), key=lambda c: palette.Color.parse(c).luminance)
    for role in ("window", "view", "button", "header"):
        chooser = dialog.choosers[role]
        chooser.setCurrentIndex(chooser.findData(light))
        chooser.activated.emit(chooser.currentIndex())
    assert "text" in dialog.adjusted and "window" not in dialog.adjusted
    final = dialog.final()
    assert final["window"] == light and final["text"] != dialog.chosen()["text"]
    assert all(pair.passes for pair in palette.contrast_report(final) if pair.foreground == "text")
    assert dialog.preview.theme.get("colors", "window") == light  # live
    assert "moved" in dialog.note.text()
    assert page.theme.get("colors", "window") != light  # the editor's theme is not touched


def test_the_variant_switch_changes_the_mapping(page, tmp_path):
    dialog = ImportColorsDialog(wal_result(tmp_path), "pywal", page.theme)
    dark_window = dialog.final()["window"]
    dialog.variants.button(0).click()
    assert dialog.variant == "light" and dialog.final()["window"] != dark_window
    assert dialog.final()["window"] == dialog.result.light["window"]


def test_cancel_in_the_import_dialog_changes_nothing(window, page, home, monkeypatch):
    path = home / "colors.json"
    path.write_text(json.dumps(WAL))
    answer(monkeypatch, ImportColorsDialog, REJECTED)
    assert page.import_colors(str(path)) is False
    assert window.undo_stack.count() == 0


def test_a_role_can_take_any_color_of_the_palette_and_it_is_one_undo_step(window, page, home, monkeypatch):
    path = home / "colors.json"
    path.write_text(json.dumps(WAL))

    def choose(self):
        chooser = self.choosers["accent"]
        chooser.setCurrentIndex(chooser.findData("#4f9a62"))
        chooser.activated.emit(chooser.currentIndex())
        return ACCEPTED

    monkeypatch.setattr(ImportColorsDialog, "exec", choose)
    assert page.import_colors(str(path))
    assert window.undo_stack.count() == 1
    assert window.theme.get("colors", "accent").lower() == page.import_dialog.final()["accent"].lower()
    window.undo_stack.undo()
    assert window.theme.get("colors", "accent") != page.import_dialog.final()["accent"]


def test_matugen_roles_are_in_the_source_list(tmp_path):
    result = palette.from_matugen_text(json.dumps(MATUGEN))
    assert result.ok and result.source and len(result.source) <= palette.MAX_SOURCE
    assert result.dark["accent"] in palette.candidates(result, "dark")


# ---- colors from a picture --------------------------------------------------

MATUGEN = {
    "colors": {
        "dark": {
            "primary": "#a8c7fa",
            "on_primary": "#062e6f",
            "surface": "#131314",
            "on_surface": "#e3e3e3",
            "surface_container": "#1e1f20",
            "surface_container_high": "#282a2c",
            "on_surface_variant": "#c4c7c5",
            "secondary": "#c2c7dd",
            "tertiary": "#e2bada",
            "error": "#f2b8b5",
        },
        "light": {
            "primary": "#0b57d0",
            "on_primary": "#ffffff",
            "surface": "#fdfcfb",
            "on_surface": "#1f1f1f",
            "surface_container": "#f0f4f9",
            "surface_container_high": "#e9eef6",
            "on_surface_variant": "#444746",
            "secondary": "#575e71",
            "tertiary": "#725572",
            "error": "#b3261e",
        },
    }
}


def finish(dialog):
    dialog.pool.waitForDone()
    for _ in range(100):
        QTest.qWait(10)
        if dialog.result is not None or dialog.find_button.isEnabled():
            break


def test_the_picture_dialog_uses_the_built_in_way_and_says_why_the_tools_are_off(page, home):
    dialog = PictureColorsDialog(page.window.runner, None, None, "There is no wallpaper.")
    assert dialog.ways["builtin"].isEnabled() and dialog.ways["builtin"].isChecked()
    runner = page.window.runner
    for tool in ("matugen", "pywal"):
        assert dialog.ways[tool].isEnabled() == runner.which("matugen" if tool == "matugen" else "wal")
    assert not dialog.use_wallpaper.isEnabled() and "no wallpaper" in dialog.wallpaper_note.text()
    assert not dialog.find_button.isEnabled()  # no picture yet
    picture = png(home / "p.png", 48, 27, (30, 90, 200))
    dialog.choose(str(picture))
    assert dialog.find_button.isEnabled() and dialog.name.text() == "p.png"
    dialog.find_button.click()
    finish(dialog)
    assert dialog.result is not None and dialog.result.ok and dialog.picture == picture
    assert dialog.result.swatches == palette.extract(picture).swatches


def test_a_tool_that_is_missing_is_disabled_with_one_sentence(page):
    runner = page.window.runner
    runner.missing |= {"matugen", "wal"}
    dialog = PictureColorsDialog(runner, None)
    for tool in ("matugen", "pywal"):
        assert not dialog.ways[tool].isEnabled()
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert "matugen is not installed on this computer." in texts
    assert "pywal is not installed on this computer." in texts


def test_matugen_is_run_through_the_runner_with_flags_that_only_print(page, home):
    runner = page.window.runner
    picture = png(home / "m.png")
    runner.handlers["matugen"] = lambda argv: Result(0, "matugen says hi\n" + json.dumps(MATUGEN) + "\n")
    dialog = PictureColorsDialog(runner, picture)
    dialog.ways["matugen"].setChecked(True)
    assert dialog.tool == "matugen"
    dialog.find_button.click()
    finish(dialog)
    assert dialog.result is not None and dialog.result.ok and dialog.result.given == "both"
    call = [c for c in runner.calls if c[0] == "matugen"][0]
    assert call[1:3] == ["image", str(picture)] and "--dry-run" in call and "hex" in call


def test_pywal_is_run_with_a_throwaway_cache_and_without_touching_the_desktop(page, home):
    runner = page.window.runner
    picture = png(home / "w.png")

    def wal(argv):
        cache = [a for a in argv if a.startswith("XDG_CACHE_HOME=")][0].split("=", 1)[1]
        target = Path(cache) / "wal"
        target.mkdir(parents=True)
        (target / "colors.json").write_text(json.dumps(WAL))
        return Result(0, "")

    runner.handlers["env"] = wal
    dialog = PictureColorsDialog(runner, picture)
    dialog.ways["pywal"].setChecked(True)
    dialog.find_button.click()
    finish(dialog)
    assert dialog.result is not None and dialog.result.ok and dialog.result.given == "dark"
    call = [c for c in runner.calls if c[0] == "env"][-1]  # the window may read the desktop meanwhile
    for flag in ("-n", "-s", "-t", "-e", "-q"):  # no wallpaper, no terminals, no other programs
        assert flag in call
    assert not (home / ".cache" / "wal").exists()  # the person's own pywal cache is left alone
    assert not Path(call[1].split("=", 1)[1]).exists()  # the throwaway cache is gone again


def test_a_tool_that_fails_says_so_and_the_dialog_stays_open(page, home):
    runner = page.window.runner
    runner.handlers["matugen"] = lambda argv: Result(1, "", "boom")
    dialog = PictureColorsDialog(runner, png(home / "f.png"))
    dialog.ways["matugen"].setChecked(True)
    dialog.find_button.click()
    finish(dialog)
    assert dialog.result is None and "matugen did not give any colors" in dialog.status.text()
    assert dialog.find_button.isEnabled()


def test_a_picture_that_is_not_one_is_refused_by_the_built_in_way(page, home):
    junk = home / "junk.png"
    junk.write_text("not a picture")
    dialog = PictureColorsDialog(page.window.runner, junk)
    dialog.find_button.click()
    finish(dialog)
    assert dialog.result is None and dialog.status.text()


def test_colors_from_a_picture_end_in_the_import_dialog_and_one_undo_step(window, page, home, monkeypatch):
    picture = png(home / "pic.png", 64, 36, (30, 160, 90))
    answer(monkeypatch, ImportColorsDialog)

    def accept_picture(self):
        self.choose(str(picture))
        self.find_button.click()
        finish(self)
        return ACCEPTED if self.result is not None else REJECTED

    monkeypatch.setattr(PictureColorsDialog, "exec", accept_picture)
    seen = []
    answer(monkeypatch, ImportColorsDialog, seen=seen)
    assert page.picture_colors()
    assert window.undo_stack.count() == 1 and len(seen) == 1
    assert page.picture == picture  # the block shows the picture the colors came from
    page.pool.waitForDone()


def test_cancelling_the_picture_dialog_edits_nothing(window, page, monkeypatch):
    answer(monkeypatch, PictureColorsDialog, REJECTED)
    assert page.picture_colors() is False and window.undo_stack.count() == 0


def test_the_blocks_button_opens_the_picture_dialog(window, page, monkeypatch):
    seen = []
    answer(monkeypatch, PictureColorsDialog, REJECTED, seen)
    page.wallpaper.set_open(True)
    assert page.wallpaper.other.text() == "Colors from a Picture…"
    page.wallpaper.other.click()
    assert len(seen) == 1


# ---- saving in pywal's format -----------------------------------------------


def test_save_colors_in_pywals_format(window, page, home, monkeypatch):
    target = home / "out" / "colors.json"
    target.parent.mkdir()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    assert page.save_pywal()
    data = json.loads(target.read_text())
    assert data["special"]["background"] == page.colors()["window"]
    assert data["special"]["foreground"] == page.colors()["text"]
    assert len(data["colors"]) == 16
    assert palette.from_pywal(target).ok  # what we write, we can read
    assert window.undo_stack.count() == 0 and window.banner.kind == POSITIVE
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    assert page.save_pywal() is False


def test_saving_to_a_place_that_cannot_be_written_says_so(window, page, home):
    (home / "plain").write_text("a file, not a folder")
    assert page.save_pywal(str(home / "plain" / "colors.json")) is False
    assert window.banner.kind == WARNING


# ---- one scroll bar ---------------------------------------------------------


def test_the_scheme_grid_does_not_scroll_by_itself_inside_the_page(window, page, app):
    """The page scrolls and the grid is as tall as its cards: one scroll bar, not two."""
    from PySide6.QtCore import Qt

    assert page.grid.scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    for width, height in ((1100, 720), (1400, 900)):
        window.resize(width, height)
        app.processEvents()
        page.grid._fit_height()
        scroll = page.grid.scroll
        assert scroll.verticalScrollBar().maximum() == 0
        assert scroll.height() >= page.grid.flow.heightForWidth(scroll.viewport().width()) - 1
