# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The contrast line of the Colors page: the pairs of colors that are hard to read, or the good news."""

from __future__ import annotations

import math

from PySide6.QtCore import QCoreApplication, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ... import palette
from ..widgets import SPACING, with_alpha

translate = QCoreApplication.translate

MAX_SHOWN = 6  # failing pairs that are listed; the rest is counted


def ratio_text(pair: palette.ContrastPair) -> str:
    """ "3.1:1", cut and not rounded, so that a failing pair never reads as its minimum."""
    return f"{math.floor(pair.ratio * 10 + 1e-9) / 10:.1f}:1"


def sentence(pair: palette.ContrastPair) -> str:
    return translate("ui", "{pair}: {ratio}, should be at least {minimum}:1").format(
        pair=str(pair.label), ratio=ratio_text(pair), minimum=f"{pair.minimum:g}"
    )


class _Chip(QWidget):
    """ "Aa" in one color on another, so the pair can be seen as well as read."""

    def __init__(self, foreground: str, background: str, parent=None):
        super().__init__(parent)
        self.foreground, self.background = QColor(foreground), QColor(background)
        self.setFixedSize(QSize(34, 22))

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


class ContrastBox(QWidget):
    """Shows the failing pairs of `set_colors` and a "Fix contrast" button; `fix_requested` is emitted
    when the button is pressed."""

    fix_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.failing: list[palette.ContrastPair] = []
        self.good = QLabel(translate("ui", "All text is readable."))
        self.good.setWordWrap(True)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)
        self.fix = QPushButton(translate("ui", "Fix contrast"))
        self.fix.setToolTip(
            translate("ui", "Changes the colors that are hard to read, as little as possible.")
        )
        self.fix.clicked.connect(self.fix_requested)
        self.more = QLabel()
        self.more.setForegroundRole(self.more.palette().ColorRole.PlaceholderText)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING)
        layout.addWidget(self.good)
        layout.addLayout(self.rows)
        layout.addWidget(self.more)
        layout.addWidget(self.fix, 0, Qt.AlignmentFlag.AlignLeft)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def set_colors(self, colors: dict[str, str]) -> None:
        self.failing = [pair for pair in palette.contrast_report(colors) if not pair.passes]
        while self.rows.count():
            item = self.rows.takeAt(0)
            row = item.layout()
            while row is not None and row.count():
                widget = row.takeAt(0).widget()
                if widget is not None:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
            if row is not None:
                row.deleteLater()
        for pair in self.failing[:MAX_SHOWN]:
            line = QHBoxLayout()
            line.setSpacing(SPACING)
            label = QLabel(sentence(pair))
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            line.addWidget(
                _Chip(colors[pair.foreground], colors[pair.background]), 0, Qt.AlignmentFlag.AlignTop
            )
            line.addWidget(label, 1)
            self.rows.addLayout(line)
        extra = len(self.failing) - MAX_SHOWN
        self.more.setText(translate("ui", "And {count} more.").format(count=extra) if extra > 0 else "")
        self.more.setVisible(extra > 0)
        self.good.setVisible(not self.failing)
        self.fix.setVisible(bool(self.failing))
