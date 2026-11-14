# Changelog

All notable changes to Plasma Theme Studio are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased (0.1.0)

### Added

- Theme file (TOML, `schema_version = 1`) with colors, shapes, shadows and panel values.
- Editor window with sections, live preview, undo and redo, and a view of the files an apply writes.
- Color scheme target: writes a `.colors` file and activates it with `plasma-apply-colorscheme`.
- Snapshot before every apply, *Undo last apply*, a snapshot list, and automatic rollback when an apply fails.
- Themes tab: saved themes and every installed color scheme as thumbnails, with the one in use marked. Select one and press the apply button (or double-click it, or press Enter) to switch the desktop to it. The editor takes that theme over, so what you change next builds on it; *Edit* opens a theme in the editor without applying it.
- The apply button always names the theme it will put on the desktop: the one selected on the Themes tab, or on the other tabs the theme in the editor.
- Windows and the panel can each have their own corner radius and border width. They follow *Shapes* until overridden.
- Window frame target. Choose *Breeze* to set Breeze's border and shadow to the nearest steps it has, or *Generated* to get a frame drawn for the theme with the exact corner radius, border width, shadow and colors. The editor says beforehand what the desktop can and cannot show, for example how round the bottom corners can be with the chosen border.
- Panel style target: a generated Plasma style gives the panel its own corner radius, border and opacity.
- Panel position: location, height, alignment, length, floating, visibility and opacity of the main panel can be set in the theme. Values left empty are not touched.
- Each of these targets is off until chosen in the theme, and each is undone by *Undo last apply* together with the files it wrote.
- Before an apply, the app lists the desktop settings that will change, next to the files that will be written and removed.
- Each editor page says, below its controls, what its values become on the desktop and what the desktop cannot show.
- `apply` on the command line does nothing, and makes no snapshot, when the desktop already has the theme.
- A banner reports the result of every apply, switch and restore, says when nothing changed, and says which values were left out because this version cannot apply them (shapes of app widgets).
- Command line: `validate`, `apply`, `restore`.
- Swedish translation. The UI follows the system language.
- Arch Linux PKGBUILD (`packaging/arch`).

### Fixed

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
