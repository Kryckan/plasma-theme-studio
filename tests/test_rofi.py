# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import re

import pytest

from plasma_theme_studio import paths
from plasma_theme_studio.apply import desktop, engine
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.generators import CSS_MARKER, ApplyError, made_here
from plasma_theme_studio.generators.rofi import (
    OUR_TAG,
    PREV_TAG,
    RofiGenerator,
    effective_theme,
    ensure_contrast,
    pango_font,
    rasi_text,
    set_theme_line,
)
from plasma_theme_studio.model.color import Color, contrast
from plasma_theme_studio.model.theme import Theme

GENERATOR = RofiGenerator()
STATES = [
    f"{row}{kind}-{part}"
    for row in ("", "alternate-", "selected-")
    for kind in ("normal", "urgent", "active")
    for part in ("background", "foreground")
]


def look(radius=10, border=2, opacity=1.0, font=None, style="generated", name="My Theme", **colors):
    values = {
        ("meta", "name"): name,
        ("rofi", "style"): style,
        ("rofi", "radius"): radius,
        ("rofi", "border_width"): border,
        ("rofi", "opacity"): opacity,
        ("rofi", "font"): font,
    }
    values.update({("colors", key): value for key, value in colors.items()})
    return Theme(values)


def config_file():
    return paths.config_home() / "rofi/config.rasi"


def theme_file(theme):
    return paths.config_home() / f"rofi/themes/{theme.slug}.rasi"


def block(text, selector):
    match = re.search(rf"^{re.escape(selector)} \{{(.*?)^\}}", text, re.M | re.S)
    assert match, selector
    return match.group(1)


def variable(text, name):
    return re.search(rf"^\s+{re.escape(name)}:\s+(.*?);", block(text, "*"), re.M).group(1)


@pytest.fixture
def rofi(home, runner, use_generators):
    """A runner with a fake rofi that reports a parse failure like the real one."""
    use_generators(GENERATOR)
    runner.dumped = []

    def tool(argv):
        runner.dumped.append(argv)
        if "-dump-theme" not in argv:
            return Result(0, "Version: 2.0.0\n")
        text = open(argv[argv.index("-theme") + 1], encoding="utf-8").read()
        if text.count("{") != text.count("}") or "FAIL" in text:
            return Result(0, "", 'Rofi-WARNING **: Failed to parse theme: "x"\n')
        return Result(0, "dump\n")

    runner.handlers["rofi"] = tool
    return runner


# The theme text


def test_has_the_marker_and_all_state_variables():
    text = rasi_text(look(font="Noto Sans 10"))
    assert text.startswith(CSS_MARKER + "\n")
    star = block(text, "*")
    for name in STATES:
        assert re.search(rf"^\s+{name}:", star, re.M), name
    assert len(STATES) == 18
    assert "<text" not in text


def test_every_style_variable_is_defined_and_used_is_defined():
    text = rasi_text(look(font="Sans 10"))
    defined = set(re.findall(r"^\s+([\w-]+):", block(text, "*"), re.M))
    for used in re.findall(r"@([\w-]+)", text):
        assert used in defined, used
    for row in ("normal", "selected", "alternate"):
        for kind in ("normal", "urgent", "active"):
            assert f"element {row}.{kind} {{" in text


def test_alpha_byte_is_only_on_the_window_background():
    translucent = rasi_text(look(opacity=0.5, font="Sans 10", window="#202326"))
    assert variable(translucent, "bg") == "#20232680"
    assert variable(translucent, "bg-view").count("#") == 1 and len(variable(translucent, "bg-view")) == 7
    opaque = rasi_text(look(opacity=1.0, font="Sans 10", window="#202326"))
    assert variable(opaque, "bg") == "#202326"
    assert variable(rasi_text(look(opacity=0.3, font="Sans 10", window="#ffffff")), "bg") == "#ffffff4d"


@pytest.mark.parametrize(("radius", "border"), [(0, 0), (8, 2), (24, 4), (3, 4)])
def test_radius_and_border(radius, border):
    text = rasi_text(look(radius=radius, border=border, font="Sans 10"))
    window = block(text, "window")
    assert f"border-radius:    {radius}px;" in window
    assert f"border:           {border}px;" in window
    inner = max(0, radius - border)
    assert f"border-radius:    {inner}px;" in block(text, "inputbar")
    # A window without border does not show the accent at its edge.
    expected = "#3daee9" if border else "#eff0f1"
    assert variable(text, "border-col") == expected


