# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
""" "Colors from a Picture": which picture (the wallpaper or any other) and who finds the colors (the app
itself, or matugen or pywal when they are installed). The colors are found in a worker, so the window
stays alive while a tool runs; the result is handed on to the import dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from ... import palette
from ..widgets import LARGE_SPACING, SPACING
from . import colors_tools as tools

translate = QCoreApplication.translate

PICTURE_FILTER = " (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff *.avif *.jxl)"


class _Answer(QObject):
    done = Signal(int, object)  # (the number of the job, a PaletteResult)


class _Job(QRunnable):
    def __init__(self, number: int, runner, tool: str, picture: Path, answer: _Answer):
        super().__init__()
        self.number, self.runner, self.tool, self.picture, self.answer = number, runner, tool, picture, answer

    def run(self) -> None:
        try:
            result = tools.find_colors(self.runner, self.tool, self.picture)
        except Exception:  # noqa: BLE001 - never leave the dialog waiting
            result = palette.PaletteResult(error=translate("core", "The image cannot be read."))
        try:
            self.answer.done.emit(self.number, result)
        except RuntimeError:  # the dialog is gone
            pass


class PictureColorsDialog(QDialog):
    """Asks which picture and which way, finds the colors and accepts. Afterwards `result` has the
    colors, `picture` the picture they come from and `tool` the way that found them.

    `wallpaper` is the picture of the wallpaper (None when there is none, which is then said);
    `picture` starts as `chosen` when the person already chose a picture."""

    def __init__(
        self, runner, wallpaper: Path | None, chosen: Path | None = None, reason: str = "", parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle(translate("ui", "Colors from a Picture"))
        self.setModal(True)
        self.runner, self.wallpaper = runner, wallpaper
        self.other: Path | None = chosen
        self.picture: Path | None = None
        self.tool = tools.BUILTIN
        self.result: palette.PaletteResult | None = None
        self.number = 0
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.answer = _Answer(self)
        self.answer.done.connect(self._found, Qt.ConnectionType.QueuedConnection)

        intro = QLabel(
            translate(
                "ui",
                "Choose the picture the colors are taken from. You see the colors and can change them "
                "before anything is used.",
            )
        )
        intro.setWordWrap(True)

        self.use_wallpaper = QRadioButton(translate("ui", "The wallpaper"))
        self.use_other = QRadioButton(translate("ui", "Another picture"))
        self.wallpaper_note = QLabel(reason if wallpaper is None else "")
        self.wallpaper_note.setWordWrap(True)
        self.wallpaper_note.setForegroundRole(self.wallpaper_note.palette().ColorRole.PlaceholderText)
        self.use_wallpaper.setEnabled(wallpaper is not None)
        self.choose_button = QPushButton(translate("ui", "Choose…"))
        self.choose_button.clicked.connect(lambda: self.choose())
        self.name = QLabel()
        self.name.setForegroundRole(self.name.palette().ColorRole.PlaceholderText)
        pictures = QButtonGroup(self)
        pictures.addButton(self.use_wallpaper)
        pictures.addButton(self.use_other)
        self.use_other.toggled.connect(self._picture_changed)
        other_row = QHBoxLayout()
        other_row.setSpacing(SPACING)
        other_row.addWidget(self.use_other)
        other_row.addWidget(self.choose_button)
        other_row.addWidget(self.name, 1)

        self.ways: dict[str, QRadioButton] = {}
        ways = QButtonGroup(self)
        way_box = QVBoxLayout()
        way_box.setSpacing(SPACING)
        for tool, title, note in (
            (tools.BUILTIN, translate("ui", "Built in"), translate("ui", "Always available.")),
            ("matugen", "matugen", ""),
            ("pywal", "pywal", ""),
        ):
            button = QRadioButton(title)
            installed = tools.installed(runner, tool)
            button.setEnabled(installed)
            button.toggled.connect(lambda on, tool=tool: on and self._way_chosen(tool))
            ways.addButton(button)
            self.ways[tool] = button
            line = QHBoxLayout()
            line.setSpacing(SPACING)
            line.addWidget(button)
            text = (
                note
                if installed
                else translate("ui", "{tool} is not installed on this computer.").format(tool=title)
            )
            label = QLabel(text)
            label.setForegroundRole(label.palette().ColorRole.PlaceholderText)
            line.addWidget(label, 1)
            way_box.addLayout(line)
        self.ways[tools.BUILTIN].setChecked(True)

        self.status = QLabel()
        self.status.setWordWrap(True)
        buttons = QDialogButtonBox()
        self.find_button = buttons.addButton(
            translate("ui", "Find Colors"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.cancel_button = buttons.addButton(
            translate("ui", "Cancel"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self.find_button.setDefault(True)
        self.find_button.clicked.connect(self.find)
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(LARGE_SPACING)
        layout.addWidget(intro)
        layout.addWidget(self._caption(translate("ui", "Picture")))
        layout.addWidget(self.use_wallpaper)
        layout.addWidget(self.wallpaper_note)
        layout.addLayout(other_row)
        layout.addWidget(self._caption(translate("ui", "Find the colors with")))
        layout.addLayout(way_box)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        self.setMinimumWidth(520)

        if wallpaper is not None and chosen is None:
            self.use_wallpaper.setChecked(True)
        else:
            self.use_other.setChecked(True)
        self._picture_changed()

    def _caption(self, text: str) -> QLabel:
        label = QLabel(text)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label

    # ---- choosing

    def choose(self, path: str | None = None) -> None:
        """Another picture, from a file dialog (or `path`)."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                translate("ui", "Choose a Picture"),
                "",
                translate("ui", "Pictures") + PICTURE_FILTER,
            )
            if not path:
                return
        self.other = Path(path)
        self.use_other.setChecked(True)
        self._picture_changed()

    def _picture_changed(self, *_) -> None:
        self.picture = self.other if self.use_other.isChecked() else self.wallpaper
        self.name.setText(self.other.name if self.other is not None else "")
        self.find_button.setEnabled(self.picture is not None)
        if self.picture is None:
            self.status.setText(translate("ui", "Choose a picture first."))
        else:
            self.status.setText("")

    def _way_chosen(self, tool: str) -> None:
        self.tool = tool

    # ---- finding

    def find(self) -> None:
        """Start finding the colors; the dialog accepts when they are there."""
        if self.picture is None:
            return
        self.number += 1
        self.find_button.setEnabled(False)
        self.status.setText(translate("ui", "Finding colors…"))
        self.pool.start(_Job(self.number, self.runner, self.tool, self.picture, self.answer))

    def _found(self, number: int, result) -> None:
        if number != self.number:
            return
        if result.ok:
            self.result = result
            self.accept()
            return
        self.status.setText(str(result.error))
        self.find_button.setEnabled(self.picture is not None)

    def reject(self) -> None:
        self.number += 1  # a tool that is still running is no longer waited for
        super().reject()
