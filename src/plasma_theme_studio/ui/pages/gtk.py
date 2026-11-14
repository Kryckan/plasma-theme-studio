# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The GTK Apps page: GTK 3 and 4 styled from this theme's colors and shapes."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..widgets import SPACING, InlineNote
from .apps_samples import GtkSample
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
        self.written = InlineNote(
            translate(
                "ui",
                "Choosing Apply writes one style sheet for GTK 3 and one for GTK 4 into your own settings "
                "folders. Nothing else of GTK is changed, and “Undo last apply” puts both back.",
            ),
            "information",
        )
        self.content.addWidget(self.written)

        self.sample = GtkSample(self.theme)
        self.sample.setAccessibleName(translate("ui", "A GTK window drawn from this theme"))
        self.sample_hint = QLabel()
        self.sample_hint.setWordWrap(True)
        self.sample_hint.setForegroundRole(self.sample_hint.palette().ColorRole.PlaceholderText)
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACING)
        column.addWidget(self.caption(translate("ui", "Preview")))
        column.addWidget(self.sample)
        column.addWidget(self.sample_hint)
        self.set_side_preview(box)

    def refresh(self) -> None:
        self.sample.set_theme(self.theme)
        generated = self.theme.get(*self.style_field) == "generated"
        self.sample_hint.setText(
            translate("ui", "Nothing reaches the desktop until you choose Apply.")
            if generated
            else translate("ui", "Only a preview: GTK applications keep their look.")
        )
        super().refresh()
