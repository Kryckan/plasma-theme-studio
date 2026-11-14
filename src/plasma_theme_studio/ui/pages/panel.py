# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Panel page: where the panel sits and how it behaves, as one form with one switch on top.

The switch "Leave as it is | Set by this theme" turns all seven values off (and remembers
them for the session) or on again: with what was there before, or else with what the desktop has now."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...model.theme import FIELD_BY_ID
from ..widgets import LARGE_SPACING, SPACING, Segmented
from .base import CONTROLS_WIDTH, Page
from .panel_screen import ScreenChooser
from .preview_box import RatioPreview

translate = QCoreApplication.translate

SECTION = "panel_layout"
FIELDS = ("location", "height", "alignment", "length_mode", "floating", "visibility", "opacity_mode")
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


class _Answer(QObject):
    done = Signal(int, object)


class _ReadJob(QRunnable):
    """Asks Plasma where the panel is, off the GUI thread (the runner must be safe to use there)."""

    def __init__(self, generation: int, runner, answer: _Answer):
        super().__init__()
        self.generation, self.runner, self.answer = generation, runner, answer

    def run(self) -> None:
        from ...generators import panellayout

        found = None
        try:
            state = panellayout._read(self.runner)
            if state.get("found"):
                try:
                    state, _known = panellayout._live_state(self.runner, state)
                except Exception:  # noqa: BLE001 - hiding and opacity stay as the getters said
                    pass
                found = layout_from(state)
        except Exception:  # noqa: BLE001 - no panel to read from: the usual values are used
            found = None
        try:
            self.answer.done.emit(self.generation, found)
        except RuntimeError:  # the page is gone
            pass


class PanelPage(Page):
    key = "panel"
    parts = ("panel",)
    note_sections = ("panel_layout",)
    modes = ("desktop", "panel")

    def subtitle(self) -> str:
        return translate("ui", "Where the main panel sits and how it behaves.")

    def build(self) -> None:
        self.remembered: dict | None = None  # the values from before "Leave the panel where it is"
        self.desktop_layout: dict | None = None  # what the desktop has, once it has been asked
        self._generation = 0
        self._answer = _Answer(self)
        self._answer.done.connect(self._desktop_answered)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

        self.header.add_part_switch()
        self.header.set_hint(translate("ui", "Moves and shapes the main panel when you apply."))
        self.header.part_mode_changed.connect(self._switched)

        self.chooser = ScreenChooser()
        self.chooser.chosen.connect(lambda edge: self.window.edit(FIELD_BY_ID[(SECTION, "location")], edge))
        self.form_box = QWidget()  # what the switch turns on and off
        inner = QVBoxLayout(self.form_box)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(LARGE_SPACING)
        inner.addWidget(self.chooser, 0, Qt.AlignmentFlag.AlignLeft)
        inner.addLayout(self.form(*((SECTION, key) for key in FIELDS)))
        self.left = QWidget()
        self.left.setMinimumWidth(340)
        self.left.setMaximumWidth(CONTROLS_WIDTH)
        column = QVBoxLayout(self.left)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(LARGE_SPACING)
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

    # ---- showing the theme

    def is_set(self) -> bool:
        return any(self.theme.get(SECTION, key) is not None for key in FIELDS)

    def refresh(self) -> None:
        on = self.is_set()
        self.header.set_part_mode(on)
        self.form_box.setEnabled(on)
        self.chooser.set_value(self.theme.get(SECTION, "location"))
        self.preview.set_theme(self.theme)
        self.hint.setText(
            translate("ui", "Nothing reaches the desktop until you choose Apply.")
            if on
            else translate("ui", "The panel is left as it is. The preview shows a usual panel.")
        )
        super().refresh()

    # ---- what the desktop has

    def read_desktop(self) -> None:
        self._generation += 1
        self._pool.start(_ReadJob(self._generation, self.window.runner, self._answer))

    def _desktop_answered(self, generation: int, layout) -> None:
        if generation == self._generation:
            self.desktop_layout = layout or None

    def settle(self) -> None:
        """Wait until the answer about the desktop's panel has come (for tests)."""
        self._pool.waitForDone()
        QCoreApplication.processEvents()

    # ---- the switch

    def starting_values(self) -> dict:
        """The seven values the switch gives when it is turned on."""
        if self.remembered is not None:
            return dict(self.remembered)
        return USUAL | (self.desktop_layout or {})

    def _switched(self, on: bool) -> None:
        if on:
            values = self.starting_values()
            text = translate("ui", "Set the panel from this theme")
        else:
            now = {key: self.theme.get(SECTION, key) for key in FIELDS}
            if any(value is not None for value in now.values()):
                self.remembered = now
            values = dict.fromkeys(FIELDS)
            text = translate("ui", "Leave the panel where it is")
        self.window.edit_many(text, {(SECTION, key): value for key, value in values.items()})
        self.refresh()
