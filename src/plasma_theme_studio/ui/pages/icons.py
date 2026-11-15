# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Icons page: the installed icon themes, six sample icons on each card and a large preview of the
chosen theme (twelve icons at 48 and 32 pixels) on the theme's window color."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSize
from PySide6.QtGui import QColor

from ...pickers import icons as icon_picker
from .base import PickerPage
from .pickers_common import Background, ImageStrip, LoadsInBackground

translate = QCoreApplication.translate

PREVIEW_SIDES = (48, 32)


class IconsPage(LoadsInBackground, PickerPage):
    key = "icons"
    parts = ("icons",)
    kind_key = "icons"
    id_field = ("desktop", "icons")
    part_key = "icons"
    thumb_size = QSize(176, 80)

    @property
    def set_hint(self):
        return translate("ui", "Switches the icon theme.")

    def subtitle(self) -> str:
        return translate("ui", "The icons of applications and the desktop.")

    def build(self) -> None:
        self.desktop_id: str | None = None  # the theme the desktop uses now
        self.shown_key = None
        self.worker = Background(self)
        self.worker.ready.connect(self._rows_ready)
        super().build()
        self.strip = ImageStrip(translate("ui", "Preview of the icon theme"))
        self.add_top_row(self.strip, 1)
        self.top_row.hide()

    def after_desktop(self) -> None:
        self.desktop_id = self.current_id()
        self.update_strip()

    def refresh(self) -> None:
        super().refresh()
        self.update_strip()

    def shown_id(self) -> str | None:
        """The theme the large preview shows: the chosen one, else what the desktop uses now."""
        on, chosen = self.selection()
        return chosen if on and chosen else self.desktop_id

    def update_strip(self) -> None:
        item = self.items.get(self.shown_id())
        colors = dict(self.colors())
        dpr = self.devicePixelRatioF()
        key = (item.id if item else None, tuple(colors.items()), dpr)
        if key == self.shown_key:
            return
        self.shown_key = key
        if item is None:
            self.worker.cancel()
            self.top_row.hide()
            return
        self.strip.set_background(QColor(colors.get("window") or "#eff0f1"))
        self.worker.request(icon_picker.sample_rows, item, PREVIEW_SIDES, dpr, colors)

    def _rows_ready(self, rows) -> None:
        self.strip.set_rows(rows or [])
        self.top_row.setVisible(self.strip.has_content())
