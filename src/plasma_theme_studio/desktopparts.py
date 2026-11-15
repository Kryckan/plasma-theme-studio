# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The parts of the desktop that are chosen from what is installed: Plasma style,
widget style, window decoration, border size, title bar buttons, icons, pointer,
fonts, sounds, splash screen and the accent color.

Every part is a small class with the same interface (see `Part`) and is found
by its `key` in `PARTS`. The KDE tools exit with 0 even when they changed
nothing, so every `apply` reads the setting back and raises an `ApplyError`
with a plain message when the desktop did not take the value.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import kconfig, paths
from .apply import desktop
from .generators.base import ApplyError
from .generators.colorscheme import FALLBACK_SCHEME, RELOAD_PLACEHOLDER, activate_scheme
from .generators.windowframe import (
    AURORAE_LIBRARY,
    AURORAE_THEME_PREFIX,
    BREEZE_LIBRARY,
    BREEZE_THEME,
    _check_decoration,
    _decoration_report,
    _kwin_answers,
    _reconfigure,
)
from .messages import Msg, translate
from .model.parts import (  # noqa: F401 - the names are part of this module's interface
    BORDER_SIZES,
    BUTTONS,
    DEFAULT_BUTTONS,
    FONT_WEIGHTS,
    FontSpec,
    button_names,
    describe_buttons,
    parse_buttons,
    weight_name,
)

Setting = tuple[str, list[str], str]  # file, groups, key


def _error(template: str, **args) -> ApplyError:
    return ApplyError(translate("core", template).format(**args))


def _check_text(value, what: str) -> str:
    """A name or value that is safe to hand to a tool: one line of text that no tool can read as an
    option."""
    if (
        not isinstance(value, str)
        or value.lstrip().startswith("-")
        or not value.strip()
        or len(value) > 300
        or re.search(r"[\x00-\x1f]", value)
    ):
        raise _error("{what} is not a valid name.", what=what)
    return value


def _folders(*subs: str) -> list[Path]:
    """Where installed things live: the user's folder, then the system's."""
    return [base / sub for base in (paths.data_home(), *paths.system_data_dirs()) for sub in subs]


def _icon_folders() -> list[Path]:
    return [
        paths.data_home() / "icons",
        Path.home() / ".icons",
        *(d / "icons" for d in paths.system_data_dirs()),
    ]


def _children(folders: list[Path], wanted) -> list[str]:
    """Names of the sub-folders for which `wanted(path)` holds, first folder wins."""
    names: dict[str, None] = {}
    for folder in folders:
        try:
            entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for entry in entries:
            if entry.name not in names and entry.is_dir() and wanted(entry):
                names[entry.name] = None
    return list(names)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _emit(runner, path: str, interface: str, member: str, *integers: int) -> None:
    """Send a D-Bus signal to the session. A signal that cannot be sent is not an error:
    the setting itself is changed and applications read it when they start."""
    if runner.which("dbus-send"):
        argv = ["dbus-send", "--session", "--type=signal", path, f"{interface}.{member}"]
        argv += [f"int32:{number}" for number in integers]
    else:
        argv = ["busctl", "--user", "emit", path, interface, member]
        argv += (["i" * len(integers), *map(str, integers)]) if integers else []
    try:
        runner.run(argv)
    except Exception:  # noqa: S110 - see above
        pass


def _drop_if_bare(file: str) -> None:
    """A KDE tool that sets a value which is the default leaves its group header and nothing else
    in a file it created. That file did not exist before, so it goes (a link is the user's own)."""
    path = paths.config_home() / file
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        if not path.is_symlink() and all(not line or line.startswith("[") for line in lines):
            path.unlink()
    except (OSError, UnicodeDecodeError):
        pass


