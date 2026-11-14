# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Panel page: where the panel sits and how it behaves."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .base import ValuePage

translate = QCoreApplication.translate

FIELDS = ("location", "height", "alignment", "length_mode", "floating", "visibility", "opacity_mode")


class PanelPage(ValuePage):
    key = "panel"
    parts = ("panel",)
    modes = ("panel", "desktop")
    preview_hint = ""

    def subtitle(self) -> str:
        return translate(
            "ui",
            "Position and behavior of the main panel. A value left as it is is not touched on the desktop.",
        )

    def build_controls(self) -> None:
        self.controls.addLayout(self.form(*(("panel_layout", key) for key in FIELDS)))
