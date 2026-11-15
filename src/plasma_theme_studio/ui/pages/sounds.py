# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The System Sounds page: the sound themes as a list of rows, each with a Play button.

Play starts a player of the system (`pw-play`, `paplay` or `canberra-gtk-play`, whichever is there)
through the window's runner with the theme's sample sound. It changes nothing in the theme.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QTimer

from ... import pickers
from .base import PickerPage
from .pickers_common import LoadsInBackground, SoundList, find_player, player_command, speaker_badge

translate = QCoreApplication.translate

BADGE_SIDE = 40


class SoundsPage(LoadsInBackground, PickerPage):
    key = "sounds"
    parts = ("sounds",)
    kind_key = "sounds"
    id_field = ("desktop", "sounds")
    part_key = "sounds"

    @property
    def set_hint(self):
        return translate("ui", "Switches the sound theme.")

    def subtitle(self) -> str:
        return translate("ui", "The sounds of notifications and events.")

    def build(self) -> None:
        # The same as PickerPage.build with a list of rows where the grid of cards is.
        self.kind = pickers.kind(self.kind_key)
        self.items = {}
        self.colors_seen = None
        self.remembered = None
        self.player: str | None = None
        self.header.add_part_switch()
        self.header.set_hint(self.set_hint)
        self.header.part_mode_changed.connect(self._switched)
        self.grid = SoundList(self.title_text(), speaker_badge(BADGE_SIDE, self.devicePixelRatioF()))
        self.grid.selected.connect(self._picked)
        self.grid.play_requested.connect(self.play)
        self.layout().insertWidget(1, self.grid.bar)
        self.content.addWidget(self.grid)
        self.below = self.content
        self.this_timer = QTimer(self, singleShot=True, interval=0)  # no generated card here
        self.load_items()

    def show_items(self, found) -> None:
        self.items = {item.id: item for item in found}
        self.grid.set_items([(item.id, item.name, item.description) for item in found])
        self.grid.set_empty_text(
            translate("ui", "Nothing matches your search.")
            if found
            else translate("ui", "Nothing of this kind is installed.")
        )
        self.find_player()

    def find_player(self) -> None:
        """Look for a player now; with none, the Play buttons are off and say why."""
        self.player = find_player(self.window.runner)
        tip = translate("ui", "No sound player was found. Install PipeWire or PulseAudio to play the sounds.")
        self.grid.set_playable(
            self.player is not None, tip, {i for i, item in self.items.items() if item.extra.get("sample")}
        )

    def update_this_theme_cards(self) -> None:
        """No generated card on this page."""

    def play(self, item_id) -> None:
        """Play the sample sound of a theme. Nothing in the theme changes."""
        from ..banner import WARNING

        item = self.items.get(item_id)
        sample = item.extra.get("sample") if item else None
        if sample is None or self.player is None:
            return
        try:
            self.window.runner.launch(player_command(self.player, sample))
        except OSError as error:
            self.window.banner.show_message(
                WARNING, translate("ui", "The sound could not be played. {detail}").format(detail=error), 8
            )
