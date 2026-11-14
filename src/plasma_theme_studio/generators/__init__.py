# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The targets a theme is applied to, in the order they are applied."""

from .base import MARKER, ApplyError, Generator, PlannedFile
from .colorscheme import ColorSchemeGenerator

GENERATORS: tuple[Generator, ...] = (ColorSchemeGenerator(),)


def generator_by_id(target_id: str) -> Generator | None:
    return next((g for g in GENERATORS if g.id == target_id), None)


__all__ = ["GENERATORS", "MARKER", "ApplyError", "Generator", "PlannedFile", "generator_by_id"]
