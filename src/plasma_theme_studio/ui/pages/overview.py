# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Overview page: the desktop next to the theme in the editor, and part by part what an apply does."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QCoreApplication, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ... import library
from ...apply import snapshot as snapshots
from ...apply.status import BLOCKED, CHANGE, LEAVE, SAME, state_word
from ...model.theme import Theme
from .. import pages as registry
from ..preview import PreviewWidget
from ..widgets import LARGE_SPACING, SPACING, mix, themed_icon, with_alpha
from .base import Page

translate = QCoreApplication.translate

PICTURE = QSize(304, 190)  # the drawn desktop of each card
NAME_WIDTH = 200  # the column of part names
ICON_SIZE = 24
RECENT = 3  # how many applies are listed
STATES = (CHANGE, SAME, LEAVE, BLOCKED)


def page_of(part_key: str) -> str:
    """The page of the window that edits the part `part_key` of `apply.status`."""
    return next((page for page, parts in registry.PARTS.items() if part_key in parts), "overview")


def when_text(created: datetime, now: datetime | None = None) -> str:
    """ "Today, 14:32", "Yesterday, 09:05", or the date."""
    now = now or datetime.now()
    clock = f"{created:%H:%M}"
    if created.date() == now.date():
        return translate("ui", "Today, {time}").format(time=clock)
    if created.date() == (now - timedelta(days=1)).date():
        return translate("ui", "Yesterday, {time}").format(time=clock)
    return f"{created:%Y-%m-%d}, {clock}"


class Picture(QWidget):
    """The drawn desktop in the colors of a theme, or a quiet frame that says there is none."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme: Theme | None = None
        self._preview = PreviewWidget(Theme())
        self._cache: tuple[QSize, float, QPixmap] | None = None
        self.setFixedSize(PICTURE)

    def set_theme(self, theme: Theme | None) -> None:
        """Show `theme` (None for no picture). The theme may have changed since the last call."""
        self.theme, self._cache = theme, None
        if theme is not None:
            self._preview.set_theme(theme)
        self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        ratio = self.devicePixelRatioF()
        if self.theme is not None:
            if self._cache is None or self._cache[:2] != (self.size(), ratio):
                self._cache = (self.size(), ratio, self._preview.render_image(self.size(), ratio))
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(frame, 6, 6)
            p.setClipPath(clip)
            p.drawPixmap(0, 0, self._cache[2])
            p.restore()
        else:
            p.setBrush(self.palette().alternateBase())
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(frame, 6, 6)
            p.setPen(self.palette().placeholderText().color())
            p.drawText(frame, Qt.AlignmentFlag.AlignCenter, translate("ui", "No picture of this"))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(self.palette().windowText().color(), 0.25), 1))
        p.drawRoundedRect(frame, 6, 6)
        p.end()


class Chip(QLabel):
    """The state of a part as a small pill: accent, muted, dimmed or warning."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = SAME
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_state(self, state: str) -> None:
        self.state = state
        self.setText(state_word(state))
        self.update()

    def width_for(self) -> int:
        metrics = self.fontMetrics()
        return max(metrics.horizontalAdvance(state_word(state)) for state in STATES) + 24

    def colors(self) -> tuple[QColor, QColor | None]:
        """The text color and the fill (None for no fill) of the state."""
        palette = self.palette()
        text, base = palette.windowText().color(), palette.window().color()
        if self.state == CHANGE:
            accent = palette.highlight().color()
            return mix(accent, text, 0.25), with_alpha(accent, 0.18)
        if self.state == BLOCKED:
            warning = QColor("#f67400")
            return mix(warning, text, 0.3), with_alpha(warning, 0.2)
        if self.state == LEAVE:
            return mix(text, base, 0.3), None
        return mix(text, base, 0.25), with_alpha(text, 0.08)

    def paintEvent(self, _) -> None:
        text, fill = self.colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if fill is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        else:
            p.setPen(QPen(with_alpha(text, 0.3), 1))
            p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.setPen(text)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()

    def sizeHint(self) -> QSize:
        return QSize(self.width_for(), self.fontMetrics().height() + 8)


