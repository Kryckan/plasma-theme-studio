# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the Icons, Pointers, Splash Screen and System Sounds pages share.

Background      runs a function off the GUI thread; only the answer to the newest request arrives
ImageStrip      rows of pictures on a background color (the large icon and pointer previews)
PreviewPicture  one picture, 16:10, with rounded corners (the splash screen preview)
SoundList       the rows of the sound themes, each with a Play button, shaped like a CardGrid
find_player     the program that plays a sound, chosen when asked
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QRectF, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...pickers.sounds import speaker_card
from ..widgets import POSITIVE, SPACING, _flip, mix, scaled_font, themed_icon, with_alpha

translate = QCoreApplication.translate

PICTURE_SIZE = QSize(320, 200)  # 16:10, as the cards
PLAYERS = (
    ("pw-play", []),
    ("paplay", []),
    ("canberra-gtk-play", ["-f"]),
)  # program, what comes before the file


def find_player(runner) -> str | None:
    """The first sound player that the runner has, or None."""
    for program, _before in PLAYERS:
        if runner.which(program):
            return program
    return None


def player_command(program: str, sound: Path) -> list[str]:
    """The command line that plays `sound` with `program` (one of `PLAYERS`)."""
    before = dict(PLAYERS)[program]
    return [program, *before, str(sound)]


# ---- off the GUI thread


class _Answer(QObject):
    done = Signal(int, object)


class _Job(QRunnable):
    def __init__(self, generation: int, answer: _Answer, function: Callable, args: tuple):
        super().__init__()
        self.generation, self.answer, self.function, self.args = generation, answer, function, args

    def run(self) -> None:
        try:
            result = self.function(*self.args)
        except Exception:  # noqa: BLE001 - a picture that cannot be made is a missing picture
            result = None
        try:
            self.answer.done.emit(self.generation, result)
        except RuntimeError:  # the page is gone
            pass


class Background(QObject):
    """Runs a function on one worker thread. `ready(result)` is emitted on the GUI thread for the newest
    `request` only (None when the function raised); an older answer is dropped. The function may use
    QImage and QPainter, never widgets or pixmaps."""

    ready = Signal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.generation = 0
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._answer = _Answer(self)
        self._answer.done.connect(self._done)

    def request(self, function: Callable, *args) -> None:
        self.generation += 1
        self.pool.start(_Job(self.generation, self._answer, function, args))

    def cancel(self) -> None:
        """Forget the answer to anything asked so far."""
        self.generation += 1

    def wait(self, milliseconds: int = 10000) -> bool:
        """Block until the worker is idle (tests)."""
        return self.pool.waitForDone(milliseconds)

    def _done(self, generation: int, result) -> None:
        if generation == self.generation:
            self.ready.emit(result)


# ---- pictures


