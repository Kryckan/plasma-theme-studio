# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The panel layout target, against a fake plasmashell that keeps panel state."""

import json
import re

import pytest

from plasma_theme_studio import kconfig
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.generators import ApplyError
from plasma_theme_studio.generators import panellayout as pl
from plasma_theme_studio.generators.panellayout import PanelLayoutGenerator
from plasma_theme_studio.model.theme import Theme

HIDING = ("none", "autohide", "dodgewindows", "windowsgobelow")
OPACITY = ("adaptive", "opaque", "translucent")
ALLOWED = {
    "location": ("top", "bottom", "left", "right"),
    "alignment": ("left", "center", "right"),
    "lengthMode": ("fill", "fit"),
    "hiding": HIDING,
    "opacity": OPACITY,
}


def panel(id, screen=0, length=1920, **overrides):
    state = {
        "id": id,
        "screen": screen,
        "maximumLength": length,
        "location": "bottom",
        "height": 46,
        "alignment": "center",
        "lengthMode": "fill",
        "floating": True,
        "hiding": "none",
        "opacity": "adaptive",
    }
    return state | overrides


class FakePlasmashell:
    """Runs a script's request the way the scripting engine would: it reads the
    JSON line at the top, applies it to its panels and prints one JSON document.
    Hiding and opacity are kept as raw numbers in plasmashellrc, and their
    getters have the quirks of the real ones."""

    def __init__(self, runner, panels):
        self.runner = runner
        self.panels = {p["id"]: p for p in panels}
        self.adaptive_disabled = False
        self.ignore = set()  # properties whose setter does nothing
        self.scripts = []
        self.writes = []  # property names in the order they were set
        self.down = False
        self.no_dump = False
        self.min_height = 0  # the thinnest panel the style can draw
        self.old_minimum = 0  # the minimum of the style that was in use just before ...
        self.old_minimum_writes = 0  # ... which still holds for this many writes of the height
        self.pending = {}  # raw keys not yet written, as plasmashell syncs them late
        self.shown = {}  # per panel: what the layout last used, set by the floating toggle in the script
        runner.handlers["qdbus6"] = self.run

    def run(self, argv):
        script = argv[-1]
        if script.endswith(".dumpCurrentLayoutJS"):
            return self.dump()
        self.scripts.append(script)
        if self.down:
            return Result(1, "", "Could not find service")
        assert script.startswith("// pts\n")
        line = script.split("\n")[1]
        assert line.startswith("var request = ") and line.endswith(";")
        request = json.loads(line[len("var request = ") : -1])
        try:
            return Result(0, json.dumps(self.execute(request), separators=(",", ":")) + "\n")
        except ValueError as error:
            text = f"Error: org.freedesktop.DBus.Error.Failed\nError: Error: {error} at line 80\n\nBacktrace:\n@:1\n"  # noqa: E501
            return Result(2, text)

    def dump(self):
        """The layout dump: live values, "normal" for no hiding, no panel ids."""
        if self.down or self.no_dump:
            return Result(1, "", "Could not find service")
        panels = [
            {
                "alignment": p["alignment"],
                "floating": p["floating"],
                "hiding": "normal" if p["hiding"] == "none" else p["hiding"],
                "lengthMode": p["lengthMode"],
                "location": p["location"],
                "opacity": p["opacity"],
            }
            for p in self.panels.values()
        ]
        layout = json.dumps({"desktops": [], "panels": panels}, indent=4)
        return Result(
            0,
            f"var plasma = getApiVersion(1);\n\nvar layout = {layout};\n\nplasma.loadSerializedLayout(layout);\n",  # noqa: E501
        )

    def choose(self, request):
        if request["panel"] is not None:
            return self.panels.get(request["panel"])
        found = None
        for p in self.panels.values():
            key = (p["screen"], -p["maximumLength"], p["id"])
            if found is None or key < (found["screen"], -found["maximumLength"], found["id"]):
                found = p
        return found

    def execute(self, request):
        p = self.choose(request)
        if p is None:
            return {"found": False}
        if request["op"] == "write":
            order = ("location", "alignment", "lengthMode", "height", "floating", "hiding", "opacity")
            for name in order:  # the script checks everything before it sets anything
                value = request["set"].get(name)
                if name not in request["set"]:
                    continue
                if name in ALLOWED and value not in ALLOWED[name]:
                    raise ValueError(f"invalid {name}: {value}")
                number = isinstance(value, int | float) and not isinstance(value, bool)
                if name == "height" and not (number and value >= request["minHeight"]):
                    raise ValueError(f"invalid height: {value}")
                if name == "floating" and not isinstance(value, bool):
                    raise ValueError(f"invalid floating: {value}")
            for name in order:
                if name not in request["set"]:
                    continue
                value = request["set"][name]
                self.writes.append(name)
                if name == "height":
                    value = max(value, self.min_height)
                    if self.old_minimum_writes > 0:
                        self.old_minimum_writes -= 1
                        value = max(value, self.old_minimum)
                if name not in self.ignore:
                    p[name] = value
                    self.persist(p, name, value)
            keys = request["set"].keys()
            if keys & {"alignment", "lengthMode"}:
                self.shown[p["id"]] = (p["alignment"], p["lengthMode"])  # the floating toggle in the script
        return {
            "found": True,
            "id": p["id"],
            "location": p["location"],
            "height": p["height"],
            "alignment": p["alignment"],
            "lengthMode": p["lengthMode"],
            "floating": p["floating"],
            "hiding": "none" if p["hiding"] == "windowsgobelow" else p["hiding"],
            "opacity": "translucent" if self.adaptive_disabled else p["opacity"],
        }

    def persist(self, p, name, value):
        keys = {"hiding": ("panelVisibility", HIDING), "opacity": ("panelOpacity", OPACITY)}
        if name in keys:
            key, names = keys[name]
            self.pending[(p["id"], key)] = str(names.index(value))

    def sync(self):
        """plasmashell writes its config a few seconds after a change."""
        for (id, key), value in self.pending.items():
            kconfig.write_value(self.runner, "plasmashellrc", ["PlasmaViews", f"Panel {id}"], key, value)
        self.pending.clear()

    def state(self, id=161):
        return dict(self.panels[id])


