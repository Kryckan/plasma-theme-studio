# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The theme file: its fields, validation, loading, saving and migration.

A theme is a TOML file with a `schema_version` and one table per section.
`FIELDS` is the single definition of what a theme contains. The UI builds
its controls from it and the file format follows it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
import tomllib
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..messages import Msg, translate
from .color import Color
from .parts import BORDER_SIZES, FontSpec, parse_buttons

SCHEMA_VERSION = 1
MAX_NAME_LENGTH = 60


@dataclass(frozen=True)
class Field:
    section: str
    key: str
    kind: str  # "color", "int", "float", "str", "choice" or "bool"
    default: object
    minimum: float | None = None
    maximum: float | None = None
    # An optional value: while it is unset (None) the field follows this other field.
    inherits: tuple[str, str] | None = None
    # The values a "choice" field accepts. They are identifiers; the UI has their names.
    choices: tuple[str, ...] = ()
    # An optional value that follows nothing: while it is unset (None) the
    # theme leaves that part of the desktop the way it is.
    optional: bool = False
    # What a "str" field holds: "id" (the name of an installed thing), "font" (see
    # `FontSpec.from_short`) or "buttons" (KWin's letters); "" for any text.
    form: str = ""

    @property
    def id(self) -> tuple[str, str]:
        return (self.section, self.key)

    @property
    def path(self) -> str:
        return f"{self.section}.{self.key}"


PANEL_LOCATIONS = ("top", "bottom", "left", "right")
PANEL_VISIBILITIES = ("none", "autohide", "dodgewindows", "windowsgobelow")
PANEL_OPACITIES = ("adaptive", "opaque", "translucent")
TOOLBAR_STYLES = ("NoText", "TextOnly", "TextBesideIcon", "TextUnderIcon")  # as kdeglobals names them
FEEDBACK_CURSORS = ("none", "static", "blinking", "bouncing")
BORDER_SIZE_KEYS = tuple(key for key, _name in BORDER_SIZES)
MAX_ID_LENGTH = 200
# The fonts the theme can set: key -> what it is called on the desktop.
FONT_KEYS = ("general", "fixed", "small", "toolbar", "menu", "window_title")

# The frames of the Plasma style that can be drawn by hand: the file (relative to the theme file) of
# each one's own artwork, in the section "artwork".
ARTWORK_KEYS = ("panel", "popups", "tooltips", "widgets")
_ARTWORK_NAME = re.compile(r"\w[\w .-]*(/\w[\w .-]*)*\.svg")


def artwork_name_ok(text: str) -> bool:
    """Whether `text` is a name the theme file may give to a frame's artwork."""
    return len(text) <= MAX_ID_LENGTH and ".." not in text and bool(_ARTWORK_NAME.fullmatch(text))


def artwork_folder(theme_file: Path) -> Path:
    """The folder next to a theme file that holds its own artwork: "my.toml" has "my-artwork".
    A file name with characters a theme file's artwork name cannot hold ("it's.toml") gets a safe name."""
    name = f"{theme_file.stem}-artwork"
    if artwork_name_ok(f"{name}/panel.svg"):
        return theme_file.with_name(name)
    stem = re.sub(r"[^\w]+", "-", theme_file.stem[:80]).strip("-") or "theme"
    # Two names can come to the same safe one ("it's" and "it-s"): the hash keeps them apart.
    digest = hashlib.sha1(theme_file.stem.encode("utf-8", "replace")).hexdigest()[:6]
    return theme_file.with_name(f"{stem}-{digest}-artwork")


ARTWORK_LIMIT = 2 * 1024 * 1024  # bytes of one own artwork file
PANEL_SECTION = "panel_layout"
MAX_PANELS = 6  # the main panel and five more
PANEL_FIELDS: tuple[Field, ...] = (
    Field(PANEL_SECTION, "location", "choice", None, choices=PANEL_LOCATIONS, optional=True),
    Field(PANEL_SECTION, "height", "int", None, 20, 120, optional=True),
    Field(PANEL_SECTION, "alignment", "choice", None, choices=("left", "center", "right"), optional=True),
    Field(PANEL_SECTION, "length_mode", "choice", None, choices=("fill", "fit"), optional=True),
    Field(PANEL_SECTION, "floating", "bool", None, optional=True),
    Field(PANEL_SECTION, "visibility", "choice", None, choices=PANEL_VISIBILITIES, optional=True),
    Field(PANEL_SECTION, "opacity_mode", "choice", None, choices=PANEL_OPACITIES, optional=True),
)


