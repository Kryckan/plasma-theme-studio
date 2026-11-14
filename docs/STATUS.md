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

**Brought forward from milestones 2 and 3**

Three more targets reach the desktop. Each is opt-in: a theme that leaves the choice at *unchanged* (the default) touches nothing but the colors.

| Target | Module | Theme values | What an apply does |
|---|---|---|---|
| Window frame | `generators/windowframe.py` | `window.decoration` (`unchanged`, `breeze`, `generated`), `window.radius`, `window.border_width`, `shadow.size`, `shadow.strength` | *breeze*: sets Breeze as decoration and maps border and shadow to Breeze's fixed steps. *generated*: writes an Aurorae theme (SVG frame with the exact radius, border, shadow and the theme's colors) and selects it. KWin is reloaded and asked which decoration it uses. |
| Panel style | `generators/plasmastyle.py` | `panel.style` (`unchanged`, `generated`), `panel.radius`, `panel.border_width`, `panel.opacity` | Writes a Plasma style package that only replaces the panel background and selects it with `plasma-apply-desktoptheme`. Everything else falls back to Breeze. |
| Panel position | `generators/panellayout.py` | `panel_layout.*`: location, height, alignment, length mode, floating, visibility, opacity mode. Every value is optional. | Sets the given values on the main panel (the longest one on the first screen) through Plasma's scripting interface and reads them back. |

Supporting pieces:

- `kconfig.py`: reads and writes single keys in KDE's config files and cleans up after `kwriteconfig6` (see *Things learned*).
- Generators report the settings they change (`Generator.changed_settings`), notes for the editor page (`Generator.notes`) and files that an apply removes (`stale_files`). The apply summary and the *Files written* tab show them before anything is written.
- A rollback only restores the targets it reached, and restoring a target that is already as it was does nothing. An apply is rolled back on any error, an interrupt included.
- When a rollback or an undo cannot put everything back, the snapshot is kept and the message says so. A failed rollback does not count as an undo. The first failed undo marks the snapshot (a `tried` file in its folder) and the second one uses it up, so that *Undo last apply* can move on to the apply before it.
- A file that cannot be put back (full disk, no permission) is reported like a setting that cannot be put back: the other files and the settings are still restored. An apply that cannot save its snapshot changes nothing.
- `write_atomic` writes through a file that is a link, so a theme file or config file kept in a dotfiles folder stays a link.
- Numbers that TOML allows but that are no size (`inf`, `nan`) are refused like any other bad value.
- Each editor page shows the notes of the targets that read it, below the controls (`Generator.section_notes`): the Shadows page only says what concerns shadows.
- The editor follows the Themes tab (`MainWindow.use_entry`): a switch loads the theme that was switched to into the editor, after asking about unsaved changes, and records it as the file the next start opens. An installed color scheme becomes a new unsaved theme. The entry that is the editor's own theme (its file, or the scheme an apply wrote from it) is applied with the unsaved changes. `MainWindow.switches` remembers what the editor held before each switch, so that undoing the switch brings it back; this only happens while the editor is clean and still holds the theme of the switch.
- Going back to an older snapshot undoes every apply after it, newest first (`engine.restore_to`), in the window and with `restore ID`. A snapshot only records what its own apply was about to change, so restoring one out of order would leave the later applies half in place. It stops at the first apply that cannot be undone completely, and before a snapshot on the way whose manifest cannot be read; *Undo last apply* then goes on with the newest readable one.
- `scripts/desktop_rig.py`: a headless KWin (and optionally plasmashell) with its own home, for trying applies without touching the developer's desktop.
- Tests: every generator against a fake KWin, plasmashell and KDE tools (`tests/test_windowframe.py`, `test_plasmastyle.py`, `test_panellayout.py`, `test_kconfig.py`), and all targets together through the engine, the window and the CLI (`tests/test_desktop.py`); switching on the Themes tab followed by edits, applies and undos (`tests/test_switching.py`, `tests/test_undo.py`). The script that is sent to plasmashell also runs as it is in Qt's JavaScript engine (`run_program` in `tests/test_panellayout.py`).

