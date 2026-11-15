# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The controls of the light and dark variants: the Light | Dark switch and the row of the Colors page.

Switching only changes which variant the editor shows (and every preview with it); it is not a step of
the undo stack. Adding and removing a variant is.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..model.theme import Theme
from ..model.variants import DARK, LIGHT, VARIANTS, opposite
from .widgets import MoreAbout, Segmented

translate = QCoreApplication.translate


def variant_name(variant: str) -> str:
    return translate("ui", "Dark") if variant == DARK else translate("ui", "Light")


class VariantSwitch(Segmented):
    """Light | Dark. `chosen` carries "light" or "dark" when the person picks one."""

    chosen = Signal(str)

    def __init__(self, parent=None):
        super().__init__(
            [variant_name(v) for v in VARIANTS], 0, name=translate("ui", "Variant"), parent=parent
        )
        self.changed.connect(lambda index: self.chosen.emit(VARIANTS[index]))

    def set_variant(self, variant: str) -> None:
        self.set_current(VARIANTS.index(variant))


class VariantRow(QWidget):
    """The top of the Colors page. A theme with one variant offers to add the other; a theme with both
    has the switch and a button that removes the variant that is shown."""

    chosen = Signal(str)
    add_requested = Signal()
    remove_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel(translate("ui", "Variant:"))
        self.switch = VariantSwitch()
        self.switch.chosen.connect(self.chosen)
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self.add_requested)
        self.remove_button = QPushButton()
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self._shown))
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setForegroundRole(self.note.palette().ColorRole.PlaceholderText)
        self.more = MoreAbout()
        self._shown = LIGHT
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.label, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.switch)
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.note)
        layout.addWidget(self.more)

    def show_theme(self, theme: Theme) -> None:
        both = theme.has_both
        self._shown = theme.shown_variant
        self.label.setVisible(both)
        self.switch.setVisible(both)
        self.remove_button.setVisible(both)
        self.add_button.setVisible(not both)
        if both:
            self.switch.set_variant(self._shown)
            self.remove_button.setText(
                translate("ui", "Remove the Dark Variant")
                if self._shown == DARK
                else translate("ui", "Remove the Light Variant")
            )
            self.note.setText(
                translate(
                    "ui",
                    "The colors on this page are those of the variant above. Shapes, fonts and everything "
                    "else are the same in both. Apply puts the variant you see on the desktop.",
                )
            )
            self.more.set_detail("")
        else:
            missing = opposite(theme.main_variant)
            self.add_button.setText(
                translate("ui", "Add a Dark Variant")
                if missing == DARK
                else translate("ui", "Add a Light Variant")
            )
            self.note.setText(
                translate(
                    "ui",
                    "This theme has one set of colors. You can add a second set for the other mode: "
                    "light colors become dark ones, or the other way round.",
                )
            )
            self.more.set_detail(
                translate(
                    "ui",
                    "The second set is made from the first by keeping the hues, turning the lightness "
                    "around and correcting the text colors so that they stay easy to read. You can change "
                    "every color of it afterwards.",
                )
            )