class Part:
    """One part of the desktop.

    `current` is the value the desktop uses now, in the id form of the part, or None.
    `capture` returns what `restore` needs to put the settings back exactly: the
    user's own value of every key, which keys hide a default of Plasma's own layer,
    and the value in use. `apply` changes the part and raises `ApplyError` when it did not take.
    `available` is None, or the reason why the part cannot be changed here.
    """

    key = ""
    title: Msg
    settings: dict[str, Setting] = {}
    tools: tuple[str, ...] = ()  # programs that must be there besides the KDE config tools
    notify = False  # write with kwriteconfig6 --notify

    def available(self, runner) -> Msg | None:
        for tool in ("kreadconfig6", "kwriteconfig6", *self.tools):
            if not runner.which(tool):
                return translate("core", "{tool} is not installed.").format(tool=tool)
        return None

    def current(self, runner):
        raise NotImplementedError

    def validate(self, value) -> None:
        """Raise an `ApplyError` that names the thing when `value` cannot be applied: it is not a
        proper name or it is not installed. Reads the installed things, changes nothing."""

    def apply(self, value, runner) -> None:
        raise NotImplementedError

    def capture(self, runner) -> dict:
        return {
            "values": {name: kconfig.user_value(*setting) for name, setting in self.settings.items()},
            "masked": [name for name, setting in self.settings.items() if kconfig.masked(*setting)],
            "effective": self.current(runner),
            "absent": sorted(
                {file for file, *_ in self.settings.values() if not (paths.config_home() / file).exists()}
            ),
        }

    def restore(self, captured: dict, runner) -> None:
        values, masked = captured.get("values") or {}, captured.get("masked") or ()
        self._restore_live(captured.get("effective"), runner)
        failure = None
        for name, setting in self.settings.items():
            if name not in values:
                continue
            try:
                # Notified, so that programs that keep the file open (the GTK sync of KDE) see it go back.
                kconfig.write_value(runner, *setting, values[name], masked=name in masked, notify=True)
            except ApplyError as error:
                failure = failure or error
        for file in captured.get("absent") or ():
            if file in {setting[0] for setting in self.settings.values()}:
                _drop_if_bare(file)
        try:
            self._refresh(runner, restoring=True)
        except ApplyError as error:
            failure = failure or error
        if failure:
            raise failure

    # What a part adds to the common flow.
    def _restore_live(self, effective, runner) -> None:
        """Make the old value live, for the parts that are changed by a tool of KDE."""

    def _refresh(self, runner, restoring: bool = False) -> None:
        """Tell the desktop that the settings changed."""

    def _get(self, runner, name: str, default: str = "") -> str:
        return kconfig.effective_value(runner, *self.settings[name], default)

    def _put(self, runner, name: str, value: str | None) -> None:
        """Write one setting and read it back."""
        file, groups, key = self.settings[name]
        if value is None or not self.notify:
            kconfig.write_value(runner, file, groups, key, value, notify=self.notify)
            return
        argv = ["kwriteconfig6", "--notify", "--file", file]
        for group in groups:
            argv += ["--group", group]
        result = runner.run([*argv, "--key", key, "--", value])
        if result.returncode != 0 or kconfig.effective_value(runner, file, groups, key) != value.strip():
            detail = (result.output.splitlines() or [""])[0][:200]
            raise _error("Could not change {key} in {file}. {detail}", key=key, file=file, detail=detail)

    def _tool_failed(self, what: str, result) -> ApplyError:
        detail = (result.output.splitlines() or [""])[0][:200]
        return _error("The desktop did not accept {what}. {detail}", what=what, detail=detail)


class _ByTool(Part):
    """A part that KDE changes with a tool of its own and that is chosen from a list of installed names."""

    what: Msg

    def installed(self) -> list[str]:
        raise NotImplementedError

    def _name(self, value) -> str:
        _check_text(value, str(self.what))
        if value not in self.installed():
            raise _error("{what} {name} is not installed.", what=str(self.what), name=value)
        return value

    def validate(self, value) -> None:
        self._name(value)

    def _restore_live(self, effective, runner) -> None:
        if effective and effective != self.current(runner):
            try:
                self.apply(effective, runner)
            except ApplyError:
                pass  # the exact values are written next, which is all that undo needs


