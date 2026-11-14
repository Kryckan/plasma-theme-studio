# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Rofi page: a Rofi theme made from this theme's colors and shapes."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..widgets import SPACING, InlineNote
from .apps_samples import RofiSample
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
        self.written = InlineNote(
            translate(
                "ui",
                "Choosing Apply writes one Rofi theme file and adds a line to your Rofi settings that "
                "selects it. “Undo last apply” takes both back.",
            ),
            "information",
        )
        self.content.addWidget(self.written)

        self.sample = RofiSample(self.theme)
        self.sample.setAccessibleName(translate("ui", "The Rofi launcher drawn from this theme"))
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
            else translate("ui", "Only a preview: Rofi keeps the theme it uses now.")
        )
        super().refresh()
