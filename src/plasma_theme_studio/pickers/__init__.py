# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pickers: the choices of the System Settings pages with pictures of them.

`kinds()` returns the `Kind` objects of the modules that exist, in page order,
`kind(key)` one of them or None. Each kind lives in its own module (see
`MODULES`), imported when first asked for; a module that is missing or fails to
import is left out. The framework: `base` (Item, Kind, helpers), `cache` (thumbnails
on disk) and `loader` (ThumbnailLoader).
"""

from __future__ import annotations

import importlib

from .base import Item, Kind

# Each module defines Kind subclasses with a `key`; one instance of each is made.
MODULES = (
    "globalthemes",
    "colorschemes",
    "appstyles",
    "plasmastyles",
    "decorations",
    "icons",
    "cursors",
    "splash",
    "sounds",
)

_kinds: dict[str, list[Kind]] = {}


def _load(module: str) -> list[Kind]:
    if module not in _kinds:
        found: list[Kind] = []
        try:
            loaded = importlib.import_module(f"{__name__}.{module}")
            for value in vars(loaded).values():
                if (
                    isinstance(value, type)
                    and issubclass(value, Kind)
                    and value is not Kind
                    and value.__module__ == loaded.__name__
                    and value.key
                ):
                    found.append(value())
        except Exception:
            found = []
        _kinds[module] = found
    return _kinds[module]


def kinds() -> list[Kind]:
    """The kinds that exist, in the order of `MODULES`."""
    return [kind for module in MODULES for kind in _load(module)]


def kind(key: str) -> Kind | None:
    return next((k for k in kinds() if k.key == key), None)


__all__ = ["Item", "Kind", "kind", "kinds", "MODULES"]
