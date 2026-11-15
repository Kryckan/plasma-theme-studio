# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The look of the window: one drawing of the frame, one order of accent swatches, the marker of a part
that is left as it is, and the notes that keep their technical detail behind "More about this"."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QModelIndex, QRectF, Qt, QThreadPool  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from plasma_theme_studio.apply import status  # noqa: E402
from plasma_theme_studio.generators.windowframe import Look  # noqa: E402
from plasma_theme_studio.model.theme import Theme  # noqa: E402
from plasma_theme_studio.ui import frame_draw  # noqa: E402
from plasma_theme_studio.ui.main_window import MainWindow  # noqa: E402
from plasma_theme_studio.ui.pages.colors import STANDARD_ACCENTS, accent_order  # noqa: E402
from plasma_theme_studio.ui.pages.login_screen import current_login_theme, preview_of, sketch  # noqa: E402
from plasma_theme_studio.ui.widgets import OFF, InlineNote, MoreAbout, NavList  # noqa: E402


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.resize(1100, 720)
    window.show()
    yield window
    for pool in window.findChildren(QThreadPool):  # background loads must end before the window goes
        pool.waitForDone()
    window.hide()  # no paint while the last answers arrive: a paint can collect garbage in a virtual lookup
    QTest.qWait(30)
    window.undo_stack.setClean()
    window.close()


@pytest.fixture(autouse=True)
def _application(app):
    """Text needs a QApplication, also in the tests that only draw on a picture."""


def theme_with(**values):
    theme = Theme.from_preset("breeze-light")
    for key, value in values.items():
        section, name = key.split("__")
        theme.set(section, name, value)
    return theme


