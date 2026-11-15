# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What KDE's tools and daemons write on their own when an apply changes the desktop.

`plasma-apply-colorscheme` rewrites the color groups of `kdeglobals`; the GTK settings daemon of KDE
(kde-gtk-config) rewrites the GTK color sheets and settings files and `xsettingsd.conf` in its own time
after that; Qt's platform theme keeps `Trolltech.conf`. None of this is part of the theme, so the
snapshot takes a copy of it before an apply and an undo puts it back last: after the settings are
back, and after the daemon has finished reacting to them. A file that did not exist is removed again.

Only the color groups of `kdeglobals` are put back (the rest of the file belongs to the user and to
the other parts, which restore their own keys), and the file itself goes if it did not exist before
and nothing else is left in it.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path

from .. import paths
from ..model.theme import write_atomic
from . import desktop

MAX_FILE = 2_000_000  # bytes; a larger file is not ours
MAX_TREE = 400  # files in a folder that is kept as a whole
# The targets after which a daemon rewrites the GTK files, and the ones that change the color groups
# of kdeglobals. An undo puts back only what the applies it undoes could have changed, so a color
# scheme chosen in System Settings since is not touched by the undo of a font.
COLOR_TARGETS = frozenset({"colors", "accent", "night_variants", "night_mode"})
SIDE_TARGETS = COLOR_TARGETS | {"gtk", "fonts", "icons", "cursors", "cursor_size", "app_style"}
QUIET = 0.5  # seconds between two looks at the files the daemon writes
QUIET_ROUNDS = 12  # at most this many looks

# The group headers of kdeglobals that the color tools own, and the keys of other groups.
OWNED_GROUPS = ("[ColorEffects:", "[Colors:")
OWNED_KEYS = {
    "[General]": ("ColorScheme", "ColorSchemeHash"),
    "[KDE]": ("contrast", "frameContrast", "LookAndFeelPackage"),
    "[WM]": (
        "activeBackground",
        "activeBlend",
        "activeForeground",
        "inactiveBackground",
        "inactiveBlend",
        "inactiveForeground",
    ),
}


def watched() -> tuple[list[Path], list[Path]]:
    """The files and the folders (kept whole) that a daemon writes, in the current home."""
    config, home = paths.config_home(), Path.home()
    files = [
        config / "xsettingsd" / "xsettingsd.conf",
        config / "Trolltech.conf",
        config / "gtkrc",
        config / "gtkrc-2.0",
        home / ".gtkrc-2.0",
    ]
    folders = []
    for version in ("gtk-3.0", "gtk-4.0"):
        files += [
            config / version / name
            for name in ("colors.css", "gtk.css", "settings.ini", "window_decorations.css")
        ]
        folders.append(config / version / "assets")
    folders.append(config / "kdedefaults")  # Plasma writes what a Global Theme sets here
    return files, folders


def managed(written) -> set[str]:
    """The watched files that the apply wrote itself: their restore puts them back, not this one."""
    return set(written)


def color_sheets() -> set[str]:
    """The GTK color sheets: a daemon writes them from the color scheme, so only an undo of a color
    change puts them back."""
    return {str(paths.config_home() / version / "colors.css") for version in ("gtk-3.0", "gtk-4.0")}


# ---------------------------------------------------------------- reading


