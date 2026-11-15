# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generates a Plasma style package that restyles the panel and popup backgrounds.

Everything the package does not contain comes from Plasma's default style.
Plasma does not notice edits to a style it already uses, so every look gets
a package of its own, named after what is in it.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import kconfig, paths
from ..messages import Msg, translate
from ..model.theme import ARTWORK_KEYS, Theme
from . import artwork
from .base import JSON_MARKER, MARKER, XML_MARKER, ApplyError, Generator, PlannedFile, made_here

ID_PREFIX = "PlasmaThemeStudio-"
# Bump when the generated artwork changes, so that existing packages are not reused.
DESIGN = 4

_CELL = 8  # width of the stretched middle of the frame
_SHADOW_TILE = 16
_SHADOW_MARGIN = 10  # how far the shadow reaches outside the panel
_SHADOW_PEAK = 0.2  # as dark as Breeze's
_BORDER_OPACITY = 0.22
_GAP = 4

_SIDES = ("top", "bottom", "left", "right")
_CORNERS = ("topleft", "topright", "bottomleft", "bottomright")
_FRAME_PARTS = (*_SIDES, *_CORNERS, "center")
# What every frame background has; the panel's also has the thick-* pieces.
POPUP_REQUIRED_IDS = frozenset(
    [
        *_FRAME_PARTS,
        *(f"mask-{part}" for part in _FRAME_PARTS),
        *(f"hint-{side}-margin" for side in _SIDES),
        *(f"shadow-{part}" for part in (*_SIDES, *_CORNERS)),
        *(f"shadow-hint-{side}-margin" for side in _SIDES),
    ]
)
REQUIRED_IDS = POPUP_REQUIRED_IDS | {"thick-center", *(f"thick-hint-{side}-margin" for side in _SIDES)}
PANEL_FILE = "widgets/panel-background.svg"
# Popups, launcher, notifications, KRunner and OSD; tooltips; desktop widgets.
POPUP_FILES = ("dialogs/background.svg", "widgets/tooltip.svg", "widgets/background.svg")
# The frames and the files of the style each one is: the keys of the theme's [artwork] section.
FRAME_FILES = {
    "panel": (PANEL_FILE,),
    "popups": ("dialogs/background.svg",),
    "tooltips": ("widgets/tooltip.svg",),
    "widgets": ("widgets/background.svg",),
}
assert tuple(FRAME_FILES) == ARTWORK_KEYS
_TOOLS = ("plasma-apply-desktoptheme", "kreadconfig6", "kwriteconfig6")
FRAME_TITLES = {
    "panel": translate("core", "the panel"),
    "popups": translate("core", "popups"),
    "tooltips": translate("core", "tooltips"),
    "widgets": translate("core", "widget backgrounds"),
}


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _look(theme: Theme) -> tuple[int, int, float]:
    return (
        int(theme.resolved("panel", "radius")),
        int(theme.resolved("panel", "border_width")),
        round(float(theme.get("panel", "opacity")), 3),
    )


def _popup_look(theme: Theme) -> tuple[int, int, float]:
    """Corner radius, border width and opacity of popups; they follow the panel until set."""
    return (
        int(theme.resolved("popup", "radius")),
        int(theme.resolved("popup", "border_width")),
        round(float(theme.resolved("popup", "opacity")), 3),
    )


def required_ids(frame: str) -> frozenset[str]:
    """The element ids Plasma needs in the SVG of `frame`."""
    return REQUIRED_IDS if frame == "panel" else POPUP_REQUIRED_IDS


def own_artwork(theme: Theme, frame: str) -> artwork.Artwork:
    """The own artwork of `frame`: unset, or read and checked (see `artwork.load`)."""
    return artwork.load(theme, frame, required_ids(frame))


