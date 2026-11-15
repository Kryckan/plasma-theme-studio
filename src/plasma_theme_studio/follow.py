# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Follow mode: the colors of the desktop follow a pywal or matugen palette file.

While it is on, every change of the palette file makes new colors with the same mapping and the same
automatic contrast correction as Import Colors (the choices made in the mapping dialog are kept) and puts
them on the desktop. Only the colors are touched: a color scheme of its own, called "<theme> Palette",
and the accent color override. Shapes, shadows, fonts, panels and artwork stay as they are, and the theme
file itself is never written.

Switching it on takes ONE snapshot of everything follow mode can write (the scheme file, the state file,
the autostart entry, the color settings and the files the desktop's daemons write in answer). Automatic
changes take none. Switching it off, or an undo of that snapshot, goes back to the state before.

It works with the window closed: `plasma-theme-studio follow` is a small watcher process. The switch
writes an XDG autostart entry, so Plasma starts the watcher at login, and removes it again. (A systemd
user unit would need `systemctl --user enable`, which makes links in a folder the snapshot does not
know and starts before the graphical session is ready; one `.desktop` file is a plain file in the
snapshot, and Plasma starts it when the session is up, with the display and the bus in its environment.)
The watcher looks at the palette file's size, time and identity every `POLL` seconds (one `stat` call,
no CPU in between), waits until a burst of writes has stopped, and ends by itself when the state file is
gone: that is how switching off, or an undo, stops it.
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import APP_DIR, palette, paths, safefile, writelock
from .apply import engine
from .apply import snapshot as snapshots
from .generators import ApplyError, generator_by_id
from .messages import Msg, translate
from .model.theme import Theme, write_atomic

POLL = 2.0  # seconds between two looks at the palette file; never faster than once a second
DEBOUNCE = 1.5  # seconds the file must have stayed as it is before it is read
SUFFIX = " Palette"  # the color scheme is called "<theme name> Palette"
AUTOSTART_NAME = "plasma-theme-studio-follow.desktop"
STATE_LIMIT = 200_000  # bytes; the state file is a few KB
SOURCE_KINDS = ("pywal", "matugen")
MARK = "X-PlasmaThemeStudio-Follow=true"
TARGETS = ("colors", "accent")  # the generators follow mode runs


class FollowError(Exception):
    """Something stopped follow mode; `message` says what, in words for a person."""

    def __init__(self, message: Msg):
        self.message = message
        super().__init__(str(message))


# ------------------------------------------------------------------ the state file


def state_path() -> Path:
    return paths.config_home() / APP_DIR / "follow.json"


def autostart_path() -> Path:
    return paths.config_home() / "autostart" / AUTOSTART_NAME


@dataclass
class State:
    """What the watcher needs: the palette file, how its colors are mapped, which snapshot is the
    "before" and what was applied last."""

    name: str  # the theme's name; the scheme is called name + SUFFIX
    variant: str  # "light" or "dark"
    kind: str  # "pywal" or "matugen"
    source: str  # the palette file
    overrides: dict[str, str] = field(default_factory=dict)  # role -> the palette color it is taken from
    snapshot: str = ""  # the id of the snapshot taken when it was switched on
    applied_colors: dict[str, str] = field(default_factory=dict)
    applied_at: str = ""

    def to_text(self) -> str:
        data = {"version": 1, **self.__dict__}
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    @property
    def source_path(self) -> Path:
        return Path(self.source)


def _parse_state(text: str) -> State | None:
    try:
        data = json.loads(text)
        strings = ("name", "variant", "kind", "source", "snapshot", "applied_at")
        if not isinstance(data, dict) or not all(isinstance(data.get(key, ""), str) for key in strings):
            return None
        colors, overrides = data.get("applied_colors", {}), data.get("overrides", {})
        for table in (colors, overrides):
            if not isinstance(table, dict) or not all(
                isinstance(k, str) and isinstance(v, str) and len(v) < 100 for k, v in table.items()
            ):
                return None
        state = State(
            name=data["name"],
            variant=data["variant"],
            kind=data["kind"],
            source=data["source"],
            overrides=overrides,
            snapshot=data.get("snapshot", ""),
            applied_colors=colors,
            applied_at=data.get("applied_at", ""),
        )
    except (ValueError, KeyError, RecursionError):
        return None
    if state.variant not in ("light", "dark") or state.kind not in SOURCE_KINDS:
        return None
    if not state.name or not state.source:
        return None
    return state