@pytest.fixture
def shell(runner, use_generators):
    use_generators(PanelLayoutGenerator())
    return FakePlasmashell(runner, [panel(161)])


def theme(**fields):
    return Theme({("panel_layout", key): value for key, value in fields.items()})


def test_nothing_set_is_not_wanted_and_nothing_is_called(runner, shell):
    generator = PanelLayoutGenerator()
    assert not generator.wanted(Theme())
    assert [str(n) for n in generator.notes(Theme())] == ["The panel stays where it is and keeps its shape."]
    assert generator.files(Theme()) == []

    result = engine.apply(Theme(), runner)

    assert shell.scripts == []
    assert "panel_layout" not in result.snapshot.settings


def test_only_the_set_fields_are_written_and_location_comes_first(runner, shell):
    t = theme(height=60, location="top", opacity_mode="opaque")
    assert PanelLayoutGenerator().wanted(t)

    engine.apply(t, runner)

    assert shell.writes == ["location", "height", "opacity"]
    state = shell.state()
    assert (state["location"], state["height"], state["opacity"]) == ("top", 60, "opaque")
    assert (state["alignment"], state["lengthMode"], state["floating"], state["hiding"]) == (
        "center",
        "fill",
        True,
        "none",
    )


def test_theme_values_map_to_the_scripting_names(runner, shell):
    t = theme(length_mode="fit", visibility="autohide", floating=False, alignment="left")
    engine.apply(t, runner)
    state = shell.state()
    assert (state["lengthMode"], state["hiding"], state["floating"], state["alignment"]) == (
        "fit",
        "autohide",
        False,
        "left",
    )
    assert engine.is_current(engine.build_plan(t), runner)
    assert not engine.is_current(engine.build_plan(theme(length_mode="fill")), runner)


