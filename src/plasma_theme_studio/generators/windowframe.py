# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The window frame: KDE's Breeze decoration with what it can do, or a
generated Aurorae theme with the exact shape of the theme."""

from __future__ import annotations

import configparser
import hashlib
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from pathlib import Path

from .. import kconfig, paths
from ..apply import desktop
from ..messages import Msg, translate
from ..model.color import BLACK, WHITE, Color, readable_on
from ..model.theme import FIELD_BY_ID, Theme
from .base import MARKER, XML_MARKER, ApplyError, Generator, PlannedFile, made_here

FOLDER_PREFIX = "PlasmaThemeStudio-"
SHAPE_GROUP = "PlasmaThemeStudio"
AURORAE_LIBRARY = "org.kde.kwin.aurorae.v2"
AURORAE_THEME_PREFIX = "__aurorae__svg__"
BREEZE_LIBRARY = "org.kde.breeze"
BREEZE_THEME = "Breeze"

KWIN_FILE, KWIN_GROUP = "kwinrc", ["org.kde.kdecoration2"]
BREEZE_FILE, BREEZE_GROUP = "breezerc", ["Common"]
# Every setting this target can change: name -> (file, groups, key).
SETTINGS = {
    "library": (KWIN_FILE, KWIN_GROUP, "library"),
    "theme": (KWIN_FILE, KWIN_GROUP, "theme"),
    "border_size_auto": (KWIN_FILE, KWIN_GROUP, "BorderSizeAuto"),
    "border_size": (KWIN_FILE, KWIN_GROUP, "BorderSize"),
    "shadow_size": (BREEZE_FILE, BREEZE_GROUP, "ShadowSize"),
    "shadow_strength": (BREEZE_FILE, BREEZE_GROUP, "ShadowStrength"),
}

# Breeze's shadow sizes: key value, blur radius in px, plain name.
BREEZE_SHADOWS = (
    ("ShadowNone", 0, "none"),
    ("ShadowSmall", 16, "small"),
    ("ShadowMedium", 32, "medium"),
    ("ShadowLarge", 48, "large"),
    ("ShadowVeryLarge", 64, "very large"),
)
BREEZE_STRENGTH_RANGE = (25, 255)
# Breeze's border sizes: key value, width of the side borders in px, as measured in a running KWin.
BREEZE_BORDERS = (
    ("None", 0),
    ("Tiny", 2),
    ("Normal", 4),
    ("Large", 6),
    ("VeryLarge", 8),
    ("Huge", 10),
    ("VeryHuge", 12),
)

# Aurorae keeps the border of a window inside a range that depends on KWin's
# border size, so the size is chosen to contain the wanted width: name, widest border.
AURORAE_BORDERS = (("Tiny", 4), ("Normal", 6), ("Large", 8), ("VeryLarge", 12))

# Geometry of the generated frame, in pixels.
TITLE_HEIGHT = 22
TITLE_EDGE = 4
TITLE_TOTAL = TITLE_HEIGHT + 2 * TITLE_EDGE
BUTTON_SIZE = 22
BUTTON_SPACING = 4
# A corner of the window can only be as round as the border lets the square
# window content stay inside it: radius <= border * (2 + sqrt(2)); a little
# less keeps the content clear of the antialiased edge.
CORNER_PER_BORDER = 3.4
SLICE = 8  # the width or height of an edge element that is stretched

PARTS = ("topleft", "top", "topright", "left", "center", "right", "bottomleft", "bottom", "bottomright")
BUTTON_STATES = ("active", "hover", "pressed", "inactive", "deactivated")
BUTTON_FILES = (
    "close",
    "minimize",
    "maximize",
    "restore",
    "alldesktops",
    "keepabove",
    "keepbelow",
    "shade",
    "help",
    "appmenu",
)
# Buttons that stay switched on: Aurorae shows them with the "pressed" look.
TOGGLE_BUTTONS = ("alldesktops", "keepabove", "keepbelow", "shade")

RECONFIGURE = ["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"]
RECONFIGURE_BUSCTL = ["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"]
SUPPORT_INFORMATION = ["qdbus6", "org.kde.KWin", "/KWin", "supportInformation"]
PING_BUSCTL = ["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.freedesktop.DBus.Peer", "Ping"]


def _pause(seconds: float) -> None:
    desktop.pause(seconds)


def breeze_shadow_step(size: int) -> tuple[str, int, str]:
    """The Breeze shadow size nearest to `size` px (a tie goes to the bigger one)."""
    return min(reversed(BREEZE_SHADOWS), key=lambda step: abs(step[1] - size))


def breeze_strength(strength: float) -> int:
    low, high = BREEZE_STRENGTH_RANGE
    return low + round(min(1.0, max(0.0, strength)) * (high - low))


def breeze_border_size(width: int) -> tuple[str, str]:
    """Breeze's border size nearest to a width: the key value and a plain name.
    A visible border never rounds down to none."""
    if width <= 0:
        return "None", "no border"
    steps = BREEZE_BORDERS[1:]
    key, px = min(reversed(steps), key=lambda step: abs(step[1] - width))
    return key, f"{key}, {px} px"


def aurorae_border_size(width: int) -> str:
    if width <= 0:
        return "None"
    return next((name for name, widest in AURORAE_BORDERS if width <= widest), AURORAE_BORDERS[-1][0])


def bottom_radius(radius: int, border: int) -> int:
    """The radius the bottom corners can have: the window content stays square."""
    return min(radius, int(border * CORNER_PER_BORDER))


@dataclass(frozen=True)
class Look:
    """What decides how the generated frame looks."""

    radius: int
    border: int
    shadow: int
    strength: float
    header: Color
    window: Color
    text: Color
    muted: Color
    accent: Color
    negative: Color

    @classmethod
    def of(cls, theme: Theme) -> Look:
        return cls(
            radius=int(theme.resolved("window", "radius")),
            border=int(theme.resolved("window", "border_width")),
            shadow=int(theme.get("shadow", "size")),
            strength=float(theme.get("shadow", "strength")),
            header=theme.color("header"),
            window=theme.color("window"),
            text=theme.color("text"),
            muted=theme.color("text_muted"),
            accent=theme.color("accent"),
            negative=theme.color("negative"),
        )

    @property
    def bottom_radius(self) -> int:
        return bottom_radius(self.radius, self.border)

    # Widths and heights of the frame's pieces, shadow included. The side
    # pieces are as wide as the top corners are round; what lies under the
    # window content is never seen.
    @property
    def side(self) -> int:
        return max(self.radius, self.border, 1)

    @property
    def base(self) -> int:
        return max(self.bottom_radius, self.border, 1)

    @property
    def title_edge(self) -> int:
        return 6 + self.radius // 4


def _n(value: float) -> str:
    return str(int(value)) if float(value) == int(value) else f"{value:.3f}".rstrip("0").rstrip(".")


class _Pieces:
    """Collects the gradients and shapes of one SVG file."""

    STOPS = 8

    def __init__(self):
        self.defs: list[str] = []
        self.shapes: list[str] = []
        self._count = 0

    def _gradient(self, tag: str, attrs: str, offsets: list[tuple[float, float]]) -> str:
        self._count += 1
        name = f"g{self._count}"
        stops = "".join(
            f'<stop offset="{_n(round(offset, 4))}" stop-color="#000000" stop-opacity="{opacity:.3f}"/>'
            for offset, opacity in offsets
        )
        self.defs.append(f'<{tag} id="{name}" gradientUnits="userSpaceOnUse" {attrs}>{stops}</{tag}>')
        return name

    def _fade(self, alpha: float) -> list[float]:
        # Dark at the window and thinning out fast, the way a blurred shadow does.
        return [alpha * (1 - k / self.STOPS) ** 2 for k in range(self.STOPS + 1)]

    def shadow_strip(self, x, y, w, h, inner: str, alpha: float) -> str:
        """A rectangle whose shadow fades away from the window; `inner` names
        the side that touches the window: "top", "bottom", "left" or "right"."""
        x1, y1, x2, y2 = {
            "bottom": (x, y + h, x, y),
            "top": (x, y, x, y + h),
            "right": (x + w, y, x, y),
            "left": (x, y, x + w, y),
        }[inner]
        offsets = [(k / self.STOPS, a) for k, a in enumerate(self._fade(alpha))]
        name = self._gradient(
            "linearGradient", f'x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}"', offsets
        )
        return f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" fill="url(#{name})"/>'

    def shadow_corner(self, x, y, w, h, cx, cy, radius, extent, alpha: float) -> str:
        reach = radius + extent
        offsets = [(0.0, alpha)] if radius else []
        offsets += [((radius + k / self.STOPS * extent) / reach, a) for k, a in enumerate(self._fade(alpha))]
        name = self._gradient(
            "radialGradient",
            f'cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(reach)}" fx="{_n(cx)}" fy="{_n(cy)}"',
            offsets,
        )
        return f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" fill="url(#{name})"/>'


def _group(ident: str, x, y, w, h, shapes: list[str]) -> str:
    # The invisible rectangle fixes the bounds that Aurorae cuts the piece out with.
    box = f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" fill="none"/>'
    return f'<g id="{ident}">{box}{"".join(shapes)}</g>'


def _piece(
    pieces: _Pieces,
    look: Look,
    part: str,
    ident: str,
    x: float,
    y: float,
    title: Color,
    alpha: float,
) -> str:
    """One of the nine pieces of the frame at (x, y).

    Inside a piece the window's edge is where the shadow ends; the shadow runs
    along the outside. `p` is the shadow size, `r` the radius of the corner."""
    p, side, base, top = look.shadow, look.side, look.base, TITLE_TOTAL
    fc = look.window.hex
    tc = title.hex
    column = {"topleft": 0, "left": 0, "bottomleft": 0, "top": 1, "center": 1, "bottom": 1}.get(part, 2)
    row = {"topleft": 0, "top": 0, "topright": 0, "left": 1, "center": 1, "right": 1}.get(part, 2)
    w = SLICE if column == 1 else p + side
    h = SLICE if row == 1 else (p + top if row == 0 else p + base)
    shapes: list[str] = []

    def rect(rx, ry, rw, rh, color):
        shapes.append(
            f'<rect x="{_n(x + rx)}" y="{_n(y + ry)}" width="{_n(rw)}" height="{_n(rh)}" fill="{color}"/>'
        )

    def path(d, color):
        shapes.append(f'<path d="{d}" fill="{color}"/>')

    def strip(rx, ry, rw, rh, inner):
        if p and rw > 0 and rh > 0:
            shapes.append(pieces.shadow_strip(x + rx, y + ry, rw, rh, inner, alpha))

    def corner(rx, ry, rw, rh, cx, cy, radius):
        if p and rw > 0 and rh > 0:
            shapes.append(pieces.shadow_corner(x + rx, y + ry, rw, rh, x + cx, y + cy, radius, p, alpha))

    def arc(radius, to):
        # Always clockwise on the screen: every corner is traced that way.
        return f"A{_n(radius)} {_n(radius)} 0 0 1 {_n(x + to[0])} {_n(y + to[1])}"

    r, rb = look.radius, look.bottom_radius
    if part == "topleft":
        corner(0, 0, p + r, p + r, p + r, p + r, r)
        strip(
            p + r,
            0,
            side - r,
            p,
            "bottom",
        )
        strip(0, p + r, p, top - r, "right")
        d = f"M{_n(x + p)} {_n(y + p + r)} "
        d += arc(r, (p + r, p)) + " " if r else f"L{_n(x + p)} {_n(y + p)} "
        path(d + f"H{_n(x + p + side)} V{_n(y + p + top)} H{_n(x + p)} Z", tc)
    elif part == "topright":
        corner(side - r, 0, p + r, p + r, side - r, p + r, r)
        strip(0, 0, side - r, p, "bottom")
        strip(side, p + r, p, top - r, "left")
        d = f"M{_n(x)} {_n(y + p)} H{_n(x + side - r)} "
        d += arc(r, (side, p + r)) + " " if r else f"L{_n(x + side)} {_n(y + p)} "
        path(d + f"V{_n(y + p + top)} H{_n(x)} Z", tc)
    elif part == "bottomleft":
        corner(0, base - rb, p + rb, rb + p, p + rb, base - rb, rb)
        strip(p + rb, base, side - rb, p, "top")
        strip(0, 0, p, base - rb, "right")
        d = f"M{_n(x + p)} {_n(y)} H{_n(x + p + side)} V{_n(y + base)} "
        d += f"H{_n(x + p + rb)} " + arc(rb, (p, base - rb)) if rb else f"H{_n(x + p)} "
        path(d + " Z", fc)
    elif part == "bottomright":
        corner(side - rb, base - rb, p + rb, rb + p, side - rb, base - rb, rb)
        strip(0, base, side - rb, p, "top")
        strip(side, 0, p, base - rb, "left")
        d = f"M{_n(x)} {_n(y)} H{_n(x + side)} V{_n(y + base - rb)} "
        d += arc(rb, (side - rb, base)) + " " if rb else f"V{_n(y + base)} "
        path(d + f"H{_n(x)} Z", fc)
    elif part == "top":
        strip(0, 0, w, p, "bottom")
        rect(0, p, w, top, tc)
    elif part == "bottom":
        rect(0, 0, w, base, fc)
        strip(0, base, w, p, "top")
    elif part == "left":
        strip(0, 0, p, h, "right")
        rect(p, 0, side, h, fc)
    elif part == "right":
        rect(0, 0, side, h, fc)
        strip(side, 0, p, h, "left")
    else:
        rect(0, 0, w, h, fc)
    return _group(ident, x, y, w, h, shapes)


def _decoration_svg(look: Look) -> str:
    pieces = _Pieces()
    p, side, base = look.shadow, look.side, look.base
    column = [p + side, SLICE, p + side]
    row = [p + TITLE_TOTAL, SLICE, p + base]
    total_w, total_h = sum(column), sum(row)
    variants = (
        ("decoration", look.header, look.strength),
        ("decoration-inactive", look.window, look.strength * 0.5),
    )
    groups = []
    for index, (prefix, title, alpha) in enumerate(variants):
        left = index * (total_w + 4)
        for number, part in enumerate(PARTS):
            col, line = number % 3, number // 3
            x, y = left + sum(column[:col]), sum(row[:line])
            groups.append(_piece(pieces, look, part, f"{prefix}-{part}", x, y, title, alpha))
    # Maximized windows have no borders and no shadow: a plain title bar.
    flat_y = total_h + 4
    for index, (prefix, color) in enumerate(
        (("decoration-maximized", look.header), ("decoration-maximized-inactive", look.window))
    ):
        x = index * (total_w + 4)
        shape = f'<rect x="{x}" y="{flat_y}" width="16" height="{TITLE_TOTAL}" fill="{color.hex}"/>'
        groups.append(_group(f"{prefix}-center", x, flat_y, 16, TITLE_TOTAL, [shape]))
    width, height = 2 * total_w + 4, flat_y + TITLE_TOTAL
    return _svg(width, height, pieces.defs, groups)


def _svg(width, height, defs: list[str], groups: list[str]) -> str:
    return (
        f"{XML_MARKER}\n"
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f"<defs>{''.join(defs)}</defs>\n" + "\n".join(groups) + "\n</svg>\n"
    )


def _glyph(name: str, x: float, y: float, color: Color) -> str:
    """The symbol of a button inside the 22 px cell at (x, y), as strokes."""

    def p(d):
        return (
            f'<path d="{d}" fill="none" stroke="{color.hex}" stroke-width="1.6" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )

    def at(px, py):
        return f"{_n(x + px)} {_n(y + py)}"

    if name == "close":
        return p(f"M{at(6.5, 6.5)} L{at(15.5, 15.5)} M{at(15.5, 6.5)} L{at(6.5, 15.5)}")
    if name == "minimize":
        return p(f"M{at(6, 14)} L{at(16, 14)}")
    if name == "maximize":
        return p(f"M{at(6, 6)} H{_n(x + 16)} V{_n(y + 16)} H{_n(x + 6)} Z")
    if name == "restore":
        back = f"M{at(8.5, 8)} V{_n(y + 5.5)} H{_n(x + 16.5)} V{_n(y + 13.5)} H{_n(x + 14)}"
        return p(back) + p(f"M{at(5.5, 8.5)} H{_n(x + 13.5)} V{_n(y + 16.5)} H{_n(x + 5.5)} Z")
    if name == "alldesktops":
        centre = f'cx="{_n(x + 11)}" cy="{_n(y + 11)}"'
        ring = f'<circle {centre} r="5.2" fill="none" stroke="{color.hex}" stroke-width="1.6"/>'
        return ring + f'<circle {centre} r="1.8" fill="{color.hex}"/>'
    if name == "keepabove":
        return p(f"M{at(6, 13.5)} L{at(11, 8.5)} L{at(16, 13.5)}")
    if name == "keepbelow":
        return p(f"M{at(6, 8.5)} L{at(11, 13.5)} L{at(16, 8.5)}")
    if name == "shade":
        return p(f"M{at(6, 6.5)} H{_n(x + 16)}") + p(f"M{at(7, 10.5)} L{at(11, 14.5)} L{at(15, 10.5)}")
    if name == "appmenu":
        return p(
            f"M{at(5.5, 7)} H{_n(x + 16.5)} M{at(5.5, 11)} H{_n(x + 16.5)} M{at(5.5, 15)} H{_n(x + 16.5)}"
        )
    # help: a question mark made of a hook and a dot
    hook = f"M{at(8.4, 9)} C{at(8.4, 6.6)} {at(10, 6)} {at(11, 6)}"
    hook += f" C{at(12.4, 6)} {at(13.8, 6.9)} {at(13.8, 8.7)}"
    hook += f" C{at(13.8, 10.9)} {at(11, 10.9)} {at(11, 13)}"
    return p(hook) + f'<circle cx="{_n(x + 11)}" cy="{_n(y + 16)}" r="1.1" fill="{color.hex}"/>'


def _button_svg(look: Look, name: str) -> str:
    cell = BUTTON_SIZE
    close = name == "close"
    toggle = name in TOGGLE_BUTTONS
    text, muted, header = look.text, look.muted, look.header
    hover_bg = look.negative if close else header.mix(text, 0.14)
    pressed_bg = (
        look.negative.mix(BLACK, 0.2) if close else (look.accent if toggle else header.mix(text, 0.26))
    )
    states = {
        "active": (None, text),
        "hover": (hover_bg, readable_on(hover_bg, dark=text, light=WHITE) if close else text),
        "pressed": (
            pressed_bg,
            readable_on(pressed_bg, dark=look.text, light=WHITE) if (close or toggle) else text,
        ),
        "inactive": (None, muted),
        "deactivated": (None, header.mix(muted, 0.4)),
    }
    groups = []
    for index, state in enumerate(BUTTON_STATES):
        x = index * (cell + 2)
        background, glyph = states[state]
        shapes = []
        if background is not None:
            shapes.append(
                f'<circle cx="{x + cell / 2:g}" cy="{cell / 2:g}" r="{cell / 2 - 1:g}" '
                f'fill="{background.hex}"/>'
            )
        shapes.append(_glyph(name, x, 0, glyph))
        groups.append(_group(f"{state}-center", x, 0, cell, cell, shapes))
    return _svg(len(BUTTON_STATES) * (cell + 2), cell, [], groups)


def _rc(look: Look) -> str:
    edge = look.title_edge
    values = [
        ("[General]", None),
        ("ActiveTextColor", look.text.kde),
        ("InactiveTextColor", look.muted.kde),
        ("TitleAlignment", "Center"),
        ("TitleVerticalAlignment", "Center"),
        ("Animation", 100),
        ("", None),
        ("[Layout]", None),
        ("BorderLeft", look.border),
        ("BorderRight", look.border),
        ("BorderBottom", look.border),
        ("BorderTop", 0),
        ("TitleEdgeTop", TITLE_EDGE),
        ("TitleEdgeBottom", TITLE_EDGE),
        ("TitleEdgeLeft", edge),
        ("TitleEdgeRight", edge),
        ("TitleEdgeTopMaximized", TITLE_EDGE),
        ("TitleEdgeBottomMaximized", TITLE_EDGE),
        ("TitleEdgeLeftMaximized", 6),
        ("TitleEdgeRightMaximized", 6),
        ("TitleBorderLeft", 6),
        ("TitleBorderRight", 6),
        ("TitleHeight", TITLE_HEIGHT),
        ("ButtonWidth", BUTTON_SIZE),
        ("ButtonHeight", BUTTON_SIZE),
        ("ButtonSpacing", BUTTON_SPACING),
        ("ButtonMarginTop", 0),
        ("ButtonMarginTopMaximized", 0),
        ("ExplicitButtonSpacer", 10),
        ("PaddingLeft", look.shadow),
        ("PaddingRight", look.shadow),
        ("PaddingTop", look.shadow),
        ("PaddingBottom", look.shadow),
        ("", None),
        # The shape, for the next apply: a theme that leaves the frame alone recolors it.
        # Aurorae ignores groups it does not know.
        (f"[{SHAPE_GROUP}]", None),
        ("Radius", look.radius),
        ("Border", look.border),
        ("ShadowSize", look.shadow),
        ("ShadowStrength", repr(float(look.strength))),
    ]
    lines = [MARKER]
    for key, value in values:
        lines.append(key if value is None else f"{key}={value}")
    return "\n".join(lines) + "\n"


def _metadata(name: str, folder: str) -> str:
    return (
        f"{MARKER}\n[Desktop Entry]\nName={name}\n"
        "X-KDE-PluginInfo-Author=Plasma Theme Studio\n"
        "X-KDE-PluginInfo-Category=\nX-KDE-PluginInfo-Depends=\n"
        f"X-KDE-PluginInfo-Name={folder}\nX-KDE-PluginInfo-Version=1.0\n"
        "X-KDE-PluginInfo-License=GPL\nX-KDE-PluginInfo-EnabledByDefault=true\n"
    )


def frame_contents(look: Look) -> dict[str, str]:
    """The content of every file of the generated frame, by file name,
    except the metadata (it carries the folder name)."""
    files = {"decoration.svg": _decoration_svg(look)}
    files.update({f"{name}.svg": _button_svg(look, name) for name in BUTTON_FILES})
    return files


def _folder_name(theme: Theme, look: Look) -> str:
    """The folder name of a generated frame. KWin keeps a theme by its name,
    so the name changes with everything that decides how the frame looks."""
    digest = hashlib.sha256(theme.name.encode())
    digest.update(_rc(look).encode())
    for name, content in sorted(frame_contents(look).items()):
        digest.update(name.encode() + b"\0" + content.encode())
    return f"{FOLDER_PREFIX}{theme.slug}-{digest.hexdigest()[:8]}"


def frame_folder(theme: Theme) -> str:
    """The folder name of the frame that the theme puts on the desktop."""
    target = frame_to_generate(theme)
    return target[1] if target else _folder_name(theme, Look.of(theme))


def frame_to_generate(theme: Theme) -> tuple[Look, str] | None:
    """The look and folder of the frame an apply of the theme generates, or None for
    none. A theme that asks for a generated frame gets its own. A theme that leaves
    the frame alone while one of ours is in use gets that frame's shape in its colors."""
    mode = theme.part_state("window", "decoration")
    if mode == "generated":
        look = Look.of(theme)
        return look, _folder_name(theme, look)
    if mode != "unchanged":
        return None
    shape = frame_in_use_shape()
    if shape is None:
        return None
    radius, border, shadow, strength = shape
    look = replace(Look.of(theme), radius=radius, border=border, shadow=shadow, strength=strength)
    return look, _folder_name(theme, look)


