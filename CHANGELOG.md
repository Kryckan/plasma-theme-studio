# Changelog

All notable changes to Plasma Theme Studio are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased (0.1.0)

### Added

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
- Panel position: location, height, alignment, length, floating, visibility and opacity of the main panel can be set in the theme. Values left empty are not touched.
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