def test_capture_apply_restore_gives_back_the_exact_state(runner, shell):
    shell.panels[161]["hiding"] = "windowsgobelow"  # the getter reads this as "none"
    shell.panels[161]["opacity"] = "opaque"
    kconfig.write_value(runner, "plasmashellrc", ["PlasmaViews", "Panel 161"], "panelVisibility", "3")
    kconfig.write_value(runner, "plasmashellrc", ["PlasmaViews", "Panel 161"], "panelOpacity", "1")
    before = shell.state()
    t = theme(
        location="left",
        height=30,
        alignment="right",
        length_mode="fit",
        floating=False,
        visibility="autohide",
    )

    result = engine.apply(t, runner)
    assert shell.state() != before

    assert result.snapshot.settings["panel_layout"]["hiding"] == "windowsgobelow"
    assert engine.restore(result.snapshot, runner, consume=True) == []
    assert shell.state() == before


def test_a_value_that_did_not_take_raises_and_the_engine_rolls_back(runner, shell):
    before = shell.state()
    shell.ignore = {"height"}

    with pytest.raises(ApplyError) as error:
        engine.apply(theme(location="right", height=70), runner)

    assert "panel height" in str(error.value)
    assert "wanted 70" in str(error.value)
    shell.ignore = set()
    assert shell.state() == before  # location was put back


def test_the_first_value_that_did_not_take_is_named(runner, shell):
    shell.ignore = {"alignment", "opacity"}
    with pytest.raises(ApplyError, match="alignment"):
        PanelLayoutGenerator().reload(theme(alignment="left", opacity_mode="opaque"), runner)


def test_getter_quirks_do_not_count_as_failures(runner, shell):
    shell.adaptive_disabled = True
    generator = PanelLayoutGenerator()
    t = theme(visibility="windowsgobelow", opacity_mode="opaque")
    generator.reload(t, runner)
    assert generator.is_active(t, runner)
    assert shell.state()["hiding"] == "windowsgobelow"


def test_an_error_from_plasma_is_reported(runner, shell):
    generator = PanelLayoutGenerator()
    # Bypass the theme's own checks to see what an invalid value does.
    with pytest.raises(ApplyError) as error:
        pl._write(runner, {"alignment": "diagonal"})
    assert "invalid alignment" in str(error.value)
    assert "DBus.Error" not in str(error.value)
    assert generator.is_active(theme(alignment="left"), runner) is False


def test_a_failed_call_or_unreadable_answer_is_an_apply_error(runner, shell):
    runner.handlers["qdbus6"] = lambda argv: Result(1, "", "boom")
    with pytest.raises(ApplyError, match="boom"):
        pl._read(runner)
    runner.handlers["qdbus6"] = lambda argv: Result(0, "this is not json\n")
    with pytest.raises(ApplyError, match="could not be understood"):
        pl._read(runner)
    runner.handlers["qdbus6"] = lambda argv: Result(0, "[1, 2]\n")
    with pytest.raises(ApplyError, match="could not be understood"):
        pl._read(runner)
    runner.handlers["qdbus6"] = lambda argv: Result(0, "Error: Widgets are locked\n")
    with pytest.raises(ApplyError, match="Widgets are locked"):
        pl._read(runner)


def test_missing_tools_or_a_silent_plasmashell_block_the_apply(runner, shell):
    generator = PanelLayoutGenerator()
    assert generator.unavailable_reason(runner) is None

    shell.down = True
    assert "does not answer" in str(generator.unavailable_reason(runner))
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(theme(height=50), runner)
    assert generator.is_active(theme(height=50), runner) is False

    runner.missing = {"qdbus6", "busctl"}
    assert "qdbus6 was not found" in str(generator.unavailable_reason(runner))
    # Nothing is set, so nothing is checked.
    engine.apply(Theme(), runner)