def _themes_root() -> Path:
    return paths.data_home() / "aurorae" / "themes"


def _in_range(value: float, section: str, key: str) -> bool:
    field = FIELD_BY_ID[(section, key)]
    return math.isfinite(value) and field.minimum <= value <= field.maximum


def _shape_ok(radius: int, border: int, shadow: int, strength: float) -> bool:
    return (
        _in_range(radius, "window", "radius")
        and _in_range(border, "window", "border_width")
        and _in_range(shadow, "shadow", "size")
        and _in_range(strength, "shadow", "strength")
    )


def _frame_folder_in_use() -> Path | None:
    """The folder of the frame of ours that kwinrc selects, if it was made here."""
    if kconfig.user_value(KWIN_FILE, KWIN_GROUP, "library") != AURORAE_LIBRARY:
        return None
    name = kconfig.user_value(KWIN_FILE, KWIN_GROUP, "theme") or ""
    if not name.startswith(AURORAE_THEME_PREFIX + FOLDER_PREFIX):
        return None
    folder = name.removeprefix(AURORAE_THEME_PREFIX)
    if "/" in folder or "\\" in folder or folder in (".", ".."):
        return None
    path = _themes_root() / folder
    if path.is_symlink() or not path.is_dir() or not made_here(path / "metadata.desktop"):
        return None
    return path


