# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Panel page: where each panel sits and how it behaves.

The switch "Leave as it is | Set by this theme" is the one decision. While the panels are left as they
are, the rows show what the desktop has now and cannot be changed. Once the theme sets them, every row
starts from the desktop's value and is simply editable; a single row can still be left alone, with the
small button at its end. The page lists the panels the desktop has (a panel more than the theme knows
of is left alone; a panel the theme has and this desktop has not is skipped when applying, and the page
says so). The theme keeps the main panel as `panel_layout` and the others as `panel_layout_2` and so on."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QCoreApplication, QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...model.theme import FIELD_BY_ID, MAX_PANELS, PANEL_FIELDS, panel_section
from ..editors import ChoiceEditor, NumberEditor
from ..labels import FIELD_LABELS
from ..widgets import LARGE_SPACING, SPACING, InlineNote, Segmented
from .base import CONTROLS_WIDTH, Page
from .panel_screen import ScreenChooser
from .preview_box import RatioPreview

translate = QCoreApplication.translate

SECTION = "panel_layout"
NAME_WIDTH = 124  # the labels are short here, so the choices get room for their words
SECTIONS = tuple(panel_section(number) for number in range(1, MAX_PANELS + 1))
FIELDS = tuple(field.key for field in PANEL_FIELDS)
# What a panel is like on a fresh Plasma, for a theme that has no other idea.
USUAL = {
    "location": "bottom",
    "height": 44,
    "alignment": "center",
    "length_mode": "fill",
    "floating": True,
    "visibility": "none",
    "opacity_mode": "adaptive",
}
# The names Plasma's scripting uses for the fields of the theme.
SCRIPT_NAMES = {
    "location": "location",
    "height": "height",
    "alignment": "alignment",
    "length_mode": "lengthMode",
    "floating": "floating",
    "visibility": "hiding",
    "opacity_mode": "opacity",
}


def layout_from(state: dict) -> dict:
    """The values of the theme that a panel state from Plasma gives; what is not a valid value is left out."""
    found = {}
    for key, name in SCRIPT_NAMES.items():
        value = state.get(name)
        if key == "visibility" and value == "normal":
            value = "none"
        field = FIELD_BY_ID[(SECTION, key)]
        if field.kind == "choice" and value in field.choices:
            found[key] = value
        elif field.kind == "bool" and isinstance(value, bool):
            found[key] = value
        elif field.kind == "int" and isinstance(value, int | float) and not isinstance(value, bool):
            found[key] = min(max(round(value), field.minimum), field.maximum)
    return found


class PanelRow(QWidget):
    """The control of one value of one panel: the editor, and while the value is set a small button
    that leaves it alone. A value that is left alone shows what the desktop has (`set_shown`) and
    says so quietly; choosing anything sets it. It is kept in `window.editors` like any other control."""

    changed = Signal(object)

    def __init__(self, field, parent=None):
        super().__init__(parent)
        self.field = field
        self._value = None
        self._shown = USUAL[field.key]
        if field.kind == "int":
            self.inner = NumberEditor(field)
        else:
            self.inner = ChoiceEditor(replace(field, optional=False))  # no "Leave as it is" in the list
        self.inner.changed.connect(self.changed)
        self.leave = QToolButton()
        self.leave.setAutoRaise(True)
        self.leave.setIcon(QIcon.fromTheme("edit-undo", QIcon.fromTheme("edit-clear")))
        self.leave.setText("×")  # shown only where the theme has no icon
        self.leave.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if not self.leave.icon().isNull()
            else Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.leave.setToolTip(translate("ui", "Leave this one as it is"))
        self.leave.clicked.connect(lambda: self.changed.emit(None))
        self.quiet = QLabel(translate("ui", "As it is now"))
        self.quiet.setForegroundRole(self.quiet.palette().ColorRole.PlaceholderText)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING)
        layout.addWidget(self.inner, 1)
        layout.addWidget(self.leave)
        layout.addWidget(self.quiet)
        self.setFocusProxy(self.inner)
        self.set_value(None)

    def set_title(self, title: str) -> None:
        self.inner.set_title(title)
        self.leave.setAccessibleName(
            translate("ui", "{setting}: leave this one as it is").format(setting=title)
        )

    def set_shown(self, value) -> None:
        """What the desktop has for this value, shown while the value is left alone."""
        self._shown = USUAL[self.field.key] if value is None else value
        if self._value is None:
            self.inner.set_value(self._shown)

    def set_value(self, value) -> None:
        self._value = value
        self.inner.set_value(self._shown if value is None else value)
        self.leave.setVisible(value is not None)
        self.quiet.setVisible(value is None and self._talks)

    _talks = False  # whether a value that is left alone says so (not while the whole panel is)

    def talk(self, talks: bool) -> None:
        """Whether a value that is left alone says so."""
        self._talks = talks
        self.quiet.setVisible(self._value is None and talks)

    def value(self):
        """What the theme has for this value; None while it is left alone."""
        return self._value

    def choose(self, value) -> None:
        """Pick a value the way the user does."""
        if isinstance(self.inner, ChoiceEditor):
            self.inner.choose(value)
        else:
            self.inner.set_value(value)
            self.changed.emit(value)