def test_radius_follows_shape_when_unset():
    theme = look(font="Sans 10")
    theme._values[("rofi", "radius")] = None
    theme._values[("shape", "radius")] = 7
    assert "border-radius:    7px;" in block(rasi_text(theme), "window")


def test_font_chosen_blank_and_desktop(home):
    assert variable(rasi_text(look(font="Fira Sans 12")), "font") == '"Fira Sans 12"'
    # Nothing set: Noto Sans 10.
    assert variable(rasi_text(look(font=None)), "font") == '"Noto Sans 10"'
    # Empty text counts as not set.
    assert variable(rasi_text(look(font="")), "font") == '"Noto Sans 10"'
    assert variable(rasi_text(look(font="   ")), "font") == '"Noto Sans 10"'
    (paths.config_home()).mkdir(parents=True)
    (paths.config_home() / "kdeglobals").write_text("[General]\nfont=Cantarell,11,-1,5,400,0,0,0,0,0\n")
    assert variable(rasi_text(look(font=None)), "font") == '"Cantarell 11"'
    assert variable(rasi_text(look(font="")), "font") == '"Cantarell 11"'
    assert variable(rasi_text(look(font="Mono 9")), "font") == '"Mono 9"'


def test_font_is_the_same_for_the_same_desktop(home):
    (paths.config_home()).mkdir(parents=True)
    (paths.config_home() / "kdeglobals").write_text("[General]\nfont=Cantarell,11\n")
    assert GENERATOR.files(look()) == GENERATOR.files(look())


def test_pango_font_and_quoting():
    assert pango_font("Noto Sans,10,-1,5,400,0") == "Noto Sans 10"
    assert pango_font("Sans,10.5") == "Sans 10.5"
    assert pango_font("Sans") == "Sans 10"
    assert pango_font("") == "Noto Sans 10"
    assert pango_font(",10") == "Noto Sans 10"
    text = rasi_text(look(), 'Evil"Font\\ 10\n}')
    assert variable(text, "font") == '"Evil\\"Font\\\\ 10}"'
    assert GENERATOR.check_output(GENERATOR.files(look(font='a"b'))[0]) == []


def test_text_is_corrected_to_aa_on_the_backgrounds_it_sits_on():
    theme = look(
        font="Sans 10",
        window="#808080",
        view="#8a8a8a",
        button="#777777",
        text="#8c8c8c",
        text_muted="#909090",
        accent="#7a7a7a",
        negative="#808000",
        positive="#008080",
    )
    text = rasi_text(theme)
    window, view = Color.parse("#808080"), Color.parse("#8a8a8a")
    for name in ("fg", "fg-muted", "prompt-col"):
        color = Color.parse(variable(text, name))
        assert contrast(color, view) >= 4.5, name
    assert contrast(Color.parse(variable(text, "fg")), window) >= 4.5
    assert contrast(Color.parse(variable(text, "fg")), Color.parse(variable(text, "bg-button"))) >= 4.5
    assert contrast(Color.parse(variable(text, "on-accent")), Color.parse(variable(text, "accent"))) >= 4.5
    for name in ("urgent", "active"):
        assert contrast(Color.parse(variable(text, name)), window) >= 4.5, name
        assert contrast(Color.parse(variable(text, name)), Color.parse(variable(text, "bg-alt"))) >= 4.5


def test_passing_colors_are_not_changed():
    theme = Theme.from_preset("breeze-dark")
    theme.set("rofi", "style", "generated")
    text = rasi_text(theme, "Sans 10")
    assert variable(text, "fg") == theme.get("colors", "text")
    assert variable(text, "fg-muted") == theme.get("colors", "text_muted")
    assert ensure_contrast(Color.parse("#ffffff"), [Color.parse("#000000")]) == Color.parse("#ffffff")


