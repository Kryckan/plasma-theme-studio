# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Which image is the desktop wallpaper, and which wallpapers are installed.

Everything is read from the files Plasma keeps (never written, plasmashell is never asked), so
a wallpaper that was changed a moment ago may not show up until Plasma has saved its settings.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import paths, safefile
from .messages import Msg, translate

IMAGE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg", ".svgz", ".avif", ".jxl", ".tif", ".tiff"}
)
APPLETSRC = "plasma-org.kde.plasma.desktop-appletsrc"
DESKTOP_PLUGINS = ("org.kde.plasma.folder", "org.kde.desktopcontainment")  # panels are org.kde.panel
MAX_CONFIG_BYTES = 4_000_000
MAX_LISTED = 500  # images listed from one folder


@dataclass(frozen=True)
class WallpaperSource:
    """The wallpaper of one screen: the image to take colors from, or why there is none."""

    path: Path | None
    plugin: str | None = None  # org.kde.image, org.kde.slideshow, org.kde.color, ...
    value: str | None = None  # the setting as Plasma has it (the Image= value, the color)
    reason: Msg | None = None  # in plain words, when `path` is None


@dataclass(frozen=True)
class InstalledWallpaper:
    name: str
    path: Path  # the image to use (the best size of a package)
    folder: Path  # the package folder, or the image file itself
    is_package: bool


def _is_image(path: Path) -> bool:
    try:
        return path.suffix.lower() in IMAGE_SUFFIXES and path.is_file()
    except OSError:
        return False


def _images_in(folder: Path) -> list[Path]:
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        return []
    return [p for p in entries if _is_image(p)][:MAX_LISTED]


def _size_of(path: Path) -> tuple[int, int]:
    match = re.match(r"(\d+)x(\d+)", path.stem)
    return (int(match[1]), int(match[2])) if match else (0, 0)


def _aspect_error(path: Path) -> float:
    width, height = _size_of(path)
    return abs(math.log((width / height) / (16 / 9))) if width and height else 9.0


def _best_size(files: list[Path]) -> Path:
    """Closest to a landscape 16:9 screen (a package may hold portrait sizes), then the
    smallest one that is at least 1920 px wide, else the largest."""
    best = min(_aspect_error(p) for p in files)
    pool = [p for p in files if _aspect_error(p) - best < 0.15]
    big = [p for p in pool if _size_of(p)[0] >= 1920]
    return min(big, key=lambda p: _size_of(p)[0]) if big else max(pool, key=lambda p: _size_of(p)[0])


def package_image(folder: Path, dark: bool = False, fragment: str = "") -> Path | None:
    """The image of a wallpaper package (`contents/images`, and `contents/images_dark` for a dark
    color scheme). A `#dark` or `#light` fragment forces the variant."""
    want_dark = dark if fragment in ("", "#day-night") else fragment == "#dark"
    for sub in ("images_dark", "images") if want_dark else ("images", "images_dark"):
        files = [p for p in _images_in(folder / "contents" / sub) if _size_of(p) != (0, 0)] or _images_in(
            folder / "contents" / sub
        )
        if files:
            return _best_size(files)
    return None


def _data_dirs() -> list[Path]:
    return [paths.data_home(), *paths.system_data_dirs()]


def _local_path(value: str) -> Path:
    return Path(unquote(urlparse(value).path)) if value.startswith("file:") else Path(value)


def resolve_value(value: str, dark: bool = False) -> Path | None:
    """An Image= value as an image file. It may be a file URL (percent-encoded), a plain path,
    a package folder or the bare name of an installed package, each with a fragment such as
    `#dark`; a folder of plain images gives its first image."""
    value = value.strip()
    fragment = ""
    if "#" in value:
        value, _, rest = value.rpartition("#")
        fragment = "#" + rest
    if not value:
        return None
    if value.startswith(("file:", "/")):
        path = _local_path(value)
    else:
        path = next(
            (b / "wallpapers" / value for b in _data_dirs() if (b / "wallpapers" / value).is_dir()), None
        )
        if path is None:
            return None
    try:
        if path.is_dir():
            return package_image(path, dark, fragment) or next(iter(_images_in(path)), None)
    except OSError:
        return None
    return path if _is_image(path) else None


def _read_config(path: Path) -> dict[tuple[str, ...], dict[str, str]] | None:
    try:
        data = safefile.read_regular(path, MAX_CONFIG_BYTES)
        if data is None:
            return None
        return safefile.parse_config(data.decode("utf-8", errors="replace"))
    except OSError:
        return None


def _global_theme_wallpaper() -> str | None:
    """An empty Image= means the wallpaper of the Global Theme in use."""
    package = "org.kde.breeze.desktop"
    given = safefile.read_regular(paths.config_home() / "kdedefaults" / "package", 4096)
    package = given.decode("utf-8", "replace").strip() or package if given is not None else package
    for base in _data_dirs():
        groups = _read_config(base / "plasma/look-and-feel" / package / "contents/defaults")
        if groups is not None:
            return groups.get(("Wallpaper",), {}).get("Image") or None
    return None


