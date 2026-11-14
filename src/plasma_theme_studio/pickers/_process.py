# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Starting the helper process (`_helper.py`) that draws what only a real KDE plugin
can draw. It runs with the offscreen platform and the software Qt Quick backend, with
core dumps off, with no display of the user's desktop in its environment and under a
time limit, so it can neither show a window nor leave a crash report.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator, Mapping
from pathlib import Path

TIMEOUT = 15  # seconds for one run; a run takes about a second
MODULE = "plasma_theme_studio.pickers._helper"

_LIVE: set[subprocess.Popen] = set()  # the helpers that run now, for terminate_all
_LOCK = threading.Lock()


def terminate_all() -> None:
    """Kill every helper that is running, so that the application can quit at once."""
    with _LOCK:
        live = list(_LIVE)
    for process in live:
        try:
            os.killpg(process.pid, signal.SIGKILL)  # the helper is the leader of its own session
        except (OSError, ProcessLookupError):
            pass


def environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """The helper's environment: the user's, made safe."""
    env = dict(os.environ)
    for name in (
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "QT_QPA_PLATFORMTHEME",
        "QT_STYLE_OVERRIDE",
        "QT_SCALE_FACTOR",
        "QT_FONT_DPI",
        "QT_AUTO_SCREEN_SCALE_FACTOR",
    ):
        env.pop(name, None)
    env.update(
        DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent/pts-no-bus",  # not the user's session
        QT_QPA_PLATFORM="offscreen",
        QT_QUICK_BACKEND="software",
        QML_DISABLE_DISK_CACHE="1",
        KDE_DEBUG="1",  # no crash dialog from KDE's handler
    )
    package_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [package_root, env.get("PYTHONPATH", "")]))
    env.update(extra or {})
    return env


def command(mode: str, spec: Path, out: Path) -> list[str]:
    """The command line: the running interpreter (the one that has the KDE plugins
    the user's Qt uses), under `prlimit` when there is one."""
    argv = [sys.executable, "-m", MODULE, mode, str(spec), str(out)]
    prlimit = shutil.which("prlimit")
    return [prlimit, "--core=0:0", "--", *argv] if prlimit else argv


def terminate_all_of(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


@contextlib.contextmanager
def run(
    mode: str, spec: Mapping, kdeglobals: str | None = None, extra: Mapping[str, str] | None = None
) -> Iterator[tuple[Path | None, int | None]]:
    """Runs the helper in `mode` ("styles" or "decorations") with the job `spec` and
    yields (output folder, return code): the folder holds the PNG files it wrote, the
    code is None when it timed out, and both are None when it could not be started. The
    folder is deleted afterwards. With `kdeglobals` the helper gets a configuration folder
    of its own that holds only that file, so it reads these colors and nothing of the
    user's settings; without it the helper reads the user's configuration (a Kvantum theme
    is found there). It never writes to either."""
    folder = Path(tempfile.mkdtemp(prefix="pts-helper-"))
    try:
        out = folder / "out"
        out.mkdir()
        spec_file = folder / "spec.json"
        spec_file.write_text(json.dumps(spec), "utf-8")
        env = dict(extra or {})
        # QML and the style plugins keep caches; they go to the run's own folder.
        env["XDG_CACHE_HOME"] = str(folder / "cache")
        if kdeglobals is not None:
            config = folder / "config"
            config.mkdir()
            (config / "kdeglobals").write_text(kdeglobals, "utf-8")
            env["XDG_CONFIG_HOME"] = str(config)
            env["XDG_CONFIG_DIRS"] = str(folder / "etc")
        try:
            process = subprocess.Popen(  # noqa: S603
                command(mode, spec_file, out),
                env=environment(env),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=folder,
                start_new_session=True,
            )
        except OSError:
            yield None, None
            return
        with _LOCK:
            _LIVE.add(process)
        try:
            code = process.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            terminate_all_of(process)
            code = None
        finally:
            with _LOCK:
                _LIVE.discard(process)
        yield out, code
    finally:
        shutil.rmtree(folder, ignore_errors=True)
