# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The controls the inspector uses, one per kind of theme field.

Every editor has `set_value(value)` (never emits) and a `changed` signal
that carries the new value when the user edits it.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..model.color import Color
from ..model.theme import Field
from .labels import CHOICE_LABELS

translate = QCoreApplication.translate

# What an optional number starts at when the user first gives it a value.
# 44 px is the thickness of Plasma's default panel.
OPTIONAL_START = {("panel_layout", "height"): 44}


class TextEditor(QLineEdit):
    changed = Signal(object)

    def __init__(self, field: Field, parent=None):
        super().__init__(parent)
        self.setMaxLength(120)
        self.textEdited.connect(lambda text: self.changed.emit(text))

    def set_title(self, title: str) -> None:
        self.setAccessibleName(title)

    def set_value(self, value) -> None:
        if self.text() != value:
            self.setText(value)


class ColorEditor(QWidget):
    changed = Signal(object)

    def __init__(self, field: Field, parent=None):
        super().__init__(parent)
        self._value = "#000000"
        self._title = ""
        self.swatch = QToolButton()
        self.swatch.setIconSize(QSize(40, 20))
        self.swatch.setToolTip(translate("ui", "Choose a color"))
        self.swatch.clicked.connect(self._pick)
        self.text = QLineEdit()
        self.text.setMaxLength(7)
        self.text.setFixedWidth(self.text.fontMetrics().horizontalAdvance("#DDDDDDD") + 24)
        self.text.editingFinished.connect(self._typed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.swatch)
        layout.addWidget(self.text)
        layout.addStretch(1)
        self.setFocusProxy(self.text)

    def set_title(self, title: str) -> None:
        self._title = title
        self.swatch.setAccessibleName(title)
        self.text.setAccessibleName(title)

    def set_value(self, value) -> None:
        self._value = value
        pixmap = QPixmap(40, 20)
        pixmap.fill(QColor(value))
        self.swatch.setIcon(QIcon(pixmap))
        if self.text.text() != value:
            self.text.setText(value)

    def _typed(self) -> None:
        typed = self.text.text().strip()
        if typed and not typed.startswith("#"):
            typed = "#" + typed
        if Color.is_valid(typed):
            value = Color.parse(typed).hex
            if value != self._value:
                self.changed.emit(value)
            else:
                self.text.setText(value)
        else:
            self.text.setText(self._value)

    def _pick(self) -> None:
        dialog = QColorDialog(QColor(self._value), self)
        dialog.setWindowTitle(self._title)
        before = self._value
        dialog.currentColorChanged.connect(lambda color: self.changed.emit(color.name()))
        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            # Not every platform color dialog reports changes while it is open.
            chosen = dialog.selectedColor()
            if chosen.isValid() and chosen.name() != self._value:
                self.changed.emit(chosen.name())
        elif self._value != before:
            self.changed.emit(before)


class NumberEditor(QWidget):
    changed = Signal(object)

    def __init__(self, field: Field, parent=None):
        super().__init__(parent)
        self._float = field.kind == "float"
        self._steps = 100 if self._float else 1
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimumWidth(120)
        self.slider.setRange(round(field.minimum * self._steps), round(field.maximum * self._steps))
        if self._float:
            self.box = QDoubleSpinBox()
            self.box.setDecimals(2)
            self.box.setSingleStep(0.05)
        else:
            self.box = QSpinBox()
            self.box.setSuffix(translate("ui", " px"))
        self.box.setRange(field.minimum, field.maximum)
        self.slider.valueChanged.connect(self._slider_moved)
        self.box.valueChanged.connect(self._box_changed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.box)
        self.setFocusProxy(self.box)

    def set_title(self, title: str) -> None:
        self.slider.setAccessibleName(title)
        self.box.setAccessibleName(title)

    def set_value(self, value) -> None:
        for widget, shown in ((self.slider, round(value * self._steps)), (self.box, value)):
            blocked = widget.blockSignals(True)
            widget.setValue(shown)
            widget.blockSignals(blocked)

    def _slider_moved(self, position: int) -> None:
        self.changed.emit(position / self._steps if self._float else position)

    def _box_changed(self, value) -> None:
        self.changed.emit(round(value, 2) if self._float else value)


