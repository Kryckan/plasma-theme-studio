# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs the KDE command-line tools. Tests replace this with a fake."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def output(self) -> str:
        return (self.stdout + self.stderr).strip()


class SystemRunner:
    def which(self, program: str) -> bool:
        return shutil.which(program) is not None

    def run(self, argv: list[str], timeout: float = 20) -> Result:
        env = dict(os.environ)
        if not env.get("WAYLAND_DISPLAY") and not env.get("DISPLAY"):
            # The KDE tools abort without a display. This keeps `restore`
            # usable from a text console.
            env["QT_QPA_PLATFORM"] = "offscreen"
        try:
            done = subprocess.run(
                argv,
                capture_output=True,
                encoding="utf-8",
                errors="replace",  # odd bytes in a tool's output must not stop an apply half way
                timeout=timeout,
                check=False,
                env=env,
            )
        except FileNotFoundError:
            return Result(127, "", f"{argv[0]}: command not found")
        except subprocess.TimeoutExpired:
            return Result(124, "", f"{argv[0]}: timed out after {timeout:g} s")
        return Result(done.returncode, done.stdout, done.stderr)
