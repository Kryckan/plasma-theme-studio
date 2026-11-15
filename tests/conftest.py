# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path

import pytest

from plasma_theme_studio import kconfig, paths
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.desktopparts import BORDER_SIZES, _kwin_numbers

ICONS_TOOL = "/usr/lib/plasma-changeicons"

# No test may ever open a window on the desktop of whoever runs the tests.
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def _cap_memory() -> None:
    """No test may take the machine down either. Several tests feed the code hostile
    files (a pointer that claims to be 100000 pixels wide, endless files); if the code
    ever believes one, the allocation has to fail here and not fill memory and swap.
    PTS_TEST_MEMORY_CAP gives another number of bytes, 0 turns the cap off."""
    try:
        import resource
    except ImportError:  # not a Unix
        return
    wanted = int(os.environ.get("PTS_TEST_MEMORY_CAP", 8 * 1024**3))
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    if wanted > 0 and (hard == resource.RLIM_INFINITY or wanted <= hard):
        if soft == resource.RLIM_INFINITY or wanted < soft:
            resource.setrlimit(resource.RLIMIT_AS, (wanted, hard))
    try:  # if the kernel must kill something for lack of memory, it is this test run
        Path("/proc/self/oom_score_adj").write_text("1000")
    except OSError:
        pass


_cap_memory()


def _escaped(value: str) -> str:
    """A value the way KDE writes it into a file."""
    value = value.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    if value.startswith(" "):
        value = "\\s" + value[1:]
    if value.endswith(" "):
        value = value[:-1] + "\\s"
    return value


def _config_text(groups) -> str:
    blocks = []
    for names, entries in groups.items():
        if entries:
            header = "".join(f"[{name}]" for name in names)
            lines = [
                key if key.endswith(kconfig.MASK) else f"{key}={_escaped(value)}"
                for key, value in entries.items()
            ]
            blocks.append("\n".join(([header] if header else []) + lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


class _Defaults(dict):
    """Plasma's layer of defaults: (file, (group, ...), key) -> value. It is also
    kept as files in the first folder of XDG_CONFIG_DIRS, where KDE has it."""

    def __setitem__(self, where, value):
        super().__setitem__(where, value)
        file = where[0]
        groups = {}
        for (name, location, key), stored in self.items():
            if name == file:
                groups.setdefault(location, {})[key] = stored
        path = Path(os.environ["XDG_CONFIG_DIRS"].split(":")[0]) / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_config_text(groups))


@pytest.fixture(autouse=True)
def pauses(monkeypatch):
    """No test waits for Plasma. The pauses the panel code asked for are listed instead."""
    from plasma_theme_studio.apply import desktop
    from plasma_theme_studio.generators import panellayout

    asked: list[float] = []
    monkeypatch.setattr(panellayout, "_pause", asked.append)
    monkeypatch.setattr(desktop, "pause", asked.append)
    return asked


@pytest.fixture(autouse=True)
def pickers_read_at_once(monkeypatch):
    """The picker pages read their lists in a worker; a test finds the cards where `show_page` left them.
    A test of the worker itself uses the fixture `pickers_in_background`."""
    from plasma_theme_studio.ui.pages import pickers_common

    monkeypatch.setattr(pickers_common.LoadsInBackground, "synchronous", True)


@pytest.fixture
def pickers_in_background(monkeypatch):
    from plasma_theme_studio.ui.pages import pickers_common

    monkeypatch.setattr(pickers_common.LoadsInBackground, "synchronous", False)


@pytest.fixture(autouse=True)
def settings(tmp_path, home):
    """What the app remembers between starts (QSettings) is kept in the test's
    own folder, under names of its own, and never reaches the real one. The home folder is
    the test's own too, so the window frame code never reads the real kwinrc."""
    try:
        from PySide6.QtCore import QCoreApplication, QSettings
    except ImportError:
        yield
        return
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "qsettings"))
    QCoreApplication.setOrganizationName("plasma-theme-studio-tests")
    QCoreApplication.setApplicationName("plasma-theme-studio-tests")
    yield