def picture(theme, title="A window", buttons=None, size=(300, 200)):
    """The frame of the theme drawn alone on a transparent picture with 40 px around it."""
    look = Look.of(theme)
    width, height = frame_draw.frame_size(look, *size)
    image = QImage(int(width) + 80, int(height) + 80, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    frame = QRectF(40, 40, width, height)
    p = QPainter(image)
    frame_draw.draw_window(p, frame, look, title, buttons or frame_draw.layout_buttons(theme))
    p.end()
    return image, frame, look


def inked(image, rect):
    """The columns of `rect` that have something drawn in them that is not the frame's own fill."""
    columns = []
    base = {image.pixel(int(rect.left()) + 1, int(rect.center().y()))}
    for x in range(int(rect.left()), int(rect.right())):
        if any(
            image.pixel(x, y) not in base
            for y in range(int(rect.top()), int(rect.bottom()))
            if y < image.height()
        ):
            columns.append(x)
    return columns


# ---- the frame is drawn the way the generated frame is


def test_the_window_is_the_content_plus_the_themes_title_bar_and_border():
    look = Look.of(theme_with(window__title_height=40, window__border_width=3))
    assert frame_draw.frame_size(look, 300, 200) == (306, 200 + look.title_total + look.border)
    content = frame_draw.content_rect(look, QRectF(0, 0, 306, 243))
    assert (content.left(), content.top(), content.width()) == (look.border, look.title_total, 300)


def test_the_shadow_reaches_as_far_as_its_size_and_offsets_say():
    theme = theme_with(shadow__size=20, shadow__offset_x=10, shadow__offset_y=0, shadow__strength=0.8)
    image, frame, look = picture(theme)
    assert look.shadow_right > look.shadow_left  # an offset to the right pushes the shadow that way
    y = int(frame.center().y())

    def alpha(x):
        return image.pixelColor(x, y).alpha()

    assert alpha(int(frame.right()) + look.shadow_right - 3) > 0
    assert alpha(int(frame.right()) + look.shadow_right + 3) == 0
    assert alpha(int(frame.left()) - look.shadow_left + 3) > 0
    assert alpha(int(frame.left()) - look.shadow_left - 3) == 0


def test_a_theme_without_a_shadow_draws_none():
    image, frame, _look = picture(theme_with(shadow__size=0))
    assert image.pixelColor(int(frame.left()) - 4, int(frame.center().y())).alpha() == 0


def test_the_title_is_centred_and_cut_off_with_dots_where_the_buttons_leave_no_room():
    theme = theme_with(window__buttons_left="MS", window__buttons_right="HIAX")
    look = Look.of(theme)
    short, frame, _ = picture(theme, "Notes")
    row = QRectF(frame.left(), frame.top() + 4, frame.width(), look.title_row)
    # the title lies in the middle between the buttons; find its columns between the two button groups
    free_left = frame.left() + look.border + 4 + 2 * (look.button + look.button_spacing) + 4
    free_right = frame.right() - look.border - 4 - 4 * (look.button + look.button_spacing)
    columns = [x for x in inked(short, row) if free_left <= x <= free_right]
    assert abs((min(columns) + max(columns)) / 2 - frame.center().x()) < 6
    long, frame, _ = picture(theme, "A very long title that can never fit between the buttons " * 3)
    columns = [x for x in inked(long, row) if free_left <= x <= free_right]
    assert max(columns) <= free_right and min(columns) >= free_left - 1  # it stays between the buttons


def test_the_buttons_follow_the_themes_layout_and_the_usual_one_while_it_leaves_it():
    assert frame_draw.layout_buttons(Theme()) == ("MSE", "HIAX")
    mac = theme_with(window__buttons_left="XIA", window__buttons_right="")
    assert frame_draw.layout_buttons(mac) == ("XIA", "")
    image, frame, look = picture(mac, "")
    row = QRectF(frame.left(), frame.top() + 4, frame.width(), look.title_row)
    columns = inked(image, row)
    assert max(columns) < frame.center().x()  # nothing is drawn on the right side


def test_a_bigger_button_takes_more_room_in_the_title_bar():
    small, frame_a, look_a = picture(theme_with(window__button_size=16), "", ("XIA", ""))
    big, frame_b, look_b = picture(
        theme_with(window__button_size=26, window__title_height=44), "", ("XIA", "")
    )
    row_a = QRectF(frame_a.left(), frame_a.top() + 4, frame_a.width(), look_a.title_row)
    row_b = QRectF(frame_b.left(), frame_b.top() + 4, frame_b.width(), look_b.title_row)
    assert len(inked(big, row_b)) > len(inked(small, row_a))


# ---- the swatches keep one order


def test_other_accents_come_after_the_standard_ones_by_hue_whatever_order_they_came_in(window):
    window.show_page("colors")
    page = window.page("colors")
    page.pool.waitForDone()
    QTest.qWait(30)
    page.extra_accents = ["#7a1fa2", "#1f7a4d"]
    first = page._dots()
    page.extra_accents = ["#1f7a4d", "#7a1fa2"]
    assert page._dots() == first
    assert first[: len(STANDARD_ACCENTS)] == list(STANDARD_ACCENTS)
    assert first[len(STANDARD_ACCENTS) :] == sorted(["#7a1fa2", "#1f7a4d"], key=accent_order)


# ---- "Left as it is" does not look switched off


def test_a_page_that_is_left_as_it_is_keeps_its_full_label_and_gets_a_small_marker(app):
    def render(state):
        nav = NavList()
        nav.add_page("fonts", "Fonts", state=state)
        nav.resize(240, 60)
        nav.show()
        nav.clearSelection()
        nav.setCurrentIndex(QModelIndex())
        app.processEvents()
        return nav.grab().toImage()

    plain, left = render(""), render(OFF)
    width = plain.width()
    label_area = (30, 4, 90, plain.height() - 8)
    assert plain.copy(*label_area) == left.copy(*label_area)  # the label is not faded
    assert plain.copy(width - 24, 0, 20, plain.height()) != left.copy(width - 24, 0, 20, plain.height())


def test_the_wording_of_a_part_nobody_looked_at_is_plain():
    assert status._not_checked() == "Left as it is on your desktop"


# ---- the notes with a line "More about this"


def test_more_about_this_opens_in_place_and_hides_when_there_is_no_detail(window):
    more = MoreAbout("The detail.", lead="Plain words.", parent=window)
    more.show()
    assert not more.is_open() and more.detail.isHidden()
    more.open(True)
    assert more.is_open() and not more.detail.isHidden()
    more.set_detail("")
    assert more.isHidden()


def test_an_inline_note_holds_its_detail_behind_more_about_this(window):
    note = InlineNote("A plain sentence.", "information", more="The technical part.", parent=window)
    note.show()
    assert note.text() == "A plain sentence."
    assert not note.more.isHidden() and note.more.detail.isHidden()
    note.set_text("Another sentence.")
    assert note.more.isHidden()


def test_the_pages_for_gtk_rofi_and_application_style_say_what_the_user_sees(window):
    from plasma_theme_studio.model.theme import FIELD_BY_ID

    for key, words, field in (
        ("gtk", "closed and opened again", ("gtk", "style")),
        ("rofi", "next time you open it", ("rofi", "style")),
        ("app_style", "change within a second", ("apps", "style")),
    ):
        window.show_page(key)
        page = window.page(key)
        assert page.plain_note("") is None  # a part that is left as it is has nothing to explain
        window.edit(FIELD_BY_ID[field], "generated")  # not the switch: it would pick an installed style
        note = page.plain_note("")
        assert words in note and "Kvantum" not in note and "GTK 3" not in note


def test_the_themes_page_keeps_the_night_text_short_and_shows_two_rows_of_cards(window, home):
    from plasma_theme_studio import paths
    from test_page_themes import make_package

    for number in range(8):
        make_package(home, f"org.example.look{number}", f"Example Look {number}")
    paths.themes_dir().mkdir(parents=True, exist_ok=True)
    Theme({("meta", "name"): "Mine"}).save(paths.themes_dir() / "mine.toml")
    window.show_page("themes")
    page = window.page("themes")
    page.reload()
    page.summary.pool.waitForDone()
    QTest.qWait(60)
    assert page.night_more.lead.text() == "Plasma changes between a light and a dark theme by itself."
    assert page.night_more.detail.isHidden()
    grid = page.library.grid
    cards = grid.visible_cards()
    view = grid.scroll.viewport()
    rows = {}
    for card in cards:
        top = card.mapTo(view, card.rect().topLeft()).y()
        bottom = card.mapTo(view, card.rect().bottomLeft()).y()
        if 0 <= top and bottom <= view.height():
            rows.setdefault(top, []).append(card)
    assert len(rows) >= 2
    window.show_page("overview")
    page.summary.pool.waitForDone()
    QTest.qWait(30)


# ---- the login screen and the system sounds say what is in use


def test_the_login_screen_names_the_theme_the_settings_choose(tmp_path):
    (tmp_path / "a.conf").write_text("[Theme]\nCurrent=first\n")
    (tmp_path / "b.conf").write_text("[Theme]\nCurrent=breeze\n")
    assert current_login_theme([tmp_path / "a.conf", tmp_path / "b.conf"]) == "breeze"  # a later file wins
    assert current_login_theme([tmp_path / "missing.conf"]) is None
    assert preview_of("breeze", tmp_path) is None
    (tmp_path / "breeze").mkdir()
    (tmp_path / "breeze" / "preview.png").write_bytes(b"")
    assert preview_of("breeze", tmp_path) == tmp_path / "breeze" / "preview.png"


def test_a_login_theme_without_a_picture_gets_a_sketch_that_says_so(window):
    picture = sketch(Look.of(Theme()))
    assert (picture.width(), picture.height()) == (360, 202)
    window.show_page("login_screen")
    page = window.page("login_screen")
    page.show_current()
    assert not page.picture.pixmap().isNull() and not page.sketch_note.isHidden()


def test_the_fonts_page_has_one_leave_as_it_is_control_while_every_font_is_left(window):
    window.show_page("fonts")
    page = window.page("fonts")
    assert all(row.leave.isHidden() for row in page.rows.values())
    page.header.part_mode_changed.emit(True)
    assert any(not row.leave.isHidden() for row in page.rows.values())


def test_the_color_of_a_title_does_not_matter_to_the_drawing_of_its_dots():
    assert frame_draw.qcolor(Look.of(Theme()).text).alpha() == 255
    assert QColor(Qt.GlobalColor.black).alpha() == 255