def panel_section(number: int) -> str:
    """The theme section of panel `number` (1 is the main panel)."""
    return PANEL_SECTION if number == 1 else f"{PANEL_SECTION}_{number}"


FIELDS: tuple[Field, ...] = (
    Field("meta", "name", "str", "My Theme"),
    Field("meta", "author", "str", ""),
    Field("colors", "accent", "color", "#3daee9"),
    # False: the theme's accent is the accent (an apply removes the accent override of System
    # Settings). True: Plasma takes the accent from the wallpaper and keeps following it.
    Field("colors", "accent_from_wallpaper", "bool", False),
    # The installed color scheme the colors were taken from. While the colors still are exactly
    # that scheme's, an apply activates the scheme itself instead of writing a copy of it.
    Field("colors", "scheme_id", "str", None, optional=True, form="id"),
    Field("colors", "window", "color", "#eff0f1"),
    Field("colors", "view", "color", "#ffffff"),
    Field("colors", "button", "color", "#fcfcfc"),
    Field("colors", "header", "color", "#dee0e2"),
    Field("colors", "text", "color", "#232629"),
    Field("colors", "text_muted", "color", "#707d8a"),
    Field("colors", "link", "color", "#2980b9"),
    Field("colors", "visited", "color", "#9b59b6"),
    Field("colors", "negative", "color", "#da4453"),
    Field("colors", "neutral", "color", "#f67400"),
    Field("colors", "positive", "color", "#27ae60"),
    Field("shape", "radius", "int", 5, 0, 24),
    Field("shape", "border_width", "int", 1, 0, 4),
    Field("apps", "style", "choice", "unchanged", choices=("unchanged", "generated", "installed")),
    Field("apps", "style_id", "str", None, optional=True, form="id"),
    Field("apps", "radius", "int", None, 0, 24, inherits=("shape", "radius")),
    Field("apps", "border_width", "int", None, 0, 4, inherits=("shape", "border_width")),
    Field(
        "window",
        "decoration",
        "choice",
        "unchanged",
        choices=("unchanged", "breeze", "generated", "installed"),
    ),
    Field("window", "decoration_id", "str", None, optional=True, form="id"),
    Field("window", "radius", "int", None, 0, 24, inherits=("shape", "radius")),
    Field("window", "border_width", "int", None, 0, 12, inherits=("shape", "border_width")),
    Field("window", "border_size", "choice", None, choices=BORDER_SIZE_KEYS, optional=True),
    Field("window", "buttons_left", "str", None, optional=True, form="buttons"),
    Field("window", "buttons_right", "str", None, optional=True, form="buttons"),
    # The generated frame only; unset they are the frame's usual 30 px bar, 22 px buttons, 4 px apart.
    Field("window", "title_height", "int", None, 20, 60, optional=True),
    Field("window", "button_size", "int", None, 12, 40, optional=True),
    Field("window", "button_spacing", "int", None, 0, 16, optional=True),
    Field("shadow", "size", "int", 24, 0, 64),
    Field("shadow", "strength", "float", 0.35, 0.0, 1.0),
    # Which way the shadow falls, in pixels (generated frame only); unset it falls evenly on all sides.
    Field("shadow", "offset_x", "int", None, -32, 32, optional=True),
    Field("shadow", "offset_y", "int", None, -32, 32, optional=True),
    Field("panel", "style", "choice", "unchanged", choices=("unchanged", "generated", "installed")),
    Field("panel", "style_id", "str", None, optional=True, form="id"),
    Field("panel", "radius", "int", None, 0, 24, inherits=("shape", "radius")),
    Field("panel", "border_width", "int", None, 0, 4, inherits=("shape", "border_width")),
    Field("panel", "opacity", "float", 0.85, 0.2, 1.0),
    Field("popup", "radius", "int", None, 0, 24, inherits=("panel", "radius")),
    Field("popup", "border_width", "int", None, 0, 4, inherits=("panel", "border_width")),
    Field("popup", "opacity", "float", None, 0.2, 1.0, inherits=("panel", "opacity")),
    *PANEL_FIELDS,
    # Further panels, in the order the desktop lists them after the main one ("panel 2", "panel 3"):
    # one section each, `panel_layout_2` and so on, with the values of the main panel's section.
    *(
        Field(
            f"{PANEL_SECTION}_{number}",
            field.key,
            field.kind,
            None,
            field.minimum,
            field.maximum,
            choices=field.choices,
            optional=True,
        )
        for number in range(2, MAX_PANELS + 1)
        for field in PANEL_FIELDS
    ),
    # True: Plasma switches between the light and the dark Global Theme chosen in System Settings
    # with the sun; False: it does not; unset: left as it is.
    # Icons and Toolbars (System Settings > Application Style) and Launch Feedback (> Pointers).
    Field("toolbars", "main_style", "choice", None, choices=TOOLBAR_STYLES, optional=True),
    Field("toolbars", "other_style", "choice", None, choices=TOOLBAR_STYLES, optional=True),
    Field("toolbars", "icons_on_buttons", "bool", None, optional=True),
    Field("toolbars", "icons_in_menus", "bool", None, optional=True),
    Field("feedback", "cursor", "choice", None, choices=FEEDBACK_CURSORS, optional=True),
    Field("feedback", "cursor_timeout", "int", None, 1, 60, optional=True),
    Field("feedback", "taskbar", "bool", None, optional=True),
    Field("feedback", "taskbar_timeout", "int", None, 1, 60, optional=True),
    *(Field("artwork", key, "str", None, optional=True, form="artwork") for key in ARTWORK_KEYS),
    Field("desktop", "dark_at_night", "bool", None, optional=True),
    Field("desktop", "icons", "str", None, optional=True, form="id"),
    Field("desktop", "cursors", "str", None, optional=True, form="id"),
    Field("desktop", "cursor_size", "int", None, 8, 256, optional=True),
    Field("desktop", "splash", "str", None, optional=True, form="id"),
    Field("desktop", "sounds", "str", None, optional=True, form="id"),
    *(Field("fonts", key, "str", None, optional=True, form="font") for key in FONT_KEYS),
    Field("gtk", "style", "choice", "unchanged", choices=("unchanged", "generated")),
    Field("gtk", "radius", "int", None, 0, 24, inherits=("shape", "radius")),
    Field("gtk", "border_width", "int", None, 0, 4, inherits=("shape", "border_width")),
    Field("gtk", "window_radius", "int", None, 0, 24, inherits=("window", "radius")),
    Field("rofi", "style", "choice", "unchanged", choices=("unchanged", "generated")),
    Field("rofi", "radius", "int", None, 0, 24, inherits=("shape", "radius")),
    Field("rofi", "border_width", "int", None, 0, 4, inherits=("shape", "border_width")),
    Field("rofi", "opacity", "float", 1.0, 0.3, 1.0),
    Field("rofi", "font", "str", None, optional=True),
)

