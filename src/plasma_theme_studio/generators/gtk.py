# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generates the style sheet that gives GTK 3, GTK 4 and libadwaita applications
the theme's corner radius, border width and colors.

The sheet is a file of its own, plasma-theme-studio.css, next to gtk.css in
gtk-3.0 and gtk-4.0. The only change to gtk.css is one @import line at the top,
which is removed again on undo. Plasma's own GTK settings module rewrites
gtk.css and keeps lines it does not know, so the line survives it.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import paths
from ..apply import desktop
from ..messages import Msg, translate
from ..model.color import Color, readable_on
from ..model.theme import Theme, write_atomic
from .base import CSS_MARKER, ApplyError, Generator, PlannedFile

FILE_NAME = "plasma-theme-studio.css"
IMPORT_LINE = f"@import '{FILE_NAME}';"
VERSIONS = (3, 4)

_STATES = ("maximized", "fullscreen", "tiled", "tiled-top", "tiled-left", "tiled-right", "tiled-bottom")
_FLAT_WINDOW = ", ".join(
    [f"window.csd.{s}" for s in _STATES] + [f"dialog.csd.{s}" for s in _STATES] + ["window.solid-csd"]
)
_FLAT_HEADER = ", ".join(f"window.csd.{s} headerbar" for s in _STATES)


def _folder(version: int) -> Path:
    return paths.config_home() / f"gtk-{version}.0"


def css_path(version: int) -> Path:
    return _folder(version) / FILE_NAME


def gtk_css_path(version: int) -> Path:
    return _folder(version) / "gtk.css"


def _look(theme: Theme) -> tuple[int, int, int]:
    return (
        int(theme.resolved("gtk", "radius")),
        int(theme.resolved("gtk", "border_width")),
        int(theme.resolved("gtk", "window_radius")),
    )


def adwaita_colors(theme: Theme) -> list[tuple[str, str]]:
    """The libadwaita named colors the theme sets, in file order. Every color
    drawn on a theme color gets the foreground that is readable on it."""

    def fg(color: Color) -> str:
        return readable_on(color).hex

    accent, window, view = theme.color("accent"), theme.color("window"), theme.color("view")
    button, header, text = theme.color("button"), theme.color("header"), theme.color("text")
    negative, neutral, positive = theme.color("negative"), theme.color("neutral"), theme.color("positive")
    return [
        ("accent_bg_color", accent.hex),
        ("accent_fg_color", fg(accent)),
        ("window_bg_color", window.hex),
        ("window_fg_color", text.hex),
        ("view_bg_color", view.hex),
        ("view_fg_color", text.hex),
        ("headerbar_bg_color", header.hex),
        ("headerbar_fg_color", text.hex),
        ("sidebar_bg_color", header.hex),
        ("sidebar_fg_color", text.hex),
        ("secondary_sidebar_bg_color", window.hex),
        ("secondary_sidebar_fg_color", text.hex),
        ("card_bg_color", button.hex),
        ("card_fg_color", text.hex),
        ("dialog_bg_color", window.hex),
        ("dialog_fg_color", text.hex),
        ("popover_bg_color", window.hex),
        ("popover_fg_color", text.hex),
        ("destructive_bg_color", negative.hex),
        ("destructive_fg_color", fg(negative)),
        ("error_bg_color", negative.hex),
        ("error_fg_color", fg(negative)),
        ("warning_bg_color", neutral.hex),
        ("warning_fg_color", fg(neutral)),
        ("success_bg_color", positive.hex),
        ("success_fg_color", fg(positive)),
    ]


