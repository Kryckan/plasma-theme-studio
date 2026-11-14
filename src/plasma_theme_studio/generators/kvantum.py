# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generates a Kvantum theme so that corner radius and border width reach the
buttons, fields, menus and tabs of Qt applications.

Kvantum draws every widget from the elements of one SVG file. Applications do
not reread a theme whose files change under the same name, so every look gets
a folder of its own, named after what is in it, and the style is switched away
and back when the theme is applied.
"""

from __future__ import annotations

import functools
import hashlib
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import kconfig, paths
from ..apply import desktop
from ..messages import Msg, translate
from ..model.color import Color
from ..model.theme import Theme, write_atomic
from .base import MARKER, XML_MARKER, ApplyError, Generator, PlannedFile, made_here

ID_PREFIX = "PlasmaThemeStudio-"
STYLE_NAME = "kvantum"
# A control's height grows with the size of its frame, so its corner stops growing here.
CONTROL_CAP = 8
# The theme folder is only ever named for what it holds.
STYLE_KEY = ("kdeglobals", ["KDE"], "widgetStyle")
# How long the style stays on its stand-in while applications drop the old Kvantum theme.
HOP_PAUSE = 0.4
HOP_STYLE = "fusion"
PLUGIN = "libkvantum.so"


def config_dir() -> Path:
    return paths.config_home() / "Kvantum"


def selection_file() -> Path:
    """Kvantum's own file that names the theme in use."""
    return config_dir() / "kvantum.kvconfig"


# ---------------------------------------------------------------- colors


def _mix(a: str, b: str, amount: float) -> str:
    return Color.parse(a).mix(Color.parse(b), amount).hex


def _on(background: str) -> str:
    """A readable text color for a background."""
    return "#ffffff" if Color.parse(background).luminance < 0.4 else "#000000"


def look_of(theme: Theme) -> tuple[dict[str, str], int, int]:
    """The colors, corner radius and border width the style is made from."""
    colors = {key: theme.color(key).hex for key in ("accent", "window", "view", "button", "header", "text")}
    colors["text_muted"] = theme.color("text_muted").hex
    return (
        colors,
        int(theme.resolved("apps", "radius")),
        int(theme.resolved("apps", "border_width")),
    )


# ---------------------------------------------------------------- SVG pieces


