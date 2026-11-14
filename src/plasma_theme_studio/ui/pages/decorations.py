# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Window Decorations page: the frame and title bar, with shadows, borders and buttons."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .base import PickerPage

translate = QCoreApplication.translate


class DecorationsPage(PickerPage):
    key = "decorations"
    parts = ("decoration", "borders")
    note_sections = ("window", "shadow")
    kind_key = "decoration"
    id_field = ("window", "decoration_id")
    mode_field = ("window", "decoration")
    part_key = "decoration"
    breeze_card = True
    tuning = (
        ("window", "radius"),
        ("window", "border_width"),
        ("shadow", "size"),
        ("shadow", "strength"),
        ("window", "border_size"),
        ("window", "buttons_left"),
        ("window", "buttons_right"),
    )

    @property
    def set_hint(self):
        return translate("ui", "Writes a window decoration and switches to it.")

    def subtitle(self) -> str:
        return translate("ui", "The frame and title bar of windows.")

    def tuning_title(self) -> str:
        return translate("ui", "Frame, shadow and title bar buttons")

    def generated_mode(self) -> str:
        return "window"
