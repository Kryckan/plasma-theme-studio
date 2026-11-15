# Project status

Where the project stands, what comes next, and things learned along the way that are easy to forget. The plan itself is in [PRD.md](PRD.md); user-visible changes are in [CHANGELOG.md](../CHANGELOG.md). Update this file in the same commit as the work it describes.

Last updated: 2026-11-15

## Done

**Milestone 1 (v0.1), not yet tagged**

- Theme model and TOML file format (`model/theme.py`). Optional fields that follow another field until set (`Field.inherits`, `Theme.resolved`): `window.radius`, `window.border_width`, `panel.radius`, `panel.border_width`.
- Color scheme generator and activation (`generators/colorscheme.py`).
- Apply engine with snapshots, rollback and restore (`apply/`).
- Library of installed color schemes and saved themes (`library.py`), switching between schemes (`engine.switch_color_scheme`).
- Qt Widgets UI: editor, drawn preview, Themes tab, result banner, snapshot dialog (`ui/`).
- CLI, Swedish translation, PKGBUILD, CI (ruff, pytest, REUSE, AppStream validation).

**Build 3 (in the working tree, not yet committed)**

- Verified apply and exact undo: `apply/sidefiles.py` copies what KDE's tools and daemons write on their own (GTK color sheets, `gtk.css`, `settings.ini`, `xsettingsd.conf`, `Trolltech.conf`, the color groups of `kdeglobals`) into the snapshot and puts it back after an undo. `scripts/rig_roundtrip.py` applies every case in a rig, undoes it and compares the home.
- The frame editor (`ui/frame_editor.py`) on the Plasma Style page: own artwork for the four frames (panel, popups, tooltips, widgets; `generators/artwork.py`), nine-part guides, *Open in Inkscape…* and *Back to the generated frame*. Own artwork travels in the `.ptstheme` archive. The embedded SVG draw mode of PRD SV-3 does not exist.
- Up to six panels (`panel_layout`, `panel_layout_2` ...) on the Panel page, window frame extras (title bar height, button size and spacing, shadow offsets), the palette mapping dialog for pywal and matugen (`colors_import.py`), colors from a picture (`colors_picture.py`), *Switch to Dark Mode at Night* with night variants (`nightvariants.py`), light and dark variants.

**Brought forward from milestones 2 and 3**

Three more targets reach the desktop. Each is opt-in: a theme that leaves the choice at *unchanged* (the default) touches nothing but the colors.

| Target | Module | Theme values | What an apply does |
|---|---|---|---|
| Window frame | `generators/windowframe.py` | `window.decoration` (`unchanged`, `breeze`, `generated`), `window.radius`, `window.border_width`, `shadow.size`, `shadow.strength` | *breeze*: sets Breeze as decoration and maps border and shadow to Breeze's fixed steps. *generated*: writes an Aurorae theme (SVG frame with the exact radius, border, shadow and the theme's colors) and selects it. KWin is reloaded and asked which decoration it uses. |
| Panel style | `generators/plasmastyle.py` | `panel.style` (`unchanged`, `generated`), `panel.radius`, `panel.border_width`, `panel.opacity` | Writes a Plasma style package that only replaces the panel background and selects it with `plasma-apply-desktoptheme`. Everything else falls back to Breeze. |
| Panel position | `generators/panellayout.py` | `panel_layout.*`: location, height, alignment, length mode, floating, visibility, opacity mode. Every value is optional. | Sets the given values on up to six panels (`panel_layout` is the main one, `panel_layout_2` and on the others) through Plasma's scripting interface and reads them back. |

Supporting pieces:

- `kconfig.py`: reads and writes single keys in KDE's config files and cleans up after `kwriteconfig6` (see *Things learned*).
- Generators report the settings they change (`Generator.changed_settings`), notes for the editor page (`Generator.notes`) and files that an apply removes (`stale_files`). The apply summary and *Show files…* show them before anything is written.
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

## What is left

- Tag v0.1.0 after a try in a real session (nothing here has been applied to one).
- Klassy as a window decoration backend (not installed here, so not built).
- The embedded draw mode of the frame editor (PRD SV-3); *Open in Inkscape…* exists.
- The package names for Fedora, Debian and openSUSE in the README are not verified; packages for other distributions.

## Left over from the earlier steps

