# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing a picture the app did not make itself, in a child process that cannot hurt the app.

An SVG that somebody drew (own artwork for a frame, one from a theme archive) can cost Qt any amount
of time and memory however small it is, and Qt's SVG renderer has no limit of its own. So such a picture
is only ever drawn by `ui/frame_child.py`, a separate program that is given the picture and a job on its
standard input, has an address-space cap and a CPU limit of its own, and is killed when it has not
answered within `TIMEOUT` seconds (the pattern of `scripts/capped`). It answers with one small PNG or
fails; nothing it does can reach the window. The answer is cached by the hash of the picture and the job,
a failure included. A timeout, a child killed from outside (the kernel's out-of-memory killer) and a child
that could not be started are only believed for `RETRY_AFTER` seconds (`Outcome.retry`): the machine may
just have been busy, so the picture is tried again after that. A picture that makes the child fail by
itself stays failed.

Nothing here needs Qt. `render` blocks: call it from a worker thread, never from the window's thread.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

TIMEOUT = 6.0  # seconds until the child is killed
MEMORY = 1 << 30  # bytes of address space the child may use
PAD = 30  # logical pixels around a frame in its tile: room for the shadow
MAX_TILES = 8
MAX_SIDE = 1024  # logical pixels, one side of a frame
MAX_RATIO = 4.0  # device pixel ratio
MAX_PNG = 16 << 20  # bytes of answer that are believed
CACHE_SIZE = 64
RETRY_AFTER = 300.0  # seconds a timeout or an outside failure is remembered

TIMED_OUT, FAILED = "timeout", "failed"

_CACHE: OrderedDict[str, Outcome] = OrderedDict()
_FAILED_AT: dict[str, float] = {}  # when each answer was found (time.monotonic)
_LOCK = threading.Lock()


@dataclass(frozen=True)
class Outcome:
    """What the child came back with: the PNG, or why there is none (`TIMED_OUT` or `FAILED`)."""

    png: bytes | None = None
    failure: str | None = None
    retry: bool = False  # the failure may be the machine's fault, not the picture's: ask again later

    @property
    def ok(self) -> bool:
        return self.png is not None


def tiles_job(tiles: list[tuple[int, int, bool]], ratio: float = 1.0) -> dict:
    """The job "draw these frames": `tiles` are (width, height, with guides) in logical pixels, each frame
    drawn with `PAD` pixels of room around it, one under the other in one picture."""
    return {"ratio": float(ratio), "tiles": [[int(w), int(h), bool(g)] for w, h, g in tiles]}


def layout(job: dict) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """(width, height, [(x, y, width, height) of each tile]) of the picture the child makes, in device
    pixels. Raises ValueError for a job that asks for too much: the child and the caller both check."""
    try:
        ratio = float(job["ratio"])
        tiles = [(int(w), int(h), bool(g)) for w, h, g in job["tiles"]]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("not a job") from error
    if not 0 < ratio <= MAX_RATIO or not 0 < len(tiles) <= MAX_TILES:
        raise ValueError("a job of this size is not drawn")
    cells = []
    for width, height, _guides in tiles:
        if not 0 < width <= MAX_SIDE or not 0 < height <= MAX_SIDE:
            raise ValueError("a frame of this size is not drawn")
        cells.append((round((width + 2 * PAD) * ratio), round((height + 2 * PAD) * ratio)))
    sheet_width = max(w for w, _ in cells)
    places, y = [], 0
    for cell_width, cell_height in cells:
        places.append((0, y, cell_width, cell_height))
        y += cell_height
    return sheet_width, y, places


def key(svg: bytes, job: dict) -> str:
    """The cache key of a picture and a job: a hash of their content."""
    digest = hashlib.sha256()
    digest.update(json.dumps(job, sort_keys=True).encode())
    digest.update(b"\0")
    digest.update(svg)
    return digest.hexdigest()


def cached(svg: bytes, job: dict) -> Outcome | None:
    """The answer for this picture and job when it is known already."""
    with _LOCK:
        name = key(svg, job)
        found = _CACHE.get(name)
        if found is not None and found.retry:
            if time.monotonic() - _FAILED_AT.get(name, 0.0) > RETRY_AFTER:
                del _CACHE[name]
                return None
        if found is not None:
            _CACHE.move_to_end(name)
        return found


def forget() -> None:
    """Empty the cache (tests)."""
    with _LOCK:
        _CACHE.clear()
        _FAILED_AT.clear()


def child_command() -> list[str]:
    """The program that draws. `-P` keeps the current folder out of its module path."""
    return [sys.executable, "-P", "-m", "plasma_theme_studio.ui.frame_child"]


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"  # never a window, never the desktop's display
    env["KDE_DEBUG"] = "1"  # no crash notification when it is killed
    root = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def _run(svg: bytes, job: dict, timeout: float) -> Outcome:
    payload = json.dumps(job).encode() + b"\n" + svg
    command = [*child_command(), str(MEMORY), str(int(timeout) + 2)]
    try:
        child = subprocess.Popen(  # noqa: S603 - our own program, no shell
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_environment(),
            cwd="/",
            start_new_session=True,  # so that everything it started goes with it
        )
    except OSError:
        return Outcome(failure=FAILED, retry=True)  # no process: EAGAIN, no memory
    try:
        answer, _ = child.communicate(payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(child)
        return Outcome(failure=TIMED_OUT, retry=True)
    except OSError:
        _kill(child)
        return Outcome(failure=FAILED, retry=True)
    if child.returncode == -signal.SIGKILL:  # nobody here sent it: the kernel's out-of-memory killer
        return Outcome(failure=FAILED, retry=True)
    if child.returncode != 0 or not answer.startswith(b"\x89PNG\r\n\x1a\n") or len(answer) > MAX_PNG:
        return Outcome(failure=FAILED)
    return Outcome(png=answer)


def _kill(child: subprocess.Popen) -> None:
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except OSError:
        child.kill()
    try:
        child.communicate(timeout=2)
    except (subprocess.TimeoutExpired, OSError):
        pass


def render(svg: bytes, job: dict, timeout: float | None = None, fresh: bool = False) -> Outcome:
    """Draw `svg` as `job` says, in the child. Blocks up to `timeout` seconds (`TIMEOUT`); never raises.
    `fresh` skips the cache's answer. Otherwise answers from the cache when it can, and keeps what it
    found (a failure too; a timeout for a while)."""
    try:
        layout(job)
    except ValueError:
        return Outcome(failure=FAILED)
    found = None if fresh else cached(svg, job)
    if found is not None:
        return found
    outcome = _run(svg, job, TIMEOUT if timeout is None else timeout)
    with _LOCK:
        name = key(svg, job)
        _CACHE[name] = outcome
        _FAILED_AT[name] = time.monotonic()
        while len(_CACHE) > CACHE_SIZE:
            _FAILED_AT.pop(_CACHE.popitem(last=False)[0], None)
    return outcome


def probe(svg: bytes, fresh: bool = False) -> Outcome:
    """Whether the picture can be drawn at all: the same job the frame thumbnail uses (so a picture that
    passes here is drawn from the cache afterwards), with the colors the file has. `fresh` asks the child
    again even when the cache holds an answer."""
    return render(svg, THUMBNAIL, fresh=fresh)


# The job of a card's thumbnail: one frame of 116 x 50 in a tile of 176 x 110.
THUMBNAIL = tiles_job([(116, 50, False)])