def frame_svg(theme: Theme, frame: str, *, solid: bool = False) -> str:
    """The generated SVG of `frame` from the theme's values."""
    if frame == "panel":
        radius, border, opacity = _look(theme)
        return panel_svg(radius, border, opacity, solid=solid)
    radius, border, opacity = _popup_look(theme)
    return panel_svg(radius, border, opacity, solid=solid, thick=False)


def artwork_problems(theme: Theme) -> list[Msg]:
    """What is wrong with the own artwork the theme names, one sentence per frame and problem."""
    found: list[Msg] = []
    for frame in ARTWORK_KEYS:
        art = own_artwork(theme, frame)
        for problem in art.problems:
            found.append(
                translate(
                    "core", "Artwork for {frame} ({name}): {problem} The generated frame is used."
                ).format(frame=FRAME_TITLES[frame], name=art.name, problem=problem)
            )
    return found


def status_words(theme: Theme) -> str:
    """For the status of the Plasma Style part: which frames are drawn by hand, or "" when none is."""
    own = [FRAME_TITLES[frame] for frame in ARTWORK_KEYS if own_artwork(theme, frame).usable]
    if not own:
        return ""
    return str(translate("core", "own artwork for {frames}").format(frames=", ".join(str(t) for t in own)))


def style_id(theme: Theme) -> str:
    """The name of the package for the theme's panel and popup look."""
    radius, border, opacity = _look(theme)
    p_radius, p_border, p_opacity = _popup_look(theme)
    key = f"{DESIGN}/{radius}/{border}/{_num(opacity)}/{p_radius}/{p_border}/{_num(p_opacity)}"
    for frame in ARTWORK_KEYS:  # a frame drawn by hand is part of the look, so it gets a name of its own
        text = own_artwork(theme, frame).text
        if text is not None:
            key += f"/{frame}:{hashlib.sha256(text.encode()).hexdigest()}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:8]
    return f"{ID_PREFIX}{theme.slug}-{digest}"


def _package_dir(name: str) -> Path:
    return paths.data_home() / "plasma" / "desktoptheme" / name


def _corner(cx, cy, dx, dy, radius, size, inset=0) -> str:
    """The part of a size x size cell at the outer corner (cx, cy) that is
    inside a rounded corner, `inset` pixels in from the edges. (dx, dy) point
    from the corner into the cell."""

    def at(a, b):
        return f"{_num(cx + dx * a)},{_num(cy + dy * b)}"

    r = max(radius - inset, 0)
    path = f"M{at(size, inset)} L{at(size, size)} L{at(inset, size)} "
    if r > 0:
        sweep = 1 if dx * dy > 0 else 0
        return path + f"L{at(inset, inset + r)} A{_num(r)},{_num(r)} 0 0 {sweep} {at(inset + r, inset)} Z"
    return path + f"L{at(inset, inset)} Z"


def _rect(x, y, w, h, extra="") -> str:
    return f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}"{extra}/>'


def _frame(radius: int, border: int, size: int, ox: float, oy: float, *, prefix: str, body: float | None):
    """The nine parts of a frame laid out in a grid with its corner at (ox, oy).
    `body` is the fill opacity, or None for the opaque black shape of a mask."""
    n = _CELL
    total = 2 * size + n
    if body is None:
        fill = ' fill="#000"'
        ring = False
    else:
        fill = f' class="ColorScheme-Background" fill="currentColor" fill-opacity="{_num(body)}"'
        ring = border > 0
    ring_fill = f' class="ColorScheme-Text" fill="currentColor" fill-opacity="{_num(_BORDER_OPACITY)}"'

    def group(name, *shapes):
        return f'<g id="{prefix}{name}">{"".join(shapes)}</g>'

    parts = []
    for name, (right, bottom) in zip(_CORNERS, ((0, 0), (1, 0), (0, 1), (1, 1)), strict=True):
        args = (ox + right * total, oy + bottom * total, -1 if right else 1, -1 if bottom else 1)
        outer = _corner(*args, radius, size)
        shapes = [f'<path d="{outer}"{fill}/>']
        if ring:
            inner = _corner(*args, radius, size, border)
            shapes.append(f'<path fill-rule="evenodd" d="{outer} {inner}"{ring_fill}/>')
        parts.append(group(name, *shapes))
    sides = {
        "top": ((size, 0, n, size), (size, 0, n, border)),
        "bottom": ((size, size + n, n, size), (size, total - border, n, border)),
        "left": ((0, size, size, n), (0, size, border, n)),
        "right": ((size + n, size, size, n), (total - border, size, border, n)),
    }
    for name, (body_box, ring_box) in sides.items():
        shapes = [_rect(ox + body_box[0], oy + body_box[1], *body_box[2:], fill)]
        if ring:
            shapes.append(_rect(ox + ring_box[0], oy + ring_box[1], *ring_box[2:], ring_fill))
        parts.append(group(name, *shapes))
    parts.append(group("center", _rect(ox + size, oy + size, n, n, fill)))
    return parts


