# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A preview that keeps the proportions of the part it shows, so it is never a tall empty box."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QSizePolicy

from ..preview import PreviewWidget


class RatioPreview(PreviewWidget):
    """The drawn desktop, as high as its width and the shown part ask for (see `PreviewWidget.view_rect`)."""

    def __init__(self, theme, mode: str = "desktop", parent=None):
        super().__init__(theme, parent)
        self.setMinimumSize(260, 120)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.set_mode(mode)

    def set_mode(self, mode: str) -> None:
        super().set_mode(mode)
        self.updateGeometry()

    def set_theme(self, theme) -> None:
        super().set_theme(theme)
        self.updateGeometry()  # a panel of another thickness or edge changes the part that is shown

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        view = self.view_rect()
        return max(120, round(width * view.height() / view.width()))

    def sizeHint(self) -> QSize:
        return QSize(480, self.heightForWidth(480))