## Newer targets (integrated, not yet tried on a real session)

| Target | Module | Theme values | What an apply does |
|---|---|---|---|
| Application style | `generators/kvantum.py` | `apps.style` (`unchanged`, `generated`), `apps.radius`, `apps.border_width` | Makes a Kvantum theme from the theme's colors and shape, sets it in `kvantum.kvconfig` and makes Kvantum the widget style (`kdeglobals`). Controls get a corner radius of at most 8 px, menus and frames the whole radius. |
| Popups and tooltips | `generators/plasmastyle.py` | `popup.*` | The generated Plasma style also holds popup, tooltip and desktop widget backgrounds. |
| GTK | `generators/gtk.py` | `gtk.style`, `gtk.radius`, `gtk.border_width` | Writes a style sheet and adds one import line to `gtk-3.0/gtk.css` and `gtk-4.0/gtk.css`. |
| Rofi | `generators/rofi.py` | `rofi.*` | Writes a `.rasi` theme and sets the `@theme` line of `config.rasi`, after a parse check with `rofi -dump-theme`. |

- Registration order in `generators/__init__.py`: colors, Kvantum, GTK, window frame, Plasma style, panel layout, Rofi.
- `tests/test_targets_together.py`: all targets applied, undone, applied twice, generated going back to *unchanged*, and an older snapshot restored.
- Shape values on the *Applications*, *Popups*, *GTK* and *Rofi* pages are disabled, with a tooltip, while their style is *Leave as it is*.
- The drawn preview uses `apps.*` and shows a popup with a tooltip from `popup.*`. The *Application style* tab draws real Qt widgets in a generated Kvantum style (debounced; needs Kvantum and Qt's plugins).
- File menu: *Import Theme…*, *Export Theme…* (`.ptstheme` archive, `archive.py`) and *Export as Global Theme…* (`globaltheme.py`: colors, window frame and Plasma style only; applying a Global Theme always writes `[ksplashrc][KSplash] Theme=None`, so it turns the splash screen off, which the export message says). The CLI has `export`, `import` and `export-global-theme FILE FOLDER`.
- Undo removes folders that the apply created and that are empty again; a restore of a file with CRLF line ends is byte-exact.
- Rig-checked after the repair step: apply and undo with the Plasma style and Rofi from a home with no `plasmarc`, no `kdeglobals` and no Rofi folder; `install.sh` refusing a foreign scheme, installing, being listed by `plasma-apply-lookandfeel -l`, and `uninstall.sh` leaving nothing behind. Not verified: GTK 3 colors in a real session, and none of it on a real desktop. The style preview tests skip when Qt's plugin path is not set (`QT_PLUGIN_PATH=/usr/lib/qt6/plugins` with the pip PySide6).

## Built but not yet wired into the window

These modules exist with tests. The window does not use them yet; the next step builds the pages on top of them.

- `pickers/`: one kind per page of System Settings > Colors & Themes (`global_theme`, `color_scheme`, `app_style`, `plasma_style`, `decoration`, `icons`, `cursors`, `splash`, `sounds`). Each kind lists what is installed (`items()`, the item id is exactly what the desktop's configuration stores) and draws a preview card (`thumbnail()`). `loader.ThumbnailLoader` renders off the GUI thread with a disk cache under `$XDG_CACHE_HOME/plasma-theme-studio/thumbs/`. Application styles that cannot be drawn in-process (Kvantum, Union) and window decorations are drawn by a helper process (`pickers/_helper.py`: offscreen, software Qt Quick, core dumps off, no session bus, 15 s timeout); they need the distribution's PySide6 and give a fallback picture otherwise.
- `globalthemes.defaults(item)` gives the parts a Global Theme sets and `globalthemes.resolve(value, items)` matches such a value to an installed item (packages spell ids loosely).
- `ui/widgets.py`: the building blocks of the new window design (`Card`, `CardGrid`, `PageHeader`, `InlineNote`, `NavList`, `Segmented`, `DesktopBar`, `ColorDots`, `FlowLayout`).
- `wallpaper.py`: the image of the desktop wallpaper, read from Plasma's files, with a plain reason when there is none. `palette.py`: a light and a dark set of the twelve theme colors from an image, accent candidates, import of pywal, matugen and `.colors` files, contrast correction and a contrast report.
- `desktopparts.py`: read, switch and exactly undo each chosen part of the desktop (Plasma style, application style, window decoration, border size, title bar buttons, icons, pointer theme and size, fonts, sounds, splash screen, system accent color), verified by read-back, plus `open_system_settings()`. Every part was run through apply and restore in the rig with the config files compared byte for byte.
- `safefile.py`: bounded reads of regular files only, for everything read from theme folders.
- Not verified: the id KWin stores for the QML decoration Plastik (`org.kde.kwin.aurorae:kwin4_decoration_qml_plastik`); the sample icons and the sizes of SVG pointer themes are a best guess at what System Settings shows; whether Plasma updates the accent color by itself in "from wallpaper" mode.
- Open in existing code: `library.read_scheme` and `kconfig.parse` still read any file a `.colors` path points to (a FIFO or an endless file would hang the Themes list); they should go through `safefile`.

## Known limits of the new targets

- Breeze cannot change its corner radius. Only the generated frame gives an exact radius. Breeze's border step *Tiny* is 2 px at the sides and 4 px at the bottom.
- Generated frame: the top corners get the exact radius. KWin does not clip the window's content, so the bottom corners can be rounded by at most about 3.4 × the border width (square with no border). The editor says what the result will be.
- Generated frame: the title bar is 30 px high, the shadow is the same on all sides, and the colors are baked into the frame: it follows a theme or scheme put on the desktop from the app, but a scheme changed in System Settings needs an apply from the app. Hover and pressed button states are drawn but have not been checked by eye.
- Panel style: Plasma makes a panel at least 2 × radius thick and does not shrink it back when the style goes away. Undoing the style alone leaves the thicker panel; set the height under *Panel position* to get it back.
- Panel position: only the main panel is handled, and only one panel on one screen has been tried. Offset, minimum and maximum length, screen and the custom length mode are not handled. If Plasma raises the height to the style's minimum, the theme does not count as "in use" (`is_active`). The same holds for *Windows go below* and for an opacity the getters cannot tell apart while Plasma's layout dump cannot be read: the apply then simply runs again.
- Undoing a window frame does not wait for KWin; the frame changes one to three seconds later. If KWin does not answer at all (asked with `qdbus6`, or with a D-Bus ping through `busctl` when `qdbus6` is missing), the undo counts as done once `kwinrc` is back, since that is all a starting KWin reads. A KWin that answers but does not reload is a failed undo.
- Undoing the colors switches back to the scheme that was in use (Breeze Light when none was set). `plasma-apply-colorscheme` also rewrites `kdeglobals` and the GTK color files, and those are not put back byte for byte.
- A config file that ends up empty after an undo is removed (KDE reads a missing and an empty file alike); the Plasma style target also removes a `plasmarc` that did not exist before the apply (the style tool of Plasma 6.8 leaves an empty one). A file that is a link is written through and never removed.
- Undo of the Rofi `config.rasi` and of Kvantum's `kvantum.kvconfig` keeps what you changed after the apply: a file that is still exactly what the apply wrote goes back as it was (a file the apply made is removed); otherwise only our `@theme` line (the Rofi line you had is switched back on) or the `theme=` line is put back. GTK's undo already worked like that.
- The scripts of an exported Global Theme only replace and remove files that carry this app's mark. `install.sh` stops before copying anything when a file at a target path is not ours (or is a link); `uninstall.sh` keeps such files and says so, and removes the folders that are empty afterwards, also ones that were empty before the install.
- GTK 3 gets its colors from `colors.css`, which kde-gtk-config writes from the color scheme in a real session; the generated GTK 3 sheet only carries radius and border. The rig has no such module, so the colors were not seen working there. libadwaita (GTK 4) ignores the border width on buttons and entries.
- Everything in this section has been verified in the headless rig and a sandboxed home, with Plasma 6.8.2. None of it has been applied to a real desktop session yet.

## Next

1. Try the new targets (window frame, panel, Kvantum, GTK, Rofi, popups) on a real session and fix what shows up. Then tag v0.1.0 and publish the AUR package.
2. **Milestone 2:** (Kvantum generator and the preview with the real style are done.) Light and dark variants; pywal and matugen import. Klassy as an optional window frame backend.
3. **Milestone 3:** SVG editor for the generated frames; more than one panel. (Popups, tooltips and widget backgrounds in the Plasma style are done.)
4. **Milestone 4:** (GTK, Rofi, export and import are done.) Switching of Global Themes and other installed theme parts (DL-4), fonts and title bar buttons (DL-5), more distribution packages.

Smaller open items:

- The Fedora, Debian and openSUSE package names in the README are not verified on those systems.
- Title bar height, button layout and a directional shadow for the generated frame.

## Product direction (from the project owner)

- Everything about the desktop's look is editable in this one app, and every editable value has a visual preview.
- The app should do what existing tools cannot, and be exceptionally good-looking and easy to use.
- Per-part control matters: for example a rounder panel than the rest, or a border on window edges only.
- Settings normally made in System Settings (panel position and the like) should be available in the app for one consistent experience.

## Things learned

**Colors and the app itself**

- `plasma-apply-colorscheme` does nothing when the named scheme is already active, even if its file changed. Workaround in `activate_scheme`: write a placeholder name to `kdeglobals` `General/ColorScheme` with `kwriteconfig6`, then apply.
- Its exit code is not reliable. Success is verified by reading the setting back with `kreadconfig6`.
- It aborts without a display. `SystemRunner` sets `QT_QPA_PLATFORM=offscreen` when neither `DISPLAY` nor `WAYLAND_DISPLAY` is set.
- Installed color schemes vary: many lack `[Colors:Header]` and `[Colors:Complementary]`, and some color values have four components (`r,g,b,a`). `library.read_scheme` handles both.
- System Settings modules cannot be embedded in a PySide6 app, so the app builds its own controls and writes through Plasma's tools.
- Whatever puts a theme on the desktop must also make it the theme in the editor. The Themes tab once switched the desktop and left the editor on the old theme; the next apply from an editor page then brought the old theme back with one value changed. `tests/test_switching.py` states the rule for every way of switching.
- What the desktop uses is asked for when it matters (`current_scheme`), never taken from what a list showed earlier: the scheme can be changed in System Settings while the app is open.
- A window frame generated by this app follows the colors of whatever is put on the desktop, so it behaves like Breeze's own decoration. A theme that leaves the window frame at *unchanged* while such a frame is in use (kwinrc names a `PlasmaThemeStudio-*` Aurorae folder that was made here) plans a new frame with the shape of the one in use and the colors of the theme; the old folder is removed after the reload and put back by an undo. The same goes for a color scheme switch on the Themes tab (`engine.switch_color_scheme` with the scheme's theme): one snapshot, one undo. The shape is read from the `[PlasmaThemeStudio]` group of the frame's rc file, or, for folders written before that group existed, from the files (border and padding in the rc, the arc of `decoration-topleft`, the first gradient stop). A frame that is not ours or cannot be read is left alone. Panel style and panel position at *unchanged* keep what an earlier theme put there (the panel SVG uses ColorScheme classes and follows the scheme by itself), and every apply runs the reload command of each target the theme asks for, changed or not.
- Use the distribution's PySide6 (`/usr/bin/python3`), not one from pip, so the app gets the desktop's Qt style and platform integration.
- `QApplication.setDesktopFileName` with an ID whose desktop file is not installed triggers a portal warning; only set it when the file exists.

**KDE configuration files**

- A global theme writes its choices to `~/.config/kdedefaults/<file>`, which Plasma puts first in `XDG_CONFIG_DIRS`. These are defaults below the user's own file: `plasmarc` `[Theme] name`, `kwinrc` `[org.kde.kdecoration2] library` and `theme`, and more.
- `kwriteconfig6 --delete` of a key that such a default defines does not remove the line. It leaves `key[$d]`, which hides the default, so the setting falls to the built-in value instead of the global theme's. `kconfig.write_value(…, None)` removes that line again, and removes the group and the file when they end up empty, so an undo leaves the user's file byte for byte as it was. A `[$d]` line the user had before the apply is recorded in the snapshot and kept.
- `kconfig.default_value` reads the value a key has without the user's file. Undo uses it to go back to the global theme's panel style rather than to `default`.
- Values are stored escaped in the files (`\s` for a space at either end, `\t`, `\n`, `\\`). `kconfig.parse` turns them back, because `kwriteconfig6` escapes what it is given: a raw value written back would double its backslashes.
- `kwriteconfig6` writes through a config file that is a link (dotfiles). The cleaning up in `kconfig.py` does the same.

**Window frame (KWin)**

- KWin picks up decoration changes in `kwinrc` after `qdbus6 org.kde.KWin /KWin reconfigure`, without a restart. The *Decoration* block of `supportInformation` (`Plugin:`, `Theme:`) tells which one is in use, about a second late, so the generator asks a few times.
- Aurorae themes live in `~/.local/share/aurorae/themes/<folder>/` and are selected with `library=org.kde.kwin.aurorae.v2`, `theme=__aurorae__svg__<folder>`. KWin caches a theme by folder name, so the folder name carries a hash of the content and a changed frame gets a new folder. Old folders of the same theme are removed by the apply and put back by an undo.
- With `BorderSizeAuto=false`, the `BorderSize` names give the generated frame an exact border of 0 to 12 px: Aurorae keeps the border within a range per name, and the generator picks the name whose range holds the wanted width.
- Breeze's fixed steps, measured in a running KWin: shadow 16, 32, 48, 64 px (Small to VeryLarge), `ShadowStrength` 25 to 255, borders Tiny 2, Normal 4, Large 6, VeryLarge 8, Huge 10, VeryHuge 12, Oversized 20 px.
- A decoration cannot round the window's own content. A corner is only as round as the border leaves room for: radius ≤ border × (2 + √2).
- `borderSize` in `supportInformation` is the number of the border size name (Tiny 2, Normal 3 and so on), not pixels. After an undo to "no decoration key at all", KWin reports an empty `Theme:` although it draws Breeze.
- Measured in the rig: the generated frame's border is exact for 0 to 12 px, the title bar is 30 px, and a maximized window has no border. At scale 2 everything doubles exactly.
- A window that a top panel pushed down stays where it is when the panel moves back.

**Panel style and position (plasmashell)**

- `plasma-apply-desktoptheme <id>` finds a package in `~/.local/share/plasma/desktoptheme/` without `kpackagetool6`. An unknown id exits with 255; an id that is already set exits with 0 and changes nothing; `default` leaves `plasmarc` empty on Plasma 6.8 (older tools wrote `name=default`). Plasma redraws the panels at once when the style name changes, so a changed style gets a new id (name plus content hash).
- The shadow tiles of a panel background must be transparent under the panel itself, or a translucent panel turns dark.
- Panel scripting (`evaluateScript` on `org.kde.plasmashell /PlasmaShell`) changes the panel live. The `hiding` getter answers `none` for *windows go below*, and `plasmashellrc` and the applets file are written 5 to 10 seconds late, so the state is read from `dumpCurrentLayoutJS`, which is live. It has no panel ids, and `normal` there means no hiding.
- Changing only the alignment or the length mode does not move the panel until something else triggers a relayout. The script toggles `floating` and back for that.
- The script sent to plasmashell is a fixed program plus one line of JSON with the request, so no value from a theme file is ever run as code. It checks every value before it sets any, so a refused request changes nothing. The lowest height comes with the request: 20 px for a theme, 1 px for an undo, so a thinner panel can be given back.
- For a few seconds after the Plasma style changes, the old style's minimum thickness still holds: a 14 px panel asked for right after a style with radius 12 went away comes back as 24 px, and Plasma does not make it thinner by itself later. `_write_settled` asks for the thickness again (up to 8 times, 0.75 s apart) while the panel is thicker than wanted. Seen in the rig, where an undo then gives the thin panel back on the first try.
- Plasma's own lowest panel thickness is 12 px (10 is answered with 12).
- A floating panel is drawn flat and full width while a window touches it. A screenshot with a window next to the panel therefore shows no rounded panel.

**Working on it without disturbing the desktop**

- `tests/conftest.py` gives every test its own `QSettings` folder and application name, so `last_file` neither leaks between tests nor reaches the real settings.
- When taking screenshots or testing the UI from a script, use `QT_QPA_PLATFORM=offscreen` so no window appears on the developer's desktop, and mark the undo stack clean before quitting so the unsaved-changes dialog does not block.
- Create a Qt application before using `QtSvg` (`QSvgRenderer` aborts without one), and keep generated SVG free of `<text>`. Run helper scripts and rig programs under `prlimit --core=1:1 --` so that a crash leaves no core dump notification.
- Never run `kwriteconfig6`, `plasma-apply-*`, KWin `reconfigure` or a writing `evaluateScript` against the session you work in. Use the rig, or a throwaway home with `env -i HOME=… XDG_CONFIG_HOME=…`.
- The tests set `XDG_CONFIG_DIRS` to a temporary folder (`tests/conftest.py`), so they never read the real `kdedefaults`.
- Rig: `KWIN_COMPOSE=Q` crashes KWin on a screenshot (the rig's default, software rendering for Qt Quick only, works); Xwayland is not started; the rig inherits `XDG_CONFIG_DIRS`, so the real `kdedefaults` are visible in it (read only); `screenshot` is called on its own, not through `run`; `kcmshell6 kcm_kwindecoration` works inside it.

- A restore must be byte-exact: files are read with `newline=""`, or CRLF files come back changed.
- A file-valued setting that is restored can leave its folder empty (`.config/Kvantum`, `.config/rofi`); `engine.restore` removes the folders the snapshot recorded as created.
- Generated Kvantum controls grow taller with the radius, so buttons, fields and tabs are capped at 8 px.
- Rofi's window mode does not work on KWin, and a theme is checked with `rofi -dump-theme` before it is written.
- Moving a generated target back to *unchanged* reverts nothing: the earlier output stays in use and an undo restores it.

## How to work on it

```sh
.venv/bin/python -m pytest          # runs offscreen; tests/conftest.py sees to that
.venv/bin/ruff check . && .venv/bin/ruff format .
scripts/update-translations.sh sv
```

The headless rig, for trying an apply against a real KWin and plasmashell that are not yours:

```sh
/usr/bin/python3 scripts/desktop_rig.py start /tmp/rig --plasmashell
/usr/bin/python3 scripts/desktop_rig.py run /tmp/rig -- env QT_QPA_PLATFORMTHEME=kde "$PWD/plasma-theme-studio" apply my-theme.toml
/usr/bin/python3 scripts/desktop_rig.py window /tmp/rig --title Test
/usr/bin/python3 scripts/desktop_rig.py screenshot /tmp/rig /tmp/shot.png
/usr/bin/python3 scripts/desktop_rig.py stop /tmp/rig
```