def _shadow(oy: float) -> tuple[list[str], list[str]]:
    """Gradient definitions and the eight shadow tiles in a grid at the left edge.

    A tile is wider than the shadow: its inner part lies under the panel, where
    the shadow must not show, because the panel can be translucent."""
    tile, reach = _SHADOW_TILE, _SHADOW_MARGIN
    under = tile - reach
    # Darkness by distance from the panel's edge, as a fraction of the reach.
    fade = [(0, 1), (1 / 3, 0.5), (0.5, 0.25), (7 / 12, 0.125), (1, 0)]

    inner = under / tile
    outer = reach / tile

    def stops(outside_first):
        """Stops along a gradient that crosses the tile. The outside of the
        tile is at the start when `outside_first`, otherwise at the end."""
        if outside_first:
            items = [(outer * (1 - at), value) for at, value in reversed(fade)]
            items += [(outer, 0), (1, 0)]
        else:
            items = [(0, 0), (inner, 0)] + [(inner + outer * at, value) for at, value in fade]
        return "".join(
            f'<stop offset="{_num(at)}" stop-color="#000" stop-opacity="{_num(value * _SHADOW_PEAK)}"/>'
            for at, value in items
        )

    defs = []
    for side, (x2, y2, outside_first) in {
        "top": (0, 1, True),
        "bottom": (0, 1, False),
        "left": (1, 0, True),
        "right": (1, 0, False),
    }.items():
        defs.append(
            f'<linearGradient id="sh-{side}" x1="0" y1="0" x2="{x2}" y2="{y2}">'
            f"{stops(outside_first)}</linearGradient>"
        )
    cells = {
        "topleft": (0, 0),
        "top": (1, 0),
        "topright": (2, 0),
        "left": (0, 1),
        "right": (2, 1),
        "bottomleft": (0, 2),
        "bottom": (1, 2),
        "bottomright": (2, 2),
    }
    # The tile corner next to the panel is where the fade starts, so that it joins
    # the side tiles without a step.
    origin = {
        "topleft": (1, 1),
        "topright": (0, 1),
        "bottomleft": (1, 0),
        "bottomright": (0, 0),
    }
    tiles = []
    for name, (col, row) in cells.items():
        x, y = col * tile, oy + row * tile
        if name not in origin:
            tiles.append(_rect(x, y, tile, tile, f' id="shadow-{name}" fill="url(#sh-{name})"'))
            continue
        cx, cy = origin[name][0] * tile, origin[name][1] * tile
        defs.append(
            f'<radialGradient id="sh-{name}" gradientUnits="userSpaceOnUse" '
            f'cx="{_num(x + cx)}" cy="{_num(y + cy)}" r="{tile}">{stops(False)}</radialGradient>'
        )
        # The square under the panel is left out, or a square panel corner would show the shadow.
        sx, sy = (1 if cx == 0 else -1) * under, (1 if cy == 0 else -1) * under
        points = [
            (cx + sx, cy),
            (tile - cx, cy),
            (tile - cx, tile - cy),
            (cx, tile - cy),
            (cx, cy + sy),
            (cx + sx, cy + sy),
        ]
        d = "M" + " L".join(f"{_num(x + px)},{_num(y + py)}" for px, py in points) + " Z"
        tiles.append(f'<path id="shadow-{name}" fill="url(#sh-{name})" d="{d}"/>')
    return defs, tiles


