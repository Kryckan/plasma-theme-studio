# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The parts of System Settings' Colors & Themes that a theme names instead of generating:
installed Plasma style, application style and window decoration, border size, title bar
buttons, icons, pointer, fonts, splash screen, system sounds, and the accent color.

Each target is a thin layer over one `Part` of `desktopparts` (which knows what is installed,
how the desktop is changed and how a change is read back). The target says when the theme wants
it and compares the theme with what the desktop uses. A thing that is installed is never
wanted together with its generated variant: the generated variants are wanted only for
"generated", these only for "installed", and an installed one removes what the generated one left.
"""

from __future__ import annotations

from pathlib import Path

from .. import kconfig
from ..messages import Msg, translate
from ..model.parts import FontSpec
from ..model.theme import FONT_KEYS, Theme
from .base import ApplyError, Generator, PlannedFile
from .colorscheme import installed_scheme_of
from .kvantum import selected_theme, selection_file, stale_themes
from .plasmastyle import stale_packages
from .windowframe import AURORAE_LIBRARY, AURORAE_THEME_PREFIX, stale_frames

# The role of a font of the theme in `desktopparts.Fonts`.
FONT_ROLES = {
    "general": "font",
    "fixed": "fixed",
    "small": "small",
    "toolbar": "toolbar",
    "menu": "menu",
    "window_title": "title",
}


def _part(key: str):
    # desktopparts imports the generators, so it cannot be imported when they are.
    from ..desktopparts import PARTS

    return PARTS[key]


def shown(kind_key: str, value: str) -> str:
    """The name System Settings shows for the installed thing `value` of a picker, or the id."""
    try:
        from ..pickers import kind

        picker = kind(kind_key)
        items = picker.items() if picker else []
        for item in items:
            if item.id == value:
                return item.name
        for item in items:
            if item.id.casefold() == str(value).casefold():
                return item.name
    except Exception:  # noqa: S110 - a name that cannot be looked up is shown as it is
        pass
    return str(value)


class PartTarget(Generator):
    """A target that sets one part of the desktop to a value the theme names."""

    key = ""  # the part in `desktopparts.PARTS`
    kind = ""  # the picker that lists it, for the display name
    # The theme's choice ("installed" and so on) that asks for it; None for a value that is set when given.
    choice: tuple[str, str] | None = None

    @property
    def part(self):
        return _part(self.key)

    def value(self, theme: Theme):
        """What the part is to be set to, None when the theme leaves it alone."""
        raise NotImplementedError

    def wanted(self, theme: Theme) -> bool:
        return self.value(theme) is not None

    def files(self, theme: Theme) -> list[PlannedFile]:
        return []  # the desktop is changed, nothing is written

    def describe(self, theme: Theme) -> list[Msg]:
        """The settings of the part that are changed, in words (see `changed_settings`)."""
        raise NotImplementedError

    def changed_settings(self, theme: Theme) -> list[Msg]:
        return self.describe(theme) if self.wanted(theme) else []

    def name(self, value) -> str:
        return shown(self.kind, value) if self.kind else str(value)

    def notes(self, theme: Theme) -> list[Msg]:
        if self.choice in theme.unnamed_parts():
            return [
                translate(
                    "core", "{part} is set to an installed one, but none is chosen. It is left as it is."
                ).format(part=str(self.title))
            ]
        return []

    def problems(self, theme: Theme) -> list[Msg]:
        value = self.value(theme)
        if value is None:
            return []
        try:
            self.part.validate(value)
        except ApplyError as error:
            return [error.message]
        return []

    def unavailable_reason(self, runner) -> Msg | None:
        reason = self.part.available(runner)
        if reason is None:
            return None
        return translate("core", "{part} cannot be changed. {reason}").format(
            part=str(self.title), reason=str(reason)
        )

    def same(self, value, current) -> bool:
        return value == current

    def is_active(self, theme: Theme, runner) -> bool:
        value = self.value(theme)
        return value is None or self.same(value, self.part.current(runner))

    def capture_settings(self, runner) -> dict:
        return self.part.capture(runner)

    def reload(self, theme: Theme, runner) -> None:
        self.part.apply(self.value(theme), runner)

    def restore_settings(self, settings: dict, runner) -> None:
        self.part.restore(settings, runner)


class _InstalledChoice(PartTarget):
    """A part chosen from the installed ones: the theme's `<key>` is "installed" and `<key>_id` names it."""

    def value(self, theme: Theme):
        section, key = self.choice
        if theme.part_state(section, key) != "installed":
            return None
        return theme.get(section, f"{key}_id")


class InstalledPlasmaStyle(_InstalledChoice):
    id = "plasma_style"
    title = translate("core", "Plasma style")
    sections = ("panel",)
    key = "plasma_style"
    kind = "plasma_style"
    choice = ("panel", "style")

    def stale_files(self, theme: Theme) -> list[Path]:
        return stale_packages(self.value(theme))  # the one made here goes, unless it is the one named

    def reload_command(self, theme: Theme) -> str:
        return f"plasma-apply-desktoptheme {self.value(theme)}" if self.wanted(theme) else ""

    def describe(self, theme: Theme) -> list[Msg]:
        return [
            translate("core", "the Plasma style: {name} (plasmarc)").format(name=self.name(self.value(theme)))
        ]


