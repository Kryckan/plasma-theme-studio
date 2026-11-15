# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Moves and shapes the Plasma panels through plasmashell's scripting interface.

The main panel is the section `panel_layout` of the theme, further panels are `panel_layout_2` and so
on. A panel is named by its number: 1 is the main panel (lowest screen, then the longest, then the
lowest id), the others follow in the order of their ids. Another machine may have fewer panels: an
entry for a panel that is not there is skipped and said so, and no panel is ever made or removed."""

from __future__ import annotations

import json
import re

from .. import kconfig
from ..apply import desktop
from ..messages import Msg, translate
from ..model.theme import MAX_PANELS, Theme, panel_section
from .base import ApplyError, Generator, PlannedFile

SECTION = "panel_layout"
SECTIONS = tuple(panel_section(number) for number in range(1, MAX_PANELS + 1))

# Theme field -> property of the scripting Panel object. Location comes first:
# it changes the orientation, and the other values are read against the new one.
PROPERTIES = (
    ("location", "location"),
    ("alignment", "alignment"),
    ("length_mode", "lengthMode"),
    ("height", "height"),
    ("floating", "floating"),
    ("visibility", "hiding"),
    ("opacity_mode", "opacity"),
)

# plasmashellrc stores these as numbers; the scripting getters are not reliable
# for them (no "windowsgobelow" for hiding, "translucent" for opacity whenever
# the Plasma style has no adaptive transparency).
MIN_HEIGHT = 20  # the thinnest panel a theme may ask for
_RAW_HIDING = ("none", "autohide", "dodgewindows", "windowsgobelow")
_RAW_OPACITY = ("adaptive", "opaque", "translucent")

# A fixed program. The values it works on come in as one JSON line at the top,
# so no theme value is ever pasted into code.
_PROGRAM = """\
var ALLOWED = {
    location: ["top", "bottom", "left", "right"],
    alignment: ["left", "center", "right"],
    lengthMode: ["fill", "fit"],
    hiding: ["none", "autohide", "dodgewindows", "windowsgobelow"],
    opacity: ["adaptive", "opaque", "translucent"]
};
var ORDER = ["location", "alignment", "lengthMode", "height", "floating", "hiding", "opacity"];
function ordered() {
    // The main panel first, the others by their ids. A panel's number is its place in this list.
    var all = [];
    var main = null;
    for (var i = 0; i < panelIds.length; i++) {
        var p = panelById(panelIds[i]);
        if (!p) {
            continue;
        }
        all.push(p);
        if (main === null || p.screen < main.screen ||
            (p.screen === main.screen && (p.maximumLength > main.maximumLength ||
             (p.maximumLength === main.maximumLength && p.id < main.id)))) {
            main = p;
        }
    }
    if (main === null) {
        return [];
    }
    var rest = [];
    for (var j = 0; j < all.length; j++) {
        if (all[j].id !== main.id) {
            rest.push(all[j]);
        }
    }
    rest.sort(function (a, b) { return a.id - b.id; });
    return [main].concat(rest);
}
function choose() {
    if (request.panel !== null) {
        return panelById(request.panel);
    }
    return ordered()[(request.number || 1) - 1] || null;
}
function describe(p) {
    return {
        id: p.id, screen: p.screen, maximumLength: p.maximumLength, location: p.location,
        height: p.height, alignment: p.alignment, lengthMode: p.lengthMode, floating: p.floating,
        hiding: p.hiding, opacity: p.opacity
    };
}
var panel = request.op === "list" ? null : choose();
if (request.op === "list") {
    var listed = [];
    var found = ordered();
    for (var n = 0; n < found.length; n++) {
        listed.push(describe(found[n]));
    }
    print(JSON.stringify({panels: listed}));
} else if (!panel) {
    print(JSON.stringify({found: false}));
} else {
    if (request.op === "write") {
        // Everything is checked before anything is set, so a refused request changes nothing.
        for (var c = 0; c < ORDER.length; c++) {
            var checked = ORDER[c];
            if (!request.set.hasOwnProperty(checked)) {
                continue;
            }
            var given = request.set[checked];
            if (ALLOWED.hasOwnProperty(checked) && ALLOWED[checked].indexOf(given) < 0) {
                throw new Error("invalid " + checked + ": " + given);
            }
            if (checked === "height" &&
                (typeof given !== "number" || !isFinite(given) || !(given >= request.minHeight))) {
                throw new Error("invalid height: " + given);
            }
            if (checked === "floating" && typeof given !== "boolean") {
                throw new Error("invalid floating: " + given);
            }
        }
        for (var k = 0; k < ORDER.length; k++) {
            var name = ORDER[k];
            if (request.set.hasOwnProperty(name)) {
                panel[name] = request.set[name];
            }
        }
        // Plasma lays the panel out again after a change of floating, but not after alignment
        // or length alone, so the panel would stay where it was drawn.
        if (request.set.hasOwnProperty("alignment") || request.set.hasOwnProperty("lengthMode")) {
            var floating = panel.floating;
            panel.floating = !floating;
            panel.floating = floating;
        }
    }
    print(JSON.stringify({
        found: true, id: panel.id, location: panel.location, height: panel.height,
        alignment: panel.alignment, lengthMode: panel.lengthMode, floating: panel.floating,
        hiding: panel.hiding, opacity: panel.opacity
    }));
}
"""

_LABELS = {
    "location": translate("core", "position"),
    "alignment": translate("core", "alignment"),
    "lengthMode": translate("core", "length"),
    "height": translate("core", "height"),
    "floating": translate("core", "floating"),
    "hiding": translate("core", "visibility"),
    "opacity": translate("core", "opacity"),
}

_QDBUS = ["qdbus6", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript"]
_BUSCTL = ["busctl", "--user", "call", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell"]


def build_script(request: dict) -> str:
    return "// pts\nvar request = " + json.dumps(request) + ";\n" + _PROGRAM


def _wanted(theme: Theme, number: int = 1) -> dict:
    """The properties the theme sets for panel `number`, under their scripting names."""
    wanted = {}
    for field, prop in PROPERTIES:
        value = theme.get(panel_section(number), field)
        if value is not None:
            wanted[prop] = value
    return wanted


def wanted_numbers(theme: Theme) -> list[int]:
    """The numbers of the panels the theme sets something on."""
    return [number for number in range(1, MAX_PANELS + 1) if _wanted(theme, number)]


def _unquote(text: str) -> str:
    """The string inside busctl's `s "..."` reply."""
    text = text.strip()
    if text.startswith("s "):
        try:
            return json.loads(text[2:])
        except ValueError:
            return text[2:].strip('"')
    return text


