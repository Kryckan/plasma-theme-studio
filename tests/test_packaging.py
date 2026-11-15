# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The package recipes (Arch, RPM, Debian) agree with the code and install the same files."""

import importlib.util
import shutil
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-packaging.py"
spec = importlib.util.spec_from_file_location("check_packaging", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

LRELEASE = any(
    shutil.which(t) for t in ("lrelease6", "lrelease-qt6", "lrelease", "/usr/lib/qt6/bin/lrelease")
)


def test_versions_and_recipes_agree():
    assert check.check_versions() == []
    assert check.check_recipes() == []


@pytest.mark.skipif(not LRELEASE, reason="needs Qt's lrelease")
def test_every_recipe_installs_every_file():
    assert check.check_staged() == []


def test_a_missing_file_in_the_spec_is_found(monkeypatch):
    monkeypatch.setattr(check, "staged_files", lambda: ["/usr/bin/plasma-theme-studio", "/usr/share/other/x"])
    monkeypatch.setattr(check, "spec_patterns", lambda: ["/usr/bin/plasma-theme-studio"])
    problems = check.check_staged()
    assert any("spec does not list /usr/share/other/x" in p for p in problems)