def test_files_and_slug():
    theme = look(name="Ocean Night")
    (planned,) = GENERATOR.files(theme)
    assert planned.path == paths.config_home() / "rofi/themes/OceanNight.rasi"
    assert planned.marker == CSS_MARKER
    assert planned.content.splitlines()[1] == "/* Theme: Ocean Night */"
    assert "/* Theme: a  b */" in rasi_text(look(name="a */ b"), "Sans 10")


def test_check_output():
    (good,) = GENERATOR.files(look())
    assert GENERATOR.check_output(good) == []
    broken = type(good)(good.path, good.content + "\nwindow {\n", CSS_MARKER)
    assert GENERATOR.check_output(broken)
    hashed = type(good)(good.path, good.content + "\n# a comment\n", CSS_MARKER)
    assert GENERATOR.check_output(hashed)


# config.rasi editing

CASES = {
    "none": None,
    "empty": "",
    "absolute": '@theme "/usr/share/rofi/themes/Arc-Dark.rasi"\n',
    "block comment": '/*\n@theme "Arc"\n*/\nwindow { width: 300px; }\n',
    "line comment": '// @theme "Arc"\nwindow { width: 300px; }\n',
    "configuration": 'configuration {\n  modes: "drun,run";\n}\n',
    "config and theme": 'configuration { modes: "drun"; }\n@theme "Arc-Dark"\nwindow { width: 300px; }\n',
    "two themes": '@theme "Arc"\n@theme "Arc-Dark" // mine\n',
    "crlf": 'configuration { modes: "drun"; }\r\n@theme "Arc-Dark"\r\nwindow { }\r\n',
    "no final newline": '@theme "Arc-Dark"',
    "no final newline config": 'configuration { modes: "drun"; }',
    "string with theme": 'configuration { prompt: "@theme \\"x\\""; }\n',
    "code before on the line": 'configuration { modes: "drun"; } @theme "Arc" window { width: 3px; }\n',
}


def theme_lines(text):
    return effective_theme(text)


@pytest.mark.parametrize("case", CASES)
def test_set_theme_line_makes_ours_effective_and_keeps_the_rest(case):
    original = CASES[case] or ""
    edited = set_theme_line(original, "MyTheme")
    assert effective_theme(edited) == ("MyTheme", True)
    # Setting it again changes nothing.
    assert set_theme_line(edited, "MyTheme") == edited
    # Another name replaces ours and keeps one previous-line comment at most per earlier theme.
    again = set_theme_line(edited, "Other")
    assert effective_theme(again) == ("Other", True)
    assert again.count(OUR_TAG) == edited.count(OUR_TAG)
    # Everything that was there is still there.
    for line in original.splitlines():
        if line.strip() and "@theme" not in line:
            assert line.strip() in edited


def test_user_theme_line_is_kept_as_a_comment_in_place():
    edited = set_theme_line('@theme "Arc-Dark"\nwindow { width: 300px; }\n', "My")
    assert edited == f'{PREV_TAG}@theme "Arc-Dark"\n@theme "My" {OUR_TAG}\nwindow {{ width: 300px; }}\n'


def test_without_a_theme_line_ours_goes_on_top():
    assert set_theme_line("", "My") == f'@theme "My" {OUR_TAG}\n'
    assert (
        set_theme_line('configuration { modes: "drun"; }', "My")
        == f'@theme "My" {OUR_TAG}\nconfiguration {{ modes: "drun"; }}'
    )
    assert set_theme_line("a\r\nb\r\n", "My").startswith(f'@theme "My" {OUR_TAG}\r\n')


def test_the_last_statement_is_replaced_and_comments_are_not_touched():
    edited = set_theme_line('@theme "Arc"\n@theme "Arc-Dark" // mine\n', "My")
    assert edited.startswith('@theme "Arc"\n')
    assert f'{PREV_TAG}@theme "Arc-Dark" // mine\n@theme "My" {OUR_TAG}\n' in edited
    block_comment = CASES["block comment"]
    edited = set_theme_line(block_comment, "My")
    assert edited == f'@theme "My" {OUR_TAG}\n' + block_comment


def test_crlf_lines_stay_crlf():
    edited = set_theme_line(CASES["crlf"], "My")
    assert edited.count("\n") == edited.count("\r\n")
    assert f'@theme "My" {OUR_TAG}\r\n' in edited