- Open after repair step 4: the window-frame cards and the Overview preview draw round red, yellow and green dots at the right and a left-aligned title (`ui/this_theme.py`, `ui/preview.py`), while the real frame centres the title and uses line glyphs; the accent swatch order changes between the light and dark variants; the Overview says "Not looked at, the theme leaves it"; a modal *unsaved changes* question blocks a headless close (`main_window.py`); the Shapes menu preview clips "Settings"; the dark-mode side bar icons of Splash Screen and System Sounds almost vanish; the Plasma Style page keeps its search box above the page scroll when the frame editor is in view; an Undo waits up to about 6 s per snapshot for the daemons (`desktop.keep_alive` keeps the window alive); a picture with many filters is bounded by `artwork._heavy`, but it is still drawn on the GUI thread (a render in a child process with a time limit would be the real fix); the tests of repair step 3 for the zip import, the FIFO `kdeglobals` and the cache key by language check little. Open from earlier: Themes page grid height and night-mode text; the muted look of *Left as it is* entries in the side bar; jargon notes on GTK Apps, Rofi and Kvantum not yet moved behind *More about this*; empty Login Screen and System Sounds pages; frame editor guides spacing. Python overrides of virtual methods on widget subclasses (a `resizeEvent` on `CardGrid`) crash PySide 6.12 at test teardown, so `CardGrid` polls with a timer instead.

- The CLI `status` and `apply` cover every target; the window shows the same status through the side bar dots and the Overview. The CLI keeps its own words for the states ("Would change", "Left alone", "Refused"); only the window uses `STATE_WORDS`.
- Not verified: the sample icons and the sizes of SVG pointer themes are a best guess at what System Settings shows; whether Plasma updates the accent color by itself in "from wallpaper" mode; the eight accent colors of the Colors page (`STANDARD_ACCENTS`) are not checked against the list System Settings offers.

## The window

