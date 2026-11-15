# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generates a Plasma color scheme (.colors) and activates it."""

from __future__ import annotations

import configparser
import re

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .. import paths
from ..messages import Msg, translate
from ..model.color import BLACK, Color
from ..model.color import on_accent as readable_on_accent
from ..model.theme import Theme
from .base import MARKER, ApplyError, Generator, PlannedFile

_TEMPLATES = Environment(
    loader=FileSystemLoader(str(paths.Path(__file__).parent / "templates")),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

# plasma-apply-colorscheme does nothing when asked for the scheme that is
# already active. To reload an edited scheme, the active name is first set
# to this placeholder.
RELOAD_PLACEHOLDER = "PlasmaThemeStudioReload"
FALLBACK_SCHEME = "BreezeLight"  # what Plasma uses when no scheme is named

COLOR_GROUPS = (
    "Colors:Button",
    "Colors:Complementary",
    "Colors:Header",
    "Colors:Header][Inactive",
    "Colors:Selection",
    "Colors:Tooltip",
    "Colors:View",
    "Colors:Window",
)
_RGB = re.compile(r"^(\d{1,3}),(\d{1,3}),(\d{1,3})$")


def _darkest(a: Color, b: Color) -> Color:
    return a if a.luminance <= b.luminance else b


def scheme_groups(theme: Theme) -> list[tuple[str, list[tuple[str, str]]]]:
    """The color groups of the scheme, derived from the theme's color tokens."""
    c = theme.color
    accent, text, muted = c("accent"), c("text"), c("text_muted")
    window, view, button, header = c("window"), c("view"), c("button"), c("header")
    status = {
        "link": c("link"),
        "visited": c("visited"),
        "negative": c("negative"),
        "neutral": c("neutral"),
        "positive": c("positive"),
    }

    def group(background, alternate, foreground, inactive, *, active=accent, **overrides):
        colors = {**status, **overrides}
        return [
            ("BackgroundAlternate", alternate.kde),
            ("BackgroundNormal", background.kde),
            ("DecorationFocus", accent.kde),
            ("DecorationHover", accent.kde),
            ("ForegroundActive", active.kde),
            ("ForegroundInactive", inactive.kde),
            ("ForegroundLink", colors["link"].kde),
            ("ForegroundNegative", colors["negative"].kde),
            ("ForegroundNeutral", colors["neutral"].kde),
            ("ForegroundNormal", foreground.kde),
            ("ForegroundPositive", colors["positive"].kde),
            ("ForegroundVisited", colors["visited"].kde),
        ]

    window_alt = window.mix(text, 0.06)
    view_alt = view.mix(window, 0.5)
    accent_tint = button.mix(accent, 0.45)
    # Whichever of white and the theme's darkest color reads better on the accent.
    on_accent = readable_on_accent(accent, text, window)

    if window.is_dark:
        comp_bg, comp_fg, comp_muted = window, text, muted
    else:
        comp_bg, comp_fg = text.mix(window, 0.04), view
        comp_muted = comp_fg.mix(comp_bg, 0.4)

    return [
        ("Colors:Button", group(button, accent_tint, text, muted)),
        ("Colors:Complementary", group(comp_bg, comp_bg.mix(BLACK, 0.3), comp_fg, comp_muted)),
        ("Colors:Header", group(header, window, text, muted)),
        ("Colors:Header][Inactive", group(window, window_alt, text, muted)),
        (
            "Colors:Selection",
            group(
                accent,
                accent_tint,
                on_accent,
                on_accent.mix(accent, 0.35),
                active=on_accent,
                link=on_accent,
                visited=on_accent,
                negative=status["negative"].mix(BLACK, 0.2),
                neutral=status["neutral"].mix(BLACK, 0.2),
                positive=status["positive"].mix(BLACK, 0.4),
            ),
        ),
        ("Colors:Tooltip", group(view_alt, window, text, muted)),
        ("Colors:View", group(view, view_alt, text, muted)),
        ("Colors:Window", group(window, window_alt, text, muted)),
    ]


def installed_scheme_of(theme: Theme):
    """The installed color scheme the theme's colors are exactly, or None. The theme names it
    (`colors.scheme_id`); as soon as one of its colors differs the colors are written as a scheme
    of their own."""
    from .. import library

    wanted = theme.get("colors", "scheme_id")
    if not wanted:
        return None
    for scheme in library.installed_schemes():
        if scheme.id == wanted:
            same = all(theme.get("colors", key) == value for key, value in scheme.colors.items())
            return scheme if same else None
    return None


def scheme_name(theme: Theme) -> str:
    """The name the desktop knows the theme's colors by."""
    found = installed_scheme_of(theme)
    return found.id if found is not None else theme.scheme_slug


class ColorSchemeGenerator(Generator):
    id = "colors"
    title = translate("core", "Colors")
    sections = ("colors",)

    def unavailable_reason(self, runner) -> Msg | None:
        for tool in ("plasma-apply-colorscheme", "kreadconfig6", "kwriteconfig6"):
            if not runner.which(tool):
                return translate(
                    "core", "{tool} was not found. Colors can only be applied in KDE Plasma 6."
                ).format(tool=tool)
        return None

    def files(self, theme: Theme) -> list[PlannedFile]:
        if installed_scheme_of(theme) is not None:
            return []  # the installed scheme is used as it is
        window, text = theme.color("window"), theme.color("text")
        content = _TEMPLATES.get_template("colorscheme.colors.j2").render(
            marker=MARKER,
            slug=theme.scheme_slug,
            name=theme.scheme_title,
            groups=scheme_groups(theme),
            wm={
                "activeBackground": theme.color("header").kde,
                "activeBlend": theme.color("header").kde,
                "activeForeground": text.kde,
                "inactiveBackground": window.kde,
                "inactiveBlend": window.kde,
                "inactiveForeground": theme.color("text_muted").kde,
            },
            disabled_color=window.mix(text, 0.75).kde,
            inactive_color=theme.color("text_muted").kde,
        )
        return [PlannedFile(paths.color_schemes_dir() / f"{theme.scheme_slug}.colors", content)]

    def check_output(self, file: PlannedFile) -> list[Msg]:
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.optionxform = str
        try:
            parser.read_string(file.content)
        except configparser.Error as error:
            return [
                translate("core", "The generated color scheme is not valid: {detail}").format(
                    detail=str(error).splitlines()[0]
                )
            ]
        problems = []
        for group in (*COLOR_GROUPS, "WM", "General"):
            if not parser.has_section(group):
                problems.append(
                    translate("core", "The generated color scheme has no [{group}] group.").format(
                        group=group
                    )
                )
        for group in parser.sections():
            if not group.startswith("Colors:") and group != "WM":
                continue
            for key, value in parser.items(group):
                match = _RGB.match(value)
                if not match or any(int(part) > 255 for part in match.groups()):
                    problems.append(
                        translate("core", "The generated color scheme has an invalid color: {key}").format(
                            key=f"[{group}] {key}={value}"
                        )
                    )
        return problems

    def problems(self, theme: Theme) -> list[Msg]:
        if not theme.scheme_slug or installed_scheme_of(theme) is not None:
            return []  # reported by the theme itself, or nothing is written
        for directory in paths.system_data_dirs():
            found = directory / "color-schemes" / f"{theme.scheme_slug}.colors"
            if found.exists():
                return [
                    translate(
                        "core",
                        "A color scheme called {name} is already installed with the system ({file}). "
                        "Give the theme another name.",
                    ).format(name=theme.scheme_slug, file=found)
                ]
        return []

    def is_active(self, theme: Theme, runner) -> bool:
        # a desktop with no ColorScheme key shows Breeze Light
        return (current_scheme(runner) or FALLBACK_SCHEME) == scheme_name(theme)

    def reload_command(self, theme: Theme) -> str:
        return f"plasma-apply-colorscheme {scheme_name(theme)}"

    def capture_settings(self, runner) -> dict:
        return {"color_scheme": _read_setting(runner, "ColorScheme")}

    def reload(self, theme: Theme, runner) -> None:
        activate_scheme(scheme_name(theme), runner)

    def restore_settings(self, settings: dict, runner) -> None:
        # With no scheme named anywhere, Plasma uses its built-in one.
        activate_scheme(settings.get("color_scheme") or FALLBACK_SCHEME, runner)


def _read_setting(runner, key: str) -> str:
    result = runner.run(["kreadconfig6", "--file", "kdeglobals", "--group", "General", "--key", key])
    return result.stdout.strip() if result.returncode == 0 else ""


def current_scheme(runner) -> str:
    """The name of the color scheme the desktop uses now."""
    return _read_setting(runner, "ColorScheme")


def _write_scheme_name(runner, name: str) -> None:
    runner.run(["kwriteconfig6", "--file", "kdeglobals", "--group", "General", "--key", "ColorScheme", name])


def activate_scheme(name: str, runner) -> None:
    """Make `name` the active color scheme, reloading it if it already is."""
    current = _read_setting(runner, "ColorScheme")
    if (current or FALLBACK_SCHEME) == name:  # no name in the file means Breeze Light
        _write_scheme_name(runner, RELOAD_PLACEHOLDER)
    result = runner.run(["plasma-apply-colorscheme", name])
    # The tool exits with 0 even when it rejects the scheme, so check the outcome.
    # Plasma drops the key when the scheme is the default one, so an empty read-back is right then.
    now = _read_setting(runner, "ColorScheme")
    if now != name and not (name == FALLBACK_SCHEME and not now):
        if current and current != RELOAD_PLACEHOLDER:
            _write_scheme_name(runner, current)
        detail = (result.output.splitlines() or [""])[0][:200]
        raise ApplyError(
            translate("core", "Plasma did not accept the color scheme {name}. {detail}").format(
                name=name, detail=detail
            )
        )
