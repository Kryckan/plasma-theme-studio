# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The targets a theme is applied to, in the order they are applied."""

from .base import JSON_MARKER, MARKER, XML_MARKER, ApplyError, Generator, PlannedFile, made_here
from .colorscheme import ColorSchemeGenerator
from .panellayout import PanelLayoutGenerator
from .plasmastyle import PlasmaStyleGenerator
from .windowframe import WindowFrameGenerator

# The panel style comes before the panel position: a style can raise the panel's
# smallest thickness, and the thickness the theme asks for is set after that.
GENERATORS: tuple[Generator, ...] = (
    ColorSchemeGenerator(),
    WindowFrameGenerator(),
    PlasmaStyleGenerator(),
    PanelLayoutGenerator(),
)


def generator_by_id(target_id: str) -> Generator | None:
    return next((g for g in GENERATORS if g.id == target_id), None)


def section_generators(section: str) -> list[Generator]:
    """The targets that read the given theme section."""
    return [g for g in GENERATORS if section in g.sections]


__all__ = [
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