def test_busctl_is_the_fallback_and_its_quoted_reply_is_read(runner, shell):
    runner.missing = {"qdbus6"}

    def busctl(argv):
        assert argv[:6] == [
            "busctl",
            "--user",
            "call",
            "org.kde.plasmashell",
            "/PlasmaShell",
            "org.kde.PlasmaShell",
        ]
        assert argv[6:8] == ["evaluateScript", "s"]
        reply = shell.run(["qdbus6", argv[-1]])
        return Result(reply.returncode, "s " + json.dumps(reply.stdout.strip()) + "\n", reply.stderr)

    runner.handlers["busctl"] = busctl
    PanelLayoutGenerator().reload(theme(height=52), runner)
    assert shell.state()["height"] == 52


def test_the_longest_panel_on_the_lowest_screen_is_chosen(runner, use_generators):
    use_generators(PanelLayoutGenerator())
    shell = FakePlasmashell(
        runner,
        [
            panel(10, screen=1, length=5000),
            panel(30, screen=0, length=800, location="left"),
            panel(25, screen=0, length=1920),
            panel(20, screen=0, length=1920),
        ],
    )

    result = engine.apply(theme(height=80), runner)

    assert result.snapshot.settings["panel_layout"]["panel"] == 20
    assert shell.panels[20]["height"] == 80
    assert all(shell.panels[i]["height"] == 46 for i in (10, 25, 30))
    # Undo goes to the captured id, even if another panel would be chosen now.
    shell.panels[20]["maximumLength"] = 10
    engine.restore(result.snapshot, runner, consume=True)
    assert shell.panels[20]["height"] == 46


def test_restore_says_so_when_the_panel_is_gone(runner, shell):
    result = engine.apply(theme(height=80), runner)
    del shell.panels[161]
    failures = engine.restore(result.snapshot, runner)
    assert [str(f) for f in failures] == ["The panel 161 does not exist any more, so it was not put back."]


def test_no_panel_blocks_the_apply(runner, shell):
    shell.panels.clear()
    assert "no panel" in str(PanelLayoutGenerator().unavailable_reason(runner))
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(theme(height=50), runner)


def test_values_are_embedded_only_as_json():
    nasty = 'x"); panel.height = 1; (" \\\n'
    script = pl.build_script({"op": "write", "panel": None, "set": {"alignment": nasty}})
    assert script.startswith("// pts\nvar request = ")
    line = script.split("\n")[1]
    assert json.loads(line[len("var request = ") : -1])["set"]["alignment"] == nasty
    assert " " not in script
    assert nasty not in script
    assert script.endswith(pl._PROGRAM)


def test_every_assignment_to_a_panel_is_inside_the_write_branch():
    write = pl._PROGRAM.index('request.op === "write"')
    assignments = list(re.finditer(r"\bpanel(\.\w+|\[\w+\])\s*=[^=]", pl._PROGRAM))
    assert [m.group(1) for m in assignments] == ["[name]", ".floating", ".floating"]  # the nudge: off and on
    assert all(m.start() > write for m in assignments)


def test_notes_and_reload_command(runner, shell):
    generator = PanelLayoutGenerator()
    assert [str(n) for n in generator.notes(theme(alignment="left", length_mode="fill"))] == [
        "Alignment has no effect while the panel fills the whole edge."
    ]
    assert generator.notes(theme(height=40)) == []
    assert "evaluateScript" in generator.reload_command(theme(height=40))
    assert generator.problems(theme(height=40)) == []


def test_hiding_and_opacity_are_read_live_not_from_the_late_config(runner, shell):
    # plasmashell has not written plasmashellrc yet; the snapshot must still be right.
    first = engine.apply(theme(visibility="windowsgobelow", opacity_mode="opaque"), runner)
    assert shell.pending
    second = engine.apply(theme(location="top"), runner)

    assert second.snapshot.settings["panel_layout"]["hiding"] == "windowsgobelow"
    assert second.snapshot.settings["panel_layout"]["opacity"] == "opaque"
    engine.restore(second.snapshot, runner, consume=True)
    assert (shell.state()["hiding"], shell.state()["opacity"]) == ("windowsgobelow", "opaque")
    engine.restore(first.snapshot, runner, consume=True)
    assert (shell.state()["hiding"], shell.state()["opacity"]) == ("none", "adaptive")


