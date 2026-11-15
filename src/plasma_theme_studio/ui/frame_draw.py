# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A window drawn the way the generated frame draws it: the theme's title bar height, border, button size
and spacing, line glyphs for the buttons in the theme's layout, a centred title that is cut off with
"…" when it does not fit, and a shadow that reaches as far as the theme's size and offset say.

The big preview on the Window Decorations page, the cards "This theme" and the Overview use these
functions, so there is one drawing of the frame. All sizes are real pixels: the caller scales the painter.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen

from ..generators.windowframe import TITLE_EDGE, Look
from ..model.parts import DEFAULT_BUTTONS, parse_buttons

BUTTON_MARGIN = 4  # between the border and the first button


def qcolor(color, alpha: float = 1.0) -> QColor:
    result = QColor(color.hex)
    result.setAlphaF(max(0.0, min(alpha, 1.0)))
    return result


def layout_buttons(theme) -> tuple[str, str]:
    """The letters left and right of the title: the theme's, or the usual ones while it leaves them."""
    left = theme.get("window", "buttons_left")
    right = theme.get("window", "buttons_right")
    return (
        left if left is not None and parse_buttons(left) is not None else DEFAULT_BUTTONS["left"],
        right if right is not None and parse_buttons(right) is not None else DEFAULT_BUTTONS["right"],
    )


def frame_size(look: Look, content_width: float, content_height: float) -> tuple[float, float]:
    """The size of the whole window (frame included) around content of the given size."""
    return content_width + 2 * look.border, content_height + look.title_total + look.border


def content_rect(look: Look, frame: QRectF) -> QRectF:
    """Where the window's content sits inside `frame`."""
    return QRectF(
        frame.left() + look.border,
        frame.top() + look.title_total,
        frame.width() - 2 * look.border,
        frame.height() - look.title_total - look.border,
    )


def draw_shadow(p: QPainter, frame: QRectF, look: Look, active: bool = True) -> None:
    """The soft shadow around `frame`, as far out on each side as the theme's size and offset allow."""
    if not look.shadow:
        return
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    steps = 14
    weight = 1.0 if active else 0.5
    for i in range(steps, 0, -1):
        t = i / steps
        grown = QRectF(
            frame.left() - look.shadow_left * t,
            frame.top() - look.shadow_top * t,
            frame.width() + (look.shadow_left + look.shadow_right) * t,
            frame.height() + (look.shadow_top + look.shadow_bottom) * t,
        )
        path = QPainterPath()
        path.addRoundedRect(grown, look.radius + look.shadow * t, look.radius + look.shadow * t)
        p.fillPath(path, QColor(0, 0, 0, round(255 * look.strength * 0.5 * weight / steps * 1.6)))
    p.restore()


def draw_body(p: QPainter, frame: QRectF, look: Look, active: bool = True) -> None:
    """The frame itself: the title bar and border in the header color, the content area in the window's."""
    path = QPainterPath()
    path.addRoundedRect(frame, look.radius, look.radius)
    p.save()
    p.fillPath(path, qcolor(look.header if active else look.window))
    p.setClipPath(path)
    p.fillRect(content_rect(look, frame), qcolor(look.window))
    p.restore()