def frame_in_use_shape() -> tuple[int, int, int, float] | None:
    """Radius, border, shadow size and shadow strength of the frame of ours that the
    desktop uses, or None when it uses another frame or this one cannot be read."""
    path = _frame_folder_in_use()
    if path is None:
        return None
    try:
        shape = _shape_from_rc(path)
        if shape is None:
            shape = _shape_from_files(path)
    except (OSError, UnicodeDecodeError, ValueError, ET.ParseError, configparser.Error, KeyError):
        return None
    if shape is None or not _shape_ok(*shape):
        return None
    return shape


def _read_rc(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string((path / f"{path.name}rc").read_text(encoding="utf-8"))
    return parser


def _shape_from_rc(path: Path) -> tuple[int, int, int, float] | None:
    parser = _read_rc(path)
    if not parser.has_section(SHAPE_GROUP):
        return None
    group = parser[SHAPE_GROUP]
    return (
        int(group["Radius"]),
        int(group["Border"]),
        int(group["ShadowSize"]),
        float(group["ShadowStrength"]),
    )


def _shape_from_files(path: Path) -> tuple[int, int, int, float] | None:
    """The shape of a folder written before the rc had a group for it."""
    layout = _read_rc(path)["Layout"]
    border, shadow = int(layout["BorderLeft"]), int(layout["PaddingLeft"])
    root = ET.fromstring((path / "decoration.svg").read_text(encoding="utf-8"))
    corner = next((e for e in root.iter() if e.get("id") == "decoration-topleft"), None)
    if corner is None:
        return None
    shape = next((e for e in corner.iter() if _local(e.tag) == "path"), None)
    if shape is None:
        return None
    arc = re.search(r"A\s*([0-9.]+)[ ,]+([0-9.]+)", shape.get("d", ""))
    radius = 0.0
    if arc:
        radius = float(arc.group(1))
        if radius != float(arc.group(2)) or radius != int(radius):
            return None
    strength = FIELD_BY_ID[("shadow", "strength")].default
    if shadow:
        stop = next((e for e in root.iter() if _local(e.tag) == "stop"), None)
        if stop is not None:
            strength = float(stop.get("stop-opacity", ""))
    return int(radius), border, shadow, float(strength)


REQUIRED_DECORATION = tuple(
    f"{prefix}-{part}" for prefix in ("decoration", "decoration-inactive") for part in PARTS
) + ("decoration-maximized-center", "decoration-maximized-inactive-center")
REQUIRED_BUTTON = tuple(f"{state}-center" for state in BUTTON_STATES)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def stale_frames(keep: str | None) -> list[Path]:
    """The frames made here, folder by folder with their files, except the folder `keep`."""
    root = _themes_root()
    if not root.is_dir():
        return []
    stale: list[Path] = []
    for folder in sorted(root.glob(f"{FOLDER_PREFIX}*")):
        if folder.is_symlink() or not folder.is_dir() or folder.name == keep:
            continue
        if not made_here(folder / "metadata.desktop"):
            continue
        stale += [f for f in sorted(folder.iterdir()) if f.is_file() and made_here(f)]
        stale.append(folder)
    return stale


class WindowFrameGenerator(Generator):
    id = "window"
    title = translate("core", "Window frame")
    sections = ("window", "shadow")

    # ---- what the theme asks for --------------------------------------

    @staticmethod
    def mode(theme: Theme) -> str:
        return theme.part_state("window", "decoration")

    def wanted(self, theme: Theme) -> bool:
        # An installed decoration is the business of its own target, which also removes the frames made here.
        mode = self.mode(theme)
        return mode in ("breeze", "generated") or frame_to_generate(theme) is not None

    def notes(self, theme: Theme) -> list[Msg]:
        mode = self.mode(theme)
        if mode == "installed":
            return []
        if mode == "unchanged":
            if frame_to_generate(theme) is not None:
                return [
                    translate(
                        "core",
                        "The desktop uses a window frame made by this app. It keeps its shape and gets "
                        "this theme's colors.",
                    )
                ]
            return [
                translate(
                    "core",
                    "The window frame is left as it is. The window and shadow values only show in "
                    "the preview until you choose a frame.",
                )
            ]
        if mode == "breeze":
            return self._breeze_frame_notes(theme) + self._breeze_shadow_notes(theme)
        return self._generated_notes(theme)

    def section_notes(self, theme: Theme, section: str) -> list[Msg]:
        mode = self.mode(theme)
        if mode == "installed":
            return []
        if section != "shadow":
            return self._breeze_frame_notes(theme) if mode == "breeze" else self.notes(theme)
        if mode == "unchanged":
            if frame_to_generate(theme) is not None:
                return [translate("core", "The window frame in use keeps its shadow.")]
            return [
                translate(
                    "core",
                    "The shadow only shows in the preview until you choose a window frame on the "
                    "Windows page.",
                )
            ]
        if mode == "breeze":
            return self._breeze_shadow_notes(theme)
        return [translate("core", "The generated window frame draws this shadow, the same on all sides.")]

    def _breeze_shadow_notes(self, theme: Theme) -> list[Msg]:
        _key, px, name = breeze_shadow_step(int(theme.get("shadow", "size")))
        if px == 0:
            return [translate("core", "Breeze will draw no shadow.")]
        return [
            translate(
                "core",
                "Breeze only has fixed shadow sizes. The shadow will use the step {step} ({px} px).",
            ).format(step=name, px=px)
        ]

    def _breeze_frame_notes(self, theme: Theme) -> list[Msg]:
        _border, border_name = breeze_border_size(int(theme.resolved("window", "border_width")))
        notes = [
            translate(
                "core",
                "Breeze fixes the corner radius. Choose the generated frame for an exact radius.",
            )
        ]
        if theme.get("window", "border_size") is not None:
            notes.append(
                translate(
                    "core",
                    "The border size you chose on the Windows page is used instead of the one "
                    "that follows the border width.",
                )
            )
        elif border_name == "no border":
            notes.append(translate("core", "Breeze will draw no border."))
        else:
            notes.append(
                translate(
                    "core",
                    "Breeze only has fixed border widths. The border will use the step {step}.",
                ).format(step=border_name)
            )
        return notes

    def _generated_notes(self, theme: Theme) -> list[Msg]:
        look = Look.of(theme)
        notes = []
        if look.bottom_radius >= look.radius:
            notes.append(
                translate("core", "All four corners of the window frame get the radius {radius} px.").format(
                    radius=look.radius
                )
            )
        elif look.bottom_radius == 0:
            notes.append(
                translate(
                    "core",
                    "KWin does not clip the window's own content, so with a {border} px border the bottom "
                    "corners stay square. The top corners get the radius {radius} px.",
                ).format(border=look.border, radius=look.radius)
            )
        else:
            notes.append(
                translate(
                    "core",
                    "KWin does not clip the window's own content, so with a {border} px border the bottom "
                    "corners can only be rounded by {bottom} px. The top corners get the radius "
                    "{radius} px. A wider border allows rounder bottom corners.",
                ).format(border=look.border, bottom=look.bottom_radius, radius=look.radius)
            )
        notes.append(
            translate(
                "core",
                "The frame colors are fixed in the frame. Apply the theme again after you change them.",
            )
        )
        if theme.get("window", "border_size") is not None:
            notes.append(
                translate(
                    "core",
                    "The frame draws its own border, but KWin's border size is the one you chose, so "
                    "the border may be narrower or wider than {border} px.",
                ).format(border=look.border)
            )
        else:
            notes.append(
                translate(
                    "core",
                    "KWin's border size is set to {size} so that the border is exactly {border} px wide.",
                ).format(size=aurorae_border_size(look.border), border=look.border)
            )
        return notes

    # ---- files ----------------------------------------------------------

    def files(self, theme: Theme) -> list[PlannedFile]:
        target = frame_to_generate(theme)
        if target is None:
            return []
        look, folder = target
        root = _themes_root() / folder
        planned = [PlannedFile(root / "metadata.desktop", _metadata(theme.name, folder))]
        planned.append(PlannedFile(root / f"{folder}rc", _rc(look)))
        for name, content in frame_contents(look).items():
            planned.append(PlannedFile(root / name, content, XML_MARKER))
        return planned

    def stale_files(self, theme: Theme) -> list[Path]:
        target = frame_to_generate(theme)
        return stale_frames(target[1] if target else None)

    def check_output(self, file: PlannedFile) -> list[Msg]:
        name = file.path.name
        if name.endswith(".svg"):
            return self._check_svg(file)
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.optionxform = str
        try:
            parser.read_string(file.content)
        except configparser.Error as error:
            return [
                translate("core", "The generated window frame file {name} is not valid: {detail}").format(
                    name=name, detail=str(error).splitlines()[0]
                )
            ]
        required = {"metadata.desktop": ("Desktop Entry",)}.get(name, ("General", "Layout"))
        return [
            translate("core", "The generated window frame file {name} has no [{group}] group.").format(
                name=name, group=group
            )
            for group in required
            if not parser.has_section(group)
        ]

    def _check_svg(self, file: PlannedFile) -> list[Msg]:
        name = file.path.name
        try:
            root = ET.fromstring(file.content)
        except ET.ParseError as error:
            return [
                translate("core", "The generated window frame file {name} is not valid: {detail}").format(
                    name=name, detail=str(error)
                )
            ]
        problems = []
        ids = {element.get("id") for element in root.iter()}
        required = REQUIRED_DECORATION if name == "decoration.svg" else REQUIRED_BUTTON
        for ident in required:
            if ident not in ids:
                problems.append(
                    translate(
                        "core", "The generated window frame file {name} has no element {ident}."
                    ).format(name=name, ident=ident)
                )
        if any(_local(element.tag) == "text" for element in root.iter()):
            problems.append(
                translate("core", "The generated window frame file {name} must not contain text.").format(
                    name=name
                )
            )
        return problems

    # ---- the desktop ----------------------------------------------------

    def unavailable_reason(self, runner) -> Msg | None:
        for tool in ("kreadconfig6", "kwriteconfig6"):
            if not runner.which(tool):
                return translate(
                    "core", "{tool} was not found. The window frame can only be applied in KDE Plasma 6."
                ).format(tool=tool)
        if not runner.which("qdbus6") and not runner.which("busctl"):
            return translate(
                "core",
                "Neither qdbus6 nor busctl was found, so KWin cannot be asked to reload the window frame.",
            )
        return None

    def reload_command(self, theme: Theme) -> str:
        return " ".join(RECONFIGURE)

    def changed_settings(self, theme: Theme) -> list[Msg]:
        if frame_to_generate(theme) is not None:
            return [translate("core", "which window frame KWin uses and its border size (kwinrc)")]
        return [
            translate(
                "core",
                "the border size of the window frame (kwinrc) and the shadow of Breeze (breezerc)",
            )
        ]

    def _decoration(self, runner) -> tuple[str, str]:
        library = kconfig.effective_value(runner, KWIN_FILE, KWIN_GROUP, "library", BREEZE_LIBRARY)
        theme = kconfig.effective_value(runner, KWIN_FILE, KWIN_GROUP, "theme", BREEZE_THEME)
        return library, theme

    def warnings(self, theme: Theme, runner) -> list[Msg]:
        library, name = self._decoration(runner)
        ours = library == AURORAE_LIBRARY and name.startswith(AURORAE_THEME_PREFIX + FOLDER_PREFIX)
        if library == BREEZE_LIBRARY or ours:
            return []
        shown = name.removeprefix(AURORAE_THEME_PREFIX) if library == AURORAE_LIBRARY else library
        return [
            translate(
                "core",
                "The window frame {name} is in use. It will be replaced by the frame of this theme.",
            ).format(name=shown or library)
        ]

    def _wanted_settings(self, theme: Theme) -> dict[str, str]:
        width = int(theme.resolved("window", "border_width"))
        target = frame_to_generate(theme)
        if target is not None:
            look, folder = target
            wanted = {
                "library": AURORAE_LIBRARY,
                "theme": AURORAE_THEME_PREFIX + folder,
                "border_size_auto": "false",
                "border_size": aurorae_border_size(look.border),
            }
        else:
            wanted = {
                "library": BREEZE_LIBRARY,
                "theme": BREEZE_THEME,
                "border_size_auto": "false",
                "border_size": breeze_border_size(width)[0],
                "shadow_size": breeze_shadow_step(int(theme.get("shadow", "size")))[0],
                "shadow_strength": str(breeze_strength(float(theme.get("shadow", "strength")))),
            }
        if theme.get("window", "border_size") is not None:
            # The border size the theme chose is set by its own target, whatever the frame is.
            del wanted["border_size_auto"], wanted["border_size"]
        return wanted

    def is_active(self, theme: Theme, runner) -> bool:
        wanted = self._wanted_settings(theme)
        decoration = (wanted.pop("library"), wanted.pop("theme"))
        # Without a value anywhere, KWin uses Breeze.
        if self._decoration(runner) != decoration:
            return False
        for name, value in wanted.items():
            file, groups, key = SETTINGS[name]
            if kconfig.effective_value(runner, file, groups, key) != value:
                return False
        return True

    def capture_settings(self, runner) -> dict:
        settings: dict = {
            name: kconfig.user_value(file, groups, key) for name, (file, groups, key) in SETTINGS.items()
        }
        # Keys whose default from Plasma's own layer the user's file hides.
        settings["masked"] = [
            name for name, (file, groups, key) in SETTINGS.items() if kconfig.masked(file, groups, key)
        ]
        return settings

    def reload(self, theme: Theme, runner) -> None:
        wanted = self._wanted_settings(theme)
        target = frame_to_generate(theme)  # before kwinrc changes: it reads the frame in use
        if self.mode(theme) == "breeze":
            # Breeze is already in use when nothing in the user's files says otherwise.
            if self._decoration(runner) == (BREEZE_LIBRARY, BREEZE_THEME):
                del wanted["library"], wanted["theme"]
        for name, value in wanted.items():
            file, groups, key = SETTINGS[name]
            kconfig.write_value(runner, file, groups, key, value)
        _reconfigure(runner)
        library = wanted.get("library", BREEZE_LIBRARY)
        folder = target[1] if target else None
        _check_decoration(runner, library, folder)

    def restore_settings(self, settings: dict, runner) -> None:
        failure = None
        masked = settings.get("masked") or ()
        for name, (file, groups, key) in SETTINGS.items():
            if name not in settings:
                continue
            try:
                kconfig.write_value(runner, file, groups, key, settings[name], masked=name in masked)
            except ApplyError as error:
                failure = failure or error
        try:
            _reconfigure(runner)
        except ApplyError as error:
            # A KWin that does not answer at all is not running, or cannot be reached from
            # here. The settings are back in its file, which is all it reads when it starts.
            if _kwin_answers(runner):
                failure = failure or error
        if failure:
            raise failure


def _reconfigure(runner) -> None:
    """Ask KWin to read its settings again. It takes a moment to do it."""
    argv = RECONFIGURE if runner.which("qdbus6") else RECONFIGURE_BUSCTL
    result = runner.run(argv)
    if result.returncode != 0:
        detail = (result.output.splitlines() or [""])[0][:200]
        raise ApplyError(
            translate("core", "KWin could not be asked to reload the window frame. {detail}").format(
                detail=detail
            )
        )


def _kwin_answers(runner) -> bool:
    """Whether a KWin can be reached at all, with the tool that would ask it to reload."""
    if runner.which("qdbus6"):
        return runner.run(SUPPORT_INFORMATION).returncode == 0
    if runner.which("busctl"):
        return runner.run(PING_BUSCTL).returncode == 0
    return True  # nothing to ask with, so nothing says that the failed reload does not matter


def _decoration_report(runner) -> dict[str, str]:
    """The "Decoration" part of KWin's support information, as key and value."""
    if not runner.which("qdbus6"):
        return {}
    result = runner.run(SUPPORT_INFORMATION)
    if result.returncode != 0:
        return {}
    report: dict[str, str] = {}
    inside = False
    for line in result.stdout.splitlines():
        if line.strip() == "Decoration":
            inside = True
        elif inside and not line.strip():
            break
        elif inside and ": " in line:
            key, value = line.split(": ", 1)
            report[key.strip()] = value.strip()
    return report


def _check_decoration(runner, library: str, folder: str | None) -> None:
    """Read back what KWin uses. The settings file is only read by KWin after a
    short delay, and a frame that cannot be loaded is replaced by another one."""
    report: dict[str, str] = {}
    for attempt in range(10):
        report = _decoration_report(runner)
        plugin = report.get("Plugin")
        if plugin is None:
            return  # KWin does not say; the settings were read back already
        if plugin == library and (folder is None or folder in report.get("Theme", folder)):
            return
        if attempt < 9:
            _pause(0.3)
    raise ApplyError(
        translate("core", "KWin did not switch to the new window frame. It still uses {name}.").format(
            name=report.get("Theme") or report.get("Plugin", "")
        )
    )