def test_without_the_layout_dump_the_config_keys_are_used(runner, shell):
    shell.no_dump = True
    shell.panels[161]["hiding"] = "windowsgobelow"
    shell.panels[161]["opacity"] = "translucent"
    shell.adaptive_disabled = True
    shell.persist(shell.panels[161], "hiding", "windowsgobelow")
    shell.persist(shell.panels[161], "opacity", "translucent")
    shell.sync()

    settings = PanelLayoutGenerator().capture_settings(runner)

    assert (settings["hiding"], settings["opacity"]) == ("windowsgobelow", "translucent")


def test_a_dump_that_cannot_tell_the_panels_apart_is_not_used(runner, use_generators):
    use_generators(PanelLayoutGenerator())
    shell = FakePlasmashell(
        runner, [panel(1, hiding="autohide"), panel(2, screen=1, hiding="windowsgobelow", opacity="opaque")]
    )
    shell.panels[1]["opacity"] = "translucent"
    shell.persist(shell.panels[1], "hiding", "autohide")
    shell.persist(shell.panels[1], "opacity", "translucent")
    shell.sync()

    settings = PanelLayoutGenerator().capture_settings(runner)

    assert settings["panel"] == 1
    assert (settings["hiding"], settings["opacity"]) == ("autohide", "translucent")


def test_is_active_is_exact_for_height_and_for_the_modes_the_getters_hide(runner, shell):
    generator = PanelLayoutGenerator()
    assert not generator.is_active(theme(height=30), runner)  # the panel is 46, not "at least 30"
    assert generator.is_active(theme(height=46), runner)
    assert not generator.is_active(theme(visibility="windowsgobelow"), runner)
    assert not generator.is_active(theme(opacity_mode="opaque"), runner)

    generator.reload(theme(visibility="windowsgobelow"), runner)
    assert generator.is_active(theme(visibility="windowsgobelow"), runner)
    assert not generator.is_active(theme(visibility="none"), runner)


def test_what_the_getters_cannot_tell_apart_does_not_count_as_in_use(runner, shell):
    """Without the layout dump the getters say "none" for windows-go-below and
    "translucent" for any opacity the style cannot draw. A theme that asks for such a
    value must get its apply, not "the desktop already uses it"."""
    shell.no_dump = True
    shell.adaptive_disabled = True
    generator = PanelLayoutGenerator()

    assert not generator.is_active(theme(visibility="windowsgobelow"), runner)
    assert not generator.is_active(theme(opacity_mode="opaque"), runner)
    assert not generator.is_active(theme(opacity_mode="adaptive"), runner)
    assert generator.is_active(theme(visibility="none", opacity_mode="translucent"), runner)

    generator.reload(theme(visibility="windowsgobelow", opacity_mode="opaque"), runner)  # still succeeds
    assert shell.state()["hiding"] == "windowsgobelow"


def test_a_thickness_below_the_minimum_is_raised_and_still_counts_as_applied(runner, shell):
    shell.min_height = 40
    generator = PanelLayoutGenerator()
    generator.reload(theme(height=24), runner)
    assert shell.state()["height"] == 40
    assert not generator.is_active(theme(height=24), runner)


def test_an_undo_waits_for_plasma_to_let_go_of_the_old_styles_minimum(runner, shell, pauses):
    """Seen in the rig: right after the style is put back, a 14 px panel comes back as 24."""
    shell.panels[161]["height"] = 14
    generator = PanelLayoutGenerator()
    settings = generator.capture_settings(runner)
    generator.reload(theme(height=44, location="top"), runner)
    shell.old_minimum, shell.old_minimum_writes = 24, 3

    generator.restore_settings(settings, runner)

    assert (shell.state()["height"], shell.state()["location"]) == (14, "bottom")
    assert len(pauses) == 3
    assert shell.writes[-4:] == ["height"] * 4  # only the thickness is asked for again


