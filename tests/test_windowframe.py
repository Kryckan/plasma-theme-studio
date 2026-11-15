# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The window frame target: Breeze with its own steps, or a generated Aurorae theme."""

import math
import xml.etree.ElementTree as ET

import pytest

from plasma_theme_studio import kconfig, paths
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.generators import ApplyError, PlannedFile, made_here
from plasma_theme_studio.generators import windowframe as wf
from plasma_theme_studio.generators.windowframe import WindowFrameGenerator
from plasma_theme_studio.model.theme import Theme

KWIN = ("kwinrc", ["org.kde.kdecoration2"])


def theme(mode="generated", **values):
    """A theme; keys are written "section__key"."""
    base = {("window", "decoration"): mode}
    base.update({tuple(key.split("__")): value for key, value in values.items()})
    return Theme(base)


def kwin_value(key):
    return kconfig.user_value("kwinrc", ["org.kde.kdecoration2"], key)


def breeze_value(key):
    return kconfig.user_value("breezerc", ["Common"], key)


def folders():
    root = paths.data_home() / "aurorae" / "themes"
    return sorted(p.name for p in root.iterdir()) if root.is_dir() else []


class Kwin:
    """Stands in for qdbus6: counts reconfigure calls and can refuse them."""

    def __init__(self, runner):
        self.reconfigured = 0
        self.fail = False
        self.report = None  # the text of supportInformation, if KWin should answer it
        runner.handlers["qdbus6"] = self

    def __call__(self, argv):
        if argv[-1] == "supportInformation":
            return Result(0, self.report) if self.report is not None else Result(1, "", "no")
        self.reconfigured += 1
        return Result(1, "", "No such object") if self.fail else Result(0)


@pytest.fixture
def kwin(runner, use_generators):
    use_generators(WindowFrameGenerator())
    return Kwin(runner)


@pytest.fixture
def no_pause(monkeypatch):
    monkeypatch.setattr(wf, "_pause", lambda seconds: None)


# ---- pure: Breeze steps -------------------------------------------------


@pytest.mark.parametrize(
    ("size", "step"),
    [
        (0, "ShadowNone"),
        (7, "ShadowNone"),
        (8, "ShadowSmall"),
        (16, "ShadowSmall"),
        (23, "ShadowSmall"),
        (24, "ShadowMedium"),
        (40, "ShadowLarge"),
        (48, "ShadowLarge"),
        (56, "ShadowVeryLarge"),
        (64, "ShadowVeryLarge"),
    ],
)
def test_the_shadow_size_goes_to_the_nearest_breeze_step(size, step):
    assert wf.breeze_shadow_step(size)[0] == step


@pytest.mark.parametrize(("strength", "stored"), [(0, 25), (1, 255), (0.5, 140), (0.35, 105)])
def test_the_shadow_strength_uses_breezes_own_range(strength, stored):
    assert wf.breeze_strength(strength) == stored


@pytest.mark.parametrize(
    ("width", "step"),
    [
        (0, "None"),
        (1, "Tiny"),
        (2, "Tiny"),
        (3, "Normal"),
        (4, "Normal"),
        (5, "Large"),
        (7, "VeryLarge"),
        (9, "Huge"),
        (12, "VeryHuge"),
    ],
)
def test_the_border_width_goes_to_a_breeze_border_size(width, step):
    assert wf.breeze_border_size(width)[0] == step


@pytest.mark.parametrize(
    ("width", "size"),
    [
        (0, "None"),
        (1, "Tiny"),
        (4, "Tiny"),
        (5, "Normal"),
        (6, "Normal"),
        (7, "Large"),
        (8, "Large"),
        (12, "VeryLarge"),
    ],
)
def test_the_aurorae_border_size_contains_the_wanted_width(width, size):
    assert wf.aurorae_border_size(width) == size
    ranges = {"None": (0, 0), "Tiny": (1, 4), "Normal": (4, 6), "Large": (6, 8), "VeryLarge": (8, 12)}
    low, high = ranges[size]
    assert low <= width <= high  # KWin keeps the border inside this range


@pytest.mark.parametrize("border", range(0, 13))
@pytest.mark.parametrize("radius", range(0, 25))
def test_square_window_content_stays_inside_the_bottom_corner(radius, border):
    bottom = wf.bottom_radius(radius, border)
    assert 0 <= bottom <= radius
    # The content's corner is the border away from both edges; the arc's centre is `bottom` away.
    assert (bottom - border) * math.sqrt(2) <= bottom + 1e-9 or bottom == 0


# ---- pure: generated content ----------------------------------------------


def contents(t):
    return {f.path.name: f.content for f in WindowFrameGenerator().files(t)}


def ids(svg):
    return {element.get("id") for element in ET.fromstring(svg).iter() if element.get("id")}


def test_the_generated_files_are_marked_and_complete():
    t = theme(meta__name="Night Sky")
    planned = WindowFrameGenerator().files(t)
    folder = wf.frame_folder(t)
    assert {f.path.name for f in planned} == {
        "metadata.desktop",
        f"{folder}rc",
        "decoration.svg",
        *(f"{name}.svg" for name in wf.BUTTON_FILES),
    }
    for file in planned:
        assert file.content.startswith(file.marker)
        assert file.path.parent == paths.data_home() / "aurorae" / "themes" / folder
    assert {f.marker for f in planned if f.path.suffix == ".svg"} == {wf.XML_MARKER}
    assert "<?xml" not in contents(t)["decoration.svg"]
    metadata = contents(t)["metadata.desktop"]
    assert "\nName=Night Sky\n" in metadata
    assert f"\nX-KDE-PluginInfo-Name={folder}\n" in metadata


def test_every_svg_has_the_elements_aurorae_reads_and_no_text():
    for name, svg in contents(theme()).items():
        if not name.endswith(".svg"):
            continue
        required = wf.REQUIRED_DECORATION if name == "decoration.svg" else wf.REQUIRED_BUTTON
        assert set(required) <= ids(svg), name
        assert not [e for e in ET.fromstring(svg).iter() if e.tag.endswith("text")]
    for file in WindowFrameGenerator().files(theme()):
        assert WindowFrameGenerator().check_output(file) == []