def draw_titlebar(
    p: QPainter,
    frame: QRectF,
    look: Look,
    title: str,
    buttons: tuple[str, str],
    active: bool = True,
) -> None:
    """The buttons in the theme's layout and the title, centred in the window and cut off with "…" where
    the buttons leave no more room."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    size = look.button
    row = QRectF(frame.left(), frame.top() + TITLE_EDGE, frame.width(), look.title_row)
    y = row.top() + (row.height() - size) / 2
    alpha = 1.0 if active else 0.55
    pen = QPen(qcolor(look.text, alpha), max(1.0, size / 16))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    x = frame.left() + look.border + BUTTON_MARGIN
    for letter in buttons[0]:
        x += _button(p, QRectF(x, y, size, size), letter, look, pen, alpha) + look.button_spacing
    left_end = x
    x = frame.right() - look.border - BUTTON_MARGIN
    for letter in reversed(buttons[1]):
        x -= _button(p, QRectF(x - size, y, size, size), letter, look, pen, alpha) + look.button_spacing
    right_start = x + look.button_spacing
    if title:
        font = QFont(p.font())
        font.setPixelSize(max(1, round(row.height() * 0.58)))
        font.setBold(active)
        p.setFont(font)
        free = QRectF(left_end + 2, row.top(), max(right_start - left_end - 4, 0.0), row.height())
        metrics = QFontMetricsF(font)
        text = metrics.elidedText(title, Qt.TextElideMode.ElideRight, free.width())
        width = metrics.horizontalAdvance(text)
        start = min(max(frame.center().x() - width / 2, free.left()), max(free.right() - width, free.left()))
        p.setPen(qcolor(look.text, alpha))
        p.drawText(QRectF(start, row.top(), width + 1, row.height()), Qt.AlignmentFlag.AlignCenter, text)
    p.restore()


def _button(p: QPainter, box: QRectF, letter: str, look: Look, pen: QPen, alpha: float) -> float:
    """One button as a line drawing in `box`; returns the room it takes (a spacer is half a button)."""
    if letter == "_":
        return box.width() / 2
    inner = box.adjusted(box.width() * 0.3, box.height() * 0.3, -box.width() * 0.3, -box.height() * 0.3)
    c = inner.center()
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if letter == "X":
        p.setPen(
            QPen(qcolor(look.negative, alpha), pen.widthF(), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        p.drawLine(inner.topLeft(), inner.bottomRight())
        p.drawLine(inner.topRight(), inner.bottomLeft())
    elif letter == "A":
        p.drawRect(inner)
    elif letter == "I":
        p.drawLine(inner.bottomLeft(), inner.bottomRight())
    elif letter in "FB":  # keep above: a chevron pointing up; keep below: pointing down
        up = letter == "F"
        tip = QPointF(c.x(), inner.top() if up else inner.bottom())
        base = inner.bottom() if up else inner.top()
        p.drawPolyline([QPointF(inner.left(), base), tip, QPointF(inner.right(), base)])
    elif letter == "L":  # shade: a bar at the top with a chevron
        p.drawLine(inner.topLeft(), inner.topRight())
        p.drawPolyline(
            [QPointF(inner.left(), c.y()), QPointF(c.x(), inner.bottom()), QPointF(inner.right(), c.y())]
        )
    elif letter == "S":  # on all desktops: a ring with a dot
        p.drawEllipse(c, inner.width() / 2, inner.height() / 2)
        p.setBrush(pen.color())
        p.drawEllipse(c, inner.width() / 7, inner.height() / 7)
    elif letter == "H":  # help: a question mark
        font = QFont(p.font())
        font.setPixelSize(max(1, round(box.height() * 0.68)))
        font.setBold(False)
        p.setFont(font)
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, "?")
    elif letter == "E":  # hidden from screenshots: a crossed-out frame
        p.drawRect(inner)
        p.drawLine(inner.bottomLeft(), inner.topRight())
    elif letter in "MN":  # window menu, application menu: three lines
        for step in (-0.5, 0.0, 0.5):
            level = c.y() + step * inner.height()
            p.drawLine(QPointF(inner.left(), level), QPointF(inner.right(), level))
    return box.width()


def draw_window(
    p: QPainter,
    frame: QRectF,
    look: Look,
    title: str,
    buttons: tuple[str, str],
    active: bool = True,
) -> QRectF:
    """Shadow, frame, buttons and title around `frame` (real pixels, the whole window). Returns the content
    area, which the caller fills in."""
    draw_shadow(p, frame, look, active)
    draw_body(p, frame, look, active)
    draw_titlebar(p, frame, look, title, buttons, active)
    return content_rect(look, frame)