class PlasmaStyle(_ByTool):
    key = "plasma_style"
    title = translate("core", "Plasma style")
    what = translate("core", "The Plasma style")
    settings = {"name": ("plasmarc", ["Theme"], "name")}
    tools = ("plasma-apply-desktoptheme",)

    def installed(self) -> list[str]:
        return _children(
            _folders("plasma/desktoptheme"),
            lambda p: (p / "metadata.json").is_file() or (p / "metadata.desktop").is_file(),
        )

    def current(self, runner) -> str | None:
        return self._get(runner, "name", "default") or None

    def apply(self, value, runner) -> None:
        name = self._name(value)
        result = runner.run(["plasma-apply-desktoptheme", name])
        if self.current(runner) != name:
            raise self._tool_failed(name, result)


class AppStyle(Part):
    """The widget style. `union/<name>` is the Union style with one of its own styles."""

    key = "app_style"
    title = translate("core", "Application style")
    settings = {
        "style": ("kdeglobals", ["KDE"], "widgetStyle"),
        "union": ("kdeglobals", ["KDE"], "unionStyle"),
    }
    notify = True
    BUILT_IN = ("fusion", "windows")
    DEFAULT_UNION = "breeze"

    @staticmethod
    def _qt_keys() -> list[str]:
        """The widget styles Qt can create, in the spelling the System Settings page writes."""
        try:
            from PySide6.QtWidgets import QStyleFactory
        except ImportError:
            return []
        return list(QStyleFactory.keys())

    def installed(self) -> list[str]:
        keys = self._qt_keys()
        if keys:
            return keys  # only what Qt can load: a themerc of a style Qt 6 lacks (CDE, Motif) is no choice
        names = list(self.BUILT_IN)
        for folder in _folders("kstyle/themes"):
            try:
                files = sorted(folder.glob("*.themerc"))
            except OSError:
                continue
            for file in files:
                found = re.search(r"^WidgetStyle=(.+)$", _read(file), re.M)
                if found and "Hidden=true" not in _read(file):
                    names.append(found[1].strip())
        for folder in self._plugin_folders():
            try:
                files = sorted(folder.glob("*.so"))
            except OSError:
                continue
            names += [self._plugin_style(file.stem) for file in files]
        first: dict[str, str] = {}  # one spelling of every style, the first
        for name in names:
            first.setdefault(name.lower(), name)
        return list(first.values())

    @staticmethod
    def _plugin_style(stem: str) -> str:
        """The name Qt knows a style plugin by: `libkvantum` is kvantum, `breeze6` breeze."""
        if stem == "UnionWidgetsStyle":
            return "union"
        return re.sub(r"6$", "", re.sub(r"^lib", "", stem))

    @staticmethod
    def _plugin_folders() -> list[Path]:
        extra = [Path(p) / "styles" for p in os.environ.get("QT_PLUGIN_PATH", "").split(":") if p]
        return [*extra, *(Path(base) / "qt6/plugins/styles" for base in ("/usr/lib", "/usr/lib64"))]

    def union_styles(self) -> list[str]:
        return _children(_folders("union/styles"), lambda p: True)

    def current(self, runner) -> str | None:
        style = self._get(runner, "style", "Breeze")
        style = {name.lower(): name for name in self.installed()}.get(style.lower(), style)
        if style.lower() == "union":
            return "union/" + (self._get(runner, "union", self.DEFAULT_UNION) or self.DEFAULT_UNION)
        return style or None

    def _split(self, value) -> tuple[str, str | None]:
        _check_text(value, str(translate("core", "The application style")))
        style, _, union = value.partition("/")
        known = {name.lower(): name for name in self.installed()}
        if style.lower() not in known:
            raise _error("The application style {name} is not installed.", name=style)
        if union and (style.lower() != "union" or union not in self.union_styles()):
            raise _error("The application style {name} is not installed.", name=value)
        return known[style.lower()], union or None

    def validate(self, value) -> None:
        self._split(value)

    def apply(self, value, runner) -> None:
        style, union = self._split(value)
        self._put(runner, "style", style)
        if style.lower() == "union" and union:
            self._put(runner, "union", union)
        self._refresh(runner)

    def _refresh(self, runner, restoring: bool = False) -> None:
        desktop.notify_change(runner, 2)