class PartRow(QAbstractButton):
    """One part: its icon, its name, what the desktop has and what the theme sets, and the state.
    A click, Return or Space opens the page of the part."""

    def __init__(self, part, parent=None):
        super().__init__(parent)
        self.key = part.key
        self.page_key = page_of(part.key)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        spec = registry.SPECS.get(self.page_key)
        if spec is not None:
            icon = themed_icon(spec.icon, spec.fallback)
            self.icon_label.setPixmap(icon.pixmap(ICON_SIZE, ICON_SIZE))
        self.name = QLabel()
        self.name.setFixedWidth(NAME_WIDTH)
        self.values = QLabel()
        self.chip = Chip()
        for label in (self.name, self.values):
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
        for widget in (self.icon_label, self.name, self.values):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.chip.setFixedWidth(self.chip.width_for())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(LARGE_SPACING)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.name, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.values, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignVCenter)
        self.set_status(part)

    def set_status(self, part) -> None:
        self.state = part.state
        self.title = str(part.title)
        if part.state == LEAVE:
            values = str(part.desktop)
        elif part.state == SAME:
            values = str(part.theme)
        else:
            values = translate("ui", "{desktop} → {theme}").format(desktop=part.desktop, theme=part.theme)
        self.name.setText(self.title)
        self.values.setText(values)
        self.values.setForegroundRole(QPalette.ColorRole.WindowText)
        self.chip.set_state(part.state)
        tip = ""
        if part.state == BLOCKED:
            tip = translate("ui", "{part} cannot be applied: {problem}").format(
                part=self.title, problem=part.theme
            )
        for widget in (self, self.chip):
            widget.setToolTip(tip)
        self.setAccessibleName(self.title)
        self.setAccessibleDescription(f"{values}. {state_word(part.state)}")
        self.setText(self.title)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
        else:
            super().keyPressEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(400, self.layout().sizeHint().height())

    def hasHeightForWidth(self) -> bool:
        return self.layout().hasHeightForWidth()

    def heightForWidth(self, width: int) -> int:
        return self.layout().heightForWidth(width)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        rect = QRectF(self.rect())
        if self.underMouse() or self.hasFocus():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(palette.highlight().color(), 0.12))
            p.drawRoundedRect(rect.adjusted(0, 1, 0, -1), 5, 5)
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(palette.highlight().color(), 1.5))
            p.drawRoundedRect(rect.adjusted(1, 2, -1, -2), 5, 5)
        p.setPen(QPen(with_alpha(palette.windowText().color(), 0.12), 1))
        p.drawLine(rect.bottomLeft(), rect.bottomRight())
        p.end()


class PartList(QWidget):
    """The parts, one row each, or one plain sentence when there is nothing to list."""

    opened = Signal(str)  # the page of a part was asked for

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[PartRow] = []
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.message.setContentsMargins(8, 8, 8, 8)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(0)
        self.box.addWidget(self.message)
        self.setAccessibleName(translate("ui", "Parts of the desktop"))

    def rowCount(self) -> int:
        return len(self.rows)

    def set_message(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))

    def set_statuses(self, statuses, empty: str) -> None:
        """Show `statuses`; a row is kept while its part stays, so that the focus is not lost."""
        unreadable = str(translate("core", "Could not be read"))
        if not statuses or all(part.desktop == unreadable for part in statuses):
            statuses = []
        self.set_message("" if statuses else empty)
        if [row.key for row in self.rows] != [part.key for part in statuses]:
            for row in self.rows:
                row.hide()
                row.setParent(None)
                row.deleteLater()
            self.rows = [PartRow(part) for part in statuses]
            for row in self.rows:
                row.clicked.connect(lambda _=False, page=row.page_key: self.opened.emit(page))
                self.box.addWidget(row)
        for row, part in zip(self.rows, statuses, strict=True):
            row.set_status(part)


