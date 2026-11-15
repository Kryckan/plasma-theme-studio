# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing a Plasma frame from its SVG the way Plasma does: the nine parts (four corners, four
edges, the center) are cut out by their element ids and put around a rectangle, and the shadow is
nine parts around that, outside it.

The SVG may be a file somebody drew, so nothing here lets its declared size decide anything: every
part is drawn into a rectangle this module chose, on a painter the caller made. A QApplication must exist.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer

_STYLE = re.compile(r'<style\s+id="current-color-scheme"[^>]*>.*?</style>', re.DOTALL)
_CORNERS = ("topleft", "topright", "bottomleft", "bottomright")


def colored(text: str, background: str, foreground: str) -> str:
    """`text` with the colors Plasma would put into it (it inserts the color scheme into the style
    element called current-color-scheme). A file without that element is left as it is."""
    style = (
        '<style id="current-color-scheme" type="text/css">'
        f".ColorScheme-Text{{color:{foreground}}}.ColorScheme-Background{{color:{background}}}</style>"
    )
    return _STYLE.sub(lambda _match: style, text, count=1)


def renderer_for(text: str) -> QSvgRenderer | None:
    """A renderer for the SVG `text`, or None when Qt cannot read it."""
    renderer = QSvgRenderer(QByteArray(text.encode("utf-8")))
    return renderer if renderer.isValid() else None


def _size(renderer: QSvgRenderer, name: str) -> tuple[float, float]:
    if not renderer.elementExists(name):
        return 0.0, 0.0
    bounds = renderer.boundsOnElement(name)
    return max(bounds.width(), 0.0), max(bounds.height(), 0.0)


def margins(renderer: QSvgRenderer, prefix: str) -> tuple[float, float, float, float]:
    """The (left, top, right, bottom) margins the hint elements of `prefix` ("" or "shadow-") give."""
    return (
        _size(renderer, f"{prefix}hint-left-margin")[0],
        _size(renderer, f"{prefix}hint-top-margin")[1],
        _size(renderer, f"{prefix}hint-right-margin")[0],
        _size(renderer, f"{prefix}hint-bottom-margin")[1],
    )


def _nine(
    renderer: QSvgRenderer, painter: QPainter, rect: QRectF, prefix: str, center: bool
) -> tuple[float, float, float, float]:
    """Draw the parts called `prefix` + corner/edge name around `rect`. Returns the widths of the left and
    right edges and the heights of the top and bottom ones as drawn."""
    size = {name: _size(renderer, prefix + name) for name in (*_CORNERS, "top", "bottom", "left", "right")}
    left = max(size["topleft"][0], size["left"][0], size["bottomleft"][0])
    right = max(size["topright"][0], size["right"][0], size["bottomright"][0])
    top = max(size["topleft"][1], size["top"][1], size["topright"][1])
    bottom = max(size["bottomleft"][1], size["bottom"][1], size["bottomright"][1])
    fx = min(1.0, rect.width() / (left + right)) if left + right > 0 else 1.0
    fy = min(1.0, rect.height() / (top + bottom)) if top + bottom > 0 else 1.0
    left, right, top, bottom = left * fx, right * fx, top * fy, bottom * fy
    x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()
    places = {
        "topleft": QRectF(x0, y0, left, top),
        "topright": QRectF(x1 - right, y0, right, top),
        "bottomleft": QRectF(x0, y1 - bottom, left, bottom),
        "bottomright": QRectF(x1 - right, y1 - bottom, right, bottom),
        "top": QRectF(x0 + left, y0, rect.width() - left - right, top),
        "bottom": QRectF(x0 + left, y1 - bottom, rect.width() - left - right, bottom),
        "left": QRectF(x0, y0 + top, left, rect.height() - top - bottom),
        "right": QRectF(x1 - right, y0 + top, right, rect.height() - top - bottom),
    }
    if center:
        places["center"] = QRectF(
            x0 + left, y0 + top, rect.width() - left - right, rect.height() - top - bottom
        )
    for name, target in places.items():
        if target.width() > 0 and target.height() > 0 and renderer.elementExists(prefix + name):
            renderer.render(painter, prefix + name, target)
    return left, top, right, bottom


def draw_frame(
    renderer: QSvgRenderer, painter: QPainter, rect: QRectF, *, shadow: bool = True, guides: bool = False
) -> None:
    """Draw the frame inside `rect` with its shadow around it, and with `guides` the lines that show how it
    is cut: the slices (solid), the margins that keep content off the edge (dashed), the reach of the
    shadow (dotted)."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    reach = margins(renderer, "shadow-")
    if shadow:
        outer = rect.adjusted(-reach[0], -reach[1], reach[2], reach[3])
        _nine(renderer, painter, outer, "shadow-", center=False)
    left, top, right, bottom = _nine(renderer, painter, rect, "", center=True)
    if guides:
        _guides(painter, rect, (left, top, right, bottom), margins(renderer, ""), reach)
    painter.restore()


GUIDE_SLICE = QColor("#e8305a")
GUIDE_MARGIN = QColor("#1fb86b")
GUIDE_SHADOW = QColor("#f5a623")


def _line(painter: QPainter, color: QColor, style: Qt.PenStyle, a: QPointF, b: QPointF) -> None:
    pen = QPen(color, 1.0, style)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.drawLine(a, b)


def _guides(painter, rect: QRectF, slices, content, reach) -> None:
    left, top, right, bottom = slices
    xs = (rect.left() + left, rect.right() - right)
    ys = (rect.top() + top, rect.bottom() - bottom)
    for x in xs:
        _line(painter, GUIDE_SLICE, Qt.PenStyle.SolidLine, QPointF(x, rect.top()), QPointF(x, rect.bottom()))
    for y in ys:
        _line(painter, GUIDE_SLICE, Qt.PenStyle.SolidLine, QPointF(rect.left(), y), QPointF(rect.right(), y))
    inner = rect.adjusted(content[0], content[1], -content[2], -content[3])
    pen = QPen(GUIDE_MARGIN, 1.0, Qt.PenStyle.DashLine)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(inner)
    outer = rect.adjusted(-reach[0], -reach[1], reach[2], reach[3])
    pen = QPen(GUIDE_SHADOW, 1.0, Qt.PenStyle.DotLine)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.drawRect(outer)
