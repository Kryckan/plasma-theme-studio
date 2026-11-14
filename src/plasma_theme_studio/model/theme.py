# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The theme file: its fields, validation, loading, saving and migration.

A theme is a TOML file with a `schema_version` and one table per section.
`FIELDS` is the single definition of what a theme contains. The UI builds
its controls from it and the file format follows it.
"""

from __future__ import annotations

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

    @property
    def id(self) -> tuple[str, str]:
        return (self.section, self.key)

    @property
    def path(self) -> str:
        return f"{self.section}.{self.key}"


PANEL_LOCATIONS = ("top", "bottom", "left", "right")
PANEL_VISIBILITIES = ("none", "autohide", "dodgewindows", "windowsgobelow")
PANEL_OPACITIES = ("adaptive", "opaque", "translucent")

FIELDS: tuple[Field, ...] = (
    Field("meta", "name", "str", "My Theme"),
    Field("meta", "author", "str", ""),
    Field("colors", "accent", "color", "#3daee9"),
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
    Field("apps", "style", "choice", "unchanged", choices=("unchanged", "generated")),
    Field("apps", "radius", "int", None, 0, 24, inherits=("shape", "radius")),
    Field("apps", "border_width", "int", None, 0, 4, inherits=("shape", "border_width")),
    Field("window", "decoration", "choice", "unchanged", choices=("unchanged", "breeze", "generated")),
    Field("window", "radius", "int", None, 0, 24, inherits=("shape", "radius")),
    Field("window", "border_width", "int", None, 0, 12, inherits=("shape", "border_width")),
    Field("shadow", "size", "int", 24, 0, 64),
    Field("shadow", "strength", "float", 0.35, 0.0, 1.0),
    Field("panel", "style", "choice", "unchanged", choices=("unchanged", "generated")),
    Field("panel", "radius", "int", None, 0, 24, inherits=("shape", "radius")),
    Field("panel", "border_width", "int", None, 0, 4, inherits=("shape", "border_width")),
    Field("panel", "opacity", "float", 0.85, 0.2, 1.0),
    Field("popup", "radius", "int", None, 0, 24, inherits=("panel", "radius")),
    Field("popup", "border_width", "int", None, 0, 4, inherits=("panel", "border_width")),
    Field("popup", "opacity", "float", None, 0.2, 1.0, inherits=("panel", "opacity")),
    Field("panel_layout", "location", "choice", None, choices=PANEL_LOCATIONS, optional=True),
    Field("panel_layout", "height", "int", None, 20, 120, optional=True),
    Field("panel_layout", "alignment", "choice", None, choices=("left", "center", "right"), optional=True),
    Field("panel_layout", "length_mode", "choice", None, choices=("fill", "fit"), optional=True),
    Field("panel_layout", "floating", "bool", None, optional=True),
    Field("panel_layout", "visibility", "choice", None, choices=PANEL_VISIBILITIES, optional=True),
    Field("panel_layout", "opacity_mode", "choice", None, choices=PANEL_OPACITIES, optional=True),
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


class Theme:
    def __init__(self, values: dict[tuple[str, str], object] | None = None):
        self._values: dict[tuple[str, str], object] = {f.id: f.default for f in FIELDS}
        for (section, key), value in (values or {}).items():
            self.set(section, key, value)

    @classmethod
    def from_preset(cls, preset: str) -> Theme:
        return cls(PRESETS[preset])

    def get(self, section: str, key: str):
        return self._values[(section, key)]

    def set(self, section: str, key: str, value) -> None:
        field = FIELD_BY_ID.get((section, key))
        if field is None:
            raise ThemeError([translate("core", "Unknown key {key}.").format(key=f"{section}.{key}")])
        stored, problem = check_value(field, value)
        if problem:
            raise ThemeError([problem])
        self._values[field.id] = stored

    def resolved(self, section: str, key: str):
        """The value in effect: the field's own value, or the one it follows
        (which may itself follow another field)."""
        value = self._values[(section, key)]
        field = FIELD_BY_ID[(section, key)]
        if value is None and field.inherits:
            return self.resolved(*field.inherits)
        return value

    def color(self, key: str) -> Color:
        return Color.parse(self._values[("colors", key)])

    @property
    def name(self) -> str:
        return self._values[("meta", "name")].strip()

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def copy(self) -> Theme:
        other = Theme()
        other._values = dict(self._values)
        return other

    def __eq__(self, other) -> bool:
        return isinstance(other, Theme) and self._values == other._values

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
                if field.section == section and self._values[field.id] is not None
            ]
            if values:  # a section where everything is left unset is not written
                lines += ["", f"[{section}]", *values]
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
        problems += theme.problems()
        if problems:
            raise ThemeError(problems)
        return theme

    @classmethod
    def load(cls, path: Path) -> Theme:
        """Read a theme file. Files in an older format are upgraded in place,
        and the original is kept next to it as a backup."""
        try:
            text = path.read_text(encoding="utf-8")
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
        if original_version != SCHEMA_VERSION:
            shutil.copy2(path, path.with_name(f"{path.name}.v{original_version}.bak"))
            theme.save(path)
        return theme

    def save(self, path: Path) -> None:
        write_atomic(path, self.to_toml())


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
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
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
