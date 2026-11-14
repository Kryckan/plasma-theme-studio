# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Icons page: the installed icon themes."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSize

from .base import PickerPage

translate = QCoreApplication.translate


class IconsPage(PickerPage):
    key = "icons"
    parts = ("icons",)
    kind_key = "icons"
    id_field = ("desktop", "icons")
    part_key = "icons"
    scrolling = False
    fit = False
    thumb_size = QSize(176, 64)

    @property
    def set_hint(self):
        return translate("ui", "Switches the icon theme.")

    def subtitle(self) -> str:
        return translate("ui", "The icons of applications and the desktop.")
