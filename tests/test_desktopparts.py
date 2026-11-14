# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The parts of the desktop that are chosen from what is installed, against stand-ins for the KDE tools."""

import pytest

from conftest import FakeRunner
from plasma_theme_studio import desktopparts as dp
from plasma_theme_studio import kconfig, paths
from plasma_theme_studio.apply import desktop
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.generators import ApplyError
from plasma_theme_studio.generators import windowframe as wf

ICONS_TOOL = "/usr/lib/plasma-changeicons"
KWINRC = ("kwinrc", ("org.kde.kdecoration2"))


class DesktopRunner(FakeRunner):
    """FakeRunner that keeps every configuration file, kdeglobals too, as a real file, and a
    desktop behind the tools: KDE's own tools, KWin's report, the D-Bus senders."""

    def __init__(self):
        super().__init__()
        self.signals = []
        self.tool_effect = True  # False: the tools exit with 0 and change nothing
        self.themes = {
            "plasma-apply-desktoptheme": ("plasmarc", ["Theme"], "name"),
            "plasma-apply-cursortheme": ("kcminputrc", ["Mouse"], "cursorTheme"),
            ICONS_TOOL: ("kdeglobals", ["Icons"], "Theme"),
        }
        for tool in self.themes:
            self.handlers[tool] = self._theme_tool
        self.handlers["plasma-apply-colorscheme"] = self._colorscheme
        self.handlers["dbus-send"] = self._signal
        self.handlers["busctl"] = self._signal
        self.handlers["qdbus6"] = self._kwin

    def _config(self, argv):
        file, key, default, delete, groups, values = "kdeglobals", "", "", False, [], []
        arguments = iter(argv[1:])
        for argument in arguments:
            if argument == "--file":
                file = next(arguments)
            elif argument == "--group":
                groups.append(next(arguments))
            elif argument == "--key":
                key = next(arguments)
            elif argument == "--default":
                default = next(arguments)
            elif argument == "--delete":
                delete = True
            elif argument == "--":
                values = list(arguments)
            elif argument != "--notify":
                values.append(argument)
        location = tuple(groups)
        path = paths.config_home() / file
        stored = kconfig.parse(path.read_text()) if path.exists() else {}
        hidden = key + kconfig.MASK
        if argv[0] == "kreadconfig6":
            value = stored.get(location, {}).get(key)
            if value is None and hidden in stored.get(location, {}):
                value = default
            elif value is None:
                value = self.defaults.get((file, location, key), default)
            return Result(0, value + "\n")
        if delete:
            stored.get(location, {}).pop(key, None)
            if (file, location, key) in self.defaults:
                stored.setdefault(location, {})[hidden] = ""
        else:
            stored.setdefault(location, {}).pop(hidden, None)
            stored.setdefault(location, {})[key] = values[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        from conftest import _config_text

        path.write_text(_config_text(stored))
        return Result(0)

    def set(self, file, groups, key, value):
        self._config(
            [
                "kwriteconfig6",
                "--file",
                file,
                *[a for g in groups for a in ("--group", g)],
                "--key",
                key,
                "--",
                value,
            ]
        )

    def get(self, file, groups, key):
        return self._config(
            ["kreadconfig6", "--file", file, *[a for g in groups for a in ("--group", g)], "--key", key]
        ).stdout.strip()

    def _theme_tool(self, argv):
        if self.tool_effect:
            file, groups, key = self.themes[argv[0]]
            self.set(file, groups, key, argv[1])
        return Result(0, "done\n")

    def _colorscheme(self, argv):
        """Applies a scheme as KDE's tool does: the colors in use get the accent."""
        if "--accent-color" in argv:
            focus = ",".join(str(int(argv[-1][n : n + 2], 16)) for n in (1, 3, 5))
        else:
            focus = self.get("kdeglobals", ["General"], "AccentColor") or "61,174,233"
            self.set("kdeglobals", ["General"], "ColorScheme", argv[1])
        if self.tool_effect:
            self.set("kdeglobals", ["Colors:Button"], "DecorationFocus", focus)
        return Result(0)

    def _signal(self, argv):
        self.signals.append(argv)
        return Result(0)

    def _kwin(self, argv):
        if argv[3:] == ["reconfigure"]:
            return Result(0)
        group = ["org.kde.kdecoration2"]
        sizes = [key for key, _name in dp.BORDER_SIZES]
        size = self.get("kwinrc", group, "BorderSize") or "Normal"
        left = self.get("kwinrc", group, "ButtonsOnLeft")
        right = self.get("kwinrc", group, "ButtonsOnRight")
        report = [
            "Decoration",
            "==========",
            f"Plugin: {self.get('kwinrc', group, 'library') or 'org.kde.breeze'}",
            f"Theme: {self.get('kwinrc', group, 'theme') or 'Breeze'}",
            f"decorationButtonsLeft: {dp._kwin_numbers(left)}",
            f"decorationButtonsRight: {dp._kwin_numbers(right)}",
            f"borderSize: {sizes.index(size)}",
            "",
        ]
        return Result(0, "\n".join(report))


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(wf, "_pause", lambda seconds: None)
    monkeypatch.setattr(desktop, "pause", lambda seconds: None)
    keys = ["Breeze", "Union", "Oxygen", "kvantum-dark", "kvantum", "Windows", "Fusion"]
    monkeypatch.setattr(dp.AppStyle, "_qt_keys", staticmethod(lambda: keys))


@pytest.fixture
def runner(home):
    runner = DesktopRunner()
    data = home / "system/share"
    for name in ("breeze-dark", "My Theme"):
        (data / "plasma/desktoptheme" / name).mkdir(parents=True)
        (data / "plasma/desktoptheme" / name / "metadata.json").write_text("{}")
    for name in ("Papirus", "breeze"):
        (data / "icons" / name).mkdir(parents=True)
        (data / "icons" / name / "index.theme").write_text("[Icon Theme]\nDirectories=16x16\n")
    (data / "icons/Hidden").mkdir()
    (data / "icons/Hidden/index.theme").write_text("[Icon Theme]\nDirectories=16x16\nHidden=true\n")
    for name in ("Pop", "Qogir Dark"):
        (data / "icons" / name / "cursors").mkdir(parents=True)
    for name in ("oxygen", "ocean"):
        (data / "sounds" / name).mkdir(parents=True)
        (data / "sounds" / name / "index.theme").write_text("[Sound Theme]\n")
    (data / "plasma/look-and-feel/org.kde.breeze.desktop/contents/splash").mkdir(parents=True)
    (data / "plasma/look-and-feel/org.kde.nosplash/contents").mkdir(parents=True)
    (data / "kstyle/themes").mkdir(parents=True)
    (data / "kstyle/themes/union.themerc").write_text("[KDE]\nWidgetStyle=Union\n")
    (data / "union/styles/breeze").mkdir(parents=True)
    return runner


def tools(runner):
    """The calls that are not reads of the settings."""
    return [call for call in runner.calls if call[0] not in ("kreadconfig6",)]


def files(home):
    """Every configuration file. KConfig keeps the keys of a group in order of their names, the stand-in in
    order of writing, so the lines of a group are compared sorted."""
    base = paths.config_home()
    result = {}
    for path in sorted(base.rglob("*")):
        if path.is_file():
            blocks = path.read_text().split("\n\n")
            result[str(path.relative_to(base))] = [sorted(block.splitlines()) for block in blocks]
    return result


# part key -> (value to apply, a value the part starts from)
SAMPLES = {
    "plasma_style": ("breeze-dark", "My Theme"),
    "app_style": ("fusion", "Breeze"),
    "decoration": (f"{wf.AURORAE_LIBRARY}:{wf.AURORAE_THEME_PREFIX}Foo", "org.kde.breeze:Breeze"),
    "border_size": ("Large", "Tiny"),
    "titlebar_buttons": ({"left": "MN", "right": "IAX"}, {"left": "M", "right": "X"}),
    "icons": ("Papirus", "breeze"),
    "cursor_theme": ("Pop", "Qogir Dark"),
    "cursor_size": (48, 32),
    "fonts": (
        {
            "font": "Noto Sans,11,-1,5,400,0,0,0,0,0,0,0,0,0,0,1",
            "title": "Noto Sans,10,-1,5,700,0,0,0,0,0,0,0,0,0,0,1",
        },
        {"font": "Sans,9,-1,5,400,0,0,0,0,0,0,0,0,0,0,1", "title": "Sans,9,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"},
    ),
    "sounds": ({"theme": "oxygen", "enabled": False}, {"theme": "ocean", "enabled": True}),
    "splash": ("None", "org.kde.breeze.desktop"),
    "accent": ("#336699", "#aa0000"),
}


def start_state(runner, part, state):
    """Bring the settings of a part into one of the states a user's files can be in."""
    if state == "user":
        for name, setting in part.settings.items():
            runner.set(*setting, "x" if name in ("auto",) else "Tiny" if name == "size" else "")
    elif state in ("layer", "masked"):
        for setting in part.settings.values():
            runner.defaults[(setting[0], tuple(setting[1]), setting[2])] = (
                "1,2,3" if setting[2] == "AccentColor" else "Tiny"
            )
        if state == "masked":
            for setting in part.settings.values():
                runner._config(
                    [
                        "kwriteconfig6",
                        "--file",
                        setting[0],
                        *[a for g in setting[1] for a in ("--group", g)],
                        "--key",
                        setting[2],
                        "--delete",
                    ]
                )


def test_every_part_is_registered_with_the_same_interface():
    assert set(SAMPLES) | {"global_theme"} == set(dp.PARTS)
    for key, part in dp.PARTS.items():
        assert part.key == key
        for method in ("current", "capture", "restore", "apply", "available"):
            assert callable(getattr(part, method))


@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_apply_reads_back(key, runner):
    value, _start = SAMPLES[key]
    part = dp.PARTS[key]
    assert part.available(runner) is None
    part.apply(value, runner)
    now = part.current(runner)
    if key == "app_style":
        assert now.lower() == value
    elif key == "border_size" or key in (
        "cursor_size",
        "icons",
        "cursor_theme",
        "plasma_style",
        "splash",
        "accent",
    ):
        assert now == value
    elif key == "decoration":
        assert now == value
    elif key == "sounds":
        assert now == value
    elif key == "titlebar_buttons":
        assert now == value
    elif key == "fonts":
        assert {role: now[role] for role in value} == value


@pytest.mark.parametrize("state", ["empty", "user", "layer", "masked"])
@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_capture_apply_restore_gives_the_same_files(key, state, runner, home):
    part = dp.PARTS[key]
    value, _start = SAMPLES[key]
    start_state(runner, part, state)
    runner.run(["plasma-apply-colorscheme", "BreezeLight"])  # the colors in use carry the accent
    before = files(home)
    effective = part.current(runner)
    captured = part.capture(runner)
    assert captured["effective"] == effective
    import json

    captured = json.loads(json.dumps(captured))
    part.apply(value, runner)
    assert files(home) != before
    part.restore(captured, runner)
    assert files(home) == before
    assert part.current(runner) == effective


def test_restore_makes_the_old_value_live_before_the_exact_state(runner):
    part = dp.PARTS["plasma_style"]
    runner.defaults[("plasmarc", ("Theme",), "name")] = "breeze-dark"
    captured = part.capture(runner)
    part.apply("My Theme", runner)
    runner.calls.clear()
    part.restore(captured, runner)
    assert ["plasma-apply-desktoptheme", "breeze-dark"] in runner.calls


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("plasma_style", "breeze-dark"),
        ("cursor_theme", "Pop"),
        ("icons", "Papirus"),
    ],
)
def test_a_tool_that_exits_with_zero_and_changes_nothing_is_an_error(key, value, runner):
    runner.tool_effect = False
    with pytest.raises(ApplyError) as error:
        dp.PARTS[key].apply(value, runner)
    assert "did not accept" in str(error.value)


