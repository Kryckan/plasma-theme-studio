#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Makes the pictures of the user guide (docs/screenshots/*.png) so they can be remade.

    scripts/capped /usr/bin/python3 scripts/make_screenshots.py [--out DIR] [NAME ...]

NAME is a page, or one of show-files, frame-editor, variants, colors-follow.

The window is built offscreen (nothing opens on your desktop), in a throwaway home that holds nothing
of yours, and with a runner that only answers a few questions and changes nothing. The themes,
icons and pointers that show up are the ones the system has installed under /usr/share (not those in
your own home). A sample theme gives every page the same good-looking content. Use the distribution's
PySide6 (/usr/bin/python3): the pip build has no KDE plugins.

Every picture is 1180 x 740 px (`WIDTH`, `HEIGHT`). Names are stable: the README and the AppStream
file point at them. `main-window.png` is the Colors page in the dark sample theme; `PAGE.png` is a
page in the light one, and `PAGE-dark.png` exists for the pages named in DARK.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WIDTH, HEIGHT = 1180, 740
DARK = ("overview", "colors", "decorations", "plasma_style")
EXTRA = ("show-files", "frame-editor", "variants", "colors-follow")  # pictures that are not a plain page
MAIN_WINDOW = "colors"  # the page of main-window.png, in the dark theme


def relaunch() -> None:
    """Start this script again in a clean environment: a throwaway home, no session bus, and only
    the system's data folders, so nothing of the person who runs it can end up in a picture."""
    home = Path(tempfile.mkdtemp(prefix="pts-shots-"))
    for name in (".config", ".local/share", ".cache", ".local/state"):
        (home / name).mkdir(parents=True)
    env = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_DATA_DIRS": "/usr/local/share:/usr/share",
        "XDG_CONFIG_DIRS": "/etc/xdg",
        "PATH": "/usr/bin",
        "LANG": "C",
        "QT_QPA_PLATFORM": "offscreen",
        "KDE_DEBUG": "1",
        "PTS_SHOTS_HOME": str(home),
        "PYTHONPATH": str(ROOT / "src"),
    }
    try:
        import subprocess

        done = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env=env, check=False
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)
    raise SystemExit(done.returncode)


def sample(dark: bool):
    """The sample theme: a calm blue accent, 8 px corners, every generated part switched on."""
    from plasma_theme_studio.model.theme import Theme

    theme = Theme.from_preset("breeze-dark" if dark else "breeze-light")
    values = {
        ("meta", "name"): "Harbour Dark" if dark else "Harbour Light",
        ("meta", "author"): "Plasma Theme Studio",
        ("colors", "accent"): "#4d8fd6" if dark else "#2f6fbd",
        ("shape", "radius"): 8,
        ("shape", "border_width"): 1,
        ("shadow", "size"): 28,
        ("shadow", "strength"): 0.4,
        ("panel", "opacity"): 0.9,
        ("window", "decoration"): "generated",
        ("panel", "style"): "generated",
        ("apps", "style"): "generated",
        ("gtk", "style"): "generated",
        ("rofi", "style"): "generated",
    }
    if dark:
        values.update(
            {
                ("colors", "window"): "#1f2430",
                ("colors", "view"): "#161a23",
                ("colors", "button"): "#2a303e",
                ("colors", "header"): "#2a303e",
                ("colors", "link"): "#6aa9ee",
            }
        )
    else:
        values.update(
            {
                ("colors", "window"): "#eef1f5",
                ("colors", "view"): "#ffffff",
                ("colors", "button"): "#f9fafc",
                ("colors", "header"): "#dfe4ec",
                ("colors", "link"): "#2f6fbd",
            }
        )
    for (section, key), value in values.items():
        theme.set(section, key, value)
    return theme


def make_runner():
    """A runner that changes nothing: it says which color scheme is in use and "not found" otherwise."""
    from plasma_theme_studio.apply.runner import Result

    class ShotRunner:
        def __init__(self, scheme):
            self.scheme = scheme

        def which(self, program):
            # the Colors page offers "Follow the palette" when pywal is there; say it is
            return program == "wal" or shutil.which(program) is not None

        def launch(self, argv):
            return None

        def run(self, argv, timeout=20):
            if argv[0] == "kreadconfig6" and "ColorScheme" in argv:
                return Result(0, self.scheme + "\n")
            return Result(127, "", f"{argv[0]}: not available here")

    return ShotRunner


def palette(dark: bool):
    from PySide6.QtGui import QColor, QPalette

    window, base, text = ("#1f2430", "#161a23", "#f1f3f6") if dark else ("#eef1f5", "#ffffff", "#232629")
    roles = {
        QPalette.ColorRole.Window: window,
        QPalette.ColorRole.Base: base,
        QPalette.ColorRole.AlternateBase: window,
        QPalette.ColorRole.Button: "#2a303e" if dark else "#f9fafc",
        QPalette.ColorRole.WindowText: text,
        QPalette.ColorRole.Text: text,
        QPalette.ColorRole.ButtonText: text,
        QPalette.ColorRole.PlaceholderText: "#8a94a3",
        QPalette.ColorRole.Highlight: "#4d8fd6" if dark else "#2f6fbd",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Mid: "#8a94a3",
    }
    result = QPalette()
    for role, color in roles.items():
        result.setColor(role, QColor(color))
    return result


