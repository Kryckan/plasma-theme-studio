# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from plasma_theme_studio.apply.runner import Result


class FakeRunner:
    """Stands in for the KDE tools: keeps kdeglobals values in a dict."""

    def __init__(self, scheme="BreezeLight", known=("BreezeLight", "BreezeDark"), schemes_dir=None):
        self.settings = {"ColorScheme": scheme}
        self.known = set(known)
        self.schemes_dir = schemes_dir
        self.calls = []
        self.missing = set()
        self.applied = []

    def which(self, program):
        return program not in self.missing

    def run(self, argv, timeout=20):
        self.calls.append(argv)
        if argv[0] == "kreadconfig6":
            return Result(0, self.settings.get(argv[argv.index("--key") + 1], "") + "\n")
        if argv[0] == "kwriteconfig6":
            self.settings[argv[-2]] = argv[-1]
            return Result(0)
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


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An empty home folder; nothing in the tests touches the real one."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local/share"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / ".cache"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "system/share"))
    return tmp_path


@pytest.fixture
def runner(home):
    return FakeRunner(schemes_dir=home / ".local/share/color-schemes")