def _detail(output: str) -> str:
    lines = []
    for line in output.splitlines():
        line = line.strip()
        while line.startswith("Error:"):
            line = line.removeprefix("Error:").strip()
        line = re.sub(r"\s+at line \d+.*$", "", line)
        if line and line != "Backtrace:" and not line.startswith(("org.freedesktop.DBus.Error", "%", "@")):
            lines.append(line)
    return " ".join(lines[:2])[:200]


def _call(runner, request: dict) -> dict:
    script = build_script(request)
    if runner.which("qdbus6"):
        argv, plain = [*_QDBUS, script], True
    else:
        argv, plain = [*_BUSCTL, "evaluateScript", "s", script], False
    result = runner.run(argv)
    if result.returncode != 0 or result.stdout.startswith("Error:"):
        raise ApplyError(
            translate("core", "The panel script failed: {detail}").format(
                detail=_detail(result.stdout + "\n" + result.stderr)
            )
        )
    text = result.stdout.strip() if plain else _unquote(result.stdout)
    try:
        answer = json.loads(text)
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        raise ApplyError(
            translate("core", "Plasma gave an answer for the panel that could not be understood.")
        )
    return answer


def _read(runner, panel: int | None = None, number: int = 1) -> dict:
    """One panel, by its id or else by its number (1 is the main panel)."""
    return _call(runner, {"op": "read", "panel": panel, "number": number, "set": {}, "minHeight": 1})


def _write(runner, values: dict, panel: int | None = None, min_height: int = 1, number: int = 1) -> dict:
    """Set the values on a panel. A theme's thickness has a lower limit; a panel that
    is put back gets the thickness it had, however thin."""
    request = {"op": "write", "panel": panel, "number": number, "set": values, "minHeight": min_height}
    return _call(runner, request)


def list_panels(runner) -> list[dict]:
    """The panels as Plasma has them, the main panel first and the others by id. Changes nothing."""
    answer = _call(runner, {"op": "list", "panel": None, "number": 1, "set": {}, "minHeight": 1})
    found = answer.get("panels")
    if not isinstance(found, list):
        return []
    return [state for state in found if isinstance(state, dict) and isinstance(state.get("id"), int)]


