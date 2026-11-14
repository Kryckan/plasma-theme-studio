# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Pointers page: the installed pointer themes, eight sample pointers on each card, the size and a
preview of the chosen theme at that size."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...model.theme import FIELD_BY_ID
from ...pickers import cursors as cursor_picker
from ..widgets import SPACING
from .base import LABEL_WIDTH, PickerPage
from .pickers_common import Background, ImageStrip

translate = QCoreApplication.translate

SIZE_FIELD = ("desktop", "cursor_size")
LAUNCH_FEEDBACK_MODULE = "kcm_cursortheme"  # System Settings has the launch feedback dialog on this page
DEFAULT_SIZE = 24


class PointersPage(PickerPage):
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
        self.launch_button = QPushButton(translate("ui", "Configure Launch Feedback in System Settings…"))
        self.launch_button.setToolTip(translate("ui", "Opens the pointer page of System Settings."))
        self.launch_button.clicked.connect(self.open_launch_feedback)
        self.header.add_action(self.launch_button)

        self.size_box = QComboBox()
        self.size_box.setAccessibleName(translate("ui", "Size"))
        self.size_box.setMinimumWidth(168)
        self.size_box.activated.connect(self._size_picked)
        label = QLabel(translate("ui", "Size:"))
        label.setMinimumWidth(LABEL_WIDTH)
        row = QHBoxLayout()
        row.setSpacing(SPACING)
        row.addWidget(label)
        row.addWidget(self.size_box)
        row.addStretch(1)
        self.strip = ImageStrip(translate("ui", "Preview of the pointer theme"))
        self.strip.hide()
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACING + 4)
        column.addWidget(self.separator())
        column.addLayout(row)
        column.addWidget(self.strip)
        self.add_below(box)

    # ---- what the desktop has

    def read_desktop(self) -> None:
        from ... import desktopparts

        self.desktop_id = self.current_id()
        self.grid.set_in_use(self.desktop_id)
        try:
            self.desktop_size = desktopparts.PARTS["cursor_size"].current(self.window.runner)
        except Exception:  # noqa: BLE001 - what the desktop has is only a hint here
            self.desktop_size = None
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
            self.strip.hide()
            return
        self.strip.set_background(QColor(window))
        self.worker.request(cursor_picker.pointer_images, item, size, dpr)

    def _images_ready(self, images) -> None:
        self.strip.set_rows([images] if images else [])
        self.strip.setVisible(self.strip.has_content())

    # ---- launch feedback

    def open_launch_feedback(self) -> None:
        from ... import desktopparts
        from ..banner import WARNING

        problem = desktopparts.open_system_settings(LAUNCH_FEEDBACK_MODULE, self.window.runner)
        if problem is not None:
            self.window.banner.show_message(WARNING, str(problem), 8)