def panel_svg(radius: int, border: int, opacity: float, *, solid: bool, thick: bool = True) -> str:
    """The panel background, or with `thick` off a popup, tooltip or widget
    background: a frame with the corner radius and border width, its mask,
    its shadow and the margins Plasma reads from it. Coordinates are absolute
    and nothing is transformed, because KSvg cuts the parts out by their
    bounding boxes."""
    size = max(radius, border, 1)
    total = 2 * size + _CELL
    margin = max(border, round(radius * 0.3), 1)  # clears the rounded corner
    thick_margin = margin + 4  # the padding Plasma keeps between panel edge and applets

    body = 1.0 if solid else opacity
    mask_y = total + _GAP
    shadow_y = 2 * mask_y
    shadow_size = 3 * _SHADOW_TILE
    column = max(total, shadow_size) + _GAP

    elements = _frame(radius, border, size, 0, 0, prefix="", body=body)
    elements += _frame(radius, border, size, 0, mask_y, prefix="mask-", body=None)

    hints = []
    y = 0.0

    def hint(name, width, height):
        nonlocal y
        hints.append(
            f'<rect id="{name}" x="{column}" y="{_num(y)}" width="{_num(width)}" '
            f'height="{_num(height)}" fill="none"/>'
        )
        y += max(width, height) + _GAP

    prefixes = [("", margin)]
    if thick:
        prefixes.append(("thick-", thick_margin))
    prefixes.append(("shadow-", _SHADOW_MARGIN))
    for prefix, value in prefixes:
        if prefix == "thick-":
            hints.append(
                f'<rect id="thick-center" x="{column}" y="{_num(y)}" width="{_CELL}" '
                f'height="{_CELL}" fill="none"/>'
            )
            y += _CELL + _GAP
        for side in _SIDES:
            vertical = side in ("top", "bottom")
            hint(f"{prefix}hint-{side}-margin", 1 if vertical else value, value if vertical else 1)
    defs, tiles = _shadow(shadow_y)
    width = column + max(thick_margin, _CELL) + _GAP
    height = max(y, shadow_y + shadow_size)
    # What Plasma shows when the style is used before KSvg inserts the colors of
    # the scheme: Breeze Dark.
    style = (
        '<style id="current-color-scheme" type="text/css">'
        ".ColorScheme-Text{color:#fcfcfc}.ColorScheme-Background{color:#232629}</style>"
    )
    inner = "\n".join([style, f"<defs>{''.join(defs)}</defs>", *elements, *hints, *tiles])
    return (
        f"{XML_MARKER}\n"
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(width)}" height="{_num(height)}" '
        f'viewBox="0 0 {_num(width)} {_num(height)}">\n{inner}\n</svg>\n'
    )


