# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Plasma Style: the packages in `plasma/desktoptheme/<name>/`.

The name is what plasmarc `[Theme] name` stores. A style *follows the color
scheme* when it has no `colors` file (the rule of System Settings): its SVGs
are then colored with the active scheme. A style with a `colors` file always
uses those colors. Files a style lacks come from the `default` style, as in
Plasma.

The card is the style's dialog background as a nine-slice frame with its
analog clock on top. The clock's hands are placed the way Plasma's analog clock
applet does (`Hand.qml`): the hand's picture is as large as its element, its
rotation center is the center of the picture (or the position of a
`hint-*-rotation-center-offset` element when the style has one), and that
point sits on the center of the face.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize
from PySide6.QtGui import QColor, QImage, QPainter

from ..messages import translate
from .base import Item, Kind, blank, installed, placeholder, read_metadata, read_svg, unique_sorted
from .colorschemes import BREEZE, lookup, parse_color, read_table

DEFAULT = "default"

# KSvg's color sets: class prefix -> color group.
_SETS = {
    "": "Colors:Window",
    "Button": "Colors:Button",
    "View": "Colors:View",
    "Complementary": "Colors:Complementary",
    "ToolTip": "Colors:Tooltip",
    "Header": "Colors:Header",
}


def _styles() -> dict[str, tuple[Path, bool]]:
    return installed("plasma", "desktoptheme")


def style_folder(name: str) -> Path | None:
    found = _styles().get(name)
    return found[0] if found else None


def find(name: str, relative: str) -> Path | None:
    """`relative` (like "widgets/clock", without extension) in the style, else in `default`."""
    for style in (name, DEFAULT):
        folder = style_folder(style)
        if folder is not None:
            for extension in (".svgz", ".svg"):
                if (folder / (relative + extension)).is_file():
                    return folder / (relative + extension)
    return None


