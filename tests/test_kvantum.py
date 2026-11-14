# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The application style target: a Kvantum theme made from the theme."""

import configparser
import xml.etree.ElementTree as ET

import pytest

from plasma_theme_studio import kconfig, paths
from plasma_theme_studio.apply import desktop, engine
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.generators import MARKER, XML_MARKER, ColorSchemeGenerator, PlannedFile, made_here
from plasma_theme_studio.generators import kvantum as kv
from plasma_theme_studio.generators.kvantum import KvantumGenerator
from plasma_theme_studio.model.theme import Theme

GENERATOR = KvantumGenerator()


def look(radius=6, border=1, style="generated", name="My Theme", **colors):
    values = {
        ("meta", "name"): name,
        ("apps", "style"): style,
        ("apps", "radius"): radius,
        ("apps", "border_width"): border,
    }
    values.update({("colors", key): value for key, value in colors.items()})
    return Theme(values)


def kvantum_dir():
    return paths.config_home() / "Kvantum"


def folders():
    root = kvantum_dir()
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def selection():
    path = kvantum_dir() / "kvantum.kvconfig"
    return path.read_text() if path.exists() else None


def parsed(text):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string(text)
    return parser


def planned(theme):
    kvconfig, svg = GENERATOR.files(theme)
    return kvconfig, svg


def svg_ids(theme):
    return {e.get("id") for e in ET.fromstring(planned(theme)[1].content).iter()}


def element(theme, element_id):
    return next(e for e in ET.fromstring(planned(theme)[1].content).iter() if e.get("id") == element_id)


# a runner with the programs of the target


def widget_style_file():
    return paths.config_home() / "kdeglobals"


class Desktop:
    """kdeglobals' widgetStyle is kept as a real file (the library reads it from there),
    everything else goes to the stock FakeRunner. Signals are recorded."""

    def __init__(self, runner):
        self.runner = runner
        self.signals = []
        self.events = []
        runner.handlers["dbus-send"] = self.signal
        runner.handlers["kwriteconfig6"] = self.config
        runner.handlers["kreadconfig6"] = self.config

    def signal(self, argv):
        self.signals.append(argv[-2:])
        self.events.append(("signal", argv[-2], argv[-1]))
        return Result(0)

    def config(self, argv):
        if "widgetStyle" not in argv:
            return type(self.runner)._config(self.runner, argv)
        path = widget_style_file()
        groups = kconfig.parse(path.read_text()) if path.exists() else {}
        entries = groups.setdefault(("KDE",), {})
        if argv[0] == "kreadconfig6":
            default = argv[argv.index("--default") + 1] if "--default" in argv else ""
            return Result(0, entries.get("widgetStyle", default) + "\n")
        if "--delete" in argv:
            entries.pop("widgetStyle", None)
        else:
            entries["widgetStyle"] = argv[argv.index("--") + 1]
            self.events.append(("style", entries["widgetStyle"]))
        lines = []
        for names, items in groups.items():
            if items:
                lines += [f"[{names[0]}]", *(f"{key}={value}" for key, value in items.items()), ""]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines))
        return Result(0)

    def style(self):
        return kconfig.user_value("kdeglobals", ["KDE"], "widgetStyle")

    def set_style(self, value):
        self.config(
            ["kwriteconfig6", "--file", "kdeglobals", "--group", "KDE", "--key", "widgetStyle", "--", value]
        )
        self.events.clear()
        self.signals.clear()


@pytest.fixture
def desk(runner, use_generators):
    use_generators(ColorSchemeGenerator(), GENERATOR)
    return Desktop(runner)


# files


def test_the_theme_folder_holds_a_kvconfig_and_an_svg():
    theme = look()
    kvconfig, svg = planned(theme)
    name = kv.folder_name(theme)
    assert kvconfig.path == kvantum_dir() / name / f"{name}.kvconfig"
    assert svg.path == kvantum_dir() / name / f"{name}.svg"
    assert kvconfig.content.startswith(MARKER) and kvconfig.marker == MARKER
    assert svg.content.startswith(XML_MARKER + "\n<svg") and svg.marker == XML_MARKER
    assert "<?xml" not in svg.content and "<text" not in svg.content


