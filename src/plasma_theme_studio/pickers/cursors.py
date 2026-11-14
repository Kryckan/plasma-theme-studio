# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cursor themes: the choices of System Settings' Pointers page and a picture of each.

A cursor theme is a folder in an icons folder with a `cursors` folder (bitmap
Xcursor files, see `xcursor`) and/or `cursors_scalable` (one folder per cursor
with metadata.json and an SVG). The id is the folder name, which is what
kcminputrc [Mouse] cursorTheme holds; the name is the one in index.theme.

The page offers the sizes that the theme's `left_ptr` file has (`extra["sizes"]`).
A theme with only SVG cursors has no such list; it gets `SCALABLE_SIZES`, the
usual steps of the size box, since an SVG scales to any size. The picture is
eight sample cursors at the nominal size nearest to 24 pixels times the pixel
ratio. Links inside the theme are followed (most cursor names are links), but
never to a place outside the icon folders and the theme's own folder.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QImage, QPainter

from ..messages import translate
from . import base, xcursor
from .base import Item, Kind
from .icons import roots

# The cursors of the picture, each with the names it goes by in different themes
# (the names the Pointers page itself asks for: left_ptr, left_ptr_watch, pointer, help, ibeam ...).
SAMPLES = (
    ("left_ptr", "default", "arrow", "top_left_arrow"),
    ("pointer", "pointing_hand", "hand2", "hand1"),
    ("ibeam", "text", "xterm"),
    ("cross", "crosshair"),
    ("left_ptr_watch", "progress", "wait", "watch"),
    ("help", "question_arrow", "whats_this", "left_ptr_help"),
    ("size_all", "fleur", "all-scroll", "move"),
    ("size_fdiag", "nwse-resize", "bd_double_arrow", "fd_double_arrow"),
)
SIZE_NAMES = SAMPLES[0]  # the cursor whose sizes are the theme's sizes
CURSOR_SIZE = 24  # logical pixels, as the default pointer size
SCALABLE_SIZES = (24, 32, 36, 48, 64, 72, 96, 128)
MAX_SVG = 8 * 1024 * 1024


