# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The block "Colors from the wallpaper" of the Colors page: the picture, six colors taken from it and
the two buttons that make a light or a dark theme of them.

Reading the picture and taking its colors (`palette.extract`) happen in a worker (`WallpaperJob`); the
answer arrives as a `WallpaperColors` on the GUI thread. A picture that claims to be huge is refused
before it is decoded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QRectF, QRunnable, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ... import images, palette, safefile, wallpaper
from ..widgets import SPACING, with_alpha

translate = QCoreApplication.translate

SHOWN = 6  # colors taken from the picture that are shown
THUMB = QSize(240, 135)
LINE_GAP = 12  # between the title of the block and its colors


@dataclass
class WallpaperColors:
    """What the worker found: the picture (or why there is none) and the colors of the picture."""

    path: Path | None = None
    thumbnail: QImage | None = None
    result: palette.PaletteResult | None = None
    reason: str = ""

    @property
    def colors(self) -> list[str]:
        return self.result.swatches[:SHOWN] if self.result is not None and self.result.ok else []


class WallpaperAnswer(QObject):
    done = Signal(int, object)  # (the number of the job, a WallpaperColors)


def _thumbnail(path: Path, dpr: float) -> QImage | None:
    """The picture cut to 16:9 at the size of the block; None when it cannot be read."""
    reader = images.open_reader(path)
    if reader is None:
        return None
    size = reader.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        # a JPEG decodes at the reduced size; other formats are scaled after they are read
        want = QSize(round(THUMB.width() * dpr), round(THUMB.height() * dpr))
        scale = max(want.width() / size.width(), want.height() / size.height())
        if scale < 1:
            reader.setScaledSize(
                QSize(max(1, round(size.width() * scale)), max(1, round(size.height() * scale)))
            )
    image = reader.read()
    if image.isNull():
        return None
    want = QSize(round(THUMB.width() * dpr), round(THUMB.height() * dpr))
    image = image.scaled(
        want, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
    )
    left, top = (image.width() - want.width()) // 2, (image.height() - want.height()) // 2
    image = image.copy(left, top, want.width(), want.height())
    image.setDevicePixelRatio(dpr)
    return image


class WallpaperJob(QRunnable):
    """Find the wallpaper (or take `path`), draw its thumbnail and take its colors."""

    def __init__(self, number: int, path: Path | None, dpr: float, answer: WallpaperAnswer):
        super().__init__()
        self.number, self.path, self.dpr, self.answer = number, path, dpr, answer

    def work(self) -> WallpaperColors:
        path, reason = self.path, ""
        if path is None:
            try:
                source = wallpaper.wallpaper_source()
            except Exception:  # noqa: BLE001 - a broken desktop file is no reason to stop
                return WallpaperColors(reason=str(translate("ui", "The desktop settings cannot be read.")))
            path = source.path
            reason = str(source.reason or "")
        if path is None:
            return WallpaperColors(reason=reason)
        if not safefile.is_regular(path):  # a pipe would block this thread for ever
            return WallpaperColors(path, reason=str(translate("ui", "This picture cannot be read.")))
        if images.too_large(path):
            return WallpaperColors(path, reason=str(translate("ui", "This picture is too large to read.")))
        thumbnail = _thumbnail(path, self.dpr)
        if thumbnail is None:
            return WallpaperColors(path, reason=str(translate("ui", "This picture cannot be read.")))
        result = palette.extract(path)
        if not result.ok:
            return WallpaperColors(path, thumbnail, reason=str(result.error))
        return WallpaperColors(path, thumbnail, result)

    def run(self) -> None:
        try:
            found = self.work()
        except Exception:  # noqa: BLE001 - never leave the block waiting
            found = WallpaperColors(reason=str(translate("ui", "This picture cannot be read.")))
        try:
            self.answer.done.emit(self.number, found)
        except RuntimeError:  # the page is gone
            pass


