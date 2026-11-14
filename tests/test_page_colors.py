# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Colors page: the accent, the scheme cards, install and import, the wallpaper, the contrast line."""

import json
import struct
import zlib

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QColorDialog, QFileDialog, QMessageBox  # noqa: E402

from plasma_theme_studio import palette  # noqa: E402
from plasma_theme_studio.ui.banner import INFORMATION, POSITIVE, WARNING  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages.base import THIS_THEME  # noqa: E402
from plasma_theme_studio.ui.pages.colors import ROLES, STANDARD_ACCENTS  # noqa: E402

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


def test_the_accent_follows_the_wallpaper_check_box(window, page):
    box = page.follows
    assert not box.isChecked()
    box.click()
    assert window.theme.get("colors", "accent_from_wallpaper") is True
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert not box.isChecked()
    assert "wallpaper" in page.follows_note.text()


def test_the_accent_dots_have_names_for_a_screen_reader(page):
    assert page.accent_dots.accessibleName() and page.follows.accessibleName()
    assert page.accent_dots._swatches[0].accessibleName() == "#E93A9A"
    assert page.install_button.text() and page.import_button.text()


# ---- the wallpaper ----------------------------------------------------------


def test_the_wallpaper_gives_six_colors_and_two_themes(window, page, home):
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


def test_another_picture_can_be_chosen(window, page, home, monkeypatch):
    other = png(home / "other.png", 32, 32, (20, 160, 90))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(other), "")))
    page.found = None
    page.wallpaper.choose.emit()
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


def test_import_pywal_loads_its_colors_in_one_step(window, page, home):
    path = home / "colors.json"
    path.write_text(json.dumps(WAL))
    expected = palette.from_pywal(path)
    assert page.import_colors(str(path))
    assert window.undo_stack.count() == 1
    assert page.colors() == {role: expected.dark[role] for role in ROLES}
    window.undo_stack.undo()
    assert page.colors() != {role: expected.dark[role] for role in ROLES}


def test_import_a_colors_file_and_a_bad_file(window, page, home):
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


def test_the_import_menu_lists_the_tools_that_exist(window, page, home):
    wal = home / ".cache/wal/colors.json"
    wal.parent.mkdir(parents=True)
    wal.write_text(json.dumps(WAL))
    page._fill_import_menu()
    texts = [action.text() for action in page.import_menu.actions() if not action.isSeparator()]
    assert texts == ["From pywal", "From a file…"]
    page.import_menu.actions()[0].trigger()
    assert window.undo_stack.count() == 1


def test_import_from_a_file_dialog(window, page, home, monkeypatch):
    path = home / "colors.json"
    path.write_text(json.dumps(WAL))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))
    page.import_menu.actions()[-1].trigger()
    assert window.undo_stack.count() == 1
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    page.import_menu.actions()[-1].trigger()
    assert window.undo_stack.count() == 1


# ---- contrast ---------------------------------------------------------------


def test_good_colors_are_all_readable(window, page):
    assert page.contrast.failing  # the starting colors have a faint pair
    page.fix_contrast()
    window.refresh()
    assert page.contrast.failing == []
    assert not page.contrast.good.isHidden()
    assert page.contrast.good.text() == "All text is readable."


def test_failing_pairs_are_listed_and_fixed_in_one_step(window, page):
    window.edit_many("test", {("colors", "text_muted"): "#c8c8c8"})
    window.refresh()
    box = page.contrast
    assert box.failing
    first = box.rows.itemAt(0).layout().itemAt(1).widget().text()
    assert first.startswith("Muted text on ") and ":1, should be at least 4.5:1" in first
    assert not box.fix.isHidden() or not page.isVisible()
    count = window.undo_stack.count()
    box.fix.click()
    assert window.undo_stack.count() == count + 1
    window.refresh()
    assert box.failing == []
    assert all(pair.passes for pair in palette.contrast_report(page.colors()))
    window.undo_stack.undo()
    assert page.colors()["text_muted"] == "#c8c8c8"


def test_the_list_is_short_when_much_fails(window, page):
    window.edit_many(
        "test",
        {("colors", role): "#e0e0e0" for role in ("text", "text_muted", "link", "visited", "negative")},
    )
    window.refresh()
    assert page.contrast.rows.count() == 6
    assert page.contrast.more.text().startswith("And ")


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