def live_panels(runner) -> list[dict]:
    """`list_panels`, with hiding and opacity as they are now where that can be told."""
    panels = list_panels(runner)
    if not panels:
        return panels
    dump = _dump_panels(runner)
    return [_live_state(runner, state, dump)[0] for state in panels]


_SETTLE_TRIES = 8
_SETTLE_PAUSE = 0.75


def _pause(seconds: float) -> None:
    desktop.pause(seconds)


def _write_settled(runner, values: dict, panel: int | None = None, min_height: int = 1) -> dict:
    """`_write`, with patience for a panel that is to get thinner. For a few seconds after
    the Plasma style changes, the old style's minimum thickness still holds and Plasma
    answers with a thicker panel. It does not make the panel thinner by itself later, so
    the thickness is asked for again until it is taken or the time is up."""
    state = _write(runner, values, panel, min_height)
    wanted = values.get("height")
    for _attempt in range(_SETTLE_TRIES):
        got = state.get("height")
        if wanted is None or not state.get("found") or not isinstance(got, int | float) or got <= wanted:
            break
        _pause(_SETTLE_PAUSE)
        again = _write(runner, {"height": wanted}, state.get("id"), min_height)
        if not again.get("found"):
            break
        state = again
    return state


def _dump_panels(runner) -> list[dict]:
    """The panels of plasmashell's own layout dump, which tells hiding and opacity as they
    are now. Empty when the dump is not available."""
    if not runner.which("qdbus6"):
        return []
    result = runner.run(
        ["qdbus6", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.dumpCurrentLayoutJS"]
    )
    start = result.stdout.find("var layout = ")
    if result.returncode != 0 or start < 0:
        return []
    try:
        layout, _end = json.JSONDecoder().raw_decode(result.stdout, result.stdout.index("{", start))
    except ValueError:
        return []
    panels = layout.get("panels") if isinstance(layout, dict) else None
    return [p for p in panels if isinstance(p, dict)] if isinstance(panels, list) else []


def _live_state(runner, state: dict, dump: list[dict] | None = None) -> tuple[dict, bool]:
    """The state with hiding and opacity from the layout dump. The dump has no panel id, so
    the panel is recognised by what the getters say about it; if that is not unique and the
    candidates disagree, nothing is replaced. The flag says whether the two are now known."""
    same = ("location", "alignment", "lengthMode", "floating")
    dump = _dump_panels(runner) if dump is None else dump
    candidates = [p for p in dump if all(p.get(key) == state.get(key) for key in same)]
    hiding = {"normal": "none"}
    seen = {(hiding.get(p.get("hiding"), p.get("hiding")), p.get("opacity")) for p in candidates}
    if len(seen) != 1:
        return state, False
    ((now_hiding, now_opacity),) = seen
    if now_hiding not in _RAW_HIDING or now_opacity not in _RAW_OPACITY:
        return state, False
    return state | {"hiding": now_hiding, "opacity": now_opacity}, True


def _differs(prop: str, wanted, got, resolved: bool, strict: bool) -> bool:
    if got == wanted:
        return False
    if prop == "height":
        # On a write, Plasma raises a thickness the style cannot draw to its minimum.
        return strict or not isinstance(got, int | float) or got < wanted
    if resolved or strict:
        return True  # strict: a value that cannot be told apart does not count as in use
    if prop == "hiding":
        return not (wanted == "windowsgobelow" and got == "none")  # the getter cannot say this mode
    if prop == "opacity":
        return got != "translucent"  # what the getter says when the style has no adaptive transparency
    return True


def _first_mismatch(
    values: dict, state: dict, resolved: bool = False, strict: bool = False, number: int = 1
) -> Msg | None:
    """The first wanted value the panel does not have. Unless `resolved`, hiding and
    opacity come from getters that are known to say less than the truth."""
    for _field, prop in PROPERTIES:
        if prop in values and _differs(prop, values[prop], state.get(prop), resolved, strict):
            if number > 1:
                text = translate(
                    "core", "Plasma did not take the {setting} of panel {number}: wanted {wanted}, got {got}."
                )
            else:
                text = translate(
                    "core", "Plasma did not take the panel {setting}: wanted {wanted}, got {got}."
                )
            return text.format(
                setting=str(_LABELS[prop]),
                number=number,
                wanted=json.dumps(values[prop]),
                got=json.dumps(state.get(prop)),
            )
    return None


def _no_panel() -> ApplyError:
    return ApplyError(translate("core", "Plasma has no panel to change."))


def _prefixed(number: int, text: str) -> str:
    """A text about panel `number`; the main panel's needs no name while it is the only one."""
    return str(translate("core", "Panel {number}: {text}").format(number=number, text=text))


def status_texts(theme: Theme, runner) -> tuple[str, str]:
    """What the desktop's panels are like and what the theme sets, for the Overview and the status."""
    numbers = wanted_numbers(theme)
    try:
        panels = live_panels(runner)
    except ApplyError:
        panels = []
    several = numbers != [1]
    desktop, wanted = [], []
    for number in numbers:
        if number <= len(panels):
            state = panels[number - 1]
            text = str(
                translate("core", "{place}, {size} px").format(
                    place=state.get("location", "?"), size=state.get("height", "?")
                )
            )
        elif number == 1:
            text = str(translate("core", "No panel was found"))
        else:
            text = str(translate("core", "No such panel on this desktop"))
        desktop.append(_prefixed(number, text) if several else text)
        shown = ", ".join(
            str(theme.get(panel_section(number), key))
            for key in ("location", "height")
            if theme.get(panel_section(number), key) is not None
        ) or str(translate("core", "other values"))
        if number > len(panels) and number > 1:
            shown = str(translate("core", "does not exist on this desktop, so it is skipped"))
        wanted.append(_prefixed(number, shown) if several else shown)
    return "; ".join(desktop), "; ".join(wanted)


class PanelLayoutGenerator(Generator):
    id = "panel_layout"
    title = translate("core", "Panel position")
    sections = SECTIONS

    def wanted(self, theme: Theme) -> bool:
        return bool(wanted_numbers(theme))

    def _section_number(self, section: str) -> int:
        return SECTIONS.index(section) + 1 if section in SECTIONS else 1

    def _fill_note(self, theme: Theme, number: int) -> Msg | None:
        section = panel_section(number)
        if theme.get(section, "alignment") and theme.get(section, "length_mode") == "fill":
            if number == 1:
                return translate("core", "Alignment has no effect while the panel fills the whole edge.")
            return translate(
                "core", "Alignment of panel {number} has no effect while it fills the whole edge."
            ).format(number=number)
        return None

    def notes(self, theme: Theme) -> list[Msg]:
        if not self.wanted(theme):
            return [translate("core", "The panel stays where it is and keeps its shape.")]
        notes = [self._fill_note(theme, number) for number in wanted_numbers(theme)]
        return [note for note in notes if note is not None]

    def section_notes(self, theme: Theme, section: str) -> list[Msg]:
        number = self._section_number(section)
        if number == 1:
            if not self.wanted(theme):
                return [translate("core", "The panel stays where it is and keeps its shape.")]
            note = self._fill_note(theme, 1)
        else:
            note = self._fill_note(theme, number)
        return [note] if note is not None else []

    def files(self, theme: Theme) -> list[PlannedFile]:
        return []

    def unavailable_reason(self, runner) -> Msg | None:
        if not (runner.which("qdbus6") or runner.which("busctl")):
            return translate("core", "qdbus6 was not found. It is needed to change the panel.")
        try:
            panels = list_panels(runner)
        except ApplyError as error:
            return translate("core", "Plasma does not answer for the panel. {detail}").format(
                detail=str(error.message)
            )
        if not panels:
            return translate("core", "Plasma has no panel to change.")
        return None

    def warnings(self, theme: Theme, runner) -> list[Msg]:
        """A panel the theme names that this desktop does not have is skipped, and that is said."""
        later = [number for number in wanted_numbers(theme) if number > 1]
        if not later:
            return []
        try:
            count = len(list_panels(runner))
        except ApplyError:
            return []
        return [
            translate(
                "core", "This desktop has no panel {number}, so that part of the theme is skipped."
            ).format(number=number)
            for number in later
            if number > count
        ]

    def reload_command(self, theme: Theme) -> str:
        return 'qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "<script>"'

    def changed_settings(self, theme: Theme) -> list[Msg]:
        if wanted_numbers(theme) == [1]:
            return [translate("core", "the position and shape of the panel, through that script")]
        return [translate("core", "the position and shape of the panels, through that script")]

    def is_active(self, theme: Theme, runner) -> bool:
        try:
            panels = list_panels(runner)
            dump = _dump_panels(runner)
        except ApplyError:
            return False
        if not panels:
            return False
        # Exact, also for the thickness: a panel that is thicker than the theme asks for
        # must get the apply that makes it thinner. The price is that a panel Plasma keeps
        # thicker than asked (the style cannot draw it thinner) never counts as in use.
        # A panel this desktop does not have is skipped by the apply, so it counts as done.
        for number in wanted_numbers(theme):
            if number > len(panels):
                continue
            state, resolved = _live_state(runner, panels[number - 1], dump)
            if _first_mismatch(_wanted(theme, number), state, resolved, strict=True, number=number):
                return False
        return True

    def _capture_one(self, runner, panel: int) -> dict:
        state = _read(runner, panel)
        if not state.get("found"):
            raise _no_panel()
        state, resolved = _live_state(runner, state)
        settings = {"panel": state["id"]}
        settings.update({prop: state.get(prop) for _field, prop in PROPERTIES})
        if not resolved:
            # plasmashellrc follows the panel only after a delay, but it is all that is left.
            group = ["PlasmaViews", f"Panel {state['id']}"]
            raw_hiding = kconfig.effective_value(runner, "plasmashellrc", group, "panelVisibility", "0")
            raw_opacity = kconfig.effective_value(runner, "plasmashellrc", group, "panelOpacity", "0")
            settings["hiding"] = _by_number(_RAW_HIDING, raw_hiding, state.get("hiding"))
            settings["opacity"] = _by_number(_RAW_OPACITY, raw_opacity, state.get("opacity"))
        return settings

    def capture_settings(self, runner) -> dict:
        """Every panel as it is: the main panel's values, and the others under "more". Only what
        differs is written back, so a panel the apply did not touch is not disturbed."""
        panels = list_panels(runner)
        if not panels:
            raise _no_panel()
        settings = self._capture_one(runner, panels[0]["id"])
        more = [self._capture_one(runner, state["id"]) for state in panels[1:]]
        if more:
            settings["more"] = more
        return settings

    def reload(self, theme: Theme, runner) -> None:
        panels = list_panels(runner)
        if not panels:
            raise _no_panel()
        # Which panel a number means is settled before anything moves: a panel that changes its
        # edge can change which one is the main panel.
        chosen = [
            (number, panels[number - 1]["id"]) for number in wanted_numbers(theme) if number <= len(panels)
        ]
        for number, panel in chosen:
            values = _wanted(theme, number)
            state = _write_settled(runner, values, panel, min_height=MIN_HEIGHT)
            if not state.get("found"):
                raise _no_panel()
            state, resolved = _live_state(runner, state)
            mismatch = _first_mismatch(values, state, resolved, number=number)
            if mismatch:
                raise ApplyError(mismatch)

    def _restore_one(self, settings: dict, runner) -> None:
        panel = settings.get("panel")
        if panel is None:
            return
        values = {prop: settings[prop] for _field, prop in PROPERTIES if settings.get(prop) is not None}
        gone = ApplyError(
            translate("core", "The panel {id} does not exist any more, so it was not put back.").format(
                id=panel
            )
        )
        state = _read(runner, panel)
        if not state.get("found"):
            raise gone
        state, resolved = _live_state(runner, state)
        # Only what differs is written, so a panel that is as it was is not disturbed. What
        # the getters cannot tell for sure (hiding, opacity) is written whenever in doubt.
        unsure = () if resolved else ("hiding", "opacity")
        values = {prop: value for prop, value in values.items() if state.get(prop) != value or prop in unsure}
        if not values:
            return
        state = _write_settled(runner, values, panel)
        if not state.get("found"):
            raise gone
        state, resolved = _live_state(runner, state)
        mismatch = _first_mismatch(values, state, resolved, strict=True)
        if mismatch:
            raise ApplyError(mismatch)

    def restore_settings(self, settings: dict, runner) -> None:
        errors = []
        for entry in [settings, *settings.get("more", [])]:
            try:
                self._restore_one(entry, runner)
            except ApplyError as error:  # the other panels are put back all the same
                errors.append(str(error.message))
        if errors:
            raise ApplyError(" ".join(errors))


def _by_number(names: tuple[str, ...], raw: str, fallback):
    try:
        return names[int(raw)]
    except (ValueError, IndexError):
        return fallback