def _kwin_reload(runner, restoring: bool = False) -> None:
    """Ask KWin to read its settings. When undoing, a KWin that cannot be reached is not an
    error: the settings are back in its file, which is all it reads when it starts."""
    try:
        _reconfigure(runner)
    except ApplyError:
        if not restoring or _kwin_answers(runner):
            raise


def _kwin_says(runner, field: str, expected: str, shown) -> None:
    """Wait until KWin reports `field` with the value `expected`. Nothing is checked
    when KWin does not say. KWin applies a new setting a moment after it was asked to."""
    report: dict[str, str] = {}
    for attempt in range(10):
        report = _decoration_report(runner)
        if field not in report or report[field] == expected:
            return
        if attempt < 9:
            desktop.pause(0.3)
    raise _error(
        "KWin did not take the new {what}. It still uses {value}.", what=str(shown), value=report[field]
    )


class Decoration(Part):
    """The window decoration as `<library>:<theme>`, for example `org.kde.breeze:Breeze`."""

    key = "decoration"
    title = translate("core", "Window decorations")
    settings = {
        "library": ("kwinrc", ["org.kde.kdecoration2"], "library"),
        "theme": ("kwinrc", ["org.kde.kdecoration2"], "theme"),
    }

    def current(self, runner) -> str:
        library = self._get(runner, "library", BREEZE_LIBRARY) or BREEZE_LIBRARY
        return f"{library}:{self._get(runner, 'theme', BREEZE_THEME) or BREEZE_THEME}"

    @staticmethod
    def _items() -> list:
        """The decorations System Settings lists, as the picker has them."""
        try:
            from .pickers import kind
        except ImportError:  # no Qt: nothing is known to be installed
            return []
        picker = kind("decoration")
        return picker.items() if picker else []

    def installed(self) -> list[str]:
        return [item.id for item in self._items()]

    def _split(self, value) -> tuple[str, str]:
        what = str(translate("core", "The window decoration"))
        _check_text(value, what)
        library, _, theme = value.partition(":")
        if not library.strip() or not theme.strip() or re.search(r"\s", library):
            raise _error("{what} is not a valid name.", what=what)
        return library, theme

    def validate(self, value) -> None:
        self._split(value)
        from .pickers.globalthemes import resolve

        if resolve(value, self._items()) is None:
            raise _error(
                "{what} {name} is not installed.",
                what=str(translate("core", "The window decoration")),
                name=value,
            )

    def _canonical(self, value) -> str:
        """The id as the installed decoration spells it: validation is lenient about case and the
        old Aurorae library, but what is written must be exactly what KWin looks up."""
        from .pickers.globalthemes import resolve

        found = resolve(value, self._items()) if isinstance(value, str) else None
        return found.id if found is not None else value

    def apply(self, value, runner) -> None:
        library, theme = self._split(self._canonical(value))
        self._put(runner, "library", library)
        self._put(runner, "theme", theme)
        _kwin_reload(runner)
        folder = theme.removeprefix(AURORAE_THEME_PREFIX) if library == AURORAE_LIBRARY else None
        _check_decoration(runner, library, folder)

    def _refresh(self, runner, restoring: bool = False) -> None:
        _kwin_reload(runner, restoring)


class BorderSize(Part):
    """The window border size by its key in `BORDER_SIZES`. None means that the decoration's
    own size is used: `apply(None)` leaves the setting alone, `current` says None for it."""

    key = "border_size"
    title = translate("core", "Border size")
    settings = {
        "auto": ("kwinrc", ["org.kde.kdecoration2"], "BorderSizeAuto"),
        "size": ("kwinrc", ["org.kde.kdecoration2"], "BorderSize"),
    }

    def current(self, runner) -> str | None:
        if self._get(runner, "auto", "true").lower() != "false":
            return None
        return self._get(runner, "size", "Normal") or "Normal"

    def apply(self, value, runner) -> None:
        if value is None:
            return
        keys = [key for key, _name in BORDER_SIZES]
        if value not in keys:
            raise _error("{what} is not a valid name.", what=str(translate("core", "The border size")))
        self._put(runner, "auto", "false")
        self._put(runner, "size", value)
        _kwin_reload(runner)
        _kwin_says(runner, "borderSize", str(keys.index(value)), translate("core", "border size"))

    def _refresh(self, runner, restoring: bool = False) -> None:
        _kwin_reload(runner, restoring)


