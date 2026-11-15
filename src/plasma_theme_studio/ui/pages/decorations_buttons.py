# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The dialog "Configure Titlebar Buttons": a drawn title bar with the buttons on its two sides and a
pool of the buttons that are not used. Buttons are dragged, or chosen and moved with the buttons below."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ...model.parts import BUTTONS, DEFAULT_BUTTONS, button_names, parse_buttons
from ..widgets import LARGE_SPACING, SPACING, mix

translate = QCoreApplication.translate

BUTTON = 30  # a button of the title bar
GAP = 6
BAR = 52  # the height of the drawn title bar
PAD = 12
CHIP = 36  # the height of a button in the pool
POOL_CAPTION = 30
SIDES = ("left", "right")
# The buttons of the pool in the order System Settings lists them. KWin 6 has no use for the shade button.
POOL_ORDER = tuple(letter for letter, _number, _name in BUTTONS if letter != "L")


def glyph(p: QPainter, letter: str, rect: QRectF, color: QColor) -> None:
    """The picture of one button, drawn with a few lines in `color`."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, max(1.4, rect.width() / 13))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    c, r = rect.center(), rect.width() * 0.26

    def line(*points: tuple[float, float]) -> None:
        path = QPainterPath(QPointF(c.x() + points[0][0] * r, c.y() + points[0][1] * r))
        for x, y in points[1:]:
            path.lineTo(c.x() + x * r, c.y() + y * r)
        p.drawPath(path)

    if letter == "X":
        line((-1, -1), (1, 1))
        line((-1, 1), (1, -1))
    elif letter == "A":  # maximize
        line((-1, 0.5), (0, -0.5), (1, 0.5))
    elif letter == "I":  # minimize
        line((-1, -0.5), (0, 0.5), (1, -0.5))
    elif letter == "N":  # application menu
        for y in (-0.8, 0, 0.8):
            line((-1, y), (1, y))
    elif letter == "M":  # window menu
        p.drawRoundedRect(QRectF(c.x() - r, c.y() - r * 0.9, r * 2, r * 1.8), r * 0.25, r * 0.25)
        line((-1, -0.3), (1, -0.3))
    elif letter == "S":  # on all desktops
        p.drawEllipse(c, r, r)
        p.setBrush(color)
        p.drawEllipse(c, r * 0.4, r * 0.4)
    elif letter == "H":  # help
        font = QFont(p.font())
        font.setBold(True)
        font.setPixelSize(max(8, round(rect.height() * 0.6)))
        p.setFont(font)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "?")
    elif letter == "F":  # keep above
        line((-1, -1), (1, -1))
        line((-0.8, 0.9), (0, -0.1), (0.8, 0.9))
    elif letter == "B":  # keep below
        line((-1, 1), (1, 1))
        line((-0.8, -0.9), (0, 0.1), (0.8, -0.9))
    elif letter == "L":  # shade
        line((-1, -0.9), (1, -0.9))
        line((-0.8, 0.8), (0, -0.2), (0.8, 0.8))
    elif letter == "E":  # hide from screenshots
        p.drawEllipse(c, r * 1.1, r * 0.7)
        line((-1.1, 1), (1.1, -1))
    elif letter == "_":  # a spacer
        line((-1, 0), (1, 0))
        line((-1, -0.5), (-1, 0.5))
        line((1, -0.5), (1, 0.5))
    p.restore()


class ButtonBoard(QWidget):
    """The title bar with its two sides and the pool of the other buttons.

    `sides` holds the letters of each side. A selected button is `(zone, index)` with the zone `left`,
    `right` or `pool`. A spacer can be used as often as wanted: the pool always has one."""

    changed = Signal()  # the buttons of a side changed
    selection_changed = Signal()

    def __init__(self, left: str = "", right: str = "", parent=None):
        super().__init__(parent)
        self.sides = {"left": list(left), "right": list(right)}
        self.selected: tuple[str, int] | None = None
        self.drag: dict | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(480)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setAccessibleName(translate("ui", "Title bar buttons"))
        self._describe()

    # ---- what is in use

    def text(self, side: str) -> str:
        return "".join(self.sides[side])

    def set_buttons(self, left: str, right: str) -> None:
        """Show these buttons (letters KWin does not know are left out)."""
        for side, text in zip(SIDES, (left, right), strict=True):
            self.sides[side] = list(text) if parse_buttons(text) is not None else []
        self.selected = None
        self._changed()

    def pool(self) -> list[str]:
        used = {letter for side in SIDES for letter in self.sides[side]}
        return [letter for letter in POOL_ORDER if letter not in used or letter == "_"]

    def zone(self, zone: str) -> list[str]:
        return self.pool() if zone == "pool" else self.sides[zone]

    def selected_letter(self) -> str | None:
        if self.selected is None:
            return None
        zone, index = self.selected
        letters = self.zone(zone)
        return letters[index] if 0 <= index < len(letters) else None

    def name_of(self, letter: str) -> str:
        return str(button_names()[letter])

    # ---- changing it (the buttons of the dialog, the keys and the mouse all end here)

    def select(self, zone: str | None, index: int = 0) -> None:
        self.selected = None if zone is None else (zone, index)
        self._describe()
        self.update()
        self.selection_changed.emit()

    def can_move(self, delta: int) -> bool:
        if self.selected is None or self.selected[0] == "pool":
            return False
        zone, index = self.selected
        return 0 <= index + delta < len(self.sides[zone])

    def move(self, delta: int) -> None:
        """Move the selected button one place left (-1) or right (+1) in its side."""
        if not self.can_move(delta):
            return
        zone, index = self.selected
        letters = self.sides[zone]
        letters[index], letters[index + delta] = letters[index + delta], letters[index]
        self.selected = (zone, index + delta)
        self._changed()

    def can_add(self, side: str) -> bool:
        return self.selected is not None and self.selected[0] != side

    def add(self, side: str) -> None:
        """Put the selected button at the end of this side (from the pool or from the other side)."""
        if self.can_add(side):
            zone, index = self.selected
            self.place(zone, index, side, len(self.sides[side]))

    def can_remove(self) -> bool:
        return self.selected is not None and self.selected[0] != "pool"

    def remove(self) -> None:
        if self.can_remove():
            zone, index = self.selected
            self.place(zone, index, "pool", 0)

    def place(self, zone: str, index: int, to: str, at: int) -> None:
        """Move the button `index` of `zone` to the place `at` of `to` (the pool takes it back)."""
        letters = self.zone(zone)
        if not 0 <= index < len(letters):
            return
        letter = letters[index]
        if zone in SIDES:
            del self.sides[zone][index]
        if to in SIDES:
            at = min(max(at, 0), len(self.sides[to]))
            self.sides[to].insert(at, letter)
            self.selected = (to, at)
        else:
            self.selected = ("pool", self.pool().index(letter))
        self._changed()

    def _changed(self) -> None:
        self._describe()
        self.updateGeometry()
        self.update()
        self.changed.emit()
        self.selection_changed.emit()

    def _describe(self) -> None:
        names = button_names()
        parts = []
        for side, title in zip(
            SIDES, (translate("ui", "On the left"), translate("ui", "On the right")), strict=True
        ):
            listed = ", ".join(str(names[letter]) for letter in self.sides[side]) or translate("ui", "none")
            parts.append(f"{title}: {listed}")
        self.setAccessibleDescription(". ".join(parts))

    # ---- where things are

    def _bar_zone(self, side: str) -> list[tuple[int, QRectF]]:
        count = len(self.sides[side])
        total = count * BUTTON + max(0, count - 1) * GAP
        x = PAD if side == "left" else self.width() - PAD - total
        top = (BAR - BUTTON) / 2
        return [(i, QRectF(x + i * (BUTTON + GAP), top, BUTTON, BUTTON)) for i in range(count)]

    def _chip_width(self, letter: str) -> int:
        return 14 + 22 + 8 + self.fontMetrics().horizontalAdvance(self.name_of(letter)) + 14

    def _chips(self, width: int) -> list[tuple[int, QRectF]]:
        x, y, found = 0.0, BAR + POOL_CAPTION, []
        for index, letter in enumerate(self.pool()):
            w = self._chip_width(letter)
            if x and x + w > width:
                x, y = 0.0, y + CHIP + GAP
            found.append((index, QRectF(x, y, w, CHIP)))
            x += w + GAP
        return found

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        chips = self._chips(width)
        return round(max(rect.bottom() for _i, rect in chips)) + 4 if chips else BAR + POOL_CAPTION

    def sizeHint(self) -> QSize:
        return QSize(640, self.heightForWidth(640))

    def items(self) -> list[tuple[str, int, QRectF]]:
        """Every button with the place it is drawn at: (zone, index, rectangle)."""
        found = [(side, i, rect) for side in SIDES for i, rect in self._bar_zone(side)]
        return found + [("pool", i, rect) for i, rect in self._chips(self.width())]

    def _item_at(self, pos) -> tuple[str, int] | None:
        for zone, index, rect in self.items():
            if rect.contains(QPointF(pos)):
                return zone, index
        return None

    def _target(self, pos) -> tuple[str, int]:
        """Where a button dropped at `pos` goes: a side and a place in it, or back to the pool."""
        if pos.y() > BAR + 4:
            return "pool", 0
        side = "left" if pos.x() < self.width() / 2 else "right"
        source = (self.drag["zone"], self.drag["index"]) if self.drag else None
        index = sum(
            1 for i, rect in self._bar_zone(side) if (side, i) != source and rect.center().x() < pos.x()
        )
        return side, index

    # ---- the mouse

    def mousePressEvent(self, event) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        hit = self._item_at(event.position()) if event.button() == Qt.MouseButton.LeftButton else None
        if hit is not None:
            self.select(*hit)
            self.drag = {"zone": hit[0], "index": hit[1], "start": event.position(), "moving": False}

    def mouseMoveEvent(self, event) -> None:
        if self.drag is None:
            return
        moved = (event.position() - self.drag["start"]).manhattanLength()
        if moved >= 6 or self.drag["moving"]:
            self.drag["moving"] = True
            self.drag["pos"] = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        drag, self.drag = self.drag, None
        self.unsetCursor()
        if drag is not None and drag["moving"]:
            to, at = self._target(event.position())
            if to == "pool" and drag["zone"] == "pool":
                pass  # a button of the pool dropped on the pool: nothing to do
            else:
                self.place(drag["zone"], drag["index"], to, at)
        self.update()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            hit = self._item_at(event.pos())
            letters = self.zone(hit[0]) if hit else []
            if hit and hit[1] < len(letters):
                QToolTip.showText(event.globalPos(), self.name_of(letters[hit[1]]), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    # ---- the keys

    def keyPressEvent(self, event) -> None:
        key, ctrl = event.key(), bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        order = [(zone, i) for zone in (*SIDES, "pool") for i in range(len(self.zone(zone)))]
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = -1 if key == Qt.Key.Key_Left else 1
            if ctrl:
                self.move(step)
            elif order:
                now = (
                    order.index(self.selected) if self.selected in order else (0 if step > 0 else len(order))
                )
                self.select(
                    *order[min(max(now + (step if self.selected in order else 0), 0), len(order) - 1)]
                )
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove()
        elif key in (Qt.Key.Key_Home, Qt.Key.Key_End) and order:
            self.select(*order[0 if key == Qt.Key.Key_Home else -1])
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        if self.selected is None and self.items():
            zone, index, _rect = self.items()[0]
            self.select(zone, index)
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.update()

    # ---- drawing

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        enabled = self.isEnabled()
        text, window = palette.color(QPalette.ColorRole.WindowText), palette.color(QPalette.ColorRole.Window)
        accent, on_accent = (
            palette.color(QPalette.ColorRole.Highlight),
            palette.color(QPalette.ColorRole.HighlightedText),
        )
        bar_fill = mix(window, text, 0.12)
        idle = mix(bar_fill, text, 0.10)
        p.setPen(QPen(mix(window, text, 0.25), 1))
        p.setBrush(bar_fill)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, BAR - 1), 8, 8)
        p.setPen(mix(window, text, 0.6))
        p.drawText(
            QRectF(0, 0, self.width(), BAR), Qt.AlignmentFlag.AlignCenter, translate("ui", "Window title")
        )
        caption_font = QFont(self.font())
        caption_font.setBold(True)
        p.setFont(caption_font)
        p.setPen(text)
        p.drawText(
            QRectF(0, BAR + 4, self.width(), POOL_CAPTION - 4),
            Qt.AlignmentFlag.AlignVCenter,
            translate("ui", "Buttons that are not used"),
        )
        p.setFont(self.font())

        source = (self.drag["zone"], self.drag["index"]) if self.drag and self.drag["moving"] else None
        target = self._target(self.drag["pos"]) if source else None
        p.setOpacity(1.0 if enabled else 0.5)
        for side in SIDES:  # an empty side shows where a button can be dropped
            if not self.sides[side]:
                x = PAD if side == "left" else self.width() - PAD - 2 * BUTTON
                p.setPen(QPen(mix(bar_fill, text, 0.35), 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(QRectF(x, (BAR - BUTTON) / 2, 2 * BUTTON, BUTTON), 6, 6)
        for zone, index, rect in self.items():
            letter = self.zone(zone)[index]
            chosen = self.selected == (zone, index)
            p.setOpacity((0.35 if (zone, index) == source else 1.0) * (1.0 if enabled else 0.5))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent if chosen else (idle if zone != "pool" else mix(window, text, 0.1)))
            p.drawRoundedRect(rect, 6, 6)
            ink = on_accent if chosen else text
            if zone == "pool":
                glyph(p, letter, QRectF(rect.left() + 14, rect.center().y() - 11, 22, 22), ink)
                p.setPen(ink)
                p.drawText(
                    rect.adjusted(14 + 22 + 8, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, self.name_of(letter)
                )
            else:
                glyph(p, letter, rect, ink)
            if chosen and self.hasFocus():
                p.setPen(QPen(text, 1, Qt.PenStyle.DotLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 8, 8)
        p.setOpacity(1.0)
        if source and target:
            self._paint_drag(p, source, target, accent)
        p.end()

    def _paint_drag(self, p: QPainter, source, target, accent: QColor) -> None:
        zone, at = target
        p.setBrush(Qt.BrushStyle.NoBrush)
        if zone == "pool":
            p.setPen(QPen(accent, 2))
            p.drawRoundedRect(QRectF(1, BAR + 2, self.width() - 2, self.height() - BAR - 4), 8, 8)
        else:
            rects = [rect for i, rect in self._bar_zone(zone) if (zone, i) != source]
            if rects:
                x = rects[at - 1].right() + GAP / 2 if at > 0 else rects[0].left() - GAP / 2
            else:
                x = PAD if zone == "left" else self.width() - PAD
            p.setPen(QPen(accent, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x, 7), QPointF(x, BAR - 7))
        letter = self.zone(source[0])[source[1]]
        pos = self.drag["pos"]
        ghost = QRectF(pos.x() - BUTTON / 2, pos.y() - BUTTON / 2, BUTTON, BUTTON)
        p.setOpacity(0.9)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(ghost, 6, 6)
        glyph(p, letter, ghost, self.palette().color(QPalette.ColorRole.HighlightedText))
        p.setOpacity(1.0)


class TitlebarButtonsDialog(QDialog):
    """Choose which buttons the title bar has and where. `left` and `right` are the theme's strings (None
    leaves a side as it is), `desktop` the strings the desktop has now."""

    def __init__(self, left: str | None, right: str | None, desktop: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("ui", "Configure Titlebar Buttons"))
        self._loading = False
        self.desktop = {side: desktop.get(side) or DEFAULT_BUTTONS[side] for side in SIDES}
        intro = QLabel(
            translate(
                "ui",
                "Drag buttons between the title bar and the pool below, or choose a button and use the "
                "buttons under it.",
            )
        )
        intro.setWordWrap(True)
        self.leave = QRadioButton(translate("ui", "Leave as it is"))
        self.own = QRadioButton(translate("ui", "Set by this theme"))
        group = QButtonGroup(self)
        group.addButton(self.leave)
        group.addButton(self.own)
        choice = QHBoxLayout()
        choice.setSpacing(LARGE_SPACING)
        choice.addWidget(self.leave)
        choice.addWidget(self.own)
        choice.addStretch(1)
        self.board = ButtonBoard()
        self.selected = QLabel()
        self.selected.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.buttons = {
            "move_left": QPushButton(translate("ui", "Move left")),
            "move_right": QPushButton(translate("ui", "Move right")),
            "remove": QPushButton(translate("ui", "Remove")),
            "add_left": QPushButton(translate("ui", "Add to the left side")),
            "add_right": QPushButton(translate("ui", "Add to the right side")),
        }
        self.buttons["move_left"].clicked.connect(lambda: self.board.move(-1))
        self.buttons["move_right"].clicked.connect(lambda: self.board.move(1))
        self.buttons["remove"].clicked.connect(self.board.remove)
        self.buttons["add_left"].clicked.connect(lambda: self.board.add("left"))
        self.buttons["add_right"].clicked.connect(lambda: self.board.add("right"))
        actions = QHBoxLayout()
        actions.setSpacing(SPACING)
        for button in self.buttons.values():
            actions.addWidget(button)
        actions.addStretch(1)
        self.box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        self.defaults = self.box.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        self.defaults.setText(translate("ui", "Defaults"))
        self.defaults.clicked.connect(self.use_defaults)
        self.box.accepted.connect(self.accept)
        self.box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(LARGE_SPACING)
        layout.addWidget(intro)
        layout.addLayout(choice)
        layout.addWidget(self.board)
        layout.addWidget(self.selected)
        layout.addLayout(actions)
        layout.addStretch(1)
        layout.addWidget(self.box)

        self.leave.setChecked(left is None and right is None)
        self.own.setChecked(not self.leave.isChecked())
        self._show(
            left if left is not None else self.desktop["left"],
            right if right is not None else self.desktop["right"],
        )
        self.board.selected = None
        self.leave.toggled.connect(self._leave_toggled)
        self.board.changed.connect(self._board_changed)
        self.board.selection_changed.connect(self._sync)
        self._leave_toggled(self.leave.isChecked())
        self.setMinimumWidth(640)

    def _leave_toggled(self, leave: bool) -> None:
        """The board is always usable and shows the desktop's layout while the choice is to leave it."""
        if leave:
            self._show(self.desktop["left"], self.desktop["right"])
        self._sync()

    def _show(self, left: str, right: str) -> None:
        self._loading = True
        try:
            self.board.set_buttons(left, right)
        finally:
            self._loading = False

    def _board_changed(self) -> None:
        if self.leave.isChecked() and not self._loading:
            self.own.setChecked(True)

    def use_defaults(self) -> None:
        self.own.setChecked(True)
        self._show(DEFAULT_BUTTONS["left"], DEFAULT_BUTTONS["right"])

    def _sync(self) -> None:
        board, free = self.board, True
        letter = board.selected_letter()
        self.buttons["move_left"].setEnabled(free and board.can_move(-1))
        self.buttons["move_right"].setEnabled(free and board.can_move(1))
        self.buttons["remove"].setEnabled(free and board.can_remove())
        self.buttons["add_left"].setEnabled(free and board.can_add("left"))
        self.buttons["add_right"].setEnabled(free and board.can_add("right"))
        if letter is None or not free:
            self.selected.setText(translate("ui", "Choose a button to move it."))
        else:
            self.selected.setText(translate("ui", "Chosen: {button}").format(button=board.name_of(letter)))

    def values(self) -> tuple[str | None, str | None]:
        """What the theme gets: a string for each side, or None for both when the buttons are left alone."""
        if self.leave.isChecked():
            return None, None
        return self.board.text("left"), self.board.text("right")
