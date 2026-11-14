# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The theme's twelve color roles turned into what a style or a decoration reads:
a QPalette, and the text of a kdeglobals file."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtGui import QColor, QPalette

from ..model.color import Color, readable_on
from ..model.color import on_accent as readable_on_accent

# Breeze Light, for a request that comes without colors and for roles that are missing.
DEFAULT_COLORS = {
    "accent": "#3daee9",
    "window": "#eff0f1",
    "view": "#fcfcfc",
    "button": "#eff0f1",
    "header": "#e3e5e7",
    "text": "#232629",
    "text_muted": "#7f8c8d",
    "link": "#2980b9",
    "visited": "#9b59b6",
    "negative": "#da4453",
    "neutral": "#f67400",
    "positive": "#27ae60",
}


def complete(colors: Mapping[str, str] | None) -> dict[str, str]:
    """`colors` with every role present; bad or missing values come from `DEFAULT_COLORS`."""
    result = dict(DEFAULT_COLORS)
    for role, value in (colors or {}).items():
        if role in result and Color.is_valid(value):
            result[role] = Color.parse(value).hex
    return result


def palette(colors: Mapping[str, str] | None) -> QPalette:
    """A palette for widgets from the color roles."""
    c = {role: QColor(value) for role, value in complete(colors).items()}
    button = c["button"]
    pal = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, c["window"]),
        (QPalette.ColorRole.WindowText, c["text"]),
        (QPalette.ColorRole.Base, c["view"]),
        (QPalette.ColorRole.AlternateBase, c["window"]),
        (QPalette.ColorRole.Text, c["text"]),
        (QPalette.ColorRole.Button, button),
        (QPalette.ColorRole.ButtonText, c["text"]),
        (QPalette.ColorRole.Highlight, c["accent"]),
        (QPalette.ColorRole.HighlightedText, QColor(readable_on(Color.parse(c["accent"].name())).hex)),
        (QPalette.ColorRole.ToolTipBase, c["window"]),
        (QPalette.ColorRole.ToolTipText, c["text"]),
        (QPalette.ColorRole.PlaceholderText, c["text_muted"]),
        (QPalette.ColorRole.Link, c["link"]),
        (QPalette.ColorRole.LinkVisited, c["visited"]),
        (QPalette.ColorRole.BrightText, QColor("white")),
        (QPalette.ColorRole.Light, button.lighter(130)),
        (QPalette.ColorRole.Midlight, button.lighter(115)),
        (QPalette.ColorRole.Mid, button.darker(125)),
        (QPalette.ColorRole.Dark, button.darker(150)),
        (QPalette.ColorRole.Shadow, QColor("black")),
    ):
        pal.setColor(role, color)
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        dim = QColor(c["text"])
        dim.setAlpha(110)
        pal.setColor(QPalette.ColorGroup.Disabled, role, dim)
    return pal


def _kde(value: str) -> str:
    return Color.parse(value).kde


def kdeglobals(colors: Mapping[str, str] | None) -> str:
    """The color groups of a kdeglobals file for these roles. Decorations read the
    title bar colors from `[WM]` and the rest from the `Colors:*` groups."""
    c = complete(colors)
    on_accent = readable_on_accent(
        Color.parse(c["accent"]), Color.parse(c["text"]), Color.parse(c["window"])
    ).hex
    lines: list[str] = []

    def group(name: str, background: str, foreground: str, alternate: str | None = None) -> None:
        lines.extend(
            [
                f"[{name}]",
                f"BackgroundNormal={_kde(background)}",
                f"BackgroundAlternate={_kde(alternate or background)}",
                f"ForegroundNormal={_kde(foreground)}",
                f"ForegroundInactive={_kde(c['text_muted'])}",
                f"ForegroundActive={_kde(c['accent'])}",
                f"ForegroundLink={_kde(c['link'])}",
                f"ForegroundVisited={_kde(c['visited'])}",
                f"ForegroundNegative={_kde(c['negative'])}",
                f"ForegroundNeutral={_kde(c['neutral'])}",
                f"ForegroundPositive={_kde(c['positive'])}",
                f"DecorationFocus={_kde(c['accent'])}",
                f"DecorationHover={_kde(c['accent'])}",
                "",
            ]
        )

    header_text = readable_on(Color.parse(c["header"])).hex
    group("Colors:Window", c["window"], c["text"])
    group("Colors:View", c["view"], c["text"], c["window"])
    group("Colors:Button", c["button"], c["text"])
    group("Colors:Selection", c["accent"], on_accent)
    group("Colors:Tooltip", c["window"], c["text"])
    group("Colors:Complementary", c["window"], c["text"])
    group("Colors:Header", c["header"], header_text)
    lines.extend(
        [
            "[WM]",
            f"activeBackground={_kde(c['header'])}",
            f"activeBlend={_kde(c['header'])}",
            f"activeForeground={_kde(header_text)}",
            f"inactiveBackground={_kde(c['window'])}",
            f"inactiveBlend={_kde(c['window'])}",
            f"inactiveForeground={_kde(c['text_muted'])}",
            "",
        ]
    )
    return "\n".join(lines)
