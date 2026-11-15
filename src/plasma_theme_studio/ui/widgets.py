# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared widgets of the window: picker cards, side bar, header, notes and the Desktop bar.

Everything is painted from the application's palette and style, so it follows the color scheme of the
desktop. Only KDE's four status colors (positive, information, warning, negative) are fixed.

  FlowLayout   wraps widgets like text; height for width (needed inside a scroll area)
  Card         one picker card: thumbnail, title, subtitle; selected, in use, hover, focus, dimmed
  CardGrid     optional search and filter above a flow of cards; one selected; keyboard navigation
  PageHeader   title, subtitle, actions on the right, optional "Leave as it is | Set by this theme" switch
  InlineNote   a strip like KMessageWidget (information, warning, positive, error)
  NavList      grouped side bar with "changes on apply" dots and dimmed rows
  Segmented    exclusive row of checkable buttons
  DesktopBar   the permanent bottom bar with Snapshots, Undo last apply and Apply to Desktop
  ColorDots    a row of round color buttons with a "Custom…" button
"""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ..model.color import BLACK, Color, readable_on

translate = QCoreApplication.translate

THUMB_SIZE = QSize(176, 110)  # 16:10, the size of most thumbnails
SPACING = 8  # between a label and its control
LARGE_SPACING = 16  # between cards and between sections of a page
POSITIVE, INFORMATION, WARNING, NEGATIVE = "#27ae60", "#3daee9", "#f67400", "#da4453"
CHANGED, OFF = "changed", "off"  # states of a NavList row

_RIGHT_TO_LEFT = Qt.LayoutDirection.RightToLeft


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """The color t of the way from a to b."""
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


def with_alpha(color: QColor, alpha: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(alpha)
    return c


def scaled_font(font: QFont, factor: float) -> QFont:
    out = QFont(font)
    if font.pointSizeF() > 0:
        out.setPointSizeF(font.pointSizeF() * factor)
    else:
        out.setPixelSize(max(1, round(font.pixelSize() * factor)))
    return out


def themed_icon(name: str, fallback: str = "") -> QIcon:
    """An icon of the icon theme, or of the fallback name; null when neither exists."""
    return QIcon.fromTheme(name, QIcon.fromTheme(fallback) if fallback else QIcon())


def _flip(width: int, rect: QRectF) -> QRectF:
    """The mirror image of a rectangle inside a widget of the given width (right-to-left layouts)."""
    return QRectF(width - rect.x() - rect.width(), rect.y(), rect.width(), rect.height())


def _scroll_area_of(widget: QWidget) -> QScrollArea | None:
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    return parent


class FlowLayout(QLayout):
    """Lays widgets out like words in a paragraph. Its height depends on its width. With `justified`
    (see `JustifiedFlow`) the cards fill every row from edge to edge.

    This is one class and not a base with a subclass: PySide 6.12 on Python 3.14 frees the methods
    a subclass inherits from a Python layout class, and the program then crashes in a later layout pass."""

    MAX_GROWTH = 1.3

    def __init__(self, parent=None, h=LARGE_SPACING, v=LARGE_SPACING, justified=False):
        super().__init__(parent)
        self._items = []
        self._h, self._v = h, v
        self._justified = justified

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._flow(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._flow(rect, True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _flow(self, rect, place):
        if self._justified:
            return self._flow_justified(rect, place)
        m = self.contentsMargins()
        inner = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        parent = self.parentWidget()
        rtl = (parent.layoutDirection() if parent else QApplication.layoutDirection()) == _RIGHT_TO_LEFT
        x, y, row_height = inner.x(), inner.y(), 0
        for item in self._items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            if x + hint.width() > inner.right() + 1 and row_height > 0:
                x, y, row_height = inner.x(), y + row_height + self._v, 0
            if place:
                left = inner.right() + 1 - (x - inner.x()) - hint.width() if rtl else x
                item.setGeometry(QRect(QPoint(left, y), hint))
            x += hint.width() + self._h
            row_height = max(row_height, hint.height())
        return y + row_height - rect.y() + m.bottom()

    def _flow_justified(self, rect, place):
        m = self.contentsMargins()
        inner = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        items = [item for item in self._items if not item.isEmpty()]
        if not items:
            return m.top() + m.bottom()
        cell_w = max(item.sizeHint().width() for item in items)
        cell_h = max(item.sizeHint().height() for item in items)
        columns = max(1, (inner.width() + self._h) // (cell_w + self._h))
        card_w, card_h, gap = cell_w, cell_h, self._h
        if len(items) >= columns:
            widgets = [item.widget() for item in items]
            growable = all(getattr(w, "thumb_size", None) is not None for w in widgets)
            room = inner.width() - (columns - 1) * self._h
            if growable:
                card_w = max(cell_w, min(room // columns, int(cell_w * self.MAX_GROWTH)))
                thumb = widgets[0].thumb_size
                card_h = cell_h + round((card_w - cell_w) * thumb.height() / max(1, thumb.width()))
            if columns > 1:
                gap = max(self._h, (inner.width() - columns * card_w) // (columns - 1))
        parent = self.parentWidget()
        rtl = parent is not None and parent.layoutDirection() == Qt.LayoutDirection.RightToLeft
        for number, item in enumerate(items):
            row, column = divmod(number, columns)
            x = column * (card_w + gap)
            left = inner.right() + 1 - x - card_w if rtl else inner.x() + x
            if place:
                item.setGeometry(QRect(left, inner.y() + row * (card_h + self._v), card_w, card_h))
        rows = -(-len(items) // columns)
        return rows * card_h + (rows - 1) * self._v + m.top() + m.bottom()


# A flow of equal cards that uses the whole width: the first column sits at the left edge and the last at
# the right edge, so no strip is left over. The room left in a row is shared first by the cards themselves
# (a card with a `thumb_size` grows its picture, up to `MAX_GROWTH`) and then by the gaps. A row that is
# not full keeps the cards of the full ones, in the same columns.
JustifiedFlow = partial(FlowLayout, justified=True)


class Card(QAbstractButton):
    """A picker card. Checked means selected. It is not a tab stop: the CardGrid owns the focus.

    The thumbnail is a QImage or QPixmap drawn into `thumb_size` (give it a device pixel ratio for sharp
    output). It becomes a pixmap on the first paint, so a card that is never shown costs no pixmap.
    """

    remove_requested = Signal()
    menu_requested = Signal(QPoint)
    doubleClicked = Signal()
    thumbnail_requested = Signal()  # once, after the first paint without a thumbnail

    PAD = 8
    CAPTION_AIR = 5  # room under the second line of words, so that it does not touch the edge
    BADGE = 18  # the check badge of the selected card

    def __init__(self, item_id, title, subtitle="", thumb_size=THUMB_SIZE, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.subtitle = subtitle
        self.thumb_size = QSize(thumb_size)
        self.in_use = False
        self.dimmed = False  # a part left as it is: still clickable
        self.focus_ring = False  # the grid has the keyboard focus and this is its current card
        self.forced_hover = False  # for pictures only
        self._thumb: QImage | QPixmap | None = None
        self._pixmap: QPixmap | None = None
        self._requested = False
        self.no_preview = False  # the picture could not be made
        self._hover = False
        self._action = ""
        self._action_tip = ""
        self._action_hover = False
        self._action_down = False
        self.setText(title)
        self.setCheckable(True)
        # Preferred both ways: a layout that makes the card larger than its hint (`JustifiedFlow`) is obeyed
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._describe()

    def title(self) -> str:
        return self.text()

    def nextCheckState(self):
        self.setChecked(True)  # a click never clears the selection of a picker

    def set_thumbnail(self, thumbnail: QImage | QPixmap | None) -> None:
        self._thumb, self._pixmap = thumbnail, None
        self.update()

    def set_no_preview(self) -> None:
        self.no_preview = True
        self.update()

    def has_thumbnail(self) -> bool:
        return self._thumb is not None

    def set_in_use(self, in_use: bool) -> None:
        self.in_use = in_use
        self._describe()
        self.update()

    def set_dimmed(self, dimmed: bool) -> None:
        self.dimmed = dimmed
        self.update()

    def set_action(self, kind: str, tooltip: str = "") -> None:
        """ "remove" (a cross) or "menu" (three dots) in the corner of the thumbnail; "" for none."""
        self._action, self._action_tip = kind, tooltip
        self.update()

    def action(self) -> str:
        return self._action

    def setChecked(self, checked):
        super().setChecked(checked)
        self._describe()

    def _describe(self) -> None:
        self.setAccessibleName(self.text())
        notes = []
        if self.in_use:
            notes.append(translate("widgets", "In use"))
        elif self.subtitle:
            notes.append(self.subtitle)
        if self.isChecked():
            notes.append(translate("widgets", "Selected"))
        self.setAccessibleDescription(", ".join(notes))

    def _small_font(self) -> QFont:
        return scaled_font(self.font(), 0.9)

    def sizeHint(self):
        line = self.fontMetrics().height() + 1 + QFontMetrics(self._small_font()).height()
        return QSize(
            self.thumb_size.width() + 2 * self.PAD,
            self.PAD + self.thumb_size.height() + 6 + line + self.PAD + self.CAPTION_AIR,
        )

    def minimumSizeHint(self):
        return self.sizeHint()

    def changeEvent(self, event):
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.updateGeometry()
        super().changeEvent(event)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = self._action_hover = False
        self.update()

    def _thumb_rect(self) -> QRectF:
        """The picture's place. A card that is laid out wider than its size hint (`JustifiedFlow`) has a
        wider picture of the same shape."""
        width = max(self.thumb_size.width(), self.width() - 2 * self.PAD)
        height = round(width * self.thumb_size.height() / max(1, self.thumb_size.width()))
        return QRectF(self.PAD, self.PAD, width, height)

    def _action_rect(self) -> QRectF:
        rect = QRectF(self._thumb_rect().x() + 6, self._thumb_rect().y() + 6, 20, 20)
        return _flip(self.width(), rect) if self.layoutDirection() == _RIGHT_TO_LEFT else rect

    def _action_visible(self) -> bool:
        return bool(self._action) and (
            self._hover or self.forced_hover or self.isChecked() or self.focus_ring
        )

    def mouseMoveEvent(self, event):
        over = self._action_visible() and self._action_rect().contains(event.position())
        if over != self._action_hover:
            self._action_hover = over
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._action_visible()
            and self._action_rect().contains(event.position())
        ):
            self._action_down = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._action_down:
            self._action_down = False
            if self._action_rect().contains(event.position()):
                if self._action == "remove":
                    self.remove_requested.emit()
                else:
                    self.menu_requested.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self._action == "menu":
            self.menu_requested.emit(event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip and self._action_tip:
            if self._action_visible() and self._action_rect().contains(QPointF(event.pos())):
                QToolTip.showText(event.globalPos(), self._action_tip, self)
                return True
        return super().event(event)

    def _thumb_pixmap(self) -> QPixmap | None:
        if self._pixmap is None and self._thumb is not None:
            thumb = self._thumb
            self._pixmap = thumb if isinstance(thumb, QPixmap) else QPixmap.fromImage(thumb)
        return self._pixmap

    def paintEvent(self, _):
        palette = self.palette()
        rtl = self.layoutDirection() == _RIGHT_TO_LEFT
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        # a card that is in the background is dimmed in its picture only: its words stay readable
        resting = 1.0 if self.isEnabled() else 0.4
        p.setOpacity(resting)
        highlight, base, text = palette.highlight().color(), palette.base().color(), palette.text().color()
        hover = self.isEnabled() and (self._hover or self.forced_hover)
        selected = self.isChecked()
        # the surface
        fill = mix(base, highlight, 0.10) if selected else (mix(base, highlight, 0.05) if hover else base)
        border = highlight if selected else with_alpha(text, 0.35 if hover else 0.16)
        p.setBrush(fill)
        p.setPen(QPen(border, 2 if selected else 1))
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1) if selected else rect, 6, 6)
        # the thumbnail, clipped to rounded corners
        thumb = self._thumb_rect()
        outline = QPainterPath()
        outline.addRoundedRect(thumb, 4, 4)
        pixmap = self._thumb_pixmap()
        p.save()
        p.setClipPath(outline)
        if pixmap is not None:
            p.drawPixmap(thumb.toRect(), pixmap)
        else:
            p.fillRect(thumb, mix(base, text, 0.07))
            if self.no_preview:
                p.setPen(with_alpha(text, 0.6))
                p.drawText(thumb, Qt.AlignmentFlag.AlignCenter, translate("widgets", "No preview"))
        p.restore()
        if pixmap is None and not self._requested:
            self._requested = True
            QTimer.singleShot(0, self.thumbnail_requested.emit)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(text, 0.18), 1))
        p.drawRoundedRect(thumb, 4, 4)
        p.setOpacity(resting)
        if self.dimmed and self.isEnabled():  # left as it is: a small neutral ring, the picture stays clear
            corner = QPointF(thumb.left() + 11, thumb.top() + 11)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(base, 0.85))
            p.drawEllipse(corner, 7, 7)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(text, 0.55), 1.4))
            p.drawEllipse(corner, 3.2, 3.2)
        if self._action_visible():
            self._paint_action(p, palette)
        # the texts
        align = Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        align |= Qt.AlignmentFlag.AlignVCenter
        fm = self.fontMetrics()
        inner = int(thumb.width())
        y = int(thumb.bottom()) + 6
        font = QFont(self.font())
        font.setBold(selected)
        p.setFont(font)
        p.setPen(palette.text().color())
        # The check badge of a selected card sits at the end of the title line, beside the words, so it
        # never hides a part of the picture (on every kind of card).
        room = inner - (self.BADGE + 6 if selected else 0)
        title = QFontMetrics(font).elidedText(self.text(), Qt.TextElideMode.ElideRight, room)
        p.drawText(self._mirrored(QRectF(self.PAD, y, room, fm.height()), rtl), align, title)
        if selected:
            self._paint_badge(p, palette, self._mirrored(self._badge_rect(y, fm.height()), rtl))
        y += fm.height() + 1
        small = self._small_font()
        p.setFont(small)
        line = QFontMetrics(small).height()
        if self.in_use:
            green = QColor(POSITIVE)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(green)
            p.drawEllipse(self._mirrored(QRectF(self.PAD + 1, y + line / 2 - 3, 6, 6), rtl))
            p.setPen(green)
            p.drawText(
                self._mirrored(QRectF(self.PAD + 12, y, inner - 12, line), rtl),
                align,
                translate("widgets", "In use"),
            )
        elif self.subtitle:
            p.setPen(with_alpha(text, 0.62))
            elided = QFontMetrics(small).elidedText(self.subtitle, Qt.TextElideMode.ElideRight, inner)
            p.drawText(self._mirrored(QRectF(self.PAD, y, inner, line), rtl), align, elided)
        # Keyboard focus is a dotted ring inside the card. It differs from the solid accent border of
        # the selection, so a card that is both selected and focused shows both.
        if self.focus_ring:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(text, 0.8), 1.5, Qt.PenStyle.DotLine))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(4, 4, -4, -4), 4, 4)

    def _mirrored(self, rect: QRectF, rtl: bool) -> QRectF:
        return _flip(self.width(), rect) if rtl else rect

    def _badge_rect(self, line_top: float, line_height: float) -> QRectF:
        """Where the check badge goes (left to right): the end of the title line."""
        side = float(self.BADGE)
        return QRectF(self._thumb_rect().right() - side, line_top + (line_height - side) / 2, side, side)

    def _paint_badge(self, p: QPainter, palette: QPalette, badge: QRectF) -> None:
        c = badge.center()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(palette.highlight().color())
        p.drawEllipse(badge)
        pen = QPen(palette.highlightedText().color(), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([c + QPointF(-3.6, 0.2), c + QPointF(-1, 2.8), c + QPointF(3.6, -2.6)])

    def _paint_action(self, p: QPainter, palette: QPalette) -> None:
        rect = self._action_rect()
        text = palette.text().color()
        p.setPen(QPen(with_alpha(text, 0.35), 1))
        p.setBrush(
            with_alpha(mix(palette.base().color(), palette.highlight().color(), 0.25), 0.95)
            if self._action_hover
            else with_alpha(palette.base().color(), 0.9)
        )
        p.drawEllipse(rect)
        c = rect.center()
        p.setPen(QPen(text, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if self._action == "remove":
            p.drawLine(c + QPointF(-3.5, -3.5), c + QPointF(3.5, 3.5))
            p.drawLine(c + QPointF(-3.5, 3.5), c + QPointF(3.5, -3.5))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(text)
            for dy in (-4.5, 0, 4.5):
                p.drawEllipse(c + QPointF(0, dy), 1.4, 1.4)


class _Body(QWidget):
    """The one tab stop of a CardGrid; it hands keys to the grid."""

    def __init__(self, grid: CardGrid, name: str):
        super().__init__()
        self.grid = grid
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(name)

    def keyPressEvent(self, event):
        if not self.grid._key_pressed(event):
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.grid._sync_ring()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.grid._sync_ring()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.LayoutDirectionChange:
            self.layout().invalidate()
        super().changeEvent(event)


_MOVES = (
    Qt.Key.Key_Left,
    Qt.Key.Key_Right,
    Qt.Key.Key_Up,
    Qt.Key.Key_Down,
    Qt.Key.Key_Home,
    Qt.Key.Key_End,
    Qt.Key.Key_PageUp,
    Qt.Key.Key_PageDown,
)


class CardGrid(QWidget):
    """A flow of cards with an optional search field and filter. One card is selected, or none.

    Keys on the grid (one tab stop): arrows move the selection (Left and Right by one, Up and Down by a
    row), Home and End, Page Up and Page Down by a screenful, Return and Space emit `activated`, Delete
    emits `remove_requested` for a card with a remove button. Typing goes to the search field, or jumps
    to a title that starts with the typed letters when there is no search field.

    `selected` is emitted when the user picks a card (also when it already was the selected one, so that
    "Leave as it is" can turn on); the set_* methods never emit it. With `fit` the grid is as tall as its
    cards, for use inside a scrolling page; otherwise it scrolls by itself.
    """

    selected = Signal(object)  # id of the card the user picked
    activated = Signal(object)  # Return, Space or double click
    remove_requested = Signal(object)
    menu_requested = Signal(object, QPoint)
    thumbnail_requested = Signal(object)  # a card without thumbnail was shown for the first time

    def __init__(
        self,
        thumb_size=THUMB_SIZE,
        with_search=True,
        fit=False,
        empty_text="",
        name="",
        type_ahead=True,
        parent=None,
        flow_class=None,
        reveal=True,
        tall=False,
    ):
        super().__init__(parent)
        self.fit = fit
        self.tall = (
            tall  # a scroll area with no scroll bar of its own, as tall as the cards (see _fit_height)
        )
        self.reveal = reveal  # scroll the page to the card that is selected by the program
        self.thumb_size = QSize(thumb_size)
        self.cards: list[Card] = []
        self._by_id: dict = {}
        self._thumbs: dict = {}
        self._selected = None
        self._in_use = None
        self._dimmed = False
        self._categories: dict = {}
        self._type_ahead = type_ahead
        self._typed = ""
        self._typed_timer = QTimer(self, singleShot=True, interval=900)
        self._typed_timer.timeout.connect(lambda: setattr(self, "_typed", ""))
        self._empty_text = empty_text or translate("widgets", "Nothing to show here.")
        self._filter_empty: dict = {}

        placeholder = translate("widgets", "Search…")
        self.search = QLineEdit(placeholderText=placeholder, clearButtonEnabled=True)
        self.search.setAccessibleName(translate("widgets", "Search"))
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self._apply_filter)
        self.search.installEventFilter(self)
        self._with_search = with_search
        self.filter = QComboBox()
        self.filter.setAccessibleName(translate("widgets", "Filter"))
        self.filter.currentIndexChanged.connect(self._apply_filter)
        self.filter.hide()
        bar = QHBoxLayout()
        bar.setSpacing(SPACING)
        bar.addWidget(self.search)
        bar.addWidget(self.filter)
        bar.addStretch(1)
        self.bar = QWidget()
        self.bar.setLayout(bar)
        bar.setContentsMargins(0, 0, 0, 0)

        self.body = _Body(self, name or translate("widgets", "Choices"))
        self.flow = (flow_class or JustifiedFlow)(self.body)
        self.flow.setContentsMargins(2, 2, 2, 2)
        self.message = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        self.message.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.message.setMinimumHeight(96)
        if not fit:  # the message takes the place of the grid, so the page keeps its shape
            self.message.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.message.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING)
        layout.addWidget(self.bar)
        layout.addWidget(self.message)
        self.empty_extras: dict = {}  # category -> a widget (buttons) shown under that group's empty message
        self._extras_box = QVBoxLayout()
        self._extras_box.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._extras_box)
        if fit:
            self.scroll = None
            layout.addWidget(self.body)
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        else:
            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.scroll.setWidget(self.body)
            self.scroll.viewport().setAutoFillBackground(False)
            self.body.setAutoFillBackground(False)
            if tall:
                self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                # No resizeEvent here: a Python override on this class crashes PySide 6.12 when windows
                # are taken apart. A light timer sees the width change instead.
                self._fit_timer = QTimer(self, interval=100)
                self._fit_timer.timeout.connect(self._fit_height)
                self._fit_timer.start()
            layout.addWidget(self.scroll, 1)
        self._content = self.scroll or self.body
        self.setFocusProxy(self.body)
        self.setTabOrder(self.search, self.filter)
        self.setTabOrder(self.filter, self.body)
        self._update_state()

    # ---- content

    def set_items(self, items) -> None:
        """Replace the cards. Each item is (id, title, subtitle) or (id, title, subtitle, category)."""
        for card in self.cards:
            card.hide()
            card.setParent(None)
            card.deleteLater()
        while self.flow.count():
            self.flow.takeAt(0)
        self.cards, self._by_id, self._categories = [], {}, {}
        for item in items:
            item_id, title, subtitle = item[:3]
            card = Card(item_id, title, subtitle, self.thumb_size, self.body)
            self._categories[item_id] = item[3] if len(item) > 3 else ""
            card.clicked.connect(lambda _=False, c=card: self._clicked(c))
            card.remove_requested.connect(lambda c=card: self.remove_requested.emit(c.item_id))
            card.menu_requested.connect(lambda pos, c=card: self.menu_requested.emit(c.item_id, pos))
            card.thumbnail_requested.connect(lambda c=card: self._thumbnail_wanted(c))
            card.doubleClicked.connect(lambda c=card: self.activated.emit(c.item_id))
            card.set_dimmed(self._dimmed)
            if item_id in self._thumbs:
                card.set_thumbnail(self._thumbs[item_id])
            self.cards.append(card)
            self._by_id[item_id] = card
            self.flow.addWidget(card)
        self._thumbs = {k: v for k, v in self._thumbs.items() if k in self._by_id}
        if self._selected not in self._by_id:
            self._selected = None
        if self._in_use not in self._by_id:
            self._in_use = None
        for card in self.cards:
            card.setChecked(card.item_id == self._selected)
            card.set_in_use(card.item_id == self._in_use)
        self._apply_filter()

    def set_filters(self, filters, empty: dict | None = None) -> None:
        """Offer a combo of categories: a list of (category, label). Items name theirs as the fourth value.
        `empty` says, by category, what to show when nothing is in it."""
        self._filter_empty = dict(empty or {})
        self.filter.blockSignals(True)
        self.filter.clear()
        if filters:
            self.filter.addItem(translate("widgets", "All"), None)
            for category, label in filters:
                self.filter.addItem(label, category)
        self.filter.blockSignals(False)
        self._apply_filter()

    def set_empty_text(self, text: str) -> None:
        self._empty_text = text
        self._update_state()

    def card(self, item_id) -> Card | None:
        return self._by_id.get(item_id)

    def ids(self) -> list:
        return [c.item_id for c in self.cards]

    def visible_cards(self) -> list[Card]:
        return [c for c in self.cards if not c.isHidden()]

    def set_thumbnail(self, item_id, image: QImage | QPixmap | None) -> None:
        """Give a card its thumbnail, before or after it is shown. It is kept if the cards are replaced."""
        if image is None:
            self._thumbs.pop(item_id, None)
        else:
            self._thumbs[item_id] = image
        card = self._by_id.get(item_id)
        if card is not None:
            card.set_thumbnail(image)

    def set_no_preview(self, item_id) -> None:
        """Say on a card that its picture cannot be made (a style that fails to draw)."""
        card = self._by_id.get(item_id)
        if card is not None:
            card.set_no_preview()

    def set_in_use(self, item_id) -> None:
        self._in_use = item_id
        for card in self.cards:
            card.set_in_use(card.item_id == item_id)

    def in_use(self):
        return self._in_use

    def set_selected(self, item_id) -> None:
        """Select one card (or none, with None) without a signal."""
        self._selected = item_id if item_id in self._by_id else None
        for card in self.cards:
            card.setChecked(card.item_id == self._selected)
        self._sync_ring()
        card = self._by_id.get(self._selected)
        if card is not None and self.reveal:
            self._reveal(card)

    def selected_id(self):
        return self._selected

    def set_dimmed(self, dimmed: bool) -> None:
        self._dimmed = dimmed
        for card in self.cards:
            card.set_dimmed(dimmed)

    def set_item_action(self, item_id, kind: str, tooltip: str = "") -> None:
        """Give one card a "remove" or "menu" button (for things installed in the home folder)."""
        card = self._by_id.get(item_id)
        if card is not None:
            card.set_action(kind, tooltip)

    def set_item_enabled(self, item_id, enabled: bool) -> None:
        card = self._by_id.get(item_id)
        if card is not None:
            card.setEnabled(enabled)

    # ---- state

    def _apply_filter(self, *_) -> None:
        text = self.search.text().strip().casefold()
        category = self.filter.currentData() if self.filter.count() else None
        for card in self.cards:
            hide = bool(text) and text not in f"{card.text()} {card.subtitle}".casefold()
            if category is not None and self._categories.get(card.item_id) != category:
                hide = True
            card.setHidden(hide)
        self.flow.invalidate()
        self._update_state()
        self._sync_ring()
        self._fit_height()

    def _fit_height(self) -> None:
        """A `tall` grid is as high as its cards need at its width, so that the page scrolls and the
        grid does not. (A `fit` grid does the same through the layout, but a page that holds one of
        those crashes PySide 6.12 when its windows are taken apart: see docs/STATUS.md.)"""
        if not self.tall or self.scroll is None:
            return
        fitted = self.scroll.minimumHeight() > 0
        if fitted and not self.isVisible():
            return
        width = self.scroll.viewport().width()
        if width <= 0 and not self.isVisible():
            width = max(self.width(), 300)
        shown = sum(1 for c in self.cards if not c.isHidden())
        key = (width, shown, self.message.isVisible())
        if fitted and key == getattr(self, "_fit_key", None):
            return
        self._fit_key = key
        height = self.flow.heightForWidth(width) if shown else 0
        height = max(height, 1)
        if self.scroll.minimumHeight() != height:
            self.scroll.setFixedHeight(height)

    def add_empty_extra(self, category, widget) -> None:
        """Show `widget` under the empty message of the group `category` (the buttons that fill it)."""
        self.empty_extras[category] = widget
        widget.hide()
        self._extras_box.addWidget(widget, 0, Qt.AlignmentFlag.AlignHCenter)

    def _show_extra(self, text: str) -> None:
        category = self.filter.currentData() if self.filter.count() else None
        searching = bool(self.search.text().strip())
        own = bool(text) and bool(self.cards) and not searching
        for key, widget in self.empty_extras.items():
            widget.setVisible(own and key == category)

    def _update_state(self) -> None:
        shown = len(self.visible_cards())
        if not self.cards:
            text = self._empty_text
        elif not shown:
            category = self.filter.currentData() if self.filter.count() else None
            if category is not None and not self.search.text().strip():
                text = self._filter_empty.get(category) or translate("widgets", "Nothing is in this group.")
            else:
                text = translate("widgets", "Nothing matches your search.")
        else:
            text = ""
        self.message.setText(text)
        self.message.setVisible(bool(text))
        self._show_extra(text)
        self._content.setVisible(not text)
        self.search.setVisible(self._with_search and bool(self.cards))
        self.filter.setVisible(self.filter.count() > 0 and bool(self.cards))
        self.bar.setVisible(
            any(not child.isHidden() for child in self.bar.children() if isinstance(child, QWidget))
        )

    def ask_again_for_thumbnails(self) -> None:
        """Let the cards that have no picture ask for it when they are painted next. A page that is
        left cancels the pictures still being made, and a card asks only once."""
        for card in self.cards:
            if not card.has_thumbnail():
                card._requested = False

    def _thumbnail_wanted(self, card: Card) -> None:
        if not card.has_thumbnail():
            self.thumbnail_requested.emit(card.item_id)

    def _ring_target(self) -> Card | None:
        if not self.body.hasFocus():
            return None
        card = self._by_id.get(self._selected)
        if card is not None and not card.isHidden():
            return card
        shown = self._navigable()
        return shown[0] if shown else None

    def _sync_ring(self) -> None:
        target = self._ring_target()
        for card in self.cards:
            ring = card is target
            if card.focus_ring != ring:
                card.focus_ring = ring
                card.update()

    def _reveal(self, card: Card) -> None:
        area = self.scroll or _scroll_area_of(self)
        if area is not None:
            self.flow.activate()
            area.ensureWidgetVisible(card, 0, 24)

    # ---- user input

    def _navigable(self) -> list[Card]:
        return [c for c in self.cards if not c.isHidden() and c.isEnabled()]

    def _clicked(self, card: Card) -> None:
        self._pick(card, focus=True)

    def _pick(self, card: Card, focus=False) -> None:
        self._selected = card.item_id
        for other in self.cards:
            other.setChecked(other is card)
        if focus:
            self.body.setFocus()
        self._sync_ring()
        self._reveal(card)
        self.selected.emit(card.item_id)

    def _rows(self, cards: list[Card]) -> list[list[Card]]:
        rows: dict[int, list[Card]] = {}
        for card in cards:
            rows.setdefault(card.geometry().y(), []).append(card)
        return [sorted(rows[y], key=lambda c: c.geometry().x()) for y in sorted(rows)]

    def _page_rows(self) -> int:
        area = self.scroll or _scroll_area_of(self)
        if area is None or not self.cards:
            return 3
        height = self.cards[0].sizeHint().height() + LARGE_SPACING
        return max(1, area.viewport().height() // height - 1)

    def _target(self, key) -> Card | None:
        shown = self._navigable()
        if not shown:
            return None
        current = self._by_id.get(self._selected)
        if current not in shown:
            return shown[-1] if key == Qt.Key.Key_End else shown[0]
        self.flow.activate()
        if self.body.layoutDirection() == _RIGHT_TO_LEFT:
            key = {Qt.Key.Key_Left: Qt.Key.Key_Right, Qt.Key.Key_Right: Qt.Key.Key_Left}.get(key, key)
        index = shown.index(current)
        if key == Qt.Key.Key_Right:
            return shown[min(index + 1, len(shown) - 1)]
        if key == Qt.Key.Key_Left:
            return shown[max(index - 1, 0)]
        if key == Qt.Key.Key_Home:
            return shown[0]
        if key == Qt.Key.Key_End:
            return shown[-1]
        rows = self._rows(shown)
        row = next(i for i, cards in enumerate(rows) if current in cards)
        step = self._page_rows() if key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown) else 1
        if key in (Qt.Key.Key_Up, Qt.Key.Key_PageUp):
            step = -step
        target = min(max(row + step, 0), len(rows) - 1)
        if target == row:
            return current
        x = current.geometry().x()
        return min(rows[target], key=lambda c: abs(c.geometry().x() - x))

    def _key_pressed(self, event) -> bool:
        key = event.key()
        if key in _MOVES:
            card = self._target(key)
            if card is not None and card.item_id != self._selected:
                self._pick(card)
            return True
        current = self._by_id.get(self._selected)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or (key == Qt.Key.Key_Space and not self._typed):
            current = current or (self._navigable() or [None])[0]
            if current is not None:
                if current.item_id != self._selected:
                    self._pick(current)
                self.activated.emit(current.item_id)
            return True
        if key == Qt.Key.Key_Delete and current is not None and current.action() == "remove":
            self.remove_requested.emit(current.item_id)
            return True
        text = event.text()
        if text.isprintable() and text.strip() or (self._typed and text == " "):
            if self.search.isVisible():
                self.search.setFocus()
                self.search.setText(self.search.text() + text)
                return True
            if self._type_ahead:
                self._typed += text.casefold()
                self._typed_timer.start()
                for card in self._navigable():
                    if card.text().casefold().startswith(self._typed):
                        if card.item_id != self._selected:
                            self._pick(card)
                        break
                return True
        return False

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Down and self.visible_cards():
                self.body.setFocus()
                return True
        return super().eventFilter(watched, event)


class Segmented(QWidget):
    """An exclusive row of checkable buttons: "From color scheme | From wallpaper | Custom".

    One tab stop; Left and Right (mirrored in right-to-left) change the choice.
    """

    changed = Signal(int)  # the user chose this segment

    def __init__(self, labels, current=0, name="", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for i, label in enumerate(labels):
            button = _SegmentButton(label)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setChecked(i == current)
            self.group.addButton(button, i)
            layout.addWidget(button)
        self.group.idClicked.connect(self.changed)
        self.group.idClicked.connect(lambda _: self.setFocus())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        if name:
            self.setAccessibleName(name)

    def current(self) -> int:
        return self.group.checkedId()

    def set_current(self, index: int) -> None:
        """Choose a segment without a signal."""
        button = self.group.button(index)
        if button is not None:
            button.setChecked(True)

    def button(self, index: int) -> QPushButton:
        return self.group.button(index)

    def keyPressEvent(self, event):
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(event.key())
        if step is None:
            super().keyPressEvent(event)
            return
        if self.layoutDirection() == _RIGHT_TO_LEFT:
            step = -step
        target = self.current() + step
        if 0 <= target < len(self.group.buttons()):
            self.set_current(target)
            self.changed.emit(target)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()
        for button in self.group.buttons():
            button.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        for button in self.group.buttons():
            button.update()


class _SegmentButton(QPushButton):
    """A chip: a rounded pill, an accent fill when checked with text that reads on that accent (white or
    dark, whichever has the better contrast), a quiet outline when not, in light and dark."""

    def __init__(self, text):
        super().__init__(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        # A minimum size, not a `sizeHint` override: PySide crashes when a layout asks a Python sizeHint
        # of a widget that is being deleted.
        metrics = self.fontMetrics()
        self.setMinimumSize(metrics.horizontalAdvance(text) + 28, metrics.height() + 12)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        palette = self.palette()
        text = palette.color(QPalette.ColorRole.ButtonText)
        accent = palette.color(QPalette.ColorRole.Highlight)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2
        if self.isChecked():
            p.setBrush(accent)
            p.setPen(Qt.PenStyle.NoPen)
            fill = Color(accent.red(), accent.green(), accent.blue())
            ink = readable_on(fill, dark=Color(35, 38, 41))
            ink = QColor(ink.r, ink.g, ink.b)
        else:
            p.setBrush(with_alpha(text, 0.14 if self._hover else 0.07))
            p.setPen(QPen(with_alpha(text, 0.3), 1))
            ink = text
        p.drawRoundedRect(rect, radius, radius)
        if self.isChecked() and self.parentWidget() and self.parentWidget().hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(ink, 0.8), 1.5, Qt.PenStyle.DotLine))
            p.drawRoundedRect(rect.adjusted(3, 3, -3, -3), radius - 3, radius - 3)
        p.setPen(ink)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class _IconLabel(QWidget):
    """A theme icon, or when the theme has none a colored disc with a letter."""

    def __init__(self, icon_names: tuple[str, str], color: str, glyph: str, size=22, parent=None):
        super().__init__(parent)
        self.icon = themed_icon(*icon_names)
        self.color, self.glyph, self.size = color, glyph, size
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        if not self.icon.isNull():
            self.icon.paint(p, self.rect())
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))
        p.setPen(QColor("white"))
        font = QFont(self.font())
        font.setBold(True)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.glyph)


class MoreAbout(QWidget):
    """A "More about this" line that opens its detail in place. Hidden while there is no detail."""

    toggled = Signal(bool)

    def __init__(self, detail="", lead="", head=None, parent=None):
        """`lead` is one line of plain words that stands before the "More about this" button, `head` a
        widget (a check box, say) that stands before the lead."""
        super().__init__(parent)
        self.lead = QLabel(lead)
        self.lead.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.lead.setVisible(bool(lead))
        self.button = QToolButton()
        self.button.setAutoRaise(True)
        self.button.setCheckable(True)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setText(translate("widgets", "More about this"))
        self.button.toggled.connect(self._toggled)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail.setForegroundRole(QPalette.ColorRole.WindowText)
        self.detail.hide()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING)
        if head is not None:
            row.addWidget(head)
        row.addWidget(self.lead)
        row.addWidget(self.button)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(row)
        layout.addWidget(self.detail)
        self._arrow()
        self.set_detail(detail)

    def _arrow(self) -> None:
        opened = self.button.isChecked()
        self.button.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)

    def _toggled(self, open_: bool) -> None:
        self._arrow()
        self.detail.setVisible(open_)
        self.toggled.emit(open_)

    def set_detail(self, text: str) -> None:
        """The text behind the line; with none the whole widget is hidden (and closed)."""
        self.detail.setText(text)
        if not text:
            self.button.setChecked(False)
        self.setVisible(bool(text))

    def is_open(self) -> bool:
        return self.button.isChecked()

    def open(self, on: bool = True) -> None:
        self.button.setChecked(on)


class InlineNote(QFrame):
    """A tinted strip like KMessageWidget. kind: information, warning, positive or error.
    `set_text(text, more)` keeps `more` (the technical detail) behind a "More about this" line."""

    LOOK = {
        "information": (("dialog-information", ""), INFORMATION, "i"),
        "warning": (("dialog-warning", ""), WARNING, "!"),
        "positive": (("emblem-success", "dialog-ok"), POSITIVE, "✓"),
        "error": (("dialog-error", ""), NEGATIVE, "×"),
    }
    action_triggered = Signal()

    def __init__(self, text="", kind="information", action_text="", more="", parent=None):
        super().__init__(parent)
        self.kind = kind if kind in self.LOOK else "information"
        icon, rgb, glyph = self.LOOK[self.kind]
        self.icon = _IconLabel(icon, rgb, glyph)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.more = MoreAbout(more)
        self.action = QPushButton(action_text)
        self.action.setVisible(bool(action_text))
        self.action.clicked.connect(self.action_triggered)
        words = QVBoxLayout()
        words.setContentsMargins(0, 0, 0, 0)
        words.setSpacing(2)
        words.addWidget(self.label)
        words.addWidget(self.more)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(words, 1)
        layout.addWidget(self.action, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setAccessibleName(text)

    def text(self) -> str:
        return self.label.text()

    def set_text(self, text: str, more: str = "") -> None:
        self.label.setText(text)
        self.more.set_detail(more)
        self.setAccessibleName(text)

    def paintEvent(self, _):
        color = QColor(self.LOOK[self.kind][1])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(with_alpha(color, 0.16))
        p.setPen(QPen(color, 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)


class PageHeader(QWidget):
    """The title and subtitle of a page with actions on the right and an optional part switch below.

    The part switch is the one place that says "Leave as it is" or "Set by this theme".
    """

    part_mode_changed = Signal(bool)  # True: set by this theme

    def __init__(self, title="", subtitle="", parent=None):
        super().__init__(parent)
        self.title = QLabel(title)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        font = self.title.font()
        font.setPointSizeF(font.pointSizeF() * 1.45) if font.pointSizeF() > 0 else None
        font.setWeight(QFont.Weight.DemiBold)
        self.title.setFont(font)
        self.title.setAccessibleName(title)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle.setWordWrap(True)
        self.subtitle.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.subtitle.setVisible(bool(subtitle))
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(SPACING)
        top = QHBoxLayout()
        top.setSpacing(LARGE_SPACING)
        top.addLayout(text, 1)
        top.addLayout(self.actions)
        top.setAlignment(self.actions, Qt.AlignmentFlag.AlignTop)
        self.part_switch: Segmented | None = None
        self.hint: QLabel | None = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)
        self._layout.addLayout(top)

    def set_title(self, title: str) -> None:
        self.title.setText(title)
        self.title.setAccessibleName(title)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))

    def add_action(self, button: QWidget) -> QWidget:
        self.actions.addWidget(button)
        return button

    def add_part_switch(self, set_by_theme=True) -> Segmented:
        """Add "Leave as it is | Set by this theme" and a hint label beside it."""
        self.part_switch = Segmented(
            [translate("widgets", "Leave as it is"), translate("widgets", "Set by this theme")],
            1 if set_by_theme else 0,
            name=translate("widgets", "This part of the desktop"),
        )
        self.part_switch.changed.connect(lambda i: self.part_mode_changed.emit(i == 1))
        self.hint = QLabel()
        self.hint.setTextFormat(Qt.TextFormat.PlainText)
        self.hint.setWordWrap(True)
        self.hint.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.part_switch)
        row.addWidget(self.hint, 1)
        self._layout.addLayout(row)
        return self.part_switch

    def set_part_mode(self, set_by_theme: bool) -> None:
        """Move the switch without a signal."""
        if self.part_switch is not None:
            self.part_switch.set_current(1 if set_by_theme else 0)

    def part_mode(self) -> bool:
        return self.part_switch is not None and self.part_switch.current() == 1

    def set_hint(self, text: str) -> None:
        if self.hint is not None:
            self.hint.setText(text)


class NavList(QListWidget):
    """The grouped side bar. Group captions cannot be selected, so the arrow keys skip them.

    Each page has a key. A row can carry the state CHANGED (a dot: the part changes the desktop on
    Apply) or OFF (a small ring: the part is left as it is).
    """

    current_changed = Signal(str)  # key of the page
    KEY = Qt.ItemDataRole.UserRole
    STATE = Qt.ItemDataRole.UserRole + 1
    GROUP = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QSize(22, 22))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setItemDelegate(_NavDelegate(self))
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(1)
        self.compact = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(translate("widgets", "Pages"))
        self.currentItemChanged.connect(self._changed)

    def add_group(self, caption: str) -> None:
        item = QListWidgetItem(caption)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setData(self.GROUP, True)
        self.addItem(item)

    def add_page(self, key: str, title: str, icon="", state="", fallback_icon="") -> QListWidgetItem:
        """icon is a QIcon or the name of a theme icon; with neither, a blank keeps the text aligned."""
        if not isinstance(icon, QIcon):
            icon = themed_icon(icon, fallback_icon) if icon else QIcon()
        if icon.isNull():
            blank = QPixmap(22, 22)
            blank.fill(Qt.GlobalColor.transparent)
            icon = QIcon(blank)
        item = QListWidgetItem(icon, title)
        item.setData(self.KEY, key)
        self.addItem(item)
        self._describe(item, state)
        return item

    def row_heights(self, compact: bool) -> tuple[int, int]:
        """(height of a page row, height of a group caption). The compact sizes are used when the
        whole list would not fit the height of the window, so that every entry is reachable without
        a scroll bar when that is possible."""
        return (28, 24) if compact else (36, 34)

    def _needed_height(self, compact: bool) -> int:
        page, group = self.row_heights(compact)
        rows = [group if self.item(r).data(self.GROUP) else page for r in range(self.count())]
        return sum(rows) + (0 if compact else self.count() * 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self._needed_height(False) > self.viewport().height()
        if compact != self.compact:
            self.compact = compact
            self.setSpacing(0 if compact else 1)
            self.scheduleDelayedItemsLayout()

    def _item(self, key: str) -> QListWidgetItem | None:
        for row in range(self.count()):
            if self.item(row).data(self.KEY) == key:
                return self.item(row)
        return None

    def keys(self) -> list[str]:
        return [self.item(r).data(self.KEY) for r in range(self.count()) if self.item(r).data(self.KEY)]

    def current_key(self) -> str:
        item = self.currentItem()
        return (item.data(self.KEY) if item else "") or ""

    def set_current(self, key: str) -> None:
        item = self._item(key)
        if item is not None:
            self.setCurrentItem(item)

    def set_state(self, key: str, state: str) -> None:
        item = self._item(key)
        if item is not None:
            self._describe(item, state)
            self.viewport().update()

    def state(self, key: str) -> str:
        item = self._item(key)
        return (item.data(self.STATE) or "") if item else ""

    def _describe(self, item: QListWidgetItem, state: str) -> None:
        item.setData(self.STATE, state)
        extra = {
            CHANGED: translate("widgets", "will change when you apply"),
            OFF: translate("widgets", "left as it is"),
        }.get(state, "")
        item.setData(Qt.ItemDataRole.AccessibleTextRole, f"{item.text()}, {extra}" if extra else item.text())
        item.setToolTip(extra[:1].upper() + extra[1:] if extra else "")

    def _changed(self, current, _previous) -> None:
        if current is not None and current.data(self.KEY):
            self.current_changed.emit(current.data(self.KEY))


def icon_is_dark(icon: QIcon, side: int = 22) -> bool:
    """True when the icon has next to nothing light in it (so it would vanish on a dark background)."""
    image = icon.pixmap(side, side).toImage().convertToFormat(QImage.Format.Format_ARGB32)
    weight = light = 0.0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            weight += color.alphaF()
            if color.lightnessF() > 0.55:
                light += color.alphaF()
    return weight > 0 and light / weight < 0.12


class _NavDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark_icons: dict[int, bool] = {}

    def _light_tile(self, p, option, index, selected: bool) -> None:
        """A dark icon on a dark side bar gets a light rounded tile behind it, so that it can be seen."""
        if selected or option.palette.window().color().lightnessF() > 0.5:
            return
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if not isinstance(icon, QIcon) or icon.isNull():
            return
        key = icon.cacheKey()
        if key not in self._dark_icons:
            self._dark_icons[key] = icon_is_dark(icon)
        if not self._dark_icons[key]:
            return
        area = QStyleOptionViewItem(option)
        self.initStyleOption(area, index)
        where = option.widget.style().subElementRect(
            QStyle.SubElement.SE_ItemViewItemDecoration, area, option.widget
        )
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 215))
        p.drawRoundedRect(QRectF(where).adjusted(-2, -2, 2, 2), 5, 5)

    def sizeHint(self, option, index):
        page, group = option.widget.row_heights(option.widget.compact)
        return QSize(0, group if index.data(NavList.GROUP) else page)

    def paint(self, p, option, index):
        rtl = option.direction == _RIGHT_TO_LEFT
        if index.data(NavList.GROUP):
            p.save()
            font = scaled_font(option.font, 0.85)
            font.setBold(True)
            font.setCapitalization(QFont.Capitalization.AllUppercase)
            font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104)
            p.setFont(font)
            p.setPen(with_alpha(option.palette.windowText().color(), 0.6))
            align = Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
            p.drawText(
                option.rect.adjusted(12, 4 if option.widget.compact else 10, -12, 0),
                align | Qt.AlignmentFlag.AlignVCenter,
                index.data(),
            )
            p.restore()
            return
        state = index.data(NavList.STATE)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        p.save()
        self._light_tile(p, option, index, selected)
        super().paint(p, option, index)
        p.restore()
        if state == OFF:  # the label keeps its full contrast; a small neutral ring says "left as it is"
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            palette = option.palette
            color = palette.highlightedText().color() if selected else palette.windowText().color()
            p.setPen(QPen(with_alpha(color, 0.45), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            x = option.rect.left() + 14 if rtl else option.rect.right() - 14
            p.drawEllipse(QPointF(x, option.rect.center().y()), 3.2, 3.2)
            p.restore()
        if state == CHANGED:
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            palette = option.palette
            p.setBrush(palette.highlightedText().color() if selected else palette.highlight().color())
            p.setPen(Qt.PenStyle.NoPen)
            x = option.rect.left() + 14 if rtl else option.rect.right() - 14
            p.drawEllipse(QPoint(x, option.rect.center().y()), 4, 4)
            p.restore()


class _ElidedLabel(QLabel):
    """One line of plain text that is cut with "…" when it does not fit, and then shows all in a tip."""

    def __init__(self):
        super().__init__()
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setPen(self.palette().windowText().color())
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        align = (
            Qt.AlignmentFlag.AlignRight
            if self.layoutDirection() == _RIGHT_TO_LEFT
            else Qt.AlignmentFlag.AlignLeft
        )
        p.drawText(self.rect(), align | Qt.AlignmentFlag.AlignVCenter, text)
        self.setToolTip(self.text() if text != self.text() else "")


class DesktopBar(QWidget):
    """The permanent bar at the bottom of the window: what Apply will do, and its buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending = False
        self.status = _ElidedLabel()
        self.files_button = QPushButton(
            themed_icon("document-open", "text-x-generic"), translate("widgets", "Show files…")
        )
        self.files_button.setFlat(True)
        self.snapshots_button = QPushButton(
            themed_icon("document-open-recent", "view-history"), translate("widgets", "Snapshots…")
        )
        self.undo_button = QPushButton(themed_icon("edit-undo"), translate("widgets", "Undo last apply"))
        self.apply_button = QPushButton(
            themed_icon("dialog-ok-apply", "dialog-ok"), translate("widgets", "Apply to Desktop")
        )
        # Ctrl+Return belongs to the Desktop menu action of the window, which is the only place for it
        self._dot = _StatusDot(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 1, 16, 0)
        layout.setSpacing(SPACING)
        layout.addWidget(self._dot)
        layout.addWidget(self.status, 1)
        for button in (self.files_button, self.snapshots_button, self.undo_button, self.apply_button):
            layout.addWidget(button)
        self.setMinimumHeight(54)

    def set_status(self, text: str, pending: bool | None = None) -> None:
        """The sentence on the left. `pending` colors its dot: True when Apply would change something."""
        self.status.setText(text)
        self.status.setAccessibleName(text)
        if pending is not None:
            self._pending = pending
            self._dot.update()

    def pending(self) -> bool:
        return self._pending

    def paintEvent(self, _):
        p = QPainter(self)
        p.setPen(with_alpha(self.palette().windowText().color(), 0.18))
        p.drawLine(0, 0, self.width(), 0)


