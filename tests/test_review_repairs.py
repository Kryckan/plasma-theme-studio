# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The faults and risks the checkers found in the installed parts and the new window."""

import random

import pytest

from plasma_theme_studio import desktopparts, kconfig, paths
from plasma_theme_studio.apply import engine, status
from plasma_theme_studio.generators import GENERATORS
from plasma_theme_studio.generators.base import ApplyError
from plasma_theme_studio.model.color import Color, on_accent
from plasma_theme_studio.model.parts import FontSpec
from plasma_theme_studio.model.theme import Theme, ThemeError
from plasma_theme_studio.pickers import _colors, plasmastyles

ACCENT = next(g for g in GENERATORS if g.id == "accent")

# ---- fonts -------------------------------------------------------------------------------------


def _forms(rng: random.Random) -> str:
    family, size = rng.choice(["Noto Sans", "Hack", "A"]), rng.choice([8, 10, 10.5, 12])
    weight = rng.choice([0, 1, 12, 25, 50, 57, 63, 75, 81, 87, 99, 100, 300, 400, 450, 700, 1000])
    slant = rng.choice([0, 1, 2])
    fields = [family, str(size), "-1", "5", str(weight), str(slant)]
    count = rng.choice([10, 11, 16])
    fields += ["0"] * (count - len(fields))
    if count == 11:
        fields[-1] = "Regular"
    return ",".join(fields)


def test_a_font_description_survives_being_written_short_and_read_again():
    rng = random.Random(7)
    for _ in range(600):
        text = _forms(rng)
        spec = FontSpec.parse(text)
        if spec is None:
            continue
        assert FontSpec.from_short(spec.short()) == spec, text
        assert FontSpec.from_short(spec.text()) == spec, text


def test_a_weight_below_one_hundred_is_written_and_read():
    spec = FontSpec("Hack", 10, 50)
    assert FontSpec.from_short(spec.short()) == spec


def test_an_eleven_field_font_has_its_old_weight_remapped():
    spec = FontSpec.parse("Noto Sans,10,-1,5,75,0,0,0,0,0,Bold")
    assert spec is not None and spec.weight == 700


# ---- decorations -------------------------------------------------------------------------------


def test_a_decoration_id_in_other_case_is_written_as_the_installed_one(desktop_runner):
    part = desktopparts.PARTS["decoration"]
    real = next(item.id for item in part._items() if "plastik" in item.id)
    odd = real.upper()
    part.validate(odd)  # lenient about the case ...
    part.apply(odd, desktop_runner)
    assert part.current(desktop_runner) == real  # ... but what KWin is given is the exact id


def test_an_id_that_a_tool_could_read_as_an_option_is_refused(desktop_runner):
    for name in ("icons", "plasma_style", "cursor_theme", "splash", "app_style"):
        with pytest.raises(ApplyError):
            desktopparts.PARTS[name].validate("-x")


# ---- the status ---------------------------------------------------------------------------------


def test_a_part_that_an_apply_would_refuse_is_blocked_and_says_why(desktop_runner):
    theme = Theme({("desktop", "icons"): "NoSuchIcons", ("desktop", "cursors"): "Pop"})
    records = {part.key: part for part in status.parts_status(theme, desktop_runner)}
    assert records["icons"].state == status.BLOCKED
    assert "NoSuchIcons" in records["icons"].theme
    assert records["pointers"].state == status.CHANGE
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(theme, desktop_runner)


def test_every_target_is_planned_and_checked_once_per_status(desktop_runner, monkeypatch):
    theme = Theme({("desktop", "icons"): "Papirus", ("desktop", "cursors"): "Pop", ("shape", "radius"): 9})
    planned, active = [], []
    real_plan = engine._plan_target
    monkeypatch.setattr(
        engine, "_plan_target", lambda generator, *a: planned.append(generator.id) or real_plan(generator, *a)
    )
    for generator in engine.generators.GENERATORS:
        real = generator.is_active
        monkeypatch.setattr(
            generator, "is_active", lambda *a, real=real, g=generator: active.append(g.id) or real(*a)
        )
    status.parts_status(theme, desktop_runner)
    assert len(planned) == len(set(planned)) and len(active) == len(set(active))


def test_the_panel_is_not_asked_when_the_theme_names_none(runner):
    calls = []
    real = runner.run
    runner.run = lambda argv, *a, **k: calls.append(argv[0]) or real(argv, *a, **k)
    status.parts_status(Theme(), runner)
    assert not any("qdbus" in call or "plasmashell" in call for call in calls)


# ---- the accent and the contrast of text on it ---------------------------------------------------


def test_an_accent_that_is_no_color_is_not_an_override(desktop_runner, home):
    (paths.config_home()).mkdir(parents=True, exist_ok=True)
    (paths.config_home() / "kdeglobals").write_text("[General]\nAccentColor=nonsense\n")
    assert not ACCENT.wanted(Theme())
    (paths.config_home() / "kdeglobals").write_text("[General]\nAccentColor=61,174,233\n")
    assert ACCENT.wanted(Theme())


def test_text_on_the_default_breeze_accent_is_dark_everywhere():
    accent, text, window = Color.parse("#3daee9"), Color.parse("#232629"), Color.parse("#eff0f1")
    assert on_accent(accent, text, window).hex == "#232629"


def test_the_pickers_choose_the_text_on_the_accent_as_the_color_scheme_does():
    for accent, text, window in (
        ("#3daee9", "#232629", "#eff0f1"),
        ("#1d99f3", "#fcfcfc", "#31363b"),
        ("#e8b000", "#ffffff", "#202020"),
    ):
        want = on_accent(Color.parse(accent), Color.parse(text), Color.parse(window)).hex
        roles = {"accent": accent, "text": text, "window": window}
        assert f"ForegroundNormal={Color.parse(want).kde}" in _colors.kdeglobals(roles)
        table = plasmastyles.table_from_roles(roles)
        assert table["Colors:Selection"]["ForegroundNormal"].name().lower() == want


# ---- files ----------------------------------------------------------------------------------------


def test_a_theme_file_that_is_missing_or_too_large_says_which(tmp_path):
    with pytest.raises(ThemeError) as missing:
        Theme.load(tmp_path / "nothing.toml")
    assert "does not exist" in str(missing.value.problems[0])
    big = tmp_path / "big.toml"
    with open(big, "wb") as handle:
        handle.truncate(2_000_000)  # sparse: nothing is written
    with pytest.raises(ThemeError) as large:
        Theme.load(big)
    assert "too large" in str(large.value.problems[0])
    with pytest.raises(ThemeError) as folder:
        Theme.load(tmp_path)
    assert "regular file" in str(folder.value.problems[0])


def test_a_theme_that_does_not_follow_the_wallpaper_does_not_say_so_in_its_file():
    assert "accent_from_wallpaper" not in Theme().to_toml()
    on = Theme({("colors", "accent_from_wallpaper"): True})
    assert "accent_from_wallpaper = true" in on.to_toml()
    assert Theme.from_toml(on.to_toml()) == on


def test_a_huge_configuration_file_is_read_as_if_it_were_not_there(home):
    paths.config_home().mkdir(parents=True, exist_ok=True)
    big = paths.config_home() / "kdeglobals"
    with open(big, "wb") as handle:
        handle.write(b"[General]\nColorScheme=Big\n")
        handle.truncate(kconfig.MAX_READ + 10)  # sparse
    assert kconfig.user_value("kdeglobals", ["General"], "ColorScheme") is None
    big.write_text("[General]\nColorScheme=Small\n")
    assert kconfig.user_value("kdeglobals", ["General"], "ColorScheme") == "Small"
