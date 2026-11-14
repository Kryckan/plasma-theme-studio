# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What is already on the system: installed color schemes and saved themes."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from . import paths, safefile
from .generators.base import MARKER
from .messages import translate
from .model.color import Color
from .model.theme import FIELD_BY_ID, MAX_NAME_LENGTH, Theme, ThemeError

# Theme color -> where to look for it in a color scheme, best source first.
_SOURCES = {
    "accent": (("Colors:Selection", "BackgroundNormal"), ("Colors:Window", "DecorationFocus")),
    "window": (("Colors:Window", "BackgroundNormal"),),
    "view": (("Colors:View", "BackgroundNormal"),),
    "button": (("Colors:Button", "BackgroundNormal"),),
    "header": (("Colors:Header", "BackgroundNormal"), ("WM", "activeBackground"),
               ("Colors:Window", "BackgroundNormal")),
    "text": (("Colors:Window", "ForegroundNormal"), ("Colors:View", "ForegroundNormal")),
    "text_muted": (("Colors:Window", "ForegroundInactive"), ("Colors:View", "ForegroundInactive")),
    "link": (("Colors:View", "ForegroundLink"), ("Colors:Window", "ForegroundLink")),
    "visited": (("Colors:View", "ForegroundVisited"), ("Colors:Window", "ForegroundVisited")),
    "negative": (("Colors:View", "ForegroundNegative"), ("Colors:Window", "ForegroundNegative")),
    "neutral": (("Colors:View", "ForegroundNeutral"), ("Colors:Window", "ForegroundNeutral")),
    "positive": (("Colors:View", "ForegroundPositive"), ("Colors:Window", "ForegroundPositive")),
}  # fmt: skip


@dataclass(frozen=True)
class InstalledScheme:
    id: str  # the name Plasma knows it by (the file name without .colors)
    name: str
    path: Path
    in_home: bool
    made_here: bool  # written by this app
    colors: dict[str, str]  # theme color key -> hex; keys the file lacks are left out


def _parse_color(value: str) -> str | None:
    value = value.strip()
    if value.startswith("#"):
        return Color.parse(value).hex if Color.is_valid(value) else None
    parts = value.split(",")
    if len(parts) not in (3, 4):
        return None
    try:
        r, g, b = (int(part) for part in parts[:3])
    except ValueError:
        return None
    if not all(0 <= channel <= 255 for channel in (r, g, b)):
        return None
    return Color(r, g, b).hex


def read_scheme(path: Path, in_home: bool) -> InstalledScheme | None:
    data = safefile.read_regular(path)  # a pipe, a device or a huge file is no color scheme
    return parse_scheme(data, path, in_home) if data is not None else None


def parse_scheme(data: bytes, path: Path, in_home: bool) -> InstalledScheme | None:
    """The color scheme in `data` (the bytes of the file `path`); None when it is not one."""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    text = data.decode("utf-8", errors="replace")
    try:
        parser.read_string(text)
    except configparser.Error:
        return None
    colors = {}
    for key, sources in _SOURCES.items():
        for group, option in sources:
            found = _parse_color(parser.get(group, option, fallback=""))
            if found:
                colors[key] = found
                break
    if "window" not in colors or "text" not in colors:
        return None  # not a usable color scheme
    name = parser.get("General", "Name", fallback="").strip() or path.stem
    return InstalledScheme(path.stem, name, path, in_home, text.startswith(MARKER), colors)


def installed_schemes() -> list[InstalledScheme]:
    """Every color scheme Plasma can use. A scheme in the home folder hides a
    system scheme with the same file name, as it does in Plasma."""
    found: dict[str, InstalledScheme] = {}
    folders = [(paths.color_schemes_dir(), True)]
    folders += [(directory / "color-schemes", False) for directory in paths.system_data_dirs()]
    for folder, in_home in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.colors")):
            if path.stem not in found:
                scheme = read_scheme(path, in_home)
                if scheme is not None:
                    found[path.stem] = scheme
    return sorted(found.values(), key=lambda scheme: scheme.name.casefold())


def theme_from_scheme(scheme: InstalledScheme) -> Theme:
    """A new theme that starts with the colors of an installed scheme."""
    theme = Theme()
    for key, value in scheme.colors.items():
        theme.set("colors", key, value)
    name = scheme.name
    if not scheme.made_here:
        # A generated scheme must not get the file name of the one it copies.
        name = str(translate("core", "{name} Copy").format(name=name))
    try:
        theme.set("meta", "name", name[:MAX_NAME_LENGTH])
    except ThemeError:
        theme.set("meta", "name", f"{scheme.id} Copy"[:MAX_NAME_LENGTH])
    if not theme.slug:
        theme.set("meta", "name", FIELD_BY_ID[("meta", "name")].default)
    return theme


@dataclass(frozen=True)
class SavedTheme:
    path: Path
    theme: Theme


def saved_themes() -> list[SavedTheme]:
    """The theme files in the themes folder that can be read as they are."""
    folder = paths.themes_dir()
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.toml")):
        data = safefile.read_regular(path)
        if data is None:
            continue
        try:
            found.append(SavedTheme(path, Theme.from_toml(data.decode("utf-8"))))
        except (ThemeError, UnicodeDecodeError):
            continue
    return sorted(found, key=lambda saved: saved.theme.name.casefold())


def save_imported(theme: Theme) -> tuple[Theme, Path]:
    """Save a theme that came from outside in the themes folder under a name of its own:
    nothing that is saved already is overwritten, and no two themes share a color scheme name.
    A name that is taken gets a number ("Name 2"). Returns the theme as saved and its file."""
    taken = {saved.theme.slug for saved in saved_themes()}
    folder = paths.themes_dir()
    base = theme.name or FIELD_BY_ID[("meta", "name")].default
    imported, number = theme.copy(), 1
    imported.set("meta", "name", base)
    while True:
        slug = imported.slug or "theme"
        path = folder / f"{slug}.toml"
        if slug not in taken and not path.exists():
            break
        number += 1
        imported.set("meta", "name", f"{base[: MAX_NAME_LENGTH - len(str(number)) - 1]} {number}")
    imported.save(path)
    return imported, path