def load_state() -> State | None:
    """The state of follow mode, or None when it is off (or the file cannot be used)."""
    raw = safefile.read_regular(state_path(), STATE_LIMIT)
    if raw is None:
        return None
    try:
        return _parse_state(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return None


def save_state(state: State) -> None:
    write_atomic(state_path(), state.to_text())


def is_on() -> bool:
    return load_state() is not None


# ------------------------------------------------------------------ palettes


def default_source(runner) -> palette.PaletteFile | None:
    """The palette file to follow: one that exists, else the place where an installed tool writes."""
    found = palette.available_sources()
    if found:
        return found[0]
    if runner.which("wal"):
        return palette.PaletteFile("pywal", paths.cache_home() / "wal" / "colors.json")
    if runner.which("matugen"):
        return palette.PaletteFile("matugen", paths.cache_home() / "matugen" / "colors.json")
    return None


def offered(runner) -> bool:
    """Whether follow mode has a palette to follow: a palette file exists or pywal or matugen is installed."""
    return default_source(runner) is not None


def read_palette_text(path: Path) -> str | None:
    """The text of a palette file, never more than the import's size limit is read; None when it is
    missing, no regular file, too large or no text."""
    raw = safefile.read_regular(path, palette.MAX_FILE_BYTES)
    if raw is None or b"\0" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def detect_kind(text: str) -> str | None:
    """ "pywal" or "matugen" for the text of a palette file, None when it is neither."""
    if palette.from_pywal_text(text).ok:
        return "pywal"
    if palette.from_matugen_text(text).ok:
        return "matugen"
    return None


def _parse(kind: str, text: str) -> palette.PaletteResult:
    return palette.from_pywal_text(text) if kind == "pywal" else palette.from_matugen_text(text)


def source_slots(kind: str, text: str) -> dict[str, str]:
    """The colors the palette file itself has, by name ("background", "color4"; matugen's roles)."""
    data = palette._parse_json(text)
    if isinstance(data, Msg):
        return {}
    slots: dict[str, str] = {}
    if kind == "pywal":
        for table in ("special", "colors"):
            values = data.get(table)
            for key, value in (values if isinstance(values, dict) else {}).items():
                color = palette._color(value)
                if color is not None and isinstance(key, str):
                    slots[key] = color.hex
        return slots
    colors = data.get("colors") if isinstance(data.get("colors"), dict) else data
    modes = palette._matugen_modes(colors)
    chosen = modes.get("dark") or modes.get("light") or {}
    return {role: color.hex for role, color in chosen.items()}


def overrides_from_choice(
    kind: str, text: str, mapped: dict[str, str], chosen: dict[str, str]
) -> dict[str, str]:
    """The choices a person made in the mapping dialog, as role -> the palette color the role is taken
    from, so that they hold for the next palette too. A role left as mapped, or set to a color that no
    color of the palette file has (a derived one), is not kept: it follows the automatic mapping."""
    slots = source_slots(kind, text)
    found: dict[str, str] = {}
    for role in palette.ROLES:
        if role not in chosen or chosen[role] == mapped.get(role):
            continue
        name = next((name for name, color in slots.items() if color == chosen[role]), None)
        if name is not None:
            found[role] = name
    return found


def colors_from(state: State, text: str) -> dict[str, str] | Msg:
    """The twelve colors for the palette text, or why there are none: the automatic mapping, the choices
    of the person on top, then the contrast correction of Import Colors."""
    result = _parse(state.kind, text)
    if not result.ok:
        return result.error or translate("core", "The file does not hold a color palette.")
    mapped = dict(result.dark if state.variant == "dark" else result.light)
    slots = source_slots(state.kind, text) if state.overrides else {}
    for role, slot in state.overrides.items():
        if role in palette.ROLES and slot in slots:
            mapped[role] = slots[slot]
    return palette.ensure_contrast(mapped)


# ------------------------------------------------------------------ applying


def follow_theme(state: State, colors: dict[str, str]) -> Theme:
    """A theme that only holds a name and the colors: all the colors targets read."""
    theme = Theme()
    theme.set("meta", "name", state.name + SUFFIX)
    for role, value in colors.items():
        if role in palette.ROLES:
            theme.set("colors", role, value)
    theme.set("colors", "accent_from_wallpaper", False)
    return theme


def _plan(theme: Theme, runner) -> list[engine.TargetPlan]:
    """The plans of the color targets; raises FollowError when they cannot run."""
    problems = list(theme.problems())
    if os.geteuid() == 0:
        problems.append(translate("core", "Plasma Theme Studio must not be run as root."))
    targets = []
    if not problems:
        for target_id in TARGETS:
            plan = engine._plan_target(generator_by_id(target_id), theme, runner)
            problems += plan.problems
            problems += [
                translate("core", "{path} already exists and was not made by Plasma Theme Studio.").format(
                    path=str(status.file.path)
                )
                for status in plan.files
                if status.state == engine.FOREIGN
            ]
            targets.append(plan)
    if problems:
        raise FollowError(problems[0])
    return [target for target in targets if target.wanted]


def _write_and_reload(theme: Theme, runner) -> bool:
    """Put the colors on the desktop. Returns False when the desktop already had them. Nothing is
    snapshotted here: a failure puts the scheme file back as it was and raises FollowError."""
    targets = _plan(theme, runner)
    files = [status.file for target in targets for status in target.files]
    before = {file.path: safefile.read_regular(file.path, 2_000_000) for file in files}
    changed = False
    try:
        for file in files:
            if before[file.path] != file.content.encode("utf-8"):
                write_atomic(file.path, file.content)
                changed = True
        for target in targets:
            if not changed and engine._settled(target, theme, runner):
                continue
            changed = True
            target.generator.reload(theme, runner)
    except (ApplyError, OSError) as error:
        for path, content in before.items():
            try:
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    write_atomic(path, content)
            except OSError:
                pass
        message = error.message if isinstance(error, ApplyError) else str(error)
        raise FollowError(
            translate("core", "The colors could not be put on the desktop: {detail}").format(
                detail=str(message)
            )
        ) from error
    return changed


def is_plasma_session(env=None) -> bool:
    """Whether this is a Plasma session with a display: the colors are never applied elsewhere."""
    env = os.environ if env is None else env
    desktops = [name.strip().upper() for name in env.get("XDG_CURRENT_DESKTOP", "").split(":")]
    return "KDE" in desktops and bool(env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"))


@dataclass(frozen=True)
class Outcome:
    """What one look at the palette came to: "applied", "same" (nothing to do), "ignored" or "failed"."""

    kind: str
    message: Msg | None = None


def _still_on(state: State) -> bool:
    """Whether follow mode is still on with the snapshot `state` was made for."""
    current = load_state()
    return current is not None and current.snapshot == state.snapshot


def apply_palette(
    state: State, runner, force: bool = False, env=None, now: datetime | None = None
) -> Outcome:
    """Read the palette file once and, when its colors are new (or `force`), put them on the desktop.
    Takes no snapshot. The state is saved with what was applied."""
    if not is_plasma_session(env):
        return Outcome(
            "ignored", translate("core", "This is not a Plasma session, so no colors were applied.")
        )
    text = read_palette_text(state.source_path)
    if text is None:
        return Outcome("ignored", translate("core", "The palette file cannot be read."))
    colors = colors_from(state, text)
    if isinstance(colors, Msg):
        return Outcome("ignored", colors)
    if colors == state.applied_colors and not force:
        return Outcome("same")
    # The write lock is held from the check to the saved state: an undo or a switch-off waits for it, so
    # none can land in the middle of the write and leave the colors of this change behind it.
    try:
        with writelock.exclusive():
            if not _still_on(state):  # switched off, or undone, while the palette was being read
                return Outcome("ignored", translate("core", "Follow mode was switched off."))
            try:
                changed = _write_and_reload(follow_theme(state, colors), runner)
            except FollowError as error:
                return Outcome("failed", error.message)
            state.applied_colors = colors
            state.applied_at = (now or datetime.now()).isoformat(timespec="seconds")
            if _still_on(state):  # not needed while the lock holds; a state file must never come back
                try:
                    save_state(state)
                except OSError:
                    pass  # the colors are on the desktop; the next change is compared with an older state
    except writelock.Busy as busy:  # an undo is writing: the watcher asks again at its next look
        return Outcome("busy", busy.message)
    return Outcome("applied" if changed else "same")


# ------------------------------------------------------------------ switching on and off


def launcher() -> list[str]:
    """The command that starts this app: the installed one, the checkout's launcher, or Python itself."""
    installed = shutil.which("plasma-theme-studio")
    if installed:
        return [installed]
    checkout = Path(__file__).resolve().parents[2] / "plasma-theme-studio"
    if checkout.is_file() and os.access(checkout, os.X_OK):
        return [str(checkout)]
    return [sys.executable, "-m", "plasma_theme_studio"]


def _quoted(argument: str) -> str:
    """One argument of an Exec line (Desktop Entry spec: quote what has spaces or reserved characters)."""
    if argument and not any(c in argument for c in " \t\n\"'\\><~|&;$*?#()`%"):
        return argument
    escaped = argument.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return '"' + escaped.replace("%", "%%") + '"'


def _ours(path: Path) -> bool:
    """Whether the autostart entry at `path` was written by follow mode."""
    raw = safefile.read_regular(path, 10_000)
    return raw is not None and MARK in raw.decode("utf-8", errors="replace").splitlines()


def autostart_text() -> str:
    """The autostart entry. Raises FollowError when the launcher's path has a character a `.desktop`
    file cannot hold (a line break, say): it would make lines of its own."""
    parts = [*launcher(), "follow"]
    if any(ord(c) < 32 or ord(c) == 127 for part in parts for c in part):
        raise FollowError(
            translate("core", "The path of this program has a character that an autostart entry cannot hold.")
        )
    command = " ".join(_quoted(part) for part in parts)
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Plasma Theme Studio palette watcher\n"
        "Comment=Keeps the desktop colors in step with the pywal or matugen palette\n"
        f"Exec={command}\n"
        "Icon=preferences-desktop-color\n"
        "OnlyShowIn=KDE;\n"
        "NoDisplay=true\n"
        "X-KDE-autostart-phase=2\n"
        f"{MARK}\n"
    )


@dataclass(frozen=True)
class Switched:
    """The answer of `enable` and `disable`: what to tell the person, and what could not be put back."""

    message: Msg
    failures: tuple = ()
    applied: bool = False


def enable(
    theme: Theme,
    runner,
    source: palette.PaletteFile | None = None,
    variant: str | None = None,
    overrides: dict[str, str] | None = None,
) -> Switched:
    """Switch follow mode on for `theme` (only its name and light or dark are used). One snapshot is
    taken first. Already on: the choices are changed, with no new snapshot. Raises FollowError, with
    everything put back, when it cannot be switched on."""
    source = source or default_source(runner)
    if source is None:
        raise FollowError(translate("core", "There is no pywal or matugen palette to follow."))
    if variant not in ("light", "dark"):
        variant = "dark" if theme.color("window").is_dark else "light"
    text = read_palette_text(source.path)
    kind = detect_kind(text) if text is not None else source.kind
    if kind not in SOURCE_KINDS:
        raise FollowError(translate("core", "The file is not a pywal or matugen color file."))
    state = State(theme.name, variant, kind, str(source.path), dict(overrides or {}))
    existing = load_state()
    if existing is not None:
        state.name = existing.name  # one scheme file: its name stays the one the snapshot knows
    colors = colors_from(state, text) if text is not None else None
    if isinstance(colors, Msg):
        raise FollowError(colors)
    if not is_plasma_session():
        raise FollowError(
            translate("core", "This is not a Plasma session, so the colors cannot be followed.")
        )
    # a theme that holds the colors the desktop has now, to check the target can run at all
    probe = follow_theme(state, colors or {role: theme.get("colors", role) for role in palette.ROLES})
    _plan(probe, runner)
    autostart_text()  # refuses a launcher path that cannot be written, before anything is touched
    if existing is None and autostart_path().exists() and not _ours(autostart_path()):
        raise FollowError(
            translate("core", "{path} already exists and was not made by Plasma Theme Studio.").format(
                path=str(autostart_path())
            )
        )
    if existing is not None:
        state.snapshot = existing.snapshot
        state.applied_colors = existing.applied_colors if existing.source == state.source else {}
    else:
        state.snapshot = _take_snapshot(probe, runner)
    try:
        write_atomic(autostart_path(), autostart_text())
        save_state(state)
        applied = False
        if colors is not None:
            outcome = apply_palette(state, runner, force=True)
            if outcome.kind == "failed":
                raise FollowError(outcome.message)
            applied = outcome.kind == "applied"
    except (FollowError, OSError) as error:
        if existing is None:
            _put_back(state.snapshot, runner)
        message = (
            error.message
            if isinstance(error, FollowError)
            else translate("core", "Could not write the files of follow mode: {detail}").format(
                detail=str(error)
            )
        )
        raise FollowError(message) from error
    try:
        runner.launch([*launcher(), "follow"])
    except OSError:
        pass  # the autostart entry starts it at the next login; the colors are already applied
    return Switched(
        translate("core", "Following the palette in {path}.").format(path=str(source.path))
        if colors is not None
        else translate("core", "Following the palette. Nothing has been written to {path} yet.").format(
            path=str(source.path)
        ),
        applied=applied,
    )


def _take_snapshot(theme: Theme, runner) -> str:
    """The one snapshot of follow mode: every file it can write, and the settings it can change."""
    files = [state_path(), autostart_path()]
    files += [file.path for target_id in TARGETS for file in generator_by_id(target_id).files(theme)]
    settings = {target_id: generator_by_id(target_id).capture_settings(runner) for target_id in TARGETS}
    try:
        snapshot = snapshots.create(theme.name + SUFFIX, files, settings)
    except OSError as error:
        raise FollowError(
            translate("core", "Could not save the snapshot, so nothing was changed: {detail}").format(
                detail=str(error)
            )
        ) from error
    snapshot = snapshots.set_reached(snapshot, list(TARGETS)) or snapshot
    snapshots.prune()
    return snapshot.id


def _put_back(snapshot_id: str, runner) -> list[Msg]:
    """Undo the snapshot of a switch-on that did not finish, and drop it when everything is back."""
    snapshot = snapshots.get(snapshot_id)
    if snapshot is None:
        return []
    failures = engine.restore(snapshot, runner, only=set(TARGETS))
    if not failures:
        snapshots.delete(snapshot)
    return failures


def disable(runner) -> Switched:
    """Switch follow mode off. The watcher writes nothing meanwhile (`writelock`). When its snapshot is
    the newest one, the desktop goes back to how it was before it was switched on (this is an undo of
    that snapshot). When something was applied after it,
    that is not undone behind the person's back: following stops, the colors stay, and the snapshot
    stays in the list for Undo."""
    try:
        with writelock.exclusive():
            return _disable(runner)
    except writelock.Busy as busy:
        return Switched(translate("core", "Follow mode was not switched off."), (busy.message,))


def _disable(runner) -> Switched:
    state = load_state()
    if state is None:
        return Switched(translate("core", "Follow mode is off."))
    snapshot = snapshots.get(state.snapshot) if state.snapshot else None
    newest = snapshots.latest()
    if snapshot is not None and newest is not None and newest.id == snapshot.id:
        failures = engine.restore(snapshot, runner, consume=True)
        if failures:
            return Switched(
                translate(
                    "core",
                    "Follow mode is off, but not everything could be put back. "
                    "The snapshot is kept, so Undo can try again.",
                ),
                tuple(failures),
            )
        return Switched(
            translate(
                "core", "Follow mode is off. The desktop is back to how it was before you switched it on."
            )
        )
    state_path().unlink(missing_ok=True)
    try:
        if _ours(autostart_path()):
            autostart_path().unlink(missing_ok=True)
    except OSError:
        pass
    snapshots.remove_empty_dirs([state_path().parent])
    return Switched(
        translate(
            "core",
            "Follow mode is off. The colors stay as the palette made them, because something else was "
            "applied after you switched it on. Undo goes back step by step.",
        )
    )


@dataclass(frozen=True)
class Status:
    on: bool
    state: State | None = None
    running: bool = False


def status() -> Status:
    state = load_state()
    return Status(state is not None, state, watcher_running())


# ------------------------------------------------------------------ the watcher


def lock_path() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    folder = Path(base) if base and Path(base).is_dir() else Path(tempfile.gettempdir())
    return folder / f"plasma-theme-studio-follow-{os.getuid()}.lock"


def _try_lock(path: Path):
    """An open, locked lock file, or None when another watcher holds it."""
    try:
        # never through a link somebody planted, never waiting for a pipe in its place
        descriptor = os.open(
            path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600
        )
        handle = os.fdopen(descriptor, "a+")
    except OSError:
        return None
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def watcher_running() -> bool:
    handle = _try_lock(lock_path())
    if handle is None:
        return True
    handle.close()  # the lock goes with the file handle
    return False


def signature(path: Path) -> tuple | None:
    """Which version of a file this is (identity, time, size); None when it is not there. A palette that
    is replaced by a new file has another identity, one that is written in place another time."""
    try:
        info = os.stat(path)
    except (OSError, ValueError):
        return None
    return (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size)


class Watcher:
    """Looks at the palette file; `tick` is one look. Time and logging are given, so a test needs no
    waiting. A new version of the file is read only after it has stayed as it is for `DEBOUNCE` seconds."""

    def __init__(
        self,
        runner,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] = print,
        env=None,
    ):
        self.runner, self.clock, self.log, self.env = runner, clock, log, env
        self.state: State | None = None
        self.state_signature: tuple | None = None
        self.pending: tuple | None = None
        self.pending_since = 0.0
        self.done: tuple | None = None  # the version of the palette file that has been dealt with

    def tick(self) -> bool:
        """One look. False means the watcher is done: follow mode was switched off."""
        seen = signature(state_path())
        if seen is None:
            return False
        if seen != self.state_signature:
            self.state = load_state()
            if self.state is None:
                return False
            self.state_signature = seen
            self.pending = self.done = None
        state = self.state
        version = signature(state.source_path)
        if version is None:
            self.pending = None
            return True
        if version == self.done:
            return True
        now = self.clock()
        if version != self.pending:
            self.pending, self.pending_since = version, now
            return True
        if now - self.pending_since < DEBOUNCE:
            return True
        self.done = version
        outcome = apply_palette(state, self.runner, env=self.env)
        if outcome.kind == "busy":
            self.done = None  # not dealt with: the next look tries this version again
        self.state_signature = signature(state_path())  # our own write of the state is no change
        if outcome.kind == "applied":
            self.log(f"follow: applied the colors of {state.source} ({len(state.applied_colors)} colors)")
        elif outcome.kind != "same":
            self.log(f"follow: {outcome.kind}: {outcome.message}")
        return True


