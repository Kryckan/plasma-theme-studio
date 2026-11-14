# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The login screen: not edited here, one button to its page in System Settings."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .base import LinkPage

translate = QCoreApplication.translate


class LoginScreenPage(LinkPage):
    key = "login_screen"

    def subtitle(self) -> str:
        return translate("ui", "The screen where you log in to the computer.")

    def explanation(self) -> str:
        return translate(
            "ui",
            "The login screen belongs to the whole computer, not to your account, and changing it needs "
            "administrator rights. That is why this app does not edit it. "
            "System Settings can do it, and asks for your password when it must.",
        )
