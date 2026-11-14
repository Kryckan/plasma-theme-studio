# Changelog

All notable changes to Plasma Theme Studio are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased (0.1.0)

### Added

- Theme file (TOML, `schema_version = 1`) with colors, shapes, shadows and panel values.
- Editor window with sections, live preview, undo and redo, and a view of the files an apply writes.
- Color scheme target: writes a `.colors` file and activates it with `plasma-apply-colorscheme`.
- Snapshot before every apply, *Undo last apply*, a snapshot list, and automatic rollback when an apply fails.
- Themes tab: saved themes and every installed color scheme as thumbnails, with the one in use marked. Select one and press the apply button (or double-click it, or press Enter) to switch the desktop to it; *Edit* opens it in the editor.
- The apply button always names the theme it will put on the desktop: the one selected on the Themes tab, or on the other tabs the theme in the editor.
- Windows and the panel can each have their own corner radius and border width. They follow *Shapes* until overridden. (Stored and previewed; applied to the desktop from 0.2 and 0.3.)
- A banner reports the result of every apply, switch and restore, says when nothing changed, and says when values were left out because this version cannot apply them.
- Command line: `validate`, `apply`, `restore`.
- Swedish translation. The UI follows the system language.
- Arch Linux PKGBUILD (`packaging/arch`).

### Fixed

- A color picked in the desktop's color dialog is now always taken when the dialog is accepted.
- No desktop portal warning when the app runs from a source checkout.
- Switching themes no longer needs a double-click first. The apply button used to apply the theme in the editor even while another theme was selected on the Themes tab, which looked as if the selection was ignored.
- Reloading the Themes tab keeps the scroll position, and a theme deselected with Ctrl+click is no longer acted on.
