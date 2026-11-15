# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Colors from a picture, found by the app itself or by matugen or pywal when they are installed.

The tools are run through the runner, with flags that only print the palette (matugen) or write it
into a folder made for the purpose (pywal): never a terminal, the wallpaper or any other program.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from ... import images, palette, safefile

translate = QCoreApplication.translate

BUILTIN = "builtin"
PROGRAMS = {"matugen": "matugen", "pywal": "wal"}  # the choice -> the program that is run
TIMEOUT = 60  # seconds; matugen and pywal take a few


def installed(runner, tool: str) -> bool:
    return tool == BUILTIN or runner.which(PROGRAMS[tool])


def tool_name(tool: str) -> str:
    return {BUILTIN: translate("ui", "the built-in way"), "matugen": "matugen", "pywal": "pywal"}[tool]


def _json_part(text: str) -> str:
    """The JSON object in what a tool printed (some print a line or two around it)."""
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else text


def find_colors(runner, tool: str, picture: Path) -> palette.PaletteResult:
    """The colors of `picture`. Never raises; `error` says what went wrong."""
    if not safefile.is_regular(picture) or images.too_large(picture):
        return palette.PaletteResult(error=translate("core", "The image cannot be read."))
    if tool == BUILTIN:
        return palette.extract(picture)
    failed = palette.PaletteResult(
        error=translate("ui", "{tool} did not give any colors for this picture.").format(tool=tool)
    )
    try:
        if tool == "matugen":
            answer = runner.run(
                ["matugen", "image", str(picture), "--dry-run", "--json", "hex"], timeout=TIMEOUT
            )
            if answer.returncode != 0:
                return failed
            return palette.from_matugen_text(_json_part(answer.stdout))
        with tempfile.TemporaryDirectory(prefix="pts-wal-") as cache:
            # -n keeps the wallpaper, -s -t -e leave terminals and other programs alone, -q is quiet;
            # the cache folder is a throwaway one, so the palette the person has in use stays
            answer = runner.run(
                ["env", f"XDG_CACHE_HOME={cache}", "wal", "-i", str(picture), "-n", "-s", "-t", "-e", "-q"],
                timeout=TIMEOUT,
            )
            if answer.returncode != 0:
                return failed
            return palette.from_pywal(Path(cache) / "wal" / "colors.json")
    except Exception:  # noqa: BLE001 - a tool that misbehaves is no reason to stop the window
        return failed