def watch(runner, log: Callable[[str], None] | None = None) -> int:
    """Run the watcher until SIGTERM, SIGINT or until follow mode is switched off. A second watcher
    does not start. Returns the exit code."""

    def say(line: str) -> None:
        print(line, file=sys.stderr, flush=True)

    log = log or say
    if not is_plasma_session():
        log("follow: this is not a Plasma session; nothing is watched")
        return 0
    lock = _try_lock(lock_path())
    if lock is None:
        log("follow: another watcher is already running")
        return 0
    stop = threading.Event()
    numbers = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    earlier = {number: signal.signal(number, lambda *_: stop.set()) for number in numbers}
    try:
        watcher = Watcher(runner, log=log)
        if load_state() is None:
            log("follow: follow mode is off; nothing to do")
            return 0
        log("follow: watching")
        while not stop.is_set() and watcher.tick():
            stop.wait(POLL)  # a signal wakes it at once; between looks it sleeps
        log("follow: stopped")
        return 0
    finally:
        for number, handler in earlier.items():
            signal.signal(number, handler)
        lock.close()


def run_once(runner) -> tuple[int, Msg]:
    """Apply the palette as it is now and finish: (exit code, what to say)."""
    state = load_state()
    if state is None:
        return 1, translate(
            "core", "Follow mode is off. Switch it on first: plasma-theme-studio follow on FILE"
        )
    outcome = apply_palette(state, runner, force=True)
    if outcome.kind == "applied":
        return 0, translate("core", "Applied the colors of {path}.").format(path=state.source)
    if outcome.kind == "same":
        return 0, translate("core", "The desktop already has these colors. Nothing was changed.")
    return 1, outcome.message or translate("core", "Nothing was changed.")
