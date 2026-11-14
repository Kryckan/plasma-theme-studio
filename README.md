<p align="center">
  <img src="data/icons/hicolor/scalable/apps/io.github.kryckan.PlasmaThemeStudio.svg" width="128" height="128" alt="Plasma Theme Studio icon">
</p>

# Plasma Theme Studio

One app for editing an entire KDE Plasma theme in one place.

Set colors, corner radii, borders, shadows and opacity once. Plasma Theme Studio writes the files each part of the desktop needs and reloads the desktop live.

> **Status: planning.** There is no usable release yet. The product plan is in [docs/PRD.md](docs/PRD.md). Feedback on the plan is welcome in the issue tracker.

## Why

Customizing Plasma today means working in several unrelated places and file formats: color schemes, the application style, the window decoration, hand-edited SVG files for the panel, and CSS for GTK apps. A single decision such as "8 px corners everywhere" has to be made five times.

Plasma Theme Studio does not replace those systems. It drives them from a single theme file.

```
my-theme.toml ──► generators (one per target) ──► files in your home directory ──► live reload
```

## Planned features

- One human-readable theme file as the single source of truth
- Live preview drawn with the real Qt style
- Built-in SVG editor for panel, popup and widget frames
- Snapshots before every apply, undo from the app, and a console recovery command
- Wallpaper-based colors through pywal and matugen
- Theme export and import
- Translatable UI that follows the system language

## Targets

| Part of the desktop | Backend |
|---|---|
| Colors | Plasma color scheme |
| App widgets | Kvantum (full control); Breeze, Darkly, Klassy style (basic) |
| Window decoration | Klassy (full control); Breeze (basic) |
| Panel, popups, widgets | Plasma style (SVG) |
| GTK 3 / GTK 4 apps | CSS overrides |
| Rofi | Rofi theme |

## Platform support

- **Plasma 6.6 or newer:** all targets.
- **Plasma 6.3 to 6.5:** everything except the Klassy window decoration.
- **Plasma 5:** not supported.

The first packages target Arch Linux (AUR). Packages for Fedora, openSUSE, Debian and Ubuntu are planned for 1.0. Details are in the [PRD](docs/PRD.md#11-platform-support).

## Roadmap

| Milestone | Scope |
|---|---|
| v0.1 | Theme file, colors, apply, undo, translations, first Arch package |
| v0.2 | Shapes and shadows for apps and windows, real-style preview, pywal and matugen import |
| v0.3 | SVG editor, panel and popups |
| v1.0 | GTK, Rofi, export and import, command line, packages for more distributions |

## Design

- [Product requirements](docs/PRD.md)
- [Interactive UI mockup](docs/mockup.html) (download and open in a browser)

## Technology

Python with PySide6 (Qt 6 Widgets), Jinja2 templates, and Qt Linguist for translations.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
