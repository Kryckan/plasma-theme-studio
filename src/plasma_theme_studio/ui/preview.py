# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A drawn mock desktop that shows the theme while it is being edited.

This is a simplified picture, not the real widget style. It reads the same
derived colors that are written to the color scheme.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ..generators.colorscheme import scheme_groups
from ..model.theme import MAX_PANELS, Theme, panel_section

translate = QCoreApplication.translate

# The scene is drawn in these units and scaled to fit the widget.
SCENE_W, SCENE_H = 760, 520
# The space around a floating panel, and the thickest panel the scene has room for.
PANEL_GAP = 8
MAX_PANEL_THICKNESS = 84
POPUP_ROOM = 160  # what the "Panel" view keeps free beside the panel for its popup and tooltip
PANEL_KEYS = ("location", "height", "alignment", "length_mode", "floating", "opacity_mode")


def _rgb(text: str, alpha: float = 1.0) -> QColor:
    r, g, b = (int(part) for part in text.split(","))
    color = QColor(r, g, b)
    color.setAlphaF(alpha)
    return color


MODES = ("desktop", "window", "panel", "menu")  # what the widget zooms in on
ZOOM_MARGIN = 28


class PreviewWidget(QWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.mode = "desktop"
        self.panel_layouts: list[dict] | None = None  # the panels to draw, when a page knows better
        self.setMinimumSize(420, 320)
        self.setAccessibleName(translate("preview", "Preview of the theme"))

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def set_panels(self, layouts: list[dict] | None) -> None:
        """Draw these panels, the main one first (each a dict with the keys of the theme's panel
        section), instead of what the theme says. None goes back to the theme."""
        self.panel_layouts = layouts
        self.update()

    def set_mode(self, mode: str) -> None:
        """Show the whole desktop, or zoom in on the window, the panel or the popups."""
        self.mode = mode if mode in MODES else "desktop"
        self.update()

    def view_rect(self) -> QRectF:
        """The part of the scene that is shown, in scene units."""
        scene = QRectF(0, 0, SCENE_W, SCENE_H)
        if self.mode == "desktop":
            return scene
        panel, vertical, attached = self._panel_geometry()
        if self.mode == "panel":
            edge = self._edge_rect(panel, vertical, attached)
            for other, other_vertical, other_attached in self._other_geometries():
                edge = edge.united(self._edge_rect(other, other_vertical, other_attached))
            return edge
        if self.mode == "window":
            area = self._frame_rect(panel, vertical, attached)
        else:  # the popup and its tooltip, with the panel they belong to
            popup, bubble = self._popup_rects(panel, vertical, attached)
            area = popup.united(bubble).united(panel)
        area = area.adjusted(-ZOOM_MARGIN, -ZOOM_MARGIN, ZOOM_MARGIN, ZOOM_MARGIN)
        return area.intersected(scene) if area.intersected(scene).isValid() else scene

    def _edge_rect(self, panel: QRectF, vertical: bool, attached: bool) -> QRectF:
        """The whole screen edge the panel is on, as deep as the panel, its gap and the popup that
        opens from it: the panel is seen in its real place, alignment, length and floating state."""
        gap = 0 if attached else PANEL_GAP
        depth = (panel.width() if vertical else panel.height()) + gap + POPUP_ROOM
        if vertical:
            depth = min(depth, SCENE_W)
            left = 0 if panel.left() < SCENE_W / 2 else SCENE_W - depth
            return QRectF(left, 0, depth, SCENE_H)
        depth = min(depth, SCENE_H)
        top = 0 if panel.top() < SCENE_H / 2 else SCENE_H - depth
        return QRectF(0, top, SCENE_W, depth)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        self._paint(painter, self.width(), self.height())
        painter.end()

    def render_image(self, size: QSize, ratio: float = 1.0, mode: str | None = None) -> QPixmap:
        """The scene (or one mode of it) as a picture of `size`, for the cards of the pickers."""
        pixmap = QPixmap(size * ratio)
        pixmap.setDevicePixelRatio(ratio)
        painter = QPainter(pixmap)
        shown, self.mode = self.mode, mode or self.mode
        try:
            self._paint(painter, size.width(), size.height())
        finally:
            self.mode = shown
            painter.end()
        return pixmap

    def _paint(self, painter: QPainter, width: float, height: float) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        view = self.view_rect()
        scale = min(width / view.width(), height / view.height())
        accent = QColor(self.theme.get("colors", "accent"))
        wallpaper = QLinearGradient(0, 0, width, height)
        wallpaper.setColorAt(0, accent.darker(170))
        wallpaper.setColorAt(1, accent.lighter(130))
        painter.fillRect(QRectF(0, 0, width, height), wallpaper)
        ax, ay = self._anchor(view)
        painter.translate((width - view.width() * scale) * ax, (height - view.height() * scale) * ay)
        painter.scale(scale, scale)
        painter.translate(-view.left(), -view.top())
        if self.mode == "panel":  # only the screen edge is shown, the rest of the picture is wallpaper
            painter.setClipRect(view)
        self._draw(painter)

    def _anchor(self, view: QRectF) -> tuple[float, float]:
        """Where the view sits in the widget, as fractions of the free room: the "Panel" view sits on
        the side of the picture that is the edge of the screen the panel is on."""
        if self.mode != "panel":
            return 0.5, 0.5
        at_start_x, at_start_y = view.left() <= 0, view.top() <= 0
        if view.width() < SCENE_W:  # a panel on the left or right
            return (0.0 if at_start_x else 1.0), 0.5
        return 0.5, (0.0 if at_start_y else 1.0)

    # ---- drawing -----------------------------------------------------

    def _draw(self, p: QPainter) -> None:
        theme = self.theme
        groups = {name: dict(entries) for name, entries in scheme_groups(theme)}
        window, view, button = groups["Colors:Window"], groups["Colors:View"], groups["Colors:Button"]
        header, selection = groups["Colors:Header"], groups["Colors:Selection"]
        accent = _rgb(selection["BackgroundNormal"])
        text, muted = _rgb(window["ForegroundNormal"]), _rgb(window["ForegroundInactive"])
        radius = theme.resolved("apps", "radius")
        border = theme.resolved("apps", "border_width")
        window_radius = theme.resolved("window", "radius")
        window_border = theme.resolved("window", "border_width")
        outline = _rgb(window["ForegroundNormal"], 0.22)

        def pen(color=outline, width=border):
            return QPen(color, width) if width else Qt.PenStyle.NoPen

        font = QFont(self.font())
        font.setPixelSize(13)
        p.setFont(font)

        panel, vertical, attached = self._panel_geometry()
        frame = self._frame_rect(panel, vertical, attached)

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

        # Panels: the main one first, drawn with its popups
        layouts = self._layouts()
        several = len(layouts) > 1
        for number, layout in enumerate(layouts, start=1):
            panel, vertical, attached = self._geometry(layout)
            panel_radius = min(theme.resolved("panel", "radius"), min(panel.width(), panel.height()) / 2)
            opaque = layout.get("opacity_mode") == "opaque"
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
                along = 16 + (24 if several else 0) + index * (icon + 12)
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
            if several:
                p.setPen(Qt.PenStyle.NoPen)
                badge = (
                    QRectF(panel.left() + 6, panel.top() + 3, 18, 18)
                    if not vertical
                    else QRectF(panel.left() + 3, panel.top() + 6, 18, 18)
                )
                p.setBrush(accent)
                p.drawEllipse(badge)
                p.setPen(_rgb(groups["Colors:Selection"]["ForegroundNormal"]))
                p.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(number))
            p.restore()
        panel, vertical, attached = self._panel_geometry()
        self._draw_popups(p, groups, panel, vertical, attached)

    def _draw_popups(self, p: QPainter, groups: dict, panel: QRectF, vertical: bool, attached: bool) -> None:
        """A popup (the launcher, say) and a tooltip beside the panel, drawn from the popup values."""
        theme = self.theme
        window, view, selection = groups["Colors:Window"], groups["Colors:View"], groups["Colors:Selection"]
        radius = theme.resolved("popup", "radius")
        border = theme.resolved("popup", "border_width")
        opacity = theme.resolved("popup", "opacity")
        text, muted = _rgb(window["ForegroundNormal"]), _rgb(window["ForegroundInactive"])
        outline = _rgb(window["ForegroundNormal"], 0.3)

        def surface(rect: QRectF) -> None:
            r = min(radius, min(rect.width(), rect.height()) / 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 46))
            p.drawRoundedRect(rect.translated(0, 3).adjusted(-2, -2, 2, 2), r + 2, r + 2)
            p.setBrush(_rgb(window["BackgroundNormal"], opacity))
            p.setPen(QPen(outline, border) if border else Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, r, r)

        popup, bubble = self._popup_rects(panel, vertical, attached)
        surface(popup)
        field = QRectF(popup.left() + 12, popup.top() + 12, popup.width() - 24, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_rgb(view["BackgroundNormal"]))
        p.drawRoundedRect(
            field, min(theme.resolved("apps", "radius"), 12), min(theme.resolved("apps", "radius"), 12)
        )
        p.setPen(muted)
        p.drawText(
            field.adjusted(10, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, translate("preview", "Search…")
        )
        for index, label in enumerate((translate("preview", "Files"), translate("preview", "Settings"))):
            row = QRectF(popup.left() + 8, field.bottom() + 6 + index * 22, popup.width() - 16, 20)
            if index == 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_rgb(selection["BackgroundNormal"]))
                p.drawRoundedRect(row, min(radius, 8), min(radius, 8))
                p.setPen(_rgb(selection["ForegroundNormal"]))
            else:
                p.setPen(text)
            p.drawText(row.adjusted(10, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, label)

        surface(bubble)
        p.setPen(text)
        p.drawText(bubble, Qt.AlignmentFlag.AlignCenter, translate("preview", "Tooltip"))

    def _frame_rect(self, panel: QRectF, vertical: bool, attached: bool) -> QRectF:
        """The window sits in the middle of what the panel leaves free."""
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
        for other, other_vertical, other_attached in self._other_geometries():
            other_gap = 0 if other_attached else PANEL_GAP
            if other_vertical:
                if other.left() < SCENE_W / 2:
                    free.setLeft(max(free.left(), other.right() + other_gap))
                else:
                    free.setRight(min(free.right(), other.left() - other_gap))
            elif other.top() < SCENE_H / 2:
                free.setTop(max(free.top(), other.bottom() + other_gap))
            else:
                free.setBottom(min(free.bottom(), other.top() - other_gap))
        frame = QRectF(0, 0, min(620, free.width() - 78), min(380, free.height() - 78))
        frame.moveCenter(free.center())
        return frame

    def _popup_rects(self, panel: QRectF, vertical: bool, attached: bool) -> tuple[QRectF, QRectF]:
        """Where the popup (the launcher, say) and the tooltip beside the panel are drawn."""
        gap = (0 if attached else PANEL_GAP) + 8
        size, tip = QSizeF(176, 100), QSizeF(92, 28)

        def place(box: QSizeF, along: float) -> QRectF:
            """A box on the free side of the panel, `along` the panel from its start."""
            if vertical:
                x = panel.right() + gap if panel.left() < SCENE_W / 2 else panel.left() - gap - box.width()
                y = min(max(panel.top() + along, 8), SCENE_H - box.height() - 8)
            else:
                x = min(max(panel.left() + along, 8), SCENE_W - box.width() - 8)
                y = panel.bottom() + gap if panel.top() < SCENE_H / 2 else panel.top() - gap - box.height()
            return QRectF(QPointF(x, y), box)

        return place(size, 10), place(
            tip, 10 + size.width() + 14 if not vertical else 10 + size.height() + 14
        )

    def _layouts(self) -> list[dict]:
        """The panels to draw, the main one first: what a page gave, or else the theme's own. A
        further panel is drawn when the theme sets something on it."""
        if self.panel_layouts is not None:
            return self.panel_layouts or [{}]
        layouts = [{key: self.theme.get("panel_layout", key) for key in PANEL_KEYS}]
        for number in range(2, MAX_PANELS + 1):
            section = {key: self.theme.get(panel_section(number), key) for key in PANEL_KEYS}
            if any(value is not None for value in section.values()):
                layouts.append(section)
        return layouts

    def _panel_geometry(self) -> tuple[QRectF, bool, bool]:
        """Where the main panel is drawn, whether it is vertical and whether it is
        attached to the screen edge."""
        return self._geometry(self._layouts()[0])

    def _other_geometries(self) -> list[tuple[QRectF, bool, bool]]:
        return [self._geometry(layout) for layout in self._layouts()[1:]]

    @staticmethod
    def _geometry(layout: dict) -> tuple[QRectF, bool, bool]:
        """Where a panel is drawn, whether it is vertical and whether it is
        attached to the screen edge. Settings the theme leaves alone are
        drawn as a floating panel in the middle of the bottom edge."""
        location = layout.get("location") or "bottom"
        vertical = location in ("left", "right")
        attached = layout.get("floating") is False
        gap = 0 if attached else PANEL_GAP
        thickness = min(layout.get("height") or 46, MAX_PANEL_THICKNESS)
        edge = SCENE_H if vertical else SCENE_W
        length = edge - 2 * gap if layout.get("length_mode") == "fill" else edge * 0.6
        start = {"left": gap, "right": edge - gap - length}.get(layout.get("alignment"), (edge - length) / 2)
        if vertical:
            x = gap if location == "left" else SCENE_W - gap - thickness
            return QRectF(x, start, thickness, length), True, attached
        y = gap if location == "top" else SCENE_H - gap - thickness
        return QRectF(start, y, length, thickness), False, attached