class OverviewPage(Page):
    key = "overview"

    def subtitle(self) -> str:
        return translate("ui", "What this theme does to the desktop when you apply it.")

    def build(self) -> None:
        self.desktop_theme: Theme | None = None
        self.desktop_name = ""
        self.recent: list = []
        self.content.addWidget(self.form_widget(("meta", "name"), ("meta", "author")))
        self.content.addLayout(self._build_cards())
        self.table = PartList()
        self.table.opened.connect(self.window.show_page)
        self.content.addWidget(self.caption(translate("ui", "Parts")))
        self.content.addWidget(self.table)
        self._build_recent()
        self.files_button = QPushButton(translate("ui", "Show the files this theme writes…"))
        self.files_button.setFlat(True)
        self.files_button.setCursor(Qt.CursorShape.PointingHandCursor)
        palette = self.files_button.palette()
        palette.setColor(QPalette.ColorRole.ButtonText, palette.link().color())
        self.files_button.setPalette(palette)
        font = self.files_button.font()
        font.setUnderline(True)
        self.files_button.setFont(font)
        self.files_button.clicked.connect(self.window.show_files)
        self.content.addWidget(self.files_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.table.set_message(translate("ui", "Reading what the desktop uses…"))

    def _card(self, caption: str) -> tuple[QVBoxLayout, Picture, QLabel]:
        box = QVBoxLayout()
        box.setSpacing(SPACING)
        title = self.caption(caption)
        picture = Picture()
        line = QLabel()
        line.setTextFormat(Qt.TextFormat.PlainText)
        line.setWordWrap(True)
        line.setMaximumWidth(PICTURE.width())
        for widget in (title, picture, line):
            box.addWidget(widget)
        box.addStretch(1)
        return box, picture, line

    def _build_cards(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(LARGE_SPACING * 2)
        desktop, self.desktop_picture, self.desktop_line = self._card(translate("ui", "On the desktop now"))
        editor, self.editor_picture, self.editor_line = self._card(translate("ui", "In the editor"))
        arrow = QLabel("→")
        arrow.setAccessibleName("")
        font = arrow.font()
        font.setPointSizeF(font.pointSizeF() * 2 if font.pointSizeF() > 0 else 24)
        font.setWeight(QFont.Weight.Light)
        arrow.setFont(font)
        arrow.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        row.addLayout(desktop)
        row.addWidget(arrow, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addLayout(editor)
        row.addStretch(1)
        return row

    def _build_recent(self) -> None:
        head = QHBoxLayout()
        head.addWidget(self.caption(translate("ui", "Recent")))
        head.addStretch(1)
        self.snapshots_button = QPushButton(themed_icon("view-history"), translate("ui", "Snapshots…"))
        self.snapshots_button.clicked.connect(self.window.show_snapshots)
        head.addWidget(self.snapshots_button)
        self.recent_grid = QGridLayout()
        self.recent_grid.setHorizontalSpacing(LARGE_SPACING)
        self.recent_grid.setVerticalSpacing(SPACING)
        self.recent_grid.setColumnStretch(1, 1)
        self.recent_labels: list[tuple[QLabel, QLabel]] = []
        self.recent_empty = QLabel(translate("ui", "Nothing has been applied yet."))
        self.recent_empty.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.recent_grid.addWidget(self.recent_empty, 0, 0, 1, 2)
        self.content.addLayout(head)
        self.content.addLayout(self.recent_grid)

    # ---- what the desktop uses now

    def read_desktop_state(self):
        """In a worker: the color scheme of the desktop and the last applies. Read when the page is first
        shown and after an apply or an undo, not at every edit."""
        name = self.window.read_scheme()
        scheme = next(
            (
                s
                for s in library.installed_schemes()
                if name and name.casefold() in (s.id.casefold(), s.name.casefold())
            ),
            None,
        )
        if scheme is not None:
            theme = library.theme_from_scheme(scheme)
            theme.set("meta", "name", scheme.name)  # the picture and the caption say one name
            found = (theme, scheme.name)
        else:
            preset = {"breezelight": "breeze-light", "breezedark": "breeze-dark"}.get(name.casefold())
            found = (Theme.from_preset(preset) if preset else None, name)
        return (name, *found, snapshots.list_snapshots()[:RECENT])

    def show_desktop_state(self, state) -> None:
        if state is None:
            self.desktop_theme, self.desktop_name, self.recent = None, "", []
        else:
            name, self.desktop_theme, self.desktop_name, self.recent = state
            self.window._active = name
        self._show_desktop()

    def _show_desktop(self) -> None:
        self.desktop_picture.set_theme(self.desktop_theme)
        self.desktop_line.setText(self.desktop_name or translate("ui", "The color scheme could not be read"))
        for first, second in self.recent_labels:
            first.deleteLater()
            second.deleteLater()
        self.recent_labels = []
        self.recent_empty.setVisible(not self.recent)
        for number, item in enumerate(self.recent):
            when = QLabel(when_text(item.created_at))
            when.setForegroundRole(QPalette.ColorRole.PlaceholderText)
            what = QLabel(translate("ui", "Applied {name}").format(name=item.theme_name))
            what.setTextFormat(Qt.TextFormat.PlainText)
            what.setWordWrap(True)
            self.recent_grid.addWidget(when, number, 0)
            self.recent_grid.addWidget(what, number, 1)
            self.recent_labels.append((when, what))

    # ---- the theme in the editor

    def refresh(self) -> None:
        self.editor_picture.set_theme(self.window.theme)
        self.editor_line.setText(self.window.theme.name)
        self.fill(self.window.statuses)  # the statuses may have been read before the page was built
        super().refresh()

    def fill(self, statuses) -> None:
        """Show the parts as `apply.status.parts_status` gives them."""
        if not self.built:
            return
        pending = self.window.status_pending or self.window.status_timer.isActive()
        self.table.set_statuses(
            statuses,
            translate("ui", "Reading what the desktop uses…")
            if pending or not self.window.statuses
            else translate("ui", "What the desktop uses now could not be read."),
        )
