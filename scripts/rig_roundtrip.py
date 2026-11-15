#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Developer tool: apply a theme in a rig, undo it with the app's own undo, and compare the rig's home.

  /usr/bin/python3 scripts/desktop_rig.py start /tmp/pts-rig-x --plasmashell
  scripts/capped /usr/bin/python3 scripts/rig_roundtrip.py /tmp/pts-rig-x [CASE...] [options]
  /usr/bin/python3 scripts/desktop_rig.py stop /tmp/pts-rig-x

For every case (a theme file that changes one part, or all of them: `--list` names them) it takes a
listing of the rig's home with a hash of every file, runs `plasma-theme-studio apply` inside the rig,
runs `plasma-theme-studio restore` (the engine call behind the window's Undo), waits for the desktop
to settle and takes a second listing. Every difference is reported and the exit code is 1; a case
that leaves the home as it was is "identical". `--window` does apply and undo from the main window
(offscreen, inside the rig) instead of the CLI. `--theme FILE` adds a theme file of your own.

It refuses to run on anything that is not a running rig (HOME, the bus and the Wayland socket must be
the rig's own), and it never reads or writes the real home.

Left out of the comparison, and why:
- `.cache` and `.local/state`: caches and the state files that running programs keep for themselves;
- `.local/share/plasma-theme-studio`: the app's own snapshots, which undo uses up;
- any file that changes by itself: the script takes two listings a few seconds apart before the first
  case and ignores what differs (databases of the programs of the session, plasmashell's own files).
Folders are compared too: a folder the apply made must be gone again, even an empty one.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import desktop_rig  # noqa: E402

SRC = HERE.parent / "src"
SKIP_PREFIXES = (
    ".cache",
    ".local/state",
    ".local/share/plasma-theme-studio",
    ".config/dconf",
    ".config/Unknown Organization",
)
SKIP_NOTE = (
    "caches, the state files of running programs, the app's own snapshots and dconf (the shared "
    "settings database of GNOME programs: undo does not overwrite it, because it also holds what "
    "other programs saved since), and the thickness lines of plasmashellrc (plasmashell writes them "
    "itself, late, with no apply going on), and the settings file that the throwaway window process of "
    "--window leaves for itself (.config/Unknown Organization)"
)
# Lines that a running program writes about itself, in its own time and also when nothing is applied:
# plasmashell records the size of its panels in plasmashellrc, a while after the panels were reloaded.
OWN_STATE = {".config/plasmashellrc": b"thickness="}
CASES = (
    "colors-installed",
    "colors-own",
    "accent-wallpaper",
    "plasma-style",
    "app-style",
    "decoration",
    "border-size",
    "buttons",
    "icons",
    "pointers",
    "pointer-size",
    "fonts",
    "splash",
    "sounds",
    "night-mode",
    "panel",
    "gtk",
    "rofi",
    "everything",
    "follow",
)


class RoundtripError(Exception):
    pass


# ------------------------------------------------------------------ the rig


def prepare(rig: Path) -> dict[str, str]:
    """The rig's environment, after checking that this really is a running rig."""
    try:
        env = desktop_rig.rig_env(rig)
    except desktop_rig.RigError as error:
        raise RoundtripError(str(error)) from error
    home = Path(env["HOME"]).resolve()
    if not home.is_relative_to(Path("/tmp")) or not home.is_relative_to(rig.resolve()):
        raise RoundtripError(f"refusing: {home} is not inside the rig {rig}")
    bus = Path(env["DBUS_SESSION_BUS_ADDRESS"].partition("path=")[2])
    if not bus.exists():
        raise RoundtripError(f"{rig} is not running (no bus socket); start it with desktop_rig.py start")
    os.environ.update(env)
    sys.path.insert(0, str(SRC))
    return env


# ------------------------------------------------------------------ listings


def listing(home: Path) -> dict[str, tuple]:
    """Every file, link and folder of the home below the excluded places, with a hash for files."""
    found: dict[str, tuple] = {}
    for base, dirs, files in os.walk(home):
        here = Path(base).relative_to(home)
        dirs[:] = sorted(d for d in dirs if str(here / d).removeprefix("./") not in SKIP_PREFIXES)
        for name in dirs:
            found[str(here / name)] = ("dir",)
        for name in files:
            path = Path(base) / name
            relative = str(here / name).removeprefix("./")
            try:
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    found[relative] = ("link", os.readlink(path))
                elif stat.S_ISREG(info.st_mode):
                    digest = hashlib.sha256()
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1 << 20), b""):
                            digest.update(chunk)
                    if relative in OWN_STATE:  # what the program keeps about itself is not compared
                        kept = b"".join(
                            line
                            for line in path.read_bytes().splitlines(keepends=True)
                            if not line.startswith(OWN_STATE[relative])
                        )
                        digest = hashlib.sha256(kept)
                    found[relative] = ("file", digest.hexdigest(), info.st_size, stat.S_IMODE(info.st_mode))
            except OSError:
                found[relative] = ("unreadable",)
    return {k.removeprefix("./"): v for k, v in found.items()}


def differences(before: dict, after: dict, ignore: set[str]) -> list[tuple[str, str]]:
    result = []
    for path in sorted(set(before) | set(after)):
        if path in ignore or any(path.startswith(f"{p}/") for p in ignore if before.get(p) == ("dir",)):
            continue
        if path not in before:
            result.append(("added", path))
        elif path not in after:
            result.append(("removed", path))
        elif before[path] != after[path]:
            result.append(("changed", path))
    return result


def noise(home: Path, seconds: float) -> set[str]:
    """What changes in the home without anyone asking."""
    first = listing(home)
    time.sleep(seconds)
    return {path for _kind, path in differences(first, listing(home), set())}


# ------------------------------------------------------------------ the cases


def installed_alternative(key: str, current) -> str | None:
    from plasma_theme_studio import desktopparts

    names = [n for n in desktopparts.PARTS[key].installed() if n != current]
    return names[0] if names else None


def case_theme(case: str, runner):
    """The theme of a case, or None when this machine has nothing to try it with."""
    from plasma_theme_studio import desktopparts, library
    from plasma_theme_studio.edits import theme_edits_from_color_scheme
    from plasma_theme_studio.model.theme import Theme

    theme = Theme.from_preset("breeze-light")
    theme.set("meta", "name", f"Roundtrip {case}")
    parts = desktopparts.PARTS

    def alt(key: str):
        return installed_alternative(key, parts[key].current(runner))

    def colors_installed() -> bool:
        schemes = {s.id: s for s in library.installed_schemes()}
        scheme = schemes.get("BreezeDark") or next((s for s in schemes.values()), None)
        if scheme is None:
            return False
        for (section, key), value in theme_edits_from_color_scheme(scheme)[0].items():
            theme.set(section, key, value)
        return True

    def decoration() -> bool:
        from plasma_theme_studio import pickers

        current = parts["decoration"].current(runner)
        items = [i for i in pickers.kind("decoration").items() if i.id != current and ":" in i.id]
        if not items:
            return False
        theme.set("window", "decoration", "installed")
        theme.set("window", "decoration_id", items[0].id)
        return True

    def named(section, key, part, id_key=None) -> bool:
        value = alt(part)
        if value is None:
            return False
        if id_key:
            theme.set(section, key, "installed")
            theme.set(section, id_key, value)
        else:
            theme.set(section, key, value)
        return True

    steps = {
        "colors-installed": colors_installed,
        "colors-own": lambda: theme.set("colors", "window", "#e8e0d0") or True,
        "accent-wallpaper": lambda: theme.set("colors", "accent_from_wallpaper", True) or True,
        "plasma-style": lambda: named("panel", "style", "plasma_style", "style_id"),
        "app-style": lambda: named("apps", "style", "app_style", "style_id"),
        "decoration": decoration,
        "border-size": lambda: theme.set("window", "border_size", "Large") or True,
        "buttons": lambda: (
            theme.set("window", "buttons_left", "MS") or theme.set("window", "buttons_right", "HIAX") or True
        ),
        "icons": lambda: named("desktop", "icons", "icons"),
        "pointers": lambda: named("desktop", "cursors", "cursor_theme"),
        "pointer-size": lambda: theme.set("desktop", "cursor_size", 36) or True,
        "fonts": lambda: (
            theme.set("fonts", "general", "DejaVu Sans, 12")
            or theme.set("fonts", "window_title", "DejaVu Sans, 13, 700")
            or True
        ),
        "splash": lambda: named("desktop", "splash", "splash"),
        "sounds": lambda: named("desktop", "sounds", "sounds"),
        "night-mode": lambda: theme.set("desktop", "dark_at_night", True) or True,
        "panel": lambda: (
            theme.set("panel_layout", "height", 52)
            or theme.set("panel_layout", "floating", True)
            or theme.set("panel", "style", "generated")
            or True
        ),
        "gtk": lambda: theme.set("gtk", "style", "generated") or True,
        "rofi": lambda: theme.set("rofi", "style", "generated") or True,
    }
    if case == "everything":
        done = [
            steps[name]()
            for name in CASES
            if name not in ("everything", "pointer-size", "colors-installed", "follow")
        ]
        return theme if any(done) else None
    return theme if steps[case]() else None


# ------------------------------------------------------------------ running


def run_cli(env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    argv = [
        str(HERE / "capped"),
        "/usr/bin/env",
        "QT_QPA_PLATFORMTHEME=kde",
        "KDE_DEBUG=1",
        "/usr/bin/python3",
        "-m",
        "plasma_theme_studio",
        *args,
    ]
    return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=300, check=False)


WINDOW_SCRIPT = """
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication([])
from pathlib import Path
from plasma_theme_studio.model.theme import Theme
from plasma_theme_studio.ui.main_window import MainWindow
for box in ("warning", "question", "information", "critical"):
    setattr(QMessageBox, box, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
window = MainWindow()
action = sys.argv[1]
if action == "apply":
    window.replace_theme("roundtrip", Theme.load(Path(sys.argv[2])))
    window.settle()
    window.apply_theme()
else:
    window.undo_last_apply()
window.settle()
window.undo_stack.setClean()
print(window.banner.text() if hasattr(window.banner, "text") else "")
"""


def run_window(env: dict[str, str], action: str, theme_file: Path) -> subprocess.CompletedProcess:
    env = {**env, "QT_QPA_PLATFORM": "offscreen"}
    argv = [str(HERE / "capped"), "/usr/bin/python3", "-c", WINDOW_SCRIPT, action, str(theme_file)]
    return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=300, check=False)


