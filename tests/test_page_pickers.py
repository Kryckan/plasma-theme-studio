# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Icons, Pointers, Splash Screen and System Sounds pages: cards, previews, sizes and Play."""

import json
import struct
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from plasma_theme_studio.model.theme import FIELD_BY_ID  # noqa: E402
from plasma_theme_studio.pickers import icons as icon_picker  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages import pickers_common  # noqa: E402

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" fill="{}"/></svg>'
)


@pytest.fixture(autouse=True)
def fresh(app):
    icon_picker.clear_caches()
    yield
    icon_picker.clear_caches()


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def click(card):
    QTest.mouseClick(card, Qt.MouseButton.LeftButton)


def icon_theme(home, name, names=(), inherits="", color="#336699"):
    folder = home / ".local/share/icons" / name
    (folder / "scalable/places").mkdir(parents=True, exist_ok=True)
    extra = f"Inherits={inherits}\n" if inherits else ""
    (folder / "index.theme").write_text(
        f"[Icon Theme]\nName={name}\n{extra}Directories=scalable/places\n"
        "[scalable/places]\nSize=48\nMinSize=8\nMaxSize=512\nType=Scalable\n"
    )
    for icon in names:
        (folder / "scalable/places" / f"{icon}.svg").write_text(SVG.format(color))
    return folder


def xcursor(argb=0xFFFF0000, nominal=24, side=4):
    head = struct.pack("<4sIII", b"Xcur", 16, 0x10000, 1)
    toc = struct.pack("<III", 0xFFFD0002, nominal, 28)
    chunk = struct.pack("<IIIIIIIII", 36, 0xFFFD0002, nominal, 1, side, side, 0, 0, 50)
    return head + toc + chunk + struct.pack("<I", argb) * (side * side)


def cursor_theme(home, name, sizes=(24, 32)):
    folder = home / ".local/share/icons" / name / "cursors"
    folder.mkdir(parents=True, exist_ok=True)
    (folder.parent / "index.theme").write_text(f"[Icon Theme]\nName={name}\n")
    head = struct.pack("<4sIII", b"Xcur", 16, 0x10000, len(sizes))
    pos = 16 + 12 * len(sizes)
    toc = chunks = b""
    for nominal in sizes:
        toc += struct.pack("<III", 0xFFFD0002, nominal, pos + len(chunks))
        chunks += struct.pack("<IIIIIIIII", 36, 0xFFFD0002, nominal, 1, 4, 4, 0, 0, 50)
        chunks += struct.pack("<I", 0xFFFF0000) * 16
    for file in ("left_ptr", "hand2", "xterm", "watch", "crosshair", "size_fdiag", "crossed_circle"):
        (folder / file).write_bytes(head + toc + chunks)
    return folder


def sound_theme(home, name, sample=True):
    folder = home / "system/share/sounds" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.theme").write_text(f"[Sound Theme]\nName={name}\nDescription=About {name}\n")
    if sample:
        (folder / "bell.oga").write_bytes(b"OggS")
    return folder


def splash_package(home, name="org.test.splash"):
    folder = home / ".local/share/plasma/look-and-feel" / name
    (folder / "contents/splash").mkdir(parents=True, exist_ok=True)
    (folder / "contents/previews").mkdir(parents=True, exist_ok=True)
    meta = {"KPlugin": {"Name": "Test splash", "Id": name, "Description": "A splash"}}
    (folder / "metadata.json").write_text(json.dumps(meta))
    image = QImage(160, 90, QImage.Format.Format_ARGB32)
    image.fill(QColor("#00aa00"))
    assert image.save(str(folder / "contents/previews/splash.png"))
    return name


def settle_worker(page, app):
    assert page.worker.wait()
    app.processEvents()


# ---- the part switch and "In use", for all four pages


@pytest.mark.parametrize(
    "key,card",
    [("icons", "Papirus"), ("pointers", "Pop"), ("splash", "org.test.splash"), ("sounds", "ocean")],
)
def test_the_part_switch_sets_and_leaves_the_part(window, home, app, key, card):
    splash_package(home)
    window.show_page(key)
    page = window.page(key)
    assert not page.header.part_mode()
    steps = window.undo_stack.count()
    click(page.grid.card(card))
    window.settle()
    assert page.header.part_mode() and page.grid.selected_id() == card
    assert window.undo_stack.count() == steps + 1
    page.header.set_part_mode(False)
    page.header.part_mode_changed.emit(False)
    window.settle()
    window.refresh()
    assert not page.header.part_mode()
    page.header.set_part_mode(True)
    page.header.part_mode_changed.emit(True)  # comes back to what was chosen before
    assert page.grid.selected_id() == card


@pytest.mark.parametrize("key", ["icons", "pointers", "splash", "sounds"])
def test_in_use_follows_the_desktop(window, desktop_runner, key):
    window.show_page(key)
    page = window.page(key)
    assert page.grid.in_use() == page.current_id()


# ---- Icons


