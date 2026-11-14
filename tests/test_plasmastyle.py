# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import re

import pytest

from plasma_theme_studio import kconfig, paths
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.generators import JSON_MARKER, MARKER, XML_MARKER, ApplyError, made_here
from plasma_theme_studio.generators.plasmastyle import (
    ID_PREFIX,
    POPUP_FILES,
    POPUP_REQUIRED_IDS,
    REQUIRED_IDS,
    PlasmaStyleGenerator,
    panel_svg,
    style_id,
)
from plasma_theme_studio.model.theme import Theme

GENERATOR = PlasmaStyleGenerator()


def look(radius=12, border=2, opacity=0.85, style="generated", name="My Theme"):
    return Theme(
        {
            ("meta", "name"): name,
            ("panel", "style"): style,
            ("panel", "radius"): radius,
            ("panel", "border_width"): border,
            ("panel", "opacity"): opacity,
        }
    )


def package_files(theme):
    root = packages_dir() / style_id(theme)
    return {file.path.relative_to(root).as_posix(): file for file in GENERATOR.files(theme)}


def packages_dir():
    return paths.data_home() / "plasma/desktoptheme"


def installed():
    root = packages_dir()
    return sorted(p.name for p in root.iterdir()) if root.is_dir() else []


def fake_style_tool(runner):
    """Make the runner's plasma-apply-desktoptheme behave like the real tool."""
    runner.calls_to_tool = []
    # Plasma's own defaults (kdedefaults) name the style, so removing the user's key leaves a
    # "[$d]" line behind, as kwriteconfig6 does on a real desktop.
    runner.defaults[("plasmarc", ("Theme",), "name")] = "default"

    def tool(argv):
        runner.calls_to_tool.append(argv)
        name = argv[1]
        current = kconfig.user_value("plasmarc", ["Theme"], "name") or "default"
        if name != "default" and not (packages_dir() / name / "metadata.json").exists():
            return Result(255, "", f'Could not find theme "{name}"\n')
        if name == current:
            return Result(0, "already set\n")
        # The real tool writes "default" as a value; it does not remove the key.
        kconfig.write_value(runner, "plasmarc", ["Theme"], "name", name)
        return Result(0, "Successfully applied\n")

    runner.handlers["plasma-apply-desktoptheme"] = tool
    return runner


@pytest.fixture
def style(home, runner, use_generators):
    """A runner whose plasma-apply-desktoptheme behaves like the real tool."""
    use_generators(GENERATOR)
    return fake_style_tool(runner)


# content


def test_the_package_has_the_files_plasma_needs():
    files = package_files(look())
    assert sorted(files) == [
        "dialogs/background.svg",
        "metadata.json",
        "plasmarc",
        "solid/dialogs/background.svg",
        "solid/widgets/background.svg",
        "solid/widgets/panel-background.svg",
        "solid/widgets/tooltip.svg",
        "widgets/background.svg",
        "widgets/panel-background.svg",
        "widgets/tooltip.svg",
    ]
    assert files["metadata.json"].content.startswith(JSON_MARKER)
    assert files["plasmarc"].content.startswith(MARKER)
    assert "[AdaptiveTransparency]\nenabled=true" in files["plasmarc"].content
    for name in ("widgets/panel-background.svg", "solid/widgets/panel-background.svg"):
        assert files[name].content.startswith(XML_MARKER + "\n<svg")
        assert "<?xml" not in files[name].content
        assert files[name].marker == XML_MARKER


def test_the_metadata_names_the_package_and_the_theme():
    theme = look(name="My Theme")
    data = json.loads(package_files(theme)["metadata.json"].content)
    assert data["KPlugin"]["Id"] == style_id(theme)
    assert data["KPlugin"]["Name"] == "My Theme"
    assert data["KPackageStructure"] == "Plasma/Theme"
    assert style_id(theme).startswith("PlasmaThemeStudio-MyTheme-")
    assert GENERATOR.files(theme)[0].path.parent.name == style_id(theme)


def test_every_generated_file_passes_the_check():
    for radius, border in ((0, 0), (12, 2), (24, 4), (3, 4)):
        for file in GENERATOR.files(look(radius, border)):
            assert GENERATOR.check_output(file) == []


