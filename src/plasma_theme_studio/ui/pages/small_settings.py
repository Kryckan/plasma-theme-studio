# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The two small settings dialogs of System Settings, built in the app: "Configure Icons and Toolbars" (the
Application Style page) and "Configure Launch Feedback" (the Pointers page).

Each dialog has the choice "Leave as it is" or "Set by this theme" and the controls of System Settings. The
controls start on what the theme says or else what the desktop has now, and always work: the first change
turns the choice to "Set by this theme". Accepting stores every value of the dialog as one undo step.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from ...model.theme import FEEDBACK_CURSORS, FIELD_BY_ID, TOOLBAR_STYLES
from .. import labels, labels_small  # noqa: F401 - the labels of the fields of these dialogs
from ..widgets import LARGE_SPACING, SPACING

translate = QCoreApplication.translate


def _label(section: str, key: str) -> str:
    return str(labels.FIELD_LABELS[(section, key)])


class SmallSettingsDialog(QDialog):
    """The shared frame: the choice, a form of controls, OK and Cancel. A subclass names its fields."""

    section = ""
    title = ""
    intro = ""
    undo_text = ""

    def __init__(self, theme, desktop: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.title)
        self.theme, self.desktop = theme, desktop
        self._loading = False
        self.controls: dict[str, object] = {}
        intro = QLabel(self.intro)
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
        self.form = QFormLayout()
        self.form.setVerticalSpacing(SPACING)
        self.build()
        self.box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.box.accepted.connect(self.accept)
        self.box.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(LARGE_SPACING)
        layout.addWidget(intro)
        layout.addLayout(choice)
        layout.addLayout(self.form)
        layout.addStretch(1)
        layout.addWidget(self.box)
        self.own.setChecked(self.is_set())
        self.leave.setChecked(not self.is_set())
        self.leave.toggled.connect(self._leave_toggled)
        self.load(self.start_values())
        self.setMinimumWidth(460)

    # ---- what a subclass gives

    def build(self) -> None:
        raise NotImplementedError

    def fields(self) -> tuple[str, ...]:
        return tuple(self.controls)

    def desktop_values(self) -> dict:
        """What the desktop has now, per key of the section (absent keys are not in it)."""
        return {}

    def is_set(self) -> bool:
        return any(self.theme.get(self.section, key) is not None for key in self.fields())

    def start_values(self) -> dict:
        """The theme's values, else the desktop's, per key."""
        shown = dict(self.desktop_values())
        for key in self.fields():
            value = self.theme.get(self.section, key)
            if value is not None:
                shown[key] = value
        return shown

    # ---- the controls

    def add_control(self, key: str, widget) -> None:
        self.controls[key] = widget
        self.form.addRow(QLabel(_label(self.section, key) + translate("ui", ":")), widget)
        signal = widget.toggled if isinstance(widget, QCheckBox) else None
        if signal is None:
            signal = widget.currentIndexChanged if isinstance(widget, QComboBox) else widget.valueChanged
        signal.connect(self._edited)

    def choices(self, key: str, values: tuple) -> QComboBox:
        box = QComboBox()
        for value in values:
            box.addItem(str(labels.CHOICE_LABELS[(self.section, key)][value]), value)
        return box

    def seconds(self) -> QSpinBox:
        box = QSpinBox()
        box.setRange(1, 60)
        box.setSuffix(translate("ui", " s"))
        return box

    def load(self, values: dict) -> None:
        self._loading = True
        try:
            for key, widget in self.controls.items():
                if key not in values:
                    continue
                value = values[key]
                if isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QComboBox):
                    index = widget.findData(value)
                    widget.setCurrentIndex(max(index, 0))
                else:
                    widget.setValue(int(value))
        finally:
            self._loading = False

    def _edited(self, *_) -> None:
        if not self._loading and self.leave.isChecked():
            self.own.setChecked(True)

    def _leave_toggled(self, leave: bool) -> None:
        if leave:  # the controls show what the desktop has again
            self.load(self.desktop_values())

    def values(self) -> dict[str, object]:
        """The value of each key for the theme, None for every key while the choice is to leave it."""
        if self.leave.isChecked():
            return {key: None for key in self.controls}
        found = {}
        for key, widget in self.controls.items():
            if isinstance(widget, QCheckBox):
                found[key] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                found[key] = widget.currentData()
            else:
                found[key] = widget.value()
        return found

    def stored(self) -> dict:
        return {FIELD_BY_ID[(self.section, key)]: value for key, value in self.values().items()}


