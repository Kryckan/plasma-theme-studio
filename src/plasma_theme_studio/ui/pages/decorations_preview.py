# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The large window on the Window Decorations page. The drawing itself is `ui/frame_draw.py`."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...generators.windowframe import Look
from ..frame_draw import draw_window, frame_size, layout_buttons

SCALE_LIMIT = 2.0  # a window is never drawn larger than this times its real size


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
        return layout_buttons(self.theme)

    def paintEvent(self, _event) -> None:  # noqa: N802
        look = self.look()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.palette().window())
        left, right, top, bottom = look.shadow_left, look.shadow_right, look.shadow_top, look.shadow_bottom
        width, height = frame_size(look, *self.WINDOW)
        total_w, total_h = width + left + right, height + top + bottom
        scale = min(self.width() / total_w, self.height() / total_h, SCALE_LIMIT)
        p.translate((self.width() - total_w * scale) / 2, (self.height() - total_h * scale) / 2)
        p.scale(scale, scale)
        p.translate(left, top)
        draw_window(p, QRectF(0, 0, width, height), look, self.theme.name, self.layout_buttons())
