# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Pointers page: the installed pointer themes, eight sample pointers on each card, the size and a
preview of the chosen theme at that size."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton

from ...model.theme import FIELD_BY_ID
from ...pickers import cursors as cursor_picker
from . import small_settings
from .base import PickerPage
from .pickers_common import Background, ImageStrip, LoadsInBackground

translate = QCoreApplication.translate

SIZE_FIELD = ("desktop", "cursor_size")
DEFAULT_SIZE = 24


def under_tile(picture: QImage) -> QImage:
    """The pointers on a tile they can be seen on: a light one for dark pointers, a dark one for light
    pointers, none for pointers that carry their own outline."""
    weight = lightness = 0.0
    for y in range(0, picture.height(), 2):
        for x in range(0, picture.width(), 2):
            color = picture.pixelColor(x, y)
            weight += color.alphaF()
            lightness += color.alphaF() * color.lightnessF()
    if weight == 0 or 0.3 <= lightness / weight <= 0.75:
        return picture
    tile = QImage(picture.size(), QImage.Format.Format_ARGB32_Premultiplied)
    tile.setDevicePixelRatio(picture.devicePixelRatio())
    tile.fill(0)
    painter = QPainter(tile)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#e4e6e8") if lightness / weight < 0.3 else QColor("#33373b"))
    size = picture.deviceIndependentSize()
    painter.drawRoundedRect(QRectF(0, 0, size.width(), size.height()), 6, 6)
    painter.drawImage(0, 0, picture)
    painter.end()
    return tile


class PointersPage(LoadsInBackground, PickerPage):
    key = "pointers"
    parts = ("pointers",)
    kind_key = "cursors"
    id_field = ("desktop", "cursors")
    part_key = "cursor_theme"
    thumb_size = QSize(176, 72)

    @property
    def set_hint(self):
        return translate("ui", "Switches the pointer theme.")

    def subtitle(self) -> str:
        return translate("ui", "The mouse pointer.")

    def build(self) -> None:
        self.desktop_id: str | None = None  # the theme the desktop uses now
        self.desktop_size: int | None = None
        self.shown_key = None
        self.size_choices: tuple = ()
        self.worker = Background(self)
        self.worker.ready.connect(self._images_ready)
        super().build()
        self.launch_button = QPushButton(translate("ui", "Configure Launch Feedback…"))
        self.launch_button.setToolTip(
            translate("ui", "Sets the busy pointer and the taskbar feedback when a program starts.")
        )
        self.launch_button.clicked.connect(self.open_launch_feedback)
        self.header.add_action(self.launch_button)

        # The size chooser sits in the search row, above the scrolling cards: always in view, as in System
        # Settings, and it offers the sizes of the theme that is shown.
        self.size_box = QComboBox()
        self.size_box.setAccessibleName(translate("ui", "Size"))
        self.size_box.setMinimumWidth(168)
        self.size_box.activated.connect(self._size_picked)
        self.size_label = QLabel(translate("ui", "Size:"))
        self.size_label.setBuddy(self.size_box)
        bar = self.grid.bar.layout()
        bar.addWidget(self.size_label)
        bar.addWidget(self.size_box)
        self.size_label.show()  # marked as shown, so that the bar is not taken for an empty one
        self.size_box.show()
        self.grid._update_state()
        self.strip = ImageStrip(translate("ui", "Preview of the pointer theme"))
        self.add_top_row(self.strip, 1)
        self.top_row.hide()

    # ---- what the desktop has

    def shown_thumbnail(self, image: QImage) -> QImage:
        return under_tile(image)

    def read_state(self) -> dict:
        from ... import desktopparts

        state = super().read_state()
        try:
            state["size"] = desktopparts.PARTS["cursor_size"].current(self.window.runner)
        except Exception:  # noqa: BLE001 - what the desktop has is only a hint here
            state["size"] = None
        return state

    def after_desktop(self) -> None:
        self.desktop_id = self.current_id()
        self.desktop_size = self.desktop_state.get("size")
        self.update_size_and_strip()

    def refresh(self) -> None:
        super().refresh()
        self.update_size_and_strip()

    def shown_id(self) -> str | None:
        """The theme the sizes and the preview are about: the chosen one, else what the desktop uses."""
        on, chosen = self.selection()
        return chosen if on and chosen else self.desktop_id

    def chosen_size(self) -> int | None:
        return self.theme.get(*SIZE_FIELD)

    # ---- the size

    def sizes_of(self, item) -> list[int]:
        """The sizes to offer: those the theme has (the usual steps for a scalable one), and the one the
        theme already holds, so the box never says something else than the theme."""
        sizes = list(item.extra.get("sizes") or cursor_picker.SCALABLE_SIZES) if item else []
        size = self.chosen_size()
        if size is not None and size not in sizes:
            sizes.append(size)
        return sorted(set(sizes))

    def fill_sizes(self) -> None:
        sizes = self.sizes_of(self.items.get(self.shown_id()))
        size = self.chosen_size()
        want = (tuple(sizes), size)
        if want == self.size_choices:
            return
        self.size_choices = want
        self.size_box.blockSignals(True)
        self.size_box.clear()
        self.size_box.addItem(translate("ui", "Leave as it is"), None)
        for value in sizes:
            self.size_box.addItem(translate("ui", "{size} pixels").format(size=value), value)
        self.size_box.setCurrentIndex(max(0, self.size_box.findData(size)) if size is not None else 0)
        self.size_box.blockSignals(False)

    def _size_picked(self, index: int) -> None:
        self.window.edit(FIELD_BY_ID[SIZE_FIELD], self.size_box.itemData(index))
        self.refresh()

    def shown_size(self) -> int:
        return self.chosen_size() or self.desktop_size or DEFAULT_SIZE

    # ---- the preview

    def update_size_and_strip(self) -> None:
        self.fill_sizes()
        item = self.items.get(self.shown_id())
        size, dpr = self.shown_size(), self.devicePixelRatioF()
        window = self.theme.get("colors", "window") or "#eff0f1"
        key = (item.id if item else None, size, dpr, window)
        if key == self.shown_key:
            return
        self.shown_key = key
        if item is None:
            self.worker.cancel()
            self.top_row.hide()
            return
        self.strip.set_background(QColor(window))
        self.worker.request(cursor_picker.pointer_images, item, size, dpr)

    def _images_ready(self, images) -> None:
        self.strip.set_rows([images] if images else [])
        self.top_row.setVisible(self.strip.has_content())

    # ---- launch feedback

    def open_launch_feedback(self) -> None:
        """Open the dialog of the launch feedback; what it holds goes into the theme."""
        small_settings.open_launch_feedback(self.window)
