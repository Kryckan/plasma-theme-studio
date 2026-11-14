# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The GTK Apps page: GTK 3 and 4 styled from this theme's colors and shapes."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .base import TargetPage

translate = QCoreApplication.translate


class GtkPage(TargetPage):
    key = "gtk"
    parts = ("gtk",)
    note_sections = ("gtk",)
    style_field = ("gtk", "style")

    @property
    def set_hint(self):
        return translate("ui", "Writes a style sheet for GTK 3 and 4 applications.")

    def subtitle(self) -> str:
        return translate("ui", "GTK applications get this theme's colors and shapes through a style sheet.")

    def build_values(self) -> None:
        self.content.addWidget(self.caption(translate("ui", "Shapes for GTK applications")))
        self.content.addWidget(
            self.form_widget(("gtk", "radius"), ("gtk", "border_width"), ("gtk", "window_radius"))
        )
