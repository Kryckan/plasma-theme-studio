# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading files that are not ours (themes, wallpapers, palettes) without trusting them: only
regular files of a sane size are opened, and a configuration text is cleaned of lines that
`kconfig.parse` needs quadratic time for."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from . import kconfig

MAX_FILE = 1_000_000  # bytes read from one file
MAX_GROUP_LINE = 1000  # characters of a "[group]" line; real ones are a few dozen


def is_regular(path: Path) -> bool:
    """Whether `path` (after following links) is a regular file: not a pipe, not a device."""
    try:
        return stat.S_ISREG(os.stat(path).st_mode)
    except (OSError, ValueError):
        return False


def read_regular(path: Path, limit: int = MAX_FILE) -> bytes | None:
    """The bytes of a regular file of at most `limit` bytes; None for anything else
    (a pipe that would block, a device such as /dev/zero, a huge file) or when it
    cannot be read."""
    try:
        # opened without waiting, and looked at after the opening: a file that is swapped for a pipe
        # between a look and the opening cannot block the reader
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    except (OSError, ValueError):
        return None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(limit + 1)
    except OSError:
        return None
    finally:
        os.close(descriptor)
    return data if len(data) <= limit else None


def parse_config(text: str) -> dict[tuple[str, ...], dict[str, str]]:
    """`kconfig.parse` of a text from outside: an over-long group line is dropped first."""
    lines = (
        "" if line.lstrip().startswith("[") and len(line) > MAX_GROUP_LINE else line
        for line in text.splitlines()
    )
    return kconfig.parse("\n".join(lines))