def metadata_json(name: str, title: str) -> str:
    data = {
        "X-Generated-By": "Plasma Theme Studio",
        "KPackageStructure": "Plasma/Theme",
        "KPlugin": {
            "Authors": [{"Name": "Plasma Theme Studio"}],
            "Category": "",
            "Description": "Panel and popup backgrounds generated by Plasma Theme Studio",
            "EnabledByDefault": True,
            "Id": name,
            "License": "GPL-3.0-or-later",
            "Name": title,
            "Version": "1.0",
        },
        "X-Plasma-API": "5.0",
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


STYLE_KEY = ("plasmarc", ["Theme"], "name")


def _current_style(runner) -> str:
    return kconfig.effective_value(runner, "plasmarc", ["Theme"], "name", "default")


def _title_of(name: str) -> str:
    """The name System Settings shows for an installed style."""
    for base in (paths.data_home(), *paths.system_data_dirs()):
        try:
            data = json.loads((base / "plasma" / "desktoptheme" / name / "metadata.json").read_text("utf-8"))
            return str(data["KPlugin"]["Name"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return name


def _first_line(result) -> str:
    return (result.output.splitlines() or [""])[0][:200]


def _use_style(name: str, runner) -> None:
    result = runner.run(["plasma-apply-desktoptheme", name])
    # The tool prints "already set" and exits with 0 when nothing has to change.
    if result.returncode != 0 or _current_style(runner) != name:
        raise ApplyError(
            translate("core", "Plasma did not accept the style {name}. {detail}").format(
                name=name, detail=_first_line(result)
            )
        )


def stale_packages(keep: str | None) -> list[Path]:
    """The styles made here, with their files, except the package `keep`."""
    root = paths.data_home() / "plasma" / "desktoptheme"
    stale: list[Path] = []
    if not root.is_dir():
        return stale
    for package in sorted(root.glob(f"{ID_PREFIX}*")):
        if package.name == keep or not made_here(package / "metadata.json"):
            continue
        stale += [item for item in sorted(package.rglob("*")) if item.is_file() and made_here(item)]
        stale += [item for item in sorted(package.rglob("*")) if item.is_dir()]
        stale.append(package)
    return stale


class PlasmaStyleGenerator(Generator):
    id = "panel"
    title = translate("core", "Panel style")
    sections = ("panel", "popup", "artwork")

    def wanted(self, theme: Theme) -> bool:
        return theme.get("panel", "style") == "generated"

    def notes(self, theme: Theme) -> list[Msg]:
        if theme.part_state("panel", "style") == "installed":
            return []
        if not self.wanted(theme):
            return [
                translate(
                    "core",
                    "The panel keeps the Plasma style in use now. "
                    "The panel values here only show in the preview.",
                )
            ]
        notes = [
            translate(
                "core",
                "Only the backgrounds of the panel, popups, tooltips and desktop widgets are restyled. "
                "Menus and everything else keep the look of Plasma's default style, and the opacity "
                "applies while the background is translucent or adaptive.",
            )
        ]
        radius, border, _opacity = _look(theme)
        thinnest = 2 * max(radius, border, 1)
        if thinnest > 40:
            notes.append(
                translate(
                    "core", "With this corner radius the panel cannot be thinner than {pixels} pixels."
                ).format(pixels=thinnest)
            )
        return notes + artwork_problems(theme)

    def section_notes(self, theme: Theme, section: str) -> list[Msg]:
        if section == "artwork":
            return []  # the page of the panel style says it all
        if section != "popup":
            return self.notes(theme)
        if self.wanted(theme):
            return []
        if theme.part_state("panel", "style") == "installed":
            return [translate("core", "The installed Plasma style has its own popups and tooltips.")]
        return [
            translate(
                "core",
                'These values take effect when the panel background is "Made from this theme". '
                "Otherwise the Plasma style in use keeps its own popups.",
            )
        ]

    def unavailable_reason(self, runner) -> Msg | None:
        for tool in _TOOLS:
            if not runner.which(tool):
                return translate(
                    "core", "{tool} was not found. The panel style can only be applied in KDE Plasma 6."
                ).format(tool=tool)
        return None

    def files(self, theme: Theme) -> list[PlannedFile]:
        name = style_id(theme)
        root = _package_dir(name)
        radius, border, opacity = _look(theme)
        p_radius, p_border, p_opacity = _popup_look(theme)
        files = [
            PlannedFile(root / "metadata.json", metadata_json(name, theme.name), JSON_MARKER),
            PlannedFile(root / "plasmarc", f"{MARKER}\n\n[AdaptiveTransparency]\nenabled=true\n"),
        ]
        for frame, relatives in FRAME_FILES.items():
            own = own_artwork(theme, frame).text
            for relative in relatives:
                for solid in (False, True):
                    if own is not None:
                        svg = artwork.style_text(own)
                    elif frame == "panel":
                        svg = panel_svg(radius, border, opacity, solid=solid)
                    else:
                        svg = panel_svg(p_radius, p_border, p_opacity, solid=solid, thick=False)
                    files.append(PlannedFile(root / ("solid" if solid else "") / relative, svg, XML_MARKER))
        return files

    def check_output(self, file: PlannedFile) -> list[Msg]:
        if file.path.name == "metadata.json":
            try:
                plugin = json.loads(file.content)["KPlugin"]
            except (ValueError, KeyError, TypeError):
                return [translate("core", "The generated style description is not valid.")]
            if plugin.get("Id") != file.path.parent.name:
                return [translate("core", "The generated style has the wrong id.")]
            return []
        if file.path.suffix != ".svg":
            return []
        if artwork.OWN_MARK in file.content[:200]:
            return []  # drawn by hand: checked when it was read
        try:
            root = ET.fromstring(file.content)
        except ET.ParseError as error:
            return [
                translate("core", "The generated panel background is not valid: {detail}").format(
                    detail=str(error)
                )
            ]
        problems = []
        ids = {element.get("id") for element in root.iter()}
        relative = file.path.as_posix()
        required = REQUIRED_IDS if relative.endswith(PANEL_FILE) else POPUP_REQUIRED_IDS
        for missing in sorted(required - ids):
            problems.append(
                translate("core", "The generated panel background has no element {name}.").format(
                    name=missing
                )
            )
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "text" or any(key.lower().endswith("transform") for key in element.attrib):
                problems.append(
                    translate(
                        "core", "The generated panel background contains {name}, which it must not."
                    ).format(name=tag)
                )
                break
        return problems

    def stale_files(self, theme: Theme) -> list[Path]:
        return stale_packages(style_id(theme))

    def warnings(self, theme: Theme, runner) -> list[Msg]:
        found = artwork_problems(theme)
        current = _current_style(runner)
        if current in ("", "default") or current.startswith(ID_PREFIX):
            return found
        return found + [
            translate(
                "core",
                "The Plasma style {name} is in use. Except for the backgrounds of the panel, popups, "
                "tooltips and desktop widgets, it is replaced by Breeze's look.",
            ).format(name=_title_of(current))
        ]

    def is_active(self, theme: Theme, runner) -> bool:
        return _current_style(runner) == style_id(theme)

    def reload_command(self, theme: Theme) -> str:
        return f"plasma-apply-desktoptheme {style_id(theme)}"

    def capture_settings(self, runner) -> dict:
        return {
            "style": kconfig.user_value("plasmarc", ["Theme"], "name"),
            "masked": kconfig.masked("plasmarc", ["Theme"], "name"),
            "file": kconfig.file_exists("plasmarc"),
        }

    def reload(self, theme: Theme, runner) -> None:
        _use_style(style_id(theme), runner)

    def restore_settings(self, settings: dict, runner) -> None:
        self._restore_style(settings, runner)
        if settings.get("file") is False:
            # plasmarc was not there before; the style tool leaves an empty one behind.
            kconfig.drop_if_empty("plasmarc")

    def _restore_style(self, settings: dict, runner) -> None:
        previous = settings.get("style")
        masked = bool(settings.get("masked"))
        if kconfig.user_value(*STYLE_KEY) == previous and (previous or kconfig.masked(*STYLE_KEY) == masked):
            return  # nothing was changed, so Plasma is not asked to switch
        if previous:
            _use_style(previous, runner)
            return
        # The user's file had no value at all. Plasma is told to switch to the style that
        # applies without one: a global theme's, unless the user's file hid that. The tool
        # writes the name as a value, which is then taken away again.
        fallback = None if masked else kconfig.default_value(*STYLE_KEY)
        _use_style(fallback or "default", runner)
        kconfig.write_value(runner, *STYLE_KEY, None, masked=masked)
