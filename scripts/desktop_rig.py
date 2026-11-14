#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Developer tool: a private, invisible KDE session for trying generated themes.

Nothing here touches the running desktop. A rig is one directory under /tmp that holds its own
HOME, XDG_* folders, D-Bus session bus, a virtual KWin (no window anywhere) and optionally a
plasmashell. Several rigs can run side by side.

Usage (run it with /usr/bin/python3, which has dbus-python and PySide6):

  desktop_rig.py start DIR [--plasmashell] [--size 1280x800] [--render software|default]
  desktop_rig.py run DIR -- COMMAND...      # COMMAND sees the rig's HOME, XDG_*, bus and socket
  desktop_rig.py window DIR [--title T] [--size WxH] [--maximized] [--color RRGGBB]
  desktop_rig.py screenshot DIR OUT.png     # whole virtual screen via KWin ScreenShot2
  desktop_rig.py status DIR
  desktop_rig.py stop DIR

DIR must be new or empty and below /tmp. "start" writes DIR/env (source it in a shell), DIR/pids
("name pid" per line) and DIR/*.log. "run" refuses to start unless HOME is inside DIR and the bus is
the rig's own. Everything that may crash runs under "prlimit --core=1:1" with KDE_DEBUG=1, so no
crash dialog or core dump notification appears. The default render mode is "software"
(QT_QUICK_BACKEND=software, LIBGL_ALWAYS_SOFTWARE=1); KWin itself still composes with OpenGL, which
works in a virtual session here. "--render default" sets nothing. Do not use KWIN_COMPOSE=Q: KWin
crashes on the first screenshot with it.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = "/usr/bin/python3"
# Variables of the real session that must never reach the rig.
DROP_PREFIXES = (
    "DBUS_",
    "XDG_SESSION",
    "KDE_SESSION",
    "SESSION_MANAGER",
    "DESKTOP_STARTUP",
    "XDG_ACTIVATION",
)
DROP_NAMES = {"DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "XAUTHORITY", "XDG_VTNR", "XDG_SEAT"}
RIG_KEYS = (
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_STATE_HOME",
    "XDG_CONFIG_DIRS",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
    "WAYLAND_DISPLAY",
    "QT_QPA_PLATFORM",
    "XDG_CURRENT_DESKTOP",
    "XDG_SESSION_TYPE",
    "KDE_FULL_SESSION",
    "KDE_SESSION_VERSION",
    "KDE_DEBUG",
    "KWIN_SCREENSHOT_NO_PERMISSION_CHECKS",
    "KWIN_COMPOSE",
    "QT_QUICK_BACKEND",
    "LIBGL_ALWAYS_SOFTWARE",
    "RIG_DIR",
)


class RigError(Exception):
    pass


# ---------------------------------------------------------------- environment


def clean_base_env() -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in DROP_NAMES
        and not k.startswith(DROP_PREFIXES)
        and k != "PYTHONPATH"
        and k != "QT_QPA_PLATFORM"
    }
    # The miniconda dbus tools come first on this machine's PATH and are broken.
    env["PATH"] = "/usr/bin:" + env.get("PATH", "")
    return env


def read_rig_env(rig: Path) -> dict[str, str]:
    path = rig / "env"
    if not path.is_file():
        raise RigError(f"{rig} is not a rig (no env file)")
    values = {}
    for line in path.read_text().splitlines():
        if line.startswith("export "):
            key, _, rest = line[7:].partition("=")
            values[key] = shlex.split(rest)[0] if rest else ""
    return values


def real_bus_addresses() -> set[str]:
    found = {os.environ.get("DBUS_SESSION_BUS_ADDRESS", ""), f"unix:path=/run/user/{os.getuid()}/bus"}
    return {a for a in found if a}


def check_isolated(rig: Path, values: dict[str, str]) -> None:
    root = rig.resolve()
    for key in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
        value = values.get(key)
        if not value or not Path(value).resolve().is_relative_to(root):
            raise RigError(f"refusing: {key}={value!r} is not inside {root}")
    address = values.get("DBUS_SESSION_BUS_ADDRESS", "")
    if address in real_bus_addresses() or f"path={root}/" not in address:
        raise RigError(f"refusing: bus address {address!r} is not this rig's own bus")
    if values.get("WAYLAND_DISPLAY", "").startswith("/") or not values.get("WAYLAND_DISPLAY"):
        raise RigError("refusing: no private Wayland socket name")
    if values["WAYLAND_DISPLAY"] == os.environ.get("WAYLAND_DISPLAY"):
        raise RigError("refusing: the socket name equals the real session's")


def rig_env(rig: Path) -> dict[str, str]:
    values = read_rig_env(rig)
    check_isolated(rig, values)
    env = clean_base_env()
    env.update(values)
    src = str(REPO / "src")
    env["PYTHONPATH"] = src
    return env


# ---------------------------------------------------------------- pids


def read_pids(rig: Path) -> list[tuple[str, int]]:
    path = rig / "pids"
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        name, _, pid = line.rpartition(" ")
        if pid.isdigit():
            out.append((name, int(pid)))
    return out


def write_pids(rig: Path, pids: list[tuple[str, int]]) -> None:
    (rig / "pids").write_text("".join(f"{n} {p}\n" for n, p in pids))


def add_pid(rig: Path, name: str, pid: int) -> None:
    write_pids(rig, read_pids(rig) + [(name, pid)])


def alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def all_processes() -> dict[int, int]:
    """pid -> parent pid for every process."""
    table = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                with open(f"/proc/{entry}/stat") as fh:
                    table[int(entry)] = int(fh.read().rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                pass
    return table


def descendants(roots: set[int]) -> set[int]:
    table = all_processes()
    found = set(roots)
    grew = True
    while grew:
        grew = False
        for pid, parent in table.items():
            if parent in found and pid not in found:
                found.add(pid)
                grew = True
    return found


def environ_mentions(pid: int, needle: bytes) -> bool:
    try:
        with open(f"/proc/{pid}/environ", "rb") as fh:
            return needle in fh.read()
    except OSError:
        return False


def rig_processes(rig: Path) -> set[int]:
    """Recorded processes, their children, and strays that carry this rig's runtime dir."""
    roots = {pid for _, pid in read_pids(rig) if alive(pid)}
    found = descendants(roots)
    needle = f"XDG_RUNTIME_DIR={rig.resolve()}/run\0".encode()
    for pid in all_processes():
        if pid not in found and pid != os.getpid() and environ_mentions(pid, needle):
            found.add(pid)
    return {p for p in found if alive(p) and p != os.getpid()}


# ---------------------------------------------------------------- D-Bus (dbus-python)


def connect(address: str):
    import dbus

    return dbus.bus.BusConnection(address)


def name_has_owner(bus, name: str) -> bool:
    try:
        return bool(bus.name_has_owner(name))
    except Exception:
        return False


def wait_for(cond, what: str, timeout: float, proc: subprocess.Popen | None = None, log: Path | None = None):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        if proc is not None and proc.poll() is not None:
            tail = log.read_text()[-1500:] if log and log.exists() else ""
            raise RigError(f"process exited ({proc.returncode}) while waiting for {what}\n{tail}")
        time.sleep(0.2)
    tail = log.read_text()[-1500:] if log and log.exists() else ""
    raise RigError(f"timed out after {timeout:.0f}s waiting for {what}\n{tail}")


# ---------------------------------------------------------------- start


def parse_size(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise RigError(f"bad size {text!r}, expected WxH") from None


def spawn(rig: Path, name: str, argv: list[str], env: dict[str, str]) -> subprocess.Popen:
    log = open(rig / f"{name}.log", "ab")
    full = ["prlimit", "--core=1:1", "--", "env", "KDE_DEBUG=1", *argv]
    proc = subprocess.Popen(
        full, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    )
    add_pid(rig, name, proc.pid)
    return proc


def cmd_start(args) -> int:
    rig = Path(args.dir).absolute()
    if not rig.is_relative_to("/tmp") or rig == Path("/tmp") or ".." in rig.parts:
        raise RigError("DIR must be a directory below /tmp")
    if rig.exists() and (not rig.is_dir() or any(rig.iterdir())):
        raise RigError(f"{rig} exists and is not empty")
    width, height = parse_size(args.size)
    rig.mkdir(parents=True, exist_ok=True)
    rig = rig.resolve()
    home = rig / "home"
    run = rig / "run"
    for path in (home / ".config", home / ".local/share", home / ".cache", home / ".local/state"):
        path.mkdir(parents=True)
    run.mkdir()
    run.chmod(0o700)
    # Keeps the first-run Welcome Center window from opening over the test screen.
    (home / ".config/plasma-welcomerc").write_text("[General]\nLastSeenVersion=99.0.0\n")
    socket = f"ptsrig-{secrets.token_hex(4)}"
    software = args.render == "software"

    values = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        # Never the real session's: kreadconfig6 must read this rig's own kdedefaults.
        "XDG_CONFIG_DIRS": f"{home / '.config/kdedefaults'}:/etc/xdg",
        "XDG_RUNTIME_DIR": str(run),
        "WAYLAND_DISPLAY": socket,
        "QT_QPA_PLATFORM": "wayland",
        "XDG_CURRENT_DESKTOP": "KDE",
        "XDG_SESSION_TYPE": "wayland",
        "KDE_FULL_SESSION": "true",
        "KDE_SESSION_VERSION": "6",
        "KDE_DEBUG": "1",
        "KWIN_SCREENSHOT_NO_PERMISSION_CHECKS": "1",
        "RIG_DIR": str(rig),
    }
    if software:
        values.update(QT_QUICK_BACKEND="software", LIBGL_ALWAYS_SOFTWARE="1")
    base = clean_base_env()
    base.update(values)
    # Fixed placeholder until the bus exists; the env file is written after.
    started: list[subprocess.Popen] = []
    try:
        bus_log = rig / "dbus.log"
        bus_path = run / "bus"
        address = f"unix:path={bus_path}"
        bus = subprocess.Popen(
            [
                "prlimit",
                "--core=1:1",
                "--",
                "/usr/bin/dbus-daemon",
                "--session",
                f"--address={address}",
                "--nofork",
            ],
            env=base,
            stdin=subprocess.DEVNULL,
            stdout=open(bus_log, "ab"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        started.append(bus)
        add_pid(rig, "dbus-daemon", bus.pid)
        wait_for(bus_path.exists, "the private bus socket", 10, bus, bus_log)
        values["DBUS_SESSION_BUS_ADDRESS"] = address
        base["DBUS_SESSION_BUS_ADDRESS"] = address
        check_isolated(rig, values)
        (rig / "env").write_text(
            "# Source with: . DIR/env  (private session of one desktop rig)\n"
            + "".join(f"export {k}={shlex.quote(v)}\n" for k, v in values.items())
            + f"export PATH={shlex.quote(base['PATH'])}\n"
            + f"export PYTHONPATH={shlex.quote(str(REPO / 'src'))}\n"
            + "unset DISPLAY\n"
        )

        kwin_log = rig / "kwin.log"
        kwin = spawn(
            rig,
            "kwin",
            [
                "kwin_wayland",
                "--virtual",
                "--no-lockscreen",
                "--no-global-shortcuts",
                "--socket",
                socket,
                "--width",
                str(width),
                "--height",
                str(height),
            ],
            base,
        )
        started.append(kwin)
        wait_for((run / socket).exists, "the Wayland socket", 30, kwin, kwin_log)
        conn = connect(address)
        wait_for(
            lambda: name_has_owner(conn, "org.kde.KWin"),
            "org.kde.KWin on the private bus",
            30,
            kwin,
            kwin_log,
        )

        if args.plasmashell:
            ps_log = rig / "plasmashell.log"
            ps = spawn(rig, "plasmashell", ["plasmashell", "--no-respawn"], base)
            started.append(ps)
            wait_for(
                lambda: name_has_owner(conn, "org.kde.plasmashell") and plasma_answers(conn),
                "plasmashell to answer evaluateScript",
                args.timeout,
                ps,
                ps_log,
            )
    except BaseException as exc:
        stop_rig(rig)
        if isinstance(exc, RigError):
            raise
        raise RigError(f"start failed: {exc!r}") from exc
    print(f"rig ready: {rig}")
    print(f"  socket {socket}  size {width}x{height}  render {args.render}  plasmashell {args.plasmashell}")
    print(f"  shell: . {rig}/env     or: {sys.argv[0]} run {rig} -- COMMAND")
    return 0


def plasma_answers(conn) -> bool:
    try:
        obj = conn.get_object("org.kde.plasmashell", "/PlasmaShell")
        obj.evaluateScript("print(panels().length)", dbus_interface="org.kde.PlasmaShell", timeout=5)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- stop / status


def stop_rig(rig: Path) -> list[int]:
    procs = rig_processes(rig)
    # Children and late-started services first; the bus last.
    for sig, wait in ((signal.SIGTERM, 6.0), (signal.SIGKILL, 3.0)):
        for pid in sorted(procs, reverse=True):
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        end = time.monotonic() + wait
        while time.monotonic() < end and any(alive(p) for p in procs):
            time.sleep(0.1)
        procs = {p for p in procs if alive(p)}
        procs |= {p for p in rig_processes(rig)}
        if not procs:
            break
    left = sorted(p for p in procs if alive(p))
    if not left:
        write_pids(rig, [])
    return left


def cmd_stop(args) -> int:
    rig = Path(args.dir).resolve()
    read_rig_env(rig)
    left = stop_rig(rig)
    if left:
        print(f"still running: {left}", file=sys.stderr)
        return 1
    print(f"rig stopped: {rig}")
    return 0


def cmd_status(args) -> int:
    rig = Path(args.dir).resolve()
    values = read_rig_env(rig)
    names = dict((pid, name) for name, pid in read_pids(rig))
    running = rig_processes(rig)
    print(f"rig {rig}  socket {values['WAYLAND_DISPLAY']}  bus {values['DBUS_SESSION_BUS_ADDRESS']}")
    for name, pid in read_pids(rig):
        print(f"  {name:12} {pid:>8} {'running' if alive(pid) else 'dead'}")
    extra = sorted(running - set(names))
    if extra:
        print("  other processes of this rig: " + " ".join(str(p) for p in extra))
    try:
        conn = connect(values["DBUS_SESSION_BUS_ADDRESS"])
        print(f"  org.kde.KWin answers: {name_has_owner(conn, 'org.kde.KWin')}")
        print(f"  org.kde.plasmashell answers: {name_has_owner(conn, 'org.kde.plasmashell')}")
    except Exception as exc:
        print(f"  bus not reachable: {exc}")
    return 0 if any(alive(p) for p in names) else 1


# ---------------------------------------------------------------- run / window


def cmd_run(args) -> int:
    rig = Path(args.dir).resolve()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise RigError("no command given")
    env = rig_env(rig)
    os.chdir(rig)
    try:
        os.execvpe(command[0], command, env)
    except OSError as exc:
        raise RigError(f"cannot run {command[0]}: {exc}") from exc


def cmd_window(args) -> int:
    rig = Path(args.dir).resolve()
    env = rig_env(rig)
    argv = [PY, str(Path(__file__).resolve()), "_window", str(rig), args.title, args.size, args.color]
    if args.maximized:
        argv.append("--maximized")
    proc = spawn(rig, f"window-{secrets.token_hex(2)}", argv, env)
    ready = rig / f"window-{proc.pid}.ready"
    wait_for(ready.exists, "the test window to show", 20, proc, rig / f"window-{proc.pid}.log")
    print(f"window pid {proc.pid} title {args.title!r} colour #{args.color}")
    return 0


def window_main(argv: list[str]) -> int:
    """Runs inside the rig: a flat coloured QWidget, kept open until killed."""
    rig, title, size, color = Path(argv[0]), argv[1], argv[2], argv[3]
    maximized = "--maximized" in argv
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication, QWidget

    app = QApplication(["desktop-rig-window"])
    w = QWidget()
    w.setWindowTitle(title)
    w.setAutoFillBackground(True)
    pal = w.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#" + color))
    w.setPalette(pal)
    width, height = parse_size(size)
    w.resize(width, height)
    if maximized:
        w.showMaximized()
    else:
        w.show()
    from PySide6.QtCore import QTimer

    QTimer.singleShot(1500, lambda: (rig / f"window-{os.getpid()}.ready").write_text("ok"))
    return app.exec()


# ---------------------------------------------------------------- screenshot


def cmd_screenshot(args) -> int:
    rig = Path(args.dir).resolve()
    values = read_rig_env(rig)
    check_isolated(rig, values)
    import dbus

    conn = connect(values["DBUS_SESSION_BUS_ADDRESS"])
    if not name_has_owner(conn, "org.kde.KWin"):
        raise RigError("org.kde.KWin does not answer on the rig bus (is the rig running?)")
    read_fd, write_fd = os.pipe()
    chunks: list[bytes] = []

    def reader():
        with os.fdopen(read_fd, "rb") as fh:
            while True:
                data = fh.read(1 << 20)
                if not data:
                    break
                chunks.append(data)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    obj = conn.get_object("org.kde.KWin", "/org/kde/KWin/ScreenShot2")
    options = {"include-cursor": False, "native-resolution": True}
    try:
        result = obj.CaptureWorkspace(
            dbus.Dictionary(options, signature="sv"),
            dbus.types.UnixFd(write_fd),
            dbus_interface="org.kde.KWin.ScreenShot2",
            timeout=30,
        )
    finally:
        os.close(write_fd)
    thread.join(30)
    data = b"".join(chunks)
    width, height, stride, fmt = (int(result[k]) for k in ("width", "height", "stride", "format"))
    if len(data) < stride * height:
        raise RigError(f"short screenshot data: {len(data)} of {stride * height} bytes")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtGui import QGuiApplication, QImage

    app = QGuiApplication.instance() or QGuiApplication(["desktop-rig"])
    image = QImage(data, width, height, stride, QImage.Format(fmt)).copy()
    out = Path(args.out).absolute()
    if not image.save(str(out), "PNG"):
        raise RigError(f"could not write {out}")
    del app
    print(f"{out} {width}x{height}")
    return 0


# ---------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Private, invisible KDE session for theme experiments.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start", help="start a rig in a new directory under /tmp")
    s.add_argument("dir")
    s.add_argument("--plasmashell", action="store_true", help="also start plasmashell")
    s.add_argument("--size", default="1280x800", help="virtual screen size WxH")
    s.add_argument("--render", choices=("software", "default"), default="software")
    s.add_argument("--timeout", type=float, default=90, help="seconds to wait for plasmashell")
    s.set_defaults(func=cmd_start)
    s = sub.add_parser("run", help="run a command with the rig's environment")
    s.add_argument("dir")
    s.add_argument("command", nargs=argparse.REMAINDER, help="-- COMMAND...")
    s.set_defaults(func=cmd_run)
    s = sub.add_parser("window", help="show a flat test window")
    s.add_argument("dir")
    s.add_argument("--title", default="Rig test window")
    s.add_argument("--size", default="480x300")
    s.add_argument("--color", default="336699", help="background colour RRGGBB")
    s.add_argument("--maximized", action="store_true")
    s.set_defaults(func=cmd_window)
    s = sub.add_parser("screenshot", help="save the whole screen as PNG")
    s.add_argument("dir")
    s.add_argument("out")
    s.set_defaults(func=cmd_screenshot)
    s = sub.add_parser("status", help="show what runs")
    s.add_argument("dir")
    s.set_defaults(func=cmd_status)
    s = sub.add_parser("stop", help="stop everything of the rig")
    s.add_argument("dir")
    s.set_defaults(func=cmd_stop)
    return p


def main() -> int:
    try:  # if memory runs out, the kernel takes the rig and what runs in it first
        Path("/proc/self/oom_score_adj").write_text("1000")
    except OSError:
        pass
    if len(sys.argv) > 1 and sys.argv[1] == "_window":
        return window_main(sys.argv[2:])
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except RigError as exc:
        print(f"desktop_rig: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