def test_effective_theme():
    assert effective_theme("") is None
    assert effective_theme('@theme "A"\n') == ("A", False)
    assert effective_theme(f'@theme "A" {OUR_TAG}\n') == ("A", True)
    assert effective_theme(f'@theme "A" {OUR_TAG}\n@theme "B"\n') == ("B", False)


# The target


def test_wanted_notes_and_unavailable(rofi):
    assert GENERATOR.wanted(look())
    assert not GENERATOR.wanted(look(style="unchanged"))
    assert GENERATOR.sections == ("rofi",)
    assert GENERATOR.id == "rofi"
    assert len(GENERATOR.notes(look(style="unchanged"))) == 1
    notes = " ".join(str(n) for n in GENERATOR.section_notes(look(), "rofi"))
    assert "starts" in notes and "KWin" in notes
    assert GENERATOR.unavailable_reason(rofi) is None
    rofi.missing.add("rofi")
    assert "Rofi was not found" in str(GENERATOR.unavailable_reason(rofi))


def test_apply_writes_the_theme_and_the_config_line_and_undo_restores(rofi):
    theme = look()
    config_file().parent.mkdir(parents=True)
    original = '@theme "/usr/share/rofi/themes/Arc-Dark.rasi"\r\nwindow { }'
    config_file().write_bytes(original.encode())
    plan = engine.build_plan(theme, rofi)
    assert not plan.blocking
    assert not engine.is_current(plan, rofi)
    result = engine.apply(theme, rofi)
    assert theme_file(theme).read_text() == rasi_text(theme)
    assert made_here(theme_file(theme))
    assert effective_theme(config_file().read_text()) == ("MyTheme", True)
    assert GENERATOR.is_active(theme, rofi)
    assert engine.is_current(engine.build_plan(theme, rofi), rofi)
    # An apply that changes nothing keeps the file as it is.
    text = config_file().read_text()
    engine.apply(theme, rofi)
    assert config_file().read_text() == text
    assert engine.restore(result.snapshot, rofi, consume=True) == []
    assert config_file().read_bytes() == original.encode()
    assert not theme_file(theme).exists()


@pytest.mark.parametrize("case", CASES)
def test_undo_is_byte_for_byte(rofi, case):
    original = CASES[case]
    if original is not None:
        config_file().parent.mkdir(parents=True)
        config_file().write_bytes(original.encode())
    theme = look()
    result = engine.apply(theme, rofi)
    assert effective_theme(config_file().read_text()) == ("MyTheme", True)
    assert engine.restore(result.snapshot, rofi, consume=True) == []
    if original is None:
        assert not config_file().exists()
    else:
        assert config_file().read_bytes() == original.encode()


def test_two_applies_undone_in_turn(rofi):
    first, second = look(radius=4), look(radius=20, name="Other")
    one = engine.apply(first, rofi)
    after_first = config_file().read_bytes()
    two = engine.apply(second, rofi)
    assert effective_theme(config_file().read_text()) == ("Other", True)
    assert engine.restore(two.snapshot, rofi, consume=True) == []
    assert config_file().read_bytes() == after_first
    assert engine.restore(one.snapshot, rofi, consume=True) == []
    assert not config_file().exists()
    assert snapshots.list_snapshots() == []


def test_a_foreign_file_with_our_slug_is_never_overwritten(rofi):
    theme = look()
    theme_file(theme).parent.mkdir(parents=True)
    theme_file(theme).write_text("window { width: 1px; }\n")
    with pytest.raises(engine.ApplyBlocked) as caught:
        engine.apply(theme, rofi)
    assert "not made by Plasma Theme Studio" in str(caught.value.problems[0])
    assert theme_file(theme).read_text() == "window { width: 1px; }\n"
    assert not config_file().exists()


def test_not_wanted_leaves_everything_alone(rofi):
    config_file().parent.mkdir(parents=True)
    config_file().write_text('@theme "Arc"\n')
    plan = engine.build_plan(look(style="unchanged"), rofi)
    target = next(t for t in plan.targets if t.generator is GENERATOR)
    assert not target.wanted
    engine.apply(look(style="unchanged"), rofi)
    assert config_file().read_text() == '@theme "Arc"\n'
    assert not theme_file(look()).exists()


