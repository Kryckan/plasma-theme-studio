# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line entry point.

Without a command the editor window opens. The `restore` command works
from a text console, so a desktop that became hard to use can be put back.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import APP_NAME, __version__, archive, globaltheme, library, writelock
from .apply import engine
from .apply import snapshot as snapshots
from .apply.runner import SystemRunner
from .generators import ApplyError, plasmastyle
from .messages import translate
from .model.theme import Theme, ThemeError

COMMANDS = ("apply", "status", "validate", "restore", "export", "import", "export-global-theme", "follow")


def _print_problems(problems) -> None:
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)


def _load_translation() -> None:
    try:
        from . import translations

        translations.load()
    except ImportError:
        pass  # without PySide6 the console commands still work, in English


def _load_theme(path: str, variant: str | None = None) -> Theme | None:
    """The theme in the file. With `variant`, the theme shows that variant; one the theme does not
    have is reported and gives None."""
    try:
        theme = Theme.load(Path(path))
    except ThemeError as error:
        print(translate("core", "{path} cannot be used:").format(path=path), file=sys.stderr)
        _print_problems(error.problems)
        return None
    if variant is not None:
        if variant not in theme.variants:
            print(
                translate("core", "{path} has no {variant} variant. Add it on the Colors page first.").format(
                    path=path, variant=variant
                ),
                file=sys.stderr,
            )
            return None
        theme.show(variant)
    return theme


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
    theme = _load_theme(args.file, getattr(args, "variant", None))
    if theme is None:
        return 1
    runner = SystemRunner()
    # The own pictures are drawn first, so that "already applied" is judged on what the apply would install
    plasmastyle.vet_artwork(theme)
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


def cmd_status(args) -> int:
    theme = _load_theme(args.file, getattr(args, "variant", None))
    if theme is None:
        return 1
    labels = {
        "change": translate("core", "Would change"),
        "same": translate("core", "Already so"),
        "leave": translate("core", "Left alone"),
        "blocked": translate("core", "Refused"),
    }
    rows = [
        (
            translate("core", "Part"),
            translate("core", "Desktop now"),
            translate("core", "Theme"),
            translate("core", "Apply"),
        )
    ]
    runner = SystemRunner()
    for part in engine.parts_status(theme, runner):
        rows.append((part.title, part.desktop, part.theme, str(labels[part.state])))
    rows = [tuple(str(cell) for cell in row) for row in rows]
    widths = [max(len(row[column]) for row in rows) for column in range(4)]
    for row in rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip())
    if theme.has_both:
        from .generators.variants import variant_on_desktop

        on_desktop = variant_on_desktop(theme, runner)
        shown = {"light": translate("core", "light"), "dark": translate("core", "dark")}
        print()
        if on_desktop is None:
            print(translate("core", "The desktop uses neither variant of this theme."))
        else:
            print(translate("core", "Variant on the desktop: {variant}").format(variant=shown[on_desktop]))
    return 0


def cmd_export(args) -> int:
    theme = _load_theme(args.file)
    if theme is None:
        return 1
    target = Path(args.archive) if args.archive else Path(args.file).with_suffix(archive.EXTENSION)
    try:
        archive.export_theme(theme, target)
    except OSError as error:
        print(
            translate("core", "Could not write {path}: {detail}").format(path=str(target), detail=str(error)),
            file=sys.stderr,
        )
        return 1
    print(translate("core", "Exported {name} to {path}.").format(name=theme.name, path=str(target)))
    return 0


def cmd_import(args) -> int:
    try:
        theme = archive.import_theme(Path(args.file))
        theme, saved = library.save_imported(theme)
    except archive.ArchiveError as error:
        print(translate("core", "{path} cannot be imported:").format(path=args.file), file=sys.stderr)
        _print_problems([error.message])
        return 1
    except OSError as error:
        print(
            translate("core", "Could not import {path}: {detail}").format(path=args.file, detail=str(error)),
            file=sys.stderr,
        )
        return 1
    print(
        translate("core", "Imported {name} as {path}. Nothing was applied to the desktop.").format(
            name=theme.name, path=str(saved)
        )
    )
    return 0


