# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""System Sounds: sound themes.

A sound theme is a folder `sounds/<name>/` in a data folder (the home one and
those of XDG_DATA_DIRS) with an `index.theme` that has a `[Sound Theme]`
section and is not hidden. The id is the folder name (what kdeglobals
`[Sounds] Theme` stores); name and comment come from `index.theme`.
`extra["sample"]` is the path of one sound of the theme, when there is one.
The card is a neutral drawing of a speaker; sounds have no picture.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen

from ..messages import translate
from .base import Item, Kind, blank, installed, read_index_theme, read_ini, unique_sorted

_EXTENSIONS = (".oga", ".ogg", ".wav")
_PREFERRED = ("message-new-instant", "desktop-login", "bell", "dialog-information", "message")


def find_sample(folder: Path) -> Path | None:
    """One sound of a theme: its `Example` entry or a common event sound, else the first sound file."""
    section = read_ini(folder / "index.theme").get("Sound Theme", {})
    directories = [d for d in section.get("Directories", "").split(",") if d.strip()] or ["."]
    wanted = [section["Example"]] if section.get("Example") else []
    wanted += _PREFERRED
    first = None
    for directory in directories:
        base = folder / directory.strip()
        for name in wanted:
            for extension in _EXTENSIONS:
                if (base / (name + extension)).is_file():
                    return base / (name + extension)
        if first is None and base.is_dir():
            try:
                first = next((f for f in sorted(base.iterdir()) if f.suffix in _EXTENSIONS), None)
            except OSError:
                pass
    return first


class SoundThemes(Kind):
    key = "sounds"

    @property
    def title(self) -> str:
        return str(translate("core", "System Sounds"))

    def items(self) -> list[Item]:
        found = []
        for name, (folder, user) in installed("sounds").items():
            try:
                meta = read_index_theme(folder)
                if meta is None or "Sound Theme" not in read_ini(folder / "index.theme"):
                    continue
                sample = find_sample(folder)
            except Exception:
                continue
            found.append(
                Item(
                    name,
                    meta["name"] or name,
                    meta["description"],
                    folder,
                    user,
                    {"sample": sample} if sample else {},
                )
            )
        return unique_sorted(found)

    def thumbnail(self, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
        return speaker_card(size, dpr)


def speaker_card(size: QSize, dpr: float) -> QImage:
    """A neutral card with a loudspeaker and sound waves, drawn by hand."""
    image = blank(size, dpr)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w, h = size.width(), size.height()
    gradient = QLinearGradient(0, 0, 0, h)
    gradient.setColorAt(0, QColor("#3a4047"))
    gradient.setColorAt(1, QColor("#2a2f35"))
    p.setPen(QColor(255, 255, 255, 30))
    p.setBrush(gradient)
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 4, 4)
    u = min(w, h) / 110  # unit of the drawing
    cx, cy = w / 2 - 6 * u, h / 2
    glyph = QColor("#dfe3e8")
    speaker = QPainterPath()
    speaker.moveTo(cx - 24 * u, cy - 9 * u)
    speaker.lineTo(cx - 10 * u, cy - 9 * u)
    speaker.lineTo(cx + 8 * u, cy - 24 * u)
    speaker.lineTo(cx + 8 * u, cy + 24 * u)
    speaker.lineTo(cx - 10 * u, cy + 9 * u)
    speaker.lineTo(cx - 24 * u, cy + 9 * u)
    speaker.closeSubpath()
    p.setPen(QPen(glyph, 2 * u, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(glyph)
    p.drawPath(speaker)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i, radius in enumerate((13, 23, 33)):
        p.setPen(
            QPen(
                QColor(glyph.red(), glyph.green(), glyph.blue(), 255 - i * 55),
                3 * u,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        r = radius * u
        p.drawArc(QRectF(cx + 8 * u - r, cy - r, 2 * r, 2 * r), -40 * 16, 80 * 16)
    p.end()
    return image