- `ui/main_window.py` is the shell: a 236 px side bar (theme block with the File menu, `NavList` in the groups Overview, Library, Basics, Desktop, Apps), a `Banner` and the page stack, the permanent `DesktopBar` (status sentence, *Show files…*, *Snapshots…*, *Undo last apply*, *Apply to Desktop*), the menu bar and the *Show files…* dialog (`ui/files_dialog.py`). `window.apply_button`, `undo_apply_button`, `banner`, `library`, `preview`, `style_preview` are kept for the tests.
- Pages live in `ui/pages/`; `pages/__init__.py` is the lazy registry (`PAGES`, `GROUPS`, `SPECS`, `create`, `title_of`, `parts_of`). A `PageSpec` has a `kind`: "page" (a normal page) or "link" (a part this app does not edit: `link` is the System Settings module, the page is a `LinkPage` with an explanation and a button that calls `desktopparts.open_system_settings`; `login_screen.py`, module `kcm_sddm`, is the first and ends the Desktop group). `pages/base.py` documents the API with examples: `Page`, `ValuePage` (controls and preview), `PickerPage` (a `CardGrid` of installed things, a part switch, optional tuning values), `TargetPage` (a part that is only written) and `LinkPage`. A page is made when first shown; `window.build_pages()` makes all of them (tests).
- Page layout. A picker page scrolls once: the header and the part switch stay, the search bar is outside the scroll (so it is always in view), and the grid (full height; a `CardGrid` with `tall=True` on Colors takes the height of its cards and has no scroll bar of its own), the tuning block, extra controls and notes are in one scroll area. Thumbnails are asked for only when a card is first painted. Extra room, all in `base.py`: `add_top_row(widget)` (between part switch and grid), `add_below(widget)` (under the grid), `set_side_preview(widget, width)` (a column on the right; a `TargetPage` has the same slot), and the header actions of `PageHeader`. The cards "This theme" and "Breeze with your changes" call `this_theme_thumbnail(size, dpr) -> QImage`; the default is `ui/this_theme.py` (decorations: active in front of inactive window with the theme's frame; Plasma style: clock on the generated panel; application style: real widgets through the generated Kvantum theme, a drawn stand-in without it; color scheme: card from the twelve colors). A page overrides the method for its own picture. The cards are redrawn 150 ms after the last edit.
- The part switch of a picker remembers the choice made before "Leave as it is" (`page.remembered`), so Leave and Set bring it back, for the session.
- Navigating never edits and editing never navigates. Every edit goes through `window.edit(field, value)` or `window.edit_many(text, {field: value})` (one undo step, nothing changes when one value is refused).
- The side bar dots and the dimming of a page come from `engine.parts_status`. It runs in a worker (`QThreadPool`, one thread) on a copy of the theme; every start bumps `window.status_generation` and an answer for an older generation is dropped. It is started after the first paint and 200 ms after the last edit; the Desktop bar keeps its last sentence while an answer is pending. Tests call `window.settle()` after anything that changes the theme to wait for the answer. The runner is used from the worker, so it must be thread-safe: `SystemRunner` is plain subprocess calls and `FakeRunner` plain Python; a runner must not touch widgets. "Apply to Desktop" is disabled, with a tooltip, when the status says nothing would change, and any edit enables it again until the next answer. A blocked part makes the bar name the part and why. The state words of the Overview are one vocabulary, `apply.status.STATE_WORDS` / `state_word()`: "Will change", "Already so", "Left as it is", "Cannot be applied"; part titles are those of the side bar. The apply button acts on the selected card while the Themes page is shown and on the editor theme elsewhere; its tooltip names the theme.
- The side bar is compact (28 and 24 px rows) when the normal rows do not fit the height (1100x720), so every entry is reachable without a scroll bar.
- In the Panel mode the preview shows the whole screen edge the panel is on (full length, as deep as panel, gap and popup), at the side of the picture that is that edge; the Menu mode holds popup, tooltip and panel without clipping.
- QSettings keys: `window/geometry`, `window/page`. Closing with unsaved changes asks first.
- Thumbnails of pickers come from `ThumbnailLoader` (disk cache); the cards of "This theme" and "Breeze with your changes" are drawn in-process by `PreviewWidget.render_image`.
- First paint (window construction to the first painted frame, offscreen, 1400x900): 0.05 to 0.15 s.
- The pages (all in `ui/pages/`, each with tests in `tests/test_page_*.py`):
  - Overview: name and author, "On the desktop now" and "In the editor" with drawn previews, one clickable row per part with a state chip, Recent (last three applies), a link to the file list.
  - Themes: chips All / My themes / Global Themes / Color schemes with search; saved themes, installed Global Themes (package picture) and color schemes. A Global Theme is loaded into the editor (one undo step, parts the app cannot match are reported); "Apply to Desktop" on it asks first, loads, then applies the editor theme. It never runs `plasma-apply-lookandfeel`. Header: "New Theme from the Desktop", a "Get More" menu. *Switch to Dark Mode at Night* sets `AutomaticLookAndFeel` and the light and dark Global Themes (`nightvariants.py`, the part `night_variants`).
  - Colors: accent row (eight standard dots, the theme's own, a custom color, a "From the wallpaper:" row, "Let the accent follow the wallpaper"), a searchable All/Light/Dark card grid of color schemes (full height in the page's one scroll area, `CardGrid(tall=True)`), "Install from File…", "Import Colors…" (pywal, matugen, `.colors`), the collapsible "Colors from the wallpaper" block (picture decoded in a worker, refused over 40 million pixels from the header), twelve color editors and the contrast box ("Fix contrast" is one undo step). Colors has no Leave/Set switch: the theme cannot store it.
  - Shapes, Fonts (six rows with a sample, "Use one family for all"), Plasma Style (cards, a "Panel" and a "Popups and tooltips" block for This theme), Panel (one switch "Leave as it is | Set by this theme", a Panel 1 | Panel 2 chooser, a switch per panel, screen chooser, seven values with "As it is now" and a clear button, live preview), Window Decorations ("Window border size", "Configure Titlebar Buttons…" with drag and drop, frame and shadow values for This theme and Breeze), Icons (six sample icons per card and a strip of a dozen at 32 and 48 px), Pointers (eight samples per card, "Size:" and "Configure Launch Feedback…"), Splash Screen (a large preview), System Sounds (a list with Play: `pw-play`, `paplay` or `canberra-gtk-play`, picked when pressed), Login Screen (SDDM) (an explanation and a button), Application Style (cards, "Configure Icons and Toolbars…", values beside a sample of real widgets), GTK Apps and Rofi (drawn previews).
- Words every page shares: "Leave as it is | Set by this theme" (part switch, also on Panel), "In use" / "Not in use yet", "This theme" and "Breeze with your changes", "…" only on a button that opens a dialog or another program, "Search…". A missing program is said in a note on the page (Kvantum) or in a warning banner when a button needs it (System Settings, a sound player).
- Known gaps: cards of the picker grids have a fixed width, so a strip of free room can remain at the right edge; a Global Theme is not installed as a whole (panel layout and widgets are not set), only the parts the app can edit.
- Measured before Build 3, offscreen at 1400x900 with the installed themes of this machine (Plasma 6.8.2, Qt 6.12): construction 57 ms, show 34 ms. Switching to a page for the first time: Overview to Rofi 0 to 38 ms, Application Style 144 ms (it builds a sample of real Kvantum widgets on the GUI thread), a second visit 2 to 6 ms. The longest GUI slice while a page filled was 27 ms (Application Style) and 12 ms elsewhere; icons, pointers and thumbnails are loaded by workers and the loader (one SVG per tick).

## Things learned about the window

- A `QUndoStack` merges two edits of one field that come within a second. A test that edits a field twice and then undoes once gets the state before both.
- `QMessageBox.warning` is a static call; tests replace it with `monkeypatch.setattr(QMessageBox, "warning", staticmethod(...))`. A real box in a test waits forever.
- `QTest.mouseClick` on a widget that is `None` aborts the whole interpreter (a Qt assert), so look the card up first.
- A hidden page is not refreshed on an edit (it is marked stale and updated when shown). Only the notes are kept current. Tests that look at the controls of a page they have not shown call `window.refresh()` and `window.build_pages()`.
- Widgets disabled through a parent stay disabled for `isEnabled()`; check the parent box too.
- Cards of the picker grids are checkable buttons; a click on the selected card does not unselect it.
- `QSettings` key `window/page` that names no page opens the Overview.
- `window.settle()` loops until no answer is pending; a test that bumps `status_generation` by hand is asked again by it. `edit()` refreshes after a 30 ms timer: a test that looks at the result calls `window.refresh()`.
- Painting a `PreviewWidget` mode that shows a part of the scene must clip to that part, or the rest of the scene shows in a tall widget.
- A `CardGrid(fit=True)` grows with its width; its vertical size policy must be Preferred. With Minimum a scroll area takes the height of the narrowest layout as the page's minimum and leaves a huge empty gap (fixed in `widgets.py`).
- `DesktopRunner` keeps `kdeglobals` as a real file, so a test that wants a color scheme in use sets it with `kwriteconfig6`, not with `runner.settings`.
- Swedish words in `i18n`: Apply is "Verkställ", accent is "accentfärg", wallpaper "skrivbordsunderlägg", fonts "teckensnitt", Plasma style "Plasmastil".

## Known limits of the new targets

- Breeze cannot change its corner radius. Only the generated frame gives an exact radius. Breeze's border step *Tiny* is 2 px at the sides and 4 px at the bottom.
- Generated frame: the top corners get the exact radius. KWin does not clip the window's content, so the bottom corners can be rounded by at most about 3.4 × the border width (square with no border). The editor says what the result will be.
- Generated frame: the title bar height (30 px at the default), the button size and spacing and the shadow offset are theme values; the colors are baked into the frame: it follows a theme or scheme put on the desktop from the app, but a scheme changed in System Settings needs an apply from the app. Hover and pressed button states are drawn but have not been checked by eye.
- Panel style: Plasma makes a panel at least 2 × radius thick and does not shrink it back when the style goes away. Undoing the style alone leaves the thicker panel; set the height under *Panel position* to get it back.
- Panel position: up to six panels (`panel_layout`, `panel_layout_2` ...), numbered main panel first and the rest by id; an entry for a panel that is not there is skipped and said so, and no panel is created or removed. Only one or two panels on one or two screens have been tried. Offset, minimum and maximum length and the custom length mode are not handled. If Plasma raises the height to the style's minimum, the theme does not count as "in use" (`is_active`). The same holds for *Windows go below* and for an opacity the getters cannot tell apart while Plasma's layout dump cannot be read: the apply then simply runs again.
- Undoing a window frame does not wait for KWin; the frame changes one to three seconds later. If KWin does not answer at all (asked with `qdbus6`, or with a D-Bus ping through `busctl` when `qdbus6` is missing), the undo counts as done once `kwinrc` is back, since that is all a starting KWin reads. A KWin that answers but does not reload is a failed undo.
- Undoing the colors switches back to the scheme that was in use (Breeze Light when none was set). `plasma-apply-colorscheme` also rewrites `kdeglobals` and the GTK color files, and the undo puts those back too (`apply/sidefiles.py`), but only for the targets that really ran in that apply, so a scheme chosen in System Settings since an apply of fonts survives. The undo waits up to about 6 s for the GTK daemon to go quiet before it does.
- A config file that ends up empty after an undo is removed (KDE reads a missing and an empty file alike); the Plasma style target also removes a `plasmarc` that did not exist before the apply (the style tool of Plasma 6.8 leaves an empty one). A file that is a link is written through and never removed.
- Undo of the Rofi `config.rasi` and of Kvantum's `kvantum.kvconfig` keeps what you changed after the apply: a file that is still exactly what the apply wrote goes back as it was (a file the apply made is removed); otherwise only our `@theme` line (the Rofi line you had is switched back on) or the `theme=` line is put back. GTK's undo puts `gtk.css` back as the snapshot has it (the daemon's own `@import 'colors.css';` line goes with it).
- The scripts of an exported Global Theme only replace and remove files that carry this app's mark. `install.sh` stops before copying anything when a file at a target path is not ours (or is a link); `uninstall.sh` keeps such files and says so, and removes the folders that are empty afterwards, also ones that were empty before the install.
- GTK 3 gets its colors from `colors.css`, which kde-gtk-config writes from the color scheme in a real session; the generated GTK 3 sheet only carries radius and border. The rig has no such module, so the colors were not seen working there. libadwaita (GTK 4) ignores the border width on buttons and entries.
- Everything in this section has been verified in the headless rig and a sandboxed home, with Plasma 6.8.2. None of it has been applied to a real desktop session yet.

## Parity gaps and open items

- Still only launched, not rebuilt: the Login Screen page (SDDM). *Get New…* does not download anything; *Find More in System Settings…* opens the real page. *Configure Icons and Toolbars…* and *Configure Launch Feedback…* now open small dialogs in the app (`ui/pages/small_settings.py`).
- The live preview (`ui/preview.py`) does not honour the title bar height, the button size or the shadow offset of the generated frame; the large frame preview on the Window Decorations page does.
- Panel numbering: Plasma may number the panels differently after a restart than the order the app saw. A theme names panels by number, so it can hit another panel; this is a limit, not a fault to chase.
- Light and dark variants: the apply writes one variant; following the desktop's own light/dark switch (`--variant`, *Add a Dark Variant*) is manual. A scheme changed in System Settings needs an apply from the app.
- First visits to Icons (150+ themes) and the pointer status still build many cards on the GUI thread. The cards are drawn as they come into view, so the page opens at once, but the status read is not in a worker for every part.
- Not tried on a real session: everything in "Newer targets". The rig (`scripts/desktop_rig.py`, `scripts/rig_roundtrip.py`) has applied and undone every case with an identical home, but a real desktop has not been used.
- Apply stays enabled right after an edit even when the edit changes nothing on the desktop; the status worker turns it off again. A button that is off after a real edit is the worse fault.

## Product direction (from the project owner)

- Everything about the desktop's look is editable in this one app, and every editable value has a visual preview.
- The app should do what existing tools cannot, and be exceptionally good-looking and easy to use.
- Per-part control matters: for example a rounder panel than the rest, or a border on window edges only.
- Settings normally made in System Settings (panel position and the like) should be available in the app for one consistent experience.

## Things learned

**Colors and the app itself**

- A theme can name an installed color scheme (`colors.scheme_id`). While every color equals that scheme's, the apply activates it by name and writes no scheme file; one changed color makes the app write a scheme of its own. Exported packages always carry their own scheme.
- `engine._execute` leaves a part alone when its files are unchanged and the desktop already has it (`_settled`), so *New Theme from the Desktop* followed by Apply is a no-op.
- `AutomaticLookAndFeel` in `kdeglobals` `[KDE]` is System Settings' "switch between light and dark Global Theme" switch (the `night_mode` part).
- Pictures are opened only through `images.open_reader`: regular files, at most 40 million pixels, 256 MB decode limit. A FIFO named as a picture would otherwise hang the reader.

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

**Installed parts**

- Plastik (the QML decoration) is chosen as `library=org.kde.kwin.aurorae`, `theme=kwin4_decoration_qml_plastik` and KWin's `supportInformation` reports exactly that as loaded (verified in the rig), so the picker id `org.kde.kwin.aurorae:kwin4_decoration_qml_plastik` is right.
- Rig run of a theme naming every installed part (style, decoration, border size, buttons, icons, pointers, fonts, splash, sounds): after the undo every config file was identical to the copy taken before (the side files of `sidefiles.py` included).
- The text color on an accent (or any background) is the one of the two candidates with the better contrast ratio, not a luminance threshold.

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
- Measured in the rig: the generated frame's border is exact for 0 to 12 px, the title bar is 30 px at the default, and a maximized window has no border. At scale 2 everything doubles exactly.
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

- Tests delete every window when the test ends (`windows_do_not_outlive_their_test` in `tests/conftest.py`). Before that the windows of 1900 tests piled up: 2.1 GB and 211 threads at the end of a run, 5.2 GB of address space, and CI (another Python and Qt build) died at the 8 GB cap with a bare `Aborted`. Now a run ends at 0.26 GB and 9 threads.
- Side files (`apply/sidefiles.py`): the snapshot copies the files a daemon writes after an apply (`watched()`: GTK sheets, `settings.ini`, `xsettingsd.conf`, `Trolltech.conf`, `kdedefaults`) and the color groups of `kdeglobals` only (`OWNED_GROUPS`, `OWNED_KEYS`; the rest of the file belongs to the user). An undo puts them back last, after waiting for the daemon to go quiet, and only for the targets that ran in that apply: the snapshot records them in `reached` (`snapshots.set_reached`), because the plan also holds targets that were already so. `COLOR_TARGETS` decide whether the color groups and the GTK color sheets go back, `SIDE_TARGETS` whether anything does. Guards: a pipe or a file over 2 MB is never read, a tree over 400 files is not kept, and the record of a manifest is trusted only for paths that `watched()` names and stored names that stay in the store folder.
- Never assign `__class__` on a live Qt object (a layout, a widget). It worked until a garbage collection ran, then `QAbstractButton.setChecked` crashed in `PySide::MetaObjectBuilder::update` while it looked for sibling buttons. `CardGrid(flow_class=…)` chooses the layout class instead.

## How to work on it

```sh
flock /tmp/pts-suite.lock scripts/capped .venv/bin/python -m pytest -q -p no:cacheprovider   # offscreen; about 1900 tests; add QT_PLUGIN_PATH=/usr/lib/qt6/plugins to run the 6 style-preview tests too
.venv/bin/ruff check . && .venv/bin/ruff format FILES
scripts/update-translations.sh sv
scripts/capped COMMAND...           # memory capped at 8 GB, first to be killed, no core dump
```

Run throwaway scripts, helpers and anything that builds or reads hostile input through `scripts/capped`.
A fixture script that built a pointer file of 100000 x 100000 pixels in memory once filled all memory and
swap, and the kernel killed unrelated programs first. A hostile file is written truncated or sparse; its
declared size is never built in memory. The test run caps itself (`tests/conftest.py`,
`PTS_TEST_MEMORY_CAP`), and the rig makes itself the first to go when memory runs out.

The headless rig, for trying an apply against a real KWin and plasmashell that are not yours:

```sh
/usr/bin/python3 scripts/desktop_rig.py start /tmp/rig --plasmashell
/usr/bin/python3 scripts/desktop_rig.py run /tmp/rig -- env QT_QPA_PLATFORMTHEME=kde "$PWD/scripts/capped" "$PWD/plasma-theme-studio" apply my-theme.toml
/usr/bin/python3 scripts/desktop_rig.py window /tmp/rig --title Test
/usr/bin/python3 scripts/desktop_rig.py screenshot /tmp/rig /tmp/shot.png
/usr/bin/python3 scripts/desktop_rig.py stop /tmp/rig
```

### PySide6 6.12 with Python 3.14

- Crashes (segfault in `gc.collect()`, mostly while a test tears down) come from Python subclasses of Qt widgets and layouts that override virtual methods. They depend on allocation timing, so any unrelated change moves them. Under `PYTHONMALLOC=malloc MALLOC_PERTURB_=85` pages with a `CardGrid(fit=True)` crashed deterministically at an earlier commit; the whole suite passed under it once at the Build 3 commit, so treat it as fragile, not as broken. The Colors page uses `tall=True` with a timer; the pages with `fit=True` and the frame editor (`frame_editor.py`) are the ones to try first when it crashes.
- A Python `eventFilter` on the main window freed its method and crashed; the window no longer has one. `_SegmentButton` sets a minimum size instead of overriding `sizeHint`. `FlowLayout` is one class (`JustifiedFlow` is a `partial`), not a subclass.
- When bisecting a crash like this, do not stop at the first failure (`-x`): count the runs that exit with a code of 128 or more.
- Workers are stopped when the window hides or closes (`MainWindow.stop_page_workers`), and `ColorsPage.stop_workers` waits for its pool, or a thread pool task can touch a deleted widget.
- Card captions need a few pixels of air under the last line (`Card.CAPTION_AIR`), or descenders touch the card's border.