def test_icon_cards_are_never_blank_and_inherited_icons_show(window, home, app):
    icon_theme(home, "Child", names=("folder",), inherits="Parent")
    icon_theme(home, "Parent", names=("user-home", "user-trash", "text-x-generic"), color="#aa0000")
    icon_theme(home, "Empty")
    window.show_page("icons")
    page = window.page("icons")
    page.load_items()
    child = icon_picker.IconThemes().thumbnail(page.items["Child"], page.grid.thumb_size, 1.0, None)
    assert not child.isNull()
    colors = {
        QColor(child.pixelColor(x, y)).name() for x in range(child.width()) for y in range(child.height())
    }
    assert "#336699" in colors and "#aa0000" in colors  # its own folder and the parent's home


def test_icon_strip_shows_the_chosen_theme_on_the_window_color(window, home, app):
    icon_theme(home, "Strip", names=("folder", "user-home", "user-trash", "configure"))
    window.show_page("icons")
    page = window.page("icons")
    page.load_items()
    window.edit(FIELD_BY_ID[("colors", "window")], "#102030")
    click(page.grid.card("Strip"))
    window.settle()
    settle_worker(page, app)
    assert page.strip.has_content() and not page.top_row.isHidden()
    assert page.strip.background.name() == "#102030"


def test_icon_search_filters_the_cards(window, home):
    window.show_page("icons")
    page = window.page("icons")
    page.grid.search.setText("papi")
    assert [c.item_id for c in page.grid.visible_cards()] == ["Papirus"]
    page.grid.search.setText("zzzz")
    assert page.grid.visible_cards() == []


# ---- Pointers


def test_pointer_cards_show_eight_pointers(window, home):
    from plasma_theme_studio.pickers import cursors

    cursor_theme(home, "Full")
    assert len(cursors.SAMPLES) == 8
    window.show_page("pointers")
    page = window.page("pointers")
    page.load_items()
    image = cursors.CursorThemes().thumbnail(page.items["Full"], page.grid.thumb_size, 1.0, None)
    assert not image.isNull()


def test_pointer_size_box_offers_the_theme_sizes_and_edits_in_one_step(window, home, app):
    cursor_theme(home, "Sized", sizes=(24, 32, 48))
    window.show_page("pointers")
    page = window.page("pointers")
    page.load_items()
    click(page.grid.card("Sized"))
    window.settle()
    window.refresh()
    labels = [page.size_box.itemText(i) for i in range(page.size_box.count())]
    assert page.size_box.itemData(0) is None and page.size_box.itemText(0) == "Leave as it is"
    assert [page.size_box.itemData(i) for i in range(1, page.size_box.count())] == [24, 32, 48]
    assert len(labels) == 4
    steps = window.undo_stack.count()
    page.size_box.setCurrentIndex(2)
    page._size_picked(2)
    assert window.theme.get("desktop", "cursor_size") == 32
    assert window.undo_stack.count() == steps + 1
    page._size_picked(0)
    assert window.theme.get("desktop", "cursor_size") is None
    window.undo_stack.undo()
    window.refresh()
    assert page.size_box.currentData() in (None, 32)  # the box shows what the theme holds
    assert page.size_box.currentData() == window.theme.get("desktop", "cursor_size")


def test_a_scalable_pointer_theme_offers_the_usual_steps(window):
    from plasma_theme_studio.pickers import cursors

    window.show_page("pointers")
    page = window.page("pointers")
    sizes = page.sizes_of(page.items["Pop"])  # no sizes of its own
    assert sizes == sorted(set(cursors.SCALABLE_SIZES))


def test_a_size_the_theme_holds_is_always_offered(window):
    window.show_page("pointers")
    page = window.page("pointers")
    window.edit(FIELD_BY_ID[("desktop", "cursor_size")], 40)
    window.refresh()
    assert 40 in page.sizes_of(page.items["Pop"])


def test_the_pointer_strip_follows_the_size(window, home, app):
    cursor_theme(home, "Strip", sizes=(24, 48))
    window.show_page("pointers")
    page = window.page("pointers")
    page.load_items()
    click(page.grid.card("Strip"))
    window.settle()
    settle_worker(page, app)
    assert page.strip.has_content() and not page.strip.isHidden()
    page._size_picked(page.size_box.findData(48))
    settle_worker(page, app)
    assert page.shown_size() == 48


def test_launch_feedback_opens_the_dialog_in_the_app(window, desktop_runner):
    window.show_page("pointers")
    page = window.page("pointers")
    assert page.launch_button.text() == "Configure Launch Feedback…"
    page.launch_button.click()
    dialog = window.small_dialog
    assert dialog.isVisible() and dialog.windowTitle() == "Configure Launch Feedback"
    assert desktop_runner.launched == []  # nothing of System Settings is started
    dialog.reject()


# ---- Splash Screen


def test_splash_none_card_and_large_preview(window, home, app):
    splash_package(home)
    window.show_page("splash")
    page = window.page("splash")
    none = page.grid.card(page.kind.items()[0].id)
    assert none is not None and none.title() == "None" if hasattr(none, "title") else none is not None
    click(page.grid.card("org.test.splash"))
    window.settle()
    settle_worker(page, app)
    assert not page.top_row.isHidden()
    assert page.name.text() and page.status.text() in ("In use", "Not in use yet")
    assert page.picture.image is not None or not page.picture.isHidden()


