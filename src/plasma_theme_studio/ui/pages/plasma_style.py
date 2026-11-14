# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Plasma Style page: panel and popup looks, installed ones or one made from this theme."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .base import PickerPage

translate = QCoreApplication.translate


class PlasmaStylePage(PickerPage):
    key = "plasma_style"
    parts = ("plasma_style",)
    note_sections = ("panel", "popup")
    kind_key = "plasma_style"
    id_field = ("panel", "style_id")
    mode_field = ("panel", "style")
    part_key = "plasma_style"
    tuning = (
        ("panel", "radius"),
        ("panel", "border_width"),
        ("panel", "opacity"),
        ("popup", "radius"),
        ("popup", "border_width"),
        ("popup", "opacity"),
    )

    @property
    def set_hint(self):
        return translate("ui", "Installs a Plasma style and switches to it.")

    def subtitle(self) -> str:
        return translate("ui", "How the panel, menus, popups and tooltips are drawn.")

    def tuning_title(self) -> str:
        return translate("ui", "Values of “This theme”")

    def generated_mode(self) -> str:
        return "panel"
