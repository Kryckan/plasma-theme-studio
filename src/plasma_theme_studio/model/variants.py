# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Light and dark variants of a theme's colors: the names, and the automatic conversion.

A theme has one set of colors and may have a second one, the other variant. Shapes, fonts and
everything else are shared. `convert` makes the second set from the first: the same hues, the
lightness turned around, and every text color corrected so that it can be read.
"""

from __future__ import annotations

from .color import Color, contrast

LIGHT, DARK = "light", "dark"
VARIANTS = (LIGHT, DARK)

SURFACES = ("window", "view", "button", "header")
# Colors that keep their hue and chroma and are only made lighter or darker when they cannot be read.
KEPT = ("accent", "link", "visited", "negative", "neutral", "positive")
# The main text colors: their contrast with the window is carried over to the other variant.
TEXTS = ("text", "text_muted")

# Lightness (OKLCH) of a dark surface from the one it was in a light theme, and back.
_DARK_BASE, _DARK_SPAN = 0.17, 1.2


def opposite(variant: str) -> str:
    return DARK if variant == LIGHT else LIGHT


def kind_of(window: str) -> str:
    """Whether a theme with this window color is a light or a dark one."""
    return DARK if Color.parse(window).is_dark else LIGHT


def _surface(color: Color, to: str, oklch) -> Color:
    from ..palette import oklch_to_color

    lightness, chroma, hue = oklch(color)
    if to == DARK:
        lightness = _DARK_BASE + _DARK_SPAN * (1 - lightness)
    else:
        lightness = 1 - (lightness - _DARK_BASE) / _DARK_SPAN
    return oklch_to_color(min(max(lightness, 0.0), 1.0), chroma, hue)


def _carry_contrast(color: Color, old_window: Color, new_window: Color, to: str, oklch) -> Color:
    """`color` in the lightness that has, on the new window, the contrast it had on the old one."""
    from ..palette import oklch_to_color

    wanted = contrast(color, old_window)
    _lightness, chroma, hue = oklch(color)
    best, best_gap = color, float("inf")
    for step in range(0, 101):  # a dark theme gets lighter text, a light theme darker text
        lightness = step / 100 if to == DARK else 1 - step / 100
        candidate = oklch_to_color(lightness, chroma, hue)
        gap = abs(contrast(candidate, new_window) - wanted)
        if gap < best_gap:
            best, best_gap = candidate, gap
    return best


def convert(colors: dict[str, str], to: str) -> dict[str, str]:
    """The colors of the `to` variant ("light" or "dark") made from the other one's. `colors` maps the
    twelve color keys to hex colors; a key that is missing or not a color is left out of the answer.
    The accent and the status colors keep their hue and are changed only as far as reading them needs;
    `scheme_id` is not carried over. Without the palette module (no Qt) the colors come back as they are."""
    try:
        from ..palette import ensure_contrast, to_oklch
    except ImportError:
        return {key: value for key, value in colors.items() if Color.is_valid(value)}
    parsed = {key: Color.parse(value) for key, value in colors.items() if Color.is_valid(value)}
    out = dict(parsed)
    for key in SURFACES:
        if key in parsed:
            out[key] = _surface(parsed[key], to, to_oklch)
    if "window" in parsed:
        for key in TEXTS:
            if key in parsed:
                out[key] = _carry_contrast(parsed[key], parsed["window"], out["window"], to, to_oklch)
    result = {key: color.hex for key, color in out.items()}
    return ensure_contrast(result)
