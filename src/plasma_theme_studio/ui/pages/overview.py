# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Overview page: what the theme in the editor changes on the desktop, part by part."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
)

from ...apply.status import BLOCKED, CHANGE, LEAVE
from .base import Page

translate = QCoreApplication.translate


class OverviewPage(Page):
    key = "overview"
    scrolling = False

    def subtitle(self) -> str:
        return translate("ui", "What this theme does to the desktop when you apply it.")

    def build(self) -> None:
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.table = QTableWidget(0, 4)
        self.table.setAccessibleName(translate("ui", "Parts of the desktop"))
        self.table.setHorizontalHeaderLabels(
            [
                translate("ui", "Part"),
                translate("ui", "On the desktop now"),
                translate("ui", "This theme"),
                translate("ui", "When you apply"),
            ]
        )
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.content.addWidget(self.form_widget(("meta", "name"), ("meta", "author")))
        row = QHBoxLayout()
        row.addWidget(self.summary, 1)
        self.content.addLayout(row)
        self.content.addWidget(self.table, 1)

    def refresh(self) -> None:
        self.summary.setText(self.window.apply_summary())
        self.fill(self.window.statuses)  # the statuses may have been read before the page was built
        super().refresh()

    def fill(self, statuses) -> None:
        """Show the parts as `apply.status.parts_status` gives them."""
        if not self.built:
            return
        words = {
            CHANGE: translate("ui", "Will change"),
            LEAVE: translate("ui", "Leave as it is"),
            BLOCKED: translate("ui", "Refused"),
        }
        self.table.setRowCount(len(statuses))
        muted = QBrush(self.palette().placeholderText())
        for number, part in enumerate(statuses):
            cells = (
                str(part.title),
                str(part.desktop),
                str(part.theme),
                str(words.get(part.state, translate("ui", "Same"))),
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if part.state == LEAVE and column:
                    item.setForeground(muted)
                if part.state in (CHANGE, BLOCKED) and column == 3:
                    item.setForeground(QBrush(QColor("#3daee9")))
                self.table.setItem(number, column, item)
        self.table.resizeRowsToContents()
