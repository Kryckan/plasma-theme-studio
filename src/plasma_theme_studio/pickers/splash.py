# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Splash Screen: the look-and-feel packages that have `contents/splash`, and "None".

The id is the package's folder name, which is what ksplashrc `[KSplash] Theme`
stores, or "None" for no splash screen. The picture is
`contents/previews/splash.png`, else the package's own preview.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen

from ..messages import translate
from .base import Item, Kind, blank
from .globalthemes import package_items, preview

NONE = "None"


class SplashScreens(Kind):
    key = "splash"

    @property
    def title(self) -> str:
        return str(translate("core", "Splash Screen"))

    def items(self) -> list[Item]:
        return [Item(NONE, str(translate("core", "None")))] + package_items("splash")

    def thumbnail(self, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
        if item.id == NONE and item.path is None:
            return none_card(size, dpr)
        return preview(item, size, dpr, ("splash.png", "preview.png", "preview.jpg"))


def none_card(size: QSize, dpr: float) -> QImage:
    """A dark empty screen with a struck-through circle."""
    image = blank(size, dpr)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w, h = size.width(), size.height()
    gradient = QLinearGradient(0, 0, 0, h)
    gradient.setColorAt(0, QColor("#2b3036"))
    gradient.setColorAt(1, QColor("#1b1e22"))
    p.setPen(QColor(255, 255, 255, 30))
    p.setBrush(gradient)
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 4, 4)
    radius = min(w, h) * 0.2
    center = QPointF(w / 2, h / 2)
    pen = QPen(QColor("#8b939c"), max(2.0, min(w, h) * 0.03))
    p.setPen(pen)
    p.setBrush(QColor(0, 0, 0, 0))
    p.drawEllipse(center, radius, radius)
    offset = radius * 0.7071
    p.drawLine(center + QPointF(-offset, offset), center + QPointF(offset, -offset))
    p.end()
    return image
