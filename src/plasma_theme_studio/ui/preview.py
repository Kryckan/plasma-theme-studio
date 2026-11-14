# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A drawn mock desktop that shows the theme while it is being edited.

This is a simplified picture, not the real widget style. It reads the same
derived colors that are written to the color scheme.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..generators.colorscheme import scheme_groups
from ..model.theme import Theme

translate = QCoreApplication.translate

# The scene is drawn in these units and scaled to fit the widget.
SCENE_W, SCENE_H = 760, 520
# The space around a floating panel, and the thickest panel the scene has room for.
PANEL_GAP = 8
MAX_PANEL_THICKNESS = 84
PANEL_KEYS = ("location", "height", "alignment", "length_mode", "floating")


def _rgb(text: str, alpha: float = 1.0) -> QColor:
    r, g, b = (int(part) for part in text.split(","))
    color = QColor(r, g, b)
    color.setAlphaF(alpha)
    return color


class PreviewWidget(QWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setMinimumSize(380, 260)

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / SCENE_W, self.height() / SCENE_H)
        accent = QColor(self.theme.get("colors", "accent"))
        wallpaper = QLinearGradient(0, 0, self.width(), self.height())
        wallpaper.setColorAt(0, accent.darker(170))
        wallpaper.setColorAt(1, accent.lighter(130))
        painter.fillRect(self.rect(), wallpaper)
        painter.translate((self.width() - SCENE_W * scale) / 2, (self.height() - SCENE_H * scale) / 2)
        painter.scale(scale, scale)
        self._draw(painter)
        painter.end()

    # ---- drawing -----------------------------------------------------

    def _draw(self, p: QPainter) -> None:
        theme = self.theme
        groups = {name: dict(entries) for name, entries in scheme_groups(theme)}
        window, view, button = groups["Colors:Window"], groups["Colors:View"], groups["Colors:Button"]
        header, selection = groups["Colors:Header"], groups["Colors:Selection"]
        accent = _rgb(selection["BackgroundNormal"])
        text, muted = _rgb(window["ForegroundNormal"]), _rgb(window["ForegroundInactive"])
        radius = theme.get("shape", "radius")
        border = theme.get("shape", "border_width")
        window_radius = theme.resolved("window", "radius")
        window_border = theme.resolved("window", "border_width")
        outline = _rgb(window["ForegroundNormal"], 0.22)

        def pen(color=outline, width=border):
            return QPen(color, width) if width else Qt.PenStyle.NoPen

        font = QFont(self.font())
        font.setPixelSize(13)
        p.setFont(font)

        panel, vertical, attached = self._panel_geometry()
        # The window sits in the middle of what the panel leaves free.
        free = QRectF(0, 0, SCENE_W, SCENE_H)
        gap = 0 if attached else PANEL_GAP
        if vertical:
            free.setLeft(panel.right() + gap) if panel.left() < SCENE_W / 2 else free.setRight(
                panel.left() - gap
            )
        else:
            free.setTop(panel.bottom() + gap) if panel.top() < SCENE_H / 2 else free.setBottom(
                panel.top() - gap
            )
        frame = QRectF(0, 0, min(620, free.width() - 78), min(380, free.height() - 78))
        frame.moveCenter(free.center())

        # Window shadow
        size, strength = theme.get("shadow", "size"), theme.get("shadow", "strength")
        p.setPen(Qt.PenStyle.NoPen)
        for step in range(size, 0, -2):
            fade = (1 - step / size) ** 2
            p.setBrush(QColor(0, 0, 0, round(255 * strength * fade * 0.16)))
            grown = frame.adjusted(-step, -step + size * 0.25, step, step + size * 0.25)
            p.drawRoundedRect(grown, window_radius + step, window_radius + step)

        # Window body, clipped to its rounded outline
        shape = QPainterPath()
        shape.addRoundedRect(frame, window_radius, window_radius)
        p.save()
        p.setClipPath(shape, Qt.ClipOperation.IntersectClip)
        p.fillRect(frame, _rgb(window["BackgroundNormal"]))
        title = QRectF(frame.left(), frame.top(), frame.width(), 36)
        p.fillRect(title, _rgb(header["BackgroundNormal"]))
        sidebar = QRectF(frame.left(), title.bottom(), 170, frame.height() - 36)
        content = QRectF(sidebar.right(), title.bottom(), frame.width() - 170, frame.height() - 36)
        p.fillRect(content.adjusted(16, 16, -16, -150), _rgb(view["BackgroundNormal"]))
        p.restore()

        p.setPen(_rgb(header["ForegroundNormal"]))
        bold = QFont(font)
        bold.setBold(True)
        p.setFont(bold)
        p.drawText(title, Qt.AlignmentFlag.AlignCenter, theme.name)
        p.setFont(font)
        for index, color in enumerate(("ForegroundNegative", "ForegroundNeutral", "ForegroundPositive")):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_rgb(window[color]))
            p.drawEllipse(QPointF(title.right() - 20 - index * 22, title.center().y()), 6, 6)

        # Sidebar list with one selected row
        rows = (
            translate("preview", "Home"),
            translate("preview", "Documents"),
            translate("preview", "Pictures"),
            translate("preview", "Downloads"),
        )
        for index, label in enumerate(rows):
            row = QRectF(sidebar.left() + 8, sidebar.top() + 10 + index * 32, sidebar.width() - 16, 28)
            if index == 1:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(accent)
                p.drawRoundedRect(row, min(radius, 14), min(radius, 14))
                p.setPen(_rgb(selection["ForegroundNormal"]))
            else:
                p.setPen(text)
            p.drawText(row.adjusted(12, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, label)
        p.setPen(pen())
        p.drawLine(sidebar.topRight(), sidebar.bottomRight())

        # View with text samples
        sheet = content.adjusted(16, 16, -16, -150)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen())
        p.drawRoundedRect(sheet, min(radius, 12), min(radius, 12))
        stripe = QRectF(sheet.left() + 1, sheet.top() + 44, sheet.width() - 2, 26)
        p.fillRect(stripe, _rgb(view["BackgroundAlternate"]))
        samples = (
            (translate("preview", "Normal text in a view"), view["ForegroundNormal"]),
            (translate("preview", "Secondary text on an alternate row"), view["ForegroundInactive"]),
            (translate("preview", "A link"), view["ForegroundLink"]),
            (translate("preview", "A visited link"), view["ForegroundVisited"]),
        )
        for index, (label, color) in enumerate(samples):
            p.setPen(_rgb(color))
            line = QRectF(sheet.left() + 14, sheet.top() + 18 + index * 26, sheet.width() - 28, 26)
            p.drawText(line, Qt.AlignmentFlag.AlignVCenter, label)

        # Status chips
        chips = (
            (translate("preview", "Positive"), window["ForegroundPositive"]),
            (translate("preview", "Neutral"), window["ForegroundNeutral"]),
            (translate("preview", "Negative"), window["ForegroundNegative"]),
        )
        x = content.left() + 16
        for label, color in chips:
            width = p.fontMetrics().horizontalAdvance(label) + 24
            chip = QRectF(x, sheet.bottom() + 14, width, 24)
            p.setPen(pen(_rgb(color), max(border, 1)))
            p.setBrush(_rgb(color, 0.16))
            p.drawRoundedRect(chip, min(radius, 12), min(radius, 12))
            p.setPen(text)
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, label)
            x += width + 8

        # Progress bar and check box
        bar = QRectF(content.left() + 16, sheet.bottom() + 54, 200, 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(outline)
        p.drawRoundedRect(bar, 4, 4)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * 0.6, bar.height()), 4, 4)
        box = QRectF(bar.right() + 24, bar.center().y() - 9, 18, 18)
        p.drawRoundedRect(box, min(radius, 5), min(radius, 5))
        p.setPen(QPen(_rgb(selection["ForegroundNormal"]), 2))
        p.drawPolyline(
            [box.topLeft() + QPointF(4, 9), box.topLeft() + QPointF(8, 13), box.topLeft() + QPointF(14, 5)]
        )
        p.setPen(muted)
        p.drawText(
            QRectF(box.right() + 8, box.top(), 160, 18),
            Qt.AlignmentFlag.AlignVCenter,
            translate("preview", "A check box"),
        )

        # Buttons: a normal one and the focused default one
        labels = (translate("preview", "Cancel"), translate("preview", "OK"))
        x = content.right() - 16
        for index, label in enumerate(reversed(labels)):
            rect = QRectF(x - 92, frame.bottom() - 48, 92, 32)
            focused = index == 0
            p.setBrush(_rgb(button["BackgroundAlternate"] if focused else button["BackgroundNormal"]))
            p.setPen(QPen(accent, max(border, 1)) if focused else pen())
            p.drawRoundedRect(rect, min(radius, 16), min(radius, 16))
            p.setPen(_rgb(button["ForegroundNormal"]))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
            x -= 100

        # Window outline
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen(width=window_border))
        p.drawRoundedRect(frame, window_radius, window_radius)

        # Panel
        panel_radius = min(theme.resolved("panel", "radius"), min(panel.width(), panel.height()) / 2)
        opaque = theme.get("panel_layout", "opacity_mode") == "opaque"
        p.save()
        p.setClipRect(QRectF(0, 0, SCENE_W, SCENE_H))
        p.setPen(pen(width=theme.resolved("panel", "border_width")))
        p.setBrush(_rgb(window["BackgroundNormal"], 1.0 if opaque else theme.get("panel", "opacity")))
        # A panel attached to the screen edge has no corners there: they are drawn off screen.
        out = panel_radius + 4 if attached else 0
        edges = (
            -out if panel.left() <= 0 else 0,
            -out if panel.top() <= 0 else 0,
            out if panel.right() >= SCENE_W else 0,
            out if panel.bottom() >= SCENE_H else 0,
        )
        p.drawRoundedRect(panel.adjusted(*edges), panel_radius, panel_radius)
        p.setPen(Qt.PenStyle.NoPen)
        icon = max(min(26.0, (panel.width() if vertical else panel.height()) - 12), 8.0)
        for index in range(6):
            p.setBrush(accent if index == 0 else muted)
            along = 16 + index * (icon + 12)
            across = ((panel.width() if vertical else panel.height()) - icon) / 2
            corner = panel.topLeft() + (QPointF(across, along) if vertical else QPointF(along, across))
            p.drawRoundedRect(
                QRectF(corner.x(), corner.y(), icon, icon), min(radius, icon / 2), min(radius, icon / 2)
            )
        p.setPen(text)
        if vertical:
            clock = QRectF(panel.left(), panel.bottom() - 34, panel.width(), 24)
            p.drawText(clock, Qt.AlignmentFlag.AlignCenter, "12:00")
        else:
            clock = panel.adjusted(0, 0, -18, 0)
            p.drawText(clock, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, "12:00")
        p.restore()

    def _panel_geometry(self) -> tuple[QRectF, bool, bool]:
        """Where the panel is drawn, whether it is vertical and whether it is
        attached to the screen edge. Settings the theme leaves alone are
        drawn as a floating panel in the middle of the bottom edge."""
        layout = {key: self.theme.get("panel_layout", key) for key in PANEL_KEYS}
        location = layout["location"] or "bottom"
        vertical = location in ("left", "right")
        attached = layout["floating"] is False
        gap = 0 if attached else PANEL_GAP
        thickness = min(layout["height"] or 46, MAX_PANEL_THICKNESS)
        edge = SCENE_H if vertical else SCENE_W
        length = edge - 2 * gap if layout["length_mode"] == "fill" else edge * 0.6
        start = {"left": gap, "right": edge - gap - length}.get(layout["alignment"], (edge - length) / 2)
        if vertical:
            x = gap if location == "left" else SCENE_W - gap - thickness
            return QRectF(x, start, thickness, length), True, attached
        y = gap if location == "top" else SCENE_H - gap - thickness
        return QRectF(start, y, length, thickness), False, attached