def _kwin_numbers(text: str) -> str:
    numbers = {letter: number for letter, number, _name in BUTTONS if number is not None}
    return ", ".join(str(numbers[letter]) for letter in text if letter in numbers)


class TitlebarButtons(Part):
    """The buttons of the title bar as `{"left": "MS", "right": "HIAX"}`; each side is optional on apply."""

    key = "titlebar_buttons"
    title = translate("core", "Title bar buttons")
    settings = {
        "left": ("kwinrc", ["org.kde.kdecoration2"], "ButtonsOnLeft"),
        "right": ("kwinrc", ["org.kde.kdecoration2"], "ButtonsOnRight"),
    }

    def current(self, runner) -> dict:
        return {side: self._get(runner, side, default) for side, default in DEFAULT_BUTTONS.items()}

    def apply(self, value, runner) -> None:
        if not isinstance(value, dict) or not set(value) <= {"left", "right"}:
            raise _error("{what} is not a valid name.", what=str(translate("core", "The title bar buttons")))
        for text in value.values():
            if text is not None and (not isinstance(text, str) or parse_buttons(text) is None):
                raise _error(
                    "{what} is not a valid name.", what=str(translate("core", "The title bar buttons"))
                )
        for side, text in value.items():
            if text is not None:
                self._put(runner, side, text)
        _kwin_reload(runner)
        for side, text in value.items():
            if text is not None:
                field = "decorationButtons" + side.capitalize()
                _kwin_says(runner, field, _kwin_numbers(text), translate("core", "title bar buttons"))

    def _refresh(self, runner, restoring: bool = False) -> None:
        _kwin_reload(runner, restoring)


class Icons(_ByTool):
    key = "icons"
    title = translate("core", "Icons")
    what = translate("core", "The icon theme")
    settings = {"theme": ("kdeglobals", ["Icons"], "Theme")}
    # Where distributions put the tool that System Settings runs to change the icon theme.
    TOOLS = (
        "/usr/lib/plasma-changeicons",
        "/usr/lib64/plasma-changeicons",
        "/usr/libexec/plasma-changeicons",
        "/usr/lib/x86_64-linux-gnu/libexec/plasma-changeicons",
    )

    def _tool(self, runner) -> str | None:
        return next((path for path in self.TOOLS if runner.which(path)), None)

    def available(self, runner) -> Msg | None:
        if not self._tool(runner):
            return translate("core", "{tool} is not installed.").format(tool="plasma-changeicons")
        return super().available(runner)

    def installed(self) -> list[str]:
        def usable(path: Path) -> bool:
            text = _read(path / "index.theme")
            return "Directories=" in text and not re.search(r"^Hidden=true", text, re.M)

        return _children(_icon_folders(), usable)

    def current(self, runner) -> str | None:
        return self._get(runner, "theme", "breeze") or None

    def apply(self, value, runner) -> None:
        name = self._name(value)  # the tool takes any text, so the name is checked first
        tool = self._tool(runner)
        if tool is None:
            raise _error("{tool} is not installed.", tool="plasma-changeicons")
        result = runner.run([tool, name])
        if self.current(runner) != name:
            raise self._tool_failed(name, result)
        self._refresh(runner)

    def _refresh(self, runner, restoring: bool = False) -> None:
        for group in range(6):  # every kind of icon, as KDE's own tool does
            _emit(runner, "/KIconLoader", "org.kde.KIconLoader", "iconChanged", group)


class CursorTheme(_ByTool):
    key = "cursor_theme"
    title = translate("core", "Pointer theme")
    what = translate("core", "The pointer theme")
    settings = {"theme": ("kcminputrc", ["Mouse"], "cursorTheme")}
    tools = ("plasma-apply-cursortheme",)

    def installed(self) -> list[str]:
        def usable(path: Path) -> bool:
            return (path / "cursors").is_dir() and not re.search(
                r"^Hidden=true", _read(path / "index.theme"), re.M
            )

        return _children(_icon_folders(), usable)

    def current(self, runner) -> str | None:
        return self._get(runner, "theme", "default") or None

    def apply(self, value, runner) -> None:
        name = self._name(value)
        result = runner.run(["plasma-apply-cursortheme", name])
        if self.current(runner) != name:
            raise self._tool_failed(name, result)
        self._refresh(runner)

    def _refresh(self, runner, restoring: bool = False) -> None:
        desktop.notify_change(runner, 5)  # KWin's own pointer only follows this