def test_a_theme_without_shadow_or_border_still_has_every_element():
    t = theme(shadow__size=0, window__border_width=0, window__radius=0)
    generator = WindowFrameGenerator()
    for file in generator.files(t):
        assert generator.check_output(file) == []


def rc_values(t):
    rc = next(f for f in WindowFrameGenerator().files(t) if f.path.name.endswith("rc"))
    parsed = kconfig.parse(rc.content)
    return rc, parsed


def test_the_rc_file_follows_border_shadow_and_colors():
    t = theme(window__radius=10, window__border_width=3, shadow__size=20, colors__text="#102030")
    rc, parsed = rc_values(t)
    assert rc.content.startswith("# Generated by Plasma Theme Studio.\n")
    assert rc.path.name == f"{wf.frame_folder(t)}rc"
    layout = parsed[("Layout",)]
    assert [layout[k] for k in ("BorderLeft", "BorderRight", "BorderBottom")] == ["3", "3", "3"]
    assert [layout[k] for k in ("PaddingLeft", "PaddingRight", "PaddingTop", "PaddingBottom")] == ["20"] * 4
    assert int(layout["TitleHeight"]) + int(layout["TitleEdgeTop"]) + int(layout["TitleEdgeBottom"]) == 30
    assert layout["ButtonWidth"] == layout["ButtonHeight"] == str(wf.BUTTON_SIZE)
    assert parsed[("General",)]["ActiveTextColor"] == "16,32,48"


def test_the_buttons_keep_clear_of_a_round_top_corner():
    small = rc_values(theme(window__radius=2))[1][("Layout",)]
    large = rc_values(theme(window__radius=24))[1][("Layout",)]
    assert int(large["TitleEdgeLeft"]) > int(small["TitleEdgeLeft"])


def test_the_folder_changes_with_the_look_and_not_with_other_fields():
    base = wf.frame_folder(theme())
    assert base.startswith("PlasmaThemeStudio-MyTheme-")
    assert len(base.rsplit("-", 1)[1]) == 8
    assert wf.frame_folder(theme()) == base
    for change in (
        {"window__radius": 9},
        {"window__border_width": 3},
        {"shadow__size": 30},
        {"shadow__strength": 0.6},
        {"colors__header": "#112233"},
        {"colors__window": "#112233"},
        {"colors__text": "#112233"},
        {"colors__text_muted": "#112233"},
        {"colors__negative": "#112233"},
        {"colors__accent": "#112233"},
        {"meta__name": "Another"},
    ):
        assert wf.frame_folder(theme(**change)) != base, change
    for unrelated in (
        {"meta__author": "Someone"},
        {"panel__opacity": 0.5},
        {"panel__style": "generated"},
        {"colors__view": "#112233"},
        {"colors__link": "#112233"},
        {"panel_layout__height": 60},
    ):
        assert wf.frame_folder(theme(**unrelated)) == base, unrelated


def test_the_window_values_follow_the_shape_values_unless_set():
    assert wf.frame_folder(theme(shape__radius=9)) == wf.frame_folder(theme(window__radius=9))
    assert wf.frame_folder(theme(shape__radius=9, window__radius=4)) == wf.frame_folder(
        theme(window__radius=4)
    )


# ---- pure: the pieces render with the right size ---------------------------

QtSvg = pytest.importorskip("PySide6.QtSvg")


@pytest.fixture
def qt(app):
    return app


def renderer(svg):
    from PySide6.QtCore import QByteArray

    return QtSvg.QSvgRenderer(QByteArray(svg.encode()))


LOOKS = [
    dict(window__radius=12, window__border_width=3, shadow__size=24),
    dict(window__radius=24, window__border_width=1, shadow__size=64),
    dict(window__radius=0, window__border_width=0, shadow__size=0),
    dict(window__radius=5, window__border_width=8, shadow__size=10),
    dict(window__radius=24, window__border_width=0, shadow__size=16),
]


@pytest.mark.parametrize("values", LOOKS)
def test_the_pieces_have_the_sizes_the_theme_asks_for(qt, values):
    t = theme(**values)
    look = wf.Look.of(t)
    svg = renderer(contents(t)["decoration.svg"])
    assert svg.isValid()
    p = look.shadow
    for prefix in ("decoration", "decoration-inactive"):
        size = {part: svg.boundsOnElement(f"{prefix}-{part}").size() for part in wf.PARTS}
        # Left and right pieces are as wide as the corners; top and bottom as high.
        for part in ("topleft", "left", "bottomleft", "topright", "right", "bottomright"):
            assert size[part].width() == p + look.side
        for part in ("topleft", "top", "topright"):
            assert size[part].height() == p + wf.TITLE_TOTAL
        for part in ("bottomleft", "bottom", "bottomright"):
            assert size[part].height() == p + look.base
    assert look.side >= look.radius
    assert look.base >= look.border
    assert svg.boundsOnElement("decoration-maximized-center").height() == wf.TITLE_TOTAL


@pytest.mark.parametrize("values", LOOKS)
def test_the_buttons_have_a_cell_for_every_state(qt, values):
    for name in wf.BUTTON_FILES:
        svg = renderer(contents(theme(**values))[f"{name}.svg"])
        assert svg.isValid(), name
        for state in wf.BUTTON_STATES:
            bounds = svg.boundsOnElement(f"{state}-center")
            assert (bounds.width(), bounds.height()) == (wf.BUTTON_SIZE, wf.BUTTON_SIZE), (name, state)