def test_every_element_a_section_names_is_in_the_svg():
    for radius, border in ((0, 0), (6, 1), (12, 2), (24, 4), (3, 4)):
        theme = look(radius, border)
        ids = svg_ids(theme)
        config = parsed(planned(theme)[0].content)
        names = {
            value
            for section in config.sections()
            for key, value in config.items(section)
            if key in ("frame.element", "interior.element", "indicator.element")
        }
        assert names
        for name in names:
            assert any(i and i.startswith(name + "-") for i in ids), name
        for file in planned(theme):
            assert GENERATOR.check_output(file) == []


def test_a_frame_has_all_eight_pieces():
    ids = svg_ids(look())
    for base in ("button-normal", "lineedit-focused", "tab-toggled", "menu-normal", "group-normal"):
        for piece in ("top", "bottom", "left", "right", "topleft", "topright", "bottomleft", "bottomright"):
            assert f"{base}-{piece}" in ids
    assert "button-normal" in ids  # the interior


def test_border_zero_draws_no_border():
    flat = element(look(6, 0), "button-normal-topleft")
    framed = element(look(6, 2), "button-normal-topleft")
    assert len(list(flat.iter("{http://www.w3.org/2000/svg}path"))) == 1
    assert len(list(framed.iter("{http://www.w3.org/2000/svg}path"))) == 2


def test_the_border_color_is_the_derived_edge_color():
    theme = look(6, 2, window="#202020", text="#ffffff")
    corner = ET.tostring(element(theme, "button-normal-topleft"), encoding="unicode")
    assert kv._mix("#202020", "#ffffff", 0.22) in corner


def test_the_colors_of_the_theme_are_in_both_files():
    theme = look(accent="#e53935", window="#101214", view="#050607")
    kvconfig, svg = planned(theme)
    config = parsed(kvconfig.content)
    assert config["GeneralColors"]["highlight.color"] == "#e53935"
    assert config["GeneralColors"]["window.color"] == "#101214"
    assert config["GeneralColors"]["base.color"] == "#050607"
    assert "#e53935" in svg.content


def test_controls_are_capped_and_containers_follow_the_radius():
    config = parsed(planned(look(radius=20, border=1))[0].content)
    assert config["PanelButtonCommand"]["frame.top"] == str(kv.CONTROL_CAP)
    assert config["LineEdit"].get("frame.top", config["PanelButtonCommand"]["frame.top"]) == str(
        kv.CONTROL_CAP
    )
    assert config["Menu"]["frame.top"] == "20"
    assert config["GroupBox"]["frame.left"] == "20"
    small = parsed(planned(look(radius=4, border=1))[0].content)
    assert small["PanelButtonCommand"]["frame.top"] == "4"
    assert small["Menu"]["frame.top"] == "4"


def test_a_border_wider_than_the_radius_still_fits_its_pieces():
    theme = look(radius=0, border=4)
    assert parsed(planned(theme)[0].content)["PanelButtonCommand"]["frame.top"] == "4"
    assert GENERATOR.check_output(planned(theme)[1]) == []


def test_the_apps_values_follow_the_shape_values_until_set():
    theme = Theme({("apps", "style"): "generated", ("shape", "radius"): 10, ("shape", "border_width"): 3})
    assert kv.look_of(theme)[1:] == (10, 3)
    theme.set("apps", "radius", 2)
    assert kv.look_of(theme)[1:] == (2, 3)


def test_the_notes_say_when_the_radius_is_above_the_cap():
    assert not any(str(kv.CONTROL_CAP) in str(n) for n in GENERATOR.notes(look(radius=6)))
    assert any(str(kv.CONTROL_CAP) in str(n) for n in GENERATOR.notes(look(radius=12)))
    assert GENERATOR.notes(look(style="unchanged"))


def test_wanted_only_when_generated():
    assert GENERATOR.wanted(look())
    assert not GENERATOR.wanted(look(style="unchanged"))


# the check