class CursorSize(Part):
    """The pointer size in pixels. KDE's tool ignores `--size`, so the size is written here."""

    key = "cursor_size"
    title = translate("core", "Pointer size")
    settings = {"size": ("kcminputrc", ["Mouse"], "cursorSize")}
    SIZES = range(8, 257)

    def current(self, runner) -> int | None:
        text = self._get(runner, "size", "24")
        return int(text) if text.isdigit() else None

    def apply(self, value, runner) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value not in self.SIZES:
            raise _error("{what} is not a valid name.", what=str(translate("core", "The pointer size")))
        self._put(runner, "size", str(value))
        self._refresh(runner)

    def _refresh(self, runner, restoring: bool = False) -> None:
        desktop.notify_change(runner, 5)


FONT_ROLES = {
    "font": ("kdeglobals", ["General"], "font"),
    "fixed": ("kdeglobals", ["General"], "fixed"),
    "small": ("kdeglobals", ["General"], "smallestReadableFont"),
    "toolbar": ("kdeglobals", ["General"], "toolBarFont"),
    "menu": ("kdeglobals", ["General"], "menuFont"),
    "title": ("kdeglobals", ["WM"], "activeFont"),
}


class Fonts(Part):
    """The fonts as `{role: Qt description}` with the roles of `FONT_ROLES`: font (general),
    fixed, small, toolbar, menu and title (window titles). On apply every role is optional."""

    key = "fonts"
    title = translate("core", "Fonts")
    settings = FONT_ROLES
    notify = True

    def current(self, runner) -> dict | None:
        fonts = {role: self._get(runner, role) for role in self.settings}
        return {role: text for role, text in fonts.items() if text} or None

    def apply(self, value, runner) -> None:
        what = str(translate("core", "The font"))
        if not isinstance(value, dict) or not value or not set(value) <= set(self.settings):
            raise _error("{what} is not a valid name.", what=what)
        for text in value.values():
            if not isinstance(text, str) or FontSpec.parse(text) is None:
                raise _error("{what} is not a valid name.", what=what)
        for role, text in value.items():
            self._put(runner, role, text)
        self._refresh(runner, wm="title" in value)

    def _refresh(self, runner, restoring: bool = False, wm: bool = True) -> None:
        desktop.notify_change(runner, 1)
        _emit(runner, "/KDEPlatformTheme", "org.kde.KDEPlatformTheme", "refreshFonts")
        if wm:  # the window title font is KWin's
            _kwin_reload(runner, restoring)


class Sounds(Part):
    """The sound theme as `{"theme": name, "enabled": bool}`; each is optional on apply."""

    key = "sounds"
    title = translate("core", "System sounds")
    settings = {"theme": ("kdeglobals", ["Sounds"], "Theme"), "enabled": ("kdeglobals", ["Sounds"], "Enable")}
    notify = True

    def installed(self) -> list[str]:
        return _children(_folders("sounds"), lambda p: (p / "index.theme").is_file())

    def current(self, runner) -> dict:
        enabled = self._get(runner, "enabled", "true").lower() != "false"
        return {"theme": self._get(runner, "theme", "ocean") or "ocean", "enabled": enabled}

    def validate(self, value) -> None:
        what = str(translate("core", "The sound theme"))
        if isinstance(value, dict) and "theme" in value:
            _check_text(value["theme"], what)
            if value["theme"] not in self.installed():
                raise _error("{what} {name} is not installed.", what=what, name=value["theme"])

    def apply(self, value, runner) -> None:
        what = str(translate("core", "The sound theme"))
        if not isinstance(value, dict) or not value or not set(value) <= {"theme", "enabled"}:
            raise _error("{what} is not a valid name.", what=what)
        theme, enabled = value.get("theme"), value.get("enabled")
        if "theme" in value:
            _check_text(theme, what)
            if theme not in self.installed():
                raise _error("{what} {name} is not installed.", what=what, name=theme)
        if "enabled" in value and not isinstance(enabled, bool):
            raise _error("{what} is not a valid name.", what=what)
        if "theme" in value:
            self._put(runner, "theme", theme)
        if "enabled" in value:
            self._put(runner, "enabled", "true" if enabled else "false")


