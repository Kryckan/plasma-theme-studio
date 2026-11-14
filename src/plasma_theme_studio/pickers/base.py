# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What every kind of picker shares: `Item`, `Kind` and the helpers to build them.

An `Item` is one choice on a System Settings page. Its `id` is exactly the
value the desktop's configuration stores for that choice, its `name` is the
display name in the user's language, `path` is the folder or file it comes
from and `user` says that it is installed in the home folder.

A `Kind` is one page (global themes, icons, ...). A module of the package
defines a subclass and sets `key`, `title`, and implements:

- `items()`: the installed choices, sorted by name (case-insensitive), a home
  folder one winning over a system one with the same id. `unique_sorted` does
  both. A broken theme folder is skipped; nothing raises.
- `thumbnail(item, size, dpr, colors)`: a QImage of `size` (logical pixels)
  times `dpr`, or a null QImage when none can be made. `colors` is the theme's
  twelve color roles as "#rrggbb" and only matters when `scheme_dependent` is
  set. Nothing raises. `gui_thread_only` says the picture has to be made on
  the GUI thread (real widgets; `on_gui_thread(item)` can narrow that to some
  items); other kinds are made on worker threads and
  may only use QImage and QPainter, never QPixmap or widgets.

Helpers: `languages`, `localized`, `read_ini`, `read_metadata`,
`read_index_theme`, `installed`, `data_folders`, `unique_sorted`, `read_svg`,
`load_svg`, `fit_image`, `placeholder`.
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QLocale, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from .. import paths
from ..safefile import MAX_FILE, read_regular


@dataclass(frozen=True)
class Item:
    """One choice of a picker. `id` is what the desktop stores for it."""

    id: str
    name: str
    description: str = ""
    path: Path | None = None
    user: bool = False
    extra: Mapping = field(default_factory=dict)


