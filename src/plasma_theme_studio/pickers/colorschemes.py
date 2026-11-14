# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Colors: the installed color schemes, drawn the way System Settings draws them.

The list is what `library.installed_schemes()` finds, except that only regular
files of a sane size are opened. The card is a small window:
an active title bar with its title, window text, a link and a visited link, a
disabled text, a view with a highlighted row, and a button. All colors are read
from the `.colors` file itself (the library keeps only twelve of them); a key
the file lacks takes the value of Breeze Light.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath

from .. import library, paths
from ..messages import translate
from .base import MAX_FILE, Item, Kind, blank, languages, localized, read_ini, read_regular, unique_sorted

# Breeze Light, for what a file leaves out: {(group, key): "r,g,b"}.
BREEZE = {
    ("Colors:Window", "BackgroundNormal"): "239,240,241",
    ("Colors:Window", "ForegroundNormal"): "35,38,41",
    ("Colors:Window", "ForegroundInactive"): "112,111,110",
    ("Colors:Window", "ForegroundLink"): "41,128,185",
    ("Colors:Window", "ForegroundVisited"): "127,140,141",
    ("Colors:Window", "ForegroundNegative"): "218,68,83",
    ("Colors:Window", "ForegroundNeutral"): "246,116,0",
    ("Colors:Window", "ForegroundPositive"): "39,174,96",
    ("Colors:Window", "DecorationFocus"): "61,174,233",
    ("Colors:Window", "DecorationHover"): "147,206,233",
    ("Colors:View", "BackgroundNormal"): "252,252,252",
    ("Colors:View", "ForegroundNormal"): "35,38,41",
    ("Colors:Button", "BackgroundNormal"): "252,252,252",
    ("Colors:Button", "ForegroundNormal"): "35,38,41",
    ("Colors:Button", "DecorationFocus"): "61,174,233",
    ("Colors:Selection", "BackgroundNormal"): "61,174,233",
    ("Colors:Selection", "ForegroundNormal"): "252,252,252",
    ("WM", "activeBackground"): "227,229,231",
    ("WM", "activeForeground"): "35,38,41",
}


def parse_color(value: str) -> QColor | None:
    """ "r,g,b" or "#rrggbb" as a QColor; None when it is neither."""
    value = value.strip()
    if value.startswith("#"):
        color = QColor(value[:7])
        return color if color.isValid() else None
    try:
        r, g, b = (int(part) for part in value.split(",")[:3])
    except ValueError:
        return None
    if all(0 <= channel <= 255 for channel in (r, g, b)):
        return QColor(r, g, b)
    return None


def read_table(path: Path) -> dict[str, dict[str, QColor]]:
    """{group: {key: QColor}} of a color scheme file; keys that are not colors are left out."""
    table: dict[str, dict[str, QColor]] = {}
    for group, entries in read_ini(path).items():
        colors = {key: c for key, value in entries.items() if (c := parse_color(value)) is not None}
        if colors:
            table[group] = colors
    return table


def lookup(table: Mapping[str, Mapping[str, QColor]], group: str, key: str) -> QColor:
    """A color of the table, or the Breeze Light one."""
    found = table.get(group, {}).get(key)
    return (
        QColor(found)
        if found is not None
        else parse_color(BREEZE.get((group, key)) or BREEZE[("Colors:Window", key)])
    )


def title_bar_colors(table: Mapping[str, Mapping[str, QColor]]) -> tuple[QColor, QColor]:
    """Background and text of an active title bar: the scheme's `WM` colors, else its header."""
    wm = table.get("WM", {})
    if "activeBackground" in wm and "activeForeground" in wm:
        return QColor(wm["activeBackground"]), QColor(wm["activeForeground"])
    header = table.get("Colors:Header", {})
    if "BackgroundNormal" in header and "ForegroundNormal" in header:
        return QColor(header["BackgroundNormal"]), QColor(header["ForegroundNormal"])
    return lookup(table, "WM", "activeBackground"), lookup(table, "WM", "activeForeground")


def installed_schemes() -> list[library.InstalledScheme]:
    """`library.installed_schemes()` without its trust in the files: a `.colors` that is a pipe
    or a link to /dev/zero would block or fill the memory, so only a regular file of
    at most MAX_FILE bytes is read."""
    found: dict[str, library.InstalledScheme] = {}
    folders = [(paths.color_schemes_dir(), True)]
    folders += [(directory / "color-schemes", False) for directory in paths.system_data_dirs()]
    for folder, in_home in folders:
        try:
            files = sorted(folder.glob("*.colors"))
        except OSError:
            continue
        for path in files:
            if path.stem in found or read_regular(path, MAX_FILE) is None:
                continue
            try:
                scheme = library.read_scheme(path, in_home)
            except Exception:
                continue
            if scheme is not None:
                found[path.stem] = scheme
    return sorted(found.values(), key=lambda scheme: scheme.name.casefold())


