# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The "Show files…" dialog: every file an apply would write, with its content."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..apply import engine
from .widgets import themed_icon

translate = QCoreApplication.translate


def state_titles() -> dict[str, str]:
    return {
        engine.NEW: translate("ui", "will be created"),
        engine.CHANGED: translate("ui", "will be updated"),
        engine.UNCHANGED: translate("ui", "already up to date"),
        engine.FOREIGN: translate("ui", "exists and was not made by this app"),
    }


class FilesDialog(QDialog):
    """Shows the plan of the window. `fill(plan, summary)` brings it up to date."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(translate("ui", "Files written"))
        self.resize(820, 560)
        self.files_info = QLabel()
        self.files_info.setWordWrap(True)
        # Commands and paths are shown as they are: "<" must not start a tag.
        self.files_info.setTextFormat(Qt.TextFormat.PlainText)
        self.files_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.files_list = QListWidget()
        self.files_list.setAccessibleName(translate("ui", "Files"))
        self.files_list.setMaximumHeight(120)
        self.files_list.currentRowChanged.connect(self._show_file)
        self.file_content = QPlainTextEdit()
        self.file_content.setReadOnly(True)
        self.file_content.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.file_content.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.file_content.setAccessibleName(translate("ui", "Content of the file"))
        open_folder = QPushButton(themed_icon("document-open-folder"), translate("ui", "Open folder"))
        open_folder.clicked.connect(self._open_file_folder)
        close = QPushButton(translate("ui", "Close"))
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(self.files_info, 1)
        row.addWidget(open_folder)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.files_list)
        layout.addWidget(self.file_content, 1)
        layout.addLayout(buttons)

    def fill(self, plan, summary: str) -> None:
        selected = max(self.files_list.currentRow(), 0)
        self.files_list.blockSignals(True)
        self.files_list.clear()
        titles = state_titles()
        for target in plan.targets:
            for status in target.files:
                item = QListWidgetItem(f"{status.file.path} — {titles[status.state]}", self.files_list)
                item.setData(Qt.ItemDataRole.UserRole, status.file)
            for path in target.stale:
                if path.is_file():
                    removed = translate("ui", "no longer needed, will be removed")
                    QListWidgetItem(f"{path} — {removed}", self.files_list)
        self.files_list.blockSignals(False)
        self.files_list.setCurrentRow(min(selected, self.files_list.count() - 1))
        self._show_file(self.files_list.currentRow())
        self.files_info.setText(summary)

    def _show_file(self, row: int) -> None:
        file = self.listed_file(row)
        self.file_content.setPlainText(file.content if file else "")

    def listed_file(self, row: int):
        """The planned file on a row of the list; None for a file that will be removed."""
        item = self.files_list.item(row)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _open_file_folder(self) -> None:
        file = self.listed_file(self.files_list.currentRow())
        if file is not None:
            self.window.open_folder(file.path.parent)
