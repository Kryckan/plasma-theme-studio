# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path

import pytest

from plasma_theme_studio import kconfig, paths
from plasma_theme_studio.apply.runner import Result

# No test may ever open a window on the desktop of whoever runs the tests.
os.environ["QT_QPA_PLATFORM"] = "offscreen"


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
    from plasma_theme_studio.generators import panellayout

    asked: list[float] = []
    monkeypatch.setattr(panellayout, "_pause", asked.append)
    return asked


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

    def which(self, program):
        return program not in self.missing

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