def show(kind: str, path: str, before: dict, after: dict, home: Path, limit: int) -> None:
    print(f"    {kind:8} {path}")
    if kind != "changed" or limit <= 0:
        return
    try:
        old = (home.parent / "roundtrip-before" / path).read_text().splitlines()
        new = (home / path).read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return
    for line in list(difflib.unified_diff(old, new, "before", "after", lineterm="", n=0))[:limit]:
        print("      " + line)


def kdeglobals_keys(home: Path) -> dict[str, str]:
    """The keys of kdeglobals as "Group/key" -> value (a plain reading; the file is simple)."""
    found, group = {}, ""
    try:
        text = (home / ".config/kdeglobals").read_text(encoding="utf-8")
    except OSError:
        return found
    for line in text.splitlines():
        if line.startswith("["):
            group = line.strip("[]")
        elif "=" in line:
            key, _, value = line.partition("=")
            found[f"{group}/{key}"] = value
    return found


def expectations(case: str, home: Path) -> list[str]:
    """What the apply of a case must have left in the home, besides what the comparison shows."""
    keys = kdeglobals_keys(home)
    wrong = []
    if case == "colors-installed":
        if keys.get("General/ColorScheme") != "BreezeDark":
            wrong.append("the scheme in use is not the installed one that was named")
        if list((home / ".local/share/color-schemes").glob("Roundtrip*")):
            wrong.append("a scheme file of the app's own was written for an installed scheme")
    elif case == "night-mode":
        if keys.get("KDE/AutomaticLookAndFeel") != "true":
            wrong.append("KDE/AutomaticLookAndFeel is not true")
    elif case == "accent-wallpaper":
        if keys.get("General/accentColorFromWallpaper") != "true":
            wrong.append("General/accentColorFromWallpaper is not true")
    return wrong


