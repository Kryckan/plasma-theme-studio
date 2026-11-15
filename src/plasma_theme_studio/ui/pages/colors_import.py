# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The dialog that every import of colors goes through: pywal, matugen, a color scheme file, a picture
or the wallpaper. It shows which color of the palette becomes which color of the theme, lets the person
choose another one for any of them, shows the result in a live preview and corrects text that would be
hard to read. Nothing is changed in the theme until "Use These Colors"."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ... import palette
from ...model.theme import Theme
from ..labels import FIELD_LABELS
from ..preview import PreviewWidget
from ..widgets import LARGE_SPACING, SPACING, Segmented, with_alpha

translate = QCoreApplication.translate

# The roles in the order they are listed, in the three groups the page has.
GROUP_ROLES = (
    ("window", "view", "button", "header"),
    ("text", "text_muted", "link", "visited"),
    ("accent", "negative", "neutral", "positive"),
)
ROLES = tuple(role for roles in GROUP_ROLES for role in roles)


def group_titles() -> tuple[str, str, str]:
    return (
        translate("ui", "Surfaces"),
        translate("ui", "Text"),
        translate("ui", "Accents and states"),
    )


LIGHT, DARK = "light", "dark"


def swatch_icon(color: str, side: int = 16) -> QIcon:
    """A round swatch of `color` for a list entry."""
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(128, 128, 128, 140), 1))
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(0.5, 0.5, side - 1, side - 1))
    p.end()
    return QIcon(pixmap)


