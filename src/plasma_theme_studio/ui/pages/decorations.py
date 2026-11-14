# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Window Decorations page: the frame of windows, the border size and the title bar buttons."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...model.theme import FIELD_BY_ID
from .base import BREEZE_ADJUSTED, THIS_THEME, TUNING_WIDTH, PickerPage
from .decorations_buttons import SIDES, TitlebarButtonsDialog
from .preview_box import RatioPreview

translate = QCoreApplication.translate

FRAME_FIELDS = (("window", "radius"), ("window", "border_width"), ("shadow", "size"), ("shadow", "strength"))
BREEZE_RADIUS, BREEZE_BORDER = 5, 1  # what Breeze draws whatever the theme says


class DecorationsPage(PickerPage):
    key = "decorations"
    parts = ("decoration", "borders")
    note_sections = ("window", "shadow")
    kind_key = "decoration"
    id_field = ("window", "decoration_id")
    mode_field = ("window", "decoration")
    part_key = "decoration"
    breeze_card = True

    @property
    def set_hint(self):
        return translate("ui", "Writes a window decoration and switches to it.")

    def subtitle(self) -> str:
        return translate("ui", "The frame and title bar of windows.")

    def build(self) -> None:
        super().build()
        self.buttons_dialog: TitlebarButtonsDialog | None = None
        self.buttons_button = QPushButton(translate("ui", "Configure Titlebar Buttons…"))
        self.buttons_button.setToolTip(
            translate("ui", "Choose which buttons the title bar of windows has, and on which side.")
        )
        self.buttons_button.clicked.connect(self.configure_buttons)
        self.header.add_action(self.buttons_button)

        size = translate("ui", "Window border size")
        self.border_label = QLabel(size + translate("ui", ":"))
        self.border_size = self.editor("window", "border_size", size)
        self.add_top_row(self.border_label)
        self.add_top_row(self.border_size)
        self.top_row_layout.addStretch(1)

        # the values of the generated frame (or of Breeze) and a large window to see them in
        self.frame_box = QWidget()
        outer = QVBoxLayout(self.frame_box)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        outer.addWidget(self.separator())
        row = QHBoxLayout()
        row.setSpacing(24)
        left = QWidget()
        left.setMaximumWidth(TUNING_WIDTH - 120)
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)
        column.addWidget(self.caption(translate("ui", "Frame and shadow")))
        column.addLayout(self.form(*FRAME_FIELDS))
        self.frame_hint = QLabel()
        self.frame_hint.setWordWrap(True)
        self.frame_hint.setForegroundRole(self.frame_hint.palette().ColorRole.PlaceholderText)
        column.addWidget(self.frame_hint)
        column.addStretch(1)
        self.frame_preview = RatioPreview(self.theme, "window")
        self.frame_preview.setAccessibleName(translate("ui", "Preview of the window frame"))
        row.addWidget(left, 5)
        row.addWidget(self.frame_preview, 6, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(row)
        self.frame_box.hide()
        self.add_below(self.frame_box)

    # ---- showing the theme

    def refresh(self) -> None:
        super().refresh()
        on, chosen = self.selection()
        shown = on and chosen in (THIS_THEME, BREEZE_ADJUSTED)
        self.frame_box.setVisible(shown)
        breeze = chosen == BREEZE_ADJUSTED
        radius = self.window.editors.get(("window", "radius"))
        if radius is not None and shown:
            radius.setEnabled(not breeze)
            radius.setToolTip(translate("ui", "Breeze draws its own corners.") if breeze else "")
        self.frame_hint.setText(
            translate(
                "ui",
                "Breeze has fixed steps for the border and the shadow. The preview shows the step "
                "your values come to.",
            )
            if breeze
            else ""
        )
        self.frame_hint.setVisible(breeze)
        if shown:
            self.frame_preview.set_theme(self.frame_theme(breeze))
        self.border_size.setToolTip(self.border_tip(chosen if on else None))

    def frame_theme(self, breeze: bool):
        """The theme the large window is drawn from: for Breeze with the corners and steps Breeze has."""
        theme = self.theme
        if not breeze:
            return theme
        from ...generators.windowframe import breeze_shadow_step

        theme = theme.copy()
        theme.set("window", "radius", BREEZE_RADIUS)
        theme.set("window", "border_width", BREEZE_BORDER)
        theme.set("shadow", "size", max(breeze_shadow_step(int(theme.get("shadow", "size")))[1], 1))
        return theme

    def border_tip(self, chosen) -> str:
        if chosen == THIS_THEME:
            return translate(
                "ui",
                "The frame of this theme draws its own border, so this size has little effect on how it "
                "looks. Leave it as it is and the border width below is used.",
            )
        return translate("ui", "How thick the border around windows is, with any window decoration.")

    # ---- the title bar buttons

    def configure_buttons(self) -> None:
        """Open the dialog; what it holds is stored when it is accepted."""
        from ... import desktopparts

        try:
            desktop = desktopparts.PARTS["titlebar_buttons"].current(self.window.runner)
        except Exception:  # noqa: BLE001 - the dialog starts from the usual buttons then
            desktop = {}
        left, right = (self.theme.get("window", f"buttons_{side}") for side in SIDES)
        dialog = TitlebarButtonsDialog(left, right, desktop, self.window)
        dialog.accepted.connect(lambda: self.store_buttons(*dialog.values()))
        self.buttons_dialog = dialog
        dialog.open()

    def store_buttons(self, left: str | None, right: str | None) -> None:
        self.window.edit_many(
            translate("ui", "Change the title bar buttons"),
            {
                FIELD_BY_ID[("window", "buttons_left")]: left,
                FIELD_BY_ID[("window", "buttons_right")]: right,
            },
        )
