# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Pointers page: the installed cursor themes and their size."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSize

from .base import PickerPage

translate = QCoreApplication.translate


class PointersPage(PickerPage):
    key = "pointers"
    parts = ("pointers",)
    kind_key = "cursors"
    id_field = ("desktop", "cursors")
    part_key = "cursor_theme"
    tuning = (("desktop", "cursor_size"),)
    scrolling = False
    fit = False
    thumb_size = QSize(176, 64)

    @property
    def set_hint(self):
        return translate("ui", "Switches the pointer theme.")

    def subtitle(self) -> str:
        return translate("ui", "The mouse pointer.")

    def tuning_title(self) -> str:
        return translate("ui", "Size")
