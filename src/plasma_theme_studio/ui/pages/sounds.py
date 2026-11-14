# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The System Sounds page: the sound theme of notifications and events."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .base import PickerPage

translate = QCoreApplication.translate


class SoundsPage(PickerPage):
    key = "sounds"
    parts = ("sounds",)
    kind_key = "sounds"
    id_field = ("desktop", "sounds")
    part_key = "sounds"
    scrolling = False
    fit = False

    @property
    def set_hint(self):
        return translate("ui", "Switches the sound theme.")

    def subtitle(self) -> str:
        return translate("ui", "The sounds of notifications and events.")
