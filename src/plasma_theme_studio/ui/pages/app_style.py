# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Application Style page: the style of buttons, fields and menus in Qt applications."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import QBoxLayout, QLabel, QPushButton, QStackedLayout, QVBoxLayout, QWidget

from ...generators import kvantum
from ..style_preview import StylePreview
from ..widgets import LARGE_SPACING, SPACING, InlineNote
from . import small_settings
from .base import TUNING_WIDTH, PickerPage
from .pickers_common import LoadsInBackground

translate = QCoreApplication.translate

STYLE_DELAY = 250  # milliseconds after the last edit before the style is made again
SIDE_BY_SIDE = 1130  # page width from which the values and the sample sit side by side


class AppStylePage(LoadsInBackground, PickerPage):
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

    def build(self) -> None:
        super().build()
        self.configure_button = QPushButton(translate("ui", "Configure Icons and Toolbars…"))
        self.configure_button.setToolTip(
            translate("ui", "Sets how toolbars show their buttons, and the icon sizes, in this theme.")
        )
        self.configure_button.clicked.connect(self.configure)
        self.header.add_action(self.configure_button)

        # the values of "This theme" on the left, the real widgets in that style on the right
        self.content.removeWidget(self.tuning_box)
        self.tuning_box.setMaximumWidth(TUNING_WIDTH - 140)
        self.tuning_box.layout().itemAt(
            0
        ).widget().hide()  # the rule above the values: they sit beside the sample now
        self.style_preview = StylePreview(self.theme)
        self.style_preview.setMinimumHeight(240)
        self.sentence = QLabel()
        self.sentence.setWordWrap(True)
        self.sentence.setForegroundRole(self.sentence.palette().ColorRole.PlaceholderText)
        self.stack_holder = QWidget()
        self.stack = QStackedLayout(self.stack_holder)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.style_preview)
        self.stack.addWidget(self.sentence)
        sample = QVBoxLayout()
        sample.setSpacing(SPACING)
        sample.addWidget(self.caption(translate("ui", "Sample")))
        sample.addWidget(self.stack_holder, 1)
        row = self.beside = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        row.setSpacing(LARGE_SPACING + 8)
        row.addWidget(self.tuning_box, 1, Qt.AlignmentFlag.AlignTop)
        row.addLayout(sample, 1)
        row.setAlignment(sample, Qt.AlignmentFlag.AlignTop)
        holder = QWidget()
        holder.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.add_below(holder)

        self.kvantum_note = InlineNote(
            translate(
                "ui",
                "Kvantum is not installed. It is the program that draws the style “This theme” in "
                "applications, so install the package “kvantum” with your software manager (on Debian "
                "and Ubuntu it is called “qt6-style-kvantum”). The other styles work without it.",
            ),
            "warning",
        )
        self.kvantum_note.setVisible(self.kvantum_missing())
        self.add_below(self.kvantum_note)

        self.arrange()
        self.timer = QTimer(self, singleShot=True, interval=STYLE_DELAY)
        self.timer.timeout.connect(self.draw_sample)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "beside"):  # not before the page is built
            self.arrange()

    def arrange(self) -> None:
        """The values and the sample go side by side when there is room, else one under the other."""
        side_by_side = self.width() >= SIDE_BY_SIDE
        direction = QBoxLayout.Direction.LeftToRight if side_by_side else QBoxLayout.Direction.TopToBottom
        if self.beside.direction() != direction:
            self.beside.setDirection(direction)

    def read_state(self) -> dict:
        """Besides what the desktop has: whether Kvantum is there (it looks through many folders)."""
        state = super().read_state()
        state["kvantum_missing"] = not (
            kvantum.plugin_installed() or self.window.runner.which("kvantummanager")
        )
        return state

    def after_desktop(self) -> None:
        self.kvantum_note.setVisible(self.kvantum_missing())

    def kvantum_missing(self) -> bool:
        """Not known (so not said) until the worker has looked."""
        return bool((self.desktop_state or {}).get("kvantum_missing"))

    def configure(self) -> None:
        """Open the dialog of the toolbar and icon settings; what it holds goes into the theme."""
        small_settings.open_toolbars(self.window)

    def draw_sample(self) -> None:
        """Show the real widgets in the style of "This theme", or say why there are none."""
        mode = self.theme.part_state("apps", "style")
        if mode == "generated":
            self.style_preview.set_theme(self.theme)
            self.stack.setCurrentWidget(self.style_preview)
            return
        if mode == "installed":
            item = self.items.get(self._match(self.theme.get("apps", "style_id")))
            name = item.name if item is not None else ""
            text = translate("ui", "{style} draws the applications. Its own picture is on the card above.")
            self.sentence.setText(text.format(style=name or translate("ui", "The chosen style")))
        else:
            self.sentence.setText(
                translate(
                    "ui",
                    "The application style is left as it is. Choose “This theme” to see buttons, fields "
                    "and menus drawn in the style that is made from it.",
                )
            )
        self.stack.setCurrentWidget(self.sentence)

    def refresh(self) -> None:
        super().refresh()
        self.kvantum_note.setVisible(self.kvantum_missing())
        if self.theme.part_state("apps", "style") != "generated":
            self.draw_sample()  # a sentence: no need to wait
        self.timer.start()  # making the style takes a moment: wait for the edits to stop