def test_the_check_rejects_missing_ids_text_and_transforms():
    svg = next(f for f in GENERATOR.files(look()) if f.path.suffix == ".svg")
    bad = [
        svg.content.replace('id="mask-top"', 'id="x"'),
        svg.content.replace("</svg>", "<text>x</text></svg>"),
        svg.content.replace("<defs>", '<g transform="scale(2)"/><defs>'),
        svg.content.replace("</svg>", ""),
    ]
    for content in bad:
        assert GENERATOR.check_output(type(svg)(svg.path, content, svg.marker))
    meta = GENERATOR.files(look())[0]
    assert GENERATOR.check_output(type(meta)(meta.path.parent.parent / "other/metadata.json", meta.content))


def test_the_svg_has_only_absolute_shapes_and_no_text():
    for solid in (False, True):
        svg = panel_svg(12, 2, 0.85, solid=solid)
        assert "<text" not in svg and "transform" not in svg.lower()
        ids = set(re.findall(r' id="([^"]+)"', svg))
        assert REQUIRED_IDS <= ids


def test_margins_follow_radius_and_border():
    def margin(svg, name):
        match = re.search(rf'id="{name}" x="[^"]+" y="[^"]+" width="([^"]+)" height="([^"]+)"', svg)
        return max(float(match.group(1)), float(match.group(2)))

    round_ = panel_svg(20, 1, 0.9, solid=False)
    flat = panel_svg(0, 5, 0.9, solid=False)
    assert margin(round_, "hint-top-margin") == 6
    assert margin(flat, "hint-top-margin") == 5
    assert margin(panel_svg(0, 0, 0.9, solid=False), "hint-left-margin") == 1
    assert margin(round_, "thick-hint-top-margin") > margin(round_, "hint-top-margin")


def test_opacity_is_only_in_the_translucent_artwork():
    files = package_files(look(opacity=0.6))
    translucent = files["widgets/panel-background.svg"].content
    solid = files["solid/widgets/panel-background.svg"].content
    assert 'fill-opacity="0.6"' in translucent
    assert 'fill-opacity="0.6"' not in solid
    assert 'class="ColorScheme-Background" fill="currentColor" fill-opacity="1"' in solid


def test_the_colors_come_from_the_color_scheme():
    svg = package_files(look())["widgets/panel-background.svg"].content
    assert 'id="current-color-scheme"' in svg
    assert 'class="ColorScheme-Background" fill="currentColor"' in svg
    assert 'class="ColorScheme-Text" fill="currentColor"' in svg
    assert "ColorScheme-Text" not in panel_svg(12, 0, 0.8, solid=False).split("</style>", 1)[1]


def test_the_id_changes_with_the_look_only():
    base = style_id(look())
    assert style_id(look()) == base
    assert style_id(look(name="Other")) != base
    assert style_id(look(radius=13)) != base
    assert style_id(look(border=3)) != base
    assert style_id(look(opacity=0.5)) != base
    same_look = look()
    same_look.set("window", "radius", 3)  # not a panel value
    assert style_id(same_look) == base
    assert re.fullmatch(rf"{ID_PREFIX}MyTheme-[0-9a-f]{{8}}", base)


def test_the_panel_follows_the_shared_radius_until_it_has_its_own():
    theme = Theme({("meta", "name"): "T", ("panel", "style"): "generated", ("shape", "radius"): 9})
    assert style_id(theme) == style_id(
        Theme({("meta", "name"): "T", ("panel", "style"): "generated", ("panel", "radius"): 9})
    )


def test_unchanged_is_not_wanted_and_says_so():
    theme = look(style="unchanged")
    assert not GENERATOR.wanted(theme)
    assert "keeps the Plasma style" in str(GENERATOR.notes(theme)[0])
    assert GENERATOR.wanted(look())
    notes = " ".join(str(n) for n in GENERATOR.notes(look()))
    assert "panel" in notes and "popups" in notes and "translucent" in notes
    assert len(GENERATOR.notes(look(radius=24))) == 2
    assert len(GENERATOR.notes(look(radius=23, border=1))) == 2
    assert len(GENERATOR.notes(look(radius=12))) == 1