class ColorSchemes(Kind):
    key = "color_scheme"

    @property
    def title(self) -> str:
        return str(translate("core", "Colors"))

    def items(self) -> list[Item]:
        found = []
        langs = languages()
        for scheme in installed_schemes():
            name = scheme.name
            try:
                general = read_ini(scheme.path).get("General", {})
                name = localized(general, "Name", langs) or name
            except OSError:
                pass
            found.append(
                Item(
                    scheme.id,
                    name,
                    path=scheme.path,
                    user=scheme.in_home,
                    extra={"colors": dict(scheme.colors), "made_here": scheme.made_here},
                )
            )
        return unique_sorted(found)

    def thumbnail(self, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
        if item.path is None:
            return QImage()
        return draw_card(read_table(Path(item.path)), size, dpr)


# The card ---------------------------------------------------------------

DESIGN = QSize(176, 110)  # the card is drawn at this size and scaled


def _font(pixels: float) -> QFont:
    font = QFont()
    font.setPixelSize(round(pixels))
    return font


def _text(p: QPainter, rect: QRectF, text: str, color: QColor, align=Qt.AlignmentFlag.AlignLeft) -> None:
    metrics = QFontMetricsF(p.font())
    p.setPen(color)
    p.drawText(
        rect,
        align | Qt.AlignmentFlag.AlignVCenter,
        metrics.elidedText(text, Qt.TextElideMode.ElideRight, rect.width()),
    )


def _alpha(color: QColor, alpha: float) -> QColor:
    result = QColor(color)
    result.setAlphaF(alpha)
    return result


def draw_card(table: Mapping[str, Mapping[str, QColor]], size: QSize, dpr: float) -> QImage:
    """The scheme card for a color table (see `read_table`)."""
    image = blank(size, dpr)
    c = lambda group, key: lookup(table, group, key)  # noqa: E731
    window, text = c("Colors:Window", "BackgroundNormal"), c("Colors:Window", "ForegroundNormal")
    bar, bar_text = title_bar_colors(table)
    p = QPainter(image)
    p.setRenderHints(
        QPainter.RenderHint.Antialiasing
        | QPainter.RenderHint.TextAntialiasing
        | QPainter.RenderHint.SmoothPixmapTransform
    )
    scale = min(size.width() / DESIGN.width(), size.height() / DESIGN.height())
    p.translate((size.width() - DESIGN.width() * scale) / 2, (size.height() - DESIGN.height() * scale) / 2)
    p.scale(scale, scale)
    outer = QRectF(0.5, 0.5, DESIGN.width() - 1, DESIGN.height() - 1)
    clip = QPainterPath()
    clip.addRoundedRect(outer, 5, 5)
    p.setClipPath(clip)
    p.fillRect(outer, window)
    p.setFont(_font(9))

    # Title bar with the window buttons.
    p.fillRect(QRectF(0, 0, DESIGN.width(), 19), bar)
    _text(p, QRectF(9, 0, 110, 19), str(translate("core", "Window title")), bar_text)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_alpha(bar_text, 0.85))
    for i, x in enumerate((137, 150, 163)):  # minimize, maximize, close
        p.save()
        p.translate(x, 9.5)
        if i == 0:
            p.drawLine(-3, 1, 3, 1)
        elif i == 1:
            p.drawRect(QRectF(-3, -3, 6, 6))
        else:
            p.drawLine(-3, -3, 3, 3)
            p.drawLine(-3, 3, 3, -3)
        p.restore()

    # Texts on the window.
    _text(p, QRectF(9, 24, 70, 13), str(translate("core", "Normal text")), text)
    for i, role in enumerate(("Positive", "Neutral", "Negative")):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c("Colors:Window", f"Foreground{role}"))
        p.drawEllipse(QRectF(141 + i * 11, 27.5, 6, 6))
    _text(p, QRectF(9, 37, 50, 13), str(translate("core", "Link")), c("Colors:Window", "ForegroundLink"))
    _text(
        p,
        QRectF(54, 37, 80, 13),
        str(translate("core", "Visited link")),
        c("Colors:Window", "ForegroundVisited"),
    )

    # A view with a highlighted row.
    view = QRectF(8, 54, 160, 31)
    p.setPen(_alpha(text, 0.25))
    p.setBrush(c("Colors:View", "BackgroundNormal"))
    p.drawRoundedRect(view, 3, 3)
    _text(
        p, QRectF(15, 56, 140, 13), str(translate("core", "View text")), c("Colors:View", "ForegroundNormal")
    )
    row = QRectF(10, 69, 156, 14)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c("Colors:Selection", "BackgroundNormal"))
    p.drawRoundedRect(row, 2, 2)
    _text(
        p,
        row.adjusted(5, 0, -5, 0),
        str(translate("core", "Selected text")),
        c("Colors:Selection", "ForegroundNormal"),
    )

    # Disabled text and a button.
    _text(
        p,
        QRectF(9, 91, 85, 15),
        str(translate("core", "Disabled text")),
        c("Colors:Window", "ForegroundInactive"),
    )
    button = QRectF(106, 90, 62, 16)
    p.setPen(_alpha(c("Colors:Button", "ForegroundNormal"), 0.3))
    p.setBrush(c("Colors:Button", "BackgroundNormal"))
    p.drawRoundedRect(button, 3, 3)
    _text(
        p,
        button,
        str(translate("core", "Button")),
        c("Colors:Button", "ForegroundNormal"),
        Qt.AlignmentFlag.AlignHCenter,
    )
    p.setClipping(False)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_alpha(text, 0.35))
    p.drawRoundedRect(outer, 5, 5)
    p.end()
    return image