class CursorThemes(Kind):
    key = "cursors"

    @property
    def title(self) -> str:
        return str(translate("ui", "Pointers"))

    def items(self) -> list[Item]:
        langs = base.languages()
        finder = Finder()
        found: list[Item] = []
        for root, user in roots():
            try:
                children = sorted(root.iterdir())
            except OSError:
                continue
            for folder in children:
                try:
                    bitmaps = (folder / "cursors").is_dir()
                    scalable = (folder / "cursors_scalable").is_dir()
                    if not (bitmaps or scalable):
                        continue
                    section = base.read_ini(folder / "index.theme").get("Icon Theme", {})
                    if section.get("Hidden", "").lower() == "true":
                        continue
                    name = base.localized(section, "Name", langs) or folder.name
                    comment = base.localized(section, "Comment", langs)
                    inherits = [p.strip() for p in section.get("Inherits", "").split(",") if p.strip()]
                    extra = {"sizes": finder.sizes(folder), "inherits": inherits, "scalable": scalable}
                except Exception:
                    continue
                found.append(Item(folder.name, name, comment, folder, user, extra))
        return base.unique_sorted(found)

    def thumbnail(self, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
        try:
            return _picture(item, size, dpr)
        except Exception:
            return QImage()


class Finder:
    """Finds the file of a cursor in a theme folder, its Inherits chain included."""

    def __init__(self) -> None:
        self.roots = [root for root, _user in roots()]
        self.real_roots = [os.path.realpath(root) for root in self.roots]

    def folder(self, theme_id: str) -> Path | None:
        for root in self.roots:
            if (root / theme_id).is_dir():
                return root / theme_id
        return None

    def chain(self, theme: Path) -> list[Path]:
        out: list[Path] = []

        def add(folder: Path) -> None:
            if any(folder.name == seen.name for seen in out):
                return
            out.append(folder)
            section = base.read_ini(folder / "index.theme").get("Icon Theme", {})
            for parent in section.get("Inherits", "").split(","):
                where = self.folder(parent.strip()) if parent.strip() else None
                if where is not None:
                    add(where)

        add(theme)
        return out

    def find(self, theme: Path, names) -> tuple[str, Path] | None:
        """("bitmap", file) or ("svg", metadata.json) for the first of `names` the theme or
        a theme it inherits has; the theme's own cursors come before the parent's."""
        for folder in self.chain(theme):
            for name in names:
                for kind, path in (
                    ("bitmap", folder / "cursors" / name),
                    ("svg", folder / "cursors_scalable" / name / "metadata.json"),
                ):
                    if path.is_file() and self._inside(path, folder):
                        return kind, path
        return None

    def sizes(self, theme: Path) -> list[int]:
        found = self.find(theme, SIZE_NAMES)
        if found is None:
            return []
        if found[0] == "bitmap":
            return xcursor.nominal_sizes(found[1])
        return list(SCALABLE_SIZES)

    def _inside(self, path: Path, folder: Path) -> bool:
        real = os.path.realpath(path)
        return any(real.startswith(top + os.sep) for top in (*self.real_roots, os.path.realpath(folder)))


def _svg_cursor(metadata: Path, pixels: int) -> QImage:
    """The SVG cursor of a cursors_scalable folder, drawn at `pixels` for its nominal size."""
    from PySide6.QtSvg import QSvgRenderer

    entries = json.loads(metadata.read_text("utf-8"))
    entry = entries[0] if isinstance(entries, list) and entries else None
    if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
        return QImage()
    nominal = entry.get("nominal_size", 24)
    file = metadata.parent / entry["filename"]
    if not isinstance(nominal, int | float) or nominal <= 0 or file.stat().st_size > MAX_SVG:
        return QImage()
    if os.path.commonpath([os.path.realpath(file), os.path.realpath(metadata.parent)]) != os.path.realpath(
        metadata.parent
    ):
        return QImage()
    data = base.read_svg(file)
    renderer = QSvgRenderer(data) if data else None
    if renderer is None or not renderer.isValid():
        return QImage()
    default = renderer.defaultSize()
    scale = pixels / nominal
    width, height = max(1, round(default.width() * scale)), max(1, round(default.height() * scale))
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    return image


def sample_image(finder: Finder, theme: Path, names, pixels: int) -> QImage:
    """One cursor of the theme at the size nearest to `pixels`, scaled to `pixels` as its
    nominal size, or a null image."""
    found = finder.find(theme, names)
    if found is None:
        return QImage()
    kind, path = found
    if kind == "svg":
        try:
            return _svg_cursor(path, pixels)
        except (OSError, ValueError):
            return QImage()
    cursor = xcursor.read_image(path, pixels)
    if cursor is None:
        return QImage()
    image = cursor.to_qimage()
    if cursor.nominal != pixels:
        factor = pixels / cursor.nominal
        image = image.scaled(
            max(1, round(image.width() * factor)),
            max(1, round(image.height() * factor)),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return image


def _picture(item: Item, size: QSize, dpr: float) -> QImage:
    if item.path is None:
        return QImage()
    finder = Finder()
    theme = Path(item.path)
    pixels = max(8, round(CURSOR_SIZE * dpr))
    columns, rows = 4, 2
    out = base.blank(size, dpr)
    painter = QPainter(out)
    drawn = 0
    for index, names in enumerate(SAMPLES):
        image = sample_image(finder, theme, names, pixels)
        if image.isNull():
            continue
        cell_w, cell_h = size.width() / columns, size.height() / rows
        width, height = image.width() / dpr, image.height() / dpr
        x = (index % columns) * cell_w + (cell_w - width) / 2
        y = (index // columns) * cell_h + (cell_h - height) / 2
        painter.drawImage(QRectF(x, y, width, height), image)
        drawn += 1
    painter.end()
    return out if drawn else QImage()
