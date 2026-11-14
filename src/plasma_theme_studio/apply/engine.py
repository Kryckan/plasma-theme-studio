# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Plans, applies and undoes theme changes.

An apply always goes: check everything, take a snapshot, write the files,
ask the desktop to reload. If a reload fails, the snapshot is put back.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .. import generators
from ..generators import ApplyError, Generator, PlannedFile, generator_by_id
from ..messages import Msg, translate
from ..model.theme import Theme, write_atomic
from . import snapshot as snapshots
from .snapshot import Snapshot

NEW, CHANGED, UNCHANGED, FOREIGN = "new", "changed", "unchanged", "foreign"


class ApplyBlocked(Exception):
    """The apply was stopped before anything was changed."""

    def __init__(self, problems: list[Msg]):
        self.problems = problems
        super().__init__("; ".join(str(p) for p in problems))


@dataclass(frozen=True)
class FileStatus:
    file: PlannedFile
    state: str  # NEW, CHANGED, UNCHANGED or FOREIGN (exists but was not made by this app)


@dataclass
class TargetPlan:
    generator: Generator
    wanted: bool = True  # False: the theme leaves this target alone
    files: list[FileStatus] = field(default_factory=list)
    stale: list[Path] = field(default_factory=list)  # written earlier, removed by this apply
    problems: list[Msg] = field(default_factory=list)
    warnings: list[Msg] = field(default_factory=list)
    notes: list[Msg] = field(default_factory=list)
    reload_command: str = ""
    settings: list[Msg] = field(default_factory=list)  # what else an apply changes, in words


@dataclass
class Plan:
    theme: Theme
    targets: list[TargetPlan]
    problems: list[Msg]

    @property
    def blocking(self) -> list[Msg]:
        return self.problems + [p for target in self.targets for p in target.problems]

    @property
    def warnings(self) -> list[Msg]:
        return [w for target in self.targets for w in target.warnings]

    @property
    def foreign_files(self) -> list[Path]:
        return [s.file.path for t in self.targets for s in t.files if s.state == FOREIGN]

    @property
    def wanted_targets(self) -> list[TargetPlan]:
        return [target for target in self.targets if target.wanted]


def _state(file: PlannedFile) -> str:
    if not file.path.exists():
        return NEW
    try:
        current = file.path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return FOREIGN
    if current == file.content:
        return UNCHANGED
    return CHANGED if current.startswith(file.marker) else FOREIGN


def _inside_home(path: Path) -> bool:
    return path.resolve().is_relative_to(Path.home().resolve())


def build_plan(theme: Theme, runner=None) -> Plan:
    """Work out what an apply would do. With a runner, the system is checked
    too: missing tools and settings that would override the theme."""
    problems = list(theme.problems())
    if runner is not None and os.geteuid() == 0:
        problems.append(translate("core", "Plasma Theme Studio must not be run as root."))
    targets = []
    for generator in generators.GENERATORS:
        target = TargetPlan(generator)
        targets.append(target)
        if theme.problems():
            continue  # without a usable name there are no file names to plan
        target.notes += generator.notes(theme)
        target.wanted = generator.wanted(theme)
        if not target.wanted:
            continue
        target.problems += generator.problems(theme)
        target.reload_command = generator.reload_command(theme)
        target.settings = generator.changed_settings(theme)
        for file in generator.files(theme):
            target.files.append(FileStatus(file, _state(file)))
            target.problems += generator.check_output(file)
            if not _inside_home(file.path):
                target.problems.append(
                    translate("core", "{path} is outside your home folder and will not be written.").format(
                        path=str(file.path)
                    )
                )
        # Only ever remove what is inside the home folder.
        target.stale = [path for path in generator.stale_files(theme) if _inside_home(path)]
        if runner is not None:
            unavailable = generator.unavailable_reason(runner)
            if unavailable:
                target.problems.append(unavailable)
            else:
                target.warnings += generator.warnings(theme, runner)
    return Plan(theme, targets, problems)


@dataclass(frozen=True)
class ApplyResult:
    snapshot: Snapshot
    plan: Plan