def _qt_application() -> None:
    """A Qt application that draws offscreen, for the preview picture of a Global Theme.
    Without PySide6 the bundle simply has no picture."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    if QApplication.instance() is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"  # no window is ever shown by this command
        QApplication(["plasma-theme-studio"])


def cmd_export_global_theme(args) -> int:
    theme = _load_theme(args.file)
    if theme is None:
        return 1
    _qt_application()
    try:
        written = globaltheme.export_global_theme(theme, Path(args.folder))
    except globaltheme.ExportError as error:
        print(translate("core", "Nothing was exported:"), file=sys.stderr)
        _print_problems([error.message])
        return 1
    except OSError as error:
        print(translate("core", "Could not export: {detail}").format(detail=str(error)), file=sys.stderr)
        return 1
    print(
        translate("core", "Exported {name} as a Global Theme ({count} files) in {path}.").format(
            name=theme.name, count=len(written), path=args.folder
        )
    )
    print(translate("core", "Run install.sh in that folder to install it for the current user."))
    print(translate("core", "Applying a Global Theme also turns the splash screen off."))
    return 0


def _say_when_waiting() -> None:
    """Tell the person once when another Plasma Theme Studio process is writing and this one waits."""
    writelock.on_wait = lambda: print(
        translate("core", "Waiting for another Plasma Theme Studio process to finish writing…"),
        file=sys.stderr,
    )


def cmd_restore(args) -> int:
    _say_when_waiting()
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
        # Each snapshot that is put back is used up, as Undo does, so running
        # the command again goes one apply further back. With an ID, the
        # applies made after that snapshot are undone on the way to it.
        reached, failures = engine.restore_to(chosen, SystemRunner())
    except OSError as error:
        print(translate("core", "Could not restore: {detail}").format(detail=str(error)), file=sys.stderr)
        return 1
    if failures:
        if reached is not None:  # None: nothing was tried (lock busy, no such snapshot); the text says it
            print(translate("core", "Some settings could not be switched back:"), file=sys.stderr)
        _print_problems(failures)
        if reached is not None and reached.id != chosen.id:
            print(
                translate(
                    "core",
                    "The undo stopped at the apply of {name} ({time}). "
                    "The applies before it were left as they are.",
                ).format(name=reached.theme_name, time=f"{reached.created_at:%Y-%m-%d %H:%M:%S}"),
                file=sys.stderr,
            )
        if reached is not None and snapshots.get(reached.id) is not None:
            print(
                translate("core", "The snapshot is kept. Run the command again to try once more."),
                file=sys.stderr,
            )
        return 1
    print(
        translate("core", "The desktop is back to how it was before {name} was applied ({time}).").format(
            name=chosen.theme_name, time=f"{chosen.created_at:%Y-%m-%d %H:%M:%S}"
        )
    )
    remaining = len(snapshots.list_snapshots())
    if remaining:
        print(
            translate(
                "core", "Run the command again to go back one more apply ({count} snapshots left)."
            ).format(count=remaining)
        )
    return 0


def cmd_follow(args) -> int:
    """Follow mode: the watcher itself, `--once`, `on FILE`, `off` and `status`."""
    if args.action is not None or args.once:  # the background watcher says nothing into the journal
        _say_when_waiting()
    from . import follow, palette

    runner = SystemRunner()
    if args.action is None:
        if args.file:
            print(translate("core", "Give a theme file only with: follow on FILE"), file=sys.stderr)
            return 2
        if args.once:
            code, message = follow.run_once(runner)
            print(str(message), file=sys.stderr if code else sys.stdout)
            return code
        return follow.watch(runner)
    if args.once:
        print(translate("core", "--once goes with plain follow, with no on, off or status."), file=sys.stderr)
        return 2
    if args.action == "on":
        if not args.file:
            print(
                translate("core", "Name the theme file whose name the colors get: follow on FILE"),
                file=sys.stderr,
            )
            return 2
        theme = _load_theme(args.file)
        if theme is None:
            return 1
        source = palette.PaletteFile("pywal", Path(args.palette)) if args.palette else None
        try:
            done = follow.enable(theme, runner, source, args.variant)
        except follow.FollowError as error:
            print(translate("core", "Follow mode was not switched on:"), file=sys.stderr)
            _print_problems([error.message])
            return 1
        print(str(done.message))
        print(translate("core", "To go back, run: plasma-theme-studio follow off"))
        return 0
    if args.action == "off":
        done = follow.disable(runner)
        print(str(done.message))
        if done.failures:
            _print_problems(done.failures)
            return 1
        return 0
    state = follow.status()
    if not state.on:
        print(translate("core", "Follow mode is off."))
        return 0
    print(translate("core", "Follow mode is on, following {path}.").format(path=state.state.source))
    print(
        translate("core", "The watcher is running.")
        if state.running
        else translate("core", "The watcher is not running. It starts at the next login.")
    )
    if state.state.applied_at:
        print(
            translate("core", "The colors were last changed at {time}.").format(time=state.state.applied_at)
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
    apply.add_argument(
        "--variant",
        choices=("light", "dark"),
        help="apply this variant of a theme that has both (default: its main one)",
    )
    apply.set_defaults(run=cmd_apply)

    status = commands.add_parser("status", help="show what an apply would change, part by part")
    status.add_argument("file")
    status.add_argument(
        "--variant", choices=("light", "dark"), help="compare this variant of a theme that has both"
    )
    status.set_defaults(run=cmd_status)

    export = commands.add_parser("export", help="write a theme file as one shareable archive")
    export.add_argument("file")
    export.add_argument("archive", nargs="?", help="where to write it (default: next to the theme file)")
    export.set_defaults(run=cmd_export)

    import_ = commands.add_parser("import", help="save a theme archive or theme file as a new theme")
    import_.add_argument("file")
    import_.set_defaults(run=cmd_import)

    global_theme = commands.add_parser(
        "export-global-theme", help="write a theme as a Global Theme in a new or empty folder"
    )
    global_theme.add_argument("file")
    global_theme.add_argument("folder")
    global_theme.set_defaults(run=cmd_export_global_theme)

    restore = commands.add_parser("restore", help="go back to the state before an apply")
    restore.add_argument("id", nargs="?", help="snapshot to go back to (default: undo the latest apply)")
    restore.add_argument("--list", action="store_true", help="list the snapshots")
    restore.set_defaults(run=cmd_restore)

    follow = commands.add_parser(
        "follow", help="keep the desktop colors in step with a pywal or matugen palette"
    )
    follow.add_argument("action", nargs="?", choices=("on", "off", "status"))
    follow.add_argument("file", nargs="?", help="with on: the theme file whose name the colors get")
    follow.add_argument("--once", action="store_true", help="apply the palette once and exit")
    follow.add_argument(
        "--palette", help="with on: the palette file to follow (default: pywal's or matugen's)"
    )
    follow.add_argument("--variant", choices=("light", "dark"), help="with on: make a light or a dark theme")
    follow.set_defaults(run=cmd_follow)
    return parser


USAGE = f"""{APP_NAME} {__version__}

usage: plasma-theme-studio [FILE]             open the editor
       plasma-theme-studio validate FILE      check a theme file
       plasma-theme-studio apply FILE [--variant light|dark]
                                              apply a theme file to the desktop
       plasma-theme-studio status FILE        show what applying a theme file would change
       plasma-theme-studio export FILE [OUT]  write a theme file as one shareable archive (.ptstheme)
       plasma-theme-studio import FILE        save an archive or theme file as a new theme
       plasma-theme-studio export-global-theme FILE FOLDER
                                              write a Global Theme with install.sh into FOLDER
       plasma-theme-studio follow on FILE     keep the colors in step with a pywal or matugen palette
       plasma-theme-studio follow off|status  switch that off (back to before), or show it
       plasma-theme-studio follow [--once]    run the watcher, or apply the palette once
       plasma-theme-studio restore            undo the latest apply (repeat to go further back)
       plasma-theme-studio restore ID         go back to a chosen snapshot, undoing the applies after it
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
