# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real widgets drawn by the generated Kvantum theme.

The sample is made of ordinary Qt widgets. Each of them gets the generated style
and its palette, so the sample shows what applications will look like while the
rest of the window keeps its own style and colors.
"""

from __future__ import annotations

import atexit
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenuBar,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QStackedLayout,
    QStyle,
    QStyleFactory,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..generators import kvantum
from ..model.theme import Theme

translate = QCoreApplication.translate

THEME_NAME = "PlasmaThemeStudioPreview"


def plugin_available() -> bool:
    """Whether Qt has the Kvantum style."""
    return any(key.lower() == kvantum.STYLE_NAME for key in QStyleFactory.keys())


def _make_style(theme: Theme, folder: Path) -> QStyle | None:
    """The Kvantum style for the theme's look, made from a theme in `folder`. Kvantum
    reads its theme from the configuration folder when the style is made, so
    XDG_CONFIG_HOME points there for that moment only."""
    colors, radius, border = kvantum.look_of(theme)
    kvconfig, svg = kvantum.make_theme(colors, radius, border)
    root = folder / "Kvantum"
    (root / THEME_NAME).mkdir(parents=True, exist_ok=True)
    (root / THEME_NAME / f"{THEME_NAME}.kvconfig").write_text(kvconfig, encoding="utf-8")
    (root / THEME_NAME / f"{THEME_NAME}.svg").write_text(svg, encoding="utf-8")
    (root / "kvantum.kvconfig").write_text(f"[General]\ntheme={THEME_NAME}\n", encoding="utf-8")
    saved = os.environ.get("XDG_CONFIG_HOME")
    os.environ["XDG_CONFIG_HOME"] = str(folder)
    try:
        return QStyleFactory.create(kvantum.STYLE_NAME)
    finally:
        if saved is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = saved


_LIVE: set[_Rendering] = set()


def _cleanup_all() -> None:
    """Remove the folders that are still there at exit: closeEvent is never sent to a tab."""
    for rendering in list(_LIVE):
        rendering.cleanup()


atexit.register(_cleanup_all)


class _Rendering:
    """A style and the temporary folder it was made from, kept as long as widgets use it."""

    def __init__(self, style: QStyle, folder: tempfile.TemporaryDirectory):
        self.style = style
        self.folder = folder
        _LIVE.add(self)

    def cleanup(self) -> None:
        _LIVE.discard(self)
        self.folder.cleanup()


class StylePreview(QWidget):
    """A compact sample of widgets in the style that the theme asks for."""

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._key = None
        self._rendering: _Rendering | None = None
        self._sample: QWidget | None = None
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._label)
        self.set_theme(theme)

    @property
    def shows_sample(self) -> bool:
        return self._stack.currentWidget() is self._sample and self._sample is not None

    @property
    def message(self) -> str:
        return self._label.text()

    def set_theme(self, theme: Theme) -> None:
        """Draw the sample again for `theme`. Nothing is done when the look is the same."""
        self.theme = theme
        generated = theme.get("apps", "style") == "generated"
        key = (generated, kvantum.look_of(theme)) if generated else (False,)
        if key == self._key:
            return
        self._key = key
        if not generated:
            self._show_message(
                translate(
                    "StylePreview",
                    "The application style is left as it is. Choose the style that is made from "
                    "this theme to see buttons, fields and menus drawn in it.",
                )
            )
        elif not plugin_available():
            self._show_message(
                translate(
                    "StylePreview",
                    "Kvantum is not installed, so the application style cannot be shown here.",
                )
            )
        else:
            self._draw()

    def _show_message(self, text: str) -> None:
        self._label.setText(text)
        self._stack.setCurrentWidget(self._label)
        self._release()

    def _draw(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="pts-style-preview-")
        try:
            style = _make_style(self.theme, Path(folder.name))
        except OSError:
            style = None
        if style is None:
            folder.cleanup()
            self._show_message(translate("StylePreview", "The application style could not be drawn here."))
            return
        old = self._rendering
        self._rendering = _Rendering(style, folder)
        if self._sample is None:
            self._sample = _build_sample()
            self._stack.addWidget(self._sample)
        palette = style.standardPalette()
        for widget in [self._sample, *self._sample.findChildren(QWidget)]:
            widget.setStyle(style)
            widget.setPalette(palette)
        self._sample.setAutoFillBackground(True)
        self._sample.setBackgroundRole(QPalette.ColorRole.Window)
        self._stack.setCurrentWidget(self._sample)
        if old is not None:
            old.cleanup()  # no widget uses the old style any longer

    def _release(self) -> None:
        """Stop using the style, so that its folder can go."""
        if self._rendering is None:
            return
        if self._sample is not None:
            for widget in [self._sample, *self._sample.findChildren(QWidget)]:
                widget.setStyle(None)
                widget.setPalette(QPalette())
        self._rendering.cleanup()
        self._rendering = None

    def closeEvent(self, event) -> None:
        self._release()
        super().closeEvent(event)


def _build_sample() -> QWidget:
    """The widgets of the sample. The texts are the usual ones of Qt widgets."""
    root = QWidget()
    outer = QVBoxLayout(root)
    outer.setContentsMargins(8, 4, 8, 8)
    bar = QMenuBar()
    file_menu = bar.addMenu(translate("StylePreview", "File"))
    file_menu.addAction(translate("StylePreview", "Open"))
    file_menu.addAction(translate("StylePreview", "Save"))
    edit_menu = bar.addMenu(translate("StylePreview", "Edit"))
    edit_menu.addAction(translate("StylePreview", "Copy"))
    edit_menu.addAction(translate("StylePreview", "Paste"))
    outer.addWidget(bar)

    tabs = QTabWidget()
    page = QWidget()
    form = QVBoxLayout(page)
    buttons = QHBoxLayout()
    plain = QPushButton(translate("StylePreview", "Button"))
    default = QPushButton(translate("StylePreview", "Default"))
    default.setDefault(True)
    checked = QPushButton(translate("StylePreview", "Checked"))
    checked.setCheckable(True)
    checked.setChecked(True)
    off = QPushButton(translate("StylePreview", "Disabled"))
    off.setEnabled(False)
    tool = QToolButton()
    tool.setText(translate("StylePreview", "Tool"))
    for button in (plain, default, checked, off, tool):
        buttons.addWidget(button)
    form.addLayout(buttons)

    fields = QHBoxLayout()
    edit = QLineEdit(translate("StylePreview", "Text field"))
    combo = QComboBox()
    combo.addItems([translate("StylePreview", "Combo box"), translate("StylePreview", "Other")])
    spin = QSpinBox()
    spin.setValue(7)
    fields.addWidget(edit, 2)
    fields.addWidget(combo, 2)
    fields.addWidget(spin, 1)
    form.addLayout(fields)

    choices = QHBoxLayout()
    on = QCheckBox(translate("StylePreview", "On"))
    on.setChecked(True)
    choices.addWidget(on)
    choices.addWidget(QCheckBox(translate("StylePreview", "Off")))
    chosen = QRadioButton(translate("StylePreview", "Chosen"))
    chosen.setChecked(True)
    choices.addWidget(chosen)
    choices.addWidget(QRadioButton(translate("StylePreview", "Other")))
    form.addLayout(choices)

    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setValue(40)
    form.addWidget(slider)
    progress = QProgressBar()
    progress.setValue(60)
    form.addWidget(progress)

    lower = QHBoxLayout()
    items = QListWidget()
    items.addItems([translate("StylePreview", "First item"), translate("StylePreview", "Selected item")])
    items.setCurrentRow(1)
    items.setFixedHeight(64)
    lower.addWidget(items, 2)
    tip = QGroupBox(translate("StylePreview", "Group"))
    tip.setMinimumHeight(68)
    inside = QVBoxLayout(tip)
    inside.addWidget(QLabel(translate("StylePreview", "A frame")))
    lower.addWidget(tip, 1)
    form.addLayout(lower)

    tabs.addTab(page, translate("StylePreview", "Controls"))
    tabs.addTab(QWidget(), translate("StylePreview", "More"))
    outer.addWidget(tabs)
    return root
