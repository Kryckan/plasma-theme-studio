# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A message strip inside the window that says what just happened."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton

translate = QCoreApplication.translate

POSITIVE, INFORMATION, WARNING = "positive", "information", "warning"

_LOOK = {
    POSITIVE: ("39,174,96", "data-success", "emblem-success"),
    INFORMATION: ("61,174,233", "data-information", "dialog-information"),
    WARNING: ("246,116,0", "data-warning", "dialog-warning"),
}


class Banner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        self.kind = INFORMATION
        self.icon = QLabel()
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        close = QToolButton()
        close.setAutoRaise(True)
        close.setIcon(QIcon.fromTheme("dialog-close"))
        close.setAccessibleName(translate("ui", "Close message"))
        close.setToolTip(translate("ui", "Close message"))
        close.clicked.connect(self.hide)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 6, 6)
        layout.addWidget(self.icon)
        layout.addWidget(self.label, 1)
        layout.addWidget(close)
        self.hide()
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self.hide)

    def text(self) -> str:
        return self.label.text()

    def show_message(self, kind: str, text: str, seconds: int = 0) -> None:
        """Show a message. It stays until closed unless `seconds` is given."""
        rgb, icon, fallback = _LOOK[kind]
        self.kind = kind
        self.setStyleSheet(
            f"#banner {{ background: rgba({rgb},45); border: 1px solid rgb({rgb}); border-radius: 5px; }}"
        )
        self.icon.setPixmap(QIcon.fromTheme(icon, QIcon.fromTheme(fallback)).pixmap(22, 22))
        self.label.setText(text)
        self.show()
        if seconds:
            self.timer.start(seconds * 1000)
        else:
            self.timer.stop()
