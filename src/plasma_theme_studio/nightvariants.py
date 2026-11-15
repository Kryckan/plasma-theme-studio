# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The two Global Themes Plasma switches between at night, and the one that is in use.

With "Switch to Dark Mode at Night" on, Plasma 6.8 applies `DefaultLightLookAndFeel` by day and
`DefaultDarkLookAndFeel` by night (both in `[KDE]` of kdeglobals; the defaults are Breeze and
Breeze Dark). `LookAndFeelPackage` names the one that is in use now. All three are the keys the
Global Theme page of System Settings writes.
"""

from __future__ import annotations

from .desktopparts import Part, _check_text
from .messages import translate

KEYS = {
    "light": ("kdeglobals", ["KDE"], "DefaultLightLookAndFeel"),
    "dark": ("kdeglobals", ["KDE"], "DefaultDarkLookAndFeel"),
    "package": ("kdeglobals", ["KDE"], "LookAndFeelPackage"),
}


class NightVariants(Part):
    """The Global Themes of the automatic switch. `current` and `apply` take (light, dark, in use)."""

    key = "night_variants"
    title = translate("core", "Light and dark theme")
    settings = KEYS
    notify = True  # the settings daemon of Plasma watches the keys

    def current(self, runner) -> tuple[str, str, str]:
        return tuple(self._get(runner, name) for name in ("light", "dark", "package"))

    def validate(self, value) -> None:
        for package in value:
            _check_text(package, str(translate("core", "The Global Theme")))

    def apply(self, value, runner) -> None:
        self.validate(value)
        for name, package in zip(("light", "dark", "package"), value, strict=True):
            self._put(runner, name, package)
