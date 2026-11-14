# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Starts the editor."""

from __future__ import annotations

import signal
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import APP_DIR, APP_ID, APP_NAME, __version__, paths, translations

# The icon in a source checkout, used when the app is not installed.
SOURCE_ICON = Path(__file__).parents[3] / "data/icons/hicolor/scalable/apps" / f"{APP_ID}.svg"


def create_app(argv: list[str]) -> QApplication:
    app = QApplication(argv)
    app.setOrganizationName(APP_DIR)
    app.setApplicationName(APP_DIR)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    # Naming a desktop file that is not installed (a source checkout) only
    # gets a warning from the desktop portal.
    folders = [paths.data_home(), *paths.system_data_dirs()]
    if any((folder / "applications" / f"{APP_ID}.desktop").is_file() for folder in folders):
        app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme(APP_ID, QIcon(str(SOURCE_ICON))))

    # Keep the translators alive for as long as the app.
    app._translators = []
    qt_translator = QTranslator(app)
    if qt_translator.load(
        QLocale(), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    ):
        app.installTranslator(qt_translator)
        app._translators.append(qt_translator)
    app_translator = translations.load()
    if app_translator is not None:
        app.installTranslator(app_translator)
        app._translators.append(app_translator)
    return app


def run(file: str | None = None) -> int:
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = create_app(sys.argv[:1])
    from .main_window import MainWindow

    window = MainWindow()
    if file:
        window.open_path(Path(file))
    else:
        last = QSettings().value("last_file", "")
        if last and Path(last).is_file():
            window.open_path(Path(last))
    window.show()
    return app.exec()