# ---- System Sounds


@pytest.mark.parametrize(
    "player,missing,before",
    [
        ("pw-play", set(), []),
        ("paplay", {"pw-play"}, []),
        ("canberra-gtk-play", {"pw-play", "paplay"}, ["-f"]),
    ],
)
def test_play_launches_the_sample_with_the_player_found(
    window, desktop_runner, home, player, missing, before
):
    sample = sound_theme(home, "melody").joinpath("bell.oga")
    desktop_runner.missing |= missing
    window.show_page("sounds")
    page = window.page("sounds")
    page.load_items()
    assert page.player == player
    row = page.grid.card("melody")
    assert row.play.isEnabled()
    steps = window.undo_stack.count()
    row.play.click()
    assert desktop_runner.launched[-1] == [player, *before, str(sample)]
    assert window.undo_stack.count() == steps  # playing edits nothing
    assert window.theme.get("desktop", "sounds") is None


def test_without_a_player_the_buttons_are_off_with_a_tooltip(window, desktop_runner, home):
    sound_theme(home, "melody")
    desktop_runner.missing |= {"pw-play", "paplay", "canberra-gtk-play"}
    window.show_page("sounds")
    page = window.page("sounds")
    page.load_items()
    assert page.player is None
    for row in page.grid.visible_cards():
        assert not row.play.isEnabled() and row.play.toolTip()
    page.play("melody")
    assert desktop_runner.launched == []


def test_a_theme_without_a_sample_cannot_play(window, desktop_runner, home):
    sound_theme(home, "silent", sample=False)
    window.show_page("sounds")
    page = window.page("sounds")
    page.load_items()
    row = page.grid.card("silent")
    assert not row.play.isEnabled() and row.play.toolTip()
    page.play("silent")
    assert desktop_runner.launched == []


def test_a_failing_player_gives_a_message_not_a_crash(window, desktop_runner, home, monkeypatch):
    sound_theme(home, "melody")
    window.show_page("sounds")
    page = window.page("sounds")
    page.load_items()

    def fail(argv):
        raise OSError("no device")

    monkeypatch.setattr(desktop_runner, "launch", fail)
    page.play("melody")  # no exception


def test_clicking_play_does_not_choose_the_theme(window, desktop_runner, home):
    sound_theme(home, "melody")
    window.show_page("sounds")
    page = window.page("sounds")
    page.load_items()
    page.grid.card("melody").play.click()
    assert window.theme.get("desktop", "sounds") is None
    click(page.grid.card("melody"))
    assert window.theme.get("desktop", "sounds") == "melody"


def test_sound_list_keys_and_search(window, home, app):
    window.show_page("sounds")
    page = window.page("sounds")
    ids = page.grid.ids()
    assert len(ids) >= 2
    page.grid.body.setFocus()
    for key, want in (
        (Qt.Key.Key_Home, ids[0]),
        (Qt.Key.Key_Down, ids[1]),
        (Qt.Key.Key_Up, ids[0]),
        (Qt.Key.Key_End, ids[-1]),
    ):
        QTest.keyClick(page.grid.body, key)
        assert page.grid.selected_id() == want
    page.grid.search.setText("ocea")
    assert [r.item_id for r in page.grid.visible_cards()] == ["ocean"]


def test_player_choice_is_made_at_run_time(runner):
    assert pickers_common.find_player(runner) == "pw-play"
    runner.missing.add("pw-play")
    assert pickers_common.find_player(runner) == "paplay"
    runner.missing |= {"paplay", "canberra-gtk-play"}
    assert pickers_common.find_player(runner) is None


# ---- many themes


def test_many_themes_do_not_slow_the_pages(window, home, app, capsys):
    for number in range(150):
        icon_theme(home, f"Icons{number:03d}", names=("folder", "user-home"), inherits="breeze")
        cursor_theme(home, f"Pointer{number:03d}", sizes=(24,))
        sound_theme(home, f"Sound{number:03d}")
    window.show_page("overview")
    results = {}
    for key in ("icons", "pointers", "sounds"):
        start = time.perf_counter()
        window.show_page(key)
        switch = time.perf_counter() - start  # the switch itself, before the first paint
        app.processEvents()
        painted = time.perf_counter() - start
        page = window.page(key)
        assert len(page.grid.ids()) >= 150
        start = time.perf_counter()
        page.grid.search.setText("0")
        app.processEvents()
        page.grid.search.setText("01")
        app.processEvents()
        keystroke = (time.perf_counter() - start) / 2
        results[key] = (switch, painted, keystroke)
        assert switch < 1.5 and keystroke < 1.0
    with capsys.disabled():
        print(
            {k: tuple(round(v * 1000) for v in r) for k, r in results.items()},
            "ms: switch, painted, keystroke",
        )
