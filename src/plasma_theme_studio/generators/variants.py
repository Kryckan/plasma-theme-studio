# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The light and dark variant of a theme, for Plasma's own switch at night.

With "Switch to Dark Mode at Night" on, Plasma 6.8 applies a Global Theme by day and another at
night (`DefaultLightLookAndFeel` and `DefaultDarkLookAndFeel` in kdeglobals, which System Settings
writes too). So a theme with both variants installs two small Global Themes of its own. Each one
only names the color scheme of its variant (its `contents/defaults`), so the switch changes the
colors and what follows the color scheme, and nothing else.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import paths
from ..messages import Msg, translate
from ..model.theme import Theme
from ..model.variants import DARK, LIGHT, VARIANTS
from .base import JSON_MARKER, MARKER, Generator, PlannedFile, made_here
from .colorscheme import ColorSchemeGenerator, scheme_name

PACKAGE_DIR = "plasma/look-and-feel"
NIGHT_INFIX = ".night."


def _part():
    # nightvariants needs desktopparts, which needs the generators.
    from ..nightvariants import NightVariants

    return NightVariants()


def package_id(theme: Theme, variant: str) -> str:
    from ..globaltheme import PACKAGE_PREFIX

    return f"{PACKAGE_PREFIX}{theme.slug.lower()}{NIGHT_INFIX}{variant}"


def of_variant(theme: Theme, variant: str) -> Theme:
    """A copy of the theme that shows `variant`."""
    shown = theme.copy()
    shown.show(variant)
    return shown


def variant_on_desktop(theme: Theme, runner) -> str | None:
    """The variant of the theme whose color scheme the desktop uses now, or None."""
    from .colorscheme import current_scheme

    scheme = current_scheme(runner)
    if not scheme:
        return None
    for variant in theme.variants:
        if scheme == scheme_name(of_variant(theme, variant)):
            return variant
    return None


def stays_until_next_apply(theme: Theme) -> list[str]:
    """The parts of the theme that bake the colors of the variant in, so that Plasma's own switch does
    not change them. The colors and the panel and popup style (which use the color scheme) follow it."""
    stays = []
    if theme.get("window", "decoration") == "generated":
        stays.append(str(translate("core", "the window frame")))
    if theme.get("apps", "style") == "generated":
        stays.append(str(translate("core", "the application style")))
    if theme.get("gtk", "style") == "generated":
        stays.append(str(translate("core", "the GTK files")))
    if theme.get("rofi", "style") == "generated":
        stays.append(str(translate("core", "the Rofi theme")))
    return stays


def _metadata(theme: Theme, variant: str, pid: str) -> str:
    title = f"{theme.name} {'Dark' if variant == DARK else 'Light'}"
    data = {
        "X-Generated-By": "Plasma Theme Studio",  # first key: the marker that made_here() looks for
        "KPackageStructure": "Plasma/LookAndFeel",
        "KPlugin": {
            "Authors": [{"Name": "Plasma Theme Studio"}],
            "Description": "The colors of one variant of a theme, for the switch at night",
            "Id": pid,
            "License": "GPL-3.0-or-later",
            "Name": title,
            "Version": "1.0",
        },
        "X-Plasma-APIVersion": "2",
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _defaults(scheme: str) -> str:
    return "\n".join([MARKER, "", "[kdeglobals][General]", f"ColorScheme={scheme}", ""])


def stale_packages(keep: set[str]) -> list[Path]:
    """The night packages made here, with their files, except the ones named in `keep`."""
    root = paths.data_home() / PACKAGE_DIR
    stale: list[Path] = []
    if not root.is_dir():
        return stale
    for package in sorted(root.glob(f"*{NIGHT_INFIX}*")):
        if package.name in keep or package.is_symlink() or not made_here(package / "metadata.json"):
            continue
        stale += [item for item in sorted(package.rglob("*")) if item.is_file() and made_here(item)]
        stale += [item for item in sorted(package.rglob("*"), reverse=True) if item.is_dir()]
        stale.append(package)
    return stale


class NightVariantsTarget(Generator):
    id = "night_variants"
    title = translate("core", "Light and dark theme")
    sections = ("colors", "desktop")

    @property
    def part(self):
        return _part()

    def wanted(self, theme: Theme) -> bool:
        return theme.has_both and theme.get("desktop", "dark_at_night") is True

    def _expected(self, theme: Theme) -> tuple[str, str, str]:
        light, dark = package_id(theme, LIGHT), package_id(theme, DARK)
        return light, dark, light if theme.shown_variant == LIGHT else dark

    def notes(self, theme: Theme) -> list[Msg]:
        if not self.wanted(theme):
            return []
        found = [
            translate(
                "core",
                "Plasma switches between the light and the dark variant by itself. The colors and the "
                "panel and popup style follow the switch.",
            )
        ]
        stays = stays_until_next_apply(theme)
        if stays:
            found.append(
                translate("core", "{stays} keep the variant of the last Apply until the next one.").format(
                    stays=", ".join(stays)
                )
            )
        return found

    def unavailable_reason(self, runner) -> Msg | None:
        reason = self.part.available(runner)
        if reason is None:
            return None
        return translate("core", "{part} cannot be changed. {reason}").format(
            part=str(self.title), reason=str(reason)
        )

    def files(self, theme: Theme) -> list[PlannedFile]:
        if not self.wanted(theme):
            return []
        planned: list[PlannedFile] = []
        root = paths.data_home() / PACKAGE_DIR
        shown = theme.shown_variant
        for variant in VARIANTS:
            own = of_variant(theme, variant)
            if variant != shown:  # the shown variant's scheme is the color scheme target's file
                planned += ColorSchemeGenerator().files(own)
            pid = package_id(theme, variant)
            planned.append(
                PlannedFile(root / pid / "metadata.json", _metadata(theme, variant, pid), JSON_MARKER)
            )
            planned.append(PlannedFile(root / pid / "contents" / "defaults", _defaults(scheme_name(own))))
        return planned

    def stale_files(self, theme: Theme) -> list[Path]:
        if not self.wanted(theme):
            return []
        return stale_packages({package_id(theme, variant) for variant in VARIANTS})

    def changed_settings(self, theme: Theme) -> list[Msg]:
        if not self.wanted(theme):
            return []
        return [
            translate(
                "core",
                "the Global Themes of the switch at night: {light} by day, {dark} at night (kdeglobals)",
            ).format(light=package_id(theme, LIGHT), dark=package_id(theme, DARK))
        ]

    def problems(self, theme: Theme) -> list[Msg]:
        return []

    def is_active(self, theme: Theme, runner) -> bool:
        return not self.wanted(theme) or tuple(self.part.current(runner)) == self._expected(theme)

    def capture_settings(self, runner) -> dict:
        return self.part.capture(runner)

    def reload(self, theme: Theme, runner) -> None:
        self.part.apply(self._expected(theme), runner)

    def restore_settings(self, settings: dict, runner) -> None:
        self.part.restore(settings, runner)