def _breeze(version: int, radius: int, border: int, window_radius: int) -> list[str]:
    """Radius and border for the Breeze GTK theme. The window node differs between GTK 3 and 4."""
    lines = [
        f"/* Breeze GTK theme: radius {radius}px, border {border}px */",
        f"button, entry, spinbutton:not(.vertical) {{ border-radius: {radius}px; }}",
        f"button, entry, spinbutton:not(.vertical) {{ border-width: {border}px; }}",
        "button.circular, button.titlebutton { border-radius: 50%; }",
        f"popover.background, menu {{ border-radius: {radius}px; }}",
    ]
    if version == 3:
        lines += [
            f"popover.background {{ border-width: {border}px; }}",
            f"decoration, .csd decoration {{ border-radius: {window_radius}px; }}",
            f"window.background.csd {{ border-radius: 0 0 {window_radius}px {window_radius}px; }}",
            f".popup decoration {{ border-radius: {radius}px; }}",
            f"headerbar {{ border-radius: {window_radius}px {window_radius}px 0 0; }}",
            ".maximized decoration, .fullscreen decoration, .tiled decoration, .solid-csd decoration,",
            "window.background.maximized, window.background.fullscreen, window.background.tiled,",
            ".maximized headerbar, .fullscreen headerbar, .tiled headerbar { border-radius: 0; }",
        ]
    else:
        lines += [
            f"popover > contents, popover.background > contents {{ border-radius: {radius}px; "
            f"border-width: {border}px; }}",
            f"window.csd, dialog.csd {{ border-radius: {window_radius}px; }}",
            f"window.csd > headerbar.titlebar, window.csd headerbar "
            f"{{ border-radius: {window_radius}px {window_radius}px 0 0; }}",
            f"{_FLAT_WINDOW} {{ border-radius: 0; }}",
            f"{_FLAT_HEADER} {{ border-radius: 0; }}",
        ]
    return lines


def _libadwaita(radius: int, window_radius: int) -> list[str]:
    """libadwaita hard-codes most radii in its own sheet, so they are set again here."""
    return [
        "/* libadwaita: the window radius and the radii its sheet fixes */",
        f":root {{ --window-radius: {window_radius}px; }}",
        f"button:not(.circular):not(.pill):not(.titlebutton) {{ border-radius: {radius}px; }}",
        f"entry, spinbutton, dropdown > button, searchbar > revealer > box {{ border-radius: {radius}px; }}",
        f"popover > contents {{ border-radius: {radius}px; }}",
        ".card, list.boxed-list, .boxed-list > row:first-child, preferencesgroup > box > list "
        f"{{ border-radius: {min(radius + 3, 24)}px; }}",
    ]


def build_css(theme: Theme, version: int) -> str:
    """The style sheet for GTK `version`. GTK's CSS knows only /* */ comments."""
    radius, border, window_radius = _look(theme)
    lines = [CSS_MARKER, f"/* GTK {version} (Breeze theme and libadwaita) */"]
    if version == 4:
        lines.append("/* libadwaita named colors. The Breeze theme gets its colors from colors.css. */")
        lines += [f"@define-color {name} {value};" for name, value in adwaita_colors(theme)]
    lines += _breeze(version, radius, border, window_radius)
    if version == 4:
        lines += _libadwaita(radius, window_radius)
    return "\n".join(lines) + "\n"


def with_import(text: str) -> str:
    """The text of gtk.css with our import line at the top, once. All else is kept."""
    return text if has_import(text) else IMPORT_LINE + "\n" + text


def has_import(text: str) -> bool:
    return any(line.strip() == IMPORT_LINE for line in text.splitlines())


def without_import(text: str) -> str:
    """The text without our import line and without anything else changed."""
    return "".join(line for line in text.splitlines(keepends=True) if line.strip() != IMPORT_LINE)


def _folder_name(version: int) -> str:
    return f"gtk-{version}.0"