def test_unavailable_blocks(rofi):
    rofi.missing.add("rofi")
    plan = engine.build_plan(look(), rofi)
    assert any("Rofi was not found" in str(p) for p in plan.blocking)


def test_is_active_needs_our_line_and_the_planned_file(rofi):
    theme = look()
    assert not GENERATOR.is_active(theme, rofi)
    engine.apply(theme, rofi)
    assert GENERATOR.is_active(theme, rofi)
    assert not GENERATOR.is_active(look(radius=3), rofi)
    theme_file(theme).write_text(theme_file(theme).read_text() + "\n")
    assert not GENERATOR.is_active(theme, rofi)
    engine.apply(theme, rofi)
    config_file().write_text(config_file().read_text() + '@theme "Arc"\n')
    assert not GENERATOR.is_active(theme, rofi)


def test_warning_about_a_user_theme_line(rofi):
    config_file().parent.mkdir(parents=True)
    config_file().write_text('@theme "Arc-Dark"\n')
    assert any("Arc-Dark" in str(w) for w in GENERATOR.warnings(look(), rofi))
    engine.apply(look(), rofi)
    assert GENERATOR.warnings(look(), rofi) == []


def test_rofi_parse_failure_is_a_warning_and_an_apply_failure(rofi):
    bad = look(name="FAIL")
    # The text of the theme itself is fine; the fake rofi fails on the word in the name comment.
    assert any("cannot read" in str(w) for w in GENERATOR.warnings(bad, rofi))
    config_file().parent.mkdir(parents=True)
    config_file().write_text('@theme "Arc"\n')
    with pytest.raises(ApplyError):
        engine.apply(bad, rofi)
    # The apply was rolled back.
    assert config_file().read_text() == '@theme "Arc"\n'
    assert not theme_file(bad).exists()
    ok = GENERATOR.warnings(look(), rofi)
    assert not any("cannot read" in str(w) for w in ok)


def test_validation_runs_rofi_without_config_and_without_a_window(rofi):
    GENERATOR.warnings(look(), rofi)
    (argv,) = rofi.dumped
    assert argv[:3] == ["rofi", "-no-config", "-theme"]
    assert argv[-1] == "-dump-theme"
    assert not any(a in argv for a in ("-show", "-dmenu"))


def test_unreadable_config_blocks_without_touching_anything(rofi):
    config_file().mkdir(parents=True)
    problems = GENERATOR.problems(look())
    assert problems and "cannot be read" in str(problems[0])
    config_file().rmdir()
    config_file().write_bytes(b"\xff\xfe\x00")
    assert GENERATOR.problems(look())


def test_restore_settings_ignores_nothing_and_changes_nothing_when_equal(rofi):
    config_file().parent.mkdir(parents=True)
    config_file().write_text("window { }\n")
    settings = GENERATOR.capture_settings(rofi)
    assert settings == {"config": "window { }\n"}
    before = config_file().stat().st_mtime_ns
    GENERATOR.restore_settings(settings, rofi)
    assert config_file().stat().st_mtime_ns == before
    GENERATOR.restore_settings({}, rofi)
    # no line of ours in the file: whatever is there now is the user's and stays
    GENERATOR.restore_settings({"config": desktop.ABSENT}, rofi)
    assert config_file().read_text() == "window { }\n"


def test_config_that_is_a_link_stays_a_link(rofi, tmp_path):
    target = tmp_path / "dotfiles/config.rasi"
    target.parent.mkdir()
    target.write_text('@theme "Arc"\n')
    config_file().parent.mkdir(parents=True)
    config_file().symlink_to(target)
    result = engine.apply(look(), rofi)
    assert config_file().is_symlink()
    assert effective_theme(target.read_text()) == ("MyTheme", True)
    assert engine.restore(result.snapshot, rofi, consume=True) == []
    assert config_file().is_symlink() and target.read_text() == '@theme "Arc"\n'


def test_reload_command_and_settings_text(rofi):
    assert "-dump-theme" in GENERATOR.reload_command(look())
    assert "config.rasi" in str(GENERATOR.changed_settings(look())[0])