def test_the_artwork_renders_with_the_intended_shapes(app):
    pytest.importorskip("PySide6.QtSvg")
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    svg = panel_svg(12, 2, 0.85, solid=False)
    renderer = QSvgRenderer(svg.encode())
    assert renderer.isValid()
    assert all(renderer.elementExists(name) for name in REQUIRED_IDS)
    assert renderer.boundsOnElement("topleft").getRect() == (0, 0, 12, 12)
    assert renderer.boundsOnElement("mask-bottomright").size().width() == 12
    assert renderer.boundsOnElement("hint-top-margin").height() == 4
    assert renderer.boundsOnElement("shadow-hint-left-margin").width() == 10

    def pixel(source, name, x, y):
        image = QImage(48, 48, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        QSvgRenderer(source.encode()).render(painter, name, QRectF(0, 0, 48, 48))
        painter.end()
        return image.pixelColor(x, y).alpha()

    assert pixel(svg, "topleft", 0, 0) == 0  # the rounded corner is cut away
    assert 200 < pixel(svg, "center", 24, 24) < 230  # 0.85 of 255
    assert pixel(panel_svg(12, 2, 0.85, solid=True), "center", 24, 24) == 255
    assert pixel(svg, "mask-center", 24, 24) == 255


def test_the_shadow_stays_out_from_under_the_panel(app):
    pytest.importorskip("PySide6.QtSvg")
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(panel_svg(0, 0, 0.5, solid=False).encode())

    def alphas(name, along_x):
        # 16 pixels per tile: the shadow reaches 10 of them out, the other 6 are under the panel
        image = QImage(16, 16, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        renderer.render(painter, name, QRectF(0, 0, 16, 16))
        painter.end()
        return [
            image.pixelColor(i, 8).alpha() if along_x else image.pixelColor(8, i).alpha() for i in range(16)
        ]

    # The panel may be translucent, so no darkness may show through it.
    top, left = alphas("shadow-top", False), alphas("shadow-left", True)
    bottom, right = alphas("shadow-bottom", False), alphas("shadow-right", True)
    for outside_first, edges in ((True, (top, left)), (False, (bottom, right))):
        for edge in edges:
            outer, under = (edge[:10], edge[10:]) if outside_first else (edge[6:][::-1], edge[:6])
            assert max(under) == 0
            assert outer[0] < 5 and max(outer) > 30  # fades out, darkest next to the panel
            assert outer == sorted(outer, key=lambda value: value)

    corner = QImage(16, 16, QImage.Format_ARGB32)
    corner.fill(0)
    painter = QPainter(corner)
    renderer.render(painter, "shadow-bottomright", QRectF(0, 0, 16, 16))
    painter.end()
    assert corner.pixelColor(2, 2).alpha() == 0  # the square under the panel's corner
    assert corner.pixelColor(7, 7).alpha() > 0


# engine


def test_apply_writes_the_package_and_switches_the_style(style):
    theme = look()
    result = engine.apply(theme, style)

    assert installed() == [style_id(theme)]
    assert kconfig.user_value("plasmarc", ["Theme"], "name") == style_id(theme)
    assert engine.is_current(engine.build_plan(theme), style)
    assert result.snapshot.settings["panel"]["style"] is None
    assert GENERATOR.reload_command(theme) == f"plasma-apply-desktoptheme {style_id(theme)}"


def test_a_new_look_replaces_the_old_package(style):
    first, second = look(radius=12), look(radius=6)
    engine.apply(first, style)
    plan = engine.build_plan(second, style)
    assert plan.targets[0].stale
    assert not engine.is_current(plan, style)

    result = engine.apply(second, style)

    assert installed() == [style_id(second)]
    assert kconfig.user_value("plasmarc", ["Theme"], "name") == style_id(second)
    assert result.snapshot.settings["panel"]["style"] == style_id(first)

    engine.restore(result.snapshot, style, consume=True)
    assert installed() == [style_id(first)]
    assert kconfig.user_value("plasmarc", ["Theme"], "name") == style_id(first)


def test_undo_puts_back_a_style_the_user_had(style):
    kconfig.write_value(style, "plasmarc", ["Theme"], "name", "breeze-dark")
    result = engine.apply(look(), style)
    assert kconfig.user_value("plasmarc", ["Theme"], "name") != "breeze-dark"
    # a system style the app does not own
    style.handlers["plasma-apply-desktoptheme"] = lambda argv: (
        kconfig.write_value(style, "plasmarc", ["Theme"], "name", argv[1]) or Result(0)
    )

    assert engine.restore(result.snapshot, style, consume=True) == []

    assert kconfig.user_value("plasmarc", ["Theme"], "name") == "breeze-dark"
    assert installed() == []


def test_undo_removes_the_key_again_when_it_was_not_there(style):
    result = engine.apply(look(), style)
    assert kconfig.user_value("plasmarc", ["Theme"], "name") is not None

    assert engine.restore(result.snapshot, style, consume=True) == []

    assert kconfig.user_value("plasmarc", ["Theme"], "name") is None
    assert installed() == []


def test_undo_leaves_the_plasmarc_as_it_was(style):
    path = paths.config_home() / "plasmarc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[Wallpapers]\nusersWallpapers=a.jpg\n")
    result = engine.apply(look(), style)

    assert engine.restore(result.snapshot, style, consume=True) == []

    assert path.read_text() == "[Wallpapers]\nusersWallpapers=a.jpg\n"


def test_undo_keeps_a_default_the_user_had_hidden(style):
    path = paths.config_home() / "plasmarc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[Theme]\nname[$d]\n")
    result = engine.apply(look(), style)
    assert result.snapshot.settings["panel"] == {"style": None, "masked": True, "file": True}

    assert engine.restore(result.snapshot, style, consume=True) == []

    assert path.read_text() == "[Theme]\nname[$d]\n"