def piece_image(svg, element, scale=1):
    from PySide6.QtGui import QImage, QPainter

    bounds = svg.boundsOnElement(element)
    image = QImage(int(bounds.width() * scale), int(bounds.height() * scale), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    svg.render(painter, element)
    painter.end()
    return image


@pytest.mark.parametrize(
    ("radius", "border"), [(24, 1), (24, 3), (24, 8), (12, 2), (6, 1), (24, 12), (5, 4), (10, 3)]
)
def test_nothing_of_the_window_pokes_out_of_the_bottom_corners(qt, radius, border):
    """The frame around the content's corner is opaque on both sides of it."""
    t = theme(window__radius=radius, window__border_width=border, shadow__size=10)
    look = wf.Look.of(t)
    svg = renderer(contents(t)["decoration.svg"])
    p = look.shadow
    left = piece_image(svg, "decoration-bottomleft")
    right = piece_image(svg, "decoration-bottomright")
    # Content corner of the bottom left piece is at (p + border, base - border).
    cx, cy = p + border, look.base - border
    # The content's own corner pixel is at worst anti-aliased by the arc; the border row beneath it likewise.
    assert left.pixelColor(cx, cy - 1).alpha() >= 128
    assert left.pixelColor(cx, cy).alpha() >= 128
    rx = look.side - border - 1
    assert right.pixelColor(rx, cy - 1).alpha() >= 128
    assert right.pixelColor(rx, cy).alpha() >= 128


def test_the_outer_corner_is_round_and_the_shadow_is_soft(qt):
    t = theme(window__radius=20, window__border_width=8, shadow__size=24, shadow__strength=0.5)
    look = wf.Look.of(t)
    svg = renderer(contents(t)["decoration.svg"])
    topleft = piece_image(svg, "decoration-topleft")
    p = 24
    corner = topleft.pixelColor(p + 1, p + 1)
    assert corner.alpha() < 255  # the very corner of the window is cut away
    assert topleft.pixelColor(p + 20, p + 20).alpha() == 255
    # Shadow: transparent at the outside, darkest next to the window.
    top = piece_image(svg, "decoration-top")
    assert top.pixelColor(2, 0).alpha() <= 3
    next_to_window = top.pixelColor(2, p - 1).alpha()
    assert 0.4 * 255 < next_to_window <= 0.5 * 255 + 1
    assert top.pixelColor(2, p // 2).alpha() < next_to_window
    inactive = piece_image(svg, "decoration-inactive-top")
    assert 0 < inactive.pixelColor(2, p - 1).alpha() < next_to_window
    assert look.bottom_radius == min(20, int(8 * 3.4))


def test_the_title_bar_uses_the_header_color_and_the_frame_the_window_color(qt):
    t = theme(colors__header="#ff0000", colors__window="#0000ff", shadow__size=0, window__radius=0)
    svg = renderer(contents(t)["decoration.svg"])
    top = piece_image(svg, "decoration-top")
    assert top.pixelColor(2, 2).name() == "#ff0000"
    assert piece_image(svg, "decoration-bottom").pixelColor(0, 0).name() == "#0000ff"
    assert piece_image(svg, "decoration-inactive-top").pixelColor(2, 2).name() == "#0000ff"
    assert piece_image(svg, "decoration-maximized-center").pixelColor(2, 2).name() == "#ff0000"


def test_the_close_button_turns_red_on_hover(qt):
    t = theme(colors__negative="#ff0000")
    svg = renderer(contents(t)["close.svg"])
    cell = piece_image(svg, "hover-center")
    assert cell.pixelColor(2, 11).name() == "#ff0000" or cell.pixelColor(11, 2).name() == "#ff0000"
    assert piece_image(svg, "active-center").pixelColor(2, 11).alpha() == 0


# ---- pure: checks and notes -------------------------------------------------


def test_the_check_finds_broken_svg_files():
    generator = WindowFrameGenerator()
    folder = paths.data_home() / "aurorae" / "themes" / "x"
    good = next(f for f in generator.files(theme()) if f.path.name == "close.svg")
    assert generator.check_output(good) == []
    broken = PlannedFile(folder / "close.svg", wf.XML_MARKER + "\n<svg", wf.XML_MARKER)
    assert len(generator.check_output(broken)) == 1
    text = good.content.replace("</svg>", '<text id="t">x</text></svg>')
    assert any("text" in str(m) for m in generator.check_output(PlannedFile(folder / "close.svg", text)))
    missing = good.content.replace('id="hover-center"', 'id="other"')
    assert any(
        "hover-center" in str(m) for m in generator.check_output(PlannedFile(folder / "close.svg", missing))
    )
    assert generator.check_output(
        PlannedFile(folder / "xrc", "# Generated by Plasma Theme Studio.\n[General]\n")
    )


def test_unchanged_wants_nothing_and_says_the_values_only_show_in_the_preview(home):
    generator = WindowFrameGenerator()
    t = theme("unchanged")
    assert not generator.wanted(t)
    (note,) = generator.notes(t)
    assert "left as it is" in str(note)
    assert "preview" in str(note)
    assert generator.files(t) == []


def test_breeze_notes_say_what_breeze_cannot_do():
    generator = WindowFrameGenerator()
    notes = [str(n) for n in generator.notes(theme("breeze", shadow__size=40, window__border_width=3))]
    assert generator.wanted(theme("breeze"))
    assert any("corner radius" in n and "generated frame" in n for n in notes)
    assert any("large" in n and "48 px" in n for n in notes)
    assert any("Normal, 4 px" in n for n in notes)
    notes = [str(n) for n in generator.notes(theme("breeze", shadow__size=0, window__border_width=0))]
    assert "Breeze will draw no shadow." in notes
    assert "Breeze will draw no border." in notes
    assert not any("the step" in n and ("none" in n or "no border" in n) for n in notes)


def test_generated_notes_state_the_bottom_corner_limit():
    generator = WindowFrameGenerator()
    narrow = [str(n) for n in generator.notes(theme(window__radius=20, window__border_width=3))]
    assert any("bottom corners can only be rounded by 10 px" in n and "radius 20 px" in n for n in narrow)
    square = [str(n) for n in generator.notes(theme(window__radius=8, window__border_width=0))]
    assert any("bottom corners stay square" in n for n in square)
    fine = [str(n) for n in generator.notes(theme(window__radius=8, window__border_width=4))]
    assert any("All four corners" in n and "8 px" in n for n in fine)
    assert any("colors are fixed" in n for n in fine)
    assert any("border size is set to Tiny" in n and "4 px" in n for n in fine)


def test_the_reload_command_is_shown():
    assert WindowFrameGenerator().reload_command(theme()) == "qdbus6 org.kde.KWin /KWin reconfigure"


# ---- engine: Breeze ------------------------------------------------------------


def test_breeze_writes_its_own_keys_and_undo_removes_exactly_those(home, runner, kwin):
    t = theme("breeze", shadow__size=40, shadow__strength=0.5, window__border_width=3)
    result = engine.apply(t, runner)

    assert breeze_value("ShadowSize") == "ShadowLarge"
    assert breeze_value("ShadowStrength") == "140"
    assert kwin_value("BorderSizeAuto") == "false"
    assert kwin_value("BorderSize") == "Normal"
    # Breeze is the decoration already, so nothing is written about it.
    assert kwin_value("library") is None and kwin_value("theme") is None
    assert kwin.reconfigured == 1
    assert not (home / ".local/share/aurorae").exists()
    assert engine.is_current(engine.build_plan(t), runner)

    assert engine.restore(result.snapshot, runner, consume=True) == []
    for key in ("BorderSizeAuto", "BorderSize", "library", "theme"):
        assert kwin_value(key) is None
    assert breeze_value("ShadowSize") is None and breeze_value("ShadowStrength") is None
    assert kwin.reconfigured == 2


def test_breeze_puts_back_the_values_that_were_there_before(home, runner, kwin):
    config = home / ".config"
    config.mkdir(parents=True)
    (config / "kwinrc").write_text(
        "[org.kde.kdecoration2]\nBorderSize=Large\nBorderSizeAuto=true\n"
        "library=org.kde.kwin.aurorae.v2\ntheme=__aurorae__svg__MoeDark\n\n[Windows]\nFocusPolicy=1\n"
    )
    (config / "breezerc").write_text("[Common]\nShadowSize=ShadowSmall\nOutlineEnabled=false\n")

    t = theme("breeze", shadow__size=64, window__border_width=0)
    result = engine.apply(t, runner)

    assert kwin_value("library") == "org.kde.breeze" and kwin_value("theme") == "Breeze"
    assert kwin_value("BorderSize") == "None" and kwin_value("BorderSizeAuto") == "false"
    assert breeze_value("ShadowSize") == "ShadowVeryLarge"
    assert kconfig.user_value("breezerc", ["Common"], "OutlineEnabled") == "false"

    engine.restore(result.snapshot, runner, consume=True)
    assert kwin_value("library") == "org.kde.kwin.aurorae.v2"
    assert kwin_value("theme") == "__aurorae__svg__MoeDark"
    assert kwin_value("BorderSize") == "Large" and kwin_value("BorderSizeAuto") == "true"
    assert breeze_value("ShadowSize") == "ShadowSmall" and breeze_value("ShadowStrength") is None
    assert kconfig.user_value("kwinrc", ["Windows"], "FocusPolicy") == "1"
    assert (config / "breezerc").read_text().count("OutlineEnabled=false") == 1


def test_breeze_in_the_system_defaults_counts_as_in_use(home, runner, kwin):
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "library")] = "org.kde.breeze"
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "theme")] = "Breeze"
    engine.apply(theme("breeze"), runner)
    assert kwin_value("library") is None


