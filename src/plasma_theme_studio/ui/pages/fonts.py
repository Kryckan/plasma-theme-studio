# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Fonts page: the six fonts of the desktop, each left as it is or set here."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QFontDialog, QPushButton, QVBoxLayout, QWidget

from ...model.parts import FontSpec
from ...model.theme import FIELD_BY_ID
from ..labels import FIELD_LABELS
from ..widgets import InlineNote
from .apps_fonts import FontRow, default_spec, qfont_of, spec_of
from .base import TUNING_WIDTH, Page

translate = QCoreApplication.translate

ROWS_WIDTH = TUNING_WIDTH + 120  # the rows and the note under them
KEYS = ("general", "fixed", "small", "toolbar", "menu", "window_title")
PROPORTIONAL = ("general", "small", "toolbar", "menu", "window_title")  # every role but the fixed width one


def role_titles() -> dict[str, str]:
    return {
        "general": translate("ui", "General"),
        "fixed": translate("ui", "Fixed width"),
        "small": translate("ui", "Small"),
        "toolbar": translate("ui", "Toolbar"),
        "menu": translate("ui", "Menu"),
        "window_title": translate("ui", "Window title"),
    }


class FontsPage(Page):
    key = "fonts"
    parts = ("fonts",)

    @property
    def set_hint(self):
        return translate("ui", "Writes the fonts you choose here to the desktop.")

    def subtitle(self) -> str:
        return translate("ui", "A font that is not set here stays as it is on the desktop.")

    def build(self) -> None:
        self.header.add_part_switch()
        self.header.set_hint(self.set_hint)
        self.header.part_mode_changed.connect(self._switched)
        self.one_family = QPushButton(translate("ui", "Use one family for all"))
        self.one_family.setToolTip(
            translate(
                "ui",
                "Gives every font except the fixed width one the family of the general font and "
                "keeps their sizes.",
            )
        )
        self.one_family.clicked.connect(self.use_one_family)
        self.header.add_action(self.one_family)

        self.present: dict[str, FontSpec | None] = {key: None for key in KEYS}
        self.remembered: dict[str, str] = {}  # what the fonts were before the switch turned them off
        self.font_dialog: QFontDialog | None = None
        self.rows: dict[str, FontRow] = {}
        titles = role_titles()
        box = QWidget()
        box.setMaximumWidth(ROWS_WIDTH)
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        for index, key in enumerate(KEYS):
            field = FIELD_BY_ID[("fonts", key)]
            row = FontRow(key, titles[key], str(FIELD_LABELS[field.id]))
            row.set_value(self.theme.get("fonts", key))
            row.choose.clicked.connect(lambda _checked=False, k=key: self.choose(k))
            row.leave_clicked.connect(lambda on, k=key: self._leave(k, on))
            self.window.editors[field.id] = row
            self.rows[key] = row
            if index:
                column.addWidget(self.separator())
            column.addWidget(row)
        self.content.addWidget(box)
        note = InlineNote(
            translate(
                "ui",
                "Choosing Apply writes the fonts you set here into the desktop's font settings. "
                "A font left as it is stays what the desktop has now, and “Undo last apply” puts "
                "the old fonts back. Applications that are already open may need a restart to "
                "show a new font.",
            ),
            "information",
        )
        note.setMaximumWidth(ROWS_WIDTH)
        self.content.addWidget(note)

    # ---- what the desktop has

    def read_desktop(self) -> None:
        """Show the fonts the desktop has now in the rows that are left as they are."""
        from ... import desktopparts
        from ...generators.installed import FONT_ROLES

        try:
            current = desktopparts.PARTS["fonts"].current(self.window.runner) or {}
        except Exception:  # noqa: BLE001 - without them the rows show no font of the desktop
            current = {}
        for key in KEYS:
            spec = FontSpec.parse(current.get(FONT_ROLES[key], ""))
            self.present[key] = spec
            row = self.window.editors.get(("fonts", key))
            if row is not None and hasattr(row, "set_present"):
                row.set_present(spec)

    def effective(self, key: str) -> FontSpec:
        """The font of a role as it is now: the theme's, else the desktop's, else Qt's own."""
        value = self.theme.get("fonts", key)
        return (FontSpec.from_short(value) if value else None) or self.present.get(key) or default_spec(key)

    # ---- what the person does

    def refresh(self) -> None:
        for key, row in self.rows.items():
            row.set_value(self.theme.get("fonts", key))
        self.header.set_part_mode(any(self.theme.get("fonts", key) for key in KEYS))
        super().refresh()

    def _edit(self, key: str, value: str | None) -> None:
        self.window.edit(FIELD_BY_ID[("fonts", key)], value)
        self.refresh()

    def _leave(self, key: str, leave: bool) -> None:
        """The check box of a row: leave it as it is, or start from the font the desktop has."""
        self._edit(key, None if leave else self.effective(key).short())

    def _switched(self, on: bool) -> None:
        if on:
            if self.remembered:  # the fonts there were before the switch was turned off
                values = {("fonts", key): self.remembered.get(key) for key in KEYS}
            else:  # start from what the desktop has, so nothing changes until a font is chosen
                values = {("fonts", key): self.effective(key).short() for key in KEYS}
            self.window.edit_many(translate("ui", "Set the fonts"), values)
        else:
            now = {key: self.theme.get("fonts", key) for key in KEYS}
            if any(now.values()):
                self.remembered = {key: value for key, value in now.items() if value}
            self.window.edit_many(
                translate("ui", "Leave the fonts as they are"), {("fonts", key): None for key in KEYS}
            )
        self.refresh()

    def use_one_family(self) -> None:
        """The general font's family on every proportional role, each keeping its size."""
        family = self.effective("general").family
        values = {}
        for key in PROPORTIONAL:
            spec = self.effective(key)
            values[("fonts", key)] = FontSpec(family, spec.size, spec.weight, spec.italic).short()
        self.window.edit_many(translate("ui", "Use one family for all fonts"), values)
        self.refresh()

    def choose(self, key: str) -> None:
        """Open the font dialog for a role; the font is taken when the dialog is accepted."""
        title = str(FIELD_LABELS[("fonts", key)])
        dialog = QFontDialog(qfont_of(self.effective(key)), self)
        dialog.setOption(QFontDialog.FontDialogOption.DontUseNativeDialog, True)  # the same everywhere
        if key == "fixed":
            dialog.setOption(QFontDialog.FontDialogOption.MonospacedFonts, True)
        dialog.setWindowTitle(title)
        dialog.accepted.connect(lambda: self._chosen(key, dialog))
        self.font_dialog = dialog
        dialog.open()

    def _chosen(self, key: str, dialog: QFontDialog) -> None:
        self._edit(key, spec_of(dialog.selectedFont()).short())
