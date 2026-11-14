# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The themes of the Themes page: saved themes and installed color schemes as cards."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from .. import library
from ..generators.colorscheme import scheme_groups
from ..model.theme import Theme
from .preview import _rgb
from .widgets import THUMB_SIZE, CardGrid, themed_icon

translate = QCoreApplication.translate

THUMBNAIL = THUMB_SIZE


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
    """Shows the themes as cards and says which one is selected.

    The window's apply button acts on the selection, so there is no second
    button here that could be mistaken for it. Return and a double click open
    the theme in the editor; nothing here puts anything on the desktop.
    """

    selection_changed = Signal()
    edit_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = ""
        self.entries: dict[tuple[str, str], Entry] = {}
        self.grid = CardGrid(
            THUMBNAIL,
            with_search=True,
            fit=False,
            name=translate("ui", "Themes"),
            empty_text=translate("ui", "No theme is saved and no color scheme is installed yet."),
        )
        self.search = self.grid.search
        self.grid.set_filters(
            [("mine", translate("ui", "My themes")), ("schemes", translate("ui", "Color schemes"))],
            empty={
                "mine": translate("ui", "You have no saved themes yet."),
                "schemes": translate("ui", "No color schemes are installed."),
            },
        )
        self.grid.selected.connect(lambda _id: self._update_buttons())
        self.grid.activated.connect(lambda _id: self._emit_edit())
        self.grid.search.textChanged.connect(lambda _text: self._update_buttons())
        self.grid.filter.currentIndexChanged.connect(lambda _index: self._update_buttons())
        self.grid.thumbnail_requested.connect(self._draw)
        self.edit_button = QPushButton(themed_icon("document-edit"), "")
        self.edit_button.clicked.connect(self._emit_edit)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.grid)
        self._update_buttons()

    @staticmethod
    def _id(entry: Entry) -> tuple[str, str]:
        return ("theme" if entry.is_saved_theme else "scheme", entry.scheme_id)

    def reload(self, active: str) -> None:
        """Read the themes again. `active` is the color scheme the desktop uses now."""
        self.active = active
        current = self.current()
        keep = (current.scheme_id, current.is_saved_theme) if current else (active, False)
        bar = self.grid.scroll.verticalScrollBar()
        position = bar.value() if self.entries else None  # keep the place, except the first time
        found = entries()
        self.entries = {self._id(entry): entry for entry in found}
        self.grid.set_items(
            [
                (
                    self._id(entry),
                    entry.title,
                    translate("ui", "Saved theme") if entry.is_saved_theme else "",
                    "mine" if entry.is_saved_theme else "schemes",
                )
                for entry in found
            ]
        )
        in_use = next((self._id(e) for e in found if e.scheme_id == active), None)
        self.grid.set_in_use(in_use)
        chosen = next(
            (
                self._id(e)
                for e in found
                if e.scheme_id == keep[0] and (e.is_saved_theme == keep[1] or e.scheme_id == active)
            ),
            None,
        )
        self.grid.set_selected(chosen)
        if position is not None:
            QTimer.singleShot(0, lambda: bar.setValue(position))
        self._update_buttons()

    def _draw(self, item_id) -> None:
        entry = self.entries.get(item_id)
        if entry is not None:
            self.grid.set_thumbnail(item_id, thumbnail(entry.theme, self.devicePixelRatioF()))

    def current(self) -> Entry | None:
        """The theme that is visibly selected, or None."""
        card = self.grid.card(self.grid.selected_id())
        return self.entries.get(card.item_id) if card is not None and not card.isHidden() else None

    def select(self, scheme_id: str) -> Entry | None:
        for item_id, entry in self.entries.items():
            if entry.scheme_id == scheme_id:
                self.grid.set_selected(item_id)
                self._update_buttons()
                return self.current()
        return None

    def _update_buttons(self) -> None:
        entry = self.current()
        self.edit_button.setEnabled(entry is not None)
        saved = entry is not None and entry.is_saved_theme
        self.edit_button.setText(translate("ui", "Edit") if saved else translate("ui", "Edit a copy"))
        self.selection_changed.emit()

    def _emit_edit(self) -> None:
        entry = self.current()
        if entry is not None:
            self.edit_requested.emit(entry)