class _Answer(QObject):
    done = Signal(int, object)


class _ReadJob(QRunnable):
    """Asks Plasma which panels there are, off the GUI thread (the runner must be safe to use there)."""

    def __init__(self, generation: int, runner, answer: _Answer):
        super().__init__()
        self.generation, self.runner, self.answer = generation, runner, answer

    def run(self) -> None:
        from ...generators import panellayout

        found = None
        try:
            found = [
                {"id": state["id"], "screen": int(state.get("screen") or 0), "values": layout_from(state)}
                for state in panellayout.live_panels(self.runner)
            ]
        except Exception:  # noqa: BLE001 - no panel to read from: the usual values are used
            found = None
        try:
            self.answer.done.emit(self.generation, found)
        except RuntimeError:  # the page is gone
            pass


class PanelPage(Page):
    key = "panel"
    parts = ("panel",)
    note_sections = SECTIONS
    modes = ("desktop", "panel")

    def subtitle(self) -> str:
        return translate("ui", "Where the panels sit and how they behave.")

    def build(self) -> None:
        self.remembered: dict[int, dict] = {}  # per panel: the values from before "Leave as it is"
        self.desktop_panels: list[dict] | None = None  # what the desktop has, once it has been asked
        self.selected = 1
        self._numbers: list[int] = [1]
        self.forms: dict[int, QWidget] = {}
        self._generation = 0
        # The pool first: Qt deletes children in the order they were made, and the pool's end waits for
        # a job that is still running, which may emit on the answer object.
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._answer = _Answer(self)
        self._answer.done.connect(self._desktop_answered)

        self.header.add_part_switch()
        self.header.set_hint(translate("ui", "Moves and shapes the panels when you apply."))
        self.header.part_mode_changed.connect(self._switched)

        self.chooser = ScreenChooser()
        self.chooser.chosen.connect(self._edge_chosen)
        self.chooser.picked.connect(self._select)

        self.picker_box = QWidget()  # the panels, when there is more than one
        self.picker_layout = QVBoxLayout(self.picker_box)
        self.picker_layout.setContentsMargins(0, 0, 0, 0)
        self.picker_layout.setSpacing(SPACING)
        self.picker: Segmented | None = None
        self.panel_switch = QCheckBox(translate("ui", "Set this panel from the theme"))
        self.panel_switch.clicked.connect(self._panel_switched)
        self.missing = InlineNote("", "warning")
        self.missing.hide()
        self.stack = QStackedWidget()
        self.form_box = QWidget()  # what the switch turns on and off
        inner = QVBoxLayout(self.form_box)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(LARGE_SPACING)
        inner.addWidget(self.stack)

        self.left = QWidget()
        self.left.setMinimumWidth(340)
        self.left.setMaximumWidth(CONTROLS_WIDTH)
        column = QVBoxLayout(self.left)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(LARGE_SPACING)
        column.addWidget(self.picker_box)
        column.addWidget(self.missing)
        column.addWidget(self.panel_switch)
        column.addWidget(self.form_box)
        self.notes_layout = column

        self.preview = RatioPreview(self.theme, self.modes[0])
        self.mode_switch = Segmented(
            [translate("ui", "Desktop"), translate("ui", "Panel")],
            0,
            name=translate("ui", "What the preview shows"),
        )
        self.mode_switch.changed.connect(lambda index: self.preview.set_mode(self.modes[index]))
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setForegroundRole(self.hint.palette().ColorRole.PlaceholderText)
        bar = QHBoxLayout()
        bar.addWidget(self.caption(translate("ui", "Preview")))
        bar.addStretch(1)
        bar.addWidget(self.mode_switch)
        right = QVBoxLayout()
        right.setSpacing(SPACING)
        right.addWidget(self.caption(translate("ui", "Screens")))
        right.addWidget(self.chooser, 0, Qt.AlignmentFlag.AlignLeft)
        right.addSpacing(SPACING)
        right.addLayout(bar)
        right.addWidget(self.preview)
        right.addWidget(self.hint)
        right.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(LARGE_SPACING + 8)
        row.addWidget(self.left, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(right, 1)
        self.content.addLayout(row)
        self.content.addStretch(1)
        self._form_of(1)

    # ---- the form of one panel

    def _form_of(self, number: int) -> QWidget:
        """The form of panel `number`, made when it is first needed: its rows are controls of the
        window like any other, so undo and loading a theme reach them."""
        if number in self.forms:
            return self.forms[number]
        section = panel_section(number)
        box = QWidget()
        form = QFormLayout(box)
        form.setContentsMargins(0, 0, 0, 0)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setVerticalSpacing(SPACING)
        form.setHorizontalSpacing(SPACING)
        for key in FIELDS:
            field = FIELD_BY_ID[(section, key)]
            text = str(FIELD_LABELS[field.id])
            name = QLabel(text + translate("ui", ":"))
            name.setMinimumWidth(NAME_WIDTH)
            row = PanelRow(field)
            row.set_title(text)
            row.set_value(self.theme.get(section, key))
            row.changed.connect(lambda value, field=field: self.window.edit(field, value))
            self.window.editors[field.id] = row
            form.addRow(name, row)
        self.forms[number] = box
        self.stack.addWidget(box)
        return box

    def _rows(self, number: int) -> list[PanelRow]:
        return [self.window.editors[(panel_section(number), key)] for key in FIELDS]

    # ---- showing the theme

    def is_set(self, number: int | None = None) -> bool:
        """Whether the theme sets anything on panel `number`, or on any panel."""
        numbers = range(1, MAX_PANELS + 1) if number is None else (number,)
        return any(self.theme.get(panel_section(n), key) is not None for n in numbers for key in FIELDS)

    @property
    def desktop_layout(self) -> dict | None:
        """What the desktop has for the main panel, once it has been asked (None when it has none)."""
        return self.desktop_panels[0]["values"] if self.desktop_panels else None

    @desktop_layout.setter
    def desktop_layout(self, values: dict | None) -> None:
        self.desktop_panels = [{"id": 0, "screen": 0, "values": values}] if values else None

    def desktop_has(self, number: int) -> bool:
        """Whether the desktop has panel `number` (when it could not be asked: only the main one)."""
        if self.desktop_panels is None:
            return number == 1
        return number <= len(self.desktop_panels)

    def desktop_values(self, number: int) -> dict:
        """What the desktop has for panel `number`; empty when that is not known."""
        if self.desktop_panels and number <= len(self.desktop_panels):
            return self.desktop_panels[number - 1]["values"]
        return {}

    def panel_numbers(self) -> list[int]:
        """The panels the page lists: those of the desktop, and those the theme sets values on."""
        found = {1}
        found.update(range(1, len(self.desktop_panels or ()) + 1))
        found.update(n for n in range(1, MAX_PANELS + 1) if self.is_set(n))
        return sorted(found)

    def effective(self, number: int) -> dict:
        """The panel as it would be: the desktop's value for every value the theme leaves alone."""
        section = panel_section(number)
        values = USUAL | self.desktop_values(number)
        for key in FIELDS:
            if self.theme.get(section, key) is not None:
                values[key] = self.theme.get(section, key)
        return values

    def _screen_of(self, number: int) -> int:
        if self.desktop_panels and number <= len(self.desktop_panels):
            return self.desktop_panels[number - 1]["screen"]
        return 0

    def refresh(self) -> None:
        on = self.is_set()
        self.header.set_part_mode(on)
        numbers = self.panel_numbers()
        if self.selected not in numbers:
            self.selected = 1
        self._fill_picker(numbers)
        number = self.selected
        panel_on = self.is_set(number)
        several = len(numbers) > 1
        for n in numbers:
            self._form_of(n)
            for key, row in zip(FIELDS, self._rows(n), strict=True):
                row.set_shown(self.desktop_values(n).get(key))
                row.talk(self.is_set(n))
        self.stack.setCurrentWidget(self._form_of(number))
        self.panel_switch.setVisible(several and on)
        self.panel_switch.setChecked(panel_on)
        self.form_box.setEnabled(panel_on)
        for key, row in zip(
            FIELDS, self._rows(number), strict=True
        ):  # the rows of a panel left alone show the desktop
            row.set_value(self.theme.get(panel_section(number), key))
        absent = not self.desktop_has(number)
        self.missing.setVisible(absent)
        if absent:
            self.missing.set_text(
                translate(
                    "ui",
                    "This desktop has no panel {number}. This part is skipped when you apply.",
                ).format(number=number)
            )
        # the screens, and the panels as they would be
        shown = [n for n in numbers if self.desktop_has(n) or self.desktop_panels is None and n == 1]
        self.chooser.set_panels(
            [
                {"number": n, "location": self.effective(n)["location"], "screen": self._screen_of(n)}
                for n in shown
            ],
            number,
        )
        self.preview.set_panels([self.effective(n) for n in shown])
        self.preview.set_theme(self.theme)
        if on:
            self.hint.setText(translate("ui", "Nothing reaches the desktop until you choose Apply."))
        elif self.desktop_panels:
            self.hint.setText(
                translate("ui", "The panels are left as they are. The preview shows this desktop's panels.")
            )
        else:
            self.hint.setText(
                translate("ui", "The panels are left as they are. The preview shows a usual panel.")
            )
        super().refresh()

    def refresh_notes(self) -> None:
        """The notes of the panel that is shown, not of the others."""
        super().refresh_notes()
        for number in range(1, MAX_PANELS + 1):
            note = self.window.notes.get(panel_section(number))
            if note is not None and number != self.selected:
                note.hide()

    def _fill_picker(self, numbers: list[int]) -> None:
        """The row of panels above the form, made again when the panels changed."""
        self.picker_box.setVisible(len(numbers) > 1)
        if numbers == self._numbers and self.picker is not None:
            self.picker.set_current(numbers.index(self.selected))
            return
        self._numbers = numbers
        if self.picker is not None:
            self.picker_layout.removeWidget(self.picker)
            self.picker.deleteLater()
        self.picker = Segmented(
            [translate("ui", "Panel {number}").format(number=n) for n in numbers],
            numbers.index(self.selected),
            name=translate("ui", "Panel"),
        )
        self.picker.changed.connect(lambda index: self._select(self._numbers[index]))
        self.picker_layout.addWidget(self.picker)
        self.picker.show()  # a widget added to a shown page stays hidden until it is told

    def _select(self, number: int) -> None:
        if number != self.selected:
            self.selected = number
            self.refresh()

    # ---- what the desktop has

    def read_desktop(self) -> None:
        self._generation += 1
        self._pool.start(_ReadJob(self._generation, self.window.runner, self._answer))

    def _desktop_answered(self, generation: int, panels) -> None:
        if generation == self._generation:
            self.desktop_panels = panels or None
            if self.built and not self.stale:
                self.refresh()

    def settle(self) -> None:
        """Wait until the answer about the desktop's panels has come (for tests)."""
        self._pool.waitForDone()
        QCoreApplication.processEvents()

    # ---- the switches

    def starting_values(self, number: int = 1) -> dict:
        """The seven values the switch gives panel `number` when it is turned on."""
        if number in self.remembered:
            return dict(self.remembered[number])
        return USUAL | self.desktop_values(number)

    def _set_panels(self, numbers: list[int], on: bool, text: str) -> None:
        values = {}
        for number in numbers:
            section = panel_section(number)
            if on:
                start = self.starting_values(number)
            else:
                now = {key: self.theme.get(section, key) for key in FIELDS}
                if any(value is not None for value in now.values()):
                    self.remembered[number] = now
                start = dict.fromkeys(FIELDS)
            values.update({(section, key): start[key] for key in FIELDS})
        self.window.edit_many(text, values)
        self.refresh()

    def _switched(self, on: bool) -> None:
        if on:
            numbers = [n for n in range(1, len(self.desktop_panels or ()) + 1)] or [1]
            self._set_panels(numbers, True, translate("ui", "Set the panels from this theme"))
        else:
            self._set_panels(
                [n for n in range(1, MAX_PANELS + 1)], False, translate("ui", "Leave the panels as they are")
            )

    def _panel_switched(self, on: bool) -> None:
        """The box of one panel (only when there is more than one)."""
        self._set_panels(
            [self.selected],
            on,
            translate("ui", "Set the panel from this theme")
            if on
            else translate("ui", "Leave the panel where it is"),
        )

    def _edge_chosen(self, edge: str) -> None:
        if self.is_set(self.selected):  # a panel that is left as it is is not moved by a click
            self.window.edit(FIELD_BY_ID[(panel_section(self.selected), "location")], edge)
