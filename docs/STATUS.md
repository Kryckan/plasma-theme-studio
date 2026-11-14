# Project status

Where the project stands, what comes next, and things learned along the way that are easy to forget. The plan itself is in [PRD.md](PRD.md); user-visible changes are in [CHANGELOG.md](../CHANGELOG.md). Update this file in the same commit as the work it describes.

Last updated: 2026-11-14

## Done

**Milestone 1 (v0.1), not yet tagged**

- Theme model and TOML file format (`model/theme.py`). Optional fields that follow another field until set (`Field.inherits`, `Theme.resolved`): `window.radius`, `window.border_width`, `panel.radius`, `panel.border_width`.
- Color scheme generator and activation (`generators/colorscheme.py`).
- Apply engine with snapshots, rollback and restore (`apply/`).
- Library of installed color schemes and saved themes (`library.py`), switching between schemes (`engine.switch_color_scheme`).
- Qt Widgets UI: editor, drawn preview, Themes tab, result banner, snapshot dialog (`ui/`).
- CLI, Swedish translation, PKGBUILD, CI (ruff, pytest, REUSE, AppStream validation).

## Not applied to the desktop yet

Shapes, window frame, shadows and panel values are stored in the theme and shown in the preview only. The app says so in the editor and after an apply.

## Next

1. **Milestone 2:** Kvantum and Klassy generators so shapes, borders and shadows reach apps and windows; preview drawn with the real style; light and dark variants; pywal and matugen import.
2. **Milestone 3:** Plasma style generator and SVG editor; panel layout (position, size, floating) through the Plasma shell scripting interface (PRD DL-2).
3. **Milestone 4:** GTK, Rofi, switching of Global Themes and other installed theme parts (DL-4), fonts and title bar buttons (DL-5), export and import, more distribution packages.

Smaller open items:

- `docs/screenshots/main-window.png` predates the Themes tab and banner.
- The Fedora, Debian and openSUSE package names in the README are not verified on those systems.
- Tag v0.1.0 and publish the AUR package once the user has tried the current build.

## Product direction (from the project owner)

- Everything about the desktop's look is editable in this one app, and every editable value has a visual preview.
- The app should do what existing tools cannot, and be exceptionally good-looking and easy to use.
- Per-part control matters: for example a rounder panel than the rest, or a border on window edges only.
- Settings normally made in System Settings (panel position and the like) should be available in the app for one consistent experience.

## Things learned

- `plasma-apply-colorscheme` does nothing when the named scheme is already active, even if its file changed. Workaround in `activate_scheme`: write a placeholder name to `kdeglobals` `General/ColorScheme` with `kwriteconfig6`, then apply.
- Its exit code is not reliable. Success is verified by reading the setting back with `kreadconfig6`.
- It aborts without a display. `SystemRunner` sets `QT_QPA_PLATFORM=offscreen` when neither `DISPLAY` nor `WAYLAND_DISPLAY` is set.
- Installed color schemes vary: many lack `[Colors:Header]` and `[Colors:Complementary]`, and some color values have four components (`r,g,b,a`). `library.read_scheme` handles both.
- System Settings modules cannot be embedded in a PySide6 app, so the app builds its own controls and writes through Plasma's tools.
- Use the distribution's PySide6 (`/usr/bin/python3`), not one from pip, so the app gets the desktop's Qt style and platform integration.
- `QApplication.setDesktopFileName` with an ID whose desktop file is not installed triggers a portal warning; only set it when the file exists.
- When taking screenshots or testing the UI from a script, use `QT_QPA_PLATFORM=offscreen` so no window appears on the developer's desktop, and mark the undo stack clean before quitting so the unsaved-changes dialog does not block.

## How to work on it

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format .
scripts/update-translations.sh sv
```