def test_a_breeze_apply_removes_the_generated_folders_and_undo_brings_them_back(home, runner, kwin):
    engine.apply(theme(), runner)
    (old,) = folders()
    second = engine.apply(theme("breeze"), runner)
    assert folders() == []
    assert kwin_value("library") == "org.kde.breeze"

    engine.restore(second.snapshot, runner, consume=True)
    assert folders() == [old]
    assert kwin_value("library") == wf.AURORAE_LIBRARY


def test_the_decoration_in_use_is_named_in_a_warning(home, runner, kwin):
    generator = WindowFrameGenerator()
    assert generator.warnings(theme(), runner) == []
    kconfig.write_value(runner, "kwinrc", ["org.kde.kdecoration2"], "library", wf.AURORAE_LIBRARY)
    kconfig.write_value(runner, "kwinrc", ["org.kde.kdecoration2"], "theme", "__aurorae__svg__MoeDark")
    (warning,) = generator.warnings(theme(), runner)
    assert "MoeDark" in str(warning)
    kconfig.write_value(
        runner, "kwinrc", ["org.kde.kdecoration2"], "theme", "__aurorae__svg__PlasmaThemeStudio-A-1"
    )
    assert generator.warnings(theme(), runner) == []
    kconfig.write_value(runner, "kwinrc", ["org.kde.kdecoration2"], "library", "org.kde.oxygen")
    (warning,) = generator.warnings(theme(), runner)
    assert "org.kde.oxygen" in str(warning)


# ---- engine: generated --------------------------------------------------------------


def test_generated_writes_the_files_and_the_keys_and_undo_removes_them(home, runner, kwin):
    t = theme(window__border_width=3, window__radius=8)
    result = engine.apply(t, runner)
    folder = wf.frame_folder(t)

    root = home / ".local/share/aurorae/themes" / folder
    assert sorted(p.name for p in root.iterdir()) == sorted(
        ["metadata.desktop", f"{folder}rc", "decoration.svg", *(f"{n}.svg" for n in wf.BUTTON_FILES)]
    )
    assert all(made_here(p) for p in root.iterdir())
    assert kwin_value("library") == "org.kde.kwin.aurorae.v2"
    assert kwin_value("theme") == f"__aurorae__svg__{folder}"
    assert kwin_value("BorderSizeAuto") == "false" and kwin_value("BorderSize") == "Tiny"
    assert breeze_value("ShadowSize") is None  # Breeze's own settings stay alone
    assert kwin.reconfigured == 1
    assert engine.is_current(engine.build_plan(t), runner)

    engine.restore(result.snapshot, runner, consume=True)
    assert folders() == []
    assert not (home / ".local/share/aurorae/themes").exists() or not list(
        (home / ".local/share/aurorae/themes").iterdir()
    )
    for key in ("library", "theme", "BorderSize", "BorderSizeAuto"):
        assert kwin_value(key) is None
    assert not engine.is_current(engine.build_plan(t), runner)