class ImageStrip(QWidget):
    """Rows of pictures on a background color, a frame around them. Each row wraps by itself when the
    widget is narrow; pictures are drawn at their logical size (`deviceIndependentSize`)."""

    PAD = 14
    GAP = 12

    def __init__(self, name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.rows: list[list[QImage]] = []
        self.background = QColor("#eff0f1")
        self.setAccessibleName(name)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def set_rows(self, rows: list[list[QImage]]) -> None:
        self.rows = [row for row in rows if row]
        self.updateGeometry()
        self.update()

    def set_background(self, color: QColor) -> None:
        if color != self.background:
            self.background = QColor(color)
            self.update()

    def has_content(self) -> bool:
        return bool(self.rows)

    def _cell(self, row: list[QImage]) -> QSize:
        sizes = [image.deviceIndependentSize() for image in row]
        return QSize(
            int(max(size.width() for size in sizes)) + self.GAP, int(max(size.height() for size in sizes))
        )

    def _layout(self, width: int) -> tuple[list[tuple[QImage, QRectF]], int]:
        """(picture, where) for every picture and the height needed at this width."""
        placed: list[tuple[QImage, QRectF]] = []
        y = self.PAD
        for index, row in enumerate(self.rows):
            cell = self._cell(row)
            per_line = max(1, (width - 2 * self.PAD + self.GAP) // cell.width())
            for line_start in range(0, len(row), per_line):
                for column, image in enumerate(row[line_start : line_start + per_line]):
                    size = image.deviceIndependentSize()
                    x = self.PAD + column * cell.width() + (cell.width() - self.GAP - size.width()) / 2
                    placed.append(
                        (
                            image,
                            QRectF(x, y + (cell.height() - size.height()) / 2, size.width(), size.height()),
                        )
                    )
                y += cell.height() + self.GAP
            if index < len(self.rows) - 1:
                y += 2
        return placed, int(y - self.GAP + self.PAD if self.rows else 0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._layout(width)[1]

    def sizeHint(self) -> QSize:
        return QSize(640, self.heightForWidth(640))

    def minimumSizeHint(self) -> QSize:
        return QSize(160, self.heightForWidth(160))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        text = self.palette().text().color()
        p.setBrush(self.background)
        p.setPen(QPen(with_alpha(text, 0.18), 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        for image, where in self._layout(self.width())[0]:
            p.drawImage(where, image)


class PreviewPicture(QWidget):
    """One picture at a fixed 16:10 size, with rounded corners and a frame. Without a picture it shows
    a plain surface."""

    def __init__(self, name: str, size: QSize | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.image: QImage | None = None
        self.setFixedSize(size or PICTURE_SIZE)
        self.setAccessibleName(name)

    def set_image(self, image: QImage | None) -> None:
        self.image = None if image is None or image.isNull() else image
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        palette = self.palette()
        rect = QRectF(self.rect())
        outline = QPainterPath()
        outline.addRoundedRect(rect, 6, 6)
        p.save()
        p.setClipPath(outline)
        if self.image is not None:
            p.drawImage(rect, self.image)
        else:
            p.fillRect(rect, mix(palette.base().color(), palette.text().color(), 0.07))
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(palette.text().color(), 0.22), 1))
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)


# ---- the sound themes


class SoundRow(QAbstractButton):
    """One sound theme: a badge, its name and description, "In use" and a Play button. Checked means
    chosen. A click anywhere but on Play chooses it."""

    HEIGHT = 64
    PAD = 12

    def __init__(self, item_id, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.item_id = item_id
        self.subtitle = subtitle
        self.in_use = False
        self.dimmed = False
        self.focus_ring = False
        self.badge: QImage | None = None
        self.setText(title)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.play = QPushButton(translate("ui", "Play"), self)
        self.play.setIcon(themed_icon("media-playback-start"))
        self.play.setAccessibleName(translate("ui", "Play {name}").format(name=title))
        self._hover = False
        self._describe()

    def nextCheckState(self):
        self.setChecked(True)  # a click never clears the choice

    def setChecked(self, checked):
        super().setChecked(checked)
        self._describe()

    def set_in_use(self, in_use: bool) -> None:
        self.in_use = in_use
        self._describe()
        self.update()

    def set_dimmed(self, dimmed: bool) -> None:
        self.dimmed = dimmed
        self.update()

    def _describe(self) -> None:
        self.setAccessibleName(self.text())
        notes = (
            [translate("widgets", "In use")] if self.in_use else ([self.subtitle] if self.subtitle else [])
        )
        if self.isChecked():
            notes.append(translate("widgets", "Selected"))
        self.setAccessibleDescription(", ".join(notes))

    def resizeEvent(self, event):
        size = self.play.sizeHint()
        right = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        x = self.PAD if right else self.width() - self.PAD - size.width()
        self.play.setGeometry(x, (self.height() - size.height()) // 2, size.width(), size.height())
        super().resizeEvent(event)

    def event(self, event):
        if event.type() == event.Type.Enter:
            self._hover = True
            self.update()
        elif event.type() == event.Type.Leave:
            self._hover = False
            self.update()
        return super().event(event)

    def paintEvent(self, _):
        palette = self.palette()
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        highlight, base, text = palette.highlight().color(), palette.base().color(), palette.text().color()
        selected = self.isChecked()
        fill = (
            mix(base, highlight, 0.10) if selected else (mix(base, highlight, 0.05) if self._hover else base)
        )
        p.setBrush(fill)
        p.setPen(
            QPen(
                highlight if selected else with_alpha(text, 0.35 if self._hover else 0.16),
                2 if selected else 1,
            )
        )
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1) if selected else rect, 6, 6)
        side = self.HEIGHT - 2 * self.PAD

        def where(rect: QRectF) -> QRectF:  # laid out left to right, mirrored for right to left
            return _flip(self.width(), rect) if rtl else rect

        p.setOpacity(0.55 if self.dimmed else 1.0)
        if self.badge is not None:
            p.drawImage(where(QRectF(self.PAD, self.PAD, side, side)), self.badge)
        p.setOpacity(1.0)
        left = self.PAD + side + 12
        room = max(0, self.width() - self.PAD - self.play.width() - 12 - left)
        align = (
            Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        ) | Qt.AlignmentFlag.AlignVCenter
        font = QFont(self.font())
        font.setBold(selected)
        small = scaled_font(self.font(), 0.9)
        title_h, small_h = QFontMetrics(font).height(), QFontMetrics(small).height()
        two = self.in_use or bool(self.subtitle)
        y = (self.height() - (title_h + (1 + small_h if two else 0))) / 2
        p.setFont(font)
        p.setPen(text)
        title = QFontMetrics(font).elidedText(self.text(), Qt.TextElideMode.ElideRight, int(room))
        p.drawText(where(QRectF(left, y, room, title_h)), align, title)
        y += title_h + 1
        p.setFont(small)
        if self.in_use:
            green = QColor(POSITIVE)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(green)
            p.drawEllipse(where(QRectF(left, y + small_h / 2 - 3, 6, 6)))
            p.setPen(green)
            p.drawText(
                where(QRectF(left + 12, y, max(0, room - 12), small_h)), align, translate("widgets", "In use")
            )
        elif self.subtitle:
            p.setPen(with_alpha(text, 0.62))
            elided = QFontMetrics(small).elidedText(self.subtitle, Qt.TextElideMode.ElideRight, int(room))
            p.drawText(where(QRectF(left, y, room, small_h)), align, elided)
        if self.focus_ring:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(text, 0.8), 1.5, Qt.PenStyle.DotLine))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(4, 4, -4, -4), 4, 4)