def _digest(path: Path) -> str | None:
    """A hash of a regular file that is not too large, None for anything else."""
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            return "link:" + os.readlink(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _tree_files(folder: Path) -> tuple[list[str], list[str]] | None:
    """The files and sub-folders below `folder` (relative names), None when it is no folder or too big."""
    if folder.is_symlink() or not folder.is_dir():
        return None
    files: list[str] = []
    dirs: list[str] = []
    for base, names, entries in os.walk(folder, followlinks=False):
        here = Path(base).relative_to(folder)
        dirs += [str(here / name) for name in names if not (Path(base) / name).is_symlink()]
        names[:] = [name for name in names if not (Path(base) / name).is_symlink()]
        files += [str(here / name) for name in entries]
        if len(files) > MAX_TREE:
            return None
    return sorted(files), sorted(dirs)


def _missing_parents(path: Path) -> list[str]:
    found = []
    for parent in path.parents:
        if parent.exists():
            break
        found.append(str(parent))
    return found


def capture(store: Path) -> dict:
    """Copy what a later undo must put back into `store` (a folder) and describe it."""
    store.mkdir(parents=True, exist_ok=True)
    files, folders = watched()
    record: dict = {"files": [], "trees": [], "created_dirs": [], "kdeglobals": None}
    count = 0

    def keep(path: Path) -> dict:
        nonlocal count
        entry = {"path": str(path), "existed": False, "stored": None}
        try:
            if _digest(path) is not None and not path.is_symlink():
                count += 1
                entry["stored"] = f"{count}"
                (store / entry["stored"]).write_bytes(path.read_bytes())
                entry["existed"] = True
            elif path.exists() or path.is_symlink():
                entry["untouched"] = True  # a link or a file too large: not ours to change
        except OSError:
            entry["untouched"] = True
        return entry

    for path in files:
        record["files"].append(keep(path))
        record["created_dirs"] += _missing_parents(path)
    for folder in folders:
        listed = _tree_files(folder)
        tree = {"path": str(folder), "existed": listed is not None, "entries": [], "dirs": []}
        if listed is not None:
            tree["entries"] = [keep(folder / name) for name in listed[0]]
            tree["dirs"] = listed[1]
        elif folder.exists() or folder.is_symlink():
            tree["untouched"] = True
        record["trees"].append(tree)
        record["created_dirs"] += _missing_parents(folder)
    record["created_dirs"] = sorted(set(record["created_dirs"]))
    path = paths.config_home() / "kdeglobals"
    try:
        if _regular(path):
            record["kdeglobals"] = {"existed": True, "text": _read(path)}
        elif not os.path.lexists(path):
            record["kdeglobals"] = {"existed": False, "text": ""}
    except (OSError, UnicodeDecodeError):
        record["kdeglobals"] = None
    return record


def _regular(path: Path) -> bool:
    """Whether `path` is a regular file (or a link to one) of a size that is read as a whole. A pipe
    or a device would block the read for ever."""
    try:
        info = path.stat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and info.st_size <= MAX_FILE


def _read(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as stream:
        return stream.read()


# ---------------------------------------------------------------- kdeglobals


def _split(text: str) -> tuple[list[str], list[list]]:
    """The lines before the first group, and the groups as [header, lines]; lines keep their ends."""
    preamble: list[str] = []
    groups: list[list] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped and "=" not in stripped.partition("]")[0]:
            groups.append([stripped, [line]])
        elif groups:
            groups[-1][1].append(line)
        else:
            preamble.append(line)
    return preamble, groups


def _key(line: str) -> str:
    return re.match(r"[^\[=]*", line.strip()).group(0).strip()


def _blank(lines: list[str]) -> bool:
    return all(not line.strip() or line.strip().startswith("[") for line in lines)


def _end(line: str) -> str:
    return line if line.endswith("\n") else line + "\n"


def put_back_colors(current: str, saved: str) -> str:
    """`current` with the color groups and keys that the color tools own as they are in `saved`."""
    old_pre, old_groups = _split(saved)
    del old_pre
    old = {header: lines for header, lines in old_groups}
    pre, groups = _split(current)
    out: list[list] = []
    seen: set[str] = set()
    for header, lines in groups:
        if header.startswith(OWNED_GROUPS):
            if header in old and header not in seen:
                out.append([header, old[header]])
                seen.add(header)
            continue
        keys = OWNED_KEYS.get(header)
        if keys is None:
            out.append([header, lines])
            continue
        old_lines = {_key(line): line for line in old.get(header, [])[1:] if _key(line) in keys}
        kept: list[str] = [lines[0]]
        emitted: set[str] = set()
        for line in lines[1:]:
            name = _key(line)
            if name in keys:
                if name in old_lines and name not in emitted:
                    kept.append(_end(old_lines[name]))
                    emitted.add(name)
                continue
            kept.append(line)
        missing = [old_lines[name] for name in keys if name in old_lines and name not in emitted]
        if missing:
            tail = (
                [kept.pop() for _ in range(len(kept)) if not kept[-1].strip()][::-1] if len(kept) > 1 else []
            )
            kept += [_end(line) for line in missing] + tail
        if not _blank(kept[1:]) or header in old:
            out.append([header, kept])
        seen.add(header)
    for header, lines in old_groups:
        if header in seen:
            continue
        if header.startswith(OWNED_GROUPS):
            out.append([header, lines])
        elif header in OWNED_KEYS:
            owned = [line for line in lines[1:] if _key(line) in OWNED_KEYS[header]]
            if owned:
                out.append([header, [lines[0], *[_end(line) for line in owned], "\n"]])
    text = "".join(pre) + "".join("".join(lines) for _header, lines in out)
    # Taking a group out can leave a blank line at the end that the file did not have.
    ending = len(saved) - len(saved.rstrip("\n"))
    return text.rstrip("\n") + "\n" * ending if text.strip() else ""


def _bare(text: str) -> bool:
    return all(not line.strip() or line.strip().startswith("[") for line in text.splitlines())


def _restore_kdeglobals(record: dict) -> None:
    path = paths.config_home() / "kdeglobals"
    if os.path.lexists(path) and not _regular(path):
        return  # a pipe, a device or something too large is not ours to rewrite
    try:
        current = _read(path) if path.exists() else ""
    except UnicodeDecodeError:
        return
    text = put_back_colors(current, record["text"])
    if not record["existed"] and _bare(text):
        if path.exists() and not path.is_symlink():
            path.unlink()
        elif path.is_symlink():
            write_atomic(path, "")
        return
    if text != current or not path.exists():
        write_atomic(path, text)


# ---------------------------------------------------------------- restoring


def _put_back(entry: dict, store: Path) -> None:
    path = Path(entry["path"])
    if entry.get("untouched"):
        return
    if entry["existed"]:
        saved = (store / entry["stored"]).read_bytes()
        if not path.is_symlink() and path.is_file() and path.read_bytes() == saved:
            return
        write_atomic(path, saved)
    elif path.is_symlink():
        return  # a link that appeared is the user's
    else:
        path.unlink(missing_ok=True)


def _differs(entry: dict, store: Path) -> bool:
    path = Path(entry["path"])
    if entry.get("untouched"):
        return False
    try:
        if entry["existed"]:
            return (
                path.is_symlink()
                or not path.is_file()
                or path.read_bytes() != (store / entry["stored"]).read_bytes()
            )
        return path.exists() or path.is_symlink()
    except OSError:
        return True


def _tree_differs(tree: dict, store: Path) -> bool:
    if tree.get("untouched"):
        return False
    folder = Path(tree["path"])
    if not tree["existed"]:
        return folder.exists()
    listed = _tree_files(folder)
    if listed is None:
        return True
    known = {entry["path"] for entry in tree["entries"]}
    return {str(folder / name) for name in listed[0]} != known or any(
        _differs(entry, store) for entry in tree["entries"]
    )


def _put_back_tree(tree: dict, store: Path) -> None:
    if tree.get("untouched"):
        return
    folder = Path(tree["path"])
    known = {entry["path"] for entry in tree["entries"]}
    listed = _tree_files(folder) if folder.is_dir() and not folder.is_symlink() else None
    for name in listed[0] if listed else ():
        if str(folder / name) not in known:
            (folder / name).unlink(missing_ok=True)
    for entry in tree["entries"]:
        _put_back(entry, store)
    for name in sorted(listed[1] if listed else (), key=lambda n: len(Path(n).parts), reverse=True):
        if name not in tree["dirs"]:
            try:
                (folder / name).rmdir()
            except OSError:
                pass
    if not tree["existed"]:
        try:
            folder.rmdir()
        except OSError:
            pass


def _wait_until_quiet(recorded: list[Path]) -> None:
    """Give a daemon that is still writing the time to finish: wait until none of the files changes
    between two looks. Gives up after a few seconds."""
    last = None
    quiet = 0
    for _ in range(QUIET_ROUNDS):
        now = [_digest(path) for path in recorded]
        quiet = quiet + 1 if now == last else 0
        if quiet >= 2:
            return
        last = now
        desktop.pause(QUIET)


def _sane(record: dict, store: Path) -> tuple[list[dict], list[dict], list[str]]:
    """The entries of a record that point at files this module watches, with stored names that stay in
    `store`. A manifest that was damaged or changed by hand must not make an undo touch other files.
    Raises ValueError for a record of the wrong shape."""
    files, folders = watched()
    known = {str(path) for path in files}
    roots = {str(path) for path in folders}

    def inside(path: str) -> bool:
        return any(path == root or path.startswith(root + os.sep) for root in roots)

    def plain(entry: dict) -> bool:
        stored = entry.get("stored")
        return not entry["existed"] or (
            isinstance(stored, str) and stored.isdigit() and (store / stored).parent == store
        )

    try:
        entries = [e for e in record.get("files", []) if e["path"] in known and plain(e)]
        trees = []
        for tree in record.get("trees", []):
            if tree["path"] not in roots:
                continue
            tree = dict(tree, entries=[e for e in tree.get("entries", []) if inside(e["path"]) and plain(e)])
            tree["dirs"] = [
                d for d in tree.get("dirs", []) if isinstance(d, str) and ".." not in Path(d).parts
            ]
            trees.append(tree)
        parents = {str(parent) for path in [*files, *folders] for parent in path.parents}
        created = [d for d in record.get("created_dirs", []) if d in parents]
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("the record of the side files is damaged") from error
    return entries, trees, created


def to_wait_for(record: dict, store: Path, skip=()) -> list[Path]:
    """The files a daemon may still be writing that `restore` would change: what `wait_until_quiet`
    should watch before it, or [] when it changes nothing (or the record is damaged: `restore` says so)."""
    try:
        entries, trees, _created = _sane(record, store)
        entries = [e for e in entries if e["path"] not in skip]
        differing = any(_differs(entry, store) for entry in entries) or any(
            _tree_differs(t, store) for t in trees
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []
    if not differing:
        return []
    live = [Path(e["path"]) for e in entries if not e.get("untouched")] + [paths.config_home() / "kdeglobals"]
    return live + [Path(t["path"]) for t in trees]


def wait_until_quiet(recorded: list[Path]) -> None:
    """Wait until none of the files changes between two looks (see `_wait_until_quiet`)."""
    _wait_until_quiet(recorded)


def restore(record: dict, store: Path, colors: bool = True, skip=(), wait: bool = True) -> None:
    """Put back what `capture` found. Every file is tried; the first error is raised at the end.
    With `colors` the color groups of kdeglobals are put back as well. The files in `skip` are the
    ones the apply wrote itself: their target puts them back, so they are left alone here. Without
    `wait` the daemons are not waited for: the caller did that once (`to_wait_for`, `wait_until_quiet`)
    for several records."""
    failed: OSError | None = None
    entries, trees, created_dirs = _sane(record, store)
    entries = [e for e in entries if e["path"] not in skip]
    if wait and (recorded := to_wait_for(record, store, skip)):
        _wait_until_quiet(recorded)
    for step in [
        *(lambda e=e: _put_back(e, store) for e in entries),
        *(lambda t=t: _put_back_tree(t, store) for t in trees),
    ]:
        try:
            step()
        except OSError as error:
            failed = failed or error
    saved = record.get("kdeglobals")
    if isinstance(saved, dict) and colors:
        try:
            _restore_kdeglobals(saved)
        except OSError as error:
            failed = failed or error
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("the record of kdeglobals is damaged") from error
    for name in sorted(created_dirs, key=lambda n: len(Path(n).parts), reverse=True):
        try:
            Path(name).rmdir()
        except OSError:
            pass
    if failed:
        raise failed
