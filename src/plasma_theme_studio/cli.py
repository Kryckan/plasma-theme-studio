# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line entry point.

Without a command the editor window opens. The `restore` command works
from a text console, so a desktop that became hard to use can be put back.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .apply import engine
from .apply import snapshot as snapshots
from .apply.runner import SystemRunner
from .generators import ApplyError
from .messages import translate
from .model.theme import Theme, ThemeError

COMMANDS = ("apply", "validate", "restore")


def _print_problems(problems) -> None:
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)


def _load_translation() -> None:
    try:
        from . import translations

        translations.load()
    except ImportError:
        pass  # without PySide6 the console commands still work, in English


def _load_theme(path: str) -> Theme | None:
    try:
        return Theme.load(Path(path))
    except ThemeError as error:
        print(translate("core", "{path} cannot be used:").format(path=path), file=sys.stderr)
        _print_problems(error.problems)
        return None


def cmd_validate(args) -> int:
    theme = _load_theme(args.file)
    if theme is None:
        return 1
    blocking = engine.build_plan(theme).blocking
    if blocking:
        print(translate("core", "{path} cannot be applied:").format(path=args.file), file=sys.stderr)
        _print_problems(blocking)
        return 1
    print(translate("core", "{path} is a valid theme.").format(path=args.file))
    return 0


def cmd_apply(args) -> int:
    theme = _load_theme(args.file)
    if theme is None:
        return 1
    runner = SystemRunner()
    plan = engine.build_plan(theme, runner)
    if not plan.blocking and engine.is_current(plan, runner):
        # Nothing to do, so no snapshot is made that would undo nothing.
        print(
            translate("core", "The desktop already uses {name}. Nothing was changed.").format(name=theme.name)
        )
        return 0
    try:
        result = engine.apply(theme, runner, replace_foreign=args.replace)
    except engine.ApplyBlocked as error:
        print(translate("core", "Nothing was changed:"), file=sys.stderr)
        _print_problems(error.problems)
        return 1
    except ApplyError as error:
        if error.restored:
            heading = translate("core", "The apply failed and was rolled back:")
        else:
            heading = translate("core", "The apply failed, and not everything could be put back:")
        print(heading, file=sys.stderr)
        _print_problems([error.message])
        return 1
    limits = [note for target in result.plan.wanted_targets for note in target.notes]
    for text in result.plan.warnings + limits:
        print(translate("core", "Note: {text}").format(text=str(text)))
    print(
        translate("core", "Applied {name}. To go back, run: plasma-theme-studio restore").format(
            name=theme.name
        )
    )
    return 0


def cmd_restore(args) -> int:
    available = snapshots.list_snapshots()
    if args.list:
        if not available:
            print(translate("core", "There are no snapshots."))
        for item in available:
            print(f"{item.id}  {item.created_at:%Y-%m-%d %H:%M:%S}  {item.theme_name}")
        return 0
    if args.id:
        chosen = snapshots.get(args.id)
        if chosen is None:
            print(translate("core", "There is no snapshot called {id}.").format(id=args.id), file=sys.stderr)
            return 1
    elif available:
        chosen = available[0]
    else:
        print(translate("core", "There are no snapshots."), file=sys.stderr)
        return 1
    try:
        # Without an ID this works like Undo: the snapshot is used up, so
        # running the command again goes one apply further back.
        failures = engine.restore(chosen, SystemRunner(), consume=args.id is None)
    except OSError as error:
        print(translate("core", "Could not restore: {detail}").format(detail=str(error)), file=sys.stderr)
        return 1
    print(
        translate("core", "Restored the files from before {name} was applied ({time}).").format(
            name=chosen.theme_name, time=f"{chosen.created_at:%Y-%m-%d %H:%M:%S}"
        )
    )
    if failures:
        print(translate("core", "Some settings could not be switched back:"), file=sys.stderr)
        _print_problems(failures)
        if args.id is None and snapshots.get(chosen.id) is not None:
            print(
                translate("core", "The snapshot is kept. Run the command again to try once more."),
                file=sys.stderr,
            )
        return 1
    remaining = len(snapshots.list_snapshots())
    if args.id is None and remaining:
        print(
            translate(
                "core", "Run the command again to go back one more apply ({count} snapshots left)."
            ).format(count=remaining)
        )
    return 0


def _command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plasma-theme-studio")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="check a theme file without changing anything")
    validate.add_argument("file")
    validate.set_defaults(run=cmd_validate)

    apply = commands.add_parser("apply", help="apply a theme file to the desktop")
    apply.add_argument("file")
    apply.add_argument(
        "--replace",
        action="store_true",
        help="replace files with the same name that were not made by this app",
    )
    apply.set_defaults(run=cmd_apply)

    restore = commands.add_parser("restore", help="go back to the state before an apply")
    restore.add_argument("id", nargs="?", help="snapshot to go back to (default: undo the latest apply)")
    restore.add_argument("--list", action="store_true", help="list the snapshots")
    restore.set_defaults(run=cmd_restore)
    return parser


USAGE = f"""{APP_NAME} {__version__}

usage: plasma-theme-studio [FILE]             open the editor
       plasma-theme-studio validate FILE      check a theme file
       plasma-theme-studio apply FILE         apply a theme file to the desktop
       plasma-theme-studio restore            undo the latest apply (repeat to go further back)
       plasma-theme-studio restore ID         go back to a chosen snapshot
       plasma-theme-studio restore --list     list the snapshots
"""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE, end="")
        return 0
    if argv and argv[0] in ("-V", "--version"):
        print(f"{APP_NAME} {__version__}")
        return 0
    if argv and argv[0] in COMMANDS:
        args = _command_parser().parse_args(argv)
        _load_translation()
        return args.run(args)
    if len(argv) > 1 or (argv and argv[0].startswith("-")):
        print(USAGE, end="", file=sys.stderr)
        return 2
    try:
        from .ui.app import run
    except ImportError as error:
        print(
            f"The editor needs PySide6 (Qt for Python), which could not be loaded: {error}\n"
            "Install your distribution's package, for example 'pyside6' on Arch "
            "or 'python3-pyside6' on Fedora, Debian and openSUSE.",
            file=sys.stderr,
        )
        return 1
    return run(argv[0] if argv else None)