class PlasmaStyles(Kind):
    key = "plasma_style"
    scheme_dependent = True  # the colors matter for the styles that follow the scheme

    @property
    def title(self) -> str:
        return str(translate("core", "Plasma Style"))

    def items(self) -> list[Item]:
        found = []
        for name, (folder, user) in _styles().items():
            try:
                meta = read_metadata(folder)
                follows = not (folder / "colors").is_file()
            except Exception:
                continue
            if meta is None:
                continue
            description = str(translate("core", "Follows color scheme")) if follows else meta["description"]
            found.append(
                Item(
                    name,
                    meta["name"] or name,
                    description,
                    folder,
                    user,
                    {"follows_color_scheme": follows, "author": meta["author"]},
                )
            )
        return unique_sorted(found)

    def thumbnail(self, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
        if item.path is None:
            return QImage()
        try:
            return draw_style(item, size, dpr, colors)
        except (OSError, ValueError):
            return QImage()


# Colors ------------------------------------------------------------------


def table_from_roles(colors: Mapping[str, str] | None) -> dict[str, dict[str, QColor]]:
    """A color table (as `colorschemes.read_table` gives) from the theme's
    twelve roles; Breeze Light where `colors` is None or lacks a role."""
    colors = colors or {}

    def role(name: str, fallback: tuple[str, str]) -> QColor:
        return parse_color(colors.get(name, "")) or parse_color(BREEZE[fallback])

    accent = role("accent", ("Colors:Selection", "BackgroundNormal"))
    window = role("window", ("Colors:Window", "BackgroundNormal"))
    text = role("text", ("Colors:Window", "ForegroundNormal"))
    base = {
        "ForegroundNormal": text,
        "ForegroundInactive": role("text_muted", ("Colors:Window", "ForegroundInactive")),
        "ForegroundLink": role("link", ("Colors:Window", "ForegroundLink")),
        "ForegroundVisited": role("visited", ("Colors:Window", "ForegroundVisited")),
        "ForegroundNegative": role("negative", ("Colors:Window", "ForegroundNegative")),
        "ForegroundNeutral": role("neutral", ("Colors:Window", "ForegroundNeutral")),
        "ForegroundPositive": role("positive", ("Colors:Window", "ForegroundPositive")),
        "DecorationFocus": accent,
        "DecorationHover": accent,
    }
    highlighted = QColor("#fcfcfc") if accent.lightness() < 160 else QColor("#232629")
    return {
        "Colors:Window": {**base, "BackgroundNormal": window},
        "Colors:View": {**base, "BackgroundNormal": role("view", ("Colors:View", "BackgroundNormal"))},
        "Colors:Button": {**base, "BackgroundNormal": role("button", ("Colors:Button", "BackgroundNormal"))},
        "Colors:Header": {**base, "BackgroundNormal": role("header", ("Colors:Window", "BackgroundNormal"))},
        "Colors:Tooltip": {**base, "BackgroundNormal": window},
        "Colors:Complementary": {**base, "BackgroundNormal": window},
        "Colors:Selection": {"BackgroundNormal": accent, "ForegroundNormal": highlighted},
    }


def stylesheet(table: Mapping[str, Mapping[str, QColor]]) -> str:
    """The `.ColorScheme-*` rules KSvg puts into a style's `current-color-scheme` element."""
    rules = []

    def add(name: str, color: QColor) -> None:
        rules.append(f".ColorScheme-{name} {{ color:{color.name()}; }}")

    for prefix, group in _SETS.items():

        def get(key: str, group: str = group) -> QColor:
            found = table.get(group, {}).get(key)
            return QColor(found) if found is not None else lookup(table, "Colors:Window", key)

        add(prefix + "Text", get("ForegroundNormal"))
        add(prefix + "Background", get("BackgroundNormal"))
        add(prefix + "Hover", get("DecorationHover"))
        add(prefix + "Focus", get("DecorationFocus"))
        add(prefix + "DisabledText", get("ForegroundInactive"))
        for role in ("Positive", "Neutral", "Negative"):
            add(f"{prefix}{role}Text", get(f"Foreground{role}"))
    add("Highlight", lookup(table, "Colors:Selection", "BackgroundNormal"))
    add("HighlightedText", lookup(table, "Colors:Selection", "ForegroundNormal"))
    return "\n".join(rules)


_STYLE = re.compile(rb'(<style[^>]*id="current-color-scheme"[^>]*>)(.*?)(</style>)', re.S)


@lru_cache(maxsize=32)
def _renderer(path: str, mtime: int, css: str):
    """The SVG at `path` with its color stylesheet replaced; None when it is not usable."""
    from PySide6.QtSvg import QSvgRenderer

    data = read_svg(Path(path))
    if data is None:
        return None
    data = _STYLE.sub(lambda m: m.group(1) + b"\n" + css.encode() + b"\n" + m.group(3), data)
    renderer = QSvgRenderer(QByteArray(data))
    return renderer if renderer.isValid() else None


def load(path: Path, css: str):
    try:
        return _renderer(str(path), path.stat().st_mtime_ns, css)
    except OSError:
        return None


# Drawing -----------------------------------------------------------------


def draw_frame(p: QPainter, svg, rect: QRectF) -> bool:
    """A nine-slice frame from the elements topleft, top, ... center; False when the SVG has none."""
    parts = {
        name: svg.boundsOnElement(name)
        for name in ("topleft", "topright", "bottomleft", "bottomright")
        if svg.elementExists(name)
    }
    if len(parts) < 4:
        return False
    left, top = parts["topleft"].width(), parts["topleft"].height()
    right, bottom = parts["topright"].width(), parts["bottomleft"].height()
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    pieces = {
        "center": QRectF(x + left, y + top, w - left - right, h - top - bottom),
        "top": QRectF(x + left, y, w - left - right, top),
        "bottom": QRectF(x + left, y + h - bottom, w - left - right, bottom),
        "left": QRectF(x, y + top, left, h - top - bottom),
        "right": QRectF(x + w - right, y + top, right, h - top - bottom),
        "topleft": QRectF(x, y, left, top),
        "topright": QRectF(x + w - right, y, right, top),
        "bottomleft": QRectF(x, y + h - bottom, left, bottom),
        "bottomright": QRectF(x + w - right, y + h - bottom, right, bottom),
    }
    for name, target in pieces.items():
        if svg.elementExists(name) and target.width() > 0 and target.height() > 0:
            svg.render(p, name, target)
    return True


def _hint_size(svg, name: str):
    return svg.boundsOnElement(name) if svg.elementExists(name) else None


def draw_clock(p: QPainter, svg, rect: QRectF, hours: int = 10, minutes: int = 8) -> None:
    """The analog clock of a style's `widgets/clock` in `rect` (a square), as Plasma's applet lays it out."""
    if not svg.elementExists("ClockFace"):
        return
    face = svg.boundsOnElement("ClockFace")
    side = min(rect.width(), rect.height())
    scale = side / face.width()
    center = rect.center()
    p.save()
    svg.render(p, "ClockFace", QRectF(center.x() - side / 2, center.y() - side / 2, side, side))
    # Shadows are moved away from the light by the hint elements (in svg units, as Plasma does).
    shadow_dx = shadow_dy = 0.0
    for name, dx, dy in (
        ("hint-hands-shadow-offset-to-west", -1, 0),
        ("hint-hands-shadow-offset-to-east", 1, 0),
        ("hint-hands-shadow-offset-to-north", 0, -1),
        ("hint-hands-shadow-offset-to-south", 0, 1),
    ):
        hint = _hint_size(svg, name)
        if hint is not None:
            shadow_dx += dx * hint.width()
            shadow_dy += dy * hint.height()
    hands = (
        ("Hour", 180 + (hours % 12 + minutes / 60) * 30),
        ("Minute", 180 + minutes * 6),
    )
    for base, angle in hands:
        for name, offset in ((base + "HandShadow", True), (base + "Hand", False)):
            if not svg.elementExists(name):
                continue
            bounds = svg.boundsOnElement(name)
            w = round(bounds.width() * scale)
            w += w % 2
            h = round(bounds.height() * scale)
            h += w % 2
            pivot_x, pivot_y = w / 2, w / 2  # Plasma's fallback; hands are drawn symmetric about it
            hint = _hint_size(
                svg, f"hint-{base.lower()}{'handshadow' if offset else 'hand'}-rotation-center-offset"
            )
            if hint is not None:
                pivot_x = round((hint.center().x() - bounds.x()) * scale)
                pivot_x += pivot_x % 2
                pivot_y = round((hint.center().y() - bounds.y()) * scale) + w % 2
            left = center.x() - pivot_x + (shadow_dx if offset else 0)
            top = center.y() - pivot_y + (shadow_dy if offset else 0)
            p.save()
            p.translate(left + pivot_x, top + pivot_y)
            p.rotate(angle)
            svg.render(p, name, QRectF(-pivot_x, -pivot_y, w, h))
            p.restore()
    if svg.elementExists("HandCenterScrew"):
        b = svg.boundsOnElement("HandCenterScrew")
        w, h = b.width() * scale, b.height() * scale
        svg.render(p, "HandCenterScrew", QRectF(center.x() - w / 2, center.y() - h / 2, w, h))
    p.restore()


def draw_style(item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
    """The card of a style item, colored by its own `colors` file or else by `colors`."""
    folder = Path(item.path)
    own = folder / "colors"
    table = read_table(own) if own.is_file() else table_from_roles(colors)
    css = stylesheet(table)
    background = find(item.id, "dialogs/background") or find(item.id, "widgets/background")
    clock = find(item.id, "widgets/clock")
    image = blank(size, dpr)
    p = QPainter(image)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    drawn = False
    frame = load(background, css) if background else None
    margin = 4
    if frame is not None:
        drawn = draw_frame(
            p, frame, QRectF(margin, margin, size.width() - 2 * margin, size.height() - 2 * margin)
        )
    face = load(clock, css) if clock else None
    if face is not None:
        side = min(size.width(), size.height()) * 0.84
        draw_clock(p, face, QRectF((size.width() - side) / 2, (size.height() - side) / 2, side, side))
        drawn = True
    p.end()
    return image if drawn else placeholder(size, dpr)