def test_a_failing_tool_message_carries_the_tools_text(runner):
    runner.handlers["plasma-apply-desktoptheme"] = lambda argv: Result(255, "Could not find theme\n")
    with pytest.raises(ApplyError, match="Could not find theme"):
        dp.PARTS["plasma_style"].apply("breeze-dark", runner)


def test_config_that_does_not_stick_is_an_error(runner):
    runner.handlers["kwriteconfig6"] = lambda argv: Result(0)  # exits with 0, writes nothing
    with pytest.raises(ApplyError):
        dp.PARTS["app_style"].apply("fusion", runner)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("plasma_style", "nonexistent"),
        ("plasma_style", "--list-themes"),
        ("plasma_style", ""),
        ("plasma_style", "two\nlines"),
        ("plasma_style", None),
        ("app_style", "nonexistent"),
        ("app_style", "fusion/breeze"),
        ("app_style", "union/nonexistent"),
        ("icons", "Hidden"),
        ("icons", "nonexistent"),
        ("cursor_theme", "Papirus"),
        ("cursor_size", 0),
        ("cursor_size", "48"),
        ("cursor_size", True),
        ("sounds", {"theme": "nonexistent"}),
        ("sounds", {"enabled": "yes"}),
        ("sounds", {}),
        ("splash", "org.kde.nosplash"),
        ("fonts", {"font": "not a font"}),
        ("fonts", {"nothing": "Sans,10"}),
        ("titlebar_buttons", {"left": "Q"}),
        ("titlebar_buttons", {"left": "MM"}),
        ("titlebar_buttons", {"middle": "M"}),
        ("border_size", "Gigantic"),
        ("decoration", "org.kde.breeze"),
        ("decoration", "bad library:Breeze"),
        ("accent", "red"),
        ("accent", "#12345"),
        ("accent", "1,2,300"),
    ],
)
def test_an_unknown_or_odd_value_is_rejected_before_any_tool_runs(key, value, runner):
    with pytest.raises(ApplyError):
        dp.PARTS[key].apply(value, runner)
    assert tools(runner) == []


