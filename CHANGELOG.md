# Changelog

All notable changes to Plasma Theme Studio are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased (0.1.0)

### Added

- *Follow the palette* on the Colors page and `plasma-theme-studio follow on|off|status|--once`: the colors and the accent of the desktop follow a pywal or matugen palette file, also with the window closed. Switching it on takes one snapshot; switching it off goes back.
- A user guide (`docs/guide.md`) with pictures of every page, made again by `scripts/make_screenshots.py`.
- Packaging: one installer, packages for Arch (releases and latest code), recipes for Fedora, openSUSE, Debian and Ubuntu, and CI jobs that check them.
- A login screen sketch for a login theme without a picture, and *More about this* on pages that had technical notes.
- A frame editor on the Plasma Style page: own artwork for the panel, popups, tooltips and widget backgrounds, nine-part guides, *Open in Inkscape…* and *Back to the generated frame*. Own artwork is packed into `.ptstheme` archives.
- An undo that also puts back what KDE's tools and daemons wrote on their own (GTK color sheets and settings, `xsettingsd.conf`, the color groups of `kdeglobals`), for the parts that took part in that apply.
- Several panels on the Panel page (up to six, a chooser for each), and window frame extras: title bar height, button size, space between buttons and shadow offsets.
- *Import Colors…* has a mapping dialog for pywal and matugen palettes, colors can be taken from a picture, and *Switch to Dark Mode at Night* picks a light and a dark Global Theme.
- Light and dark variants: *Add a Dark Variant* on the Colors page; the Overview and the apply follow the variant on the desktop, and `apply` and `status` take `--variant light|dark`.
- *Configure Icons and Toolbars…* and *Configure Launch Feedback…* open small dialogs inside the app instead of System Settings.
- *Fix Contrast…* shows each color as it is and as it will be before it changes anything.
- Every part, including the new ones, shows in the status bar, the Overview and *Show files…*.
- Swedish translation of all new text.
- `scripts/rig_roundtrip.py` checks that an apply and its undo leave a throwaway desktop's home as it was.

### Changed

- Own artwork that the draw process cannot draw in time or at all is no longer installed by Apply: the generated frame is, with a warning. A picture that only timed out is tried again after a few minutes, and an imported one once more at once.
- The progress window of Undo and of reading a theme now shows when the work is slow.
- Follow mode: switching it on again under another theme name keeps one color scheme file, a launcher path that cannot be written to the autostart entry is refused, an autostart entry that is not ours is not replaced, a switch-off or undo during an apply no longer brings the state file back, and the lock file is not opened through a link. The Colors page says that applying another theme does not stop following.
- SVG artwork is drawn in a child process with a time and memory limit, so a bad picture cannot freeze the window. A drawing that failed because the machine was busy or the child was killed from outside is tried again after a few minutes, like a timeout.
- An undo, a switch-off of follow mode or a watcher write that cannot get the shared write lock within 30 seconds does nothing and says so, instead of going on; the command line prints a line while it waits. Closing the window during an undo waits for the undo.
- A Global Theme export leaves out an own picture that cannot be drawn, as Apply does.
- Application Style at a small window size shows the whole sample and no gap above it.
- A package that Apply installed without a picture the draw process could not draw is still seen as the theme's package by the next start of the app and by the command line, so *Apply to Desktop* stays off and the Overview says *Already so*.
- Undo and switching off *Follow the palette* now wait for the watcher's write to end (one shared lock), so the watcher can no longer write colors after an undo and leave the home different from the snapshot.
- The user guide names the wallpaper buttons as they are (*Use as light theme*, *Use as dark theme*), says where the section is, and shows the dark pictures.
- *Undo* of several applies runs in the background with a progress dialog.
- The window frame in the previews is drawn like the real one: centred title, your button layout and size, your shadow.
- Accent colors are listed by hue; *Left as it is* is shown muted.
- Card captions have a little more air under the last line.
- The same words are used for the same things on every page: *Colors from a Picture…*, *Configure …*, *Leave as it is*.

