# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Icon themes: the choices of System Settings' Icons page and a picture of each.

The list follows that page: a folder with an index.theme that has a Directories
key (a cursor-only theme has none), not Hidden, and not one of the themes the
page leaves out (hicolor, locolor, default as fallbacks; Adwaita, Adwaita Dark
and HighContrast are the names kcm_icons itself compares with). The id is the
folder name, which is what kdeglobals [Icons] Theme holds.

The picture is six sample icons found by hand, the way the icon theme
specification says (the directory that fits the size best, then the themes in
Inherits, then hicolor). Nothing here touches QIcon's theme or any other state
of the application. Monochrome icons that use the "current-color-scheme"
stylesheet are recolored with the given colors.
"""

from __future__ import annotations

import math
import os
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from .. import images
from ..messages import translate
from ..model.color import Color
from ..model.color import on_accent as readable_on_accent
from . import base
from .base import Item, Kind

# Each slot of the picture: the icon names to try, best first. They are the names the
# Icons page itself looks up (home, folder, a document, trash, settings, run).
SAMPLES = (
    ("user-home", "folder-home", "go-home"),
    ("folder", "inode-directory"),
    ("text-x-generic", "text-plain", "document"),
    ("user-trash", "trash-empty", "edittrash"),
    ("configure", "preferences-system", "systemsettings"),
    ("system-run", "application-x-executable", "exec"),
)

# The twelve icons of the large preview on the Icons page (the page shows them at 48 and 32 pixels).
STRIP = (
    ("folder", "inode-directory"),
    ("user-home", "folder-home", "go-home"),
    ("folder-documents", "folder-document"),
    ("folder-download", "folder-downloads"),
    ("folder-pictures", "folder-image", "folder-images"),
    ("text-x-generic", "text-plain", "document"),
    ("image-x-generic", "image-png"),
    ("audio-x-generic", "audio-mp3"),
    ("user-trash", "trash-empty", "edittrash"),
    ("configure", "preferences-system", "systemsettings"),
    ("help-contents", "help-about", "system-help", "help-browser"),
    ("system-run", "application-x-executable", "exec"),
)

NOT_LISTED = {"hicolor", "locolor", "default", "Adwaita", "Adwaita Dark", "HighContrast"}
EXTENSIONS = (".svg", ".svgz", ".png", ".xpm")


def roots() -> list[tuple[Path, bool]]:
    """The folders that hold icon themes, the home folder's first."""
    return base.data_folders("icons", legacy_home=".icons")


def _list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _number(value, default: int) -> int:
    """The leading integer of a value; index.theme files in the wild have "12px"."""
    found = re.match(r"\s*(-?\d+)", str(value))
    return int(found.group(1)) if found else default