def run_case(case, theme, env, home, ignore, args, extra=None) -> bool:
    folder = Path(tempfile.mkdtemp(prefix="pts-rt-", dir="/tmp"))
    try:
        file = folder / "theme.toml"
        theme.save(file)
        before = listing(home)
        # Keep text copies of the files for the diff (small ones only).
        backup = home.parent / "roundtrip-before"
        for path, entry in before.items():
            if entry[0] == "file" and entry[2] < 200_000:
                (backup / path).parent.mkdir(parents=True, exist_ok=True)
                (backup / path).write_bytes((home / path).read_bytes())
        if args.window:
            applied = run_window(env, "apply", file)
        else:
            applied = run_cli(env, "apply", str(file))
        time.sleep(args.settle)
        wrong = expectations(case, home)
        changed = differences(before, listing(home), ignore)
        undone = run_window(env, "undo", file) if args.window else run_cli(env, "restore")
        time.sleep(args.settle)
        after = listing(home)
        left = differences(before, after, ignore)
        print(f"{case}: apply changed {len(changed)} paths, ", end="")
        print("undo left the home identical" if not left else f"undo left {len(left)} differences")
        if args.verbose or left:
            for line in (applied.stdout + applied.stderr).strip().splitlines()[-4:]:
                print(f"    apply: {line}")
            for line in (undone.stdout + undone.stderr).strip().splitlines()[-4:]:
                print(f"    undo:  {line}")
        if args.verbose:
            for kind, path in changed:
                print(f"    apply {kind:8} {path}")
        if applied.returncode != 0:  # a crashed apply changes nothing, and nothing then needs undoing
            wrong.append(f"the apply exited with code {applied.returncode}")
        if undone.returncode != 0:
            wrong.append(f"the undo exited with code {undone.returncode}")
        if not changed:
            wrong.append("the apply changed nothing")
        for problem in wrong:
            print(f"    after the apply: {problem}")
        for kind, path in left:
            show(kind, path, before, after, home, args.diff_lines)
        return not left and not wrong
    finally:
        subprocess.run(["rm", "-rf", str(folder), str(home.parent / "roundtrip-before")], check=False)