class Splash(Part):
    """The splash screen: the name of a Global Theme package with a splash, or "None"."""

    key = "splash"
    title = translate("core", "Splash screen")
    settings = {"theme": ("ksplashrc", ["KSplash"], "Theme"), "engine": ("ksplashrc", ["KSplash"], "Engine")}
    NONE = "None"

    def installed(self) -> list[str]:
        return [
            self.NONE,
            *_children(_folders("plasma/look-and-feel"), lambda p: (p / "contents/splash").is_dir()),
        ]

    def current(self, runner) -> str | None:
        if self._get(runner, "engine").lower() == "none":
            return self.NONE
        return self._get(runner, "theme", "org.kde.breeze.desktop") or None

    def validate(self, value) -> None:
        what = str(translate("core", "The splash screen"))
        _check_text(value, what)
        if value not in self.installed():
            raise _error("{what} {name} is not installed.", what=what, name=value)

    def apply(self, value, runner) -> None:
        self.validate(value)
        self._put(runner, "theme", value)
        self._put(runner, "engine", "none" if value == self.NONE else "KSplashQML")


def _hex(color: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


class Accent(Part):
    """The accent color of the desktop: "wallpaper" when it follows the wallpaper, else the custom
    color as `#rrggbb`, else None when the color scheme's own accent is used."""

    key = "accent"
    title = translate("core", "Accent color")
    settings = {
        "color": ("kdeglobals", ["General"], "AccentColor"),
        "wallpaper": ("kdeglobals", ["General"], "accentColorFromWallpaper"),
        "last": ("kdeglobals", ["General"], "LastUsedCustomAccentColor"),
    }
    tools = ("plasma-apply-colorscheme",)
    # Plasma watches these keys: only when it is told does it take the accent from the wallpaper
    # (and then it writes AccentColor itself), as it does for System Settings.
    notify = True
    SCHEME = ("kdeglobals", ["General"], "ColorScheme")

    @staticmethod
    def parse_color(value) -> tuple[int, int, int] | None:
        """`#rrggbb` or `r,g,b` as numbers."""
        if not isinstance(value, str):
            return None
        text = value.strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
            return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)
        found = re.fullmatch(r"(\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3})", text)
        numbers = tuple(int(n) for n in found.groups()) if found else None
        return numbers if numbers and max(numbers) <= 255 else None

    def current(self, runner) -> str | None:
        if self._get(runner, "wallpaper", "false").lower() == "true":
            return "wallpaper"
        color = self.parse_color(self._get(runner, "color"))
        return _hex(color) if color else None

    def apply(self, value, runner) -> None:
        what = str(translate("core", "The accent color"))
        if value == "wallpaper":
            # Told with --notify, Plasma takes the wallpaper's color at once (and writes AccentColor).
            self._put(runner, "wallpaper", "true")
            return
        color = self.parse_color(value)
        if color is None:
            raise _error("{what} is not a valid name.", what=what)
        text = ",".join(map(str, color))
        self._put(runner, "wallpaper", None)  # false is the default: System Settings removes the key
        self._put(runner, "color", text)
        self._put(runner, "last", text)
        self._reload(runner, color)

    def clear(self, runner) -> None:
        """Let the color scheme's own accent show: no custom color, not from the wallpaper."""
        self._put(runner, "wallpaper", None)
        self._put(runner, "color", None)
        self._reload(runner, None)

    def _reload(self, runner, color: tuple[int, int, int] | None) -> None:
        """Put the accent into the colors in use: the color scheme is applied again, with the
        accent, or without it for None. The settings are already written."""
        scheme = kconfig.effective_value(runner, *self.SCHEME, FALLBACK_SCHEME)
        if scheme == RELOAD_PLACEHOLDER:
            scheme = FALLBACK_SCHEME
        if color is None:
            activate_scheme(scheme, runner)  # takes the detour that makes Plasma read the scheme again
            return
        result = runner.run(["plasma-apply-colorscheme", scheme, "--accent-color", _hex(color)])
        shown = kconfig.effective_value(runner, "kdeglobals", ["Colors:Button"], "DecorationFocus")
        if shown != ",".join(map(str, color)):  # the tool writes the accent into the colors
            raise self._tool_failed(scheme, result)

    def restore(self, captured: dict, runner) -> None:
        was = self.current(runner)
        super().restore(captured, runner)
        if was != self.current(runner):  # the colors in use carry the accent, so they follow it
            values = captured.get("values") or {}
            try:
                self._reload(runner, self.parse_color(values.get("color") or ""))
            except ApplyError:
                pass  # the settings are back; the colors follow at the next change of the scheme


