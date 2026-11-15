# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from plasma_theme_studio import paths
from plasma_theme_studio.apply import engine
from plasma_theme_studio.generators import CSS_MARKER, made_here
from plasma_theme_studio.generators.gtk import (
    IMPORT_LINE,
    GtkGenerator,
    build_css,
    css_path,
    gtk_css_path,
    with_import,
    without_import,
)
from plasma_theme_studio.model.theme import Theme

GENERATOR = GtkGenerator()


def look(radius=8, border=1, window_radius=None, style="generated"):
    values = {
        ("meta", "name"): "My Theme",
        ("gtk", "style"): style,
        ("gtk", "radius"): radius,
        ("gtk", "border_width"): border,
    }
    if window_radius is not None:
        values[("gtk", "window_radius")] = window_radius
    return Theme(values)


def gtk_css(version, text=None):
    path = gtk_css_path(version)
    if text is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
    return path


def raw(version):
    return gtk_css_path(version).read_bytes().decode() if gtk_css_path(version).exists() else None


@pytest.fixture(autouse=True)
def only_gtk(use_generators):
    use_generators(GENERATOR)


def test_wanted_only_when_generated():
    assert GENERATOR.wanted(look())
    assert not GENERATOR.wanted(look(style="unchanged"))
    assert GENERATOR.notes(look(style="unchanged"))


def test_sections_and_id():
    assert GENERATOR.id == "gtk"
    assert GENERATOR.sections == ("gtk",)


@pytest.mark.parametrize("radius,border", [(0, 0), (5, 1), (24, 4)])
@pytest.mark.parametrize("version", [3, 4])
def test_css_values_marker_and_braces(radius, border, version):
    text = build_css(look(radius, border), version)
    assert text.startswith(CSS_MARKER + "\n")
    assert text.count("{") == text.count("}")
    assert f"border-radius: {radius}px;" in text
    assert f"border-width: {border}px;" in text
    assert "<text" not in text
    for planned in GENERATOR.files(look(radius, border)):
        assert GENERATOR.check_output(planned) == []


def test_window_radius_follows_window_and_shape_by_default():
    theme = look(radius=7, window_radius=14)
    assert "decoration, .csd decoration { border-radius: 14px; }" in build_css(theme, 3)
    assert "window.csd, dialog.csd { border-radius: 14px; }" in build_css(theme, 4)
    assert "--window-radius: 14px" in build_css(theme, 4)
    follows = Theme({("meta", "name"): "x", ("gtk", "style"): "generated", ("shape", "radius"): 9})
    assert "--window-radius: 9px" in build_css(follows, 4)


def test_maximized_reset_in_both_versions():
    assert ".maximized decoration" in build_css(look(), 3)
    assert "window.csd.maximized" in build_css(look(), 4)


def test_big_radius_caps_cards():
    assert "border-radius: 24px; }" in build_css(look(24), 4)
    assert (
        "list.boxed-list, .boxed-list > row:first-child, preferencesgroup > box > list { border-radius: 24px;"
        in (build_css(look(24), 4))
    )


def test_libadwaita_colors_only_in_gtk4():
    assert "@define-color accent_bg_color #3daee9;" in build_css(look(), 4)
    assert "@define-color" not in build_css(look(), 3)


def test_foreground_readable_on_accent():
    theme = look()
    theme.set("colors", "accent", "#ffff00")
    assert "@define-color accent_fg_color #232629;" in build_css(theme, 4)
    theme.set("colors", "accent", "#000066")
    assert "@define-color accent_fg_color #ffffff;" in build_css(theme, 4)


def test_no_compound_not_in_output():
    for version in (3, 4):
        assert GENERATOR.check_output(GENERATOR.files(look())[version - 3]) == []


def test_check_output_rejects_bad_sheets(home):
    from plasma_theme_studio.generators import PlannedFile

    bad = PlannedFile(css_path(4), CSS_MARKER + "\na:not(.b.c) { }\n", CSS_MARKER)
    assert GENERATOR.check_output(bad)
    bad = PlannedFile(css_path(4), CSS_MARKER + "\na { \n", CSS_MARKER)
    assert GENERATOR.check_output(bad)
    bad = PlannedFile(css_path(4), CSS_MARKER + "\n# comment\n", CSS_MARKER)
    assert GENERATOR.check_output(bad)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "@import 'colors.css';\n",
        "@import 'colors.css';",
        "button { color: red; }\n\nentry { color: blue; }\n",
        "@import 'colors.css';\r\nbutton { color: red; }\r\n",
        "a { }",
        f"x {{ }}\n{IMPORT_LINE}\n@import 'colors.css';\n",
        f"{IMPORT_LINE}\r\nbutton {{ }}\r\n",
    ],
)
def test_import_add_remove_is_exact(text):
    added = with_import(text)
    assert IMPORT_LINE in added
    assert with_import(added) == added
    if IMPORT_LINE not in text:
        assert without_import(added) == text


