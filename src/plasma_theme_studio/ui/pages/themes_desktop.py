# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A theme made from what the desktop uses now, for "New Theme from the Desktop". Nothing is written."""

from __future__ import annotations

from ... import desktopparts, edits, library, pickers
from ...generators.colorscheme import FALLBACK_SCHEME, current_scheme
from ...generators.installed import FONT_ROLES
from ...messages import translate
from ...model.parts import FontSpec
from ...pickers import globalthemes

# The parts that are named by an installed id: the edits' own table (`edits._NAMED`) and the part of
# the desktop each is read from.
_READ_FROM = {
    "app_style": "app_style",
    "plasma_style": "plasma_style",
    "decoration": "decoration",
    "icons": "icons",
    "cursors": "cursor_theme",
    "splash": "splash",
}


def _not_found(part: str, value) -> str:
    return str(
        translate(
            "ui", "{part} in use ({value}) is not in the list of what is installed, so it is left as it is."
        ).format(part=edits._part_name(part), value=str(value))
    )


def theme_edits_from_desktop(runner) -> tuple[edits.Edits, list[str]]:
    """What the desktop uses now as edits for a theme: the colors of its color scheme and, for every
    part that is chosen from what is installed, the installed id. A part that cannot be read, or is not
    in the lists, is left out and said so in the messages."""
    found: edits.Edits = {}
    messages: list[str] = []
    name = current_scheme(runner) or FALLBACK_SCHEME  # Plasma names none when it uses its own
    scheme = next(
        (
            s
            for s in library.installed_schemes()
            if name and name.casefold() in (s.id.casefold(), s.name.casefold())
        ),
        None,
    )
    if scheme is not None:
        colors, notes = edits.theme_edits_from_color_scheme(scheme)
        found.update(colors)
        messages += notes
    else:
        messages.append(_not_found("color_scheme", name or "?"))
    for part, kind_key, (section, key, id_key) in edits._NAMED:
        try:
            value = desktopparts.PARTS[_READ_FROM[part]].current(runner)
        except Exception:  # noqa: BLE001 - a part that cannot be read is left alone
            value = None
        picker = pickers.kind(kind_key)
        item = globalthemes.resolve(value, list(picker.items()) if picker else []) if value else None
        if item is None:
            messages.append(_not_found(part, value or "?"))
        elif id_key:
            found[(section, key)] = "installed"
            found[(section, id_key)] = item.id
        else:
            found[(section, key)] = item.id
    size = desktopparts.PARTS["cursor_size"].current(runner)
    if isinstance(size, int) and 8 <= size <= 256:
        found[("desktop", "cursor_size")] = size
    fonts = desktopparts.PARTS["fonts"].current(runner) or {}
    for key, role in FONT_ROLES.items():
        spec = FontSpec.parse(fonts.get(role, ""))
        if spec is not None:
            found[("fonts", key)] = spec.short()
    return found, messages
