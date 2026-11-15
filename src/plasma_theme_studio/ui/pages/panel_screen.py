# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A small drawn screen with four edges to click: where the panels sit."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPalette, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..widgets import mix

translate = QCoreApplication.translate

SCREEN = QSize(220, 136)
SCREEN_GAP = 16
MAX_WIDTH = 420  # all the screens together, so that the page needs no sideways scroll bar
MAX_SCREENS = 3
STRIP = 10  # how thick an edge is drawn
STACK = STRIP + 3  # how far in a second panel on the same edge is drawn
REACH = 0.26  # how much of the screen a click on an edge reaches in


def edge_names() -> dict[str, str]:
    return {
        "top": translate("ui", "Top edge"),
        "bottom": translate("ui", "Bottom edge"),
        "left": translate("ui", "Left edge"),
        "right": translate("ui", "Right edge"),
    }


class ScreenChooser(QWidget):
    """The screens of the desktop with the panels on their edges. A panel is a dict with `number`,
    `location` ("top", "bottom", "left", "right") and `screen` (0 for the first). One panel is the
    chosen one: a click on another panel's strip chooses it (`picked`), a click on an edge of the
    chosen panel's screen moves the chosen panel there (`chosen`). The arrow keys move it as well, so
    it is reachable without a mouse. `value()` is the chosen panel's edge, or None."""

    chosen = Signal(str)  # the person clicked an edge or pressed an arrow key
    picked = Signal(int)  # the person clicked a panel: its number

    def __init__(self, parent=None):
        super().__init__(parent)
        self._panels: list[dict] = []
        self._cell = SCREEN
        self._selected = 1
        self._hover: tuple[int, str] | None = None  # screen index and edge
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(translate("ui", "Screen edge of the panel"))
        self.set_panels([], 1)

    # ---- what is shown

    def set_panels(self, panels: list[dict], selected: int = 1) -> None:
        self._panels = [dict(panel) for panel in panels]
        self._selected = selected
        count = len(self._screens())
        each = min(SCREEN.width(), (MAX_WIDTH - SCREEN_GAP * (count - 1)) // count)
        self._cell = QSize(each, round(SCREEN.height() * each / SCREEN.width()))
        self.setFixedSize(QSize(each * count + SCREEN_GAP * (count - 1), self._cell.height()))
        names = edge_names()
        if self._panels:
            text = "; ".join(
                translate("ui", "Panel {number}: {edge}").format(
                    number=panel["number"], edge=names.get(panel.get("location"), "?")
                )
                for panel in self._panels
            )
        else:
            text = translate("ui", "No edge chosen")
        self.setAccessibleDescription(text)
        self.update()

    def set_value(self, value: str | None) -> None:
        """One panel on the first screen, on this edge (or none)."""
        self.set_panels([{"number": 1, "location": value, "screen": 0}] if value else [], 1)

    def value(self) -> str | None:
        panel = self._chosen_panel()
        return panel.get("location") if panel else None

    def sizeHint(self) -> QSize:
        return self.size()

    def _chosen_panel(self) -> dict | None:
        return next((panel for panel in self._panels if panel["number"] == self._selected), None)

    def _screens(self) -> list[int]:
        """The screens that have a panel, at least the first one, as the numbers Plasma gives them."""
        found = sorted({int(panel.get("screen", 0)) for panel in self._panels})[:MAX_SCREENS]
        return found or [0]

    def screen_rect(self, screen: int = 0) -> QRectF:
        screens = self._screens()
        index = screens.index(screen) if screen in screens else 0
        left = index * (self._cell.width() + SCREEN_GAP)
        return QRectF(left + 1, 1, self._cell.width() - 2, self._cell.height() - 2)

    def _on_edge(self, screen: int, edge: str) -> list[dict]:
        return [
            panel
            for panel in self._panels
            if panel.get("location") == edge and int(panel.get("screen", 0)) == screen
        ]

    def edge_rect(self, edge: str, screen: int = 0, stack: int = 0) -> QRectF:
        """What is drawn for an edge; `stack` counts the panels already on it, which are further out."""
        r = self.screen_rect(screen).adjusted(5, 5, -5, -5)
        inset = stack * STACK
        return {
            "top": QRectF(r.left(), r.top() + inset, r.width(), STRIP),
            "bottom": QRectF(r.left(), r.bottom() - STRIP - inset, r.width(), STRIP),
            "left": QRectF(r.left() + inset, r.top() + STRIP + 4, STRIP, r.height() - 2 * STRIP - 8),
            "right": QRectF(
                r.right() - STRIP - inset, r.top() + STRIP + 4, STRIP, r.height() - 2 * STRIP - 8
            ),
        }[edge]

    def panel_rect(self, panel: dict) -> QRectF:
        screen = int(panel.get("screen", 0))
        stack = self._on_edge(screen, panel["location"]).index(panel)
        return self.edge_rect(panel["location"], screen, stack)

    def screen_at(self, pos: QPointF) -> int | None:
        return next((screen for screen in self._screens() if self.screen_rect(screen).contains(pos)), None)

    def edge_at(self, pos: QPointF, screen: int = 0) -> str | None:
        r = self.screen_rect(screen)
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

    def panel_at(self, pos: QPointF) -> dict | None:
        """The panel whose strip is under the point."""
        return next(
            (panel for panel in self._panels if self.panel_rect(panel).adjusted(-3, -3, 3, 3).contains(pos)),
            None,
        )

    # ---- the mouse and keys

    def _target(self, pos: QPointF) -> tuple[int, str] | None:
        screen = self.screen_at(pos)
        edge = self.edge_at(pos, screen) if screen is not None else None
        return (screen, edge) if edge else None

    def mouseMoveEvent(self, event) -> None:
        target = self._target(event.position())
        if target != self._hover:
            self._hover = target
            self.setCursor(Qt.CursorShape.PointingHandCursor if target else Qt.CursorShape.ArrowCursor)
            self.update()
            if target:
                QToolTip.showText(event.globalPosition().toPoint(), edge_names()[target[1]], self)

    def leaveEvent(self, event) -> None:
        self._hover = None
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hit = self.panel_at(event.position())
        if hit is not None and hit["number"] != self._selected:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.picked.emit(hit["number"])
            return
        target = self._target(event.position())
        mine = self._chosen_panel()
        if target and (mine is None or int(mine.get("screen", 0)) == target[0]):
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.chosen.emit(target[1])

    def keyPressEvent(self, event) -> None:
        edge = {
            Qt.Key.Key_Up: "top",
            Qt.Key.Key_Down: "bottom",
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_Right: "right",
        }.get(event.key())
        if edge is None:
            super().keyPressEvent(event)
        elif edge != self.value():
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
        several = len(self._panels) > 1
        for screen in self._screens():
            self._paint_screen(p, screen, text, window, accent, several)
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(text, 1, Qt.PenStyle.DotLine))
            focus = self.screen_rect(self._chosen_screen())
            p.drawRoundedRect(focus.adjusted(-1, -1, 1, 1), 8, 8)
        p.end()

    def _chosen_screen(self) -> int:
        panel = self._chosen_panel()
        return int(panel.get("screen", 0)) if panel else self._screens()[0]

    def _paint_screen(self, p, screen: int, text, window, accent, several: bool) -> None:
        palette = self.palette()
        rect = self.screen_rect(screen)
        wallpaper = QLinearGradient(rect.topLeft(), rect.bottomRight())
        wallpaper.setColorAt(0, mix(window, accent, 0.35))
        wallpaper.setColorAt(1, mix(window, accent, 0.12))
        p.setPen(QPen(mix(window, text, 0.45), 1.5))
        p.setBrush(wallpaper)
        p.drawRoundedRect(rect, 7, 7)
        window_rect = rect.adjusted(
            rect.width() * 0.3, rect.height() * 0.3, -rect.width() * 0.3, -rect.height() * 0.3
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(window, text, 0.06 if window.lightness() > 128 else 0.18))
        p.drawRoundedRect(window_rect, 4, 4)
        p.setBrush(mix(window, text, 0.18))
        p.drawRoundedRect(QRectF(window_rect.left(), window_rect.top(), window_rect.width(), 7), 3, 3)
        # the edge under the mouse, when nothing sits there
        if self._hover and self._hover[0] == screen and not self._on_edge(screen, self._hover[1]):
            p.setBrush(mix(window, text, 0.4))
            p.drawRoundedRect(self.edge_rect(self._hover[1], screen), 3, 3)
        if not any(int(panel.get("screen", 0)) == screen for panel in self._panels):
            return
        for panel in self._panels:
            if int(panel.get("screen", 0)) != screen or panel.get("location") not in edge_names():
                continue
            chosen = panel["number"] == self._selected
            rect = self.panel_rect(panel)
            p.setBrush(accent if chosen else mix(window, text, 0.45))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 3, 3)
            dot = QColor(
                palette.color(QPalette.ColorRole.HighlightedText if chosen else QPalette.ColorRole.Window)
            )
            dot.setAlphaF(0.9)
            p.setBrush(dot)
            horizontal = rect.width() > rect.height()
            if several:  # the number of the panel, as the list names it
                p.setPen(dot)
                font = p.font()
                font.setPixelSize(9)
                font.setBold(True)
                p.setFont(font)
                badge = QRectF(
                    rect.left() + (3 if horizontal else 0),
                    rect.top() + (0 if horizontal else 2),
                    STRIP,
                    STRIP,
                )
                p.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(panel["number"]))
                p.setPen(Qt.PenStyle.NoPen)
            for i in range(3):
                spot = rect.center() + (
                    QPointF((i - 1) * 14, 0) if horizontal else QPointF(0, (i - 1) * 14 + 8)
                )
                p.drawEllipse(spot, 2, 2)