class FakeRunner:
    """Stands in for the KDE tools.

    `kdeglobals` values are kept in the `settings` dict by key. Every other
    configuration file is a real file in the test's XDG_CONFIG_HOME, written
    the way kwriteconfig6 writes it; `defaults` plays the part of Plasma's
    layer of defaults (kdedefaults) that kreadconfig6 falls back to, and a key
    removed from above it leaves a `key[$d]` line. Tests add more programs through
    `handlers`: program name -> function(argv) -> Result.
    """

    def __init__(self, scheme="BreezeLight", known=("BreezeLight", "BreezeDark"), schemes_dir=None):
        self.settings = {"ColorScheme": scheme}
        self.defaults = _Defaults()
        self.handlers = {}
        self.known = set(known)
        self.schemes_dir = schemes_dir
        self.calls = []
        self.missing = set()
        self.applied = []
        self.launched = []

    def which(self, program):
        return program not in self.missing

    def launch(self, argv):
        self.launched.append(argv)

    def run(self, argv, timeout=20):
        self.calls.append(argv)
        if argv[0] in self.missing:
            return Result(127, "", f"{argv[0]}: command not found")
        if argv[0] in self.handlers:
            return self.handlers[argv[0]](argv)
        if argv[0] in ("kreadconfig6", "kwriteconfig6"):
            return self._config(argv)
        if argv[0] == "plasma-apply-colorscheme":
            name = argv[1]
            exists = name in self.known or (
                self.schemes_dir is not None and (self.schemes_dir / f"{name}.colors").exists()
            )
            if not exists:
                return Result(0, f'Could not find theme "{name}"\n')
            if self.settings.get("ColorScheme") == name:
                return Result(0, "already set\n")
            self.settings["ColorScheme"] = name
            self.applied.append(name)
            return Result(0, "Successfully applied\n")
        return Result(127)

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
            elif argument in ("--type",):
                next(arguments)
            elif argument != "--notify":
                values.append(argument)
        location = tuple(groups)
        if file == "kdeglobals":
            if argv[0] == "kreadconfig6":
                return Result(0, self.settings.get(key, default) + "\n")
            if delete:
                self.settings.pop(key, None)
            else:
                self.settings[key] = values[0]
            return Result(0)
        path = paths.config_home() / file
        stored = kconfig.parse(path.read_text()) if path.exists() else {}
        hidden = key + kconfig.MASK
        if argv[0] == "kreadconfig6":
            value = stored.get(location, {}).get(key)
            if value is None and hidden in stored.get(location, {}):
                value = default  # the layer of defaults is hidden
            elif value is None:
                value = self.defaults.get((file, location, key), default)
            return Result(0, value + "\n")
        if delete:
            stored.get(location, {}).pop(key, None)
            if (file, location, key) in self.defaults:
                stored.setdefault(location, {})[hidden] = ""
        else:
            stored.setdefault(location, {}).pop(hidden, None)
            stored[location][key] = values[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_config_text(stored))
        return Result(0)


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
        sizes = [key for key, _name in BORDER_SIZES]
        size = self.get("kwinrc", group, "BorderSize") or "Normal"
        left = self.get("kwinrc", group, "ButtonsOnLeft")
        right = self.get("kwinrc", group, "ButtonsOnRight")
        report = [
            "Decoration",
            "==========",
            f"Plugin: {self.get('kwinrc', group, 'library') or 'org.kde.breeze'}",
            f"Theme: {self.get('kwinrc', group, 'theme') or 'Breeze'}",
            f"decorationButtonsLeft: {_kwin_numbers(left)}",
            f"decorationButtonsRight: {_kwin_numbers(right)}",
            f"borderSize: {sizes.index(size)}",
            "",
        ]
        return Result(0, "\n".join(report))


@pytest.fixture(autouse=True)
def windows_do_not_outlive_their_test():
    """Every window a test made is deleted when the test ends, with its pages, pictures and
    worker threads. Left alone they pile up (2 GB and 200 threads by the end of the run),
    and the run then dies at the memory cap on a machine that lays memory out differently."""
    yield
    import gc
    import sys

    widgets = sys.modules.get("PySide6.QtWidgets")
    application = widgets.QApplication.instance() if widgets else None
    if not isinstance(application, widgets.QApplication if widgets else ()):
        return
    from PySide6.QtCore import QCoreApplication, QEvent

    for widget in application.topLevelWidgets():
        widget.hide()
        widget.deleteLater()  # not close(): closing asks about unsaved changes
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()


@pytest.fixture(scope="session")
def app():
    """The one Qt application of the test run. It has to be a QApplication from
    the start: widgets cannot be made once a plainer kind of application exists."""
    widgets = pytest.importorskip("PySide6.QtWidgets")
    return widgets.QApplication.instance() or widgets.QApplication([])


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An empty home folder; nothing in the tests touches the real one."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local/share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / ".cache"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "system/share"))
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path / "system/xdg"))
    return tmp_path


@pytest.fixture
def runner(home):
    return FakeRunner(schemes_dir=home / ".local/share/color-schemes")


@pytest.fixture
def use_generators(monkeypatch):
    """Replace the list of targets, so that a test covers just the ones it names."""

    def use(*generators):
        monkeypatch.setattr("plasma_theme_studio.generators.GENERATORS", tuple(generators))

    return use


@pytest.fixture
def desktop_runner(home):
    """A runner whose desktop keeps every file, with a few things installed to choose from."""
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
    plastik = data / "kwin/decorations/kwin4_decoration_qml_plastik"
    (plastik / "contents/ui").mkdir(parents=True)
    (plastik / "contents/ui/main.qml").write_text("import QtQuick\nItem {}\n")
    (plastik / "metadata.json").write_text(
        '{"KPlugin": {"Id": "kwin4_decoration_qml_plastik", "Name": "Plastik"}}'
    )
    (data / "kstyle/themes").mkdir(parents=True)
    (data / "kstyle/themes/union.themerc").write_text("[KDE]\nWidgetStyle=Union\n")
    (data / "union/styles/breeze").mkdir(parents=True)
    return runner
