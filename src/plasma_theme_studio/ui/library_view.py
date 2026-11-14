# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Themes tab: saved themes and installed color schemes as pictures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import library
from ..generators.colorscheme import scheme_groups
from ..model.theme import Theme
from .preview import _rgb

translate = QCoreApplication.translate

THUMBNAIL = QSize(168, 104)


@dataclass(frozen=True)
class Entry:
    title: str
    scheme_id: str  # the color scheme name the desktop would report for it
    theme: Theme
    path: Path | None = None  # set for a saved theme file
    scheme: library.InstalledScheme | None = None  # set for an installed color scheme

    @property
    def is_saved_theme(self) -> bool:
        return self.path is not None


def entries() -> list[Entry]:
    saved = [
        Entry(item.theme.name, item.theme.slug, item.theme, path=item.path) for item in library.saved_themes()
    ]
    own = {entry.scheme_id for entry in saved}
    found = saved
    for scheme in library.installed_schemes():
        # A scheme this app wrote from a saved theme is shown once, as the theme.
        if not (scheme.made_here and scheme.id in own):
            found.append(Entry(scheme.name, scheme.id, library.theme_from_scheme(scheme), scheme=scheme))
    return found


def thumbnail(theme: Theme, ratio: float = 1.0, active: bool = False) -> QPixmap:
    groups = {name: dict(values) for name, values in scheme_groups(theme)}
    window, view, button = groups["Colors:Window"], groups["Colors:View"], groups["Colors:Button"]
    header, selection = groups["Colors:Header"], groups["Colors:Selection"]
    accent = _rgb(selection["BackgroundNormal"])
    width, height = THUMBNAIL.width(), THUMBNAIL.height()
    pixmap = QPixmap(THUMBNAIL * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    frame = QRectF(2, 2, width - 4, height - 4)
    outline = QPainterPath()
    outline.addRoundedRect(frame, 7, 7)
    p.save()
    p.setClipPath(outline)
    p.fillRect(frame, _rgb(window["BackgroundNormal"]))
    p.fillRect(QRectF(frame.left(), frame.top(), frame.width(), 16), _rgb(header["BackgroundNormal"]))
    p.fillRect(QRectF(60, 26, width - 70, 44), _rgb(view["BackgroundNormal"]))
    p.restore()
    p.setPen(Qt.PenStyle.NoPen)

    def bar(x, y, length, color, alpha=1.0, thickness=4):
        p.setBrush(_rgb(color, alpha))
        p.drawRoundedRect(QRectF(x, y, length, thickness), thickness / 2, thickness / 2)

    bar(width / 2 - 22, 8, 44, header["ForegroundNormal"], 0.8)
    for index, color in enumerate(("ForegroundNegative", "ForegroundNeutral", "ForegroundPositive")):
        p.setBrush(_rgb(window[color]))
        p.drawEllipse(QPointF(width - 12 - index * 9, 10), 2.5, 2.5)
    # Side list with a selected row
    p.setBrush(accent)
    p.drawRoundedRect(QRectF(8, 38, 46, 12), 3, 3)
    bar(12, 29, 30, window["ForegroundNormal"], 0.85)
    bar(12, 42, 34, selection["ForegroundNormal"])
    bar(12, 57, 26, window["ForegroundNormal"], 0.85)
    bar(12, 70, 32, window["ForegroundInactive"])
    # Text in the view
    bar(67, 33, 70, view["ForegroundNormal"], 0.9)
    bar(67, 43, 52, view["ForegroundInactive"])
    bar(67, 53, 34, view["ForegroundLink"])
    bar(105, 53, 26, view["ForegroundVisited"])
    # Buttons
    for x, focused in ((86, False), (124, True)):
        p.setBrush(_rgb(button["BackgroundNormal"]))
        p.setPen(QPen(accent if focused else _rgb(button["ForegroundNormal"], 0.3), 1))
        p.drawRoundedRect(QRectF(x, 79, 32, 14), 3, 3)
        p.setPen(Qt.PenStyle.NoPen)
        bar(x + 8, 84, 16, button["ForegroundNormal"], 0.85)
    p.setBrush(accent)
    p.drawRoundedRect(QRectF(8, 86, 40, 4), 2, 2)

    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(accent, 3) if active else QPen(_rgb(window["ForegroundNormal"], 0.3), 1))
    p.drawRoundedRect(frame, 7, 7)
    p.end()
    return pixmap


class LibraryView(QWidget):
    use_requested = Signal(object)
    edit_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = ""
        info = QLabel(
            translate(
                "ui",
                "Your saved themes and the color schemes installed on this computer. "
                "Switch the desktop to one of them, or open one in the editor to change it.",
            )
        )
        info.setWordWrap(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText(translate("ui", "Search…"))
        self.search.setAccessibleName(translate("ui", "Search themes"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.list = QListWidget()
        self.list.setAccessibleName(translate("ui", "Themes"))
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setIconSize(THUMBNAIL)
        self.list.setGridSize(QSize(THUMBNAIL.width() + 24, THUMBNAIL.height() + 84))
        self.list.setWordWrap(True)
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        self.list.itemActivated.connect(lambda _item: self._emit(self.edit_requested))
        self.use_button = QPushButton(QIcon.fromTheme("dialog-ok-apply"), translate("ui", "Use on desktop"))
        self.use_button.clicked.connect(lambda: self._emit(self.use_requested))
        self.edit_button = QPushButton(QIcon.fromTheme("document-edit"), "")
        self.edit_button.clicked.connect(lambda: self._emit(self.edit_requested))
        buttons = QHBoxLayout()
        buttons.addWidget(self.search, 1)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.use_button)
        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self._update_buttons()

    def reload(self, active: str) -> None:
        """Read the themes again. `active` is the color scheme the desktop uses now."""
        self.active = active
        current = self.current()
        keep = (current.scheme_id, current.is_saved_theme) if current else (active, False)
        self.list.clear()
        chosen = None
        for entry in entries():
            in_use = entry.scheme_id == active
            lines = [entry.title]
            if entry.is_saved_theme:
                lines.append(translate("ui", "Saved theme"))
            if in_use:
                lines.append(translate("ui", "In use"))
            item = QListWidgetItem(
                QIcon(thumbnail(entry.theme, self.devicePixelRatioF(), in_use)), "\n".join(lines), self.list
            )
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            if in_use:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            if chosen is None and entry.scheme_id == keep[0] and (entry.is_saved_theme == keep[1] or in_use):
                chosen = item
        self._filter(self.search.text())
        if chosen is not None:
            self.list.setCurrentItem(chosen)
            # The grid is laid out later; scroll once it has been.
            QTimer.singleShot(0, lambda: self.list.scrollToItem(self.list.currentItem()))
        self._update_buttons()

    def current(self) -> Entry | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None and not item.isHidden() else None

    def select(self, scheme_id: str) -> Entry | None:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole).scheme_id == scheme_id:
                self.list.setCurrentRow(row)
                return self.current()
        return None

    def _filter(self, text: str) -> None:
        wanted = text.strip().casefold()
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setHidden(wanted not in item.data(Qt.ItemDataRole.UserRole).title.casefold())
        self._update_buttons()

    def _update_buttons(self) -> None:
        entry = self.current()
        self.use_button.setEnabled(entry is not None)
        self.edit_button.setEnabled(entry is not None)
        saved = entry is not None and entry.is_saved_theme
        self.edit_button.setText(translate("ui", "Edit") if saved else translate("ui", "Edit a copy"))

    def _emit(self, signal) -> None:
        entry = self.current()
        if entry is not None:
            signal.emit(entry)
