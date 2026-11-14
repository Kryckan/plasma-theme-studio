# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Application Style page: the style of buttons, fields and menus in Qt applications."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QVBoxLayout

from ..style_preview import StylePreview
from .base import PickerPage

translate = QCoreApplication.translate

STYLE_DELAY = 250  # milliseconds after the last edit before the style is made again


class AppStylePage(PickerPage):
    key = "app_style"
    parts = ("app_style",)
    note_sections = ("apps",)
    kind_key = "app_style"
    id_field = ("apps", "style_id")
    mode_field = ("apps", "style")
    part_key = "app_style"
    tuning = (("apps", "radius"), ("apps", "border_width"))

    @property
    def set_hint(self):
        return translate("ui", "Writes a Kvantum style and switches to it.")

    def subtitle(self) -> str:
        return translate("ui", "How buttons, fields and menus look in applications.")

    def tuning_title(self) -> str:
        return translate("ui", "Values of “This theme”")

    def generated_mode(self) -> str:
        return "window"

    def build(self) -> None:
        super().build()
        self.style_preview = StylePreview(self.theme)
        self.style_preview.setMinimumHeight(220)
        box = QVBoxLayout()
        box.addWidget(self.caption(translate("ui", "Sample")))
        box.addWidget(self.style_preview)
        self.content.addLayout(box)
        self.timer = QTimer(self, singleShot=True, interval=STYLE_DELAY)
        self.timer.timeout.connect(lambda: self.style_preview.set_theme(self.theme))

    def refresh(self) -> None:
        super().refresh()
        self.timer.start()  # making the style takes a moment: wait for the edits to stop