def test_a_new_look_replaces_the_old_folder_and_undo_brings_it_back(home, runner, kwin):
    first = theme(window__radius=5)
    second = theme(window__radius=12)
    engine.apply(first, runner)
    plan = engine.build_plan(second, runner)
    (target,) = plan.targets
    old = home / ".local/share/aurorae/themes" / wf.frame_folder(first)
    assert target.stale[-1] == old and old / "decoration.svg" in target.stale
    assert not engine.is_current(plan, runner)

    result = engine.apply(second, runner)
    assert folders() == [wf.frame_folder(second)]
    assert kwin_value("theme") == f"__aurorae__svg__{wf.frame_folder(second)}"

    engine.restore(result.snapshot, runner, consume=True)
    assert folders() == [wf.frame_folder(first)]
    assert "decoration-topleft" in (old / "decoration.svg").read_text()
    assert kwin_value("theme") == f"__aurorae__svg__{wf.frame_folder(first)}"
    assert engine.is_current(engine.build_plan(first), runner)


def test_a_failed_reconfigure_rolls_everything_back(home, runner, kwin):
    first = theme(window__radius=5)
    engine.apply(first, runner)
    kwin.fail = True

    with pytest.raises(ApplyError) as error:
        engine.apply(theme(window__radius=12, window__border_width=6), runner)

    assert "reload" in str(error.value.message)
    assert folders() == [wf.frame_folder(first)]
    assert kwin_value("theme") == f"__aurorae__svg__{wf.frame_folder(first)}"
    assert kwin_value("BorderSize") == "Tiny"


def test_a_failed_reconfigure_on_a_fresh_desktop_leaves_no_keys(home, runner, kwin):
    kwin.fail = True
    with pytest.raises(ApplyError):
        engine.apply(theme(), runner)
    assert folders() == []
    for key in ("library", "theme", "BorderSize", "BorderSizeAuto"):
        assert kwin_value(key) is None


def test_a_frame_that_kwin_does_not_take_over_is_rolled_back(home, runner, kwin, no_pause):
    kwin.report = "Decoration\n==========\nPlugin: org.kde.breeze\nTheme: Breeze\n\nOutput backend\n"
    with pytest.raises(ApplyError) as error:
        engine.apply(theme(), runner)
    assert "Breeze" in str(error.value.message)
    assert folders() == []
    assert kwin_value("library") is None


def test_a_frame_that_kwin_reports_is_accepted(home, runner, kwin, no_pause):
    t = theme()
    folder = wf.frame_folder(t)
    kwin.report = (
        f"Decoration\n==========\nPlugin: org.kde.kwin.aurorae.v2\nTheme: __aurorae__svg__{folder}\n\nX\n"
    )
    engine.apply(t, runner)
    assert folders() == [folder]


def test_a_folder_made_by_someone_else_is_never_removed(home, runner, kwin):
    root = home / ".local/share/aurorae/themes"
    other = root / "PlasmaThemeStudio-Foreign-12345678"
    other.mkdir(parents=True)
    (other / "metadata.desktop").write_text("[Desktop Entry]\nName=Mine\n")
    (other / "decoration.svg").write_text("<svg/>\n")
    named_like_ours = root / "MoeDark"
    named_like_ours.mkdir()
    (named_like_ours / "decoration.svg").write_text(wf.XML_MARKER + "\n<svg/>\n")

    engine.apply(theme(), runner)
    engine.apply(theme("breeze"), runner)

    assert (other / "decoration.svg").read_text() == "<svg/>\n"
    assert (named_like_ours / "decoration.svg").exists()
    assert folders() == ["MoeDark", "PlasmaThemeStudio-Foreign-12345678"]


def test_only_files_made_here_are_removed_from_an_old_folder(home, runner, kwin):
    engine.apply(theme(window__radius=5), runner)
    (old,) = (home / ".local/share/aurorae/themes").iterdir()
    (old / "notes.txt").write_text("mine\n")

    engine.apply(theme(window__radius=12), runner)

    assert (old / "notes.txt").read_text() == "mine\n"
    assert not (old / "decoration.svg").exists()


def test_a_theme_that_leaves_the_frame_alone_changes_nothing_when_it_is_not_ours(home, runner, kwin):
    engine.apply(theme("breeze"), runner)
    reconfigured = kwin.reconfigured
    snapshot_keys = {name: kwin_value(name) for name in ("library", "theme", "BorderSize")}

    result = engine.apply(theme("unchanged", window__radius=3), runner)

    assert "window" not in result.snapshot.settings
    assert kwin.reconfigured == reconfigured
    assert {name: kwin_value(name) for name in ("library", "theme", "BorderSize")} == snapshot_keys
    assert folders() == []


def test_the_busctl_fallback_asks_kwin_to_reconfigure(home, runner, use_generators):
    use_generators(WindowFrameGenerator())
    runner.missing.add("qdbus6")
    calls = []
    runner.handlers["busctl"] = lambda argv: calls.append(argv) or Result(0)

    engine.apply(theme("breeze"), runner)

    assert calls == [["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"]]


@pytest.mark.parametrize(
    ("missing", "blocked"),
    [
        ({"kwriteconfig6"}, True),
        ({"kreadconfig6"}, True),
        ({"qdbus6", "busctl"}, True),
        ({"qdbus6"}, False),
        ({"busctl"}, False),
    ],
)
def test_missing_tools_block_the_apply(home, runner, kwin, missing, blocked):
    runner.missing |= missing
    runner.handlers["busctl"] = lambda argv: Result(0)
    assert (WindowFrameGenerator().unavailable_reason(runner) is not None) == blocked
    if blocked:
        with pytest.raises(engine.ApplyBlocked) as error:
            engine.apply(theme(), runner)
        assert error.value.problems
        assert folders() == []
        assert kwin.reconfigured == 0


def test_the_snapshot_records_every_key_the_target_can_touch(home, runner, kwin):
    assert set(WindowFrameGenerator().capture_settings(runner)) == {
        "library",
        "theme",
        "border_size_auto",
        "border_size",
        "shadow_size",
        "shadow_strength",
        "masked",
    }


# ---- undo above the defaults of a global theme ----------------------------------------


