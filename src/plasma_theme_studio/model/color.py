# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A small RGB color type with the operations the generators need."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int

    @classmethod
    def parse(cls, text: str) -> Color:
        if not isinstance(text, str) or not _HEX.match(text):
            raise ValueError(f"not a hex color: {text!r}")
        digits = text[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return cls(int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))

    @staticmethod
    def is_valid(text) -> bool:
        return isinstance(text, str) and bool(_HEX.match(text))

    @property
    def hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    @property
    def kde(self) -> str:
        """The "r,g,b" form used in KDE config files."""
        return f"{self.r},{self.g},{self.b}"

    def mix(self, other: Color, amount: float) -> Color:
        """Blend towards `other`: 0 returns this color, 1 returns `other`."""
        amount = min(1.0, max(0.0, amount))
        return Color(
            round(self.r + (other.r - self.r) * amount),
            round(self.g + (other.g - self.g) * amount),
            round(self.b + (other.b - self.b) * amount),
        )

    @property
    def luminance(self) -> float:
        """Relative luminance as defined by WCAG 2."""

        def channel(value: int) -> float:
            c = value / 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        return 0.2126 * channel(self.r) + 0.7152 * channel(self.g) + 0.0722 * channel(self.b)

    @property
    def is_dark(self) -> bool:
        return self.luminance < 0.18


BLACK = Color(0, 0, 0)
WHITE = Color(255, 255, 255)


def contrast(a: Color, b: Color) -> float:
    """WCAG contrast ratio between two colors, from 1 to 21."""
    hi, lo = sorted((a.luminance, b.luminance), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def readable_on(background: Color, dark: Color = Color(35, 38, 41), light: Color = WHITE) -> Color:
    """Pick whichever of `dark` and `light` reads better on `background`."""
    return light if contrast(light, background) >= contrast(dark, background) else dark
