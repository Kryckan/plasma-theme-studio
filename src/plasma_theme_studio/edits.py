# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a theme should change to follow something that is installed: a Global Theme or a color
scheme. Nothing is written here. The edits are `{(section, key): value}` for the caller to put into
a theme, with plain messages about what could not be carried over."""

from __future__ import annotations

from . import library
from .messages import translate
from .model.parts import FontSpec
from .model.theme import FONT_KEYS

Edits = dict[tuple[str, str], object]

# The parts that are named by an installed id: part id, the picker, the theme fields
# (the choice that becomes "installed" with its id field, or just the field), the name in messages.
_NAMED = (
    ("app_style", "app_style", ("apps", "style", "style_id")),
    ("plasma_style", "plasma_style", ("panel", "style", "style_id")),
    ("decoration", "decoration", ("window", "decoration", "decoration_id")),
    ("icons", "icons", ("desktop", "icons", None)),
    ("cursors", "cursors", ("desktop", "cursors", None)),
    ("splash", "splash", ("desktop", "splash", None)),
)


def _part_name(part: str) -> str:
    names = {
        "color_scheme": translate("core", "The color scheme"),
        "app_style": translate("core", "The application style"),
        "plasma_style": translate("core", "The Plasma style"),
        "decoration": translate("core", "The window decoration"),
        "icons": translate("core", "The icons"),
        "cursors": translate("core", "The pointers"),
        "splash": translate("core", "The splash screen"),
        "cursor_size": translate("core", "The pointer size"),
        "fonts": translate("core", "The fonts"),
    }
    return str(names[part])


def _items(kind_key: str) -> list:
    from .pickers import kind

    picker = kind(kind_key)
    return list(picker.items()) if picker else []


def theme_edits_from_color_scheme(scheme: library.InstalledScheme) -> tuple[Edits, list[str]]:
    """The colors of an installed scheme as edits. The colors the scheme file lacks are not in them."""
    edits: Edits = {}
    source = library.theme_from_scheme(scheme)
    edits[("colors", "scheme_id")] = scheme.id
    for key in scheme.colors:
        edits[("colors", key)] = source.get("colors", key)
    messages = []
    if len(scheme.colors) < len(library._SOURCES):
        missing = len(library._SOURCES) - len(scheme.colors)
        messages.append(
            str(
                translate(
                    "core", "{scheme} has no value for {count} of the colors, so those were left as they are."
                ).format(scheme=scheme.name, count=missing)
            )
        )
    return edits, messages


def theme_edits_from_global_theme(item) -> tuple[Edits, list[str]]:
    """What a Global Theme (an item of the Global Themes picker) sets, as edits that name the
    installed parts. A part that is not installed is left alone and said so."""
    from .pickers import globalthemes

    given = globalthemes.defaults(item)
    edits: Edits = {}
    messages: list[str] = []

    def missing(part: str, value) -> None:
        messages.append(
            str(
                translate(
                    "core", "{part} of {name}: {value} is not installed, so it was left as it is."
                ).format(part=_part_name(part), name=item.name, value=str(value))
            )
        )

    if "color_scheme" in given:
        found = globalthemes.resolve(given["color_scheme"], _items("color_scheme"))
        scheme = next((s for s in library.installed_schemes() if found and s.id == found.id), None)
        if scheme is None:
            missing("color_scheme", given["color_scheme"])
        else:
            colors, notes = theme_edits_from_color_scheme(scheme)
            edits.update(colors)
            messages += notes
    for part, kind_key, (section, key, id_key) in _NAMED:
        if part not in given:
            continue
        found = globalthemes.resolve(given[part], _items(kind_key))
        if found is None:
            missing(part, given[part])
        elif id_key:
            edits[(section, key)] = "installed"
            edits[(section, id_key)] = found.id
        else:
            edits[(section, key)] = found.id
    if "cursor_size" in given:
        if 8 <= given["cursor_size"] <= 256:
            edits[("desktop", "cursor_size")] = given["cursor_size"]
        else:
            messages.append(
                str(
                    translate("core", "{part} of {name}: {value} is not a size it can have.").format(
                        part=_part_name("cursor_size"), name=item.name, value=given["cursor_size"]
                    )
                )
            )
    for name in FONT_KEYS:
        text = given.get("fonts", {}).get(name)
        if text is None:
            continue
        spec = FontSpec.parse(text)
        if spec is None:
            missing("fonts", text)
        else:
            edits[("fonts", name)] = spec.short()
    return edits, messages
