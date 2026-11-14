# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Rofi page: a Rofi theme made from this theme's colors and shapes."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .base import TargetPage

translate = QCoreApplication.translate


class RofiPage(TargetPage):
    key = "rofi"
    parts = ("rofi",)
    note_sections = ("rofi",)
    style_field = ("rofi", "style")

    @property
    def set_hint(self):
        return translate("ui", "Writes a Rofi theme file.")

    def subtitle(self) -> str:
        return translate("ui", "The Rofi launcher gets this theme's colors and shapes.")

    def build_values(self) -> None:
        self.content.addWidget(self.caption(translate("ui", "Shapes and font for Rofi")))
        self.content.addWidget(
            self.form_widget(
                ("rofi", "radius"), ("rofi", "border_width"), ("rofi", "opacity"), ("rofi", "font")
            )
        )