def test_an_undo_gives_up_on_a_thickness_plasma_never_takes(runner, shell, pauses):
    shell.panels[161]["height"] = 14
    generator = PanelLayoutGenerator()
    settings = generator.capture_settings(runner)
    generator.reload(theme(height=44), runner)
    shell.min_height = 24

    with pytest.raises(ApplyError) as error:
        generator.restore_settings(settings, runner)

    assert str(error.value).endswith("wanted 14, got 24.")
    assert len(pauses) == pl._SETTLE_TRIES


def test_an_apply_waits_for_a_thinner_panel_too(runner, shell, pauses):
    shell.old_minimum, shell.old_minimum_writes = 40, 2

    PanelLayoutGenerator().reload(theme(height=24), runner)

    assert shell.state()["height"] == 24 and len(pauses) == 2


def test_a_write_that_is_taken_at_once_does_not_wait(runner, shell, pauses):
    PanelLayoutGenerator().reload(theme(height=60, location="top"), runner)  # thicker than before
    PanelLayoutGenerator().reload(theme(location="left"), runner)  # no thickness at all
    assert pauses == [] and shell.writes == ["location", "height", "location"]


def test_alignment_or_length_alone_makes_plasma_lay_the_panel_out_again(runner, shell):
    PanelLayoutGenerator().reload(theme(alignment="right"), runner)
    assert shell.shown[161] == ("right", "fill")
    PanelLayoutGenerator().reload(theme(length_mode="fit", height=46), runner)  # same height: no layout
    assert shell.shown[161] == ("right", "fit")


def test_an_error_message_has_no_line_numbers_or_backtrace(runner, shell):
    with pytest.raises(ApplyError) as error:
        pl._write(runner, {"alignment": "diagonal"})
    assert str(error.value).endswith("invalid alignment: diagonal")


def test_undo_writes_only_what_the_apply_changed(runner, shell):
    result = engine.apply(theme(location="top", height=60), runner)
    shell.writes.clear()

    assert engine.restore(result.snapshot, runner, consume=True) == []

    assert shell.writes == ["location", "height"]  # alignment and the rest were as before
    assert (shell.state()["location"], shell.state()["height"]) == ("bottom", 46)


def test_a_panel_that_is_as_it_was_is_not_written_to(runner, shell):
    settings = PanelLayoutGenerator().capture_settings(runner)
    shell.scripts.clear()

    PanelLayoutGenerator().restore_settings(settings, runner)

    assert shell.writes == []
    assert all('"op": "read"' in script for script in shell.scripts)


def test_without_the_layout_dump_undo_writes_hiding_and_opacity_to_be_sure(runner, shell):
    shell.no_dump = True
    settings = PanelLayoutGenerator().capture_settings(runner)

    PanelLayoutGenerator().restore_settings(settings, runner)

    assert shell.writes == ["hiding", "opacity"]


def test_undo_gives_back_a_panel_thinner_than_a_theme_may_ask_for(runner, shell):
    shell.panels[161]["height"] = 12
    result = engine.apply(theme(height=40, floating=False), runner)
    assert (shell.state()["height"], shell.state()["floating"]) == (40, False)

    assert engine.restore(result.snapshot, runner, consume=True) == []

    assert (shell.state()["height"], shell.state()["floating"]) == (12, True)


def test_an_apply_keeps_the_lower_limit_and_a_refused_request_sets_nothing(runner, shell):
    before = shell.state()
    with pytest.raises(ApplyError) as error:
        pl._write(runner, {"location": "top", "height": 10, "floating": False}, min_height=pl.MIN_HEIGHT)
    assert str(error.value).endswith("invalid height: 10")
    assert shell.writes == [] and shell.state() == before
    # The apply itself asks with the limit, the undo without it.
    PanelLayoutGenerator().reload(theme(height=30), runner)
    assert f'"minHeight": {pl.MIN_HEIGHT}' in shell.scripts[-1].split("\n")[1]