def test_names_with_spaces_reach_the_tool_as_one_argument(runner):
    dp.PARTS["plasma_style"].apply("My Theme", runner)
    assert ["plasma-apply-desktoptheme", "My Theme"] in runner.calls
    dp.PARTS["cursor_theme"].apply("Qogir Dark", runner)
    assert ["plasma-apply-cursortheme", "Qogir Dark"] in runner.calls
    assert dp.PARTS["cursor_theme"].current(runner) == "Qogir Dark"


def test_border_size_none_leaves_the_setting_alone(runner):
    part = dp.PARTS["border_size"]
    part.apply(None, runner)
    assert runner.calls == []
    assert part.current(runner) is None
    part.apply("Huge", runner)
    assert runner.get(*KWINRC[:1], ["org.kde.kdecoration2"], "BorderSizeAuto") == "false"
    assert part.current(runner) == "Huge"


def test_border_choices_are_translated_names_of_the_keys_kwin_knows():
    keys = [key for key, _name in dp.BORDER_SIZES]
    assert keys == [
        "None",
        "NoSides",
        "Tiny",
        "Normal",
        "Large",
        "VeryLarge",
        "Huge",
        "VeryHuge",
        "Oversized",
    ]
    assert all(str(name) for _key, name in dp.BORDER_SIZES)


