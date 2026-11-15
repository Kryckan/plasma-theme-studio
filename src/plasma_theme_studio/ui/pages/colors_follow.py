# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The "Follow the palette" switch of the Colors page.

On, the colors of the desktop follow a pywal or matugen palette file, also while this window is
closed (see follow.py). Switching on takes one snapshot; Undo and switching off go back."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from ... import follow, palette
from ..banner import INFORMATION, POSITIVE, WARNING

translate = QCoreApplication.translate


class FollowRow(QWidget):
    """A check box with a plain note under it; the page asks it to `show_state` when it refreshes and
    tells it what the person chose in the import dialog with `remember`."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.choice: tuple[palette.PaletteFile, dict[str, str], str] | None = None  # source, mapping, variant
        self.box = QCheckBox(translate("ui", "Follow the palette"))
        self.box.setToolTip(
            translate(
                "ui",
                "Keep the desktop colors in step with the pywal or matugen palette, "
                "also when this window is closed.",
            )
        )
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setForegroundRole(self.note.palette().ColorRole.PlaceholderText)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.box)
        layout.addWidget(self.note)
        self.box.toggled.connect(self._toggled)

    def remember(self, path: str, dialog) -> None:
        """Keep the palette file just imported and the mapping chosen for it; when following, follow it."""
        text = follow.read_palette_text(Path(path))
        kind = follow.detect_kind(text) if text is not None else None
        if kind is None:
            return
        overrides = follow.overrides_from_choice(kind, text, dialog.mapped(), dialog.chosen())
        self.choice = (palette.PaletteFile(kind, Path(path)), overrides, dialog.variant)
        if follow.is_on():
            self._switch_on()

    def show_state(self) -> None:
        """Read the state from disk, so Undo and the command line show here too."""
        status = follow.status()
        offered = status.on or follow.offered(self.page.window.runner)
        self.box.blockSignals(True)
        self.box.setChecked(status.on)
        self.box.blockSignals(False)
        self.box.setEnabled(offered)
        if status.on and status.state is not None:
            self.note.setText(
                translate(
                    "ui",
                    "Following {path}. Colors only: shapes, fonts and panels stay. "
                    "If you apply another theme, the next change of the palette puts these colors back. "
                    "Untick to stop.",
                ).format(path=str(status.state.source_path))
            )
        elif offered:
            self.note.setText(
                translate(
                    "ui",
                    "When the palette file changes, the colors of this theme change with it, "
                    "also while this window is closed.",
                )
            )
        else:
            self.note.setText(
                translate(
                    "ui",
                    "This needs a pywal or matugen palette file, or one of the two programs installed. "
                    "Neither was found.",
                )
            )

    def _switch_on(self) -> bool:
        source, overrides, variant = self.choice or (None, None, None)
        try:
            theme, runner = self.page.theme, self.page.window.runner
            done = self.page.window._away(
                lambda _progress: follow.enable(theme, runner, source, variant, overrides),
                translate("ui", "Switching on follow mode…"),
            )
        except follow.FollowError as error:
            self.page.window.banner.show_message(WARNING, str(error.message), 12)
            return False
        self.page.window.banner.show_message(POSITIVE if done.applied else INFORMATION, str(done.message), 12)
        return True

    def _toggled(self, on: bool) -> None:
        if on:
            self._switch_on()
        else:
            runner = self.page.window.runner
            done = self.page.window._away(
                lambda _progress: follow.disable(runner), translate("ui", "Switching off follow mode…")
            )
            if done.failures:
                self.page.window.banner.show_message(WARNING, str(done.message), 12)
            else:
                self.page.window.banner.show_message(INFORMATION, str(done.message), 12)
        self.page.window.refresh()
