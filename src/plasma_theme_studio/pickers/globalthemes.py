# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Global Themes: Plasma look-and-feel packages.

A package is a folder `plasma/look-and-feel/<id>/` (the folder name is the id
Plasma stores) with a `contents/` folder and `metadata.json` or the older
`metadata.desktop`. Its picture is `contents/previews/preview.png`. What the
package sets is in `contents/defaults`; `defaults(item)` reads it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader

from ..messages import translate
from .base import Item, Kind, fit_image, installed, placeholder, read_ini, read_metadata, unique_sorted

_PREVIEWS = ("preview.png", "preview.jpg")
_FULLSCREEN = ("fullscreenpreview.jpg", "fullscreenpreview.png")


def package_items(subfolder: str = "") -> list[Item]:
    """The look-and-feel packages (those with a `contents` folder and metadata),
    each with `extra["splash"]` saying whether it has a splash screen."""
    found = []
    for folder_id, (folder, user) in installed("plasma", "look-and-feel").items():
        try:
            if not (folder / "contents").is_dir() or (
                subfolder and not (folder / "contents" / subfolder).is_dir()
            ):
                continue
            meta = read_metadata(folder)
        except Exception:
            continue
        if meta is None:
            continue
        found.append(
            Item(
                folder_id,
                meta["name"] or folder_id,
                meta["description"],
                folder,
                user,
                {"author": meta["author"], "splash": (folder / "contents" / "splash").is_dir()},
            )
        )
    return unique_sorted(found)


def first_picture(folder: Path, names: tuple[str, ...]) -> Path | None:
    return next((folder / name for name in names if (folder / name).is_file()), None)


def read_scaled(path: Path, size: QSize, dpr: float) -> QImage:
    """The picture at `path` shrunk while it is read (large screenshots are cheap
    this way) and fitted into `size` at `dpr`; null when it cannot be read."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    source = reader.size()
    target = QSize(max(1, round(size.width() * dpr)), max(1, round(size.height() * dpr)))
    if source.isValid() and (source.width() > target.width() or source.height() > target.height()):
        reader.setScaledSize(source.scaled(target, Qt.AspectRatioMode.KeepAspectRatio))
    return fit_image(reader.read(), size, dpr, enlarge=False)


def preview(item: Item, size: QSize, dpr: float, names: tuple[str, ...]) -> QImage:
    """The first readable picture of `names` in the package's `contents/previews`,
    else a placeholder."""
    if item.path is not None:
        previews = Path(item.path) / "contents" / "previews"
        for name in names:
            if (previews / name).is_file():
                image = read_scaled(previews / name, size, dpr)
                if not image.isNull():
                    return image
    return placeholder(size, dpr)


class GlobalThemes(Kind):
    key = "global_theme"

    @property
    def title(self) -> str:
        return str(translate("core", "Global Theme"))

    def items(self) -> list[Item]:
        return package_items()

    def thumbnail(self, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
        return preview(item, size, dpr, _PREVIEWS + _FULLSCREEN)


# What a package sets -----------------------------------------------------

_SIMPLE = {
    ("kdeglobals", "General", "ColorScheme"): "color_scheme",
    ("kdeglobals", "KDE", "widgetStyle"): "app_style",
    ("plasmarc", "Theme", "name"): "plasma_style",
    ("kdeglobals", "Icons", "Theme"): "icons",
    ("kcminputrc", "Mouse", "cursorTheme"): "cursors",
    ("ksplashrc", "KSplash", "Theme"): "splash",
}
_FONTS = {
    ("kdeglobals", "General", "font"): "general",
    ("kdeglobals", "General", "fixed"): "fixed",
    ("kdeglobals", "General", "smallestReadableFont"): "small",
    ("kdeglobals", "General", "toolBarFont"): "toolbar",
    ("kdeglobals", "General", "menuFont"): "menu",
    ("kdeglobals", "WM", "activeFont"): "window_title",
}


def resolve(value: str, items: list[Item]) -> Item | None:
    """The item of a picker list that a package's value means, or None when it is not
    installed. Packages spell values loosely: "oxygen" for the style "Oxygen", the scheme by its
    name ("Nordic-Darker") where the id is the file name, the old Aurorae library
    ("org.kde.kwin.aurorae:...") for the one this Plasma writes ("org.kde.kwin.aurorae.v2:...")."""
    wanted = {value.casefold()}
    for old, new in (("org.kde.kwin.aurorae:", "org.kde.kwin.aurorae.v2:"),):
        if value.startswith(old):
            wanted.add((new + value[len(old) :]).casefold())
        elif value.startswith(new):
            wanted.add((old + value[len(new) :]).casefold())
    for field in ("id", "name"):
        for item in items:
            if str(getattr(item, field)).casefold() in wanted:
                return item
    return None


# What KWin takes when a package names the library only.
DEFAULT_THEMES = {"org.kde.breeze": "Breeze", "org.kde.oxygen": "Oxygen"}


def defaults(item: Item) -> dict:
    """The parts a Global Theme sets, from its `contents/defaults`, under this
    app's part ids: `color_scheme`, `app_style`, `plasma_style`, `decoration`
    ("<library>:<theme>"), `icons`, `cursors`, `cursor_size` (int), `fonts`
    (a dict: general, fixed, small, toolbar, menu, window_title) and `splash`.
    Only what the package gives is in the result; other keys are ignored and
    names are not checked against what is installed."""
    if item.path is None:
        return {}
    given: dict[tuple[str, ...], str] = {}
    for header, entries in read_ini(Path(item.path) / "contents" / "defaults").items():
        parts = tuple(header.split("]["))
        for key, value in entries.items():
            if value:
                given[(*parts, key)] = value
    found: dict = {}
    for where, part in _SIMPLE.items():
        if where in given:
            found[part] = given[where]
    library = given.get(("kwinrc", "org.kde.kdecoration2", "library"), "")
    theme = given.get(("kwinrc", "org.kde.kdecoration2", "theme"), "")
    if library:
        theme = theme or DEFAULT_THEMES.get(library, "")
        if theme:  # a library without a theme name and without a default gives nothing
            found["decoration"] = f"{library}:{theme}"
    try:
        found["cursor_size"] = int(given[("kcminputrc", "Mouse", "cursorSize")])
    except (KeyError, ValueError):
        pass
    fonts = {name: given[where] for where, name in _FONTS.items() if where in given}
    if fonts:
        found["fonts"] = fonts
    return found
