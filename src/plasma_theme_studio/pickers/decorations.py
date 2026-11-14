# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Window Decorations: what System Settings' page lists, drawn by the decorations themselves.

Three sorts of decoration are listed, with the ids KWin's configuration stores in
kwinrc `[org.kde.kdecoration2]` as `<library>:<theme>`:

- Binary plugins in the `org.kde.kdecoration3` plugin folder that are a decoration
  themselves, not an engine for themes (Breeze, Oxygen, Klassy when it is installed
  as a plugin): `org.kde.breeze:Breeze`. The name comes from the plugin's metadata.
- Aurorae SVG themes (`aurorae/themes/<name>/` with a `decoration.svg` or `.svgz` and
  an rc file): `org.kde.kwin.aurorae.v2:__aurorae__svg__<name>`. The page writes the
  `.v2` library on this Plasma version; the old `org.kde.kwin.aurorae` is its QML engine.
- Aurorae QML themes (`kwin/decorations/<name>/`, for example Plastik):
  `org.kde.kwin.aurorae:<name>`, the name being `kwin4_decoration_qml_plastik`.

`extra["made_here"]` marks a frame this app generated. A thumbnail is an inactive and an active
window drawn by KWin's own plugin in the helper process (`_helper.py`), one run for all
decorations. If that fails, an Aurorae SVG theme is composed here from its pieces, and any
other decoration is a neutral window.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QPluginLoader, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter

from ..generators.base import made_here
from ..generators.windowframe import AURORAE_LIBRARY, AURORAE_THEME_PREFIX, FOLDER_PREFIX
from ..messages import translate
from . import _colors, _process
from ._helper import DECORATION_MARGIN as MARGIN
from .base import Item, Kind, blank, data_folders, load_svg, localized, read_ini, read_metadata, unique_sorted

QML_LIBRARY = "org.kde.kwin.aurorae"
PLUGIN_SUBFOLDER = "org.kde.kdecoration3"
# The helper draws windows at this part of their size in the picture, so that the title
# fits between the buttons.
SCALE = 0.65
INSET = 12  # the space between the windows and the edge of the picture
RETRY = 30  # a failed helper run is tried again after this many seconds


# Listing -------------------------------------------------------------------


def plugin_folders() -> list[Path]:
    """The folders that may hold KWin decoration plugins."""
    import os

    bases = [Path(p) for p in os.environ.get("QT_PLUGIN_PATH", "").split(os.pathsep) if p]
    bases.append(Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)))
    for lib in ("lib", "lib64", "lib/x86_64-linux-gnu", "lib/aarch64-linux-gnu"):
        bases.append(Path("/usr") / lib / "qt6" / "plugins")
    found: list[Path] = []
    for base in bases:
        folder = base / PLUGIN_SUBFOLDER
        if folder.is_dir() and folder not in found:
            found.append(folder)
    return found


def plugin_metadata(path: Path) -> dict:
    """The metadata of a plugin file, {} when it has none."""
    return QPluginLoader(str(path)).metaData().get("MetaData", {})


def _plugins() -> list[Item]:
    items = []
    for folder in plugin_folders():
        for path in sorted(folder.glob("*.so")):
            metadata = plugin_metadata(path)
            if not isinstance(metadata, dict) or metadata.get("org.kde.kdecoration3", {}).get("themes"):
                continue  # not a decoration, or an engine such as Aurorae
            plugin = metadata.get("KPlugin") or {}
            theme = plugin.get("Name")
            if not theme:
                continue
            items.append(
                Item(
                    f"{path.stem}:{theme}",
                    localized(plugin, "Name") or theme,
                    localized(plugin, "Description"),
                    path,
                    False,
                    {"kind": "plugin", "library": path.stem, "theme": theme, "made_here": False},
                )
            )
    return items


