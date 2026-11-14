# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Loads the translation that matches the system language.

Installed packages ship compiled `.qm` files next to the `.ts` sources.
When running from a source checkout, the `.ts` files are compiled into the
cache folder on first use.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator

from . import APP_DIR, messages, paths

SOURCE_DIR = Path(__file__).parent / "i18n"
BASE_NAME = "plasma_theme_studio"
_LRELEASE = (
    "lrelease6",
    "lrelease-qt6",
    "/usr/lib/qt6/bin/lrelease",
    "/usr/lib64/qt6/bin/lrelease",
    "/usr/lib/qt6/libexec/lrelease",
    "pyside6-lrelease",
    "lrelease",
)


def _compile_from_source() -> Path | None:
    """Return the folder holding compiled translations, compiling .ts files if needed."""
    sources = sorted(SOURCE_DIR.glob("*.ts"))
    if not sources:
        return SOURCE_DIR  # an installed package ships only the compiled files
    if all((SOURCE_DIR / f"{ts.stem}.qm").exists() for ts in sources):
        return SOURCE_DIR
    tool = next((t for t in _LRELEASE if shutil.which(t)), None)
    target = paths.cache_home() / APP_DIR / "i18n"
    for ts in sources:
        qm = target / f"{ts.stem}.qm"
        if qm.exists() and qm.stat().st_mtime >= ts.stat().st_mtime:
            continue
        if tool is None:
            return None
        target.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [tool, "-silent", str(ts), "-qm", str(qm)], check=True, timeout=30, capture_output=True
            )
        except (OSError, subprocess.SubprocessError):
            return None
    return target


def load(locale: QLocale | None = None) -> QTranslator | None:
    """Load the app translation for the locale and route core messages through it."""
    directory = _compile_from_source()
    if directory is None:
        return None
    translator = QTranslator()
    if not translator.load(locale or QLocale(), BASE_NAME, "_", str(directory)):
        return None

    def hook(context: str, text: str) -> str:
        return translator.translate(context, text) or text

    messages.set_hook(hook)
    return translator
