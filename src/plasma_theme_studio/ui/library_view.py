# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The themes of the Themes page: saved themes, installed Global Themes and color schemes as cards."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from .. import library, pickers
from ..generators.colorscheme import scheme_groups
from ..model.theme import Theme
from ..pickers.base import Item
from .preview import _rgb
from .widgets import THUMB_SIZE, CardGrid, FlowLayout, Segmented, themed_icon

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

    @property
    def is_global(self) -> bool:
        return False


@dataclass(frozen=True)
class GlobalEntry(Entry):
    """An installed Global Theme. Its `theme` is only a stand-in: what the package sets is read
    from the package (`item`) when it is shown or loaded."""

    item: Item | None = None

    @property
    def is_global(self) -> bool:
        return True


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


def global_entries() -> list[GlobalEntry]:
    """The installed Global Themes, by name."""
    picker = pickers.kind("global_theme")
    try:
        items = list(picker.items()) if picker else []
    except Exception:  # noqa: BLE001 - a folder that cannot be read must not empty the whole page
        items = []
    stand_in = Theme.from_preset("breeze-light")
    return [GlobalEntry(item.name, "", stand_in, item=item) for item in items]


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


class JustifiedFlow(FlowLayout):
    """A flow of equal cards that shares the room left in a row between the gaps, so that the first
    column sits at the left edge and the last at the right edge. A row that is not full keeps the
    ordinary gap, and the cards of the last row stand in the same columns."""

    def _flow(self, rect, place):
        m = self.contentsMargins()
        inner = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        items = [item for item in self._items if not item.isEmpty()]
        if not items:
            return m.top() + m.bottom()
        cell_w = max(item.sizeHint().width() for item in items)
        cell_h = max(item.sizeHint().height() for item in items)
        columns = max(1, (inner.width() + self._h) // (cell_w + self._h))
        gap = self._h
        if columns > 1 and len(items) >= columns:
            gap = max(self._h, (inner.width() - columns * cell_w) // (columns - 1))
        parent = self.parentWidget()
        rtl = parent is not None and parent.layoutDirection() == Qt.LayoutDirection.RightToLeft
        for number, item in enumerate(items):
            row, column = divmod(number, columns)
            x = column * (cell_w + gap)
            left = inner.right() + 1 - x - cell_w if rtl else inner.x() + x
            if place:
                item.setGeometry(QRect(QPoint(left, inner.y() + row * (cell_h + self._v)), item.sizeHint()))
        rows = -(-len(items) // columns)
        return rows * cell_h + (rows - 1) * self._v + m.top() + m.bottom()


class ThemeGrid(CardGrid):
    """The grid of the Themes page. The filter is chosen with chips (`LibraryView.chips`), so the combo
    that holds the groups stays hidden, and the cards fill the width."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.flow.__class__ = JustifiedFlow

    def _update_state(self) -> None:
        super()._update_state()
        self.filter.hide()


class LibraryView(QWidget):
    """Shows the themes as cards and says which one is selected.

    The window's apply button acts on the selection, so there is no second
    button here that could be mistaken for it. Return and a double click open
    the theme in the editor; nothing here puts anything on the desktop. The pictures of
    Global Themes come from the window's thumbnail `loader`.
    """

    selection_changed = Signal()
    edit_requested = Signal(object)

    GROUPS = ("", "mine", "global", "schemes")  # the chips, in order; "" is All

    def __init__(self, loader=None, parent=None):
        super().__init__(parent)
        self.loader = loader
        self.active = ""
        self.global_active = ""
        self.entries: dict[tuple[str, str], Entry] = {}
        self.grid = ThemeGrid(
            THUMBNAIL,
            with_search=True,
            fit=False,
            name=translate("ui", "Themes"),
            empty_text=translate(
                "ui",
                "Nothing is installed yet. “New Theme from the Desktop” starts from what your desktop "
                "uses now.",
            ),
        )
        self.search = self.grid.search
        self.grid.set_filters(
            [
                ("mine", translate("ui", "My themes")),
                ("global", translate("ui", "Global Themes")),
                ("schemes", translate("ui", "Color schemes")),
            ],
            empty={
                "mine": translate("ui", "You have no saved themes yet."),
                "global": translate(
                    "ui", "No Global Themes are installed. “Open in System Settings…” gets some."
                ),
                "schemes": translate("ui", "No color schemes are installed."),
            },
        )
        self.chips = Segmented(
            [
                translate("widgets", "All"),
                translate("ui", "My themes"),
                translate("ui", "Global Themes"),
                translate("ui", "Color schemes"),
            ],
            name=translate("ui", "Kind of theme"),
        )
        self.chips.changed.connect(self.grid.filter.setCurrentIndex)
        self.grid.filter.currentIndexChanged.connect(self.chips.set_current)
        self.grid.bar.layout().insertWidget(0, self.chips)
        self.grid.selected.connect(lambda _id: self._update_buttons())
        self.grid.activated.connect(lambda _id: self._emit_edit())
        self.grid.search.textChanged.connect(lambda _text: self._update_buttons())
        self.grid.filter.currentIndexChanged.connect(lambda _index: self._update_buttons())
        self.grid.thumbnail_requested.connect(self._draw)
        if loader is not None:
            loader.ready.connect(self._picture_ready)
        self.edit_button = QPushButton(themed_icon("document-edit"), "")
        self.edit_button.clicked.connect(self._emit_edit)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.grid)
        self._update_buttons()

    @staticmethod
    def _id(entry: Entry) -> tuple[str, str]:
        if entry.is_global:
            return ("global", entry.item.id)
        return ("theme" if entry.is_saved_theme else "scheme", entry.scheme_id)

    @staticmethod
    def _group(entry: Entry) -> str:
        if entry.is_global:
            return "global"
        return "mine" if entry.is_saved_theme else "schemes"

    @staticmethod
    def _kind_word(entry: Entry) -> str:
        if entry.is_global:
            return translate("ui", "Global Theme")
        return translate("ui", "Saved theme") if entry.is_saved_theme else translate("ui", "Color scheme")

    def reload(self, active: str, global_active: str = "") -> None:
        """Read the themes again. `active` is the color scheme the desktop uses now, `global_active`
        the Global Theme it records."""
        self.active, self.global_active = active, global_active
        current = self.current()
        keep = (current.scheme_id, current.is_saved_theme) if current else (active, False)
        keep_global = self._id(current) if current is not None and current.is_global else None
        bar = self.grid.scroll.verticalScrollBar()
        position = bar.value() if self.entries else None  # keep the place, except the first time
        saved_and_schemes = entries()
        found = [e for e in saved_and_schemes if e.is_saved_theme]
        found += global_entries()
        found += [e for e in saved_and_schemes if not e.is_saved_theme]
        self.entries = {self._id(entry): entry for entry in found}
        self.grid.set_items([(self._id(e), e.title, self._kind_word(e), self._group(e)) for e in found])
        in_use = next((self._id(e) for e in found if not e.is_global and e.scheme_id == active), None)
        self.grid.set_in_use(in_use)
        card = self.grid.card(("global", global_active)) if global_active else None
        if card is not None:
            card.set_in_use(True)
        chosen = keep_global if keep_global in self.entries else None
        if chosen is None:
            chosen = next(
                (
                    self._id(e)
                    for e in found
                    if not e.is_global
                    and e.scheme_id == keep[0]
                    and (e.is_saved_theme == keep[1] or e.scheme_id == active)
                ),
                None,
            )
        self.grid.set_selected(chosen)
        if position is not None:
            QTimer.singleShot(0, lambda: bar.setValue(position))
        self._update_buttons()

    def _draw(self, item_id) -> None:
        entry = self.entries.get(item_id)
        if entry is None:
            return
        if not entry.is_global:
            self.grid.set_thumbnail(item_id, thumbnail(entry.theme, self.devicePixelRatioF()))
            return
        picker = pickers.kind("global_theme")
        if self.loader is None or picker is None:
            self.grid.set_no_preview(item_id)
            return
        image = self.loader.request(picker, entry.item, QSize(THUMBNAIL), self.devicePixelRatioF())
        if image is not None:
            self._set_picture(item_id, image)

    def _picture_ready(self, kind_key: str, item_id: str, image) -> None:
        if kind_key == "global_theme" and self.grid.card(("global", item_id)) is not None:
            self._set_picture(("global", item_id), image)

    def _set_picture(self, item_id, image) -> None:
        if image.isNull():
            self.grid.set_no_preview(item_id)
        else:
            self.grid.set_thumbnail(item_id, image)

    def leave(self) -> None:
        """The page is not shown: stop drawing pictures, and ask again when it is."""
        if self.loader is not None:
            self.loader.cancel("global_theme")
        self.grid.ask_again_for_thumbnails()

    def current(self) -> Entry | None:
        """The theme that is visibly selected, or None."""
        card = self.grid.card(self.grid.selected_id())
        return self.entries.get(card.item_id) if card is not None and not card.isHidden() else None

    def select(self, scheme_id: str) -> Entry | None:
        for item_id, entry in self.entries.items():
            if not entry.is_global and entry.scheme_id == scheme_id:
                self.grid.set_selected(item_id)
                self._update_buttons()
                return self.current()
        return None

    def select_global(self, package_id: str) -> GlobalEntry | None:
        """Select the Global Theme with this package id."""
        if ("global", package_id) not in self.entries:
            return None
        self.grid.set_selected(("global", package_id))
        self._update_buttons()
        return self.current()

    def _update_buttons(self) -> None:
        entry = self.current()
        self.edit_button.setEnabled(entry is not None)
        if entry is not None and entry.is_global:
            text = translate("ui", "Load into the editor")
        elif entry is not None and entry.is_saved_theme:
            text = translate("ui", "Edit")
        else:
            text = translate("ui", "Edit a copy")
        self.edit_button.setText(text)
        self.selection_changed.emit()

    def _emit_edit(self) -> None:
        entry = self.current()
        if entry is not None:
            self.edit_requested.emit(entry)
