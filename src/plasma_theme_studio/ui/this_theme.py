# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The pictures of the card "This theme" of a picker, one per part, drawn from the theme's own values.

`thumbnail(kind_key, theme, size, dpr)` is the default behind `PickerPage.this_theme_thumbnail`: a page
that wants another picture overrides that method. Every function needs a QApplication and returns a
QImage of `size` logical pixels at `dpr`. They draw the PART the card stands for (a frame, a panel,
widgets, a color card), not the whole mock desktop.
"""

from __future__ import annotations

import re
from dataclasses import replace

from PySide6.QtCore import QByteArray, QCoreApplication, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer

from ..generators import kvantum, plasmastyle
from ..generators.windowframe import Look
from ..model.theme import Theme
from ..palette import ROLES
from ..pickers import colorschemes, decorations, plasmastyles
from ..pickers.base import blank, placeholder
from .preview import PreviewWidget

translate = QCoreApplication.translate

SAMPLE = QSize(260, 162)  # the widgets of the application style are made at this size and scaled


def role_colors(theme: Theme) -> dict[str, str]:
    return {role: theme.color(role).hex for role in ROLES}


def _painter(image: QImage) -> QPainter:
    painter = QPainter(image)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing
        | QPainter.RenderHint.SmoothPixmapTransform
        | QPainter.RenderHint.TextAntialiasing
    )
    return painter


# ---- window decorations ------------------------------------------------------------------------


def _window(p: QPainter, rect: QRectF, look: Look, active: bool, caption: str) -> None:
    """One window with the frame the look describes: radius, border, shadow, title bar and buttons."""
    reach = max(2, min(look.shadow, 18)) * rect.width() / 260
    strength = min(1.0, look.strength)
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    steps = 7
    for step in range(steps, 0, -1):  # a soft shadow, a little lower than the window
        grow = reach * step / steps
        alpha = strength * (120 if active else 60) * (1 - step / (steps + 1)) / steps * 2
        p.setBrush(QColor(0, 0, 0, round(min(255, alpha))))
        p.drawRoundedRect(
            rect.adjusted(-grow, -grow + reach / 3, grow, grow + reach / 3),
            look.radius + grow,
            look.radius + grow,
        )
    border = max(look.border, 0)
    outline = QColor(look.text.hex)
    outline.setAlpha(60 if active else 35)
    p.setBrush(QColor(look.window.hex))
    p.setPen(QPen(outline, max(border, 1) * 0.8))
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), look.radius, look.radius)
    bar_height = max(14.0, rect.height() * 0.2)
    clip = QPainterPath()
    clip.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), look.radius, look.radius)
    p.setClipPath(clip)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(look.header.hex if active else look.window.hex))
    p.drawRect(QRectF(rect.x(), rect.y(), rect.width(), bar_height))
    p.setClipping(False)
    text = QColor(look.text.hex)
    if not active:
        text.setAlpha(150)
    p.setPen(text)
    font = QFont()
    font.setPixelSize(max(7, round(bar_height * 0.5)))
    p.setFont(font)
    p.drawText(
        QRectF(rect.x() + 8, rect.y(), rect.width() - 56, bar_height), Qt.AlignmentFlag.AlignCenter, caption
    )
    p.setPen(Qt.PenStyle.NoPen)
    for number in range(3):  # minimize, maximize, close
        color = QColor(look.negative.hex if number == 2 else look.muted.hex)
        color.setAlpha(255 if active else 120)
        p.setBrush(color)
        p.drawEllipse(QPointF(rect.right() - 9 - number * 9, rect.y() + bar_height / 2), 2.8, 2.8)
    p.setBrush(QColor(look.accent.hex) if active else QColor(0, 0, 0, 0))
    p.drawRect(QRectF(rect.x() + rect.width() * 0.08, rect.y() + bar_height + 9, rect.width() * 0.3, 3))
    p.restore()


def decoration(theme: Theme, size: QSize, dpr: float, breeze: bool = False) -> QImage:
    """An active window in front of an inactive one, in the theme's frame. With `breeze` the frame is
    Breeze's (radius 5, one pixel border) in the theme's colors: "Breeze with your changes"."""
    look = Look.of(theme)
    if breeze:
        look = replace(look, radius=5, border=1)
    image = blank(size, dpr)
    p = _painter(image)
    frame = decorations.frame_size(size)
    inset = decorations.INSET
    back = QRectF(inset, inset - 2, frame.width(), frame.height())
    front = QRectF(
        size.width() - inset - frame.width(),
        size.height() - inset - frame.height(),
        frame.width(),
        frame.height(),
    )
    _window(p, back, look, False, "")
    _window(p, front, look, True, theme.name)
    p.end()
    return image


# ---- Plasma style -------------------------------------------------------------------------------

_STYLE_TAG = re.compile(rb'(<style[^>]*id="current-color-scheme"[^>]*>)(.*?)(</style>)', re.S)


def plasma_style(theme: Theme, size: QSize, dpr: float) -> QImage:
    """The clock of the default style on the panel background the theme makes (radius, border, opacity)."""
    radius, border, opacity = plasmastyle._look(theme)
    table = plasmastyles.table_from_roles(role_colors(theme))
    css = plasmastyles.stylesheet(table).encode()
    data = panel = plasmastyle.panel_svg(radius, border, opacity, solid=False).encode()
    data = _STYLE_TAG.sub(lambda m: m.group(1) + css + m.group(3), panel)
    frame = QSvgRenderer(QByteArray(data))
    image = blank(size, dpr)
    p = _painter(image)
    # what lies behind a panel: the wallpaper, so that a see-through panel shows
    p.fillRect(
        QRectF(0, 0, size.width(), size.height()),
        QColor(table["Colors:Selection"]["BackgroundNormal"]).darker(160),
    )
    margin = 8
    box = QRectF(margin, margin, size.width() - 2 * margin, size.height() - 2 * margin)
    drawn = frame.isValid() and plasmastyles.draw_frame(p, frame, box)
    clock = plasmastyles.find(plasmastyles.DEFAULT, "widgets/clock")
    face = plasmastyles.load(clock, css.decode()) if clock else None
    if face is not None:
        side = min(box.width(), box.height()) * 0.78
        plasmastyles.draw_clock(
            p, face, QRectF(box.center().x() - side / 2, box.center().y() - side / 2, side, side)
        )
    elif drawn:
        p.setPen(QColor(table["Colors:Window"]["ForegroundNormal"]))
        font = QFont()
        font.setPixelSize(round(box.height() * 0.4))
        p.setFont(font)
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, "12:30")
    p.end()
    return image if drawn or face is not None else placeholder(size, dpr)


# ---- application style --------------------------------------------------------------------------


def _stand_in(theme: Theme, size: QSize, dpr: float) -> QImage:
    """Buttons and a field drawn by hand in the look Kvantum would get, when it cannot be asked."""
    colors, radius, border = kvantum.look_of(theme)
    image = blank(size, dpr)
    p = _painter(image)
    window = QRectF(0.5, 0.5, size.width() - 1, size.height() - 1)
    p.setBrush(QColor(colors["window"]))
    p.setPen(QColor(0, 0, 0, 50))
    p.drawRoundedRect(window, 4, 4)
    scale = size.width() / 176
    r = min(radius * scale * 0.6, 12)
    width = max(1.0, border * scale * 0.7)
    outline = QColor(colors["text"])
    outline.setAlpha(110)

    def box(rect: QRectF, fill: str, text: str = "", accent: bool = False) -> None:
        p.setBrush(QColor(colors["accent"] if accent else fill))
        p.setPen(QPen(QColor(colors["accent"]) if accent else outline, width))
        p.drawRoundedRect(rect, r, r)
        if text:
            p.setPen(QColor("#ffffff" if accent else colors["text"]))
            font = QFont()
            font.setPixelSize(round(9 * scale))
            p.setFont(font)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    w, h = size.width(), size.height()
    box(QRectF(w * 0.08, h * 0.12, w * 0.84, h * 0.2), colors["view"])
    box(QRectF(w * 0.08, h * 0.45, w * 0.38, h * 0.2), colors["button"], "OK")
    box(QRectF(w * 0.54, h * 0.45, w * 0.38, h * 0.2), colors["button"], "OK", accent=True)
    box(QRectF(w * 0.08, h * 0.76, w * 0.84, h * 0.07), colors["button"])
    p.setBrush(QColor(colors["accent"]))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(w * 0.08, h * 0.76, w * 0.5, h * 0.07), r, r)
    p.end()
    return image


def app_style(theme: Theme, size: QSize, dpr: float) -> QImage:
    """Real widgets drawn by the Kvantum style made from the theme; a drawn stand-in without Kvantum."""
    from .style_preview import StylePreview, plugin_available

    if plugin_available():
        shown = theme.copy()
        shown.set("apps", "style", "generated")
        preview = StylePreview(shown)
        try:
            if preview.shows_sample:
                preview.resize(SAMPLE)
                preview.layout().activate()
                picture = preview.grab().toImage()
                target = QSize(round(size.width() * dpr), round(size.height() * dpr))
                picture = picture.scaled(
                    target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                image = blank(size, dpr)
                p = _painter(image)
                p.drawImage(
                    QPointF(
                        (size.width() - picture.width() / dpr) / 2,
                        (size.height() - picture.height() / dpr) / 2,
                    ),
                    picture,
                )
                p.end()
                return image
        finally:
            preview._release()
            preview.deleteLater()
    return _stand_in(theme, size, dpr)


# ---- colors -------------------------------------------------------------------------------------


def colors(theme: Theme, size: QSize, dpr: float) -> QImage:
    """The window card of a color scheme, from the theme's twelve colors."""
    return colorschemes.draw_card(plasmastyles.table_from_roles(role_colors(theme)), size, dpr)


# ---- the default ---------------------------------------------------------------------------------

DRAWERS = {
    "decoration": decoration,
    "plasma_style": plasma_style,
    "app_style": app_style,
    "color_scheme": colors,
}


def thumbnail(kind_key: str, theme: Theme, size: QSize, dpr: float) -> QImage:
    """The card of "This theme" for the picker `kind_key`; the mock desktop for a part without a drawing."""
    draw = DRAWERS.get(kind_key)
    if draw is not None:
        try:
            image = draw(theme, size, dpr)
            if not image.isNull():
                return image
        except Exception:  # noqa: BLE001, S110 - a card must never break the page
            pass
    return PreviewWidget(theme).render_image(size, dpr, "window").toImage()


def breeze_thumbnail(theme: Theme, size: QSize, dpr: float) -> QImage:
    """The card "Breeze with your changes" of the window decorations."""
    return decoration(theme, size, dpr, breeze=True)
