# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The "Show files…" dialog: what Apply puts on the computer, file by file, with each file's content."""

from __future__ import annotations

from pathlib import Path

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
from .widgets import LARGE_SPACING, SPACING, themed_icon

translate = QCoreApplication.translate


def state_titles() -> dict[str, str]:
    return {
        engine.NEW: translate("ui", "will be created"),
        engine.CHANGED: translate("ui", "will be updated"),
        engine.UNCHANGED: translate("ui", "already up to date"),
        engine.FOREIGN: translate("ui", "already there, made by something else"),
    }


VISIBLE_ROWS = 5  # a list is as tall as its rows, up to this many; then it scrolls


def shown_path(path: Path) -> str:
    """A path as a person writes it: the home folder as "~"."""
    text = str(path)
    home = str(Path.home())
    return "~" + text[len(home) :] if text == home or text.startswith(home + "/") else text


class FilesDialog(QDialog):
    """Shows the plan of the window in three lists (written, already up to date, removed) and the
    content of the selected file. `fill(plan, summary)` brings it up to date."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(translate("ui", "Files"))
        self.resize(860, 640)
        title = QLabel(
            translate(
                "ui",
                "These are the files Apply puts on your computer. Nothing is written until you choose "
                "Apply to Desktop.",
            )
        )
        title.setWordWrap(True)
        title.setTextFormat(Qt.TextFormat.PlainText)
        self.files_title = title
        self.files_info = QLabel()
        self.files_info.setWordWrap(True)
        # Commands and paths are shown as they are: "<" must not start a tag.
        self.files_info.setTextFormat(Qt.TextFormat.PlainText)
        self.files_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.files_info.setForegroundRole(self.files_info.palette().ColorRole.PlaceholderText)

        self.files_new = self._list()
        self.files_current = self._list()
        self.files_removed = self._list()
        self.lists = (self.files_new, self.files_current, self.files_removed)
        self.heading_titles = (
            translate("ui", "Will be written"),
            translate("ui", "Already up to date"),
            translate("ui", "Will be removed"),
        )
        self.headings = tuple(QLabel(title) for title in self.heading_titles)
        for heading in self.headings:
            font = heading.font()
            font.setBold(True)
            heading.setFont(font)
        self.files_new.setAccessibleName(translate("ui", "Files that will be written"))
        self.files_current.setAccessibleName(translate("ui", "Files that are already up to date"))
        self.files_removed.setAccessibleName(translate("ui", "Files that will be removed"))

        self.content_heading = QLabel(translate("ui", "Content of the selected file"))
        font = self.content_heading.font()
        font.setBold(True)
        self.content_heading.setFont(font)
        self.file_content = QPlainTextEdit()
        self.file_content.setReadOnly(True)
        self.file_content.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.file_content.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.file_content.setAccessibleName(translate("ui", "Content of the file"))
        self.open_folder = QPushButton(themed_icon("document-open-folder"), translate("ui", "Open folder"))
        self.open_folder.clicked.connect(self._open_file_folder)
        self.close_button = QPushButton(translate("ui", "Close"))
        self.close_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self.open_folder)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(LARGE_SPACING)
        layout.addWidget(title)
        layout.addWidget(self.files_info)
        for heading, files in zip(self.headings, self.lists, strict=True):
            section = QVBoxLayout()
            section.setSpacing(SPACING)
            section.addWidget(heading)
            section.addWidget(files)
            layout.addLayout(section)
        view = QVBoxLayout()
        view.setSpacing(SPACING)
        view.addWidget(self.content_heading)
        view.addWidget(self.file_content, 1)
        layout.addLayout(view, 1)
        layout.addLayout(buttons)

    def _list(self) -> QListWidget:
        files = QListWidget()
        files.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        files.currentItemChanged.connect(lambda item, _before, files=files: self._selected(files, item))
        return files

    def _selected(self, files: QListWidget, item) -> None:
        """One file is selected in all three lists together: the others let go of theirs."""
        if item is None:
            return
        for other in self.lists:
            if other is not files and other.currentRow() >= 0:
                other.blockSignals(True)
                other.setCurrentRow(-1)
                other.clearSelection()
                other.blockSignals(False)
        file = item.data(Qt.ItemDataRole.UserRole)
        self.file_content.setPlainText(file.content if file else "")

    def fill(self, plan, summary: str) -> None:
        before = self.selected_path()
        for files in self.lists:
            files.blockSignals(True)
            files.clear()
        titles = state_titles()
        for target in plan.targets:
            for status in target.files:
                where = self.files_current if status.state == engine.UNCHANGED else self.files_new
                text = shown_path(status.file.path)
                if status.state == engine.FOREIGN:
                    text = f"{text} — {titles[status.state]}"
                item = QListWidgetItem(text, where)
                item.setData(Qt.ItemDataRole.UserRole, status.file)
                item.setToolTip(str(status.file.path))
            for path in target.stale:
                if path.is_file():
                    item = QListWidgetItem(shown_path(path), self.files_removed)
                    item.setToolTip(str(path))
        for title, heading, files in zip(self.heading_titles, self.headings, self.lists, strict=True):
            files.blockSignals(False)
            rows = files.count()
            heading.setVisible(rows > 0)
            files.setVisible(rows > 0)
            heading.setText(f"{title} ({rows})")
            if rows:
                height = files.sizeHintForRow(0) * min(rows, VISIBLE_ROWS) + 2 * files.frameWidth() + 2
                files.setFixedHeight(height)
        self.select_path(before)
        self.files_info.setText(summary)
        self.files_info.setVisible(bool(summary))

    def rows(self) -> list[str]:
        """The text of every listed file, in the order of the three lists."""
        return [files.item(row).text() for files in self.lists for row in range(files.count())]

    def selected_path(self):
        file = self.listed_file()
        return file.path if file else None

    def select_path(self, path) -> None:
        """Select the file at `path` if it is listed, else the first file (the content follows)."""
        first = None
        for files in self.lists:
            for row in range(files.count()):
                file = files.item(row).data(Qt.ItemDataRole.UserRole)
                first = first or (files, row)
                if path is not None and file is not None and file.path == path:
                    files.setCurrentRow(row)
                    return
        if first is not None:
            first[0].setCurrentRow(first[1])
        else:
            self.file_content.setPlainText("")

    def listed_file(self, row: int | None = None):
        """The planned file that is selected (or, with `row`, on that row of the lists counted
        together); None for a file that will be removed or when there is no file."""
        if row is None:
            for files in self.lists:
                if files.currentRow() >= 0:
                    return files.currentItem().data(Qt.ItemDataRole.UserRole)
            return None
        for files in self.lists:
            if row < files.count():
                return files.item(row).data(Qt.ItemDataRole.UserRole)
            row -= files.count()
        return None

    def _open_file_folder(self) -> None:
        file = self.listed_file()
        if file is not None:
            self.window.open_folder(file.path.parent)
