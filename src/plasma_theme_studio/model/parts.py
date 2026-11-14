# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the theme file and the desktop parts share about borders, title bar buttons and fonts.

Nothing here needs Qt or a KDE tool, so the theme model can check these values. `desktopparts`
re-exports every name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..messages import Msg, translate

# What System Settings offers for the border size: key in kwinrc and the name shown.
BORDER_SIZES = (
    ("None", translate("core", "No borders")),
    ("NoSides", translate("core", "No side borders")),
    ("Tiny", translate("core", "Tiny")),
    ("Normal", translate("core", "Normal")),
    ("Large", translate("core", "Large")),
    ("VeryLarge", translate("core", "Very large")),
    ("Huge", translate("core", "Huge")),
    ("VeryHuge", translate("core", "Very huge")),
    ("Oversized", translate("core", "Oversized")),
)


# The letters of KWin's title bar button strings: letter, number in KWin's report, name.
# KWin 6 keeps no number for L, which it still accepts and ignores.
BUTTONS = (
    ("M", 0, translate("core", "Window menu")),
    ("N", 1, translate("core", "Application menu")),
    ("S", 2, translate("core", "On all desktops")),
    ("H", 6, translate("core", "Help")),
    ("I", 3, translate("core", "Minimize")),
    ("A", 4, translate("core", "Maximize")),
    ("X", 5, translate("core", "Close")),
    ("F", 9, translate("core", "Keep above others")),
    ("B", 8, translate("core", "Keep below others")),
    ("L", None, translate("core", "Shade (not used by KWin 6)")),
    ("E", 12, translate("core", "Hide from screenshots")),
    ("_", 11, translate("core", "Spacer")),
)
DEFAULT_BUTTONS = {"left": "MSE", "right": "HIAX"}


def button_names() -> dict[str, Msg]:
    """Letter -> plain name, for a button editor."""
    return {letter: name for letter, _number, name in BUTTONS}


def parse_buttons(text: str) -> list[str] | None:
    """The letters of a button string in order, or None when it has a letter KWin does not know
    or a button twice (a spacer may come as often as wanted)."""
    letters = list(text.strip())
    known = button_names()
    if any(letter not in known for letter in letters):
        return None
    real = [letter for letter in letters if letter != "_"]
    return letters if len(set(real)) == len(real) else None


def describe_buttons(text: str) -> list[Msg]:
    """The names of the buttons of a string, in order. A letter KWin does not know is left out."""
    return [button_names()[letter] for letter in text if letter in button_names()]


# Qt's font weights and the names a chooser shows for them.
FONT_WEIGHTS = (
    (100, translate("core", "Thin")),
    (200, translate("core", "Extra light")),
    (300, translate("core", "Light")),
    (400, translate("core", "Regular")),
    (500, translate("core", "Medium")),
    (600, translate("core", "Demi bold")),
    (700, translate("core", "Bold")),
    (800, translate("core", "Extra bold")),
    (900, translate("core", "Black")),
)
_QT5_WEIGHTS = {0: 100, 12: 200, 25: 300, 50: 400, 57: 500, 63: 600, 75: 700, 81: 800, 87: 900}


@dataclass(frozen=True)
class FontSpec:
    """A font as KDE stores it: Qt's description, `Family,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1`."""

    family: str
    size: float
    weight: int = 400
    italic: bool = False

    @classmethod
    def parse(cls, text: str) -> FontSpec | None:
        """The family, point size, weight and slant of a Qt font description, or None when it is
        not one. Both Qt 6 and the shorter Qt 5 form are read. Needs no QApplication."""
        fields = [part.strip() for part in text.split(",")]
        try:
            size = float(fields[1])
            weight = int(fields[4]) if len(fields) > 4 else 400
            slant = int(fields[5]) if len(fields) > 5 else 0
        except (ValueError, IndexError):
            return None
        if not fields[0] or not 0 < size < 1000 or slant not in (0, 1, 2) or not 0 <= weight <= 1000:
            return None
        if len(fields) in (10, 11):  # Qt 5 counted weights from 0 to 99
            weight = _QT5_WEIGHTS[min(_QT5_WEIGHTS, key=lambda old: abs(old - weight))]
        weight = max(weight, 1)  # one range for every form, as `from_short` has it
        return cls(fields[0], size, weight, slant != 0)

    def text(self) -> str:
        size = f"{self.size:g}"
        return f"{self.family},{size},-1,5,{self.weight},{int(self.italic)},0,0,0,0,0,0,0,0,0,1"

    @classmethod
    def from_short(cls, text: str) -> FontSpec | None:
        """The form a theme file holds: `Family, 10`, `Family, 10, 700` (weight, 100 to 900) and
        `Family, 10.5, 400, italic`; the weight can be left out before `italic`. A Qt description
        (what `text` gives) is read too. None when it is neither."""
        if not isinstance(text, str) or re.search(r"[\x00-\x1f\x7f\\]", text):
            return None
        fields = [part.strip() for part in text.split(",")]
        if len(fields) >= 5 and re.fullmatch(r"-?\d+", fields[2]):
            return cls.parse(text)
        if len(fields) < 2 or not fields[0] or len(text) > 200:
            return None
        try:
            size = float(fields[1].removesuffix("pt").strip())
        except ValueError:
            return None
        weight, italic = 400, False
        for extra in fields[2:]:
            if extra.lower() == "italic" and not italic:
                italic = True
            elif re.fullmatch(r"\d{1,4}", extra) and weight == 400 and not italic:
                weight = int(extra)
            else:
                return None
        if not 0 < size < 1000 or not 1 <= weight <= 1000:
            return None
        return cls(fields[0], size, weight, italic)

    def short(self) -> str:
        """The form of `from_short`, the one a theme file is written in."""
        parts = [self.family, f"{self.size:g}"]
        if self.weight != 400 or self.italic:
            parts.append(str(self.weight))
        if self.italic:
            parts.append("italic")
        return ", ".join(parts)

    def label(self) -> str:
        """`Family, 10 pt` with the weight and slant when they are not the usual."""
        parts = [self.family, f"{self.size:g} pt"]
        if self.weight != 400:
            parts.append(str(weight_name(self.weight)))
        if self.italic:
            parts.append(str(translate("core", "Italic")))
        return ", ".join(parts)


def weight_name(weight: int) -> Msg:
    return min(FONT_WEIGHTS, key=lambda item: abs(item[0] - weight))[1]
