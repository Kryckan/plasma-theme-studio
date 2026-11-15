# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One lock that an undo and the follow mode watcher both hold while they write the desktop's files.

Without it the watcher can write a palette's colors into `kdeglobals` and the scheme file just after an
undo has put them back, and the home is no longer what the snapshot recorded. The lock is a file in the
runtime folder (`flock`, so it goes away with a process that dies) and is re-entrant: a restore that
calls another restore takes it once. A holder that is stuck is not waited for longer than `WAIT` seconds
(for the threads of this process and for other processes each); after that `Busy` is raised and nothing
is written: going on without the lock would bring the race back and the work would report success.
"""

from __future__ import annotations

import fcntl
import os
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .messages import translate

WAIT = 30.0  # seconds
# Called once, from the waiting thread, when the lock is held by somebody else (the command line prints it)
on_wait: Callable[[], None] | None = None

_THREADS = threading.RLock()  # the threads of one process; flock does not tell them apart
_DEPTH = 0  # how many times this process holds the lock (guarded by _THREADS)


class Busy(Exception):
    """The lock stayed with another holder for `WAIT` seconds. `message` says so, for the person."""

    def __init__(self) -> None:
        self.message = translate(
            "core",
            "Another part of Plasma Theme Studio, the palette watcher or another undo, is still writing "
            "the desktop's files. Nothing was changed. Try again in a moment.",
        )
        super().__init__(str(self.message))


def lock_file() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    folder = Path(base) if base and Path(base).is_dir() else Path(tempfile.gettempdir())
    return folder / f"plasma-theme-studio-write-{os.getuid()}.lock"


def _acquire(path: Path):
    """An open, locked file, or None when it cannot be opened (then the work goes on without). Raises
    `Busy` when another process holds it for longer than `WAIT`."""
    try:
        # never through a link somebody planted, never waiting for a pipe in its place
        descriptor = os.open(
            path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600
        )
    except OSError:
        return None
    handle = os.fdopen(descriptor, "a+")
    deadline = time.monotonic() + WAIT
    told = False
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError:
            if not told and on_wait is not None:
                told = True
                on_wait()
            if time.monotonic() > deadline:
                handle.close()
                raise Busy from None
            time.sleep(0.05)


@contextmanager
def exclusive() -> Iterator[None]:
    """Hold the write lock for the block. Nested uses in one process take it once. Raises `Busy`."""
    global _DEPTH
    if not _THREADS.acquire(timeout=WAIT):
        raise Busy
    try:
        handle = _acquire(lock_file()) if _DEPTH == 0 else None
        _DEPTH += 1
        try:
            yield
        finally:
            _DEPTH -= 1
            if handle is not None:
                handle.close()  # the lock goes with the file handle
    finally:
        _THREADS.release()
