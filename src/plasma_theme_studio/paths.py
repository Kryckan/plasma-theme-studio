# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Locations the app reads and writes. All of them are inside the user's home."""

from __future__ import annotations

import os
from pathlib import Path

from . import APP_DIR


def data_home() -> Path:
    value = os.environ.get("XDG_DATA_HOME")
    return Path(value) if value else Path.home() / ".local" / "share"


def cache_home() -> Path:
    value = os.environ.get("XDG_CACHE_HOME")
    return Path(value) if value else Path.home() / ".cache"


def system_data_dirs() -> list[Path]:
    value = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [Path(p) for p in value.split(":") if p]


def themes_dir() -> Path:
    return data_home() / APP_DIR / "themes"


def snapshots_dir() -> Path:
    return data_home() / APP_DIR / "snapshots"


def color_schemes_dir() -> Path:
    return data_home() / "color-schemes"