class Strip(QWidget):
    """A row of round color samples."""

    def __init__(self, side: int, parent=None):
        super().__init__(parent)
        self.side = side
        self.colors: list[QColor] = []
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._resize()

    def set_colors(self, colors) -> None:
        self.colors = [QColor(c) for c in colors]
        self._resize()
        self.update()

    def _resize(self) -> None:
        count = max(1, len(self.colors))
        self.setFixedSize(count * self.side + (count - 1) * SPACING // 2, self.side)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(with_alpha(self.palette().text().color(), 0.3), 1))
        for i, color in enumerate(self.colors):
            p.setBrush(color)
            x = i * (self.side + SPACING // 2)
            p.drawEllipse(QRectF(x + 0.5, 0.5, self.side - 1, self.side - 1))


class Picture(QLabel):
    """The thumbnail with rounded corners, or a plain frame while there is none."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(THUMB)
        self.image: QImage | None = None

    def set_image(self, image: QImage | None) -> None:
        self.image = image
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        text = self.palette().text().color()
        if self.image is not None:
            p.setClipPath(path)
            p.drawPixmap(self.rect(), QPixmap.fromImage(self.image))
            p.setClipping(False)
        else:
            p.fillPath(path, with_alpha(text, 0.06))
        p.setPen(QPen(with_alpha(text, 0.25), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


class WallpaperBlock(QWidget):
    """One line (the title, an arrow and the six colors) that opens into the picture, a sentence and
    the buttons. Signals: `use_light`, `use_dark` and `choose` (the person wants another picture)."""

    use_light = Signal()
    use_dark = Signal()
    choose = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.toggle = QToolButton()
        self.toggle.setText(translate("ui", "Colors from the wallpaper"))
        self.toggle.setAutoRaise(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        font = self.toggle.font()
        font.setBold(True)
        self.toggle.setFont(font)
        self.toggle.clicked.connect(lambda: self.set_open(not self.body.isVisible()))
        self.small = Strip(14)
        line = QHBoxLayout()
        line.setSpacing(LINE_GAP)
        line.addWidget(self.toggle)
        line.addWidget(self.small)
        line.addStretch(1)

        self.picture = Picture()
        self.sentence = QLabel()
        self.sentence.setWordWrap(True)
        self.sentence.setTextFormat(Qt.TextFormat.PlainText)
        self.big = Strip(28)
        self.light = QPushButton(translate("ui", "Use as light theme"))
        self.dark = QPushButton(translate("ui", "Use as dark theme"))
        self.other = QPushButton(translate("ui", "Colors from a Picture…"))
        self.light.clicked.connect(self.use_light)
        self.dark.clicked.connect(self.use_dark)
        self.other.clicked.connect(self.choose)
        buttons = QHBoxLayout()
        buttons.setSpacing(SPACING)
        for button in (self.light, self.dark, self.other):
            buttons.addWidget(button)
        buttons.addStretch(1)
        side = QVBoxLayout()
        side.setSpacing(12)
        side.addWidget(self.sentence)
        side.addWidget(self.big)
        side.addLayout(buttons)
        side.addStretch(1)
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self.picture, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(side, 1)
        self.body = QWidget()
        self.body.setLayout(body)
        body.setContentsMargins(0, 0, 0, 0)
        self.body.hide()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SPACING)
        outer.addLayout(line)
        outer.addWidget(self.body)
        self.set_busy()

    def set_open(self, open_: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow)
        self.body.setVisible(open_)

    def set_busy(self) -> None:
        self.sentence.setText(translate("ui", "Reading the picture…"))
        self.picture.set_image(None)
        self._colors([])
        for button in (self.light, self.dark):
            button.setEnabled(False)

    def _colors(self, colors) -> None:
        self.small.set_colors(colors)
        self.small.setVisible(bool(colors))
        self.big.set_colors(colors)
        self.big.setVisible(bool(colors))

    def show_found(self, found: WallpaperColors) -> None:
        """Show what the worker found."""
        self.picture.set_image(found.thumbnail)
        colors = found.colors
        self._colors(colors)
        for button in (self.light, self.dark):
            button.setEnabled(bool(colors))
        if found.result is not None and found.result.ok:
            name = found.path.name if found.path is not None else ""
            text = translate("ui", "The colors are taken from {name}.").format(name=name)
            if not found.result.colorful:
                text += " " + translate(
                    "ui", "There is hardly any color in it, so the accent is Breeze blue."
                )
            self.sentence.setText(text)
        else:
            self.sentence.setText(found.reason or translate("ui", "The wallpaper cannot be read."))
        self.toggle.setToolTip(self.sentence.text())