class _Rows(QWidget):
    """The one tab stop of a SoundList (the Play buttons are tab stops of their own)."""

    def __init__(self, owner: SoundList, name: str):
        super().__init__()
        self.owner = owner
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(name)

    def keyPressEvent(self, event):
        if not self.owner.key_pressed(event):
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.owner.sync_ring()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.owner.sync_ring()


class SoundList(QWidget):
    """The sound themes as a column of `SoundRow`s with a search field above (`bar`). It has the parts of
    `CardGrid` that a `PickerPage` uses, so the page code is the same: `selected(id)` is emitted when
    the person picks a row (also one that is chosen already), the `set_*` methods never emit it.
    Keys: Up and Down choose the row before or after, Home and End the first and last."""

    selected = Signal(object)
    thumbnail_requested = Signal(object)  # never: the rows have no pictures to ask for
    play_requested = Signal(object)  # the id of the row whose Play was pressed

    def __init__(self, name: str = "", badge: QImage | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.rows: list[SoundRow] = []
        self._by_id: dict = {}
        self._selected = None
        self._in_use = None
        self._dimmed = False
        self._badge = badge
        self._player_tip = ""
        self._can_play = True
        self.search = QLineEdit(placeholderText=translate("widgets", "Search…"), clearButtonEnabled=True)
        self.search.setAccessibleName(translate("widgets", "Search"))
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self._apply_filter)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(self.search)
        bar.addStretch(1)
        self.bar = QWidget()
        self.bar.setLayout(bar)
        self.body = _Rows(self, name or translate("ui", "System Sounds"))
        self.column = QVBoxLayout(self.body)
        self.column.setContentsMargins(2, 2, 2, 2)
        self.column.setSpacing(SPACING)
        self.message = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        self.message.setForegroundRole(self.message.palette().ColorRole.PlaceholderText)
        self.message.setMinimumHeight(96)
        self.message.hide()
        self._empty_text = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.body)
        layout.addWidget(self.message)
        self.setFocusProxy(self.body)

    # ---- the parts of CardGrid the page uses

    def set_items(self, items) -> None:
        for row in self.rows:
            row.hide()
            row.setParent(None)
            row.deleteLater()
        while self.column.count():
            self.column.takeAt(0)
        self.rows, self._by_id = [], {}
        for item in items:
            item_id, title, subtitle = item[:3]
            row = SoundRow(item_id, title, subtitle, self.body)
            row.badge = self._badge
            row.clicked.connect(lambda _=False, r=row: self._clicked(r))
            row.play.clicked.connect(lambda _=False, r=row: self.play_requested.emit(r.item_id))
            row.set_dimmed(self._dimmed)
            self.rows.append(row)
            self._by_id[item_id] = row
            self.column.addWidget(row)
        if self._selected not in self._by_id:
            self._selected = None
        if self._in_use not in self._by_id:
            self._in_use = None
        for row in self.rows:
            row.setChecked(row.item_id == self._selected)
            row.set_in_use(row.item_id == self._in_use)
        self.set_playable(self._can_play, self._player_tip)
        self._apply_filter()

    def set_empty_text(self, text: str) -> None:
        self._empty_text = text
        self.message.setText(text)

    def card(self, item_id) -> SoundRow | None:
        return self._by_id.get(item_id)

    def ids(self) -> list:
        return [row.item_id for row in self.rows]

    def visible_cards(self) -> list[SoundRow]:
        return [row for row in self.rows if not row.isHidden()]

    def set_thumbnail(self, item_id, image) -> None:  # the rows have no thumbnails
        pass

    def set_no_preview(self, item_id) -> None:
        pass

    def ask_again_for_thumbnails(self) -> None:
        pass

    def set_in_use(self, item_id) -> None:
        self._in_use = item_id if item_id in self._by_id else None
        for row in self.rows:
            row.set_in_use(row.item_id == self._in_use)

    def in_use(self):
        return self._in_use

    def set_selected(self, item_id) -> None:
        self._selected = item_id if item_id in self._by_id else None
        for row in self.rows:
            row.setChecked(row.item_id == self._selected)

    def selected_id(self):
        return self._selected

    def set_dimmed(self, dimmed: bool) -> None:
        self._dimmed = dimmed
        for row in self.rows:
            row.set_dimmed(dimmed)

    # ---- playing

    def set_playable(self, can_play: bool, tooltip: str = "", only=None) -> None:
        """Turn every Play button on or off; `only` is the set of ids that have a sound (the others are
        off with their own tooltip)."""
        self._can_play, self._player_tip = can_play, tooltip
        self._only = only
        for row in self.rows:
            has_sound = only is None or row.item_id in only
            row.play.setEnabled(can_play and has_sound)
            row.play.setToolTip(
                tooltip
                if not can_play
                else ("" if has_sound else translate("ui", "This sound theme has no sound to play."))
            )

    # ---- keys and clicks

    def _clicked(self, row: SoundRow) -> None:
        self.body.setFocus(Qt.FocusReason.MouseFocusReason)
        self.selected.emit(row.item_id)

    def _shown(self) -> list[SoundRow]:
        return self.visible_cards()

    def _current(self) -> SoundRow | None:
        rows = self._shown()
        chosen = self._by_id.get(self._selected)
        return chosen if chosen in rows else (rows[0] if rows else None)

    def key_pressed(self, event) -> bool:
        rows = self._shown()
        if not rows:
            return False
        key = event.key()
        current = self._current()
        index = rows.index(current) if current in rows else 0
        if key == Qt.Key.Key_Up:
            target = rows[max(0, index - 1)]
        elif key == Qt.Key.Key_Down:
            target = rows[min(len(rows) - 1, index + 1)]
        elif key == Qt.Key.Key_Home:
            target = rows[0]
        elif key == Qt.Key.Key_End:
            target = rows[-1]
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            target = current
        else:
            return False
        if target is not None:
            self.selected.emit(target.item_id)
            self.sync_ring()
            scroll = _scroll_of(target)
            if scroll is not None:
                scroll.ensureWidgetVisible(target)
        return True

    def sync_ring(self) -> None:
        current = self._current() if self.body.hasFocus() else None
        for row in self.rows:
            row.focus_ring = row is current
            row.update()

    def _apply_filter(self, *_) -> None:
        words = self.search.text().casefold().split()
        shown = 0
        for row in self.rows:
            hay = f"{row.text()} {row.subtitle}".casefold()
            match = all(word in hay for word in words)
            row.setVisible(match)
            shown += match
        self.message.setVisible(shown == 0)
        self.message.setText(self._empty_text)
        self.sync_ring()


def _scroll_of(widget: QWidget):
    from PySide6.QtWidgets import QScrollArea

    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    return parent


def speaker_badge(side: int, dpr: float) -> QImage:
    """The small speaker tile of a sound row, drawn by the picker."""
    return speaker_card(QSize(side, side), dpr)