class InstalledAppStyle(_InstalledChoice):
    id = "app_style"
    title = translate("core", "Application style")
    sections = ("apps",)
    key = "app_style"
    kind = "app_style"
    choice = ("apps", "style")

    def same(self, value, current) -> bool:
        return str(value).casefold() == str(current).casefold()

    def stale_files(self, theme: Theme) -> list[Path]:
        keep = None
        if str(self.value(theme)).lower().startswith("kvantum"):
            try:  # the theme Kvantum has selected is the one the style shows, so it stays
                keep = selected_theme(selection_file().read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                keep = None
        return stale_themes(keep)

    def describe(self, theme: Theme) -> list[Msg]:
        return [
            translate("core", "the application style: {name} (kdeglobals)").format(
                name=self.name(self.value(theme))
            )
        ]


class InstalledDecoration(_InstalledChoice):
    id = "decoration"
    title = translate("core", "Window decorations")
    sections = ("window",)
    key = "decoration"
    kind = "decoration"
    choice = ("window", "decoration")

    def stale_files(self, theme: Theme) -> list[Path]:
        library, _, name = str(self.value(theme)).partition(":")
        keep = name.removeprefix(AURORAE_THEME_PREFIX) if library == AURORAE_LIBRARY else None
        return stale_frames(keep)

    def describe(self, theme: Theme) -> list[Msg]:
        return [
            translate("core", "the window decoration: {name} (kwinrc)").format(
                name=self.name(self.value(theme))
            )
        ]


class BorderSizeTarget(PartTarget):
    id = "border_size"
    title = translate("core", "Border size")
    sections = ("window",)
    key = "border_size"

    def value(self, theme: Theme):
        return theme.get("window", "border_size")

    def notes(self, theme: Theme) -> list[Msg]:
        if self.value(theme) is None:
            return []
        if theme.part_state("window", "decoration") in ("breeze", "generated"):
            return [
                translate(
                    "core",
                    "The border size chosen here is used instead of the one the window frame "
                    "of this theme would set.",
                )
            ]
        return [translate("core", "KWin uses this border size with whichever window decoration is in use.")]

    def describe(self, theme: Theme) -> list[Msg]:
        from ..model.parts import BORDER_SIZES

        name = dict(BORDER_SIZES).get(self.value(theme), self.value(theme))
        return [translate("core", "the border size of windows: {name} (kwinrc)").format(name=str(name))]


class TitlebarButtonsTarget(PartTarget):
    id = "buttons"
    title = translate("core", "Title bar buttons")
    sections = ("window",)
    key = "titlebar_buttons"

    def value(self, theme: Theme):
        sides = {
            side: theme.get("window", f"buttons_{side}")
            for side in ("left", "right")
            if theme.get("window", f"buttons_{side}") is not None
        }
        return sides or None

    def same(self, value, current) -> bool:
        return all(current.get(side) == text for side, text in value.items())

    def describe(self, theme: Theme) -> list[Msg]:
        return [translate("core", "the buttons in the title bar of windows (kwinrc)")]


class IconsTarget(PartTarget):
    id = "icons"
    title = translate("core", "Icons")
    sections = ("desktop",)
    key = "icons"
    kind = "icons"

    def value(self, theme: Theme):
        return theme.get("desktop", "icons")

    def describe(self, theme: Theme) -> list[Msg]:
        return [
            translate("core", "the icon theme: {name} (kdeglobals)").format(name=self.name(self.value(theme)))
        ]


class CursorThemeTarget(PartTarget):
    id = "cursors"
    title = translate("core", "Pointer theme")
    sections = ("desktop",)
    key = "cursor_theme"
    kind = "cursors"

    def value(self, theme: Theme):
        return theme.get("desktop", "cursors")

    def describe(self, theme: Theme) -> list[Msg]:
        return [
            translate("core", "the pointer theme: {name} (kcminputrc)").format(
                name=self.name(self.value(theme))
            )
        ]


class CursorSizeTarget(PartTarget):
    id = "cursor_size"
    title = translate("core", "Pointer size")
    sections = ("desktop",)
    key = "cursor_size"

    def value(self, theme: Theme):
        return theme.get("desktop", "cursor_size")

    def describe(self, theme: Theme) -> list[Msg]:
        return [translate("core", "the pointer size: {size} px (kcminputrc)").format(size=self.value(theme))]


class NightModeTarget(PartTarget):
    id = "night_mode"
    title = translate("core", "Dark mode at night")
    sections = ("desktop",)
    key = "night_mode"

    def value(self, theme: Theme):
        return theme.get("desktop", "dark_at_night")

    def reload_command(self, theme: Theme) -> str:
        return ""

    # What the switch to the other Global Theme changes: Plasma makes it at once when the switch is
    # turned on at night. An undo puts all of it back, not only the switch.
    SWITCHED = ("plasma_style", "app_style", "decoration", "icons", "cursor_theme", "splash")

    def capture_settings(self, runner) -> dict:
        captured = self.part.capture(runner)
        captured["switched"] = {key: _part(key).capture(runner) for key in self.SWITCHED}
        return captured

    def restore_settings(self, settings: dict, runner) -> None:
        failure = None
        try:
            self.part.restore(settings, runner)
        except ApplyError as error:
            failure = error
        for key, captured in (settings.get("switched") or {}).items():
            try:
                _part(key).restore(captured, runner)
            except ApplyError as error:
                failure = failure or error
        if failure:
            raise failure

    def describe(self, theme: Theme) -> list[Msg]:
        if self.value(theme):
            return [translate("core", "the switch to dark mode at night: on (kdeglobals)")]
        return [translate("core", "the switch to dark mode at night: off (kdeglobals)")]


class FontsTarget(PartTarget):
    id = "fonts"
    title = translate("core", "Fonts")
    sections = ("fonts",)
    key = "fonts"

    def value(self, theme: Theme):
        fonts = {}
        for name in FONT_KEYS:
            text = theme.get("fonts", name)
            spec = FontSpec.from_short(text) if text is not None else None
            if spec is not None:
                fonts[FONT_ROLES[name]] = spec.text()
        return fonts or None

    def same(self, value, current) -> bool:
        return all(
            FontSpec.parse((current or {}).get(role, "")) == FontSpec.parse(text)
            for role, text in value.items()
        )

    def describe(self, theme: Theme) -> list[Msg]:
        return [translate("core", "the fonts of the desktop (kdeglobals)")]


class SplashTarget(PartTarget):
    id = "splash"
    title = translate("core", "Splash screen")
    sections = ("desktop",)
    key = "splash"
    kind = "splash"

    def value(self, theme: Theme):
        return theme.get("desktop", "splash")

    def describe(self, theme: Theme) -> list[Msg]:
        return [
            translate("core", "the splash screen: {name} (ksplashrc)").format(
                name=self.name(self.value(theme))
            )
        ]


class SoundsTarget(PartTarget):
    id = "sounds"
    title = translate("core", "System sounds")
    sections = ("desktop",)
    key = "sounds"
    kind = "sounds"

    def value(self, theme: Theme):
        name = theme.get("desktop", "sounds")
        return {"theme": name} if name is not None else None

    def same(self, value, current) -> bool:
        return current.get("theme") == value["theme"]

    def describe(self, theme: Theme) -> list[Msg]:
        return [
            translate("core", "the sound theme: {name} (kdeglobals)").format(
                name=self.name(self.value(theme)["theme"])
            )
        ]


class AccentTarget(PartTarget):
    """The accent color of the desktop. System Settings can set one of its own (or follow the
    wallpaper), and that overrides the accent of every color scheme. A theme that does not follow the
    wallpaper wants its own accent to show, so an apply removes the override; it is wanted only when
    there is one to remove."""

    id = "accent"
    title = translate("core", "Accent color")
    sections = ("colors",)
    key = "accent"

    @staticmethod
    def follows_wallpaper(theme: Theme) -> bool:
        return bool(theme.get("colors", "accent_from_wallpaper"))

    def value(self, theme: Theme):
        return "wallpaper" if self.follows_wallpaper(theme) else None

    def wanted(self, theme: Theme) -> bool:
        if self.follows_wallpaper(theme):
            return True
        if installed_scheme_of(theme) is not None:
            return False  # an installed scheme is applied by name; its accent is not overridden here
        settings = self.part.settings
        flag = kconfig.user_value(*settings["wallpaper"]) or ""
        # a value that is no color is not an override: Plasma ignores it, so it is left as it is
        return self.part.parse_color(kconfig.user_value(*settings["color"])) is not None or (
            flag.lower() == "true"
        )

    def notes(self, theme: Theme) -> list[Msg]:
        if self.follows_wallpaper(theme):
            return [
                translate(
                    "core",
                    "Plasma takes the accent color from the wallpaper and keeps following it. "
                    "The accent color of this theme is not used while it does.",
                )
            ]
        if self.wanted(theme):
            return [
                translate(
                    "core",
                    "The accent color chosen in System Settings overrides the one of the theme. "
                    "Applying the theme removes it, so that the accent color of the theme shows.",
                )
            ]
        return []

    def is_active(self, theme: Theme, runner) -> bool:
        current = self.part.current(runner)
        return current == "wallpaper" if self.follows_wallpaper(theme) else current is None

    def reload(self, theme: Theme, runner) -> None:
        if self.follows_wallpaper(theme):
            self.part.apply("wallpaper", runner)
        else:
            self.part.clear(runner)

    def reload_command(self, theme: Theme) -> str:
        return "" if self.follows_wallpaper(theme) else "plasma-apply-colorscheme"

    def describe(self, theme: Theme) -> list[Msg]:
        if self.follows_wallpaper(theme):
            return [translate("core", "the accent color: it follows the wallpaper (kdeglobals)")]
        return [
            translate("core", "the accent color chosen in System Settings, which is removed (kdeglobals)")
        ]
