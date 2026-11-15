# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Splash Screen page: what is shown while Plasma starts. Each package is a card with its own
picture; the chosen one is shown large above the grid."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..widgets import LARGE_SPACING, SPACING
from .base import PickerPage
from .pickers_common import PICTURE_SIZE, Background, LoadsInBackground, PreviewPicture

translate = QCoreApplication.translate


class SplashPage(LoadsInBackground, PickerPage):
    key = "splash"
    parts = ("splash",)
    kind_key = "splash"
    id_field = ("desktop", "splash")
    part_key = "splash"

    @property
    def set_hint(self):
        return translate("ui", "Switches the splash screen.")

    def subtitle(self) -> str:
        return translate("ui", "What is shown while Plasma starts.")

    def build(self) -> None:
        self.desktop_id: str | None = None  # the package the desktop uses now
        self.shown_key = None
        self.worker = Background(self)
        self.worker.ready.connect(self._picture_ready)
        super().build()
        self.picture = PreviewPicture(translate("ui", "Preview of the splash screen"))
        self.name = QLabel()
        font = self.name.font()
        font.setPointSizeF(font.pointSizeF() * 1.25) if font.pointSizeF() > 0 else None
        font.setBold(True)
        self.name.setFont(font)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.status = QLabel()
        for label in (self.name, self.description, self.status):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.description.setForegroundRole(self.description.palette().ColorRole.PlaceholderText)
        text = QVBoxLayout()
        text.setSpacing(SPACING)
        text.addWidget(self.name)
        text.addWidget(self.description)
        text.addWidget(self.status)
        text.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(LARGE_SPACING)
        row.addWidget(self.picture, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(text, 1)
        box = QWidget()
        box.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        box.setMaximumHeight(PICTURE_SIZE.height())
        self.add_top_row(box, 1)
        self.top_row.hide()

    def after_desktop(self) -> None:
        self.desktop_id = self.current_id()
        self.update_large()

    def refresh(self) -> None:
        super().refresh()
        self.update_large()

    def shown_id(self) -> str | None:
        """The package the large preview shows: the chosen one, else what the desktop uses now."""
        on, chosen = self.selection()
        return chosen if on and chosen else self.desktop_id

    def update_large(self) -> None:
        item = self.items.get(self.shown_id())
        in_use = item is not None and item.id == self.desktop_id
        key = (item.id if item else None, in_use, self.devicePixelRatioF())
        if key == self.shown_key:
            return
        self.shown_key = key
        if item is None:
            self.worker.cancel()
            self.top_row.hide()
            return
        self.name.setText(item.name)
        self.description.setText(item.description)
        self.description.setVisible(bool(item.description))
        self.status.setText(translate("ui", "In use") if in_use else translate("ui", "Not in use yet"))
        self.top_row.show()
        self.worker.request(self.kind.thumbnail, item, PICTURE_SIZE, self.devicePixelRatioF(), None)

    def _picture_ready(self, image) -> None:
        self.picture.set_image(image)
