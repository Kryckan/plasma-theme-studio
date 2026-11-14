# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Plasma Style page: panel and popup looks, installed ones or one made from this theme."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .base import THIS_THEME, TUNING_WIDTH, PickerPage
from .preview_box import RatioPreview

translate = QCoreApplication.translate


class PlasmaStylePage(PickerPage):
    key = "plasma_style"
    parts = ("plasma_style",)
    note_sections = ("panel", "popup")
    kind_key = "plasma_style"
    id_field = ("panel", "style_id")
    mode_field = ("panel", "style")
    part_key = "plasma_style"

    @property
    def set_hint(self):
        return translate("ui", "Installs a Plasma style and switches to it.")

    def subtitle(self) -> str:
        return translate("ui", "How the panel, menus, popups and tooltips are drawn.")

    def build(self) -> None:
        super().build()
        # two short groups of values and a panel with an open popup and a tooltip to see them in
        self.style_box = QWidget()
        outer = QVBoxLayout(self.style_box)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        outer.addWidget(self.separator())
        row = QHBoxLayout()
        row.setSpacing(24)
        left = QWidget()
        left.setMaximumWidth(TUNING_WIDTH - 120)
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)
        column.addWidget(self.caption(translate("ui", "Panel")))
        column.addLayout(self.form(("panel", "radius"), ("panel", "border_width"), ("panel", "opacity")))
        column.addSpacing(8)
        column.addWidget(self.caption(translate("ui", "Popups and tooltips")))
        column.addLayout(self.form(("popup", "radius"), ("popup", "border_width"), ("popup", "opacity")))
        column.addStretch(1)
        self.style_preview = RatioPreview(self.theme, "menu")
        self.style_preview.setAccessibleName(translate("ui", "Preview of the panel and its popups"))
        row.addWidget(left, 5)
        row.addWidget(self.style_preview, 6, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(row)
        self.style_box.hide()
        self.add_below(self.style_box)

    def refresh(self) -> None:
        super().refresh()
        on, chosen = self.selection()
        shown = on and chosen == THIS_THEME
        self.style_box.setVisible(shown)
        if shown:
            self.style_preview.set_theme(self.theme)