def extras(window, wait, scroll, out, args) -> int:
    """The pictures that show more than a page: the file list, the frame editor, a theme with two variants."""
    made = 0

    def save(name):
        window.grab().save(str(out / name))
        print("wrote", out / name)

    if not args or "show-files" in args:
        window.show_files()
        wait(0.5)
        dialog = window.files_dialog
        dialog.resize(760, 560)
        wait(0.5)
        dialog.grab().save(str(out / "show-files.png"))
        print("wrote", out / "show-files.png")
        dialog.hide()
        made += 1
    if not args or "frame-editor" in args:
        # the panel frame is an own picture (its border in the accent color) and the guide lines are on
        from plasma_theme_studio.generators import plasmastyle
        from plasma_theme_studio.model.theme import Theme

        folder = Path(os.environ["PTS_SHOTS_HOME"]) / "art"
        (folder / "harbour-artwork").mkdir(parents=True, exist_ok=True)
        artful = sample(False)
        own = plasmastyle.frame_svg(artful, "panel").replace(
            'class="ColorScheme-Text" fill="currentColor" fill-opacity="0.22"',
            'fill="#2f6fbd" fill-opacity="0.9"',
        )
        (folder / "harbour-artwork" / "panel.svg").write_text(own)
        artful.set("artwork", "panel", "harbour-artwork/panel.svg")
        artful.save(folder / "harbour.toml")
        window._load_into_window(Theme.load(folder / "harbour.toml"), folder / "harbour.toml")
        window.show_page("plasma_style")
        wait(1.0)
        page = window.page("plasma_style")
        page.frame_editor.guides.setChecked(True)
        page.frame_editor.wait_drawing()
        scroll(page, page.frame_editor)
        wait(1.5)
        save("frame-editor.png")
        made += 1
        window._load_into_window(sample(False), None)
    if not args or "colors-follow" in args:
        # follow mode as it looks when it is on: only its state file is written (in the throwaway home)
        from plasma_theme_studio import follow

        # a made-up path: the page only shows it, nothing reads it
        source = "/home/you/.cache/wal/colors.json"
        follow.save_state(follow.State("Harbour Light", "light", "pywal", source, snapshot="shot"))
        window.show_page("colors")
        window.refresh()
        wait(1.0)
        page = window.page("colors")
        scroll(page, page.follow_row)
        wait(0.5)
        save("colors-follow.png")
        made += 1
        follow.state_path().unlink()
        window.refresh()
    if not args or "variants" in args:
        window.show_page("colors")
        window.add_variant()
        wait(1.5)
        scroll(window.page("colors"))
        save("variants.png")
        made += 1
    return made


def main() -> int:
    if "PTS_SHOTS_HOME" not in os.environ:
        relaunch()
    args = sys.argv[1:]
    out = ROOT / "docs" / "screenshots"
    if args[:1] == ["--out"]:
        out, args = Path(args[1]), args[2:]
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QIcon.setThemeSearchPaths(["/usr/share/icons"])
    from plasma_theme_studio.ui import pages
    from plasma_theme_studio.ui.main_window import MainWindow

    def wait(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)

    def scroll(widget, to=None):
        """Scroll the page's one scroll area to the top, or until `to` is in view."""
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QScrollArea

        for area in widget.findChildren(QScrollArea):
            if to is None:
                area.verticalScrollBar().setValue(0)
            else:
                top = to.mapTo(area.widget(), QPoint(0, 0)).y()
                area.verticalScrollBar().setValue(max(0, top - 8))
        wait(0.5)

    runner_class = make_runner()
    keys = [spec.key for spec in pages.PAGES if not args or spec.key in args]
    wants_extras = not args or any(a in EXTRA for a in args)
    made = 0
    for dark in (False, True):
        wanted = [k for k in keys if not dark or k in DARK or k == MAIN_WINDOW]
        if not wanted and (dark or not wants_extras):
            continue
        QIcon.setThemeName("breeze-dark" if dark else "breeze")
        app.setPalette(palette(dark))
        window = MainWindow(runner_class("BreezeDark" if dark else "BreezeLight"))
        window.resize(WIDTH, HEIGHT)
        window.show()
        app.processEvents()
        window._load_into_window(sample(dark), None)
        for key in wanted:
            window.show_page(key)
            wait(2.0)  # thumbnails are made by workers
            scroll(window.page(key))
            window.update_status()
            wait(0.3)
            image = window.grab()
            names = []
            if dark and key in DARK:
                names.append(f"{key}-dark.png")
            if dark and key == MAIN_WINDOW:
                names.append("main-window.png")
            if not dark:
                names.append(f"{key}.png")
            for name in names:
                image.save(str(out / name))
                print("wrote", out / name)
                made += 1
        if not dark and wants_extras:
            made += extras(window, wait, scroll, out, args)
        window.stop_page_workers()
        window.undo_stack.setClean()
        window.close_without_asking()
    print(f"{made} pictures in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