@pytest.fixture
def global_theme(runner):
    """A global theme that names its own window frame in Plasma's layer of defaults."""
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "library")] = "org.kde.kwin.aurorae"
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "theme")] = "__aurorae__svg__Nordic"
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "BorderSize")] = "Normal"


@pytest.mark.parametrize("mode", ["generated", "breeze"])
def test_undo_leaves_the_frame_of_a_global_theme_in_use(home, runner, kwin, global_theme, mode):
    before = "[Windows]\nFocusPolicy=ClickToFocus\n"
    (home / ".config").mkdir(parents=True)
    (home / ".config/kwinrc").write_text(before)

    result = engine.apply(theme(mode, window__border_width=3), runner)
    assert kwin_value("library") in (wf.AURORAE_LIBRARY, wf.BREEZE_LIBRARY)
    assert result.snapshot.settings["window"]["masked"] == []

    assert engine.restore(result.snapshot, runner, consume=True) == []

    # No "key[$d]" line is left that would hide the global theme's frame.
    assert (home / ".config/kwinrc").read_text() == before
    assert not (home / ".config/breezerc").exists()
    assert kconfig.effective_value(runner, *KWIN, "library") == "org.kde.kwin.aurorae"
    assert kconfig.effective_value(runner, *KWIN, "theme") == "__aurorae__svg__Nordic"
    assert kconfig.effective_value(runner, *KWIN, "BorderSize") == "Normal"


def test_undo_keeps_the_defaults_the_user_had_hidden(home, runner, kwin, global_theme):
    before = "[org.kde.kdecoration2]\nlibrary[$d]\ntheme[$d]\n"
    (home / ".config").mkdir(parents=True)
    (home / ".config/kwinrc").write_text(before)

    result = engine.apply(theme(), runner)
    assert result.snapshot.settings["window"]["masked"] == ["library", "theme"]
    assert kwin_value("library") == wf.AURORAE_LIBRARY

    assert engine.restore(result.snapshot, runner, consume=True) == []

    assert (home / ".config/kwinrc").read_text() == before


def test_a_rolled_back_apply_leaves_the_global_themes_frame_too(home, runner, kwin, global_theme):
    kwin.fail = True
    with pytest.raises(ApplyError):
        engine.apply(theme(window__border_width=3), runner)
    assert not (home / ".config/kwinrc").exists()
    assert folders() == []


def test_a_snapshot_from_before_hidden_defaults_were_recorded_still_restores(home, runner, kwin):
    engine.apply(theme(), runner)
    old = {name: None for name in wf.SETTINGS}  # no "masked" entry
    WindowFrameGenerator().restore_settings(old, runner)
    assert kwin_value("library") is None and kwin_value("theme") is None


def test_the_plan_says_which_settings_change(home, runner, kwin):
    (generated,) = engine.build_plan(theme(), runner).targets
    assert [str(text) for text in generated.settings] == [
        "which window frame KWin uses and its border size (kwinrc)"
    ]
    (breeze,) = engine.build_plan(theme("breeze"), runner).targets
    assert "breezerc" in str(breeze.settings[0]) and "kwinrc" in str(breeze.settings[0])
    (unchanged,) = engine.build_plan(theme("unchanged"), runner).targets
    assert unchanged.settings == []


