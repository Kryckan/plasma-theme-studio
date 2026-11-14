# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Fonts page: the six fonts of the desktop, each left as it is or set here."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFontDialog, QHBoxLayout, QPushButton, QWidget

from ...model.parts import FontSpec
from ...model.theme import FIELD_BY_ID
from ..labels import FIELD_LABELS
from .base import ValuePage

translate = QCoreApplication.translate

KEYS = ("general", "fixed", "small", "toolbar", "menu", "window_title")


class FontsPage(ValuePage):
    key = "fonts"
    parts = ("fonts",)
    modes = ("window", "menu", "desktop")

    def subtitle(self) -> str:
        return translate("ui", "A font that is not set here stays as it is on the desktop.")

    def build_controls(self) -> None:
        for key in KEYS:
            field = FIELD_BY_ID[("fonts", key)]
            title = str(FIELD_LABELS[field.id])
            editor = self.editor("fonts", key, title)
            choose = QPushButton(translate("ui", "Choose…"))
            choose.setAccessibleName(translate("ui", "Choose {font}").format(font=title))
            choose.clicked.connect(lambda _checked=False, f=field, t=title: self._choose(f, t))
            row = QHBoxLayout()
            row.addWidget(editor, 1)
            row.addWidget(choose)
            holder = QWidget()
            holder.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            self.controls.addWidget(self.caption(title))
            self.controls.addWidget(holder)

    def read_desktop(self) -> None:
        """Show the fonts the desktop has in the fields that are left as they are."""
        from ... import desktopparts
        from ...generators.installed import FONT_ROLES

        try:
            current = desktopparts.PARTS["fonts"].current(self.window.runner) or {}
        except Exception:  # noqa: BLE001 - without them the fields stay empty
            return
        for key in KEYS:
            editor = self.window.editors.get(("fonts", key))
            spec = FontSpec.parse(current.get(FONT_ROLES[key], ""))
            if editor is not None and hasattr(editor, "set_placeholder") and spec is not None:
                editor.set_placeholder(spec.label())

    def _choose(self, field, title: str) -> None:
        current = FontSpec.from_short(self.theme.get(*field.id) or "")
        start = QFont(current.family, round(current.size)) if current else self.font()
        ok, font = QFontDialog.getFont(start, self, title)
        if ok:
            spec = FontSpec(font.family(), font.pointSizeF(), font.weight().value, font.italic())
            self.window.edit(field, spec.short())