def apply(theme: Theme, runner, replace_foreign: bool = False) -> ApplyResult:
    plan = build_plan(theme, runner)
    blocking = plan.blocking
    if plan.foreign_files and not replace_foreign:
        blocking = blocking + [
            translate("core", "{path} already exists and was not made by Plasma Theme Studio.").format(
                path=str(path)
            )
            for path in plan.foreign_files
        ]
    if blocking:
        raise ApplyBlocked(blocking)

    targets = plan.wanted_targets
    files = [status.file for target in targets for status in target.files]
    stale = [path for target in targets for path in target.stale]
    stale_files = [path for path in stale if path.is_file()]
    settings = {t.generator.id: t.generator.capture_settings(runner) for t in targets}
    try:
        snapshot = snapshots.create(theme.name, [f.path for f in files] + stale_files, settings)
    except OSError as error:
        # Without a snapshot there is no way back, so nothing is touched.
        raise ApplyError(
            translate("core", "Could not save the snapshot, so nothing was changed: {detail}").format(
                detail=str(error)
            )
        ) from error
    reached: list[str] = []  # the targets whose settings may have changed
    try:
        for file in files:
            write_atomic(file.path, file.content)
        for target in targets:
            reached.append(target.generator.id)
            target.generator.reload(theme, runner)
        # The desktop has switched to the new files; the old ones can go.
        for path in stale_files:
            path.unlink(missing_ok=True)
        snapshots.remove_empty_dirs(path for path in stale if path.is_dir())
    except BaseException as error:  # an interrupted apply is rolled back too
        # The snapshot goes when everything is back. If not, it is kept as it is: this
        # was not an undo yet, so the user's own undo still gets both of its tries.
        failures = restore(snapshot, runner, only=reached)
        if not failures:
            snapshots.delete(snapshot)
        if not isinstance(error, (ApplyError, OSError)):
            raise
        message = (
            error.message
            if isinstance(error, ApplyError)
            else translate("core", "Could not write the theme files: {detail}").format(detail=str(error))
        )
        if failures:
            message = translate(
                "core",
                "{error} Not everything could be put back either: {failures} "
                "The snapshot is kept, so the undo can be tried again.",
            ).format(error=str(message), failures=" ".join(str(failure) for failure in failures))
        raise ApplyError(message, restored=not failures) from error
    snapshots.prune()
    return ApplyResult(snapshot, plan)


def is_current(plan: Plan, runner) -> bool:
    """Whether an apply would change nothing: every file is already written
    and the desktop already uses it."""
    targets = plan.wanted_targets
    return (
        bool(targets)
        and all(status.state == UNCHANGED for target in targets for status in target.files)
        and not any(target.stale for target in targets)
        and all(target.generator.is_active(plan.theme, runner) for target in targets)
    )


def switch_color_scheme(scheme_id: str, scheme_name: str, runner) -> Snapshot:
    """Make an installed color scheme the active one. No files are written."""
    generator = generator_by_id("colors")
    unavailable = generator.unavailable_reason(runner)
    if unavailable:
        raise ApplyBlocked([unavailable])
    snapshot = snapshots.create(scheme_name, [], {generator.id: generator.capture_settings(runner)})
    try:
        generator.restore_settings({"color_scheme": scheme_id}, runner)
    except ApplyError:
        snapshots.delete(snapshot)
        raise
    snapshots.prune()
    return snapshot


def restore_to(snapshot: Snapshot, runner) -> tuple[Snapshot | None, list[Msg]]:
    """Go back to the state a snapshot recorded.

    A snapshot holds only what its own apply was about to change, so every
    apply made after it is undone first, newest first. The snapshots on the
    way are used up, as Undo does, and the next undo goes further back from
    there. It stops at the first snapshot that cannot be put back completely,
    and before one on the way that cannot be read: what was applied then
    cannot be undone, and anything older would be put back on top of it.

    Returns the snapshot it stopped at and what failed there; without failures
    that is the snapshot asked for. The snapshot is None when it stopped for
    another reason than a snapshot that could not be put back.
    """
    newer = [item for item in snapshots.list_snapshots() if item.id >= snapshot.id]
    if not newer or newer[-1].id != snapshot.id:
        return None, [translate("core", "There is no snapshot called {id}.").format(id=snapshot.id)]
    unreadable = snapshots.unreadable()
    for item, older in zip(newer, [*newer[1:], None], strict=True):
        failures = restore(item, runner, consume=True)
        if failures:
            return item, failures
        between = [name for name in unreadable if older is not None and older.id < name < item.id]
        if between:
            return None, [
                translate(
                    "core",
                    "The snapshot {id} cannot be read, so what was applied then cannot be undone. "
                    "The applies before it were left as they are.",
                ).format(id=between[-1])
            ]
    return snapshot, []


def restore(snapshot: Snapshot, runner, consume: bool = False, only=None) -> list[Msg]:
    """Put files and desktop settings back to what the snapshot recorded.

    Returns messages about settings that could not be restored. With
    `consume`, the snapshot is removed afterwards (this is what Undo does),
    unless something could not be restored: then it is kept for one more try,
    so that what it recorded is not lost to a desktop that was busy.
    `only` names the targets whose settings are put back; the files always are.
    """
    failures = []
    try:
        snapshots.restore_files(snapshot)
    except OSError as error:
        failures.append(translate("core", "Could not put the files back: {detail}").format(detail=str(error)))
    for target_id, settings in snapshot.settings.items():
        generator = generator_by_id(target_id)
        if generator is None or (only is not None and target_id not in only):
            continue
        try:
            generator.restore_settings(settings, runner)
        except ApplyError as error:
            failures.append(error.message)
        except OSError as error:
            failures.append(str(error))
    try:
        if consume and failures and not snapshots.tried(snapshot):
            snapshots.mark_tried(snapshot)
        elif consume:
            snapshots.delete(snapshot)
    except OSError as error:  # the snapshot's own folder cannot be written to
        failures.append(str(error))
    return failures
