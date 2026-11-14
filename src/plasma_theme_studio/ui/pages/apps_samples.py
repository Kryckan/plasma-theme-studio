# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawn samples for the GTK Apps and Rofi pages: a small GTK-like window and a Rofi launcher.

Both are plain QPainter drawings made from the theme's colors and shapes; no GTK and no Rofi runs.
They are drawn on a fixed design grid of `DESIGN` pixels and scaled to the widget, so the shapes keep
their proportions at any width.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...generators import rofi
from ...model.color import readable_on
from ...model.theme import Theme

translate = QCoreApplication.translate

DESIGN = QSize(320, 232)


def _color(color, alpha: float = 1.0) -> QColor:
    result = QColor(color.hex)
    result.setAlphaF(alpha)
    return result


def parse_pango(text: str, fallback: QFont) -> tuple[str, float]:
    """The family and size of a Rofi font such as `Inter 11` (the last word is the size)."""
    words = (text or "").split()
    if len(words) >= 2:
        try:
            return " ".join(words[:-1]), float(words[-1])
        except ValueError:
            pass
    if words:
        return " ".join(words), max(fallback.pointSizeF(), 10.0)
    return fallback.family(), max(fallback.pointSizeF(), 10.0)


class _Sample(QWidget):
    """A drawing that follows a theme and keeps the shape of `DESIGN`."""

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(DESIGN.width() * 3 // 4, DESIGN.height() * 3 // 4)

    def sizeHint(self) -> QSize:
        return DESIGN

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return round(width * DESIGN.height() / DESIGN.width())

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        scale = min(self.width() / DESIGN.width(), self.height() / DESIGN.height())
        p.translate((self.width() - DESIGN.width() * scale) / 2, 0)
        p.scale(scale, scale)
        self.backdrop(p)
        self.draw(p)
        p.end()

    def backdrop(self, p: QPainter) -> None:
        """Something to be in front of: a wallpaper-like gradient from the accent color."""
        accent = self.theme.color("accent")
        gradient = QLinearGradient(0, 0, DESIGN.width(), DESIGN.height())
        gradient.setColorAt(0, _color(accent.mix(self.theme.color("window"), 0.15)))
        gradient.setColorAt(1, _color(accent.mix(self.theme.color("text"), 0.45)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawRoundedRect(QRectF(0, 0, DESIGN.width(), DESIGN.height()), 10, 10)

    def draw(self, p: QPainter) -> None:
        raise NotImplementedError

    def font_of(self, pixels: float, bold: bool = False, family: str | None = None) -> QFont:
        font = QFont(family) if family else QFont(self.font())
        font.setPixelSize(round(pixels))
        font.setBold(bold)
        return font


class GtkSample(_Sample):
    """A GTK-like window: a header bar with rounded top corners, an entry, a switch and two buttons."""

    def draw(self, p: QPainter) -> None:
        theme = self.theme
        radius = int(theme.resolved("gtk", "radius"))
        border = int(theme.resolved("gtk", "border_width"))
        corner = int(theme.resolved("gtk", "window_radius"))
        window, view, button = theme.color("window"), theme.color("view"), theme.color("button")
        header, text, accent = theme.color("header"), theme.color("text"), theme.color("accent")
        frame = QRectF(28, 26, DESIGN.width() - 56, DESIGN.height() - 52)
        corner = min(corner, frame.height() / 4)

        p.setPen(Qt.PenStyle.NoPen)
        for step in range(8, 0, -1):  # the window's shadow
            grow = step * 1.6
            p.setBrush(QColor(0, 0, 0, 9))
            p.drawRoundedRect(frame.adjusted(-grow, -grow + 4, grow, grow + 4), corner + grow, corner + grow)
        shape = QPainterPath()
        shape.addRoundedRect(frame, corner, corner)
        p.fillPath(shape, _color(window))
        bar = QRectF(frame.x(), frame.y(), frame.width(), 34)
        p.save()
        p.setClipPath(shape)
        p.fillRect(bar, _color(header))
        p.setPen(QPen(_color(text, 0.14), 1))
        p.drawLine(QPointF(bar.left(), bar.bottom()), QPointF(bar.right(), bar.bottom()))
        p.restore()
        p.setPen(QPen(_color(text, 0.25), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(frame.adjusted(0.5, 0.5, -0.5, -0.5), corner, corner)

        p.setPen(_color(text))
        p.setFont(self.font_of(13, bold=True))
        p.drawText(bar, Qt.AlignmentFlag.AlignCenter, translate("ui", "Window"))
        close = QRectF(bar.right() - 28, bar.center().y() - 9, 18, 18)  # the close button
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_color(text, 0.12))
        p.drawEllipse(close)
        p.setPen(QPen(_color(text), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        c = close.center()
        p.drawLine(QPointF(c.x() - 3.5, c.y() - 3.5), QPointF(c.x() + 3.5, c.y() + 3.5))
        p.drawLine(QPointF(c.x() - 3.5, c.y() + 3.5), QPointF(c.x() + 3.5, c.y() - 3.5))

        left, right = frame.left() + 18, frame.right() - 18
        # an entry
        entry = QRectF(left, bar.bottom() + 20, right - left, 30)
        p.setBrush(_color(view))
        p.setPen(QPen(_color(accent), max(border, 1)) if border else QPen(_color(text, 0.2), 1))
        inset = max(border, 1) / 2
        p.drawRoundedRect(entry.adjusted(inset, inset, -inset, -inset), radius, radius)
        p.setPen(_color(text))
        p.setFont(self.font_of(13))
        p.drawText(
            entry.adjusted(10, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, translate("ui", "Sample text")
        )
        # a switch with its label
        row = QRectF(left, entry.bottom() + 18, right - left, 24)
        track = QRectF(right - 46, row.y(), 46, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_color(accent))
        p.drawRoundedRect(track, 12, 12)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(track.right() - 22, track.y() + 2, 20, 20))
        p.setPen(_color(text))
        p.drawText(row.adjusted(0, 0, -56, 0), Qt.AlignmentFlag.AlignVCenter, translate("ui", "Switch"))
        # two buttons
        top = frame.bottom() - 18 - 30
        width = (right - left - 12) / 2
        cancel, ok = QRectF(left, top, width, 30), QRectF(left + width + 12, top, width, 30)
        p.setBrush(_color(button))
        p.setPen(QPen(_color(text, 0.3), max(border, 1)))
        p.drawRoundedRect(cancel.adjusted(inset, inset, -inset, -inset), radius, radius)
        p.setPen(_color(text))
        p.drawText(cancel, Qt.AlignmentFlag.AlignCenter, translate("ui", "Cancel"))
        p.setBrush(_color(accent))
        p.setPen(QPen(_color(accent), max(border, 1)))
        p.drawRoundedRect(ok.adjusted(inset, inset, -inset, -inset), radius, radius)
        p.setPen(_color(readable_on(accent)))
        p.setFont(self.font_of(13, bold=True))
        p.drawText(ok, Qt.AlignmentFlag.AlignCenter, translate("ui", "OK"))


class RofiSample(_Sample):
    """A Rofi launcher: an input line and a list with one selected row."""

    def draw(self, p: QPainter) -> None:
        theme = self.theme
        radius = int(theme.resolved("rofi", "radius"))
        border = int(theme.resolved("rofi", "border_width"))
        opacity = float(theme.get("rofi", "opacity"))
        window, view, text = theme.color("window"), theme.color("view"), theme.color("text")
        accent, muted = theme.color("accent"), theme.color("text_muted")
        alt = view.mix(text, 0.06)
        text = rofi.ensure_contrast(text, [window, view, alt])
        muted = rofi.ensure_contrast(muted, [window, view])
        prompt = rofi.ensure_contrast(accent, [view])
        on_accent = rofi.ensure_contrast(readable_on(accent), [accent])
        family, points = parse_pango(theme.get("rofi", "font") or "", self.font())
        pixels = max(11.0, min(18.0, points * 1.3))
        font = self.font_of(pixels, family=family)

        box = QRectF(34, 30, DESIGN.width() - 68, DESIGN.height() - 60)
        radius = min(radius, 40)
        for step in range(7, 0, -1):  # a faint shadow
            grow = step * 1.5
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 10))
            p.drawRoundedRect(box.adjusted(-grow, -grow + 4, grow, grow + 4), radius + grow, radius + grow)
        edge = max(border, 0)
        # the window: a translucent background and an accent border
        p.setBrush(_color(window, opacity))
        p.setPen(QPen(_color(accent), edge) if edge else Qt.PenStyle.NoPen)
        half = edge / 2
        p.drawRoundedRect(box.adjusted(half, half, -half, -half), radius, radius)
        inner = box.adjusted(edge + 12, edge + 12, -edge - 12, -edge - 12)
        inner_radius = max(0, radius - edge - 6)

        p.setFont(font)
        input_row = QRectF(inner.x(), inner.y(), inner.width(), pixels + 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_color(view))
        p.drawRoundedRect(
            input_row, min(inner_radius, input_row.height() / 2), min(inner_radius, input_row.height() / 2)
        )
        p.setPen(_color(prompt))
        p.drawText(input_row.adjusted(10, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, translate("ui", "Run:"))
        advance = p.fontMetrics().horizontalAdvance(translate("ui", "Run:") + " ")
        p.setPen(_color(text))
        p.drawText(input_row.adjusted(10 + advance, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, "fi")

        names = (
            translate("ui", "Files"),
            translate("ui", "Firefox"),
            translate("ui", "Image viewer"),
            translate("ui", "Fixed width terminal"),
        )
        top = input_row.bottom() + 10
        step = pixels + 14
        for index, name in enumerate(names):
            row = QRectF(inner.x(), top + index * step, inner.width(), step)
            if row.bottom() > inner.bottom() - 18:
                break
            selected = index == 1
            if selected:
                p.setBrush(_color(accent))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(row, min(inner_radius, 8), min(inner_radius, 8))
            elif index % 2:
                p.setBrush(_color(alt))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(row, min(inner_radius, 8), min(inner_radius, 8))
            p.setPen(_color(on_accent if selected else text))
            p.drawText(row.adjusted(10, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, name)
        p.setPen(_color(muted))
        p.setFont(self.font_of(11, family=family))
        p.drawText(
            QRectF(inner.x(), inner.bottom() - 16, inner.width(), 16),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            translate("ui", "4 results"),
        )
