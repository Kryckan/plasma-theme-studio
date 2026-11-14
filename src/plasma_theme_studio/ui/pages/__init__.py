# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The pages of the window, in the order of the side bar.

`PAGES` is the registry: one `PageSpec` per page, with the module and class that build it. A page is
imported and made by `create(key, window)` the first time it is shown, so the window opens without
loading what it does not show. `GROUPS` is the captions of the side bar and the keys under each.

An entry is of kind "page" (edits a part of the theme) or "link": a part this app does not edit, with
an explanation and a button that opens the matching System Settings module (`PageSpec.link`, a key of
`desktopparts.MODULES`; the page class is a `base.LinkPage`).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from ...messages import translate


@dataclass(frozen=True)
class PageSpec:
    key: str
    title: object  # a lazy message: the page's name as System Settings has it
    icon: str
    fallback: str
    module: str
    cls: str
    kind: str = "page"  # "page", or "link" for an entry that opens a System Settings module
    link: str = ""  # the module id of a "link" entry


PAGES: tuple[PageSpec, ...] = (
    PageSpec(
        "overview",
        translate("ui", "Overview"),
        "view-list-details",
        "document-properties",
        "overview",
        "OverviewPage",
    ),
    PageSpec(
        "themes",
        translate("ui", "Themes"),
        "preferences-desktop-theme-global",
        "preferences-desktop-theme",
        "themes",
        "ThemesPage",
    ),
    PageSpec(
        "colors",
        translate("ui", "Colors"),
        "preferences-desktop-color",
        "color-management",
        "colors",
        "ColorsPage",
    ),
    PageSpec("shapes", translate("ui", "Shapes"), "draw-rectangle", "shapes", "shapes", "ShapesPage"),
    PageSpec("fonts", translate("ui", "Fonts"), "preferences-desktop-font", "font", "fonts", "FontsPage"),
    PageSpec(
        "plasma_style",
        translate("ui", "Plasma Style"),
        "preferences-desktop-plasma",
        "plasma",
        "plasma_style",
        "PlasmaStylePage",
    ),
    PageSpec(
        "panel", translate("ui", "Panel"), "view-bottom-pane", "align-vertical-bottom", "panel", "PanelPage"
    ),
    PageSpec(
        "decorations",
        translate("ui", "Window Decorations"),
        "preferences-system-windows",
        "window",
        "decorations",
        "DecorationsPage",
    ),
    PageSpec(
        "icons",
        translate("ui", "Icons"),
        "preferences-desktop-icons",
        "applications-graphics",
        "icons",
        "IconsPage",
    ),
    PageSpec(
        "pointers",
        translate("ui", "Pointers"),
        "input-mouse",
        "preferences-desktop-cursors",
        "pointers",
        "PointersPage",
    ),
    PageSpec(
        "splash",
        translate("ui", "Splash Screen"),
        "preferences-desktop-splash",
        "preferences-system-splash",
        "splash",
        "SplashPage",
    ),
    PageSpec(
        "sounds",
        translate("ui", "System Sounds"),
        "preferences-desktop-sound",
        "audio-volume-high",
        "sounds",
        "SoundsPage",
    ),
    PageSpec(
        "login_screen",
        translate("ui", "Login Screen (SDDM)"),
        "preferences-system-login",
        "system-lock-screen",
        "login_screen",
        "LoginScreenPage",
        kind="link",
        link="kcm_sddm",
    ),
    PageSpec(
        "app_style",
        translate("ui", "Application Style"),
        "preferences-desktop-theme-applications",
        "applications-graphics",
        "app_style",
        "AppStylePage",
    ),
    PageSpec(
        "gtk",
        translate("ui", "GTK Apps"),
        "preferences-desktop-gtk",
        "preferences-gtk-config",
        "gtk",
        "GtkPage",
    ),
    PageSpec("rofi", translate("ui", "Rofi"), "system-run", "utilities-terminal", "rofi", "RofiPage"),
)

# The captions of the side bar and the pages under them; the first group has no caption.
GROUPS: tuple[tuple[object, tuple[str, ...]], ...] = (
    ("", ("overview",)),
    (translate("ui", "Library"), ("themes",)),
    (translate("ui", "Basics"), ("colors", "shapes", "fonts")),
    (
        translate("ui", "Desktop"),
        ("plasma_style", "panel", "decorations", "icons", "pointers", "splash", "sounds", "login_screen"),
    ),
    (translate("ui", "Apps"), ("app_style", "gtk", "rofi")),
)

SPECS = {spec.key: spec for spec in PAGES}


def title_of(key: str) -> str:
    return str(SPECS[key].title)


def create(key: str, window):
    """Make the page `key` (not built yet: the window builds it when it is first shown)."""
    spec = SPECS[key]
    module = importlib.import_module(f"{__name__}.{spec.module}")
    return getattr(module, spec.cls)(window)


# The `parts_status` keys each page follows, so that the side bar can be marked without importing the
# pages (a page class says the same in its `parts`; a test keeps the two equal).
PARTS: dict[str, tuple[str, ...]] = {
    "decorations": ("decoration", "borders"),
    "colors": ("colors",),
    "app_style": ("app_style",),
    "fonts": ("fonts",),
    "icons": ("icons",),
    "sounds": ("sounds",),
    "gtk": ("gtk",),
    "splash": ("splash",),
    "rofi": ("rofi",),
    "plasma_style": ("plasma_style",),
    "panel": ("panel",),
    "pointers": ("pointers",),
    "themes": ("night_mode",),
}


def parts_of(key: str) -> tuple[str, ...]:
    """The `parts_status` keys the page `key` follows (without importing the page)."""
    return PARTS.get(key, ())