- Every page of System Settings' Colors & Themes part now has a page in the app with preview cards: Themes (also the installed Global Themes, loaded into the editor), Colors, Application Style, Plasma Style, Window Decorations, Icons, Pointers, Splash Screen, System Sounds and Login Screen (SDDM), and Fonts.
- Colors: an accent color row (standard colors, your own, colors from the wallpaper, or let the accent follow the wallpaper), color scheme cards drawn as small windows with search and a Light/Dark filter, *Install from File…*, *Import Colors…* (pywal, matugen and `.colors` files), theme colors taken from a wallpaper or any picture, and a contrast check that lists text that is hard to read and fixes it with one click.
- Window Decorations: *Window border size*, *Configure Titlebar Buttons…* (drag buttons between the title bar and a pool), and the frame and shadow values with a large preview.
- Plasma Style cards show a clock on the style's panel, and the Panel page has a screen chooser with a preview of the whole screen edge.
- Icons, Pointers, Splash Screen and System Sounds show sample icons, eight sample pointers, a large splash preview and a list of sounds with a *Play* button; Pointers has a *Size:* choice and *Configure Launch Feedback…*; Application Style has *Configure Icons and Toolbars…* and a sample of real widgets.
- Fonts has a row for each of the six fonts with a sample and *Use one family for all*. GTK Apps and Rofi show a drawn preview.
- Overview shows the desktop now next to the editor, one row for each part with what an apply does to it, and the last applies.
- Pages with cards scroll as one page: the title, the part switch and the search stay in view, the cards are drawn when they come into view.
- The cards *This theme* and *Breeze with your changes* show the part itself: window frames, the panel with its clock, real widgets in the generated application style, and the color scheme.
- *Leave as it is* | *Set by this theme* remembers your earlier choice while the app is open.
- The state of every part is read in the background, so typing and dragging stay smooth. *Apply to Desktop* is off, with an explanation, when nothing would change, and the bar names a part that cannot be applied and why.
- A page *Login Screen (SDDM)* that explains why the login screen is not edited here and opens its System Settings page.
- The side bar fits in a window of 1100 x 720 without a scroll bar. The Overview uses the same words for every part: *Will change*, *Already so*, *Left as it is*, *Cannot be applied*.
- The Panel preview shows the whole screen edge with the panel where it really is.
- *Show files…* is laid out like the rest of the window, with a plain sentence on top and three lists: will be written, already up to date, will be removed.
- A new window: a side bar with the pages Overview, Themes, Colors, Shapes, Fonts, Plasma Style, Panel, Window Decorations, Icons, Pointers, Splash Screen, System Sounds, Application Style, GTK Apps and Rofi, a dot beside every part that an apply would change, and a bar at the bottom with what an apply does and the buttons *Show files…*, *Snapshots…*, *Undo last apply* and *Apply to Desktop*. The window remembers its size and the page it was on.
- Pages for the icon, pointer and sound themes, the splash screen, the Plasma style, window decorations and the application style show what is installed as cards. Choosing one sets it in the theme; *Leave as it is* | *Set by this theme* turns a part off or on. Each choice is one step of undo.
- Theme file (TOML, `schema_version = 1`) with colors, shapes, shadows and panel values.
- Editor window with sections, live preview, undo and redo, and a view of the files an apply writes.
- Color scheme target: writes a `.colors` file and activates it with `plasma-apply-colorscheme`.
- Snapshot before every apply, *Undo last apply*, a snapshot list, and automatic rollback when an apply fails.
- Themes page: saved themes and every installed color scheme as thumbnails, with the one in use marked. Select one and press the apply button to switch the desktop to it. The editor takes that theme over, so what you change next builds on it; *Edit* (also a double click or Enter) opens a theme in the editor without applying it.
- The apply button always names the theme it will put on the desktop: the one selected on the Themes page, or on the other pages the theme in the editor.
- Windows and the panel can each have their own corner radius and border width. They follow *Shapes* until overridden.
- Window frame target. Choose *Breeze* to set Breeze's border and shadow to the nearest steps it has, or *Generated* to get a frame drawn for the theme with the exact corner radius, border width, shadow and colors. The editor says beforehand what the desktop can and cannot show, for example how round the bottom corners can be with the chosen border.
- Panel style target: a generated Plasma style gives the panel its own corner radius, border and opacity.
- Panel position: location, height, alignment, length, floating, visibility and opacity of up to six panels can be set in the theme. Values left empty are not touched.
- Each of these targets is off until chosen in the theme, and each is undone by *Undo last apply* together with the files it wrote.
- Before an apply, the app lists the desktop settings that will change, next to the files that will be written and removed.
- Each editor page says, below its controls, what its values become on the desktop and what the desktop cannot show.
- `apply` on the command line does nothing, and makes no snapshot, when the desktop already has the theme.
- A banner reports the result of every apply, switch and restore, says when nothing changed.
- Application style target: a generated Kvantum theme gives buttons, fields, menus and frames the theme's colors, radius and border.
- Popups, tooltips and desktop widgets get their own backgrounds in the generated Plasma style.
- GTK target: a style sheet for GTK 3 and 4 applications, added to `gtk.css` with one import line.
- Rofi target: a generated theme, set with the `@theme` line of `config.rasi` after a parse check.
- Pages for Applications, Popups and tooltips, GTK and Rofi. Their shape fields are disabled and explained while the style is *Leave as it is*.
- The drawn preview follows the Applications values and shows a popup with a tooltip. A new tab, *Application style*, draws real widgets in the generated Kvantum style.
- Theme export and import (`.ptstheme` archive) and export as a Global Theme, in the File menu and on the command line.
- Command line: `validate`, `apply`, `restore`, `export`, `import`, `export-global-theme`.
- Swedish translation. The UI follows the system language.
- Arch Linux PKGBUILD (`packaging/arch`).
- Installed parts in the theme file: Plasma style, application style and window decoration can name an installed one (`installed` plus an id), and the theme can set border size, title bar buttons, icons, pointer theme and size, fonts, splash screen and system sounds. Each is applied with a snapshot and undone exactly; a part that names something not installed is reported and nothing changes. `colors.accent_from_wallpaper` chooses between the theme's accent and the wallpaper's.
- Command line: `status` shows, part by part, what the desktop has now and what a theme would change.
- Filling a theme from an installed Global Theme or color scheme (`edits.py`).