def _n(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


class _Path:
    """A path in a size x size cell that can be mirrored, for the four corners."""

    def __init__(self, size: float, flip_x: bool = False, flip_y: bool = False):
        self.size, self.flip_x, self.flip_y, self.parts = size, flip_x, flip_y, []

    def _at(self, x: float, y: float) -> str:
        return f"{_n(self.size - x if self.flip_x else x)},{_n(self.size - y if self.flip_y else y)}"

    def move(self, x, y) -> None:
        self.parts.append(f"M{self._at(x, y)}")

    def line(self, x, y) -> None:
        self.parts.append(f"L{self._at(x, y)}")

    def arc(self, radius, x, y) -> None:
        sweep = 1 if self.flip_x == self.flip_y else 0
        self.parts.append(f"A{_n(radius)},{_n(radius)} 0 0 {sweep} {self._at(x, y)}")

    def text(self) -> str:
        return " ".join(self.parts) + " Z"


def _corner(size: float, radius: float, inset: float, flip_x: bool, flip_y: bool) -> str:
    """A quarter of a rounded rectangle (the top left one, mirrored as asked)
    inside a size x size cell, `inset` pixels in from the edges."""
    inner = max(radius - inset, 0.0)
    path = _Path(size, flip_x, flip_y)
    path.move(inset, size)
    path.line(inset, inset + inner)
    if inner > 0:
        path.arc(inner, inset + inner, inset)
    path.line(size, inset)
    path.line(size, size)
    return path.text()


def _rect_path(x, y, w, h) -> str:
    return f"M{_n(x)},{_n(y)} h{_n(w)} v{_n(h)} h{_n(-w)} Z"


def _fill(d: str, color: str, opacity: float = 1.0, evenodd: bool = False) -> str:
    extra = ' fill-rule="evenodd"' if evenodd else ""
    alpha = "" if opacity >= 1 else f' fill-opacity="{_n(opacity)}"'
    return f'<path fill="{color}"{alpha}{extra} d="{d}"/>'


def _rounded(x, y, w, h, radius, color, stroke=None, width=0.0) -> str:
    radius = min(radius, w / 2, h / 2)
    line = f' stroke="{stroke}" stroke-width="{_n(width)}"' if stroke and width > 0 else ""
    return (
        f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" '
        f'rx="{_n(radius)}" fill="{color}"{line}/>'
    )


PIECES = ("top", "bottom", "left", "right", "topleft", "topright", "bottomleft", "bottomright")
_EDGE = 8.0  # length of the stretched edge pieces; Kvantum scales them


def _pieces(size, radius, border, fill, line, open_bottom=False) -> dict[str, tuple[str, float, float]]:
    """The eight pieces of a frame drawn at `size` px. `fill` is the color inside the
    border (None leaves it empty) and `line` the border color. A frame with an open
    bottom (the selected tab) has no border along its lower edge and square lower corners."""
    radius = min(radius, size)
    out = {}
    for name in PIECES:
        flip_x, flip_y = "right" in name, "bottom" in name
        lower = flip_y
        square = open_bottom and lower
        if name in ("top", "bottom"):
            w, h = _EDGE, size
            outer = _rect_path(0, 0, w, h)
            if square:
                inner = outer
            else:
                inner = (
                    _rect_path(0, border, w, h - border) if name == "top" else _rect_path(0, 0, w, h - border)
                )
        elif name in ("left", "right"):
            w, h = size, _EDGE
            outer = _rect_path(0, 0, w, h)
            inner = (
                _rect_path(border, 0, w - border, h) if name == "left" else _rect_path(0, 0, w - border, h)
            )
        else:
            w = h = size
            if square:
                outer = _corner(size, 0, 0, flip_x, flip_y)
                inner = _side_corner(size, border, flip_x)
            else:
                outer = _corner(size, radius, 0, flip_x, flip_y)
                inner = _corner(size, radius, border, flip_x, flip_y)
        if fill is None:
            body = _fill(f"{outer} {inner}", line, evenodd=True) if border > 0 else ""
        elif border > 0:
            body = _fill(outer, line) + _fill(inner, fill)
        else:
            body = _fill(outer, fill)
        if not body:  # keeps the element and its size, draws nothing
            body = _fill(outer, "#000000", 0.0)
        out[name] = (body, w, h)
    return out


def _side_corner(size: float, border: float, flip_x: bool) -> str:
    """A square corner without border along the lower edge, with the side border kept."""
    x = 0 if flip_x else border
    return _rect_path(x, 0, size - border, size)


class _Svg:
    """Collects the elements; each one gets a place of its own so that none overlap."""

    def __init__(self):
        self.items: list[str] = []
        self.y = 0.0

    def add(self, element_id: str, body: str, height: float) -> None:
        self.items.append(f'<g id="{element_id}" transform="translate(0,{_n(self.y)})">{body}</g>')
        self.y += height + 4

    def frame(self, base, state, size, radius, border, fill, line, interior=True, open_bottom=False) -> None:
        """`<base>-<state>` (the interior) and its eight pieces."""
        element = f"{base}-{state}"
        if interior and fill is not None:
            self.add(element, _fill(_rect_path(0, 0, 8, 8), fill), 8)
        for name, (body, _w, h) in _pieces(size, radius, border, fill, line, open_bottom).items():
            self.add(f"{element}-{name}", body, h)

    def text(self) -> str:
        body = "\n".join(self.items)
        head = f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="{int(self.y) + 1}">'
        return f"{XML_MARKER}\n{head}\n{body}\n</svg>\n"


def _arrow(direction: str, color: str, size: int = 16) -> str:
    c, t = size / 2, size * 0.22
    points = {
        "up": [(c - t * 1.3, c + t * 0.6), (c, c - t * 0.7), (c + t * 1.3, c + t * 0.6)],
        "down": [(c - t * 1.3, c - t * 0.6), (c, c + t * 0.7), (c + t * 1.3, c - t * 0.6)],
        "left": [(c + t * 0.6, c - t * 1.3), (c - t * 0.7, c), (c + t * 0.6, c + t * 1.3)],
        "right": [(c - t * 0.6, c - t * 1.3), (c + t * 0.7, c), (c - t * 0.6, c + t * 1.3)],
    }[direction]
    d = "M{:.2f},{:.2f} L{:.2f},{:.2f} L{:.2f},{:.2f}".format(*(v for p in points for v in p))
    # The invisible square gives the element a fixed size.
    return (
        f'<path fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" '
        f'stroke-linejoin="round" d="{d}"/>' + _fill(_rect_path(0, 0, size, size), "#000", 0.0)
    )


def _tick(color: str, size: int) -> str:
    d = (
        f"M{size * 0.26:.2f},{size * 0.52:.2f} L{size * 0.43:.2f},{size * 0.68:.2f} "
        f"L{size * 0.74:.2f},{size * 0.32:.2f}"
    )
    return (
        f'<path fill="none" stroke="{color}" stroke-width="{max(1.5, size * 0.12):.2f}" '
        f'stroke-linecap="round" stroke-linejoin="round" d="{d}"/>'
    )


def _sizes(radius: int, border: int) -> dict[str, int]:
    """The frame sizes: containers take the whole radius, controls are capped, and small parts
    (scroll bar handle, progress bar) stay thin."""
    return {
        "container": max(radius, border, 1),
        "control": max(min(radius, CONTROL_CAP), border, 1),
        "small": max(min(radius, 6), border, 1),
    }


def make_svg(colors: dict[str, str], radius: int, border: int) -> str:
    """The SVG file of the style. Nothing is drawn by hand: every element is computed
    from the colors, the radius and the border width."""
    accent, window, view, button = colors["accent"], colors["window"], colors["view"], colors["button"]
    header, text, muted = colors["header"], colors["text"], colors["text_muted"]
    on_accent = _on(accent)
    edge = _mix(window, text, 0.22)
    soft = _mix(window, text, 0.18)
    hover = _mix(button, text, 0.10)
    press = _mix(button, accent, 0.55)
    size = _sizes(radius, border)
    big, ctl, small = size["container"], size["control"], size["small"]
    r_ctl = min(radius, ctl)
    svg = _Svg()

    # Buttons and tool buttons. A tool button is flat until it is hovered.
    states = {
        "normal": (button, edge),
        "focused": (hover, accent),
        "pressed": (press, accent),
        "toggled": (accent, accent),
    }
    for state, (fill, line) in states.items():
        svg.frame("button", state, ctl, r_ctl, border, fill, line)
    for state in ("focused", "pressed", "toggled"):
        fill, line = states[state]
        svg.frame(
            "tbutton", state, ctl, r_ctl, border, _mix(window, fill, 0.5 if state != "toggled" else 1), line
        )
    # Fields. The focused field always has a visible ring.
    focus_border = max(border, 1)
    svg.frame("lineedit", "normal", ctl, r_ctl, border, view, edge)
    svg.frame("lineedit", "focused", ctl, r_ctl, focus_border, view, accent)
    # Frames that have no fill of their own get a faint one when there is no border to show them.
    faint = None if border > 0 else _mix(window, text, 0.05)
    for base in ("common", "group", "tabframe"):
        svg.frame(base, "normal", big, radius, border, faint, soft, interior=False)
    # Tabs. The selected one is open at the bottom and joins the tab frame.
    svg.frame("tab", "normal", ctl, r_ctl, border, _mix(window, text, 0.06), soft)
    svg.frame("tab", "focused", ctl, r_ctl, border, _mix(window, text, 0.10), accent)
    svg.frame("tab", "toggled", ctl, r_ctl, focus_border, window, accent, open_bottom=True)
    # Headers, tool tips and menus.
    svg.frame("header", "normal", 2, 0, 0, header, header)
    svg.frame("tooltip", "normal", big, radius, focus_border, _mix(window, text, 0.08), edge)
    svg.frame("menu", "normal", big, radius, focus_border, window, edge)
    for base in ("menuitem", "menubaritem"):
        for state in ("focused", "pressed", "toggled"):
            svg.frame(base, state, max(min(radius, 8), 2), min(radius, 8), 0, accent, accent)
    for state in ("focused", "pressed", "toggled"):
        fill = _mix(view, accent, 0.5 if state == "focused" else 0.85)
        svg.frame("itemview", state, 2, min(radius, 2), 0, fill, accent)
    # Progress bar: the filled part follows the groove's corners.
    groove_radius = min(radius, small)
    inner = max(groove_radius - border, 0)
    svg.frame("progress", "normal", small, groove_radius, border, _mix(window, text, 0.12), soft)
    svg.frame("progress-pattern", "normal", small, inner, 0, accent, accent)
    svg.frame("progress-pattern", "disabled", small, inner, 0, _mix(window, muted, 0.5), muted)
    # Slider groove and scroll bar.
    svg.frame("slider", "normal", 3, 3, 0, _mix(window, text, 0.18), _mix(window, text, 0.18))
    svg.frame("slider", "toggled", 3, 3, 0, accent, accent)
    svg.frame("scrollbargroove", "normal", 2, 0, 0, _mix(window, text, 0.04), _mix(window, text, 0.04))
    handle = max(min(radius, 6), 2)
    for state, fill in (
        ("normal", _mix(window, text, 0.30)),
        ("focused", _mix(window, text, 0.42)),
        ("pressed", accent),
    ):
        svg.frame("scrollbarslider", state, handle, min(radius, handle), 0, fill, fill)
    # Check boxes and radio buttons, 16 px.
    box = 16
    box_radius = min(radius, 5)
    line_width = max(border, 1)
    for state in ("normal", "focused"):
        line = edge if state == "normal" else accent
        shape = _rounded(
            0.5 + line_width / 2,
            0.5 + line_width / 2,
            box - 1 - line_width,
            box - 1 - line_width,
            box_radius,
            view,
            line,
            line_width,
        )
        svg.add(f"checkbox-{state}", shape, box)
        ring = (
            f'<circle cx="8" cy="8" r="{7.5 - line_width / 2 + 0.5:.2f}" fill="{view}" '
            f'stroke="{line}" stroke-width="{line_width}"/>'
        )
        svg.add(f"radio-{state}", ring, box)
        full = _rounded(0.5, 0.5, box - 1, box - 1, box_radius, accent, line, border)
        svg.add(f"checkbox-checked-{state}", full + _tick(on_accent, box), box)
        dash = f'<rect x="4" y="7.2" width="8" height="1.6" rx=".8" fill="{on_accent}"/>'
        svg.add(f"checkbox-tristate-{state}", full + dash, box)
        dot = f'<circle cx="8" cy="8" r="3.4" fill="{accent}"/>'
        svg.add(f"radio-checked-{state}", ring + dot, box)
    # Slider handle: its corners follow the radius up to a circle.
    handle_radius = min(radius, 8)
    for state, fill in (
        ("normal", accent),
        ("focused", _mix(accent, text, 0.2)),
        ("pressed", _mix(accent, text, 0.35)),
        ("disabled", muted),
    ):
        svg.add(f"slidercursor-{state}", _rounded(0.5, 0.5, 15, 15, max(handle_radius, 2), fill), 16)
    for direction in ("up", "down", "left", "right"):
        svg.add(f"arrow-{direction}-normal", _arrow(direction, text), 16)
        svg.add(f"arrow-{direction}-pressed", _arrow(direction, on_accent), 16)
    return svg.text()


# ---------------------------------------------------------------- kvconfig


def _frame(size: int) -> str:
    return f"frame.top={size}\nframe.bottom={size}\nframe.left={size}\nframe.right={size}\n"


def make_kvconfig(colors: dict[str, str], radius: int, border: int) -> str:
    """The .kvconfig file of the style: the colors and which element draws what."""
    text, accent, window, view, button = (
        colors["text"],
        colors["accent"],
        colors["window"],
        colors["view"],
        colors["button"],
    )
    on_accent = _on(accent)
    size = _sizes(radius, border)
    big, ctl, small = size["container"], size["control"], size["small"]
    handle = max(min(radius, 6), 2)
    pad = max(0, 6 - ctl)
    return f"""{MARKER}
[%General]
author=Plasma Theme Studio
comment=Made from a theme: corner radius {radius}, border width {border}
composite=true
menu_shadow_depth=0
tooltip_shadow_depth=0
alt_mnemonic=true
left_tabs=false
attach_active_tab=true
group_toolbar_buttons=false
groupbox_top_label=true
spread_progressbar=true
spread_menuitems=true
splitter_width=6
scroll_width=12
scroll_min_extent=40
scroll_arrows=false
combo_as_lineedit=true
inline_spin_indicators=true
slider_width=6
slider_handle_width=16
slider_handle_length=16
check_size=16
toolbar_icon_size=16
animate_states=false
transient_scrollbar=false
transient_groove=false
progressbar_thickness=18
fill_rubberband=true
layout_spacing=6
layout_margin=8
submenu_overlap=0
vertical_spin_indicators=false

[GeneralColors]
window.color={window}
base.color={view}
alt.base.color={_mix(view, window, 0.5)}
button.color={button}
light.color={_mix(button, "#ffffff", 0.15)}
mid.light.color={_mix(button, "#ffffff", 0.08)}
dark.color={_mix(window, "#000000", 0.3)}
mid.color={_mix(window, "#000000", 0.15)}
highlight.color={accent}
inactive.highlight.color={_mix(accent, window, 0.5)}
text.color={text}
window.text.color={text}
button.text.color={text}
disabled.text.color={colors["text_muted"]}
tooltip.text.color={text}
highlight.text.color={on_accent}
link.color={accent}
link.visited.color={_mix(accent, text, 0.4)}

[Hacks]
transparent_ktitle_label=true
respect_darkness=true

[PanelButtonCommand]
frame=true
frame.element=button
{_frame(ctl)}interior=true
interior.element=button
indicator.size=9
indicator.element=arrow
text.normal.color={text}
text.focus.color={text}
text.press.color={on_accent}
text.toggle.color={on_accent}
text.shadow=0
text.margin=1
text.iconspacing=4
text.margin.top={pad}
text.margin.bottom={pad}
text.margin.left={pad + 4}
text.margin.right={pad + 4}

[PanelButtonTool]
inherits=PanelButtonCommand
interior.element=tbutton
frame.element=tbutton
text.margin.left={pad}
text.margin.right={pad}

[Dock]
inherits=PanelButtonCommand
frame=false
interior=false

[DockTitle]
inherits=PanelButtonCommand
frame=false
interior=false
text.bold=true

[IndicatorSpinBox]
inherits=PanelButtonCommand
indicator.element=arrow
indicator.size=9
{_frame(ctl)}
[RadioButton]
inherits=PanelButtonCommand
frame=false
interior.element=radio

[CheckBox]
inherits=PanelButtonCommand
frame=false
interior.element=checkbox

[GenericFrame]
inherits=PanelButtonCommand
frame=true
interior=false
frame.element=common
interior.element=common
{_frame(big)}
[LineEdit]
inherits=PanelButtonCommand
frame.element=lineedit
interior.element=lineedit
text.margin.left=2
text.margin.right=2
text.margin.top={pad}
text.margin.bottom={pad}

[DropDownButton]
inherits=PanelButtonCommand
indicator.element=arrow-down

[IndicatorArrow]
indicator.element=arrow
indicator.size=9

[ToolboxTab]
inherits=PanelButtonCommand

[Tab]
inherits=PanelButtonCommand
interior.element=tab
frame.element=tab
indicator.element=tab
{_frame(ctl)}text.margin.left=6
text.margin.right=6
text.margin.top={pad}
text.margin.bottom={pad}
text.press.color={text}
text.toggle.color={text}
min_width=+2

[TabFrame]
inherits=PanelButtonCommand
frame.element=tabframe
interior=false
{_frame(big)}
[TreeExpander]
inherits=PanelButtonCommand
frame=false
interior=false
indicator.size=9

[HeaderSection]
inherits=PanelButtonCommand
frame.element=header
interior.element=header
{_frame(2)}text.margin.top=3
text.margin.bottom=3
text.press.color={text}
text.toggle.color={text}

[SizeGrip]
inherits=PanelButtonCommand
frame=false
interior=false

[Toolbar]
inherits=PanelButtonCommand
frame=false
interior=false
text.margin=0

[Slider]
inherits=PanelButtonCommand
frame.element=slider
interior.element=slider
{_frame(3)}
[SliderCursor]
inherits=PanelButtonCommand
frame=false
interior.element=slidercursor

[Progressbar]
inherits=PanelButtonCommand
frame.element=progress
interior.element=progress
{_frame(small)}text.margin=0
text.focus.color={text}
text.press.color={text}
text.toggle.color={text}

[ProgressbarContents]
inherits=PanelButtonCommand
frame=true
frame.element=progress-pattern
interior.element=progress-pattern
{_frame(small)}
[ItemView]
inherits=PanelButtonCommand
text.margin=1
frame.element=itemview
interior.element=itemview
{_frame(2)}text.focus.color={text}
text.press.color={text}
text.toggle.color={text}

[Splitter]
inherits=PanelButtonCommand
frame=false
interior=false

[Scrollbar]
inherits=PanelButtonCommand
indicator.size=9

[ScrollbarSlider]
inherits=PanelButtonCommand
frame.element=scrollbarslider
interior.element=scrollbarslider
{_frame(handle)}
[ScrollbarGroove]
inherits=PanelButtonCommand
interior.element=scrollbargroove
frame.element=scrollbargroove
frame.top=0
frame.bottom=0
frame.left=2
frame.right=2

[MenuItem]
inherits=PanelButtonCommand
frame=true
frame.element=menuitem
interior.element=menuitem
indicator.element=menuitem
text.focus.color={on_accent}
text.margin.top=1
text.margin.bottom=1
text.margin.left=3
text.margin.right=3
{_frame(2)}
[MenuBarItem]
inherits=PanelButtonCommand
interior.element=menubaritem
frame.element=menubaritem
{_frame(2)}text.margin.left=4
text.margin.right=4
text.focus.color={on_accent}

[TitleBar]
inherits=PanelButtonCommand
frame=false
interior=false

[ComboBox]
inherits=PanelButtonCommand

[Menu]
inherits=PanelButtonCommand
{_frame(big)}frame.element=menu
interior.element=menu

[GroupBox]
inherits=GenericFrame
frame=true
frame.element=group
text.shadow=0
text.margin=0
{_frame(big)}
[TabBarFrame]
inherits=GenericFrame
frame=false
interior=false

[ToolTip]
inherits=GenericFrame
{_frame(big)}interior=true
text.margin=0
interior.element=tooltip
frame.element=tooltip

[StatusBar]
inherits=GenericFrame
frame=false
interior=false

[Window]
interior=false
"""


# ---------------------------------------------------------------- the theme folder


def make_theme(colors: dict[str, str], radius: int, border: int) -> tuple[str, str]:
    """The text of the .kvconfig and the .svg file for a look."""
    return make_kvconfig(colors, radius, border), make_svg(colors, radius, border)


def folder_name(theme: Theme) -> str:
    """The name of the Kvantum theme: the theme's name and a hash of what is in it."""
    kvconfig, svg = make_theme(*look_of(theme))
    digest = hashlib.sha256(f"{kvconfig}\0{svg}".encode()).hexdigest()[:8]
    return f"{ID_PREFIX}{theme.slug}-{digest}"


def _folder(name: str) -> Path:
    return config_dir() / name


def theme_files(theme: Theme, name: str | None = None) -> tuple[PlannedFile, PlannedFile]:
    name = name or folder_name(theme)
    kvconfig, svg = make_theme(*look_of(theme))
    root = _folder(name)
    return (
        PlannedFile(root / f"{name}.kvconfig", kvconfig, MARKER),
        PlannedFile(root / f"{name}.svg", svg, XML_MARKER),
    )


# ---------------------------------------------------------------- kvantum.kvconfig


_SECTION = re.compile(r"^\s*\[(%?[^\]]*)\]\s*$")


def selected_theme(text: str) -> str | None:
    """The `theme=` value of the [General] section of a kvantum.kvconfig text."""
    general = False
    for line in text.splitlines():
        section = _SECTION.match(line)
        if section:
            general = section[1].lstrip("%") == "General"
        elif general and line.strip().startswith("theme="):
            return line.split("=", 1)[1].strip()
    return None


def with_theme(text: str, name: str) -> str:
    """The text of a kvantum.kvconfig that selects `name`. Only `theme=` in [General]
    changes; every other section and key (such as [Applications]) stays."""
    lines = text.splitlines()
    general = False
    last = None  # the last line of [General]
    for index, line in enumerate(lines):
        section = _SECTION.match(line)
        if section:
            general = section[1].lstrip("%") == "General"
            if general and last is None:
                last = index
        elif general:
            if line.strip().startswith("theme="):
                lines[index] = f"theme={name}"
                return "\n".join(lines) + "\n"
            if line.strip():
                last = index
    if last is None:
        return f"[General]\ntheme={name}\n" + (("\n" + text) if text.strip() else "")
    lines.insert(last + 1, f"theme={name}")
    return "\n".join(lines) + "\n"


def without_theme(text: str) -> str:
    """The text without the `theme=` line of [General], everything else as it is."""
    general = False
    kept = []
    for line in text.splitlines(keepends=True):
        section = _SECTION.match(line.rstrip("\r\n"))
        if section:
            general = section[1].lstrip("%") == "General"
        elif general and line.strip().startswith("theme="):
            continue
        kept.append(line)
    return "".join(kept)


def restored_selection(current: str, saved: str) -> str:
    """What kvantum.kvconfig should hold after an undo, given its text now and the text
    captured before the apply (`desktop.ABSENT` for no file). A file that is still exactly
    what the apply wrote goes back as it was. One the user has changed since keeps the
    changes: only the `theme=` line is put back. A theme line that is not ours is left."""
    name = selected_theme(current) if current != desktop.ABSENT else None
    if name is None or not name.startswith(ID_PREFIX):
        return current
    before = "" if saved == desktop.ABSENT else saved
    if current == with_theme(before, name):
        return saved
    previous = selected_theme(before)
    return without_theme(current) if previous is None else with_theme(current, previous)


def _style(runner) -> str:
    return kconfig.effective_value(runner, *STYLE_KEY, "Breeze")


def _uses_kvantum(style: str) -> bool:
    return style.lower().startswith(STYLE_NAME)


def plugin_dirs() -> list[Path]:
    """Where Qt looks for style plugins."""
    found = [Path(p) for p in os.environ.get("QT_PLUGIN_PATH", "").split(":") if p]
    for base in ("/usr/lib", "/usr/lib64", "/usr/local/lib"):
        root = Path(base)
        found += [root / "qt6/plugins", root / "qt/plugins"]
        try:
            found += [child / "qt6/plugins" for child in sorted(root.iterdir()) if child.is_dir()]
        except OSError:
            pass
    return found


def plugin_installed() -> bool:
    return any((folder / "styles" / PLUGIN).is_file() for folder in plugin_dirs())


def _switch_style(runner, name: str) -> None:
    kconfig.write_value(runner, *STYLE_KEY, name)
    desktop.notify_change(runner, desktop.CHANGE_STYLE)


class KvantumGenerator(Generator):
    id = "apps"
    title = translate("core", "Application style")
    sections = ("apps",)

    def wanted(self, theme: Theme) -> bool:
        return theme.get("apps", "style") == "generated"

    def notes(self, theme: Theme) -> list[Msg]:
        if not self.wanted(theme):
            return [
                translate(
                    "core",
                    "Applications keep the style in use now. The values here only show in the preview.",
                )
            ]
        notes = [
            translate(
                "core",
                "A Kvantum theme is made from these values and the theme's colors, and Kvantum becomes the "
                "application style. Applications that are open pick it up within a second. "
                "Kvantum draws with the theme's colors, so a color scheme changed later in System Settings "
                "does not reach it until the theme is applied again.",
            )
        ]
        radius = look_of(theme)[1]
        if radius > CONTROL_CAP:
            notes.append(
                translate(
                    "core",
                    "Buttons, fields and tabs get a corner radius of at most {cap} pixels, because they "
                    "grow taller with a bigger radius. Menus, group boxes, tab frames and tooltips use "
                    "the whole radius of {radius} pixels.",
                ).format(cap=CONTROL_CAP, radius=radius)
            )
        return notes

    def unavailable_reason(self, runner) -> Msg | None:
        if plugin_installed() or runner.which("kvantummanager"):
            return None
        return translate(
            "core", "Kvantum is not installed. Install it to give applications a generated style."
        )

    def files(self, theme: Theme) -> list[PlannedFile]:
        return list(theme_files(theme))

    def check_output(self, file: PlannedFile) -> list[Msg]:
        if file.path.suffix == ".kvconfig":
            return self._check_kvconfig(file)
        if file.path.suffix != ".svg":
            return []
        try:
            root = ET.fromstring(file.content)
        except ET.ParseError as error:
            return [
                translate("core", "The generated application style is not valid: {detail}").format(
                    detail=str(error)
                )
            ]
        if any(element.tag.rsplit("}", 1)[-1] == "text" for element in root.iter()):
            return [translate("core", "The generated application style contains text, which it must not.")]
        return []

    def _check_kvconfig(self, file: PlannedFile) -> list[Msg]:
        """Every element a section names must be in the SVG file."""
        ids = _svg_ids()
        return [
            translate("core", "The generated application style has no element {name}.").format(name=name)
            for name in sorted(_elements_used(file.content))
            if not any(i.startswith(f"{name}-") for i in ids)
        ]

    def stale_files(self, theme: Theme) -> list[Path]:
        keep = folder_name(theme)
        root = config_dir()
        stale: list[Path] = []
        if not root.is_dir():
            return stale
        for folder in sorted(root.glob(f"{ID_PREFIX}*")):
            if folder.name == keep or folder.is_symlink() or not folder.is_dir():
                continue
            if not made_here(folder / f"{folder.name}.kvconfig"):
                continue
            stale += [f for f in sorted(folder.iterdir()) if f.is_file() and made_here(f)]
            stale.append(folder)
        return stale

    def warnings(self, theme: Theme, runner) -> list[Msg]:
        warnings = []
        style = _style(runner)
        if style and style.lower() not in ("breeze", "kvantum", "kvantum-dark", "fusion"):
            warnings.append(
                translate("core", "The application style {name} is in use. Kvantum takes its place.").format(
                    name=style
                )
            )
        try:
            current = selected_theme(selection_file().read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            current = None
        if current and not current.startswith(ID_PREFIX) and _uses_kvantum(style):
            warnings.append(
                translate("core", "The Kvantum theme {name} is in use. It is replaced.").format(name=current)
            )
        return warnings

    def is_active(self, theme: Theme, runner) -> bool:
        if not _uses_kvantum(_style(runner)):
            return False
        name = folder_name(theme)
        try:
            if selected_theme(selection_file().read_text(encoding="utf-8")) != name:
                return False
            return all(f.path.read_text(encoding="utf-8") == f.content for f in theme_files(theme, name))
        except (OSError, UnicodeDecodeError):
            return False

    def changed_settings(self, theme: Theme) -> list[Msg]:
        return [
            translate("core", "the application style, which becomes Kvantum (widgetStyle in kdeglobals)"),
            translate("core", "which Kvantum theme is used: {name} (kvantum.kvconfig)").format(
                name=folder_name(theme)
            ),
        ]

    def capture_settings(self, runner) -> dict:
        return {
            "style": kconfig.user_value(*STYLE_KEY),
            "masked": kconfig.masked(*STYLE_KEY),
            "selection": desktop.capture_file(selection_file()),
        }

    def reload(self, theme: Theme, runner) -> None:
        name = folder_name(theme)
        was_kvantum = _uses_kvantum(_style(runner))
        saved = desktop.capture_file(selection_file())
        write_atomic(selection_file(), with_theme(saved if saved != desktop.ABSENT else "", name))
        if was_kvantum:
            # Running applications keep the Kvantum theme they loaded unless the style changes.
            self._hop(runner)
        _switch_style(runner, STYLE_NAME)

    def _hop(self, runner) -> None:
        _switch_style(runner, HOP_STYLE)
        desktop.pause(HOP_PAUSE)

    def restore_settings(self, settings: dict, runner) -> None:
        previous = settings.get("style")
        masked = bool(settings.get("masked"))
        saved = settings.get("selection", desktop.ABSENT)
        same_style = kconfig.user_value(*STYLE_KEY) == previous and (
            previous or kconfig.masked(*STYLE_KEY) == masked
        )
        now = desktop.capture_file(selection_file())
        if same_style and now == saved:
            return  # nothing was changed
        failure = None
        try:
            desktop.restore_file(selection_file(), restored_selection(now, saved))
        except OSError as error:
            failure = ApplyError(
                translate("core", "Could not put back {path}: {detail}").format(
                    path=str(selection_file()), detail=str(error)
                )
            )
        # An application that already uses Kvantum only loads another theme when the style changes.
        if previous and _uses_kvantum(previous) and _uses_kvantum(_style(runner)):
            self._hop(runner)
        try:
            kconfig.write_value(runner, *STYLE_KEY, previous, masked=masked)
        except ApplyError as error:
            failure = failure or error
        desktop.notify_change(runner, desktop.CHANGE_STYLE)
        # Applications keep Kvantum's palette until they are told about the colors again.
        desktop.notify_change(runner, desktop.CHANGE_PALETTE)
        if failure:
            raise failure


_ELEMENT_KEYS = re.compile(r"^(?:frame|interior|indicator)\.element=(\S+)$", re.MULTILINE)


@functools.cache
def _svg_ids() -> frozenset[str]:
    """The ids in a generated SVG file. They do not depend on the colors, radius or border."""
    colors = {k: "#808080" for k in ("accent", "window", "view", "button", "header", "text", "text_muted")}
    return frozenset(e.get("id") for e in ET.fromstring(make_svg(colors, 4, 1)).iter() if e.get("id"))


def _elements_used(kvconfig: str) -> set[str]:
    """The element names the sections of a .kvconfig draw with."""
    return set(_ELEMENT_KEYS.findall(kvconfig))