class _Result(QWidget):
    """What a role will be: a swatch for a background, "Aa" on the window for the rest."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.color, self.background, self.is_surface = QColor(), QColor(), True
        self.setFixedSize(QSize(38, 24))

    def show_color(self, color: str, background: str, is_surface: bool) -> None:
        self.color, self.background, self.is_surface = QColor(color), QColor(background), is_surface
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(with_alpha(self.palette().text().color(), 0.3), 1))
        p.setBrush(self.color if self.is_surface else self.background)
        p.drawRoundedRect(rect, 4, 4)
        if not self.is_surface:
            font = QFont(self.font())
            font.setBold(True)
            p.setFont(font)
            p.setPen(self.color)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Aa")


class ImportColorsDialog(QDialog):
    """`result` is what `palette` made of the source (a pywal file, a picture, ...); `source` says where
    it came from, for the sentence on top. `theme` is the theme in the editor: the preview shows a copy
    of it with the chosen colors. After `exec()` returns Accepted, `final()` has the twelve colors."""

    def __init__(
        self,
        result: palette.PaletteResult,
        source: str,
        theme: Theme,
        variant: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(translate("ui", "Import Colors"))
        self.setModal(True)
        self.result = result
        window = theme.get("colors", "window")
        if variant not in (LIGHT, DARK):
            variant = result.given if result.given in (LIGHT, DARK) else None
        self.variant = variant or (DARK if QColor(window).lightnessF() < 0.5 else LIGHT)
        self.adjusted: list[str] = []
        self.choosers: dict[str, QComboBox] = {}
        self.results: dict[str, _Result] = {}
        self._filling = False
        self._theme = theme.copy()

        intro = QLabel(
            translate(
                "ui",
                "The colors from {source} are matched to the colors of the theme. Choose another color "
                "for any of them. Nothing changes until you choose Use These Colors.",
            ).format(source=source)
        )
        intro.setWordWrap(True)

        self.variants = Segmented(
            [translate("ui", "Light theme"), translate("ui", "Dark theme")],
            0 if self.variant == LIGHT else 1,
            name=translate("ui", "Make a light or a dark theme"),
        )
        self.variants.changed.connect(self._variant_chosen)

        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACING)
        grid.setVerticalSpacing(SPACING)
        grid.setColumnStretch(1, 1)
        row = 0
        for title, roles in zip(group_titles(), GROUP_ROLES, strict=True):
            caption = QLabel(title)
            font = caption.font()
            font.setBold(True)
            caption.setFont(font)
            grid.addWidget(caption, row, 0, 1, 3)
            row += 1
            for role in roles:
                name = QLabel(str(FIELD_LABELS[("colors", role)]) + translate("ui", ":"))
                chooser = QComboBox()
                chooser.setAccessibleName(str(FIELD_LABELS[("colors", role)]))
                chooser.setIconSize(QSize(16, 16))
                chooser.setMinimumContentsLength(8)
                chooser.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
                chooser.activated.connect(self._changed)
                self.choosers[role] = chooser
                self.results[role] = _Result()
                grid.addWidget(name, row, 0)
                grid.addWidget(chooser, row, 1)
                grid.addWidget(self.results[role], row, 2)
                row += 1

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setForegroundRole(self.note.palette().ColorRole.PlaceholderText)

        self.preview = PreviewWidget(self._theme)
        self.preview.setMinimumSize(300, 220)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        buttons = QDialogButtonBox()
        self.use_button = buttons.addButton(
            translate("ui", "Use These Colors"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.cancel_button = buttons.addButton(
            translate("ui", "Cancel"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self.use_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        left = QVBoxLayout()
        left.setSpacing(LARGE_SPACING)
        left.addWidget(self.variants, 0, Qt.AlignmentFlag.AlignLeft)
        left.addLayout(grid)
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(SPACING)
        caption = QLabel(translate("ui", "Preview"))
        font = caption.font()
        font.setBold(True)
        caption.setFont(font)
        right.addWidget(caption)
        right.addWidget(self.preview, 1)
        right.addWidget(self.note)
        columns = QHBoxLayout()
        columns.setSpacing(LARGE_SPACING + 8)
        columns.addLayout(left, 0)
        columns.addLayout(right, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(LARGE_SPACING)
        layout.addWidget(intro)
        layout.addLayout(columns, 1)
        layout.addWidget(buttons)
        self.setMinimumWidth(860)
        self._fill()

    # ---- the choices

    def mapped(self) -> dict[str, str]:
        """What the source itself maps to each role, for the variant now chosen."""
        return dict(self.result.light if self.variant == LIGHT else self.result.dark)

    def _fill(self) -> None:
        """Offer the palette's colors in every chooser and select the mapped one."""
        self._filling = True
        offered = palette.candidates(self.result, self.variant)
        mapped = self.mapped()
        for role, chooser in self.choosers.items():
            chooser.clear()
            for color in offered:
                chooser.addItem(swatch_icon(color), color.upper(), color)
            wanted = mapped.get(role)
            index = chooser.findData(wanted)
            chooser.setCurrentIndex(max(index, 0))
        self._filling = False
        self._changed()

    def _variant_chosen(self, index: int) -> None:
        self.variant = LIGHT if index == 0 else DARK
        self._fill()

    def chosen(self) -> dict[str, str]:
        """The color each chooser has now, before the text is corrected."""
        mapped = self.mapped()
        return {
            role: chooser.currentData() or mapped.get(role, "#000000")
            for role, chooser in self.choosers.items()
        }

    def final(self) -> dict[str, str]:
        """The twelve colors that "Use These Colors" puts in the theme: the chosen ones, with text that is
        hard to read on its background moved as little as possible."""
        return palette.ensure_contrast(self.chosen())

    def _changed(self, *_) -> None:
        if self._filling:
            return
        chosen, final = self.chosen(), self.final()
        self.adjusted = [role for role in ROLES if final[role] != chosen[role]]
        for role in ROLES:
            self.results[role].show_color(final[role], final["window"], role in palette.SURFACES)
            self.results[role].setToolTip(
                translate("ui", "Made a little lighter or darker so that it can be read.")
                if role in self.adjusted
                else ""
            )
        for role, color in final.items():
            self._theme.set("colors", role, color)
        self.preview.set_theme(self._theme)
        self.note.setText(
            translate("ui", "Some colors were moved a little to keep the text easy to read.")
            if self.adjusted
            else translate("ui", "All text on these colors is easy to read.")
        )
