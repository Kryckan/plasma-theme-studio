# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One row of the Fonts page: a sample drawn in the font, its name and size, and the buttons."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QWidget

from ...model.parts import FontSpec

translate = QCoreApplication.translate

SAMPLE_LOW, SAMPLE_HIGH = 8.0, 22.0  # the sample is drawn at the font's size, within these points
ROLE_WIDTH = 120


def sample_text() -> str:
    return translate("ui", "The quick brown fox jumps over the lazy dog")


def qfont_of(spec: FontSpec, limit: bool = False) -> QFont:
    """The QFont of a FontSpec. `limit` keeps the size where a sample line still fits a row."""
    font = QFont(spec.family)
    size = max(SAMPLE_LOW, min(SAMPLE_HIGH, spec.size)) if limit else spec.size
    font.setPointSizeF(size)
    try:
        font.setWeight(QFont.Weight(spec.weight))
    except ValueError:  # a weight between the named ones: the nearest named one
        font.setWeight(QFont.Weight(min(900, max(100, round(spec.weight / 100) * 100))))
    font.setItalic(spec.italic)
    return font


def spec_of(font: QFont) -> FontSpec:
    size = font.pointSizeF()
    return FontSpec(font.family(), size if size > 0 else 10.0, font.weight().value, font.italic())


def default_spec(key: str) -> FontSpec:
    """A font for a role when the desktop's cannot be read: what Qt itself uses for that role."""
    kind = {
        "fixed": QFontDatabase.SystemFont.FixedFont,
        "small": QFontDatabase.SystemFont.SmallestReadableFont,
        "window_title": QFontDatabase.SystemFont.TitleFont,
    }.get(key, QFontDatabase.SystemFont.GeneralFont)
    return spec_of(QFontDatabase.systemFont(kind))


class _Elided(QLabel):
    """A line of text that is cut with an ellipsis instead of widening the row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def minimumSizeHint(self) -> QSize:
        return QSize(40, self.sizeHint().height())

    def sizeHint(self) -> QSize:
        return QSize(200, QFontMetrics(self.font()).height() + 6)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        p.setFont(self.font())
        metrics = QFontMetrics(self.font())
        p.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width()),
        )


class FontRow(QWidget):
    """The font of one role. `set_value(text)` takes the short form of a theme file or None (left as it
    is). `leave_clicked(on)` and the button `choose` are the person's actions; the page edits the theme."""

    leave_clicked = Signal(bool)

    def __init__(self, key: str, title: str, full_title: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._value: str | None = None
        self._present: FontSpec | None = None
        self.role = QLabel(title)
        self.role.setFixedWidth(ROLE_WIDTH)
        self.sample = _Elided()
        self.sample.setText(sample_text())
        self.text = QLineEdit()  # the name and size; while empty it shows the desktop's own font
        self.text.setReadOnly(True)
        self.text.setFrame(False)
        self.text.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        palette = self.text.palette()
        palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.transparent)
        self.text.setPalette(palette)
        small = self.text.font()
        small.setPointSizeF(max(8.0, small.pointSizeF() * 0.9))
        self.text.setFont(small)
        self.choose = QPushButton(translate("ui", "Choose…"))
        self.choose.setAccessibleName(translate("ui", "Choose {font}").format(font=full_title))
        self.leave = QCheckBox(translate("ui", "Leave as it is"))
        self.leave.setAccessibleName(translate("ui", "Leave {font} as it is").format(font=full_title))
        self.leave.clicked.connect(self.leave_clicked)
        self.setAccessibleName(full_title)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 6, 0, 6)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(0)
        grid.addWidget(self.role, 0, 0, 2, 1, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.sample, 0, 1)
        grid.addWidget(self.text, 1, 1)
        grid.addWidget(self.choose, 0, 2, 2, 1, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.leave, 0, 3, 2, 1, Qt.AlignmentFlag.AlignVCenter)
        grid.setColumnStretch(1, 1)
        self.setFocusProxy(self.choose)
        self._show()

    @property
    def value(self) -> str | None:
        return self._value

    def set_title(self, title: str) -> None:
        self.setAccessibleName(title)

    def set_value(self, value) -> None:
        self._value = value if isinstance(value, str) and value else None
        self._show()

    def set_present(self, spec: FontSpec | None) -> None:
        """The font the desktop has now, shown (dimmed) while this role is left as it is."""
        self._present = spec
        self._show()

    def _show(self) -> None:
        spec = FontSpec.from_short(self._value) if self._value else None
        left = self._value is None
        shown = spec or (self._present if left else None)
        self.leave.setChecked(left)
        self.sample.setFont(qfont_of(shown, True) if shown else QFont(self.font()))
        self.sample.setForegroundRole(QPalette.ColorRole.PlaceholderText if left else QPalette.ColorRole.Text)
        self.sample.updateGeometry()
        self.sample.update()
        if spec is not None:
            self.text.setText(spec.label())
        elif self._value:  # a value this app cannot read: show it as it is
            self.text.setText(self._value)
        else:
            self.text.setText("")
        self.text.setPlaceholderText(
            self._present.label() if self._present else translate("ui", "The font the desktop uses")
        )
        self.text.setForegroundRole(QPalette.ColorRole.PlaceholderText if left else QPalette.ColorRole.Text)