@pytest.mark.parametrize(
    "before",
    [
        None,
        "",
        "@import 'colors.css';\n",
        "@import 'colors.css';",
        "button { color: red; }\n",
        "@import 'colors.css';\r\nbutton { color: red; }\r\n",
        "no final newline {}",
        f"{IMPORT_LINE}\nbutton {{ }}\n",
    ],
)
def test_apply_and_undo_leave_gtk_css_byte_for_byte(home, runner, before):
    for v in (3, 4):
        if before is not None:
            gtk_css(v, before)
    result = engine.apply(look(), runner)
    for v in (3, 4):
        assert IMPORT_LINE in raw(v)
        assert css_path(v).read_text().startswith(CSS_MARKER)
        assert made_here(css_path(v))
    assert GENERATOR.is_active(look(), runner)
    assert not engine.restore(result.snapshot, runner, consume=True)
    for v in (3, 4):
        assert raw(v) == before
        assert not css_path(v).exists()
    if before is None:
        assert not (paths.config_home() / "gtk-3.0").exists()
        assert not (paths.config_home() / "gtk-4.0").exists()
    assert not GENERATOR.is_active(look(), runner)


def test_undo_puts_back_gtk_css_as_it_was_whatever_kded_wrote_meanwhile(home, runner):
    result = engine.apply(look(), runner)
    for v in (3, 4):
        with gtk_css(v).open("a") as f:
            f.write("@import 'colors.css';\n")
    engine.restore(result.snapshot, runner, consume=True)
    for v in (3, 4):
        assert raw(v) is None  # there was no gtk.css before the apply


def test_undo_of_second_apply_keeps_line_first_undo_removes_it(home, runner):
    first = engine.apply(look(radius=3), runner)
    second = engine.apply(look(radius=9), runner)
    assert "border-radius: 9px" in css_path(4).read_text()
    engine.restore(second.snapshot, runner, consume=True)
    assert "border-radius: 3px" in css_path(4).read_text()
    assert IMPORT_LINE in raw(4)
    engine.restore(first.snapshot, runner, consume=True)
    assert raw(4) is None


def test_foreign_css_file_is_never_overwritten(home, runner):
    css_path(4).parent.mkdir(parents=True)
    css_path(4).write_text("mine { }\n")
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(look(), runner)
    assert css_path(4).read_text() == "mine { }\n"
    assert raw(4) is None
    assert not css_path(3).exists()


def test_symlinked_gtk_css_is_followed_and_kept(home, runner):
    target = home / "dotfiles/gtk4.css"
    target.parent.mkdir()
    target.write_text("button { color: red; }\n")
    gtk_css(3, "")
    gtk_css_path(4).parent.mkdir(parents=True, exist_ok=True)
    gtk_css_path(4).symlink_to(target)
    result = engine.apply(look(), runner)
    assert gtk_css_path(4).is_symlink()
    assert IMPORT_LINE in target.read_text()
    engine.restore(result.snapshot, runner, consume=True)
    assert gtk_css_path(4).is_symlink()
    assert target.read_text() == "button { color: red; }\n"


def test_symlink_out_of_home_is_a_problem(home, tmp_path_factory, runner):
    outside = tmp_path_factory.mktemp("outside") / "gtk.css"
    outside.write_text("")
    gtk_css_path(4).parent.mkdir(parents=True)
    gtk_css_path(4).symlink_to(outside)
    assert GENERATOR.problems(look())
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(look(), runner)
    assert outside.read_text() == ""


def test_unreadable_gtk_css_is_a_problem(home):
    gtk_css(3, "")
    gtk_css_path(4).parent.mkdir(parents=True)
    gtk_css_path(4).write_bytes(b"\xff\xfe\x00")
    assert GENERATOR.problems(look())


def test_not_wanted_changes_nothing(home, runner):
    result = engine.apply(look(style="unchanged"), runner)
    assert result.plan.wanted_targets == []
    assert not (paths.config_home() / "gtk-4.0").exists()


def test_is_active_needs_import_and_current_content(home, runner):
    engine.apply(look(), runner)
    assert GENERATOR.is_active(look(), runner)
    assert not GENERATOR.is_active(look(radius=2), runner)
    gtk_css(4, "")
    assert not GENERATOR.is_active(look(), runner)


def test_second_apply_is_current(home, runner):
    theme = look()
    engine.apply(theme, runner)
    assert engine.is_current(engine.build_plan(theme, runner), runner)


def test_notes_explain_reload(home):
    text = " ".join(str(n) for n in GENERATOR.notes(look()))
    assert "restart" in text and "dark" in text
