# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The targets a theme is applied to, in the order they are applied."""

from .base import CSS_MARKER, JSON_MARKER, MARKER, XML_MARKER, ApplyError, Generator, PlannedFile, made_here
from .colorscheme import ColorSchemeGenerator
from .gtk import GtkGenerator
from .kvantum import KvantumGenerator
from .panellayout import PanelLayoutGenerator
from .plasmastyle import PlasmaStyleGenerator
from .rofi import RofiGenerator
from .windowframe import WindowFrameGenerator

# The colors come first: Kvantum and GTK take their palette from the scheme that is in use.
# Rofi is last: it only reads its theme when it starts, so nothing waits for it.
# The panel style comes before the panel position: a style can raise the panel's
# smallest thickness, and the thickness the theme asks for is set after that.
GENERATORS: tuple[Generator, ...] = (
    ColorSchemeGenerator(),
    KvantumGenerator(),
    GtkGenerator(),
    WindowFrameGenerator(),
    PlasmaStyleGenerator(),
    PanelLayoutGenerator(),
    RofiGenerator(),
)


def generator_by_id(target_id: str) -> Generator | None:
    return next((g for g in GENERATORS if g.id == target_id), None)


def section_generators(section: str) -> list[Generator]:
    """The targets that read the given theme section."""
    return [g for g in GENERATORS if section in g.sections]


__all__ = [
    "CSS_MARKER",
    "GENERATORS",
    "JSON_MARKER",
    "MARKER",
    "XML_MARKER",
    "ApplyError",
    "Generator",
    "PlannedFile",
    "generator_by_id",
    "made_here",
    "section_generators",
]