def test_the_check_rejects_bad_xml_text_and_missing_elements():
    theme = look()
    kvconfig, svg = planned(theme)
    broken = PlannedFile(svg.path, svg.content.replace("</svg>", ""), XML_MARKER)
    texty = PlannedFile(svg.path, svg.content.replace("</svg>", "<text>x</text></svg>"), XML_MARKER)
    assert GENERATOR.check_output(broken)
    assert GENERATOR.check_output(texty)
    stripped = PlannedFile(kvconfig.path, kvconfig.content + "\n[X]\nframe.element=nothing\n", MARKER)
    assert GENERATOR.check_output(stripped)


# names and stale folders


def test_the_folder_name_has_the_theme_name_and_a_hash_of_the_contents():
    theme = look()
    name = kv.folder_name(theme)
    assert name.startswith("PlasmaThemeStudio-MyTheme-")
    assert kv.folder_name(look()) == name
    assert kv.folder_name(look(radius=7)) != name
    assert kv.folder_name(look(border=2)) != name
    assert kv.folder_name(look(accent="#ff0000")) != name
    assert kv.folder_name(look(name="Other")) != name


def test_old_folders_of_ours_are_stale_and_foreign_ones_are_not(desk):
    old, new = look(radius=4), look(radius=9)
    engine.apply(old, desk.runner)
    foreign = kvantum_dir() / "PlasmaThemeStudio-Foreign"
    foreign.mkdir()
    (foreign / "PlasmaThemeStudio-Foreign.kvconfig").write_text("[General]\n")
    other = kvantum_dir() / "Nordic"
    other.mkdir()
    (other / "Nordic.kvconfig").write_text(MARKER + "\n")
    (kvantum_dir() / kv.folder_name(old) / "notes.txt").write_text("mine")

    stale = GENERATOR.stale_files(new)

    assert kvantum_dir() / kv.folder_name(old) in stale
    assert kvantum_dir() / kv.folder_name(old) / "notes.txt" not in stale
    assert foreign not in stale and other not in stale
    assert not any(path.is_relative_to(foreign) or path.is_relative_to(other) for path in stale)
    assert GENERATOR.stale_files(old) == []


def test_a_foreign_file_at_a_planned_path_blocks_the_apply(desk):
    theme = look()
    kvconfig = planned(theme)[0]
    kvconfig.path.parent.mkdir(parents=True)
    kvconfig.path.write_text("[General]\nauthor=someone\n")
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(theme, desk.runner)
    assert kvconfig.path.read_text() == "[General]\nauthor=someone\n"
    assert not made_here(kvconfig.path)
    assert selection() is None


# kvantum.kvconfig


def test_with_theme_changes_only_the_theme_line():
    text = "[General]\ntheme=Nordic\n\n[Applications]\nKvantum\\x20Manager=KvFlat\nkate, okular=KvArc\n"
    result = kv.with_theme(text, "Mine")
    assert (
        result == "[General]\ntheme=Mine\n\n[Applications]\nKvantum\\x20Manager=KvFlat\nkate, okular=KvArc\n"
    )
    assert kv.selected_theme(result) == "Mine"


def test_with_theme_adds_the_line_or_the_section():
    assert kv.with_theme("", "Mine") == "[General]\ntheme=Mine\n"
    assert kv.with_theme("[General]\n", "Mine") == "[General]\ntheme=Mine\n"
    added = kv.with_theme("[General]\nx=1\n\n[Applications]\na=b\n", "Mine")
    assert added == "[General]\nx=1\ntheme=Mine\n\n[Applications]\na=b\n"
    only = kv.with_theme("[Applications]\na=b\n", "Mine")
    assert kv.selected_theme(only) == "Mine" and "[Applications]\na=b" in only


def test_selected_theme_reads_only_the_general_section():
    assert kv.selected_theme("[Applications]\ntheme=No\n[General]\ntheme=Yes\n") == "Yes"
    assert kv.selected_theme("[%General]\ntheme=Yes\n") == "Yes"
    assert kv.selected_theme("") is None


# settings


def test_capture_reads_the_style_and_the_whole_selection_file(desk):
    desk.set_style("breeze")
    kvantum_dir().mkdir(parents=True)
    (kvantum_dir() / "kvantum.kvconfig").write_text("[General]\ntheme=Nordic\n[Applications]\na=b\n")
    saved = GENERATOR.capture_settings(desk.runner)
    assert saved["style"] == "breeze" and saved["masked"] is False
    assert saved["selection"] == "[General]\ntheme=Nordic\n[Applications]\na=b\n"


