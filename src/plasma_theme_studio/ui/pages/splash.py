# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Splash Screen page: what is shown while Plasma starts."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .base import PickerPage

translate = QCoreApplication.translate


class SplashPage(PickerPage):
    key = "splash"
    parts = ("splash",)
    kind_key = "splash"
    id_field = ("desktop", "splash")
    part_key = "splash"
    scrolling = False
    fit = False

    @property
    def set_hint(self):
        return translate("ui", "Switches the splash screen.")

    def subtitle(self) -> str:
        return translate("ui", "What is shown while Plasma starts.")
