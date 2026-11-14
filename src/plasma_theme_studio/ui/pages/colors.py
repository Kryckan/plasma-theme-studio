# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Colors page: the accent and the roles of the color scheme, beside the drawn preview."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .base import ValuePage

translate = QCoreApplication.translate

SURFACES = ("window", "view", "button", "header")
TEXTS = ("text", "text_muted", "link", "visited", "negative", "neutral", "positive")


class ColorsPage(ValuePage):
    key = "colors"
    parts = ("colors",)
    note_sections = ("colors",)
    modes = ("desktop", "window", "menu")

    def subtitle(self) -> str:
        return translate("ui", "The color scheme and the accent color. Every part follows these.")

    def build_controls(self) -> None:
        self.controls.addWidget(self.caption(translate("ui", "Accent")))
        self.controls.addLayout(self.form(("colors", "accent"), ("colors", "accent_from_wallpaper")))
        self.controls.addWidget(self.separator())
        self.controls.addWidget(self.caption(translate("ui", "Surfaces")))
        self.controls.addLayout(self.form(*(("colors", key) for key in SURFACES)))
        self.controls.addWidget(self.separator())
        self.controls.addWidget(self.caption(translate("ui", "Text and status")))
        self.controls.addLayout(self.form(*(("colors", key) for key in TEXTS)))