def test_undo_goes_back_to_the_style_of_a_global_theme(style):
    """Without a value of the user's, the style is the one Plasma's defaults name."""
    style.defaults[("plasmarc", ("Theme",), "name")] = "Nordic"
    nordic = paths.data_home() / "plasma/desktoptheme/Nordic"
    nordic.mkdir(parents=True)
    (nordic / "metadata.json").write_text("{}\n")
    result = engine.apply(look(), style)

    assert engine.restore(result.snapshot, style, consume=True) == []

    assert style.calls_to_tool[-1] == ["plasma-apply-desktoptheme", "Nordic"]  # Plasma switches now
    assert not (paths.config_home() / "plasmarc").exists()
    assert kconfig.effective_value(style, "plasmarc", ["Theme"], "name") == "Nordic"


def test_undo_goes_back_to_the_plain_default_when_the_user_had_hidden_the_global_one(style):
    style.defaults[("plasmarc", ("Theme",), "name")] = "Nordic"
    path = paths.config_home() / "plasmarc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[Theme]\nname[$d]\n")
    result = engine.apply(look(), style)

    assert engine.restore(result.snapshot, style, consume=True) == []

    assert style.calls_to_tool[-1] == ["plasma-apply-desktoptheme", "default"]
    assert path.read_text() == "[Theme]\nname[$d]\n"


def test_a_style_that_is_as_it_was_is_not_switched_again(style):
    settings = GENERATOR.capture_settings(style)
    GENERATOR.restore_settings(settings, style)
    kconfig.write_value(style, "plasmarc", ["Theme"], "name", "breeze-dark")
    GENERATOR.restore_settings(GENERATOR.capture_settings(style), style)
    assert style.calls_to_tool == []


def test_undo_does_not_leave_an_empty_plasmarc_behind(style):
    result = engine.apply(look(), style)
    engine.restore(result.snapshot, style, consume=True)
    assert not (paths.config_home() / "plasmarc").exists()


def test_a_style_that_plasma_refuses_rolls_everything_back(style):
    engine.apply(look(radius=12), style)
    style.handlers["plasma-apply-desktoptheme"] = lambda argv: Result(255, "", "Could not find theme")

    with pytest.raises(ApplyError) as error:
        engine.apply(look(radius=6), style)

    assert "did not accept" in str(error.value.message)
    assert installed() == [style_id(look(radius=12))]
    assert kconfig.user_value("plasmarc", ["Theme"], "name") == style_id(look(radius=12))
    assert len(snapshots.list_snapshots()) == 1


def test_a_tool_that_says_yes_but_changes_nothing_is_an_error(style):
    style.handlers["plasma-apply-desktoptheme"] = lambda argv: Result(0, "Successfully applied\n")
    with pytest.raises(ApplyError):
        engine.apply(look(), style)
    assert installed() == []
    assert kconfig.user_value("plasmarc", ["Theme"], "name") is None