def test_kwin_that_keeps_the_old_value_is_an_error(runner):
    runner.handlers["qdbus6"] = lambda argv: Result(
        0, "" if argv[3] == "reconfigure" else "Decoration\n==========\nborderSize: 3\n\n"
    )
    with pytest.raises(ApplyError, match="KWin did not take"):
        dp.PARTS["border_size"].apply("Large", runner)


def test_a_decoration_kwin_did_not_load_is_an_error(runner):
    runner.handlers["qdbus6"] = lambda argv: Result(
        0,
        ""
        if argv[3] == "reconfigure"
        else "Decoration\n==========\nPlugin: org.kde.breeze\nTheme: Breeze\n\n",
    )
    with pytest.raises(ApplyError, match="did not switch"):
        dp.PARTS["decoration"].apply(f"{wf.AURORAE_LIBRARY}:{wf.AURORAE_THEME_PREFIX}Foo", runner)


def test_decoration_uses_busctl_without_qdbus6(runner):
    runner.missing.add("qdbus6")
    runner.handlers["busctl"] = lambda argv: Result(0)
    dp.PARTS["decoration"].apply("org.kde.breeze:Breeze", runner)
    assert any(call[:2] == ["busctl", "--user"] and "reconfigure" in call for call in runner.calls)


def test_decoration_current_is_breeze_when_nothing_is_set(runner):
    assert dp.PARTS["decoration"].current(runner) == "org.kde.breeze:Breeze"