def test_capture_of_nothing_says_so(desk):
    saved = GENERATOR.capture_settings(desk.runner)
    assert saved["style"] is None
    assert saved["selection"] == desktop.ABSENT


def test_reload_selects_the_theme_and_the_style_and_tells_applications(desk):
    theme = look()
    kvantum_dir().mkdir(parents=True)
    (kvantum_dir() / "kvantum.kvconfig").write_text("[General]\ntheme=Nordic\n\n[Applications]\na=b\n")
    GENERATOR.reload(theme, desk.runner)
    assert kv.selected_theme(selection()) == kv.folder_name(theme)
    assert "[Applications]\na=b" in selection()
    assert desk.style() == "kvantum"
    assert desk.signals == [["int32:2", "int32:0"]]


def test_reload_hops_through_fusion_when_kvantum_is_already_the_style(desk, pauses):
    desk.set_style("kvantum")
    GENERATOR.reload(look(), desk.runner)
    assert [e for e in desk.events if e[0] == "style"] == [("style", "fusion"), ("style", "kvantum")]
    assert desk.signals == [["int32:2", "int32:0"], ["int32:2", "int32:0"]]
    assert pauses == [kv.HOP_PAUSE]
    assert desk.style() == "kvantum"


def test_reload_does_not_hop_from_another_style(desk, pauses):
    desk.set_style("breeze")
    GENERATOR.reload(look(), desk.runner)
    assert [e for e in desk.events if e[0] == "style"] == [("style", "kvantum")]
    assert pauses == []


def test_reload_without_a_signal_tool_still_succeeds(desk):
    desk.runner.missing.update({"dbus-send", "busctl"})
    GENERATOR.reload(look(), desk.runner)
    assert desk.style() == "kvantum"


def test_restore_puts_back_the_style_the_file_and_tells_applications(desk):
    desk.set_style("breeze")
    kvantum_dir().mkdir(parents=True)
    original = "[General]\ntheme=Nordic\n\n[Applications]\na=b\n"
    (kvantum_dir() / "kvantum.kvconfig").write_text(original)
    saved = GENERATOR.capture_settings(desk.runner)
    GENERATOR.reload(look(), desk.runner)
    desk.signals.clear()

    GENERATOR.restore_settings(saved, desk.runner)

    assert selection() == original
    assert desk.style() == "breeze"
    assert desk.signals == [["int32:2", "int32:0"], ["int32:0", "int32:0"]]


def test_restore_removes_what_was_not_there(desk):
    saved = GENERATOR.capture_settings(desk.runner)
    GENERATOR.reload(look(), desk.runner)
    GENERATOR.restore_settings(saved, desk.runner)
    assert selection() is None
    assert desk.style() is None


def test_restore_hops_when_kvantum_was_in_use_before(desk, pauses):
    desk.set_style("kvantum")
    kvantum_dir().mkdir(parents=True)
    (kvantum_dir() / "kvantum.kvconfig").write_text("[General]\ntheme=Nordic\n")
    saved = GENERATOR.capture_settings(desk.runner)
    GENERATOR.reload(look(), desk.runner)
    pauses.clear()
    desk.events.clear()

    GENERATOR.restore_settings(saved, desk.runner)

    assert [e for e in desk.events if e[0] == "style"] == [("style", "fusion"), ("style", "kvantum")]
    assert pauses == [kv.HOP_PAUSE]
    assert selection() == "[General]\ntheme=Nordic\n"


def test_restore_of_an_untouched_state_does_nothing(desk):
    desk.set_style("breeze")
    saved = GENERATOR.capture_settings(desk.runner)
    GENERATOR.restore_settings(saved, desk.runner)
    assert desk.signals == [] and desk.events == []


# is_active, unavailable, warnings


