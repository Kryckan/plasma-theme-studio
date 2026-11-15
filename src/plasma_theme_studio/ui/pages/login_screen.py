# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The login screen: not edited here, one button to its page in System Settings."""

from __future__ import annotations

import configparser
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...generators.windowframe import Look
from .base import TUNING_WIDTH, LinkPage

translate = QCoreApplication.translate

SDDM_CONFIGS = (Path("/etc/sddm.conf"), *sorted(Path("/etc/sddm.conf.d").glob("*.conf")))
SDDM_THEMES = Path("/usr/share/sddm/themes")
SAMPLE_WIDTH = 360


def current_login_theme(configs=None) -> str | None:
    """The name of the SDDM theme the settings name, or None when they name none (or cannot be read)."""
    name = None
    for path in SDDM_CONFIGS if configs is None else configs:  # a later file wins
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read(path, encoding="utf-8")
        except (OSError, UnicodeDecodeError, configparser.Error):
            continue
        name = parser.get("Theme", "Current", fallback="").strip() or name
    return name


def preview_of(name: str, themes: Path | None = None) -> Path | None:
    """The picture a login theme ships to show itself, if it has one."""
    folder = (SDDM_THEMES if themes is None else themes) / name
    for candidate in ("preview.png", "preview.jpg", "preview.jpeg"):
        if (folder / candidate).is_file():
            return folder / candidate
    return None


def sketch(look: Look, width: int = SAMPLE_WIDTH) -> QPixmap:
    """A drawn stand-in for a login theme that ships no picture: a round user picture and a password field
    in the colors of the theme."""
    height = round(width * 9 / 16)
    picture = QPixmap(width, height)
    p = QPainter(picture)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(picture.rect(), QColor(look.header.hex))
    text = QColor(look.text.hex)
    muted = QColor(look.muted.hex)
    middle = width / 2
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(look.accent.hex))
    p.drawEllipse(QRectF(middle - 22, height * 0.2, 44, 44))
    p.setBrush(text)
    p.drawEllipse(QRectF(middle - 8, height * 0.2 + 9, 16, 16))
    p.drawRoundedRect(QRectF(middle - 14, height * 0.2 + 28, 28, 12), 6, 6)
    field = QRectF(middle - 70, height * 0.55, 140, 22)
    p.setBrush(QColor(look.window.hex))
    p.drawRoundedRect(field, look.radius, look.radius)
    p.setBrush(muted)
    for i in range(5):
        p.drawEllipse(QRectF(field.left() + 10 + i * 11, field.center().y() - 2.5, 5, 5))
    p.setBrush(QColor(look.accent.hex))
    p.drawRoundedRect(QRectF(middle - 28, height * 0.55 + 32, 56, 14), look.radius, look.radius)
    p.end()
    return picture


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

    def build(self) -> None:
        super().build()
        self.sample = QWidget()
        self.sample.setMaximumWidth(TUNING_WIDTH)
        column = QVBoxLayout(self.sample)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        self.current = QLabel()
        self.current.setTextFormat(Qt.TextFormat.PlainText)
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignLeft)
        column.addWidget(self.current)
        column.addWidget(self.picture)
        self.sketch_note = QLabel(
            translate("ui", "A sketch. The real login screen is set in System Settings.")
        )
        self.sketch_note.setWordWrap(True)
        self.sketch_note.setEnabled(False)
        column.addWidget(self.sketch_note)
        self.content.insertWidget(1, self.sample)
        self.show_current()

    def show_current(self) -> None:
        """Name the login theme in use and show the picture it ships, or a sketch, read-only."""
        name = current_login_theme()
        if name is None:
            self.current.setText(translate("ui", "The computer uses the default login screen."))
        else:
            self.current.setText(translate("ui", "The login screen now uses “{name}”.").format(name=name))
        path = preview_of(name) if name else None
        pixmap = QPixmap(str(path)) if path else QPixmap()
        shipped = not pixmap.isNull()
        if shipped:
            pixmap = pixmap.scaledToWidth(SAMPLE_WIDTH, Qt.TransformationMode.SmoothTransformation)
        self.picture.setPixmap(pixmap if shipped else sketch(Look.of(self.theme)))
        self.picture.setAccessibleName(translate("ui", "Picture of the login screen"))
        self.sketch_note.setVisible(not shipped)