class GtkGenerator(Generator):
    id = "gtk"
    title = translate("core", "GTK applications")
    sections = ("gtk",)

    def wanted(self, theme: Theme) -> bool:
        return theme.get("gtk", "style") == "generated"

    def notes(self, theme: Theme) -> list[Msg]:
        if not self.wanted(theme):
            return [
                translate(
                    "core",
                    "GTK applications keep their look. The GTK values here only show in the preview.",
                )
            ]
        return [
            translate(
                "core",
                "Applications started after the apply use the new look at once. Running GTK 3 applications "
                "need a restart. Running GTK 4 applications change when the desktop switches between "
                "light and dark.",
            ),
            translate(
                "core",
                "The colors of GTK applications that use the Breeze theme come from the color scheme. "
                "libadwaita applications get the theme's colors from the sheet written here.",
            ),
        ]

    def files(self, theme: Theme) -> list[PlannedFile]:
        return [PlannedFile(css_path(v), build_css(theme, v), CSS_MARKER) for v in VERSIONS]

    def check_output(self, file: PlannedFile) -> list[Msg]:
        text = file.content
        problems = []
        if text.count("{") != text.count("}"):
            problems.append(translate("core", "The generated GTK style sheet has unbalanced braces."))
        for argument in re.findall(r":not\(([^)]*)\)", text):
            # GTK 4 drops a rule whose :not() holds more than one simple selector.
            if len(re.findall(r"[.#:\[]", argument)) > 1 or re.search(r"[\s>+~,]", argument):
                problems.append(
                    translate("core", "The generated GTK style sheet has a :not() that GTK 4 rejects.")
                )
                break
        if re.search(r"^\s*#", text, re.MULTILINE):
            problems.append(translate("core", "The generated GTK style sheet has a line comment."))
        return problems

    def changed_settings(self, theme: Theme) -> list[Msg]:
        return [
            translate("core", "one added line in {path}, which an undo takes away again").format(
                path=f"~/.config/{_folder_name(v)}/gtk.css"
            )
            for v in VERSIONS
        ]

    def problems(self, theme: Theme) -> list[Msg]:
        found = []
        home = Path.home().resolve()
        for version in VERSIONS:
            path = gtk_css_path(version)
            try:
                desktop.capture_file(path)
            except OSError:
                found.append(
                    translate("core", "{path} cannot be read as text, so it is not changed.").format(
                        path=str(path)
                    )
                )
                continue
            if path.is_symlink() and not path.resolve().is_relative_to(home):
                found.append(
                    translate(
                        "core", "{path} is a link to a file outside your home folder and is not changed."
                    ).format(path=str(path))
                )
        return found

    def is_active(self, theme: Theme, runner) -> bool:
        for planned in self.files(theme):
            try:
                if desktop.capture_file(planned.path) != planned.content:
                    return False
            except OSError:
                return False
        for version in VERSIONS:
            try:
                if not has_import(desktop.capture_file(gtk_css_path(version))):
                    return False
            except OSError:
                return False
        return True

    def capture_settings(self, runner) -> dict:
        saved = {}
        for version in VERSIONS:
            path = gtk_css_path(version)
            try:
                text = desktop.capture_file(path)
            except OSError:
                text = ""  # never reached: the plan refuses a file that cannot be read
            saved[str(version)] = {
                "dir_existed": _folder(version).is_dir(),
                "file_existed": text != desktop.ABSENT or path.is_symlink(),
                "had_import": text != desktop.ABSENT and has_import(text),
            }
        return saved

    def reload(self, theme: Theme, runner) -> None:
        for version in VERSIONS:
            path = gtk_css_path(version)
            try:
                text = desktop.capture_file(path)
                if text == desktop.ABSENT:
                    text = ""
                if not has_import(text):
                    write_atomic(path, with_import(text))
            except OSError as error:
                raise ApplyError(
                    translate("core", "Could not add the style sheet to {path}: {detail}").format(
                        path=str(path), detail=str(error)
                    )
                ) from error

    def restore_settings(self, settings: dict, runner) -> None:
        for version in VERSIONS:
            saved = settings.get(str(version))
            if not saved or saved.get("had_import"):
                continue  # not reached, or the line was there before and stays
            path = gtk_css_path(version)
            text = desktop.capture_file(path)
            if text == desktop.ABSENT:
                continue
            remaining = without_import(text)
            if remaining != text:
                if not saved.get("file_existed") and not remaining.strip() and not path.is_symlink():
                    path.unlink(missing_ok=True)
                else:
                    write_atomic(path, remaining)
            elif not saved.get("file_existed") and not text.strip() and not path.is_symlink():
                path.unlink(missing_ok=True)
            if not saved.get("dir_existed"):
                try:
                    _folder(version).rmdir()
                except OSError:
                    pass  # not empty: it holds something that is not ours
