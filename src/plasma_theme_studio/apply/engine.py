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

from ..generators import GENERATORS, MARKER, ApplyError, Generator, PlannedFile, generator_by_id
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
    files: list[FileStatus] = field(default_factory=list)
    problems: list[Msg] = field(default_factory=list)
    warnings: list[Msg] = field(default_factory=list)
    reload_command: str = ""


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


def _state(file: PlannedFile) -> str:
    if not file.path.exists():
        return NEW
    try:
        current = file.path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return FOREIGN
    if current == file.content:
        return UNCHANGED
    return CHANGED if current.startswith(MARKER) else FOREIGN


def _inside_home(path: Path) -> bool:
    return path.resolve().is_relative_to(Path.home().resolve())


def build_plan(theme: Theme, runner=None) -> Plan:
    """Work out what an apply would do. With a runner, the system is checked
    too: missing tools and settings that would override the theme."""
    problems = list(theme.problems())
    if runner is not None and os.geteuid() == 0:
        problems.append(translate("core", "Plasma Theme Studio must not be run as root."))
    targets = []
    for generator in GENERATORS:
        target = TargetPlan(generator)
        targets.append(target)
        if theme.problems():
            continue  # without a usable name there are no file names to plan
        target.problems += generator.problems(theme)
        target.reload_command = generator.reload_command(theme)
        for file in generator.files(theme):
            target.files.append(FileStatus(file, _state(file)))
            target.problems += generator.check_output(file)
            if not _inside_home(file.path):
                target.problems.append(
                    translate("core", "{path} is outside your home folder and will not be written.").format(
                        path=str(file.path)
                    )
                )
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

    files = [status.file for target in plan.targets for status in target.files]
    settings = {t.generator.id: t.generator.capture_settings(runner) for t in plan.targets}
    snapshot = snapshots.create(theme.name, [f.path for f in files], settings)
    try:
        for file in files:
            write_atomic(file.path, file.content)
        for target in plan.targets:
            target.generator.reload(theme, runner)
    except (ApplyError, OSError) as error:
        restore(snapshot, runner, consume=True)
        if isinstance(error, ApplyError):
            raise
        raise ApplyError(
            translate("core", "Could not write the theme files: {detail}").format(detail=str(error))
        ) from error
    snapshots.prune()
    return ApplyResult(snapshot, plan)


def is_current(plan: Plan, runner) -> bool:
    """Whether an apply would change nothing: every file is already written
    and the desktop already uses it."""
    files = [status for target in plan.targets for status in target.files]
    return (
        bool(files)
        and all(status.state == UNCHANGED for status in files)
        and all(target.generator.is_active(plan.theme, runner) for target in plan.targets)
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


def restore(snapshot: Snapshot, runner, consume: bool = False) -> list[Msg]:
    """Put files and desktop settings back to what the snapshot recorded.

    Returns messages about settings that could not be restored. With
    `consume`, the snapshot is removed afterwards (this is what Undo does).
    """
    snapshots.restore_files(snapshot)
    failures = []
    for target_id, settings in snapshot.settings.items():
        generator = generator_by_id(target_id)
        if generator is None:
            continue
        try:
            generator.restore_settings(settings, runner)
        except ApplyError as error:
            failures.append(error.message)
    if consume:
        snapshots.delete(snapshot)
    return failures