class ToolbarsDialog(SmallSettingsDialog):
    section = "toolbars"

    @property
    def title(self):  # type: ignore[override]
        return translate("ui", "Configure Icons and Toolbars")

    @property
    def intro(self):  # type: ignore[override]
        return translate("ui", "How applications label their toolbars, and where they show icons.")

    def build(self) -> None:
        self.add_control("main_style", self.choices("main_style", TOOLBAR_STYLES))
        self.add_control("other_style", self.choices("other_style", TOOLBAR_STYLES))
        self.add_control("icons_on_buttons", QCheckBox(translate("ui", "On buttons")))
        self.add_control("icons_in_menus", QCheckBox(translate("ui", "In menus")))

    def desktop_values(self) -> dict:
        return self.desktop


class LaunchFeedbackDialog(SmallSettingsDialog):
    section = "feedback"

    @property
    def title(self):  # type: ignore[override]
        return translate("ui", "Configure Launch Feedback")

    @property
    def intro(self):  # type: ignore[override]
        return translate("ui", "What shows that an application is starting.")

    def build(self) -> None:
        self.add_control("cursor", self.choices("cursor", FEEDBACK_CURSORS))
        self.add_control("cursor_timeout", self.seconds())
        self.add_control("taskbar", QCheckBox(translate("ui", "Show a button in the Task Manager")))
        self.add_control("taskbar_timeout", self.seconds())

    def desktop_values(self) -> dict:
        return self.desktop


# ---- opening them from a page


def _read(target, runner, names) -> dict:
    """What the desktop has for these keys, as the values of the theme's fields."""
    found = {}
    for name in names:
        try:
            found[name] = target.current(runner, name)
        except Exception:  # noqa: BLE001 - the dialog then starts from the usual values
            continue
    return found


def toolbars_on_desktop(runner) -> dict:
    from ...generators.extras import ToolbarsTarget

    target = ToolbarsTarget()
    read = _read(target, runner, target.keys)
    found = {}
    styles = {value.lower(): value for value in TOOLBAR_STYLES}
    for key in ("main_style", "other_style"):
        if read.get(key) in styles:
            found[key] = styles[read[key]]
    for key in ("icons_on_buttons", "icons_in_menus"):
        if key in read:
            found[key] = read[key] == "true"
    return found


def feedback_on_desktop(runner) -> dict:
    from ...generators.extras import LaunchFeedbackTarget

    target = LaunchFeedbackTarget()
    read = _read(target, runner, target.keys)
    found = {}
    if "busy_cursor" in read:
        if read["busy_cursor"] != "true":
            found["cursor"] = "none"
        elif read.get("blinking") == "true":
            found["cursor"] = "blinking"
        elif read.get("bouncing") == "true":
            found["cursor"] = "bouncing"
        else:
            found["cursor"] = "static"
    for key in ("cursor_timeout", "taskbar_timeout"):
        if read.get(key, "").isdigit():
            found[key] = min(max(int(read[key]), 1), 60)
    if "taskbar" in read:
        found["taskbar"] = read["taskbar"] == "true"
    return found


def _open(window, dialog_class, on_desktop, undo_text: str):
    try:
        desktop = on_desktop(window.runner)
    except Exception:  # noqa: BLE001
        desktop = {}
    dialog = dialog_class(window.theme, desktop, window)
    dialog.accepted.connect(lambda: window.edit_many(undo_text, dialog.stored()))
    window.small_dialog = dialog  # kept so that it is not collected while it is open
    dialog.open()
    return dialog


def open_toolbars(window):
    """Open "Configure Icons and Toolbars"; what it holds is stored in the theme when it is accepted."""
    return _open(window, ToolbarsDialog, toolbars_on_desktop, translate("ui", "Change icons and toolbars"))


def open_launch_feedback(window):
    """Open "Configure Launch Feedback"; what it holds is stored in the theme when it is accepted."""
    return _open(window, LaunchFeedbackDialog, feedback_on_desktop, translate("ui", "Change launch feedback"))