def _aurorae_svg() -> list[Item]:
    items = []
    for base, user in data_folders("aurorae", "themes"):
        try:
            folders = sorted(base.iterdir())
        except OSError:
            continue
        for folder in folders:
            if not (folder / f"{folder.name}rc").is_file() or not any(
                (folder / f"decoration{ext}").is_file() for ext in (".svg", ".svgz")
            ):
                continue  # for example a source tree of a decoration
            metadata = read_metadata(folder) or {}
            made = folder.name.startswith(FOLDER_PREFIX) and made_here(folder / "metadata.desktop")
            theme = AURORAE_THEME_PREFIX + folder.name
            items.append(
                Item(
                    f"{AURORAE_LIBRARY}:{theme}",
                    metadata.get("name") or folder.name,
                    metadata.get("description", ""),
                    folder,
                    user,
                    {"kind": "svg", "library": AURORAE_LIBRARY, "theme": theme, "made_here": made},
                )
            )
    return items


def _aurorae_qml() -> list[Item]:
    items = []
    for base, user in data_folders("kwin", "decorations"):
        try:
            folders = sorted(base.iterdir())
        except OSError:
            continue
        for folder in folders:
            metadata = read_metadata(folder)
            if metadata is None or not (folder / "contents" / "ui" / "main.qml").is_file():
                continue
            items.append(
                Item(
                    f"{QML_LIBRARY}:{folder.name}",
                    metadata["name"] or folder.name,
                    metadata["description"],
                    folder,
                    user,
                    {"kind": "qml", "library": QML_LIBRARY, "theme": folder.name, "made_here": False},
                )
            )
    return items


def list_decorations() -> list[Item]:
    return unique_sorted([*_plugins(), *_aurorae_svg(), *_aurorae_qml()])


# Pictures made here ----------------------------------------------------------

# Buttons the way KWin's defaults have them: Aurorae button letters and their files.
BUTTON_FILES = {"I": "minimize", "A": "maximize", "X": "close", "S": "alldesktops", "H": "help"}
LEFT_BUTTONS, RIGHT_BUTTONS = "S", "IAX"


def _number(values: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(float(values.get(key, "").strip()))
    except ValueError:
        return default


def _rgb(text: str, default: str) -> QColor:
    try:
        return QColor(*[int(part) for part in text.split(",")])
    except (TypeError, ValueError):
        return QColor(default)


def _canvas(size: QSize, dpr: float) -> tuple[QImage, QPainter, int, int]:
    """An image for a window of `size` with the margin of its shadow, a painter that draws
    at `SCALE` times the size, and the window's width and height in what the painter draws."""
    image = blank(QSize(size.width() + 2 * MARGIN, size.height() + 2 * MARGIN), dpr)
    painter = QPainter(image)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing
        | QPainter.RenderHint.SmoothPixmapTransform
        | QPainter.RenderHint.TextAntialiasing
    )
    painter.translate(MARGIN, MARGIN)
    painter.scale(SCALE, SCALE)
    return image, painter, round(size.width() / SCALE), round(size.height() / SCALE)


