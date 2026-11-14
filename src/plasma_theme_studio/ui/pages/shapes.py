# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Shapes page: the corner radius and border width the other pages start from."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .base import ValuePage

translate = QCoreApplication.translate


class ShapesPage(ValuePage):
    key = "shapes"
    note_sections = ("shape",)
    modes = ("window", "desktop", "panel", "menu")

    def subtitle(self) -> str:
        return translate("ui", "Corners and borders. Applications, windows, panels and popups follow these.")

    def build_controls(self) -> None:
        self.controls.addLayout(self.form(("shape", "radius"), ("shape", "border_width")))