def _running_activity() -> str | None:
    groups = _read_config(paths.config_home() / "kactivitymanagerdrc") or {}
    current = groups.get(("main",), {}).get("currentActivity")
    if current:
        return current
    known = groups.get(("activities",), {})
    return next(iter(known)) if len(known) == 1 else None


def _slide(general: dict[str, str], dark: bool) -> Path | None:
    unchecked = {_local_path(p) for p in general.get("UncheckedSlides", "").split(",") if p}
    for entry in (p for p in general.get("SlidePaths", "").split(",") if p):
        base = _local_path(entry)
        for image in [base] if _is_image(base) else _images_in(base):
            if image not in unchecked:
                return image
        found = package_image(base, dark) if base.is_dir() else None
        if found:
            return found
    return None


def wallpaper_source(
    screen: int = 0, activity: str | None = None, dark: bool = False, config: Path | None = None
) -> WallpaperSource:
    """The wallpaper of `screen` (0 is the primary one) in `activity` (default: the running one,
    as far as the files tell). `dark` chooses the dark image of a package that has one."""
    groups = _read_config(config or paths.config_home() / APPLETSRC)
    if groups is None:
        return WallpaperSource(None, None, None, translate("core", "The desktop settings cannot be read."))
    activity = activity or _running_activity()
    found = []
    for key, values in groups.items():
        if len(key) != 2 or key[0] != "Containments" or values.get("plugin") not in DESKTOP_PLUGINS:
            continue
        try:
            if int(values.get("lastScreen", "-1")) != screen:
                continue
            number = int(key[1])
        except ValueError:
            continue
        found.append((0 if activity and values.get("activityId") == activity else 1, number, key[1], values))
    if not found:
        return WallpaperSource(
            None, None, None, translate("core", "No desktop wallpaper is set for this screen.")
        )
    _, _, name, containment = min(found, key=lambda f: f[:2])
    plugin = containment.get("wallpaperplugin") or "org.kde.image"
    general = groups.get(("Containments", name, "Wallpaper", plugin, "General"), {})
    if plugin in ("org.kde.image", "org.kde.tiled"):
        value = general.get("Image") or _global_theme_wallpaper()
        path = resolve_value(value, dark) if value else None
        if path is None:
            return WallpaperSource(
                None, plugin, value, translate("core", "The wallpaper image cannot be found.")
            )
        return WallpaperSource(path, plugin, value)
    if plugin == "org.kde.slideshow":
        path = _slide(general, dark)
        if path is None:
            return WallpaperSource(
                None, plugin, None, translate("core", "The slideshow has no images the app can read.")
            )
        return WallpaperSource(path, plugin, general.get("SlidePaths"))
    if plugin == "org.kde.color":
        return WallpaperSource(
            None,
            plugin,
            general.get("Color"),
            translate("core", "The wallpaper is a plain color, not an image."),
        )
    if plugin == "org.kde.potd":
        cache = paths.cache_home() / "plasma_engine_potd"
        files = _images_in(cache)
        if files:
            try:
                return WallpaperSource(max(files, key=lambda p: p.stat().st_mtime), plugin)
            except OSError:
                pass
        return WallpaperSource(
            None, plugin, None, translate("core", "The picture of the day has not been downloaded yet.")
        )
    return WallpaperSource(None, plugin, None, translate("core", "This kind of wallpaper has no image."))


def current_wallpaper(**kwargs) -> Path | None:
    """The image file of the primary screen's wallpaper, or None."""
    return wallpaper_source(**kwargs).path


def _package_name(folder: Path) -> str:
    try:
        raw = safefile.read_regular(folder / "metadata.json")
        data = json.loads(raw.decode("utf-8")) if raw is not None else {}
        name = data["KPlugin"]["Name"]
        if isinstance(name, str) and name.strip():
            return name.strip()
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        pass
    return folder.name


def installed_wallpapers() -> list[InstalledWallpaper]:
    """The wallpaper packages and loose images in the wallpaper folders, the home folder's
    first. A package in the home folder hides a system package of the same folder name."""
    found: dict[str, InstalledWallpaper] = {}
    for base in _data_dirs():
        folder = base / "wallpapers"
        try:
            entries = sorted(folder.iterdir(), key=lambda p: p.name.casefold())[:MAX_LISTED]
        except OSError:
            continue
        for entry in entries:
            if entry.name in found:
                continue
            try:
                if entry.is_dir():
                    image = package_image(entry)
                    if image:
                        found[entry.name] = InstalledWallpaper(_package_name(entry), image, entry, True)
                elif _is_image(entry):
                    found[entry.name] = InstalledWallpaper(entry.stem, entry, entry, False)
            except OSError:
                continue
    return sorted(found.values(), key=lambda w: w.name.casefold())
