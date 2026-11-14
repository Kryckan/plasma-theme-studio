# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Snapshots: copies of everything an apply is about to change.

Each snapshot is a directory holding `manifest.json` and the previous
content of every file the apply writes. A directory without a manifest is
an unfinished snapshot and is ignored.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .. import paths
from ..model.theme import write_atomic

KEEP = 20
_MANIFEST = "manifest.json"
_TRIED = "tried"  # an undo of this snapshot has failed once already


@dataclass(frozen=True)
class Snapshot:
    id: str
    directory: Path
    created: str
    theme_name: str
    files: tuple[dict, ...]  # {"path": str, "existed": bool, "stored": str | None}
    settings: dict  # target id -> settings captured by that target's generator
    # Folders that did not exist yet; a restore removes them again if they are empty.
    created_dirs: tuple[str, ...] = ()

    @property
    def created_at(self) -> datetime:
        return datetime.fromisoformat(self.created)


def create(theme_name: str, file_paths: list[Path], settings: dict) -> Snapshot:
    now = datetime.now()
    snapshot_id = now.strftime("%Y%m%d-%H%M%S-%f")
    directory = paths.snapshots_dir() / snapshot_id
    (directory / "files").mkdir(parents=True)
    files = []
    created_dirs: list[str] = []
    for index, path in enumerate(file_paths):
        existed = path.is_file()
        stored = f"files/{index}" if existed else None
        if existed:
            shutil.copy2(path, directory / stored)
        files.append({"path": str(path), "existed": existed, "stored": stored})
        for parent in path.parents:
            if parent.exists():
                break
            if str(parent) not in created_dirs:
                created_dirs.append(str(parent))
    manifest = {
        "created": now.isoformat(timespec="seconds"),
        "theme": theme_name,
        "files": files,
        "settings": settings,
        "created_dirs": created_dirs,
    }
    write_atomic(directory / _MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return _read(directory)


def _read(directory: Path) -> Snapshot | None:
    try:
        data = json.loads((directory / _MANIFEST).read_text(encoding="utf-8"))
        return Snapshot(
            id=directory.name,
            directory=directory,
            created=data["created"],
            theme_name=data["theme"],
            files=tuple(data["files"]),
            settings=data["settings"],
            created_dirs=tuple(data.get("created_dirs", ())),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def list_snapshots() -> list[Snapshot]:
    """All complete snapshots, newest first."""
    root = paths.snapshots_dir()
    if not root.is_dir():
        return []
    found = (_read(d) for d in sorted(root.iterdir(), reverse=True) if d.is_dir())
    return [s for s in found if s is not None]


def latest() -> Snapshot | None:
    snapshots = list_snapshots()
    return snapshots[0] if snapshots else None


def get(snapshot_id: str) -> Snapshot | None:
    return next((s for s in list_snapshots() if s.id == snapshot_id), None)


def restore_files(snapshot: Snapshot) -> None:
    """Put every file back the way it was when the snapshot was made. A file
    that cannot be put back does not stop the others; its error is raised at
    the end."""
    failed: OSError | None = None
    for entry in snapshot.files:
        path = Path(entry["path"])
        try:
            if entry["existed"]:
                write_atomic(path, (snapshot.directory / entry["stored"]).read_bytes())
            else:
                path.unlink(missing_ok=True)
        except OSError as error:
            failed = failed or error
    remove_empty_dirs(Path(d) for d in snapshot.created_dirs)
    if failed:
        raise failed


def remove_empty_dirs(directories) -> None:
    """Remove the given folders if nothing is left in them, deepest first."""
    for directory in sorted(directories, key=lambda d: len(d.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass  # not empty, already gone or not ours to remove


def tried(snapshot: Snapshot) -> bool:
    return (snapshot.directory / _TRIED).exists()


def mark_tried(snapshot: Snapshot) -> None:
    (snapshot.directory / _TRIED).touch()


def delete(snapshot: Snapshot) -> None:
    shutil.rmtree(snapshot.directory, ignore_errors=True)


def prune(keep: int = KEEP) -> None:
    root = paths.snapshots_dir()
    if not root.is_dir():
        return
    complete = {s.id for s in list_snapshots()[:keep]}
    for directory in root.iterdir():
        if directory.is_dir() and directory.name not in complete:
            shutil.rmtree(directory, ignore_errors=True)