def pywal_text(background: str, foreground: str, hues: list[str]) -> str:
    """A pywal colors.json: the two special colors and sixteen entries, the hues in color1 to color6."""
    colors = {f"color{i}": "#808080" for i in range(16)}
    for i, hue in enumerate(hues):
        colors[f"color{i + 1}"] = colors[f"color{i + 9}"] = hue
    colors["color0"], colors["color15"] = background, foreground
    special = {"background": background, "foreground": foreground, "cursor": foreground}
    return json.dumps({"special": special, "colors": colors})


def run_follow(env, home, ignore, args) -> bool:
    """Follow mode: switch it on, change the palette file twice (the watcher that the switch started
    applies each change by itself), switch it off, and compare the home with the listing from before."""
    palettes = [
        pywal_text("#1b2b24", "#d8e0dc", ["#8a5a4b", "#4f9a62", "#b89b4a", "#4b78a8", "#8a5f99", "#4a9a94"]),
        pywal_text("#101820", "#e6edf3", ["#e06c75", "#98c379", "#e5c07b", "#61afef", "#c678dd", "#56b6c2"]),
        pywal_text("#2b2118", "#eadcc8", ["#c4573a", "#7f9a3c", "#d9a441", "#5b86a5", "#a0658a", "#5a9a8a"]),
    ]
    folder = Path(tempfile.mkdtemp(prefix="pts-rt-", dir="/tmp"))
    wrong: list[str] = []
    try:
        theme_file = folder / "theme.toml"
        theme_file.write_text(
            'schema_version = 1\n\n[meta]\nname = "Roundtrip Follow"\n\n[colors]\nwindow = "#1b2b24"\n'
        )
        palette_file = home / ".cache/wal/colors.json"  # .cache is left out of the comparison
        palette_file.parent.mkdir(parents=True, exist_ok=True)
        before = listing(home)
        palette_file.write_text(palettes[0])
        scheme = home / ".local/share/color-schemes/RoundtripFollowPalette.colors"
        seen = []
        steps = [
            ("on", ("follow", "on", str(theme_file), "--palette", str(palette_file))),
            ("change 1", None),
            ("change 2", None),
        ]
        results = []
        for number, (what, command) in enumerate(steps):
            if command is not None:
                results.append(run_cli(env, *command))
            else:
                palette_file.write_text(palettes[number])
            time.sleep(args.settle)
            keys = kdeglobals_keys(home)
            seen.append((what, keys.get("General/ColorScheme"), keys.get("Colors:Window/BackgroundNormal")))
        if results[0].returncode != 0:
            wrong.append(
                "follow on exited with "
                + str(results[0].returncode)
                + ": "
                + results[0].stderr.strip()[-200:]
            )
        for what, active, background in seen:
            print(f"    after {what}: scheme {active}, window background {background}")
        if len({background for _, _, background in seen}) != 3:
            wrong.append("the window background did not change with each palette")
        if any(active != "RoundtripFollowPalette" for _, active, _ in seen):
            wrong.append("the scheme in use is not the palette scheme")
        status = run_cli(env, "follow", "status")
        print(
            "    status:",
            status.stdout.strip().splitlines()[0] if status.stdout.strip() else status.stderr.strip(),
        )
        off = run_cli(env, "follow", "off")
        time.sleep(args.settle)
        if off.returncode != 0:
            wrong.append(f"follow off exited with {off.returncode}: {off.stderr.strip()[-200:]}")
        left = differences(before, listing(home), ignore)
        result = "the home identical" if not left else f"{len(left)} differences"
        print(f"follow: palette changed twice, off left {result}")
        if scheme.exists():
            wrong.append("the scheme file is still there after switching off")
        for problem in wrong:
            print(f"    {problem}")
        for kind, path in left:
            print(f"    {kind:8} {path}")
        return not left and not wrong
    finally:
        run_cli(env, "follow", "off")  # nothing may stay behind, also after a failure
        subprocess.run(["rm", "-rf", str(folder)], check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("rig", nargs="?", help="the rig folder (made by desktop_rig.py start)")
    parser.add_argument("cases", nargs="*", help="the cases to run (default: all)")
    parser.add_argument("--list", action="store_true", help="name the cases and stop")
    parser.add_argument("--theme", action="append", default=[], help="a theme file to try as well")
    parser.add_argument("--window", action="store_true", help="apply and undo from the main window")
    parser.add_argument("--settle", type=float, default=6.0, help="seconds to wait after each step")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--diff-lines", type=int, default=12, help="lines of diff shown per changed file")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(CASES))
        return 0
    if not args.rig:
        parser.error("name the rig folder")
    unknown = [c for c in args.cases if c not in CASES]
    if unknown:
        parser.error(f"unknown case {unknown[0]}; --list names them")
    rig = Path(args.rig).resolve()
    try:
        env = prepare(rig)
    except RoundtripError as error:
        print(error, file=sys.stderr)
        return 2
    home = Path(env["HOME"])
    from plasma_theme_studio.apply.runner import SystemRunner
    from plasma_theme_studio.model.theme import Theme

    runner = SystemRunner()
    ignore = noise(home, 4.0)
    print(f"left out: {SKIP_NOTE}; changing by itself: {sorted(ignore) or 'nothing'}")
    failed = 0
    for case in args.cases or CASES:
        if case == "follow":
            failed += not run_follow(env, home, ignore, args)
            continue
        theme = case_theme(case, runner)
        if theme is None:
            print(f"{case}: skipped (nothing installed to try it with)")
            continue
        failed += not run_case(case, theme, env, home, ignore, args)
    for name in args.theme:
        failed += not run_case(Path(name).name, Theme.load(Path(name)), env, home, ignore, args)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