def test_decoration_restore_with_kwin_gone_still_puts_the_settings_back(runner, home):
    part = dp.PARTS["decoration"]
    before = files(home)
    captured = part.capture(runner)
    part.apply("org.kde.breeze:Other", runner)
    runner.handlers["qdbus6"] = lambda argv: Result(1, "", "no such service")
    runner.missing.add("busctl")
    part.restore(captured, runner)
    assert files(home) == before


def test_title_bar_buttons_may_be_empty_and_default_to_kwins(runner):
    part = dp.PARTS["titlebar_buttons"]
    assert part.current(runner) == {"left": "MSE", "right": "HIAX"}
    part.apply({"left": ""}, runner)
    assert part.current(runner) == {"left": "", "right": "HIAX"}


def test_button_letters_are_explained_and_checked():
    names = dp.button_names()
    assert set(names) == set("MNSHIAXFBLE_")
    assert [str(n) for n in dp.describe_buttons("MSX")] == ["Window menu", "On all desktops", "Close"]
    assert dp.parse_buttons("M_S_X") == list("M_S_X")
    assert dp.parse_buttons("MM") is None
    assert dp.parse_buttons("MQ") is None
    assert dp.parse_buttons("") == []
    assert dp._kwin_numbers("MSEHIAX") == "0, 2, 12, 6, 3, 4, 5"  # as KWin 6.8 reports the defaults


def test_icons_use_the_tool_after_checking_the_name_and_send_the_signal(runner):
    dp.PARTS["icons"].apply("Papirus", runner)
    assert [ICONS_TOOL, "Papirus"] in runner.calls
    assert len([s for s in runner.signals if "iconChanged" in " ".join(s)]) == 6
    assert sorted(dp.PARTS["icons"].installed()) == ["Papirus", "breeze"]


def test_icons_without_the_tool_are_unavailable(runner):
    runner.missing.update(dp.Icons.TOOLS)
    assert dp.PARTS["icons"].available(runner) is not None
    with pytest.raises(ApplyError, match="plasma-changeicons"):
        dp.PARTS["icons"].apply("Papirus", runner)


@pytest.mark.parametrize(
    ("key", "tool"),
    [
        ("plasma_style", "plasma-apply-desktoptheme"),
        ("cursor_theme", "plasma-apply-cursortheme"),
        ("accent", "plasma-apply-colorscheme"),
        ("fonts", "kwriteconfig6"),
        ("splash", "kreadconfig6"),
    ],
)
def test_a_missing_tool_makes_the_part_unavailable_with_a_reason(key, tool, runner):
    runner.missing.add(tool)
    reason = dp.PARTS[key].available(runner)
    assert tool in str(reason)


def test_a_missing_tool_makes_apply_fail_plainly(runner):
    runner.missing.add("plasma-apply-desktoptheme")
    with pytest.raises(ApplyError):
        dp.PARTS["plasma_style"].apply("breeze-dark", runner)


def test_cursor_size_signals_the_pointer_change(runner):
    dp.PARTS["cursor_size"].apply(48, runner)
    assert any(
        "notifyChange" in " ".join(call) and "5" in call[-2:] or "int32:5" in call for call in runner.signals
    )
    assert dp.PARTS["cursor_size"].current(runner) == 48


def test_app_style_writes_the_union_style_too_and_signals(runner):
    part = dp.PARTS["app_style"]
    part.apply("union/breeze", runner)
    assert runner.get("kdeglobals", ["KDE"], "widgetStyle") == "Union"
    assert runner.get("kdeglobals", ["KDE"], "unionStyle") == "breeze"
    assert part.current(runner) == "union/breeze"
    assert any("--notify" in call for call in runner.calls)
    assert any("int32:2" in call for call in runner.signals)
    part.apply("fusion", runner)
    assert part.current(runner) == "Fusion"  # the spelling the page writes


