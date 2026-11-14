# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Themes page: saved themes and installed color schemes as cards.

Apply puts the selected card on the desktop; Return and a double click open it in the editor.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QVBoxLayout

from ..library_view import LibraryView
from .base import Page

translate = QCoreApplication.translate


class ThemesPage(Page):
    key = "themes"
    scrolling = False
    acts_on_selection = True

    def subtitle(self) -> str:
        return translate(
            "ui",
            "Your saved themes and the installed color schemes. Apply puts the selected one on the desktop.",
        )

    def build(self) -> None:
        self.library = LibraryView()
        self.library.selection_changed.connect(self.window.update_apply_button)
        self.library.edit_requested.connect(self.window.edit_entry)
        self.header.add_action(self.library.edit_button)
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.library)
        self.content.addLayout(box, 1)
        self.reload()

    def reload(self) -> None:
        self.library.reload(self.window.active_scheme())
