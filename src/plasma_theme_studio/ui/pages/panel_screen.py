# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A small drawn screen with four edges to click: where the panel sits."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPalette, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..widgets import mix

translate = QCoreApplication.translate

SCREEN = QSize(200, 124)
STRIP = 10  # how thick an edge is drawn
REACH = 0.26  # how much of the screen a click on an edge reaches in


def edge_names() -> dict[str, str]:
    return {
        "top": translate("ui", "Top edge"),
        "bottom": translate("ui", "Bottom edge"),
        "left": translate("ui", "Left edge"),
        "right": translate("ui", "Right edge"),
    }


class ScreenChooser(QWidget):
    """The screen edge the panel is on. `value()` is "top", "bottom", "left", "right" or None (not set).
    The arrow keys choose an edge, so it is reachable without a mouse."""

    chosen = Signal(str)  # the person clicked or pressed an arrow key

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value: str | None = None
        self._hover: str | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(SCREEN)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(translate("ui", "Screen edge of the panel"))
        self.set_value(None)

    def value(self) -> str | None:
        return self._value

    def set_value(self, value: str | None) -> None:
        self._value = value
        names = edge_names()
        self.setAccessibleDescription(names.get(value, translate("ui", "No edge chosen")))
        self.update()

    def sizeHint(self) -> QSize:
        return SCREEN

    # ---- the edges

    def screen_rect(self) -> QRectF:
        return QRectF(1, 1, self.width() - 2, self.height() - 2)

    def edge_rect(self, edge: str) -> QRectF:
        """What is drawn for an edge."""
        r = self.screen_rect().adjusted(5, 5, -5, -5)
        return {
            "top": QRectF(r.left(), r.top(), r.width(), STRIP),
            "bottom": QRectF(r.left(), r.bottom() - STRIP, r.width(), STRIP),
            "left": QRectF(r.left(), r.top() + STRIP + 4, STRIP, r.height() - 2 * STRIP - 8),
            "right": QRectF(r.right() - STRIP, r.top() + STRIP + 4, STRIP, r.height() - 2 * STRIP - 8),
        }[edge]

    def edge_at(self, pos: QPointF) -> str | None:
        r = self.screen_rect()
        if not r.contains(pos):
            return None
        x, y = (pos.x() - r.left()) / r.width(), (pos.y() - r.top()) / r.height()
        if y < REACH and x > 0.12 and x < 0.88:
            return "top"
        if y > 1 - REACH and x > 0.12 and x < 0.88:
            return "bottom"
        if x < REACH:
            return "left"
        if x > 1 - REACH:
            return "right"
        return None

    # ---- the mouse and keys

    def mouseMoveEvent(self, event) -> None:
        edge = self.edge_at(event.position())
        if edge != self._hover:
            self._hover = edge
            self.setCursor(Qt.CursorShape.PointingHandCursor if edge else Qt.CursorShape.ArrowCursor)
            self.update()
            if edge:
                QToolTip.showText(event.globalPosition().toPoint(), edge_names()[edge], self)

    def leaveEvent(self, event) -> None:
        self._hover = None
        self.update()

    def mousePressEvent(self, event) -> None:
        edge = self.edge_at(event.position())
        if edge and event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.chosen.emit(edge)

    def keyPressEvent(self, event) -> None:
        edge = {
            Qt.Key.Key_Up: "top",
            Qt.Key.Key_Down: "bottom",
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_Right: "right",
        }.get(event.key())
        if edge is None:
            super().keyPressEvent(event)
        elif edge != self._value:
            self.chosen.emit(edge)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.update()

    # ---- drawing

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        text, window = palette.color(QPalette.ColorRole.WindowText), palette.color(QPalette.ColorRole.Window)
        accent = palette.color(QPalette.ColorRole.Highlight)
        screen = self.screen_rect()
        wallpaper = QLinearGradient(screen.topLeft(), screen.bottomRight())
        wallpaper.setColorAt(0, mix(window, accent, 0.35))
        wallpaper.setColorAt(1, mix(window, accent, 0.12))
        p.setPen(QPen(mix(window, text, 0.45), 1.5))
        p.setBrush(wallpaper)
        p.drawRoundedRect(screen, 7, 7)
        window_rect = screen.adjusted(
            screen.width() * 0.3, screen.height() * 0.3, -screen.width() * 0.3, -screen.height() * 0.3
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(window, text, 0.06 if window.lightness() > 128 else 0.18))
        p.drawRoundedRect(window_rect, 4, 4)
        p.setBrush(mix(window, text, 0.18))
        p.drawRoundedRect(QRectF(window_rect.left(), window_rect.top(), window_rect.width(), 7), 3, 3)
        for edge in ("top", "bottom", "left", "right"):
            chosen, hover = edge == self._value, edge == self._hover
            color = accent if chosen else mix(window, text, 0.55 if hover else 0.28)
            p.setBrush(color)
            p.drawRoundedRect(self.edge_rect(edge), 3, 3)
            if chosen:  # a few icons on the panel, so that it reads as a panel
                rect, dot = self.edge_rect(edge), QColor(palette.color(QPalette.ColorRole.HighlightedText))
                dot.setAlphaF(0.85)
                p.setBrush(dot)
                horizontal = rect.width() > rect.height()
                for i in range(3):
                    spot = rect.center() + (
                        QPointF((i - 1) * 14, 0) if horizontal else QPointF(0, (i - 1) * 14)
                    )
                    p.drawEllipse(spot, 2, 2)
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(text, 1, Qt.PenStyle.DotLine))
            p.drawRoundedRect(screen.adjusted(-1, -1, 1, 1), 8, 8)
        p.end()
