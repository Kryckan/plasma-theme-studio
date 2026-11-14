# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reads and changes single keys in KDE's configuration files.

Changes go through `kwriteconfig6`, the tool KDE provides for it. Reading
has two forms, because KDE settings cascade: `effective_value` asks
`kreadconfig6` what the desktop uses (the user's file, then the defaults),
while `user_value` looks only at the user's own file. A snapshot needs the
second one: a key that is not in the user's file must be removed again on
undo, not written with the default value.

KDE has one more state for a key. Plasma keeps a layer of defaults of its own
(`kdedefaults`, written by the global theme), and a `key[$d]` line in the
user's file hides that layer's value. `kwriteconfig6 --delete` leaves such a
line whenever the layer defines the key, so removing a key here also takes
the line away again, unless the user's file had it from the start (`masked`).
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path

from . import paths
from .generators.base import ApplyError
from .messages import translate
from .model.theme import write_atomic

_GROUP = re.compile(r"\[((?:[^\]\\]|\\.)*)\]")
MASK = "[$d]"  # after a key: the default from KDE's own layer is hidden
# How KDE writes characters that a line cannot hold as they are. Other
# sequences (`\,` and `\;` in lists) are left for whoever reads the list.
_ESCAPE = re.compile(r"\\([stnr\\])")
_ESCAPED = {"s": " ", "t": "\t", "n": "\n", "r": "\r", "\\": "\\"}


def _unescape(value: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPED[match[1]], value)


def parse(text: str) -> dict[tuple[str, ...], dict[str, str]]:
    """The groups of a KDE configuration file. A nested group such as
    `[Containments][2]` has the key `("Containments", "2")`. A line that hides
    a default is kept under its whole text, `key[$d]`, with an empty value.
    Values are as the desktop reads them, without the file's escapes, so one
    that is written back with `write_value` comes out the same."""
    groups: dict[tuple[str, ...], dict[str, str]] = {}
    current = groups.setdefault((), {})
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            current = groups.setdefault(tuple(_GROUP.findall(line)), {})
        elif "=" in line:
            key, value = line.split("=", 1)
            current[key.strip()] = _unescape(value.strip())
        elif line.endswith(MASK):
            current[line] = ""
    return groups


def _user_groups(file: str) -> dict[tuple[str, ...], dict[str, str]]:
    try:
        return parse((paths.config_home() / file).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}


def user_value(file: str, groups: Sequence[str], key: str) -> str | None:
    """The value in the user's own configuration file, or None when the key
    is not set there and the default applies."""
    return _user_groups(file).get(tuple(groups), {}).get(key)


def masked(file: str, groups: Sequence[str], key: str) -> bool:
    """Whether the user's own file hides the default that Plasma's layer of
    defaults has for the key."""
    return key + MASK in _user_groups(file).get(tuple(groups), {})


def default_value(file: str, groups: Sequence[str], key: str) -> str | None:
    """The value the key has without the user's own file: the first one in the
    system's configuration folders, where Plasma's layer of defaults is too.
    None when no folder sets the key."""
    for folder in (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":"):
        if not folder:
            continue
        try:
            text = (Path(folder) / file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        value = parse(text).get(tuple(groups), {}).get(key)
        if value is not None:
            return value
    return None


def _location(file: str, groups: Sequence[str], key: str) -> list[str]:
    argv = ["--file", file]
    for group in groups:
        argv += ["--group", group]
    return [*argv, "--key", key]


def effective_value(runner, file: str, groups: Sequence[str], key: str, default: str = "") -> str:
    """The value the desktop uses: the user's setting or else the default."""
    argv = ["kreadconfig6", *_location(file, groups, key)]
    if default:
        argv += ["--default", default]
    result = runner.run(argv)
    return result.stdout.strip() if result.returncode == 0 else default


def write_value(
    runner, file: str, groups: Sequence[str], key: str, value: str | None, masked: bool = False
) -> None:
    """Set a key, or with None remove it so that the default applies again.

    `masked` says that the user's file hid the default before (see `masked`),
    so that the line which does it is left in place when the key is removed."""
    if value is None:
        if user_value(file, groups, key) is None:
            return
        result = runner.run(["kwriteconfig6", *_location(file, groups, key), "--delete"])
        failed = result.returncode != 0 or user_value(file, groups, key) is not None
        if not failed:
            if not masked:
                _unmask(file, groups, key)
            drop_if_empty(file)
    else:
        result = runner.run(["kwriteconfig6", *_location(file, groups, key), "--", value])
        # The tool that reads the value back prints it on a line, so the ends cannot be compared.
        failed = result.returncode != 0 or effective_value(runner, file, groups, key) != value.strip()
    if failed:
        detail = (result.output.splitlines() or [""])[0][:200]
        raise ApplyError(
            translate("core", "Could not change {key} in {file}. {detail}").format(
                key=key, file=file, detail=detail
            )
        )


def drop_if_empty(file: str) -> None:
    """kwriteconfig6 leaves a file without content when it removes the last
    key. KDE reads no file and an empty file alike, so the file goes. A link
    to a file kept somewhere else is the user's own arrangement and stays."""
    path = paths.config_home() / file
    try:
        if not path.is_symlink() and not path.read_text(encoding="utf-8").strip():
            path.unlink()
    except (OSError, UnicodeDecodeError):
        pass  # the empty file does no harm


def _unmask(file: str, groups: Sequence[str], key: str) -> None:
    """Take the `key[$d]` line out of the user's file, and the group with it
    when nothing else is in it. The rest of the file stays as it is."""
    path = paths.config_home() / file
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return
    wanted, current = tuple(groups), ()
    kept: list[str] = []
    found = False
    for line in lines:
        text = line.strip()
        if text.startswith("["):
            current = tuple(_GROUP.findall(text))
        elif current == wanted and text == key + MASK:
            found = True
            continue
        kept.append(line)
    if not found:
        return
    result: list[str] = []
    emptied = False  # just after the header of a group that has nothing left in it
    for number, line in enumerate(kept):
        text = line.strip()
        if text.startswith("[") and tuple(_GROUP.findall(text)) == wanted:
            following = next((item.strip() for item in kept[number + 1 :] if item.strip()), "[")
            if following.startswith("["):
                emptied = True
                continue
        if emptied and not text:
            continue  # the blank lines that set the group apart go with it
        emptied = False
        result.append(line)
    text = "\n".join(result).strip("\n")
    linked = path.is_symlink()  # the file is kept somewhere else: it is changed there
    try:
        if text or linked:
            write_atomic(path.resolve() if linked else path, text + "\n" if text else "")
        else:
            path.unlink(missing_ok=True)  # KDE reads no file and an empty file alike
    except OSError as error:
        raise ApplyError(
            translate("core", "Could not change {key} in {file}. {detail}").format(
                key=key, file=file, detail=str(error)
            )
        ) from error


def file_exists(file: str) -> bool:
    """Whether the user's file is there (a link counts, a broken one too)."""
    path = paths.config_home() / file
    return path.exists() or path.is_symlink()