class ChoiceEditor(QComboBox):
    """One of a few named values. An optional field also offers to leave
    that part of the desktop as it is."""

    changed = Signal(object)

    def __init__(self, field: Field, parent=None):
        super().__init__(parent)
        if field.optional:
            self.addItem(translate("ui", "Leave as it is"), None)
        for value in (True, False) if field.kind == "bool" else field.choices:
            self.addItem(str(CHOICE_LABELS[field.id][value]), value)
        self.activated.connect(lambda index: self.changed.emit(self.itemData(index)))

    def set_title(self, title: str) -> None:
        self.setAccessibleName(title)

    def set_value(self, value) -> None:
        for index in range(self.count()):
            if self.itemData(index) == value:
                self.setCurrentIndex(index)

    def choose(self, value) -> None:
        """Pick a value the way the user does."""
        self.set_value(value)
        self.activated.emit(self.currentIndex())


class OptionalTextEditor(QWidget):
    """A text that is only used once the user gives it a value. Until then
    the desktop's own value is used."""

    changed = Signal(object)

    def __init__(self, field: Field, parent=None):
        super().__init__(parent)
        self.same = QCheckBox(translate("ui", "Same as the desktop"))
        self.text = QLineEdit()
        self.text.setMaxLength(200)
        self.same.toggled.connect(lambda checked: self.changed.emit(None if checked else self.text.text()))
        self.text.textEdited.connect(lambda text: self.changed.emit(text))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.same)
        layout.addWidget(self.text)
        self.setFocusProxy(self.same)

    def set_title(self, title: str) -> None:
        self.same.setAccessibleName(f"{title}: {self.same.text()}")
        self.text.setAccessibleName(title)

    def set_placeholder(self, text: str) -> None:
        """What to show while the field is empty, such as the value the desktop has."""
        self.text.setPlaceholderText(text)

    def set_value(self, value) -> None:
        blocked = self.same.blockSignals(True)
        self.same.setChecked(value is None)
        self.same.blockSignals(blocked)
        self.text.setEnabled(value is not None)
        if value is not None and self.text.text() != value:
            self.text.setText(value)


# What an inheriting number says it follows.
INHERIT_TEXTS = {
    "shape": translate("ui", "Same as Shapes"),
    "window": translate("ui", "Same as Windows"),
    "panel": translate("ui", "Same as Panel"),
}


class OverrideEditor(QWidget):
    """A number that is only used once the user gives it a value. Until
    then the field follows another field, or leaves the desktop as it is."""

    changed = Signal(object)

    def __init__(self, field: Field, parent=None):
        super().__init__(parent)
        self._value = None
        self._unset_value = OPTIONAL_START.get(field.id, field.minimum)
        self.same = QCheckBox(
            INHERIT_TEXTS[field.inherits[0]] if field.inherits else translate("ui", "Leave as it is")
        )
        self.number = NumberEditor(field)
        self.same.toggled.connect(lambda checked: self.changed.emit(None if checked else self._unset_value))
        self.number.changed.connect(lambda value: self.changed.emit(value))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.same)
        layout.addWidget(self.number)
        self.setFocusProxy(self.same)

    def set_title(self, title: str) -> None:
        self.same.setAccessibleName(f"{title}: {self.same.text()}")
        self.number.set_title(title)

    def set_inherited(self, value) -> None:
        """The value of the field this one follows while it is unset."""
        self._unset_value = value
        if self._value is None:
            self.number.set_value(value)

    def set_value(self, value) -> None:
        self._value = value
        blocked = self.same.blockSignals(True)
        self.same.setChecked(value is None)
        self.same.blockSignals(blocked)
        self.number.setEnabled(value is not None)
        self.number.set_value(self._unset_value if value is None else value)


def editor_for(field: Field) -> QWidget:
    if field.kind in ("choice", "bool"):
        return ChoiceEditor(field)
    if field.optional and field.kind == "str":
        return OptionalTextEditor(field)
    if field.inherits or field.optional:
        return OverrideEditor(field)
    if field.kind == "color":
        return ColorEditor(field)
    if field.kind == "str":
        return TextEditor(field)
    return NumberEditor(field)
