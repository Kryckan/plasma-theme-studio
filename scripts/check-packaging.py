#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks that the package recipes agree with each other and with the code.

    scripts/check-packaging.py [--stage]

Always: the version is the same in the code, both PKGBUILDs, the RPM spec, the
.dsc, the Debian changelog and the AppStream data; every recipe installs through
packaging/install.sh; the metainfo screenshots exist in the repository.
With --stage: runs packaging/install.sh into a throwaway folder and checks that
the RPM spec's %files and the Debian install list cover every file it installs
(needs Qt's lrelease; the files of the repository are only read).
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
APP_ID = "io.github.kryckan.PlasmaThemeStudio"
MACROS = {"%{_bindir}": "/usr/bin", "%{_datadir}": "/usr/share", "%{_prefix}": "/usr"}


def first(pattern: str, text: str, flags: int = re.M) -> str | None:
    found = re.search(pattern, text, flags)
    return found.group(1) if found else None


def check_versions() -> list[str]:
    problems = []
    code = first(r'^__version__ = "(.*)"$', (ROOT / "src/plasma_theme_studio/__init__.py").read_text())
    seen = {
        "PKGBUILD (release)": first(r"^pkgver=(.*)$", (PKG / "arch/release/PKGBUILD").read_text()),
        "plasma-theme-studio.spec": first(
            r"^Version:\s+(.*)$", (PKG / "obs/plasma-theme-studio.spec").read_text()
        ),
        "plasma-theme-studio.dsc": first(
            r"^Version: (.*)$", (PKG / "obs/plasma-theme-studio.dsc").read_text()
        ),
        "debian/changelog": first(
            r"^plasma-theme-studio \((.*?)\)", (PKG / "obs/debian/changelog").read_text()
        ),
        "_service": first(r'"versionformat">(.*?)<', (PKG / "obs/_service").read_text()),
        "_service revision": (first(r'"revision">v?(.*?)<', (PKG / "obs/_service").read_text())),
    }
    metainfo = ET.parse(ROOT / f"data/{APP_ID}.metainfo.xml").getroot()
    release = metainfo.find("releases/release")
    seen["metainfo"] = release.get("version") if release is not None else None
    git_pkgver = first(r"^pkgver=(\d+\.\d+\.\d+)", (PKG / "arch/git/PKGBUILD").read_text())
    seen["PKGBUILD (git)"] = git_pkgver
    for name, value in seen.items():
        if value != code:
            problems.append(f"{name} says version {value}, the code says {code}")
    return problems


def check_recipes() -> list[str]:
    problems = []
    recipes = {
        "arch/release/PKGBUILD": "packaging/install.sh",
        "arch/git/PKGBUILD": "packaging/install.sh",
        "obs/plasma-theme-studio.spec": "packaging/install.sh",
        "obs/debian/rules": "packaging/install.sh",
    }
    for name, needle in recipes.items():
        if needle not in (PKG / name).read_text():
            problems.append(f"{name} does not call {needle}")
    metainfo = (ROOT / f"data/{APP_ID}.metainfo.xml").read_text()
    for url in re.findall(r"<image[^>]*>(.*?)</image>", metainfo):
        path = url.split("/main/", 1)[-1]
        if "/main/" not in url or not (ROOT / path).is_file():
            problems.append(f"screenshot {url} is not a file of the repository")
    return problems


def staged_files() -> list[str]:
    with tempfile.TemporaryDirectory(prefix="pts-stage-") as stage:
        subprocess.run([str(PKG / "install.sh"), stage], check=True, capture_output=True)
        return sorted("/" + str(p.relative_to(stage)) for p in Path(stage).rglob("*") if not p.is_dir())


def spec_patterns() -> list[str]:
    text = (PKG / "obs/plasma-theme-studio.spec").read_text()
    section = text.split("\n%files", 1)[1].split("\n%changelog", 1)[0]
    patterns = []
    for line in section.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("%license") or line.startswith("%doc"):
            continue
        for macro, value in MACROS.items():
            line = line.replace(macro, value)
        patterns.append(line)
    return patterns


def covered_by_spec(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, p) or (p.endswith("/") and path.startswith(p)) for p in patterns)


def covered_by_debian(path: str, lines: list[str]) -> bool:
    return any(
        path == "/" + line.rstrip("/") or path.startswith("/" + line.rstrip("/") + "/") for line in lines
    )


def check_staged() -> list[str]:
    problems = []
    files = staged_files()
    if not files:
        return ["install.sh installed nothing"]
    patterns = spec_patterns()
    debian = [
        line.split()[0]
        for line in (PKG / "obs/debian/install").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    for path in files:
        if not covered_by_spec(path, patterns):
            problems.append(f"the RPM spec does not list {path}")
        if not covered_by_debian(path, debian):
            problems.append(f"debian/install does not list {path}")
    for pattern in patterns:
        if not any(fnmatch.fnmatchcase(f, pattern) or f.startswith(pattern) for f in files):
            problems.append(f"the RPM spec lists {pattern}, which install.sh does not install")
    for needed in (
        "/usr/bin/plasma-theme-studio",
        f"/usr/share/applications/{APP_ID}.desktop",
        f"/usr/share/metainfo/{APP_ID}.metainfo.xml",
        "/usr/share/plasma-theme-studio/plasma_theme_studio/i18n/plasma_theme_studio_sv.qm",
    ):
        if needed not in files:
            problems.append(f"install.sh does not install {needed}")
    if any(f.endswith(".ts") for f in files):
        problems.append("translation sources are installed")
    return problems


def main(argv: list[str]) -> int:
    problems = check_versions() + check_recipes()
    if "--stage" in argv:
        problems += check_staged()
    for problem in problems:
        print("PROBLEM:", problem, file=sys.stderr)
    if not problems:
        print("packaging recipes agree")
    return 1 if problems else 0


if __name__ == "__main__":
    os.umask(0o022)
    sys.exit(main(sys.argv[1:]))