FIELD_BY_ID: dict[tuple[str, str], Field] = {f.id: f for f in FIELDS}
SECTIONS: tuple[str, ...] = tuple(dict.fromkeys(f.section for f in FIELDS))

PRESETS: dict[str, dict[tuple[str, str], object]] = {
    "breeze-light": {("meta", "name"): "Breeze Light Copy"},
    "breeze-dark": {
        ("meta", "name"): "Breeze Dark Copy",
        ("colors", "window"): "#202326",
        ("colors", "view"): "#141618",
        ("colors", "button"): "#292c30",
        ("colors", "header"): "#292c30",
        ("colors", "text"): "#fcfcfc",
        ("colors", "text_muted"): "#a1a9b1",
        ("colors", "link"): "#1d99f3",
    },
}


class ThemeError(Exception):
    """One or more problems with a theme or theme file."""

    def __init__(self, problems: list[Msg]):
        self.problems = problems
        super().__init__("; ".join(str(p) for p in problems))


def slugify(name: str) -> str:
    """Turn a theme name into the ASCII identifier used for generated files."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", ascii_name)
    return "".join(word[:1].upper() + word[1:] for word in words)


def check_value(field: Field, value) -> tuple[object, Msg | None]:
    """Return the value in its stored form, or a message saying why it is invalid."""
    if value is None and (field.inherits or field.optional):
        return None, None
    if field.kind == "choice":
        if not isinstance(value, str) or value not in field.choices:
            return value, translate("core", "{key} must be one of: {choices}.").format(
                key=field.path, choices=", ".join(field.choices)
            )
        return value, None
    if field.kind == "bool":
        if not isinstance(value, bool):
            return value, translate("core", "{key} must be true or false.").format(key=field.path)
        return value, None
    if field.kind == "color":
        if not Color.is_valid(value):
            return value, translate("core", "{key} must be a hex color such as #3daee9.").format(
                key=field.path
            )
        return Color.parse(value).hex, None
    if field.kind == "str":
        if not isinstance(value, str):
            return value, translate("core", "{key} must be text.").format(key=field.path)
        if any(ord(c) < 32 or c == "\\" for c in value):
            return value, translate(
                "core", "{key} must not contain line breaks, control characters or backslashes."
            ).format(key=field.path)
        if field.form:
            return _check_form(field, value)
        return value, None
    # TOML also has inf and nan, which are no size or strength of anything.
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if field.kind == "int":
        if not is_number or float(value) != int(value):
            return value, translate("core", "{key} must be a whole number.").format(key=field.path)
        value = int(value)
    else:
        if not is_number:
            return value, translate("core", "{key} must be a number.").format(key=field.path)
        value = float(value)
    if value < field.minimum or value > field.maximum:
        return value, translate("core", "{key} must be between {minimum} and {maximum}.").format(
            key=field.path, minimum=field.minimum, maximum=field.maximum
        )
    return value, None


def _check_form(field: Field, value: str) -> tuple[object, Msg | None]:
    """The checks of a "str" field that holds a name, a font or a button string."""
    text = value.strip()
    if any(unicodedata.category(c) == "Cc" for c in value):
        return value, translate("core", "{key} must not contain control characters.").format(key=field.path)
    if field.form == "font":
        spec = FontSpec.from_short(text)
        if spec is None:
            return value, translate("core", "{key} must be a font such as “Noto Sans, 10”.").format(
                key=field.path
            )
        return spec.short(), None
    if field.form == "artwork":
        # A file inside the folder of the theme file: relative, no "..", an SVG.
        if not artwork_name_ok(text):
            return value, translate(
                "core", "{key} must be the name of an .svg file next to the theme file."
            ).format(key=field.path)
        return text, None
    if field.form == "buttons":
        if parse_buttons(text) is None:
            return value, translate(
                "core", "{key} must be KWin's button letters, each at most once (a spacer is _)."
            ).format(key=field.path)
        return text, None
    if not text or len(text) > MAX_ID_LENGTH:
        return value, translate("core", "{key} must be a name of at most {count} characters.").format(
            key=field.path, count=MAX_ID_LENGTH
        )
    return text, None


# The colors a second (light or dark) variant of a theme has of its own. Everything else is shared.
VARIANT_KEYS = (
    "accent",
    "scheme_id",
    "window",
    "view",
    "button",
    "header",
    "text",
    "text_muted",
    "link",
    "visited",
    "negative",
    "neutral",
    "positive",
)
VARIANT_NAMES = ("light", "dark")


class Theme:
    def __init__(self, values: dict[tuple[str, str], object] | None = None):
        self._values: dict[tuple[str, str], object] = {f.id: f.default for f in FIELDS}
        # Where the theme file is (set by `load` and `save`): own artwork is found relative to it.
        self.base_dir: Path | None = None
        # Artwork that came with an imported archive, written next to the theme file on its first save.
        self.pending_artwork: dict[str, bytes] = {}
        # The second variant's colors (keys of VARIANT_KEYS), and which variant `_values` holds.
        # `shown` is the variant the editor works on; it is a view, not part of the theme.
        self._other: dict[str, object] | None = None
        self._main: str | None = None
        self.shown: str | None = None
        for (section, key), value in (values or {}).items():
            self.set(section, key, value)

    @classmethod
    def from_preset(cls, preset: str) -> Theme:
        return cls(PRESETS[preset])

    def _slot(self, section: str, key: str) -> dict:
        """The table that holds the value: the other variant's colors while that one is shown."""
        if section == "colors" and key in VARIANT_KEYS and self._other is not None:
            if self.shown is not None and self.shown != self._main:
                return self._other
        return self._values

    def get(self, section: str, key: str):
        slot = self._slot(section, key)
        return slot[key] if slot is self._other else slot[(section, key)]

    def set(self, section: str, key: str, value) -> None:
        field = FIELD_BY_ID.get((section, key))
        if field is None:
            raise ThemeError([translate("core", "Unknown key {key}.").format(key=f"{section}.{key}")])
        stored, problem = check_value(field, value)
        if problem:
            raise ThemeError([problem])
        if self._slot(section, key) is self._other:
            self._other[key] = stored
        else:
            self._values[field.id] = stored

    def resolved(self, section: str, key: str):
        """The value in effect: the field's own value, or the one it follows
        (which may itself follow another field)."""
        value = self.get(section, key)
        field = FIELD_BY_ID[(section, key)]
        if value is None and field.inherits:
            return self.resolved(*field.inherits)
        return value

    def part_state(self, section: str, key: str) -> str:
        """The state of a part that is left as it is, installed or generated: the value of the
        choice `section.key`, except that "installed" without the name of one (`<key>_id`) is
        "unchanged"."""
        state = self._values[(section, key)]
        if state == "installed" and not self._values.get((section, f"{key}_id")):
            return "unchanged"
        return state

    def unnamed_parts(self) -> list[tuple[str, str]]:
        """The parts that are set to "installed" without the name of the installed thing."""
        return [
            (section, key)
            for (section, key), value in self._values.items()
            if value == "installed" and not self._values.get((section, f"{key}_id"))
        ]

    def color(self, key: str) -> Color:
        return Color.parse(self.get("colors", key))

    # ---- light and dark variants --------------------------------------

    @property
    def has_both(self) -> bool:
        return self._other is not None

    @property
    def main_variant(self) -> str:
        """The variant the theme file's own [colors] hold."""
        from .variants import kind_of

        return self._main or kind_of(self._values[("colors", "window")])

    @property
    def shown_variant(self) -> str:
        """The variant the editor shows and an apply puts on the desktop."""
        return self.shown if self._other is not None and self.shown else self.main_variant

    @property
    def variants(self) -> tuple[str, ...]:
        """The variants the theme has, light first."""
        if self._other is None:
            return (self.main_variant,)
        return VARIANT_NAMES

    def show(self, variant: str | None) -> None:
        """Make the editor work on `variant`; a variant the theme does not have is ignored."""
        self.shown = variant if variant in self.variants else None

    def colors_of(self, variant: str) -> dict[str, object]:
        """The colors of one variant (keys of VARIANT_KEYS); empty when the theme has no such variant."""
        if variant == self.main_variant:
            return {key: self._values[("colors", key)] for key in VARIANT_KEYS}
        return dict(self._other) if self._other is not None else {}

    def for_variant(self, variant: str) -> Theme | None:
        """A copy of the theme that has only `variant`, or None when it has no such variant."""
        if variant not in self.variants:
            return None
        single = self.copy()
        single.shown = None
        if variant != self.main_variant:
            for key, value in (self._other or {}).items():
                single._values[("colors", key)] = value
        single._other = None
        single._main = None
        return single

    def add_variant(self) -> str:
        """Make the missing variant from the one the theme has, by the automatic conversion, and
        return its name. Does nothing and returns "" when the theme has both."""
        from .variants import convert, opposite

        if self._other is not None:
            return ""
        main = self.main_variant
        made = convert(
            {key: self._values[("colors", key)] for key in VARIANT_KEYS if key != "scheme_id"}, opposite(main)
        )
        other = {key: self._values[("colors", key)] for key in VARIANT_KEYS}
        other.update(made)
        other["scheme_id"] = None
        self._other, self._main = other, main
        return opposite(main)

    def remove_variant(self, variant: str) -> None:
        """Drop `variant`; the theme keeps the other one, which becomes its only colors."""
        if self._other is None or variant not in VARIANT_NAMES:
            return
        if variant == self._main:
            for key, value in self._other.items():
                self._values[("colors", key)] = value
        self._other = self._main = self.shown = None

    @property
    def scheme_title(self) -> str:
        """The name of the color scheme of the variant that is shown."""
        if self._other is None or self.shown_variant == self._main:
            return self.name
        return f"{self.name} {'Dark' if self.shown_variant == 'dark' else 'Light'}"

    @property
    def scheme_slug(self) -> str:
        return slugify(self.scheme_title)

    @property
    def name(self) -> str:
        return self._values[("meta", "name")].strip()

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def copy(self) -> Theme:
        other = Theme()
        other._values = dict(self._values)
        other._other = dict(self._other) if self._other is not None else None
        other._main = self._main
        other.shown = self.shown
        other.base_dir = self.base_dir
        other.pending_artwork = dict(self.pending_artwork)
        return other

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, Theme)
            and self._values == other._values
            and self._other == other._other
            and (self._main if self._other is not None else None)
            == (other._main if other._other is not None else None)
        )

    def problems(self) -> list[Msg]:
        """Problems that make the theme unusable even though each value is valid."""
        found = []
        if not self.slug:
            found.append(translate("core", "The theme needs a name that contains letters or digits."))
        if len(self.name) > MAX_NAME_LENGTH:
            found.append(
                translate("core", "The theme name must be at most {count} characters.").format(
                    count=MAX_NAME_LENGTH
                )
            )
        return found

    # ---- file format -------------------------------------------------

    def to_toml(self) -> str:
        lines = [f"schema_version = {SCHEMA_VERSION}"]
        for section in SECTIONS:
            values = [
                f"{field.key} = {_toml_value(self._values[field.id])}"
                for field in FIELDS
                if field.section == section
                and self._values[field.id] is not None
                and not (field.id == ("colors", "accent_from_wallpaper") and self._values[field.id] is False)
            ]
            if values:  # a section where everything is left unset is not written
                lines += ["", f"[{section}]", *values]
            if section == "colors" and self._other is not None:
                lines += ["", "[variant]", f"main = {_toml_value(self._main)}"]
                lines += ["", "[colors_other]"]
                lines += [
                    f"{key} = {_toml_value(self._other[key])}"
                    for key in VARIANT_KEYS
                    if self._other[key] is not None
                ]
        return "\n".join(lines) + "\n"

    @classmethod
    def from_toml(cls, text: str) -> Theme:
        try:
            data = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, RecursionError, ValueError) as error:
            # RecursionError: input nested deeper than the parser can follow.
            detail = str(error) if isinstance(error, tomllib.TOMLDecodeError) else "too deeply nested"
            raise ThemeError(
                [translate("core", "The file is not valid TOML: {detail}").format(detail=detail)]
            ) from error
        return cls.from_data(migrate(data))

    @classmethod
    def from_data(cls, data: dict) -> Theme:
        problems: list[Msg] = []
        theme = cls()
        for section, table in data.items():
            if section == "schema_version":
                continue
            if section in ("variant", "colors_other") and isinstance(table, dict):
                continue  # read below, after the main colors
            if section not in SECTIONS or not isinstance(table, dict):
                problems.append(translate("core", "Unknown section {key}.").format(key=section))
                continue
            for key, value in table.items():
                field = FIELD_BY_ID.get((section, key))
                if field is None:
                    problems.append(translate("core", "Unknown key {key}.").format(key=f"{section}.{key}"))
                    continue
                stored, problem = check_value(field, value)
                if problem:
                    problems.append(problem)
                else:
                    theme._values[field.id] = stored
        problems += theme._read_variants(data.get("variant"), data.get("colors_other"))
        problems += theme.problems()
        if problems:
            raise ThemeError(problems)
        return theme

    def _read_variants(self, variant, other) -> list[Msg]:
        """The optional `[variant]` and `[colors_other]` tables: the second variant of the colors."""
        problems: list[Msg] = []
        for section, table in (("variant", variant), ("colors_other", other)):
            if table is None:
                continue
            allowed = ("main",) if section == "variant" else VARIANT_KEYS
            for key in table:
                if key not in allowed:
                    problems.append(translate("core", "Unknown key {key}.").format(key=f"{section}.{key}"))
        if problems or other is None:
            return problems  # a main variant without a second one means nothing
        from .variants import convert, kind_of, opposite

        main = (variant or {}).get("main")
        if main is None:
            main = kind_of(self._values[("colors", "window")])
        elif main not in VARIANT_NAMES:
            return [translate("core", "{key} must be light or dark.").format(key="variant.main")]
        colors: dict[str, object] = {}
        for key, value in other.items():
            stored, problem = check_value(FIELD_BY_ID[("colors", key)], value)
            if problem:
                problems.append(problem)
            else:
                colors[key] = stored
        if problems:
            return problems
        made = convert(
            {key: self._values[("colors", key)] for key in VARIANT_KEYS if key != "scheme_id"},
            opposite(main),
        )
        full = {key: self._values[("colors", key)] for key in VARIANT_KEYS}
        full.update(made)
        full["scheme_id"] = None
        full.update(colors)
        self._other, self._main = full, main
        return []

    @classmethod
    def load(cls, path: Path) -> Theme:
        """Read a theme file. Files in an older format are upgraded in place,
        and the original is kept next to it as a backup."""
        from ..safefile import MAX_FILE, read_regular  # safefile needs kconfig, which needs this module

        try:
            raw = read_regular(path)
            if raw is None:
                if not path.exists():
                    raise OSError(translate("core", "The file does not exist."))
                if path.is_file() and path.stat().st_size > MAX_FILE:
                    raise OSError(translate("core", "The file is too large."))
                raise OSError(translate("core", "It is not a regular file that can be read."))
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ThemeError(
                [
                    translate("core", "Could not read {path}: {detail}").format(
                        path=str(path), detail=str(error)
                    )
                ]
            ) from error
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            raise ThemeError(
                [translate("core", "The file is not valid TOML: {detail}").format(detail=str(error))]
            ) from error
        original_version = data.get("schema_version")
        theme = cls.from_data(migrate(data))
        theme.base_dir = path.parent
        if original_version != SCHEMA_VERSION:
            shutil.copy2(path, path.with_name(f"{path.name}.v{original_version}.bak"))
            theme.save(path)
        return theme

    def save(self, path: Path) -> None:
        self._place_artwork(path)
        write_atomic(path, self.to_toml())
        self.base_dir = path.parent

    def _place_artwork(self, path: Path) -> None:
        """Put the artwork of the theme where the file at `path` expects it: what an archive brought
        into the folder of the file, and what a theme saved in another folder had next to the old file."""
        folder = artwork_folder(path)
        for key, data in self.pending_artwork.items():
            name = self._free_artwork_name(folder, key, data)
            self._values[("artwork", key)] = f"{folder.name}/{name}"
        self.pending_artwork = {}
        if self.base_dir is None or self.base_dir == path.parent:
            return
        from ..safefile import read_regular  # safefile needs kconfig, which needs this module

        base = self.base_dir.resolve()
        for key in ARTWORK_KEYS:
            name = self._values[("artwork", key)]
            if name is None:
                continue
            try:
                source = (base / name).resolve()
            except (OSError, RuntimeError):
                continue
            if not source.is_relative_to(base):  # a link must not lead the copy out of the folder
                continue
            data = read_regular(source, ARTWORK_LIMIT)
            if data is None:
                continue
            target = path.parent / name
            if not target.exists():
                write_atomic(target, data)
            elif read_regular(target, ARTWORK_LIMIT) != data:
                # Another picture of that name is there already: this one gets a free name.
                new_folder = artwork_folder(path)
                self._values[("artwork", key)] = (
                    f"{new_folder.name}/{self._free_artwork_name(new_folder, key, data)}"
                )

    @staticmethod
    def _free_artwork_name(folder: Path, key: str, data: bytes) -> str:
        """Write `data` as the artwork of `key` in `folder` and return the file name. A file that is
        already there with other content is never replaced: the new one gets the next free name."""
        number = 1
        while True:
            name = f"{key}.svg" if number == 1 else f"{key}-{number}.svg"
            target = folder / name
            if not target.exists():
                write_atomic(target, data)
                return name
            try:
                if target.is_file() and target.read_bytes() == data:
                    return name
            except OSError:
                pass
            number += 1


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, float):
        return repr(round(value, 4))
    return str(value)


# Each entry upgrades file data from the given version to the next one.
MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def migrate(data: dict) -> dict:
    version = data.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ThemeError([translate("core", "The file has no valid schema_version.")])
    if version > SCHEMA_VERSION:
        raise ThemeError(
            [
                translate(
                    "core",
                    "The file was made by a newer version of Plasma Theme Studio "
                    "(format {found}, this version reads up to format {supported}).",
                ).format(found=version, supported=SCHEMA_VERSION)
            ]
        )
    while version < SCHEMA_VERSION:
        data = MIGRATIONS[version](dict(data))
        version += 1
        data["schema_version"] = version
    return data


def write_atomic(path: Path, content: str | bytes) -> None:
    """Write a file so that a crash never leaves a half-written file behind."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    if path.is_symlink():
        # The file is kept somewhere else; it is written there and the link stays.
        try:
            path = path.resolve()
        except (OSError, RuntimeError):
            pass  # a link that leads nowhere is replaced by the file
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)  # a file that is replaced keeps its permissions
    except OSError:
        mask = os.umask(0)
        os.umask(mask)
        mode = 0o666 & ~mask  # what any newly made file gets
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name[:50]}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), mode)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
