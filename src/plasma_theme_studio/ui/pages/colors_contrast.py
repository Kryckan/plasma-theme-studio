# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Readability on the Colors page: a short line with a button, and the dialog that shows what "Fix
Contrast" is going to change (each color as it is and as it will be, on the background it is hard to
read on) before it changes anything."""

from __future__ import annotations

import math

from PySide6.QtCore import QCoreApplication, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ... import palette
from ...model.color import Color, contrast
from ..labels import FIELD_LABELS
from ..widgets import LARGE_SPACING, SPACING, with_alpha

translate = QCoreApplication.translate

MAX_CHIPS = 8  # one chip for each color that is hard to read (there are seven text colors and the accent)


def ratio_text(ratio: float) -> str:
    """ "3.1:1", cut and not rounded, so that a failing color never reads as its minimum."""
    return f"{math.floor(ratio * 10 + 1e-9) / 10:.1f}:1"


def failing_roles(colors: dict[str, str]) -> dict[str, palette.ContrastPair]:
    """The worst pair of every color that is hard to read, by role (the order of `palette.ROLES`)."""
    worst: dict[str, palette.ContrastPair] = {}
    for pair in palette.contrast_report(colors):
        if not pair.passes and (pair.foreground not in worst or pair.ratio < worst[pair.foreground].ratio):
            worst[pair.foreground] = pair
    return {role: worst[role] for role in palette.TEXT_ROLES + ("accent",) if role in worst}


class _Chip(QWidget):
    """ "Aa" in one color on another, so the pair can be seen as well as read."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.foreground, self.background = QColor(), QColor()
        self.setFixedSize(QSize(34, 22))

    def set_colors(self, foreground: str, background: str) -> None:
        self.foreground, self.background = QColor(foreground), QColor(background)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(with_alpha(self.palette().text().color(), 0.3), 1))
        p.setBrush(self.background)
        p.drawRoundedRect(rect, 4, 4)
        font = QFont(self.font())
        font.setBold(True)
        p.setFont(font)
        p.setPen(self.foreground)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Aa")


class _Sample(QWidget):
    """A line of sample text in `foreground` on `background`, with a round swatch of the color."""

    def __init__(self, foreground: str, background: str, parent=None):
        super().__init__(parent)
        self.foreground, self.background = QColor(foreground), QColor(background)
        self.text = translate("ui", "Sample text")
        self.setMinimumSize(QSize(150, 34))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(with_alpha(self.palette().text().color(), 0.25), 1))
        p.setBrush(self.background)
        p.drawRoundedRect(rect, 6, 6)
        dot = QRectF(rect.left() + 9, rect.center().y() - 6, 12, 12)
        p.setPen(QPen(with_alpha(self.palette().text().color(), 0.3), 1))
        p.setBrush(self.foreground)
        p.drawEllipse(dot)
        p.setPen(self.foreground)
        p.drawText(
            rect.adjusted(30, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text
        )


class ContrastBox(QWidget):
    """One line about readability and the button "Fix Contrast…"; `fix_requested` is emitted when it is
    pressed. The pairs that fail are shown as small "Aa" chips, never as a list."""

    fix_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.failing: dict[str, palette.ContrastPair] = {}
        self.sentence = QLabel()
        self.sentence.setWordWrap(True)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(4)
        self.pool = [_Chip(self) for _ in range(MAX_CHIPS)]  # made once, shown as far as they are needed
        for chip in self.pool:
            chip.hide()
            self.chips.addWidget(chip)
        self.fix = QPushButton(translate("ui", "Fix Contrast…"))
        self.fix.setToolTip(
            translate("ui", "Shows which colors would change, as little as possible, before it changes them.")
        )
        self.fix.clicked.connect(self.fix_requested)
        row = QHBoxLayout()
        row.setSpacing(SPACING)
        row.addLayout(self.chips)
        row.addStretch(1)
        row.addWidget(self.fix)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING)
        layout.addWidget(self.sentence)
        layout.addLayout(row)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def set_colors(self, colors: dict[str, str]) -> None:
        self.failing = failing_roles(colors)
        shown = list(self.failing.values())[:MAX_CHIPS]
        for number, chip in enumerate(self.pool):
            chip.setVisible(number < len(shown))
            if number < len(shown):
                pair = shown[number]
                chip.set_colors(colors[pair.foreground], colors[pair.background])
                chip.setToolTip(str(pair.label))
        if self.failing:
            self.sentence.setText(translate("ui", "Some text is hard to read on its background."))
        else:
            self.sentence.setText(translate("ui", "All text is readable."))
        self.fix.setVisible(bool(self.failing))


class FixContrastDialog(QDialog):
    """What "Fix Contrast" would change: each color as it is now and as it would be, on the background it
    is hard to read on. "Fix" accepts, "Cancel" rejects; nothing is changed here."""

    def __init__(self, old: dict[str, str], new: dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("ui", "Fix Contrast"))
        self.setModal(True)
        self.old, self.new = dict(old), dict(new)
        self.changed = [role for role in palette.TEXT_ROLES + ("accent",) if old.get(role) != new.get(role)]
        failing = failing_roles(old)

        intro = QLabel(
            translate(
                "ui",
                "These colors are hard to read on their background. They will be changed as little as "
                "possible and keep their hue.",
            )
        )
        intro.setWordWrap(True)
        grid = QGridLayout()
        grid.setHorizontalSpacing(LARGE_SPACING)
        grid.setVerticalSpacing(LARGE_SPACING)
        grid.setColumnStretch(0, 1)
        for row, role in enumerate(self.changed):
            pair = failing.get(role)
            surface = pair.background if pair is not None else "window"
            background = old[surface]
            name = QLabel(str(FIELD_LABELS[("colors", role)]))
            font = name.font()
            font.setBold(True)
            name.setFont(font)
            where = QLabel(
                translate("ui", "Hard to read on the {background}.").format(
                    background=str(palette.surface_label(surface))
                )
            )
            numbers = QLabel(
                translate("ui", "Contrast: {old} now, {new} after.").format(
                    old=ratio_text(contrast(Color.parse(old[role]), Color.parse(background))),
                    new=ratio_text(contrast(Color.parse(new[role]), Color.parse(background))),
                )
            )
            for detail in (where, numbers):  # short lines that are not wrapped, so they are never cut
                detail.setForegroundRole(detail.palette().ColorRole.PlaceholderText)
            words = QVBoxLayout()
            words.setSpacing(2)
            words.addWidget(name)
            words.addWidget(where)
            words.addWidget(numbers)
            before, after = _Sample(old[role], background), _Sample(new[role], background)
            before.setAccessibleName(translate("ui", "{color} now").format(color=name.text()))
            after.setAccessibleName(translate("ui", "{color} after").format(color=name.text()))
            arrow = QLabel("→")
            arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addLayout(words, row, 0)
            grid.addWidget(before, row, 1, Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(arrow, row, 2)
            grid.addWidget(after, row, 3, Qt.AlignmentFlag.AlignVCenter)
        buttons = QDialogButtonBox()
        self.fix_button = buttons.addButton(translate("ui", "Fix"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = buttons.addButton(
            translate("ui", "Cancel"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self.fix_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(LARGE_SPACING)
        layout.addWidget(intro)
        layout.addLayout(grid)
        layout.addWidget(buttons)
        self.setMinimumWidth(760)