class IconThemes(Kind):
    key = "icons"
    scheme_dependent = True

    @property
    def title(self) -> str:
        return str(translate("ui", "Icons"))

    def items(self) -> list[Item]:
        langs = base.languages()
        found: list[Item] = []
        for root, user in roots():
            try:
                children = sorted(root.iterdir())
            except OSError:
                continue
            for folder in children:
                if folder.name in NOT_LISTED:
                    continue
                section = base.read_ini(folder / "index.theme").get("Icon Theme")
                if section is None or not section.get("Directories", "").strip():
                    continue
                if section.get("Hidden", "").lower() == "true":
                    continue
                name = base.localized(section, "Name", langs) or folder.name
                if name in NOT_LISTED:
                    continue
                comment = base.localized(section, "Comment", langs)
                extra = {"inherits": _list(section.get("Inherits", ""))}
                found.append(Item(folder.name, name, comment, folder, user, extra))
        return base.unique_sorted(found)

    def thumbnail(self, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
        try:
            return _picture(item, size, dpr, colors)
        except Exception:
            return QImage()


# Reading a theme ------------------------------------------------------------


@dataclass(frozen=True)
class _Directory:
    name: str
    size: int  # physical pixels: Size * Scale
    scale: int
    kind: str
    minimum: int
    maximum: int
    threshold: int


@dataclass(frozen=True)
class _Theme:
    inherits: tuple[str, ...]
    directories: tuple[_Directory, ...]


_lock = threading.Lock()
_themes: dict[tuple[str, int], _Theme | None] = {}
_listings: dict[str, frozenset[str]] = {}
_orders: dict[tuple[str, int, int, int], list[_Directory]] = {}


def clear_caches() -> None:
    """Forget the directory listings (after icons were installed)."""
    with _lock:
        _themes.clear()
        _listings.clear()
        _orders.clear()


def _theme(folder: Path) -> tuple[tuple[str, int], _Theme | None]:
    """The parsed index.theme of a theme folder with the key it is kept under (it
    is read again when the file changes)."""
    index = folder / "index.theme"
    try:
        key = (str(folder), os.stat(index).st_mtime_ns)
    except OSError:
        return (str(folder), 0), None
    with _lock:
        if key in _themes:
            return key, _themes[key]
    sections = base.read_ini(index)
    section = sections.get("Icon Theme")
    theme = None
    if section is not None:
        directories = []
        for name in _list(section.get("Directories", "") + "," + section.get("ScaledDirectories", "")):
            entry = sections.get(name)
            if entry is None:
                continue
            scale = max(1, _number(entry.get("Scale", "1"), 1))
            size = _number(entry.get("Size", "0"), 0)
            directories.append(
                _Directory(
                    name,
                    size * scale,
                    scale,
                    entry.get("Type", "Threshold"),
                    _number(entry.get("MinSize", size), size) * scale,
                    _number(entry.get("MaxSize", size), size) * scale,
                    _number(entry.get("Threshold", 2), 2) * scale,
                )
            )
        theme = _Theme(tuple(_list(section.get("Inherits", ""))), tuple(directories))
    with _lock:
        _themes[key] = theme
    return key, theme


def _names(folder: Path) -> frozenset[str]:
    """The file names in a directory of a theme; one listing instead of a check per file."""
    key = str(folder)
    found = _listings.get(key)
    if found is None:
        try:
            with os.scandir(folder) as entries:
                found = frozenset(entry.name for entry in entries)
        except OSError:
            found = frozenset()
        _listings[key] = found
    return found


def _distance(directory: _Directory, want: int) -> int:
    """How far the directory is from `want` physical pixels (icon theme specification)."""
    if directory.kind == "Fixed":
        return abs(directory.size - want)
    if directory.kind == "Scalable":
        low, high = directory.minimum, directory.maximum
    else:
        low, high = directory.size - directory.threshold, directory.size + directory.threshold
    return low - want if want < low else want - high if want > high else 0


def _ordered(key: tuple[str, int], theme: _Theme, want: int, scale: int) -> list[_Directory]:
    """The directories of the theme, the best fit for `want` first. Among equals a scalable one
    wins, then the bigger one (KDE's icon loader scales down rather than up). Directories
    made for a bigger scale than `scale` (Breeze's monochrome 22@2x) come last."""
    order = _orders.get((*key, want, scale))
    if order is None:
        order = sorted(
            theme.directories,
            key=lambda d: (d.scale > scale, _distance(d, want), d.kind != "Scalable", -d.size),
        )
        _orders[(*key, want, scale)] = order
    return order


class Finder:
    """Looks icons up in the installed themes; nothing of the application's own icon theme is used."""

    def __init__(self) -> None:
        self.roots = [root for root, _user in roots()]
        self.real_roots = [os.path.realpath(root) for root in self.roots]

    def folder(self, theme_id: str) -> Path | None:
        for root in self.roots:
            if (root / theme_id / "index.theme").is_file():
                return root / theme_id
        return None

    def find(self, theme: Path, names, want: int, scale: int = 1) -> Path | None:
        """The file of the first of `names` that the theme, the themes it inherits or
        hicolor have, for an icon of about `want` physical pixels."""
        chain = self.chain(theme)
        for name in names:
            for folder in chain:
                found = self._in_theme(folder, name, want, scale)
                if found is not None:
                    return found
        return None

    def chain(self, theme: Path) -> list[Path]:
        """The theme, what it inherits (depth first, as the specification has it), then hicolor."""
        out: list[Path] = []
        seen: set[str] = set()

        def add(folder: Path) -> None:
            if folder.name in seen:
                return
            seen.add(folder.name)
            out.append(folder)
            parsed = _theme(folder)[1]
            for parent in parsed.inherits if parsed else ():
                where = self.folder(parent)
                if where is not None:
                    add(where)

        add(theme)
        hicolor = self.folder("hicolor")
        if hicolor is not None:
            add(hicolor)
        return out

    def _in_theme(self, folder: Path, name: str, want: int, scale: int) -> Path | None:
        key, parsed = _theme(folder)
        if parsed is None:
            return None
        for directory in _ordered(key, parsed, want, scale):
            here = folder / directory.name
            listed = _names(here)
            for extension in EXTENSIONS:
                if name + extension in listed:
                    path = here / (name + extension)
                    return path if self._inside(path, folder) else None
        return None

    def _inside(self, path: Path, folder: Path) -> bool:
        """False for a link that leads out of the icon folders and the theme's own folder."""
        real = os.path.realpath(path)
        return any(real.startswith(top + os.sep) for top in (*self.real_roots, os.path.realpath(folder)))


# Drawing ---------------------------------------------------------------------


def _stylesheet(colors: Mapping[str, str]) -> str:
    """The stylesheet KDE's icon loader puts into "current-color-scheme", from the twelve roles."""
    accent = colors.get("accent", "#3daee9")
    text = colors.get("text", "#232629")
    rules = {
        "Text": text,
        "Background": colors.get("window", "#eff0f1"),
        "Accent": accent,
        "Highlight": accent,
        "HighlightedText": readable_on_accent(
            Color.parse(QColor(accent).name()),
            Color.parse(QColor(text).name()),
            Color.parse(QColor(colors.get("window", "#eff0f1")).name()),
        ).hex,
        "PositiveText": colors.get("positive", "#27ae60"),
        "NeutralText": colors.get("neutral", "#f67400"),
        "NegativeText": colors.get("negative", "#da4453"),
        "ButtonText": text,
        "ButtonBackground": colors.get("button", "#eff0f1"),
        "ButtonHover": accent,
        "ButtonFocus": accent,
        "ViewText": text,
        "ViewBackground": colors.get("view", "#fcfcfc"),
        "ViewHover": accent,
        "ViewFocus": accent,
    }
    return "".join(f".ColorScheme-{name}{{color:{value};}}" for name, value in rules.items())


_STYLE = re.compile(rb'(<style[^>]*id="current-color-scheme"[^>]*>)(.*?)(</style>)', re.DOTALL)


def recolor(svg: bytes, colors: Mapping[str, str] | None) -> bytes:
    """`svg` with its "current-color-scheme" stylesheet replaced by one made of `colors`."""
    if not colors or b"current-color-scheme" not in svg:
        return svg
    sheet = _stylesheet(colors).encode()
    return _STYLE.sub(lambda found: found.group(1) + sheet + found.group(3), svg, count=1)


def _icon_image(path: Path, side: int, colors: Mapping[str, str] | None) -> QImage:
    """The icon file as a picture that fits `side` x `side` pixels, or a null image."""
    if path.suffix in (".svg", ".svgz"):
        from PySide6.QtSvg import QSvgRenderer

        data = base.read_svg(path)
        renderer = QSvgRenderer(recolor(data, colors)) if data else None
        if renderer is None or not renderer.isValid():
            return QImage()
        view = renderer.viewBoxF()
        if view.width() <= 0 or view.height() <= 0:
            return QImage()
        image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        scale = side / max(view.width(), view.height())
        width, height = view.width() * scale, view.height() * scale
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF((side - width) / 2, (side - height) / 2, width, height))
        painter.end()
        return image
    return base.fit_image(images.read_image(path), QSize(side, side), 1.0)