class _StatusDot(QWidget):
    def __init__(self, bar: DesktopBar):
        super().__init__(bar)
        self.bar = bar
        self.setFixedSize(10, 10)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(
            palette.highlight().color() if self.bar.pending() else with_alpha(palette.text().color(), 0.3)
        )
        p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))


class _Swatch(QAbstractButton):
    """A round color button; the checked one has a ring in the accent and a tick."""

    SIZE = 40

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setCheckable(True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(self.color.name().upper())
        self.setToolTip(self.color.name().upper())

    def nextCheckState(self):
        self.setChecked(True)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and isinstance(self.parent(), ColorDots):
            self.parent()._step(self, -1 if event.key() == Qt.Key.Key_Left else 1)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _):
        palette = self.palette()
        highlight, text = palette.highlight().color(), palette.text().color()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = self.SIZE
        if self.isChecked():
            p.setPen(QPen(highlight, 2.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(1.5, 1.5, side - 3, side - 3))
        elif self.underMouse():
            p.setPen(QPen(with_alpha(text, 0.35), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(2, 2, side - 4, side - 4))
        inset = 9 if self.isChecked() else 6
        p.setPen(QPen(with_alpha(text, 0.3), 1))
        p.setBrush(self.color)
        p.drawEllipse(QRectF(inset, inset, side - 2 * inset, side - 2 * inset))
        if self.isChecked():
            pen = QPen(QColor(readable_on(Color.parse(self.color.name()), dark=BLACK).hex), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            c = QPointF(side / 2, side / 2)
            p.drawPolyline([c + QPointF(-4, 0), c + QPointF(-1, 3), c + QPointF(5, -3)])
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(text, 0.8), 1.5, Qt.PenStyle.DotLine))
            p.drawEllipse(QRectF(0.75, 0.75, side - 1.5, side - 1.5))


class ColorDots(QWidget):
    """A row of round color buttons, one checked, and a "Custom…" button that opens a color dialog.

    Tab reaches every swatch; Left and Right (mirrored in right-to-left) pick the next or previous one.
    """

    picked = Signal(QColor)  # the user chose a color

    def __init__(self, colors=(), parent=None):
        super().__init__(parent)
        self._swatches: list[_Swatch] = []
        self._custom: _Swatch | None = None
        self.custom_button = QPushButton(translate("widgets", "Custom…"))
        self.custom_button.clicked.connect(self._choose_custom)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.addWidget(self.custom_button)
        self._layout.addStretch(1)
        self.setAccessibleName(translate("widgets", "Accent color"))
        self.set_colors(colors)

    def _all(self) -> list[_Swatch]:
        return self._swatches + ([self._custom] if self._custom else [])

    def _add(self, color: QColor) -> _Swatch:
        swatch = _Swatch(color, self)
        swatch.clicked.connect(lambda _=False, s=swatch: self._user_picked(s))
        return swatch

    def _user_picked(self, swatch: _Swatch) -> None:
        for other in self._all():
            other.setChecked(other is swatch)
        self.picked.emit(QColor(swatch.color))

    def _step(self, swatch: _Swatch, delta: int) -> None:
        if self.layoutDirection() == _RIGHT_TO_LEFT:
            delta = -delta
        swatches = self._all()
        target = (
            swatches[swatches.index(swatch) + delta]
            if 0 <= swatches.index(swatch) + delta < len(swatches)
            else None
        )
        if target is not None:
            target.setFocus()
            self._user_picked(target)

    def _drop(self, swatches) -> None:
        for swatch in swatches:
            swatch.hide()
            swatch.deleteLater()

    def set_colors(self, colors) -> None:
        """Replace the swatches (QColor or "#rrggbb"); none is checked afterwards."""
        self._drop(self._all())
        self._swatches, self._custom = [], None
        for i, color in enumerate(colors):
            swatch = self._add(QColor(color))
            self._swatches.append(swatch)
            self._layout.insertWidget(i, swatch)

    def colors(self) -> list[QColor]:
        return [QColor(s.color) for s in self._swatches]

    def current(self) -> QColor | None:
        for swatch in self._all():
            if swatch.isChecked():
                return QColor(swatch.color)
        return None

    def set_current(self, color) -> None:
        """Check the swatch of this color, or show it as a custom one; without a signal. None clears."""
        for swatch in self._all():
            swatch.setChecked(False)
        if color is None:
            return
        color = QColor(color)
        for swatch in self._swatches:
            if swatch.color.rgb() == color.rgb():
                swatch.setChecked(True)
                return
        self._drop([self._custom] if self._custom else [])
        self._custom = self._add(color)
        self._layout.insertWidget(len(self._swatches), self._custom)
        self._custom.setChecked(True)

    def _choose_custom(self) -> None:
        color = QColorDialog.getColor(
            self.current() or QColor(INFORMATION), self, translate("widgets", "Choose a Color")
        )
        if color.isValid():
            self.set_current(color)
            self.picked.emit(color)
