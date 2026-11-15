# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small helpers that several targets share: waiting, telling running programs
that a setting changed, and keeping one whole text file in a snapshot."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from ..model.theme import write_atomic
from .runner import Result

# KGlobalSettings.notifyChange kinds.
CHANGE_PALETTE = 0
CHANGE_FONT = 1
CHANGE_STYLE = 2
CHANGE_ICONS = 4
CHANGE_CURSOR = 5

# What `capture_file` stores for a file that does not exist.
ABSENT = "absent"

_PATH = "/KGlobalSettings"
_INTERFACE = "org.kde.KGlobalSettings"
_MEMBER = "notifyChange"


# A function the window sets while it waits for an undo, so the window keeps painting during a pause.
keep_alive: Callable[[], None] | None = None


def pause(seconds: float) -> None:
    """The one place that sleeps. Tests replace it. While `keep_alive` is set the wait is cut into
    short slices and it is called between them."""
    if keep_alive is None:
        time.sleep(seconds)
        return
    end = time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        time.sleep(min(left, 0.03))
        keep_alive()


def notify_change(runner, kind: int, argument: int = 0) -> Result:
    """Tell running programs that a palette, font, style, icon or cursor setting
    changed (KGlobalSettings.notifyChange). Uses `dbus-send`, or `busctl --user`
    when that is missing. Never raises: without either tool the result is a failure."""
    if runner.which("dbus-send"):
        argv = [
            "dbus-send",
            "--session",
            "--type=signal",
            _PATH,
            f"{_INTERFACE}.{_MEMBER}",
            f"int32:{int(kind)}",
            f"int32:{int(argument)}",
        ]
    elif runner.which("busctl"):
        argv = [
            "busctl",
            "--user",
            "emit",
            _PATH,
            _INTERFACE,
            _MEMBER,
            "ii",
            str(int(kind)),
            str(int(argument)),
        ]
    else:
        return Result(127, "", "neither dbus-send nor busctl is installed")
    try:
        return runner.run(argv)
    except OSError as error:
        return Result(127, "", str(error))


def capture_file(path: Path) -> str:
    """The whole text of a file for a snapshot, or ABSENT when there is none.
    Line endings are kept as they are, so that a restore is byte for byte."""
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            return stream.read()
    except FileNotFoundError:
        return ABSENT
    except IsADirectoryError as error:
        raise OSError(f"{path} is a folder") from error
    except UnicodeDecodeError as error:
        raise OSError(f"{path} is not a text file") from error


def restore_file(path: Path, saved: str) -> None:
    """Put a file back the way `capture_file` found it. A file that did not
    exist is removed; one that is a link is emptied instead, since the link
    is not ours. A file that is already as it was is left alone."""
    if capture_file(path) == saved:
        return
    if saved != ABSENT:
        write_atomic(path, saved)
    elif path.is_symlink():
        write_atomic(path, "")
    else:
        path.unlink(missing_ok=True)