def _title(painter: QPainter, rect: QRectF, caption: str) -> None:
    """The caption centered in `rect`, cut off with "..." when it does not fit."""
    if rect.width() > 4:
        text = QFontMetricsF(painter.font()).elidedText(caption, Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def compose_svg(folder: Path, size: QSize, dpr: float, active: bool, colors, caption: str) -> QImage:
    """An Aurorae SVG theme drawn from its nine pieces and its buttons, with the frame
    of `size` and a margin around it; a null image when the theme cannot be read. It is
    close to what the decoration plugin draws, not the same."""
    renderer = next(
        (r for ext in (".svg", ".svgz") if (folder / f"decoration{ext}").is_file()
         for r in [load_svg(folder / f"decoration{ext}")]),
        None,
    )  # fmt: skip
    if renderer is None:
        return QImage()
    sections = read_ini(folder / f"{folder.name}rc")
    layout, general = sections.get("Layout", {}), sections.get("General", {})
    left, right, bottom = (_number(layout, key, 1) for key in ("BorderLeft", "BorderRight", "BorderBottom"))
    edge_top, edge_bottom = _number(layout, "TitleEdgeTop", 0), _number(layout, "TitleEdgeBottom", 0)
    title_height = _number(layout, "TitleHeight", 20)
    top = edge_top + title_height + edge_bottom
    image, painter, width, height = _canvas(size, dpr)
    prefix = "decoration-" + ("" if active else "inactive-")

    def piece(name: str, rect: QRectF) -> None:
        for candidate in (prefix + name, "decoration-" + name):
            if renderer.elementExists(candidate):
                renderer.render(painter, candidate, rect)
                return

    piece("center", QRectF(left, top, width - left - right, height - top - bottom))
    piece("top", QRectF(left, 0, width - left - right, top))
    piece("bottom", QRectF(left, height - bottom, width - left - right, bottom))
    piece("left", QRectF(0, top, left, height - top - bottom))
    piece("right", QRectF(width - right, top, right, height - top - bottom))
    piece("topleft", QRectF(0, 0, left, top))
    piece("topright", QRectF(width - right, 0, right, top))
    piece("bottomleft", QRectF(0, height - bottom, left, bottom))
    piece("bottomright", QRectF(width - right, height - bottom, right, bottom))
    painter.fillRect(
        QRectF(left, top, width - left - right, height - top - bottom),
        QColor(_colors.complete(colors)["window"]),
    )
    button_w = _number(layout, "ButtonWidth", 16)
    button_h = _number(layout, "ButtonHeight", 16)
    spacing = _number(layout, "ButtonSpacing", 2)
    button_y = edge_top + _number(layout, "ButtonMarginTop", 0)
    state = "active-center" if active else "inactive-center"

    def buttons(letters: str, x: float, step: int) -> float:
        """Draws the buttons from `x` in direction `step`; returns where the next one would go."""
        for letter in letters:
            name = BUTTON_FILES.get(letter)
            icon = load_svg(folder / f"{name}.svg") if name else None
            if icon is None:
                continue
            element = state if icon.elementExists(state) else "active-center"
            if icon.elementExists(element):
                icon.render(
                    painter, element, QRectF(x if step > 0 else x - button_w, button_y, button_w, button_h)
                )
            x += step * (button_w + spacing)
        return x

    start = buttons(general.get("LeftButtons", LEFT_BUTTONS), left + _number(layout, "TitleEdgeLeft", 4), 1)
    end = buttons(RIGHT_BUTTONS[::-1], width - right - _number(layout, "TitleEdgeRight", 4), -1)
    font = QFont()
    font.setPixelSize(max(8, title_height - 3))
    painter.setFont(font)
    key = "ActiveTextColor" if active else "InactiveTextColor"
    painter.setPen(_rgb(general.get(key, ""), "#dddddd" if active else "#999999"))
    _title(painter, QRectF(start, edge_top, end - start, title_height), caption)
    painter.end()
    return image


def plain_window(size: QSize, dpr: float, active: bool, colors, caption: str) -> QImage:
    """A neutral window with a title bar, for a decoration that cannot be drawn."""
    c = _colors.complete(colors)
    image, painter, width, height = _canvas(size, dpr)
    frame = QRectF(0, 0, width, height)
    reach = round(MARGIN / SCALE)
    for grow in range(reach, 0, -2):  # a soft shadow
        shadow = QColor(0, 0, 0, 5 + (reach - grow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawRoundedRect(frame.adjusted(-grow, -grow + 3, grow, grow + 3), 5 + grow, 5 + grow)
    painter.setBrush(QColor(c["window"]))
    painter.setPen(QColor(0, 0, 0, 60))
    painter.drawRoundedRect(frame.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
    bar = QRectF(1, 1, width - 2, 26)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(c["header"] if active else c["window"]))
    painter.drawRoundedRect(bar, 4, 4)
    painter.drawRect(bar.adjusted(0, 10, 0, 0))
    text = QColor(c["text"])
    if not active:
        text.setAlpha(150)
    painter.setPen(text)
    font = QFont()
    font.setPixelSize(12)
    painter.setFont(font)
    _title(painter, QRectF(8, 1, width - 62, 26), caption)
    painter.setPen(Qt.PenStyle.NoPen)
    for number in range(3):  # minimize, maximize, close
        color = QColor(c["negative"] if number == 2 else c["text_muted"])
        color.setAlpha(255 if active else 120)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(width - 14 - number * 16, 14), 4.5, 4.5)
    painter.end()
    return image


def frame_size(size: QSize) -> QSize:
    """The size of one window of the pair inside a thumbnail of `size`."""
    return QSize(round(size.width() * 0.66), round(size.height() * 0.68))


def fade(piece: QImage, margin: int = MARGIN) -> QImage:
    """`piece` with its outer margin faded out, so that a shadow that was cut off has no hard edge."""
    ratio = piece.devicePixelRatio()
    width, height = piece.width() / ratio, piece.height() / ratio
    out = QImage(piece)
    painter = QPainter(out)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    for end, vertical in ((width, False), (height, True)):
        gradient = QLinearGradient(0, 0, 0, end) if vertical else QLinearGradient(0, 0, end, 0)
        step = margin / end
        for position, alpha in ((0, 0), (step, 255), (1 - step, 255), (1, 0)):
            gradient.setColorAt(position, QColor(0, 0, 0, alpha))
        painter.fillRect(QRectF(0, 0, width, height), QBrush(gradient))
    painter.end()
    return out


def pair(inactive: QImage, active: QImage, size: QSize, dpr: float) -> QImage:
    """The two windows together: the inactive one behind at the top left, the active one in front."""
    image = blank(size, dpr)
    frame = frame_size(size)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(QPointF(INSET - MARGIN, 8 - MARGIN), fade(inactive))
    painter.drawImage(
        QPointF(
            size.width() - INSET - frame.width() - MARGIN, size.height() - INSET - frame.height() - MARGIN
        ),
        active,
    )
    painter.end()
    return fade(image, INSET - 2)  # shadows end softly at the edge of the picture


class Decorations(Kind):
    key = "decoration"
    scheme_dependent = True

    def __init__(self):
        self._lock = threading.Lock()
        self._batches: dict[tuple, dict[str, QImage]] = {}
        self._tried = 0.0

    @property
    def title(self) -> str:
        return str(translate("pickers", "Window Decorations"))

    def items(self) -> list[Item]:
        try:
            return list_decorations()
        except Exception:
            return []

    def thumbnail(self, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
        try:
            drawn = self._batch(size, dpr, colors).get(item.id)
            if drawn is not None:
                return drawn
            return self._fallback(item, size, dpr, colors)
        except Exception:
            return QImage()

    def _fallback(self, item: Item, size: QSize, dpr: float, colors) -> QImage:
        frame, caption = frame_size(size), str(translate("pickers", "Window"))
        pieces = []
        for active in (False, True):
            piece = QImage()
            if item.extra.get("kind") == "svg" and item.path is not None:
                piece = compose_svg(Path(item.path), frame, dpr, active, colors, caption)
            if piece.isNull():
                piece = plain_window(frame, dpr, active, colors, caption)
            pieces.append(piece)
        return pair(pieces[0], pieces[1], size, dpr)

    def _batch(self, size: QSize, dpr: float, colors) -> dict[str, QImage]:
        """What one helper run drew for every decoration, made once per size, scale and colors."""
        key = (size.width(), size.height(), dpr, tuple(sorted(_colors.complete(colors).items())))
        with self._lock:
            tried = self._batches.get(key)
            if tried is None or (not tried and time.monotonic() - self._tried > RETRY):
                self._batches = {key: self._run_helper(size, dpr, colors)}
                self._tried = time.monotonic()
            return self._batches[key]

    def _run_helper(self, size: QSize, dpr: float, colors) -> dict[str, QImage]:
        items = self.items()
        frame = frame_size(size)
        spec = {
            "frame": [frame.width(), frame.height()],
            "dpr": dpr,
            "scale": SCALE,
            "window_color": _colors.complete(colors)["window"],
            "caption": str(translate("pickers", "Window")),
            "icon": "applications-system",
            "icon_theme": "breeze",
            "items": [
                {"key": str(number), "plugin": item.extra["library"], "theme": item.extra["theme"]}
                for number, item in enumerate(items)
            ],
        }
        drawn: dict[str, QImage] = {}
        if not items:
            return drawn
        with _process.run("decorations", spec, _colors.kdeglobals(colors)) as (out, _code):
            if out is None:
                return drawn
            for number, item in enumerate(items):
                inactive = QImage(str(out / f"{number}-inactive.png"))
                active = QImage(str(out / f"{number}-active.png"))
                if inactive.isNull() or active.isNull():
                    continue
                inactive.setDevicePixelRatio(dpr)
                active.setDevicePixelRatio(dpr)
                drawn[item.id] = pair(inactive, active, size, dpr)
        return drawn


__all__ = ["Decorations", "list_decorations", "compose_svg", "plain_window"]
