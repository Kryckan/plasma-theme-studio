# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The targets a theme is applied to, in the order they are applied."""

from .base import CSS_MARKER, JSON_MARKER, MARKER, XML_MARKER, ApplyError, Generator, PlannedFile, made_here
from .colorscheme import ColorSchemeGenerator
from .extras import LaunchFeedbackTarget, ToolbarsTarget
from .gtk import GtkGenerator
from .installed import (
    AccentTarget,
    BorderSizeTarget,
    CursorSizeTarget,
    CursorThemeTarget,
    FontsTarget,
    IconsTarget,
    InstalledAppStyle,
    InstalledDecoration,
    InstalledPlasmaStyle,
    NightModeTarget,
    SoundsTarget,
    SplashTarget,
    TitlebarButtonsTarget,
)
from .kvantum import KvantumGenerator
from .panellayout import PanelLayoutGenerator
from .plasmastyle import PlasmaStyleGenerator
from .rofi import RofiGenerator
from .variants import NightVariantsTarget
from .windowframe import WindowFrameGenerator

# The colors come first: Kvantum and GTK take their palette from the scheme that is in use.
# The accent follows the colors, because it is put into the scheme that is in use.
# An installed variant comes right after the generated one it replaces (the two are never
# wanted together), and the window settings (border size, buttons) after the frame they apply to.
# The panel style comes before the panel position: a style can raise the panel's
# smallest thickness, and the thickness the theme asks for is set after that.
# Undo walks the list the same way, so what was set last is put back last.
# Rofi is last: it only reads its theme when it starts, so nothing waits for it.
GENERATORS: tuple[Generator, ...] = (
    ColorSchemeGenerator(),
    AccentTarget(),
    KvantumGenerator(),
    InstalledAppStyle(),
    ToolbarsTarget(),
    GtkGenerator(),
    WindowFrameGenerator(),
    InstalledDecoration(),
    BorderSizeTarget(),
    TitlebarButtonsTarget(),
    PlasmaStyleGenerator(),
    InstalledPlasmaStyle(),
    PanelLayoutGenerator(),
    IconsTarget(),
    CursorThemeTarget(),
    CursorSizeTarget(),
    LaunchFeedbackTarget(),
    FontsTarget(),
    SplashTarget(),
    SoundsTarget(),
    NightVariantsTarget(),
    NightModeTarget(),
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