class GlobalTheme(Part):
    """The Global Theme in use. It is only read here."""

    key = "global_theme"
    title = translate("core", "Global theme")
    settings = {"package": ("kdeglobals", ["KDE"], "LookAndFeelPackage")}

    def current(self, runner) -> str | None:
        return self._get(runner, "package") or None

    def apply(self, value, runner) -> None:
        raise _error("The global theme cannot be changed from here.")

    def capture(self, runner) -> dict:
        return {"values": {}, "masked": [], "effective": self.current(runner)}


class NightMode(Part):
    """Whether Plasma switches between its light and dark Global Theme with the time of day (the
    "Switch to Dark Mode at Night" check box of System Settings). Which two themes it switches
    between is chosen there; only the switch is changed here."""

    key = "night_mode"
    title = translate("core", "Dark mode at night")
    settings = {"on": ("kdeglobals", ["KDE"], "AutomaticLookAndFeel")}
    notify = True  # the settings daemon of Plasma watches the key

    def current(self, runner) -> bool:
        return self._get(runner, "on", "false").lower() == "true"

    def apply(self, value, runner) -> None:
        if not isinstance(value, bool):
            raise _error("{what} is not a valid name.", what=str(translate("core", "The dark mode switch")))
        self._put(runner, "on", "true" if value else None)  # false is the default: the key goes


PARTS: dict[str, Part] = {
    part.key: part
    for part in (
        GlobalTheme(),
        PlasmaStyle(),
        AppStyle(),
        Decoration(),
        BorderSize(),
        TitlebarButtons(),
        Icons(),
        CursorTheme(),
        CursorSize(),
        Fonts(),
        Sounds(),
        Splash(),
        Accent(),
        NightMode(),
    )
}

# The pages of System Settings, by the id `systemsettings` and `kcmshell6` take.
MODULES = {
    "kcm_lookandfeel": translate("core", "Global Theme"),
    "kcm_colors": translate("core", "Colors"),
    "kcm_style": translate("core", "Application Style"),
    "kcm_desktoptheme": translate("core", "Plasma Style"),
    "kcm_kwindecoration": translate("core", "Window Decorations"),
    "kcm_icons": translate("core", "Icons"),
    "kcm_cursortheme": translate("core", "Cursors"),
    "kcm_fonts": translate("core", "Fonts"),
    "kcm_splashscreen": translate("core", "Splash Screen"),
    "kcm_soundtheme": translate("core", "System Sounds"),
    "kcm_wallpaper": translate("core", "Wallpaper"),
    "kcm_sddm": translate("core", "Login Screen (SDDM)"),
}


def open_system_settings(module_id: str, runner) -> Msg | None:
    """Open a page of System Settings. None when it was started, else the reason why not."""
    if module_id not in MODULES:
        return translate("core", "{name} is not a page of System Settings.").format(name=str(module_id)[:60])
    for program in ("systemsettings", "kcmshell6"):
        if runner.which(program):
            try:
                runner.launch([program, module_id])
            except OSError as error:
                return translate("core", "{tool} could not be started. {detail}").format(
                    tool=program, detail=str(error)
                )
            return None
    return translate("core", "System Settings is not installed.")