def test_the_shadow_fades_out_softly():
    """The halo is darkest at the window and thins out faster than a straight line."""
    fade = wf._Pieces()._fade(0.8)
    assert fade[0] == 0.8 and fade[-1] == 0
    assert all(near > far for near, far in zip(fade, fade[1:], strict=False))
    assert fade[len(fade) // 2] == pytest.approx(0.2)  # a quarter at the middle, not a half

    files = WindowFrameGenerator().files(theme(shadow__size=40, shadow__strength=0.8))
    svg = next(file.content for file in files if file.path.name == "decoration.svg")
    assert 'stop-opacity="0.000"' in svg


RUNNING = "Decoration\n==========\nPlugin: org.kde.kwin.aurorae.v2\nTheme: x\n\nOutput backend\n"


def test_undo_without_a_kwin_to_ask_is_done_when_the_settings_are_back(home, runner, kwin):
    """A KWin that is not there has nothing to reload: it reads its file when it starts."""
    result = engine.apply(theme(), runner)
    kwin.fail = True

    assert engine.restore(result.snapshot, runner, consume=True) == []

    assert kwin_value("library") is None and kwin_value("theme") is None
    assert folders() == []


def test_undo_says_so_when_a_running_kwin_does_not_reload(home, runner, kwin):
    result = engine.apply(theme(), runner)
    kwin.fail, kwin.report = True, RUNNING

    (failure,) = engine.restore(result.snapshot, runner, consume=True)

    assert "could not be asked to reload" in str(failure)
    assert kwin_value("library") is None  # the settings are back all the same
    (kept,) = engine.snapshots.list_snapshots()
    assert kept.id == result.snapshot.id


def test_a_kwin_that_answers_without_saying_its_frame_is_still_a_running_kwin(home, runner, kwin):
    result = engine.apply(theme(), runner)
    kwin.fail, kwin.report = True, "KWin Support Information:\n"

    (failure,) = engine.restore(result.snapshot, runner, consume=True)

    assert "could not be asked to reload" in str(failure)


class Busctl:
    """Stands in for busctl on a system without qdbus6."""

    def __init__(self, runner, running=True, reloads=True):
        self.running, self.reloads = running, reloads
        self.calls = []
        runner.missing.add("qdbus6")
        runner.handlers["busctl"] = self

    def __call__(self, argv):
        self.calls.append(argv[-1])
        if not self.running:
            return Result(1, "", "Call failed: The name org.kde.KWin was not provided by any .service files")
        if argv[-1] == "Ping":
            return Result(0)
        return Result(0) if self.reloads else Result(1, "", "Call failed: Connection timed out")


def test_without_qdbus6_a_running_kwin_that_does_not_reload_is_still_a_failure(home, runner, kwin):
    busctl = Busctl(runner)
    result = engine.apply(theme(), runner)
    assert busctl.calls == ["reconfigure"]
    busctl.reloads = False

    (failure,) = engine.restore(result.snapshot, runner, consume=True)

    assert "could not be asked to reload" in str(failure) and "timed out" in str(failure)
    assert busctl.calls[-2:] == ["reconfigure", "Ping"]
    assert kwin_value("library") is None  # the settings are back all the same
    assert [s.id for s in engine.snapshots.list_snapshots()] == [result.snapshot.id]


def test_without_qdbus6_an_undo_without_kwin_is_done(home, runner, kwin):
    busctl = Busctl(runner)
    result = engine.apply(theme(), runner)
    busctl.running = False

    assert engine.restore(result.snapshot, runner, consume=True) == []
    assert engine.snapshots.list_snapshots() == []


def test_with_no_tool_to_ask_kwin_the_failed_reload_is_reported(home, runner, kwin):
    result = engine.apply(theme(), runner)
    runner.missing.update({"qdbus6", "busctl"})

    (failure,) = engine.restore(result.snapshot, runner, consume=True)

    assert "could not be asked to reload" in str(failure)


def test_each_page_gets_the_notes_that_concern_it(home):
    generator = WindowFrameGenerator()

    unchanged = Theme()
    assert [str(n) for n in generator.section_notes(unchanged, "window")] == [
        str(n) for n in generator.notes(unchanged)
    ]
    (shadow,) = generator.section_notes(unchanged, "shadow")
    assert "choose a window frame on the Windows page" in str(shadow)

    breeze = theme("breeze", shadow__size=40, window__border_width=3)
    window = [str(n) for n in generator.section_notes(breeze, "window")]
    shadow = [str(n) for n in generator.section_notes(breeze, "shadow")]
    assert window + shadow == [str(n) for n in generator.notes(breeze)]
    assert len(shadow) == 1 and "48 px" in shadow[0]
    assert len(window) == 2 and not any("shadow" in n for n in window)
    assert [str(n) for n in generator.section_notes(theme("breeze", shadow__size=0), "shadow")] == [
        "Breeze will draw no shadow."
    ]

    made = theme(window__radius=20, window__border_width=3)
    assert [str(n) for n in generator.section_notes(made, "window")] == [
        str(n) for n in generator.notes(made)
    ]
    assert [str(n) for n in generator.section_notes(made, "shadow")] == [
        "The generated window frame draws this shadow, the same on all sides."
    ]


# ---- the shape of the frame in use -----------------------------------------------------


def apply_generated(runner, **values):
    engine.apply(theme("generated", **values), runner)


def strip_shape_group(folder_name):
    """Imitate a folder written before the rc had a group for the shape."""
    rc = paths.data_home() / "aurorae" / "themes" / folder_name / f"{folder_name}rc"
    text = rc.read_text()
    assert f"[{wf.SHAPE_GROUP}]" in text
    rc.write_text(text.split(f"[{wf.SHAPE_GROUP}]")[0])


def test_the_shape_is_written_into_a_group_of_its_own_and_the_rc_still_parses(kwin):
    sample = theme(window__radius=9, window__border_width=3, shadow__size=20, shadow__strength=0.5)
    rc = next(f for f in WindowFrameGenerator().files(sample) if f.path.name.endswith("rc"))

    assert "[PlasmaThemeStudio]\nRadius=9\nBorder=3\nShadowSize=20\nShadowStrength=0.5\n" in rc.content
    assert WindowFrameGenerator().check_output(rc) == []


SHAPES = [
    (r, b, s, k)
    for r, b in ((0, 0), (5, 1), (14, 2), (24, 12), (3, 12), (24, 0))
    for s, k in ((0, 0.35), (8, 0.0), (24, 0.35), (64, 1.0), (32, 0.123))
]


@pytest.mark.parametrize("stripped", [False, True])
@pytest.mark.parametrize(("radius", "border", "shadow", "strength"), SHAPES)
def test_the_shape_of_the_frame_in_use_is_read_back(kwin, runner, radius, border, shadow, strength, stripped):
    values = {
        "window__radius": radius,
        "window__border_width": border,
        "shadow__size": shadow,
        "shadow__strength": strength,
    }
    apply_generated(runner, **values)
    if stripped:
        strip_shape_group(folders()[0])
    found = wf.frame_in_use_shape()
    assert found is not None
    assert found[:3] == (radius, border, shadow)
    # Without the group, the strength comes from the gradient (3 decimals), or is the default without one.
    expected = strength if shadow else (strength if not stripped else 0.35)
    assert found[3] == pytest.approx(expected, abs=1e-9)


def test_no_frame_of_ours_in_use_gives_no_shape(kwin, runner):
    assert wf.frame_in_use_shape() is None
    kconfig.write_value(runner, *KWIN, "library", wf.BREEZE_LIBRARY)
    kconfig.write_value(runner, *KWIN, "theme", "Breeze")
    assert wf.frame_in_use_shape() is None
    kconfig.write_value(runner, *KWIN, "library", wf.AURORAE_LIBRARY)
    kconfig.write_value(runner, *KWIN, "theme", wf.AURORAE_THEME_PREFIX + "MoeDark")
    assert wf.frame_in_use_shape() is None


@pytest.mark.parametrize("stripped", [False, True])
@pytest.mark.parametrize("damage", ["foreign", "missing", "bad_rc", "bad_svg", "range", "path"])
def test_an_unreadable_or_out_of_range_frame_is_not_ours(kwin, runner, damage, stripped):
    apply_generated(runner, window__radius=8, window__border_width=2)
    name = folders()[0]
    if stripped:
        strip_shape_group(name)
    folder = paths.data_home() / "aurorae" / "themes" / name
    rc = folder / f"{name}rc"
    if damage == "foreign":
        (folder / "metadata.desktop").write_text("[Desktop Entry]\nName=x\n")
    elif damage == "missing":
        rc.unlink()
        (folder / "decoration.svg").unlink()
    elif damage == "bad_rc":
        rc.write_text("[Layout\nBorderLeft=2\n")
    elif damage == "bad_svg":
        (folder / "decoration.svg").write_text("<svg")
        if not stripped:
            rc.write_text(rc.read_text().replace("Radius=8", "Radius=x"))
    elif damage == "range":
        text = rc.read_text()
        rc.write_text(text.replace("BorderLeft=2", "BorderLeft=99").replace("Border=2", "Border=99"))
    else:
        kconfig.write_value(runner, *KWIN, "theme", wf.AURORAE_THEME_PREFIX + "../" + name)
    assert wf.frame_in_use_shape() is None
    assert not WindowFrameGenerator().wanted(theme("unchanged"))


def test_a_colors_only_theme_plans_the_frame_in_use_in_its_own_colors(kwin, runner):
    apply_generated(runner, window__radius=10, window__border_width=3, shadow__size=16)
    old = folders()[0]
    plain = theme("unchanged", meta__name="Plain", colors__header="#123456")
    generator = WindowFrameGenerator()

    assert generator.wanted(plain)
    files = generator.files(plain)
    new = wf.frame_folder(plain)
    assert new != old and {f.path.parent.name for f in files} == {new}
    assert "#123456" in next(f for f in files if f.path.name == "decoration.svg").content
    assert [p.name for p in generator.stale_files(plain) if p.name == old] == [old]
    assert "keeps its shape" in str(generator.notes(plain)[0])
    assert not generator.is_active(plain, runner)

    engine.apply(plain, runner)

    assert folders() == [new]
    assert generator.is_active(plain, runner)
    assert kwin_value("BorderSize") == wf.aurorae_border_size(3)


@pytest.mark.parametrize("key", ["Radius", "Border", "ShadowSize", "ShadowStrength"])
def test_a_shape_group_with_a_missing_key_is_not_ours(kwin, runner, key):
    apply_generated(runner, window__radius=8, window__border_width=2)
    name = folders()[0]
    rc = paths.data_home() / "aurorae" / "themes" / name / f"{name}rc"
    lines = [line for line in rc.read_text().splitlines() if not line.startswith(key + "=")]
    rc.write_text("\n".join(lines) + "\n")
    assert wf.frame_in_use_shape() is None


# ---- the title bar, the buttons and the shadow's direction


def rc_parsed(look):
    import configparser

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_string(wf._rc(look))
    return parser


def test_the_defaults_are_the_frame_they_always_were():
    look = wf.Look.of(theme(window__radius=8, window__border_width=2, shadow__size=16))
    assert (look.title_total, look.button_size, look.button_spacing) == (wf.TITLE_TOTAL, wf.BUTTON_SIZE, 4)
    assert (look.shadow_x, look.shadow_y) == (0, 0)
    assert look.shadow_left == look.shadow_right == look.shadow_top == look.shadow_bottom == 16
    assert "ShadowX" not in wf._rc(look) and "TitleBar" not in wf._rc(look)


def test_the_title_bar_height_button_size_and_spacing_reach_the_rc_file():
    look = wf.Look.of(
        theme(window__title_height=44, window__button_size=30, window__button_spacing=9, shadow__size=10)
    )
    rc = rc_parsed(look)
    row = 44 - 2 * wf.TITLE_EDGE
    assert rc["Layout"]["TitleHeight"] == str(row)
    assert rc["Layout"]["ButtonWidth"] == rc["Layout"]["ButtonHeight"] == "30"
    assert rc["Layout"]["ButtonSpacing"] == "9"
    assert rc["Layout"]["ButtonMarginTop"] == str((row - 30) // 2)
    assert rc[wf.SHAPE_GROUP]["TitleBar"] == "44"


def test_a_button_cannot_be_taller_than_the_title_row():
    look = wf.Look.of(theme(window__title_height=20, window__button_size=40))
    assert look.button == look.title_row


def test_the_shadow_offset_moves_the_reach_to_one_side():
    look = wf.Look.of(theme(shadow__size=20, shadow__offset_x=8, shadow__offset_y=-12))
    assert (look.shadow_left, look.shadow_right) == (12, 28)
    assert (look.shadow_top, look.shadow_bottom) == (32, 8)
    rc = rc_parsed(look)
    assert rc["Layout"]["PaddingLeft"] == "12" and rc["Layout"]["PaddingRight"] == "28"
    assert rc[wf.SHAPE_GROUP]["ShadowX"] == "8" and rc[wf.SHAPE_GROUP]["ShadowY"] == "-12"


def test_an_offset_larger_than_the_shadow_leaves_none_on_that_side():
    look = wf.Look.of(theme(shadow__size=6, shadow__offset_y=30))
    assert look.shadow_top == 0 and look.shadow_bottom == 36


def test_every_file_of_a_changed_frame_passes_the_checks(runner):
    values = {
        "window__radius": 12,
        "window__border_width": 3,
        "window__title_height": 40,
        "window__button_size": 28,
        "window__button_spacing": 8,
        "shadow__size": 24,
        "shadow__offset_x": 10,
        "shadow__offset_y": 16,
    }
    generator = WindowFrameGenerator()
    planned = generator.files(theme(**values))
    assert planned
    for file in planned:
        assert generator.check_output(file) == [], file.path.name


def test_a_frame_of_ours_in_use_keeps_its_title_bar_and_shadow_when_the_theme_leaves_the_frame(kwin, runner):
    apply_generated(
        runner,
        window__title_height=40,
        window__button_size=26,
        shadow__size=16,
        shadow__offset_x=4,
        shadow__offset_y=9,
    )
    extras = wf.frame_in_use_extras()
    assert extras == {"title_total": 40, "button_size": 26, "shadow_x": 4, "shadow_y": 9}
    kept = wf.frame_to_generate(theme("unchanged", window__radius=7))
    assert kept is not None
    look, _folder = kept
    assert (look.title_total, look.button_size, look.shadow_y) == (40, 26, 9)


def test_no_frame_of_ours_in_use_gives_no_extras(kwin, runner):
    assert wf.frame_in_use_extras() == {}


def test_the_folder_changes_with_the_new_values():
    plain = wf.frame_to_generate(theme())[1]
    assert wf.frame_to_generate(theme(window__title_height=44))[1] != plain
    assert wf.frame_to_generate(theme(shadow__offset_y=6))[1] != plain