def test_fonts_signal_fonts_and_reconfigure_kwin_for_the_title_font(runner):
    part = dp.PARTS["fonts"]
    runner.calls.clear()
    part.apply({"menu": "Sans,9,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"}, runner)
    assert not any(call[0] == "qdbus6" for call in runner.calls)
    assert any("refreshFonts" in " ".join(call) for call in runner.signals)
    part.apply({"title": "Sans,9,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"}, runner)
    assert ["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"] in runner.calls
    assert runner.get("kdeglobals", ["WM"], "activeFont").startswith("Sans,9")


def test_fonts_with_nothing_set_are_none(runner):
    assert dp.PARTS["fonts"].current(runner) is None


def test_font_description_round_trip():
    spec = dp.FontSpec.parse("Noto Sans,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1")
    assert spec == dp.FontSpec("Noto Sans", 10.0)
    assert spec.text() == "Noto Sans,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"
    assert spec.label() == "Noto Sans, 10 pt"
    bold = dp.FontSpec.parse("Fira Sans,10.5,-1,5,700,1,0,0,0,0,0,0,0,0,0,1")
    assert bold == dp.FontSpec("Fira Sans", 10.5, 700, True)
    assert bold.label() == "Fira Sans, 10.5 pt, Bold, Italic"
    assert dp.FontSpec.parse(bold.text()) == bold
    assert dp.FontSpec.parse("Noto Sans,10,-1,5,50,0,0,0,0,0").weight == 400  # Qt 5 weights
    assert dp.FontSpec.parse("Noto Sans,10,-1,5,75,0,0,0,0,0").weight == 700
    assert dp.FontSpec.parse("Noto Sans,10").weight == 400
    for bad in ("", "Noto Sans", "Noto Sans,x", ",10", "Noto Sans,0", "Noto Sans,10,-1,5,abc"):
        assert dp.FontSpec.parse(bad) is None


def test_font_spec_agrees_with_qt(app):
    from PySide6.QtGui import QFont

    font = QFont()
    assert font.fromString(dp.FontSpec("Noto Sans", 11, 700, True).text())
    assert (font.pointSizeF(), font.weight().value, font.italic()) == (11.0, 700, True)


def test_sounds_default_to_ocean_and_on(runner):
    assert dp.PARTS["sounds"].current(runner) == {"theme": "ocean", "enabled": True}


def test_splash_none_writes_the_engine_kde_expects(runner):
    part = dp.PARTS["splash"]
    part.apply("None", runner)
    assert runner.get("ksplashrc", ["KSplash"], "Engine") == "none"
    assert runner.get("ksplashrc", ["KSplash"], "Theme") == "None"
    assert part.current(runner) == "None"
    part.apply("org.kde.breeze.desktop", runner)
    assert runner.get("ksplashrc", ["KSplash"], "Engine") == "KSplashQML"
    assert part.installed() == ["None", "org.kde.breeze.desktop"]


def test_accent_modes_and_clear(runner):
    part = dp.PARTS["accent"]
    runner.run(["plasma-apply-colorscheme", "BreezeLight"])
    assert part.current(runner) is None
    part.apply("51,102,153", runner)
    assert part.current(runner) == "#336699"
    assert runner.get("kdeglobals", ["General"], "LastUsedCustomAccentColor") == "51,102,153"
    assert ["plasma-apply-colorscheme", "BreezeLight", "--accent-color", "#336699"] in runner.calls
    part.apply("wallpaper", runner)
    assert part.current(runner) == "wallpaper"
    part.clear(runner)
    assert part.current(runner) is None
    assert runner.get("kdeglobals", ["General"], "AccentColor") == ""
    assert runner.get("kdeglobals", ["General"], "ColorScheme") == "BreezeLight"


def test_accent_clear_that_loses_the_scheme_is_an_error(runner):
    runner.set("kdeglobals", ["General"], "ColorScheme", "BreezeLight")
    runner.handlers["plasma-apply-colorscheme"] = lambda argv: Result(0)
    with pytest.raises(ApplyError):
        dp.PARTS["accent"].clear(runner)
    assert runner.get("kdeglobals", ["General"], "ColorScheme") == "BreezeLight"


def test_accent_that_does_not_reach_the_colors_is_an_error(runner):
    runner.run(["plasma-apply-colorscheme", "BreezeLight"])
    runner.tool_effect = False
    with pytest.raises(ApplyError, match="did not accept"):
        dp.PARTS["accent"].apply("#336699", runner)


