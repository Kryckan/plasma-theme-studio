# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Window Decorations page: the frame of windows, the border size and the title bar buttons."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...model.theme import FIELD_BY_ID
from ...pickers.base import Item
from .base import BREEZE_ADJUSTED, THIS_THEME, TUNING_WIDTH, PickerPage
from .decorations_buttons import SIDES, TitlebarButtonsDialog
from .decorations_preview import FramePreview
from .preview_box import RatioPreview

translate = QCoreApplication.translate

FRAME_FIELDS = (
    ("window", "radius"),
    ("window", "border_width"),
    ("window", "title_height"),
    ("window", "button_size"),
    ("window", "button_spacing"),
    ("shadow", "size"),
    ("shadow", "strength"),
    ("shadow", "offset_x"),
    ("shadow", "offset_y"),
)
# what an unset value of the frame is drawn with (the generated frame's own defaults)
FRAME_DEFAULTS = {
    ("window", "title_height"): 30,
    ("window", "button_size"): 22,
    ("window", "button_spacing"): 4,
    ("shadow", "offset_x"): 0,
    ("shadow", "offset_y"): 0,
}
KLASSY_ID = "klassy"
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
        for field_id, value in FRAME_DEFAULTS.items():
            editor = self.window.editors.get(field_id)
            if editor is not None and hasattr(editor, "set_inherited"):
                editor.set_inherited(value)
        self.frame_preview = RatioPreview(self.theme, "window")
        self.frame_preview.setAccessibleName(translate("ui", "Preview of the window frame"))
        self.own_preview = FramePreview(self.theme)
        self.own_preview.setAccessibleName(translate("ui", "Preview of the window frame"))
        previews = QVBoxLayout()
        previews.setContentsMargins(0, 0, 0, 0)
        previews.addWidget(self.frame_preview)
        previews.addWidget(self.own_preview)
        row.addWidget(left, 5)
        row.addLayout(previews, 6)
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
        self.frame_preview.setVisible(breeze)
        self.own_preview.setVisible(not breeze)
        if shown:
            self.frame_preview.set_theme(self.frame_theme(breeze))
            self.own_preview.set_theme(self.theme)
        # Breeze draws its own title bar, buttons and shadow, so those values belong to the generated frame
        for field_id in FRAME_DEFAULTS:
            editor = self.window.editors.get(field_id)
            if editor is not None and shown:
                editor.setEnabled(not breeze)
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

    # ---- Klassy

    def show_items(self, found) -> None:
        """The cards, with Klassy among them: switched off with the reason while it is not installed."""
        found = list(found)
        self.klassy_installed = any("klassy" in f"{i.id} {i.name}".casefold() for i in found)
        if not self.klassy_installed:
            found.append(Item(KLASSY_ID, "Klassy", translate("ui", "Not installed")))
        super().show_items(found)
        if not self.klassy_installed:
            self.grid.set_item_enabled(KLASSY_ID, False)
            card = self.grid.card(KLASSY_ID)
            if card is not None:
                card.setToolTip(
                    translate(
                        "ui", "Klassy is a separate window decoration that is not installed on this computer."
                    )
                )

    def _request(self, item_id) -> None:
        if item_id == KLASSY_ID and not getattr(self, "klassy_installed", True):
            return  # nothing to draw for something that is not there
        super()._request(item_id)

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
