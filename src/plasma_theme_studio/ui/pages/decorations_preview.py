# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A window drawn the way the generated frame draws it: title bar height, the theme's buttons, the shadow."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...generators.windowframe import TITLE_EDGE, Look
from ...model.parts import DEFAULT_BUTTONS, parse_buttons

SCALE_LIMIT = 2.0  # a window is never drawn larger than this times its real size


def _qcolor(color, alpha: float = 1.0) -> QColor:
    result = QColor(color.hex)
    result.setAlphaF(max(0.0, min(alpha, 1.0)))
    return result


class FramePreview(QWidget):
    """The frame of this theme with its own title bar, buttons and offset shadow."""

    WINDOW = (300, 150)  # the size of the window content in real pixels

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setMinimumSize(260, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_theme(self, theme) -> None:
        self.theme = theme
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(480, 280)

    def look(self) -> Look:
        return Look.of(self.theme)

    def layout_buttons(self) -> tuple[str, str]:
        """The letters left and right of the title: the theme's, or the usual ones while it leaves them."""
        left = self.theme.get("window", "buttons_left")
        right = self.theme.get("window", "buttons_right")
        return (
            left if left is not None and parse_buttons(left) is not None else DEFAULT_BUTTONS["left"],
            right if right is not None and parse_buttons(right) is not None else DEFAULT_BUTTONS["right"],
        )

    def paintEvent(self, _event) -> None:  # noqa: N802
        look = self.look()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.palette().window())
        left, right, top, bottom = look.shadow_left, look.shadow_right, look.shadow_top, look.shadow_bottom
        width = self.WINDOW[0] + 2 * look.border
        height = self.WINDOW[1] + look.title_total + look.border
        total_w, total_h = width + left + right, height + top + bottom
        scale = min(self.width() / total_w, self.height() / total_h, SCALE_LIMIT)
        p.translate((self.width() - total_w * scale) / 2, (self.height() - total_h * scale) / 2)
        p.scale(scale, scale)
        p.translate(left, top)
        frame = QRectF(0, 0, width, height)
        self._shadow(p, frame, look)
        path = QPainterPath()
        path.addRoundedRect(frame, look.radius, look.radius)
        p.fillPath(path, _qcolor(look.header))
        p.setClipPath(path)
        content = QRectF(look.border, look.title_total, self.WINDOW[0], self.WINDOW[1])
        p.fillRect(content, _qcolor(look.window))
        p.setClipping(False)
        self._title(p, frame, look)

    def _shadow(self, p: QPainter, frame: QRectF, look: Look) -> None:
        if not look.shadow:
            return
        steps = 14
        for i in range(steps, 0, -1):
            t = i / steps
            grow = QRectF(
                frame.left() - look.shadow_left * t,
                frame.top() - look.shadow_top * t,
                frame.width() + (look.shadow_left + look.shadow_right) * t,
                frame.height() + (look.shadow_top + look.shadow_bottom) * t,
            )
            path = QPainterPath()
            path.addRoundedRect(grow, look.radius + look.shadow * t, look.radius + look.shadow * t)
            p.fillPath(path, QColor(0, 0, 0, round(255 * look.strength * 0.5 / steps * 1.6)))

    def _title(self, p: QPainter, frame: QRectF, look: Look) -> None:
        row_top = TITLE_EDGE
        size = look.button
        y = row_top + (look.title_row - size) / 2
        left, right = self.layout_buttons()
        pen = QPen(_qcolor(look.text), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        x = look.border + 4
        for letter in left:
            self._button(p, QRectF(x, y, size, size), letter, look, pen)
            x += size + look.button_spacing
        x = frame.width() - look.border - 4
        for letter in reversed(right):
            x -= size
            self._button(p, QRectF(x, y, size, size), letter, look, pen)
            x -= look.button_spacing
        p.setPen(_qcolor(look.text))
        title = QRectF(frame.left(), row_top, frame.width(), look.title_row)
        p.drawText(
            title, Qt.AlignmentFlag.AlignCenter, self.theme.name if hasattr(self.theme, "name") else ""
        )

    def _button(self, p: QPainter, box: QRectF, letter: str, look: Look, pen: QPen) -> None:
        if letter == "_":
            return
        inner = box.adjusted(box.width() * 0.3, box.height() * 0.3, -box.width() * 0.3, -box.height() * 0.3)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if letter == "X":
            p.setPen(QPen(_qcolor(look.negative), 1.4))
            p.drawLine(inner.topLeft(), inner.bottomRight())
            p.drawLine(inner.topRight(), inner.bottomLeft())
        elif letter == "A":
            p.drawRect(inner)
        elif letter == "I":
            p.drawLine(inner.bottomLeft(), inner.bottomRight())
        else:
            p.drawEllipse(inner.center(), inner.width() / 3, inner.height() / 3)