class Kind:
    """A picker page. See the module docstring for what a subclass provides."""

    key: str = ""
    gui_thread_only: bool = False
    scheme_dependent: bool = False

    @property
    def title(self) -> str:
        """The page's name as System Settings has it, translated."""
        return self.key

    def on_gui_thread(self, item: Item) -> bool:
        """Whether the picture of `item` is made on the GUI thread; `gui_thread_only` unless
        a kind has choices that are drawn elsewhere (by a helper process)."""
        return self.gui_thread_only

    def items(self) -> list[Item]:
        return []

    def thumbnail(self, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
        return QImage()


# Names ---------------------------------------------------------------------


def languages() -> list[str]:
    """The user's languages as KDE metadata spells them, best first:
    "sv-SE" gives "sv_SE" then "sv"."""
    found: list[str] = []
    for tag in QLocale().uiLanguages():
        parts = tag.replace("_", "-").split("-")
        for candidate in ("_".join(parts), parts[0]):
            if candidate and candidate not in found and candidate not in ("C", "c"):
                found.append(candidate)
    return found


def localized(values: Mapping[str, str], key: str = "Name", langs: Iterable[str] | None = None) -> str:
    """`values["Name[sv]"]` for the first language that has one, else `values["Name"]`.
    Only text counts: a number or a list in a hostile file is left out."""
    for lang in languages() if langs is None else langs:
        text = values.get(f"{key}[{lang}]")
        if text and isinstance(text, str):
            return text
    text = values.get(key, "")
    return text if isinstance(text, str) else ""


# Reading theme folders -----------------------------------------------------


def read_ini(path: Path) -> dict[str, dict[str, str]]:
    """A desktop-style file as {section: {key: value}}; {} when it cannot be read.
    Keys keep their case and their "[sv]" suffix; a repeated key keeps the last value."""
    sections: dict[str, dict[str, str]] = {}
    data = read_regular(path)
    if data is None:
        return {}
    text = data.decode("utf-8", "replace")
    current: dict[str, str] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
        elif current is not None and "=" in line:
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()
    return sections


def _metadata(name: str, description: str, ident: str, author: str) -> dict[str, str]:
    return {"name": name, "description": description, "id": ident, "author": author}


def read_metadata(folder: Path, langs: Iterable[str] | None = None) -> dict[str, str] | None:
    """The metadata of a KPackage folder (metadata.json, else metadata.desktop) as
    {name, description, id, author} with name and description localized, or None."""
    folder = Path(folder)
    try:
        raw = read_regular(folder / "metadata.json")
        plugin = json.loads(raw.decode("utf-8")).get("KPlugin") if raw is not None else None
        if isinstance(plugin, dict):
            authors = plugin.get("Authors")
            author = authors[0].get("Name", "") if isinstance(authors, list) and authors else ""
            author = author if isinstance(author, str) else ""
            return _metadata(
                localized(plugin, "Name", langs),
                localized(plugin, "Description", langs),
                plugin["Id"] if isinstance(plugin.get("Id"), str) else "",
                str(author),
            )
    except (ValueError, AttributeError, TypeError, RecursionError):
        pass
    entry = read_ini(folder / "metadata.desktop").get("Desktop Entry")
    if entry is None:
        return None
    return _metadata(
        localized(entry, "Name", langs),
        localized(entry, "Comment", langs),
        entry.get("X-KDE-PluginInfo-Name", ""),
        entry.get("X-KDE-PluginInfo-Author", ""),
    )


def read_index_theme(folder: Path, langs: Iterable[str] | None = None) -> dict[str, str] | None:
    """The same for an icon, cursor or sound theme's index.theme (or theme.index);
    None when there is none. Hidden themes (Hidden=true) give None as well."""
    for name in ("index.theme", "theme.index"):
        sections = read_ini(Path(folder) / name)
        for section in ("Icon Theme", "Sound Theme", "Desktop Entry"):
            entry = sections.get(section)
            if entry is not None:
                if entry.get("Hidden", "").lower() == "true":
                    return None
                return _metadata(localized(entry, "Name", langs), localized(entry, "Comment", langs), "", "")
    return None


# Where themes are installed -----------------------------------------------


def data_folders(*sub: str, legacy_home: str | None = None) -> list[tuple[Path, bool]]:
    """The existing folders `<data dir>/<sub...>`, the home folder first and the
    system ones in XDG_DATA_DIRS order, each with its `user` flag. `legacy_home`
    adds a folder directly under $HOME (".icons") right after the home data folder."""
    found: list[tuple[Path, bool]] = []
    candidates = [(paths.data_home().joinpath(*sub), True)]
    if legacy_home:
        candidates.append((Path.home() / legacy_home, True))
    candidates += [(base.joinpath(*sub), False) for base in paths.system_data_dirs()]
    for folder, user in candidates:
        if folder.is_dir() and all(folder != other for other, _ in found):
            found.append((folder, user))
    return found


def installed(*sub: str, legacy_home: str | None = None) -> dict[str, tuple[Path, bool]]:
    """Theme folders by folder name as {name: (folder, user)}; when a name is in
    several data folders the first one in `data_folders` order (the home folder) wins."""
    found: dict[str, tuple[Path, bool]] = {}
    for base, user in data_folders(*sub, legacy_home=legacy_home):
        try:
            children = sorted(base.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name not in found and child.is_dir():
                found[child.name] = (child, user)
    return found


def unique_sorted(items: Iterable[Item]) -> list[Item]:
    """One item per id (an installed-in-home one beats a system one, else the
    first seen), sorted by name without regard to case."""
    chosen: dict[str, Item] = {}
    for item in items:
        old = chosen.get(item.id)
        if old is None or (item.user and not old.user):
            chosen[item.id] = item
    return sorted(chosen.values(), key=lambda item: (str(item.name).casefold(), item.id))


# Pictures ------------------------------------------------------------------


def read_svg(path: Path) -> bytes | None:
    """The bytes of a .svg or .svgz file; None when it cannot be read."""
    data = read_regular(path)
    if data is not None and data[:2] == b"\x1f\x8b":
        try:
            unpacker = zlib.decompressobj(31)
            data = unpacker.decompress(data, MAX_FILE * 8)
            if unpacker.unconsumed_tail:
                return None  # a bomb
        except zlib.error:
            return None
    return data


def load_svg(path: Path):
    """A valid QtSvg.QSvgRenderer for a .svg or .svgz file, or None. A Qt application
    must exist."""
    from PySide6.QtSvg import QSvgRenderer

    data = read_svg(path)
    if data is None:
        return None
    renderer = QSvgRenderer(data)
    return renderer if renderer.isValid() else None


def blank(size: QSize, dpr: float, color: QColor | None = None) -> QImage:
    """A transparent (or filled) image of `size` logical pixels at `dpr`."""
    image = QImage(
        max(1, round(size.width() * dpr)),
        max(1, round(size.height() * dpr)),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.setDevicePixelRatio(dpr)
    image.fill(color if color is not None else Qt.GlobalColor.transparent)
    return image


def fit_image(
    image: QImage, size: QSize, dpr: float, background: QColor | None = None, enlarge: bool = True
) -> QImage:
    """`image` scaled to fit inside `size` logical pixels at `dpr`, keeping its
    proportions and centered on a transparent (or `background`) canvas. A null
    image gives a null image."""
    if image.isNull():
        return QImage()
    out = blank(size, dpr, background)
    target = QSize(out.width(), out.height())
    scaled = image
    if enlarge or image.width() > target.width() or image.height() > target.height():
        scaled = image.scaled(
            target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    out.setDevicePixelRatio(1.0)  # paint in device pixels
    painter = QPainter(out)
    painter.drawImage(
        (target.width() - scaled.width()) // 2, (target.height() - scaled.height()) // 2, scaled
    )
    painter.end()
    out.setDevicePixelRatio(dpr)
    return out


def placeholder(size: QSize, dpr: float) -> QImage:
    """A neutral grey rounded rectangle, for choices that have no picture."""
    image = blank(size, dpr)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(128, 128, 128, 120))
    painter.setBrush(QColor(128, 128, 128, 50))
    painter.drawRoundedRect(QRectF(0.5, 0.5, size.width() - 1, size.height() - 1), 4, 4)
    painter.end()
    return image