def test_is_active_needs_the_style_the_selection_and_the_files(desk):
    theme = look()
    assert not GENERATOR.is_active(theme, desk.runner)
    engine.apply(theme, desk.runner)
    assert GENERATOR.is_active(theme, desk.runner)
    assert engine.is_current(engine.build_plan(theme, desk.runner), desk.runner)

    desk.set_style("breeze")
    assert not GENERATOR.is_active(theme, desk.runner)
    desk.set_style("Kvantum-dark")
    assert GENERATOR.is_active(theme, desk.runner)

    (kvantum_dir() / "kvantum.kvconfig").write_text("[General]\ntheme=Nordic\n")
    assert not GENERATOR.is_active(theme, desk.runner)
    (kvantum_dir() / "kvantum.kvconfig").write_text(f"[General]\ntheme={kv.folder_name(theme)}\n")
    assert GENERATOR.is_active(theme, desk.runner)
    planned(theme)[1].path.write_text("changed")
    assert not GENERATOR.is_active(theme, desk.runner)


def test_unavailable_without_the_plugin_and_without_kvantummanager(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(kv, "plugin_dirs", lambda: [tmp_path / "none"])
    assert GENERATOR.unavailable_reason(runner) is None  # kvantummanager is on the PATH
    runner.missing.add("kvantummanager")
    assert GENERATOR.unavailable_reason(runner)
    styles = tmp_path / "plugins" / "styles"
    styles.mkdir(parents=True)
    (styles / "libkvantum.so").write_text("")
    monkeypatch.setattr(kv, "plugin_dirs", lambda: [tmp_path / "plugins"])
    assert GENERATOR.unavailable_reason(runner) is None


def test_the_plan_reports_a_missing_kvantum(desk, monkeypatch, tmp_path):
    monkeypatch.setattr(kv, "plugin_dirs", lambda: [])
    desk.runner.missing.add("kvantummanager")
    plan = engine.build_plan(look(), desk.runner)
    assert plan.blocking


def test_warnings_name_a_style_and_a_kvantum_theme_that_are_replaced(desk):
    assert GENERATOR.warnings(look(), desk.runner) == []
    desk.set_style("oxygen")
    assert any("oxygen" in str(w) for w in GENERATOR.warnings(look(), desk.runner))
    desk.set_style("kvantum")
    kvantum_dir().mkdir(parents=True)
    (kvantum_dir() / "kvantum.kvconfig").write_text("[General]\ntheme=Nordic\n")
    assert any("Nordic" in str(w) for w in GENERATOR.warnings(look(), desk.runner))


# the engine


def test_apply_and_undo_through_the_engine(desk):
    theme = look()
    desk.set_style("breeze")
    kvantum_dir().mkdir(parents=True)
    original = "[General]\ntheme=Nordic\n\n[Applications]\na=b\n"
    (kvantum_dir() / "kvantum.kvconfig").write_text(original)
    before = folders()

    result = engine.apply(theme, desk.runner)

    assert folders() == [*before, kv.folder_name(theme)]
    assert desk.style() == "kvantum"
    assert kv.selected_theme(selection()) == kv.folder_name(theme)
    assert "[Applications]\na=b" in selection()
    assert result.snapshot.settings["apps"]["selection"] == original

    assert engine.restore(result.snapshot, desk.runner, consume=True) == []

    assert selection() == original
    assert desk.style() == "breeze"
    assert folders() == before


def test_a_second_look_replaces_the_first_and_the_undo_brings_it_back(desk):
    first, second = look(radius=4), look(radius=10)
    engine.apply(first, desk.runner)
    result = engine.apply(second, desk.runner)
    assert folders() == [kv.folder_name(second)]
    assert desk.signals  # applications were told

    engine.restore(result.snapshot, desk.runner, consume=True)

    assert folders() == [kv.folder_name(first)]
    assert kv.selected_theme(selection()) == kv.folder_name(first)
    assert desk.style() == "kvantum"


def test_a_theme_that_leaves_the_style_alone_touches_nothing(desk):
    engine.apply(look(style="unchanged"), desk.runner)
    assert folders() == [] and selection() is None and desk.style() is None


def test_a_failed_reload_rolls_everything_back(desk):
    desk.set_style("breeze")
    desk.runner.handlers["kwriteconfig6"] = lambda argv: (
        Result(1, "", "nope") if "widgetStyle" in argv else Result(0)
    )
    with pytest.raises(engine.ApplyError):
        engine.apply(look(), desk.runner)
    assert folders() == [] and selection() is None
    assert desk.style() == "breeze"
