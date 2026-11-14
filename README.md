<p align="center">
  <img src="data/icons/hicolor/scalable/apps/io.github.kryckan.PlasmaThemeStudio.svg" width="128" height="128" alt="Plasma Theme Studio icon">
</p>

# Plasma Theme Studio

One app for editing an entire KDE Plasma theme in one place.

Set colors, corner radii, borders, shadows, opacity and the panel's position in one theme. Plasma Theme Studio writes the files each part of the desktop needs and reloads the desktop live.

> **Status: early development (v0.1).** Colors, the window frame (corner radius, border, shadow), the panel's look (corner radius, border, opacity) and the panel's position can be edited, previewed, applied and undone. The Themes tab shows your saved themes and every installed color scheme, switches the desktop between them and opens any of them for editing. Shapes of app widgets (buttons, fields, menus) are previewed but not applied to the desktop yet. What works and what does not is in [docs/STATUS.md](docs/STATUS.md); the plan is in [docs/PRD.md](docs/PRD.md).

![The editor with a dark theme open](docs/screenshots/main-window.png)

## Try it

You need KDE Plasma 6, Python 3.11 or newer, and your distribution's PySide6 and Jinja2 packages.

| Distribution | Install the dependencies |
|---|---|
| Arch, CachyOS, Manjaro | `sudo pacman -S --needed pyside6 python-jinja` |
| Fedora | `sudo dnf install python3-pyside6 python3-jinja2` |
| Debian, Ubuntu | `sudo apt install python3-pyside6.qtwidgets python3-jinja2` |
| openSUSE | `sudo zypper install python3-pyside6 python3-Jinja2` |

Run it from a checkout, without installing anything:

```sh
git clone https://github.com/Kryckan/plasma-theme-studio.git
cd plasma-theme-studio
./plasma-theme-studio
```

On Arch-based systems you can build a package instead:

```sh
cd packaging/arch
makepkg -si
```

Use the distribution's PySide6, not the one from pip. Only the distribution's build loads the KDE widget styles.

## Safety

- The app writes only inside your home folder and never asks for root.
- The **Files written** tab shows every file and its content before you apply.
- It also lists the desktop settings an apply changes. The window frame, the panel style and the panel position are only touched when the theme asks for them.
- A snapshot is taken before every apply. **Undo last apply** puts the files and settings back, one apply at a time. Restoring an older snapshot undoes every apply made after it as well.
- If the desktop becomes hard to use, switch to a text console (Ctrl+Alt+F3), log in and run:

  ```sh
  plasma-theme-studio restore
  ```

Themes are stored in `~/.local/share/plasma-theme-studio/themes/` and snapshots in `~/.local/share/plasma-theme-studio/snapshots/`.

## Command line

```
plasma-theme-studio [FILE]           open the editor
plasma-theme-studio validate FILE    check a theme file
plasma-theme-studio apply FILE       apply a theme file to the desktop
plasma-theme-studio restore          undo the latest apply (repeat to go further back)
plasma-theme-studio restore ID       go back to a chosen snapshot, undoing the applies after it
plasma-theme-studio restore --list   list the snapshots
```

## Why

Customizing Plasma today means working in several unrelated places and file formats: color schemes, the application style, the window decoration, hand-edited SVG files for the panel, and CSS for GTK apps. A single decision such as "8 px corners everywhere" has to be made five times.

Plasma Theme Studio does not replace those systems. It drives them from a single theme file.

```
my-theme.toml ──► generators (one per target) ──► files in your home directory ──► live reload
```

## Planned features

- Shapes applied to app widgets, and styles for popups and tooltips
- Live preview drawn with the real Qt style
- Built-in SVG editor for panel, popup and widget frames
- Wallpaper-based colors through pywal and matugen
- Theme export and import

## Targets

| Part of the desktop | Backend | State |
|---|---|---|
| Colors | Plasma color scheme | Works |
| Window decoration | Generated frame (exact radius, border and shadow); Breeze (its fixed steps) | Works |
| Panel background | Plasma style (SVG) | Works |
| Panel position | Plasma's scripting interface | Works for the main panel |
| App widgets | Kvantum (full control); Breeze, Darkly, Klassy style (basic) | Planned |
| Popups, tooltips, widgets | Plasma style (SVG) | Planned |
| GTK 3 / GTK 4 apps | CSS overrides | Planned |
| Rofi | Rofi theme | Planned |

The window frame, panel style and panel position have so far been tried with Plasma 6.8 in an isolated test session only.

## Platform support

- **Plasma 6.6 or newer:** all targets.
- **Plasma 6.3 to 6.5:** everything except the optional Klassy window decoration.
- **Plasma 5:** not supported.

The first packages target Arch Linux (AUR). Packages for Fedora, openSUSE, Debian and Ubuntu are planned for 1.0. Details are in the [PRD](docs/PRD.md#11-platform-support).

## Roadmap

| Milestone | Scope |
|---|---|
| v0.1 | Theme file, colors, window frame, panel look and position, apply, undo, translations, first Arch package |
| v0.2 | Shapes for app widgets, real-style preview, pywal and matugen import |
| v0.3 | SVG editor, popups and widgets |
| v1.0 | GTK, Rofi, export and import, command line, packages for more distributions |

## Design

- [Product requirements](docs/PRD.md)
- [Project status](docs/STATUS.md)
- [Changelog](CHANGELOG.md)
- [Interactive UI mockup](docs/mockup.html) (download and open in a browser)

## Technology

Python with PySide6 (Qt 6 Widgets), Jinja2 templates, and Qt Linguist for translations. The UI follows the system language; English and Swedish are included.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to run the tests and add a translation.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