def run_program(request, panels):
    """Run the real script in a JavaScript engine, with stand-ins for what plasmashell
    gives it. Returns what it printed (or None when it stopped with an error), the
    error text and the panels as they are afterwards."""
    qml = pytest.importorskip("PySide6.QtQml")
    js = qml.QJSEngine()
    js.evaluate(
        "var printed = [];\n"
        "function print(text) { printed.push(text); }\n"
        f"var panels = {json.dumps(panels)};\n"
        "var panelIds = panels.map(function (p) { return p.id; });\n"
        "function panelById(id) {\n"
        "    for (var i = 0; i < panels.length; i++) { if (panels[i].id === id) { return panels[i]; } }\n"
        "    return null;\n"
        "}\n"
    )
    outcome = js.evaluate(pl.build_script(request))
    error = outcome.toString() if outcome.isError() else ""
    printed = json.loads(js.evaluate("JSON.stringify(printed)").toString())
    after = json.loads(js.evaluate("JSON.stringify(panels)").toString())
    return (json.loads(printed[0]) if printed else None), error, after


def request(values, op="write", panel=None, min_height=1):
    return {"op": op, "panel": panel, "set": values, "minHeight": min_height}


def test_the_real_script_sets_what_is_asked_and_answers_with_the_state(app):
    answer, error, (after,) = run_program(
        request({"location": "top", "height": 30, "floating": False, "hiding": "autohide"}), [panel(161)]
    )
    assert error == ""
    assert (after["location"], after["height"], after["floating"], after["hiding"]) == (
        "top",
        30,
        False,
        "autohide",
    )
    assert answer == {
        key: after[key]
        for key in ("id", "location", "height", "alignment", "lengthMode", "floating", "hiding", "opacity")
    } | {"found": True}


def test_the_real_script_only_reads_when_asked_to_read(app):
    before = panel(161)
    answer, error, (after,) = run_program(request({"location": "top"}, op="read"), [before])
    assert error == "" and after == before
    assert answer["found"] and answer["location"] == "bottom"


@pytest.mark.parametrize(
    ("values", "min_height", "message"),
    [
        ({"location": "top", "height": 10, "floating": False}, 20, "invalid height: 10"),
        ({"location": "top", "height": "40"}, 1, "invalid height: 40"),
        ({"location": "top", "height": None}, 1, "invalid height: null"),
        ({"location": "top", "height": 0}, 1, "invalid height: 0"),
        ({"location": "top", "height": float("inf")}, 1, "invalid height: Infinity"),
        ({"location": "top", "height": float("nan")}, 1, "invalid height: NaN"),
        ({"location": "top", "floating": "yes"}, 1, "invalid floating: yes"),
        ({"location": "top", "opacity": "glass"}, 1, "invalid opacity: glass"),
        ({"alignment": "left", "location": "middle"}, 1, "invalid location: middle"),
    ],
)
def test_the_real_script_sets_nothing_when_one_value_is_refused(app, values, min_height, message):
    before = panel(161)
    answer, error, (after,) = run_program(request(values, min_height=min_height), [before])
    assert answer is None
    assert error.endswith(message)
    assert after == before


def test_the_real_script_lets_an_undo_make_the_panel_thin_again(app):
    answer, error, (after,) = run_program(request({"height": 12}), [panel(161)])
    assert error == "" and after["height"] == 12 and answer["height"] == 12


def test_the_real_script_chooses_the_same_panel_as_the_stand_in(app):
    panels = [
        panel(7, screen=1, length=3000),
        panel(9, length=800),
        panel(4, length=1920),
        panel(3, length=1920),
    ]
    answer, _error, _after = run_program(request({}, op="read"), panels)
    assert answer["id"] == 3  # lowest screen, then longest, then lowest id
    answer, _error, _after = run_program(request({}, op="read", panel=9), panels)
    assert answer["id"] == 9
    answer, _error, _after = run_program(request({}, op="read", panel=99), panels)
    assert answer == {"found": False}
    answer, _error, _after = run_program(request({}, op="read"), [])
    assert answer == {"found": False}