### Fixed

- Follow the palette: a palette change that met a busy write lock (an undo running) is applied at the next look, not left until the file changes again.
- `apply` on the command line draws a theme's own pictures before it decides that the theme is already applied, and `restore` no longer says that settings could not be switched back when it was told to wait and tried nothing.
- Repair step 4: an undo of fonts or another single part no longer puts an older color scheme, GTK colors or `kdeglobals` colors over a scheme chosen since (the snapshot records which parts ran); an undo of GTK gives back `gtk.css` as it was, also when it did not exist; a damaged snapshot manifest can no longer make an undo touch files outside what the app watches; pictures with many blurred elements or markers are refused before they are drawn; saving an imported theme next to another picture of the same name picks a free name; two theme file names that clean up alike get their own artwork folders; very long theme file names can be saved; the thumbnail cache keeps the newest few pictures of an item; the Panel page with two or three screens no longer scrolls sideways at 1100 px.
- Repair step 3: an imported theme keeps its picture names and never overwrites a different picture; frames with nested `<use>` or chained patterns are refused before they are drawn; the undo of one part puts back only the side files of the parts that took part; a named pipe called `kdeglobals` no longer blocks a snapshot; waiting for the desktop after an undo keeps the window alive; the panel page makes its thread pool before the object that answers it; Rofi follows the general font of the theme; the Plasma Style banner no longer calls own artwork unapplied; the Plasma Style page opens at the top; the Colors page scrolls once; the label and slider on the Shapes page no longer overlap at 1100 px; thumbnails are cached per language, so the sample texts of the cards are translated.

- A picture that is a pipe or a huge file no longer hangs or fills memory; every picture goes through one safe reader.
- Installing a color scheme from a file reads it once, and asks before it hides a scheme that came with the system. The clash message names the file.
- Choosing a Global Theme or a color scheme card applies the installed scheme by name; Apply no longer rewrites parts the desktop already has, so *New Theme from the Desktop* then Apply changes nothing.
- *New Theme from the Desktop* can be undone and no longer asks about unsaved changes.
- Clicking choices one after another gives one Undo step for each click.
- Themes: *Switch to Dark Mode at Night* works and is applied; *Save Current Theme…* saves the theme in the editor; the buttons that open System Settings say so.
- Fonts with an old-style (Qt 5) description or a weight below 100 are read and saved back unchanged.
- A window decoration id is written exactly as the installed decoration spells it, and a name that starts with `-` is refused for every part.
- *Status* and the Overview say when an apply would be refused (*Refused*) and give the reason, instead of *Will change*.
- Text on the accent color is chosen the same way in the color scheme and in every preview.
- An accent color in kdeglobals that is not a color is no longer treated as an override to remove.
- Theme files without a wallpaper accent no longer gain an `accent_from_wallpaper = false` line; a missing, oversized or irregular theme file gets its own message.
- The Overview shows its parts when it is opened after another page, and has the theme's name and author. Thumbnails of a card grid are no longer lost by leaving the page early, and a card that cannot be drawn says *No preview*. The group *My themes* says so when it is empty. A card of a part that is left as it is dims only its picture. Applying a theme from the Themes page with unsaved changes says what happens to them. Fonts left as they are show the desktop's font.