def test_global_theme_is_read_only(runner):
    part = dp.PARTS["global_theme"]
    assert part.current(runner) is None
    runner.set("kdeglobals", ["KDE"], "LookAndFeelPackage", "org.kde.breezedark.desktop")
    assert part.current(runner) == "org.kde.breezedark.desktop"
    with pytest.raises(ApplyError):
        part.apply("org.kde.breeze.desktop", runner)
    assert part.capture(runner)["effective"] == "org.kde.breezedark.desktop"
    part.restore(part.capture(runner), runner)


def test_open_system_settings_prefers_systemsettings(runner, monkeypatch):
    started = []
    monkeypatch.setattr(dp, "_launch", started.append)
    assert dp.open_system_settings("kcm_sddm", runner) is None
    assert started == [["systemsettings", "kcm_sddm"]]
    runner.missing.add("systemsettings")
    assert dp.open_system_settings("kcm_fonts", runner) is None
    assert started[-1] == ["kcmshell6", "kcm_fonts"]
    runner.missing.add("kcmshell6")
    assert "System Settings" in str(dp.open_system_settings("kcm_fonts", runner))
    assert len(started) == 2


def test_open_system_settings_refuses_other_ids_and_survives_a_failing_start(runner, monkeypatch):
    started = []
    monkeypatch.setattr(dp, "_launch", started.append)
    assert dp.open_system_settings("../evil --flag", runner) is not None
    assert started == []

    def fail(argv):
        raise OSError("no")

    monkeypatch.setattr(dp, "_launch", fail)
    assert "could not be started" in str(dp.open_system_settings("kcm_colors", runner))


def test_the_module_ids_cover_the_pages_of_colors_and_themes():
    assert {"kcm_lookandfeel", "kcm_colors", "kcm_style", "kcm_desktoptheme", "kcm_kwindecoration"} <= set(
        dp.MODULES
    )
    assert {
        "kcm_icons",
        "kcm_cursortheme",
        "kcm_fonts",
        "kcm_splashscreen",
        "kcm_soundtheme",
        "kcm_sddm",
    } <= set(dp.MODULES)


def test_notify_change_uses_dbus_send_then_busctl(runner):
    assert desktop.notify_change(runner, 2).returncode == 0
    assert runner.signals[-1] == [
        "dbus-send",
        "--session",
        "--type=signal",
        "/KGlobalSettings",
        "org.kde.KGlobalSettings.notifyChange",
        "int32:2",
        "int32:0",
    ]
    runner.missing.add("dbus-send")
    desktop.notify_change(runner, 5)
    assert runner.signals[-1][:3] == ["busctl", "--user", "emit"]
    assert runner.signals[-1][-3:] == ["ii", "5", "0"]


def test_restore_removes_a_file_the_tool_left_bare(runner, tmp_path):
    from plasma_theme_studio import paths

    bare = paths.config_home() / "plasmarc"
    bare.parent.mkdir(parents=True, exist_ok=True)
    bare.write_text("[Theme]\n", encoding="utf-8")
    dp.PARTS["plasma_style"].restore(
        {"values": {"name": None}, "masked": [], "effective": "default", "absent": ["plasmarc"]}, runner
    )
    assert not bare.exists()


def test_app_style_knows_what_qt_can_load_and_nothing_else(runner):
    part = dp.PARTS["app_style"]
    assert "kvantum-dark" in part.installed()
    part.apply("kvantum-dark", runner)
    for gone in ("Motif", "CDE", "Plastique", "Gtk+"):
        with pytest.raises(ApplyError):
            part.apply(gone, runner)


def test_launch_uses_no_preexec_function(monkeypatch):
    calls = []
    monkeypatch.setattr(dp.subprocess, "Popen", lambda argv, **kw: calls.append((argv, kw)))
    monkeypatch.setattr(dp.shutil, "which", lambda name: "/usr/bin/prlimit")
    dp._launch(["systemsettings", "kcm_fonts"])
    argv, kw = calls[0]
    assert argv[:3] == ["/usr/bin/prlimit", "--core=0:0", "--"] and argv[3:] == [
        "systemsettings",
        "kcm_fonts",
    ]
    assert "preexec_fn" not in kw