def _grid(size: QSize) -> tuple[int, int, float]:
    """Columns, rows and the icon side (logical pixels) for six icons: one row or two."""
    best = (3, 2, 0.0)
    for columns in (6, 3):
        rows = 6 // columns
        side = min(size.width() / columns, size.height() / rows) * 0.72
        if side > best[2]:
            best = (columns, rows, side)
    return best


def _picture(item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
    if item.path is None or _theme(Path(item.path))[1] is None:
        return QImage()
    finder = Finder()
    columns, rows, side = _grid(size)
    pixels = max(8, round(side * dpr))
    out = base.blank(size, dpr)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    drawn = 0
    for index, names in enumerate(SAMPLES):
        path = finder.find(Path(item.path), names, pixels, max(1, math.ceil(dpr)))
        image = _icon_image(path, pixels, colors) if path else QImage()
        if image.isNull():
            continue
        cell_w, cell_h = size.width() / columns, size.height() / rows
        x = (index % columns) * cell_w + (cell_w - side) / 2
        y = (index // columns) * cell_h + (cell_h - side) / 2
        painter.drawImage(QRectF(x, y, side, side), image)
        drawn += 1
    painter.end()
    return out if drawn else QImage()


def sample_rows(
    item: Item, sides: tuple[int, ...], dpr: float, colors: Mapping[str, str] | None
) -> list[list[QImage]]:
    """The twelve icons of `STRIP` of the theme, one row for each of `sides` (logical pixels). An icon that
    neither the theme, its parents nor hicolor have is left out, so a row has no holes. Safe on a worker
    thread; an empty list when the theme cannot be read."""
    if item.path is None or _theme(Path(item.path))[1] is None:
        return []
    finder = Finder()
    rows: list[list[QImage]] = []
    for side in sides:
        pixels = max(8, round(side * dpr))
        row = []
        for names in STRIP:
            path = finder.find(Path(item.path), names, pixels, max(1, math.ceil(dpr)))
            image = _icon_image(path, pixels, colors) if path else QImage()
            if not image.isNull():
                image.setDevicePixelRatio(dpr)
                row.append(image)
        rows.append(row)
    return rows if any(rows) else []