- The text color on the accent color is the one with the better contrast, and theme and scheme files are read through bounded reads of regular files only; a line of nothing but `[` no longer makes the config parser slow.
- Importing a theme that is nested too deeply no longer crashes the app or the command line; it is refused with a message.
- A theme name can no longer break out of the comment in the generated Rofi theme.
- The scripts of an exported Global Theme no longer replace or remove a file that this app did not make, and uninstall also removes the folders it leaves empty. The export message says that applying a Global Theme turns the splash screen off.
- Undo of a color scheme no longer fails when it goes back to Breeze Light, which Plasma stores as no value at all.
- Undo of the Plasma style removes a `plasmarc` that did not exist before the apply.
- Undo of the Rofi and Kvantum settings keeps what you changed in those files after the apply.
- The list of settings an apply changes reads as one sentence.
- The style preview's temporary folder is removed at exit; an export keeps the `.ptstheme` extension for a name like `my.theme`.
- A window frame generated by this app now follows the colors of the theme that is put on the desktop afterwards, also when that theme leaves the window frame at *unchanged*, and when you switch color scheme on the Themes tab. The frame keeps its shape (radius, border, shadow) and is redrawn in the new colors; one *Undo last apply* brings back both the scheme and the old frame. Before, the frame kept the colors baked into it: white title bars on a dark desktop.
- A color picked in the desktop's color dialog is now always taken when the dialog is accepted.
- No desktop portal warning when the app runs from a source checkout.
- Switching themes no longer needs a double-click first. The apply button used to apply the theme in the editor even while another theme was selected on the Themes tab, which looked as if the selection was ignored.
- Reloading the Themes tab keeps the scroll position, and a theme deselected with Ctrl+click is no longer acted on.
- A changed window radius, border or shadow used to stop at the preview. With a window frame chosen it now reaches the desktop on the next apply.
- When a failed apply or an undo cannot put every setting or file back, the app and the command line now say so and keep the snapshot, so the undo can be tried again. They used to report that everything was back and drop the snapshot.
- A theme file that is a link (kept in a dotfiles folder, for example) stays a link when it is saved.
- A theme file with `inf` or `nan` as a number is refused with a message instead of an error trace.
- An apply that is interrupted or stops on an unexpected error is rolled back as well.
- Undo switches back to Breeze Light when no color scheme was set before the apply. It used to leave the theme's colors on.
- Files that an apply replaces keep their permissions, and new files get the usual ones instead of being readable by the owner only.
- The list of what an apply does is no longer cut off at the panel command.
- After a switch on the Themes tab, a change in the editor (the panel position, for example) followed by an apply used to put the previous theme back on the desktop, because the editor still held it. The editor now takes over the theme that was switched to. An installed color scheme becomes a new theme named after it. With unsaved changes in the editor the switch asks first, and Cancel leaves everything as it was.
- Undoing a switch brings the editor back to the theme it held before, unless it has unsaved changes or holds another theme by then.
- The theme that was switched to is the one the next start opens.
- A switch asks the desktop which color scheme is in use. It used to trust what the Themes tab showed, and said "already uses" after the scheme had been changed in System Settings.
- The theme in the editor is applied with its unsaved changes when it is chosen on the Themes tab as the color scheme that was written from it. It used to be replaced by a plain copy of that scheme.
- Restoring an older snapshot, from the list or with `restore ID`, undoes the applies made after it as well and uses their snapshots up. *Undo last apply* afterwards used to put a newer state back on the desktop. When one of those applies cannot be undone, the restore stops there and says so; `restore` on the command line no longer reports success in that case.