def test_unchanged_leaves_everything_alone(style):
    kconfig.write_value(style, "plasmarc", ["Theme"], "name", "breeze-dark")
    before = (paths.config_home() / "plasmarc").read_text()

    result = engine.apply(look(style="unchanged"), style)

    assert style.calls_to_tool == []
    assert installed() == []
    assert (paths.config_home() / "plasmarc").read_text() == before
    assert "panel" not in result.snapshot.settings
    assert engine.build_plan(look(style="unchanged"), style).warnings == []


def test_a_package_made_by_someone_else_is_never_removed(style):
    other = packages_dir() / "PlasmaThemeStudio-Mine-12345678"
    other.mkdir(parents=True)
    (other / "metadata.json").write_text('{"KPlugin": {"Id": "x"}}\n')
    third = packages_dir() / "SomeoneElse"
    third.mkdir()
    (third / "metadata.json").write_text(JSON_MARKER + "\n}\n")  # not in our folder naming

    engine.apply(look(), style)

    assert (other / "metadata.json").exists()
    assert (third / "metadata.json").exists()


def test_a_foreign_file_in_our_package_blocks_the_apply(style):
    target = GENERATOR.files(look())[1].path
    target.parent.mkdir(parents=True)
    target.write_text("[Hand]\nmade=1\n")
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(look(), style)


def test_stale_packages_are_only_ones_this_app_wrote(style):
    engine.apply(look(radius=12), style)
    stale = GENERATOR.stale_files(look(radius=5))
    old = packages_dir() / style_id(look(radius=12))
    assert old in stale and old / "widgets/panel-background.svg" in stale
    assert old / "widgets" in stale
    assert all(made_here(p) for p in stale if p.is_file())
    assert GENERATOR.stale_files(look(radius=12)) == []
    (old / "widgets/panel-background.svg").write_text("<svg/>")
    assert old / "widgets/panel-background.svg" not in GENERATOR.stale_files(look(radius=5))


def test_a_style_from_elsewhere_is_named_in_a_warning(style):
    assert GENERATOR.warnings(look(), style) == []
    kconfig.write_value(style, "plasmarc", ["Theme"], "name", "breeze-dark")
    [warning] = GENERATOR.warnings(look(), style)
    assert "breeze-dark" in str(warning) and "Breeze" in str(warning)

    kconfig.write_value(style, "plasmarc", ["Theme"], "name", style_id(look()))
    assert GENERATOR.warnings(look(), style) == []


def test_the_style_name_in_a_warning_is_the_one_system_settings_shows(style, home):
    folder = home / "system/share/plasma/desktoptheme/nordic"
    folder.mkdir(parents=True)
    (folder / "metadata.json").write_text('{"KPlugin": {"Name": "Nordic Night", "Id": "nordic"}}')
    kconfig.write_value(style, "plasmarc", ["Theme"], "name", "nordic")
    assert "Nordic Night" in str(GENERATOR.warnings(look(), style)[0])


def test_missing_tools_block_the_apply(style):
    for tool in ("plasma-apply-desktoptheme", "kreadconfig6", "kwriteconfig6"):
        style.missing = {tool}
        assert tool in str(GENERATOR.unavailable_reason(style))
        with pytest.raises(engine.ApplyBlocked):
            engine.apply(look(), style)
    style.missing = set()
    assert GENERATOR.unavailable_reason(style) is None
    assert installed() == []


# popups, tooltips and widgets


def popup_look(p_radius=None, p_border=None, p_opacity=None, **panel):
    theme = look(**panel)
    for key, value in (("radius", p_radius), ("border_width", p_border), ("opacity", p_opacity)):
        if value is not None:
            theme.set("popup", key, value)
    return theme


def test_every_popup_file_has_its_required_ids_and_no_text():
    files = package_files(popup_look(6, 1, 0.7))
    assert POPUP_FILES == ("dialogs/background.svg", "widgets/tooltip.svg", "widgets/background.svg")
    for name in POPUP_FILES:
        for prefix in ("", "solid/"):
            content = files[prefix + name].content
            ids = set(re.findall(r' id="([^"]+)"', content))
            assert POPUP_REQUIRED_IDS <= ids
            assert "thick-center" not in ids
            assert "<text" not in content and "transform" not in content.lower()
            assert 'class="ColorScheme-Background" fill="currentColor"' in content
            assert GENERATOR.check_output(files[prefix + name]) == []
    assert "thick-center" in files["widgets/panel-background.svg"].content


def test_the_check_requires_the_pieces_of_a_popup_background():
    file = package_files(popup_look())["dialogs/background.svg"]
    bad = type(file)(file.path, file.content.replace('id="shadow-top"', 'id="x"'), file.marker)
    assert GENERATOR.check_output(bad)


def test_popup_values_are_independent_from_the_panel():
    files = package_files(popup_look(14, 0, 0.5, radius=0, border=3, opacity=0.9))
    panel = files["widgets/panel-background.svg"].content
    popup = files["dialogs/background.svg"].content
    assert panel == panel_svg(0, 3, 0.9, solid=False)
    assert popup == panel_svg(14, 0, 0.5, solid=False, thick=False)
    assert (
        'fill-opacity="0.5"' in popup
        and 'fill-opacity="0.5"' not in files["solid/dialogs/background.svg"].content
    )
    assert files["widgets/tooltip.svg"].content == popup
    assert files["widgets/background.svg"].content == popup


def test_popups_follow_the_panel_until_they_have_their_own():
    files = package_files(look(radius=7, border=1, opacity=0.6))
    assert files["dialogs/background.svg"].content == panel_svg(7, 1, 0.6, solid=False, thick=False)
    shared = Theme({("meta", "name"): "T", ("panel", "style"): "generated", ("shape", "radius"): 9})
    assert shared.resolved("popup", "radius") == 9
    assert style_id(shared) == style_id(
        look(
            radius=9,
            border=shared.get("panel", "border_width"),
            opacity=shared.get("panel", "opacity"),
            name="T",
        )
    )


def test_the_id_changes_with_the_popup_values():
    base = style_id(look())
    assert style_id(popup_look(p_radius=3)) != base
    assert style_id(popup_look(p_border=3)) != base
    assert style_id(popup_look(p_opacity=0.5)) != base
    assert style_id(popup_look(p_radius=3)) != style_id(popup_look(p_radius=4))
    assert style_id(popup_look(p_radius=12, border=2, opacity=0.85)) == base  # the same as inherited


def test_an_old_package_of_this_theme_becomes_stale(style):
    engine.apply(popup_look(p_radius=3), runner=style)
    old = packages_dir() / style_id(popup_look(p_radius=3))
    stale = GENERATOR.stale_files(popup_look(p_radius=4))
    assert old in stale and old / "dialogs/background.svg" in stale
    assert old not in GENERATOR.stale_files(popup_look(p_radius=3))


def test_the_popup_page_explains_when_the_values_apply():
    note = " ".join(str(n) for n in GENERATOR.section_notes(look(style="unchanged"), "popup"))
    assert "Made from this theme" in note and "keeps its own popups" in note
    assert GENERATOR.section_notes(look(), "popup") == []
    assert GENERATOR.section_notes(look(style="unchanged"), "panel") == GENERATOR.notes(
        look(style="unchanged")
    )
    assert GENERATOR.sections == ("panel", "popup")


def test_undo_removes_the_plasmarc_the_apply_made(style):
    path = paths.config_home() / "plasmarc"
    assert not path.exists()
    result = engine.apply(look(), style)
    assert result.snapshot.settings["panel"]["file"] is False
    assert path.exists()

    assert engine.restore(result.snapshot, style, consume=True) == []

    assert not path.exists()


def test_undo_removes_an_empty_plasmarc_the_style_tool_left_behind(style):
    """The tool of Plasma 6.8 leaves an empty file when it switches to the default."""
    result = engine.apply(look(), style)

    def tool(argv):
        (paths.config_home() / "plasmarc").write_text("")
        return Result(0, "Successfully applied\n")

    style.handlers["plasma-apply-desktoptheme"] = tool
    kconfig.write_value(style, "plasmarc", ["Theme"], "name", None)
    (paths.config_home() / "plasmarc").write_text("")
    assert engine.restore(result.snapshot, style, consume=True) == []
    assert not (paths.config_home() / "plasmarc").exists()
