# Plasma Theme Studio — Product Requirements Document

| | |
|---|---|
| **Status** | Draft 4, awaiting review |
| **Repository** | https://github.com/Kryckan/plasma-theme-studio |
| **Date** | 2026-11-14 |
| **Target platform** | KDE Plasma 6 on Linux (Wayland and X11) |
| **License** | GPL-3.0-or-later |

## 1. Summary

Plasma Theme Studio is a desktop app for editing an entire KDE Plasma theme in one place. The user sets colors, corner radii, borders, shadows and opacity once. The app writes the files each part of the desktop needs and reloads the desktop live.

It does not replace Kvantum, Klassy or Plasma's own theming. It drives them from a single theme file.

## 2. Problem

Customizing the look of Plasma today means working in several unrelated places:

| Part of the desktop | Where it is configured today | Format |
|---|---|---|
| Colors in apps | System Settings → Colors | `.colors` (INI) |
| Buttons, fields, menus in apps | Application style settings, or Kvantum Manager | C++ plugin config, or Kvantum SVG + INI |
| Title bars, window shadows | Window decoration settings | KWin plugin config |
| Panel, widgets, popups | Hand-edited SVG files | SVG with fixed element IDs |
| GTK apps (Firefox, GNOME apps) | Hand-edited CSS | CSS |

A single design decision, such as "8 px corners everywhere", has to be made five times in five formats. The panel and popups have no GUI at all. There is no shared preview and no single undo.

## 3. Goals

1. **One place.** Every visual property of a theme can be edited inside the app.
2. **One source of truth.** A theme is one human-readable file. Everything else is generated from it.
3. **Visual first.** Changes are shown in a live preview before they touch the desktop.
4. **Safe.** Every apply can be undone. The app never modifies files it does not own without a backup.
5. **Shareable.** A theme can be exported and installed by someone else.
6. **Open.** Free software, English source and docs, translatable UI.

## 4. Non-goals

- Writing a new widget style, window decoration or compositor effect. We reuse existing ones.
- Supporting Plasma 5, GNOME, or other desktops.
- Icon and cursor *design*. The app only selects installed icon and cursor themes.
- A general-purpose vector editor. The SVG editor is for theme graphics; Inkscape remains available for anything else.
- Flatpak, Snap or AppImage packaging (see section 10).
- Theming of login screen (SDDM), boot splash and lock screen in version 1.0. Candidates for later.
- Per-app themes (a different theme for individual apps). Deferred until after 1.0.

## 5. Users

| User | Needs |
|---|---|
| **Tinkerer** (primary) | Wants their own look, is comfortable with Linux, but does not want to learn five file formats. Works visually. |
| **Theme author** | Builds themes to publish. Needs precise control, SVG editing, and a clean export. |
| **Casual user** | Picks a preset, changes accent color and roundness, clicks Apply. |

## 6. Product overview

### 6.1 Main window

- **Left: sections.** Foundation (Colors, Shapes, Shadows, Fonts), Targets (Apps, Windows, Panel & popups, GTK apps, Rofi, Icons & cursors), and Snapshots / Export.
- **Center: workspace** with three tabs.
  - **Preview**: sample window, widgets, menu and panel rendered with the theme.
  - **SVG editor**: edits frame graphics for the panel, popups and widgets.
  - **Show files…** (a dialog, no tab): lists every file the next apply will create or change, and how each target is reloaded.
- **Right: inspector.** Controls for the selected section.
- **Bottom: status and actions.** What will change, *Undo last apply*, *Apply to desktop*.

An interactive mockup is in [`mockup.html`](mockup.html). Open it in a browser.

### 6.2 How a theme flows

```
my-theme.toml ──► generators (one per target) ──► files in the user's home ──► live reload
```

Global values (for example `shape.radius`) apply everywhere by default. Each target can override them (for example a larger radius for the panel only).

### 6.3 Targets

Each target has one backend with full control and, where it is cheap and safe, simpler backends with basic control. A basic backend only sets options the style already exposes in its own config file. The inspector shows which controls the active backend supports and greys out the rest.

| Target | Backend | Output | Reload |
|---|---|---|---|
| Colors | Plasma color scheme | `~/.local/share/color-schemes/<Name>.colors` | `plasma-apply-colorscheme` |
| App widgets | Kvantum (full control), Breeze / Darkly / Klassy style (basic) | `~/.config/Kvantum/<Name>/<Name>.kvconfig` + `.svg`, or the style's own config | `kvantummanager --set`, or style reload |
| Window decoration | Generated Aurorae frame (full control), Breeze (basic), Klassy (optional, planned) | `~/.local/share/aurorae/themes/PlasmaThemeStudio-<name>-<hash>/`, and the decoration keys in `kwinrc` and `breezerc` | KWin `reconfigure` over D-Bus |
| Panel, popups, widgets | Plasma style | `~/.local/share/plasma/desktoptheme/PlasmaThemeStudio-<name>-<hash>/` | `plasma-apply-desktoptheme` |
| Panel position | Plasma shell scripting | No files; properties of the panel | `evaluateScript` over D-Bus |
| GTK 3 / GTK 4 apps | CSS overrides | `~/.config/gtk-3.0/gtk.css`, `~/.config/gtk-4.0/gtk.css` | Theme setting toggled |
| Rofi launcher | Rofi theme | `~/.config/rofi/themes/<Name>.rasi`, plus one `@theme` line in `~/.config/rofi/config.rasi` | None needed. Rofi reads its theme each time it opens |
| Whole theme | Global theme package | `~/.local/share/plasma/look-and-feel/<Name>/` | `plasma-apply-lookandfeel` |

## 7. Functional requirements

Priorities: **P0** = required for the milestone, **P1** = should have, **P2** = nice to have.

### 7.1 Theme file

| ID | Requirement | Priority |
|---|---|---|
| TF-1 | A theme is one TOML file with a `schema_version` field. | P0 |
| TF-2 | The file holds global tokens (colors, radius, border width, shadow, opacity, fonts) and optional per-target overrides. | P0 |
| TF-3 | A theme can define a light and a dark variant that share shape tokens. | P1 |
| TF-4 | Older schema versions are migrated automatically on load. The original file is kept as a backup. | P0 |
| TF-5 | Invalid files produce an error that names the key and the problem. The app does not crash or apply partial themes. | P0 |
| TF-7 | Themes are stored in `~/.local/share/plasma-theme-studio/themes/`. The app shows the path and has an *Open themes folder* action, and each row in *Show files…* links to its folder. | P0 |
| TF-6 | Custom SVG artwork made in the editor is stored next to the theme file and referenced from it. | P0 (M3) |

Draft format, to be finalized in milestone 1:

```toml
schema_version = 1

[meta]
name = "My Theme"
author = ""

[colors]
accent = "#3daee9"
window_background = "#eff0f1"
view_background = "#fcfcfc"
text = "#232629"

[shape]
radius = 8          # px
border_width = 1    # px

[shadow]
size = 24           # px
strength = 0.35     # 0–1

[panel]
opacity = 0.85
radius = 12         # overrides shape.radius for the panel only
```

### 7.2 Editing and preview

| ID | Requirement | Priority |
|---|---|---|
| ED-1 | Every token in the theme file has a control in the inspector. No hand-editing is needed. | P0 |
| ED-2 | The preview updates within 100 ms of a control change. | P0 |
| ED-3 | App widgets in the preview are drawn by the real Qt style (Kvantum), not an imitation. | P0 (M2) |
| ED-4 | Undo and redo for all edits inside the app. | P0 |
| ED-5 | Built-in presets, including one that matches stock Breeze. | P1 |
| ED-6 | Import an existing `.colors` file as a starting point. | P1 |
| ED-7 | Contrast warning when text and background colors fall below WCAG AA (4.5:1). | P1 |

### 7.3 Apply, undo and safety

| ID | Requirement | Priority |
|---|---|---|
| AP-1 | *Apply to desktop* writes all target files and reloads each target without logging out. | P0 |
| AP-2 | Before each apply, the app saves a snapshot of every file it is about to change, plus the active theme settings. | P0 |
| AP-3 | *Undo last apply* restores the latest snapshot. Any snapshot can be restored from the Snapshots section. | P0 |
| AP-4 | The app only writes inside its own theme folders, except for a documented list of shared files (`gtk.css`, Klassy config). Shared files are always snapshotted first. | P0 |
| AP-5 | *Show files…* shows the exact list before the user applies. | P0 |
| AP-6 | If one target fails, the others still apply, and the failure is reported with the reason. | P0 |
| AP-7 | Targets whose backend is not installed (for example Klassy) are disabled with an explanation, not hidden. | P0 |
| AP-8 | A command-line mode applies a theme file without the GUI: `plasma-theme-studio apply my-theme.toml`. | P1 |
| AP-9 | A recovery command restores the latest snapshot without the GUI, so it works from a text console if the desktop does not start: `plasma-theme-studio restore`. | P0 |
| AP-10 | Generated output is validated before it is written (parsable INI, well-formed SVG with required element IDs). Invalid output is never applied. | P0 |
| AP-11 | The app only writes inside the user's home directory. It never needs root and never changes system files. | P0 |

### 7.4 SVG editor

| ID | Requirement | Priority |
|---|---|---|
| SV-1 | Frame mode: edit a 9-slice frame (corners, edges, center, shadow) using radius, border, fill, opacity and shadow controls. The app generates the correctly named SVG elements. | P0 (M3) |
| SV-2 | Frame mode covers the Plasma panel, dialogs/popups, tooltips and widget backgrounds. | P0 (M3) |
| SV-3 | Draw mode: free editing with select, node, rectangle, pen and gradient tools, using embedded SVG-Edit. | P1 (M3) |
| SV-4 | *Open in Inkscape* opens the current file externally and reloads it when saved. | P1 |
| SV-5 | Validation: warns when an element ID that Plasma or Kvantum requires is missing. | P0 (M3) |
| SV-6 | The same frame editor can edit Kvantum widget frames. | P2 |

### 7.5 Export and sharing

| ID | Requirement | Priority |
|---|---|---|
| EX-1 | Export a theme as one archive containing the theme file and its SVG assets. | P0 (M4) |
| EX-2 | Import such an archive. | P0 (M4) |
| EX-3 | Export as a Plasma Global Theme package that works without Plasma Theme Studio installed. | P1 |
| EX-4 | Upload to the KDE Store from inside the app. | P2 |

### 7.6 Wallpaper colors (pywal and matugen)

pywal generates a 16-color palette from a wallpaper and writes it to `~/.cache/wal/colors.json`. The app reads that file, so it works with pywal and its maintained fork pywal16. Neither is in the official Arch repositories (AUR only), so the tool is an optional dependency and the app explains how to install it when it is missing. matugen (Material You colors, in the official Arch repositories) is supported as a second palette source with its own mapping to theme roles. Everything after reading the palette is shared between the two. In the requirements below, "palette tool" means either one.

| ID | Requirement | Priority |
|---|---|---|
| PW-1 | Import: fill the theme's colors from the current pywal or matugen palette with one click. The user can adjust the result afterwards. | P0 (M2) |
| PW-2 | The mapping from pywal's 16 colors to theme roles (accent, backgrounds, text) is shown and editable. Text contrast is corrected automatically to meet WCAG AA. | P0 (M2) |
| PW-3 | Generate from inside the app: pick a wallpaper (or use the current one) and the app runs the installed palette tool. If both are installed, the user chooses. | P1 (M2) |
| PW-4 | Follow mode: when the pywal palette changes, the active theme's colors are regenerated and re-applied automatically. Shapes, shadows and SVG artwork stay as they are. Off by default. | P1 (M4) |
| PW-5 | Export: write the theme's colors in pywal's format, so terminals and other tools that read pywal's files follow a theme made by hand. | P2 |
| PW-6 | Follow mode never creates snapshots for each automatic change. It keeps one snapshot from when it was switched on. | P1 (M4) |

### 7.7 Rofi

Best effort: the Rofi target covers what Rofi's theme format can express (colors, radius, borders, opacity, font, layout). Window shadows come from the compositor and are outside the theme.

| ID | Requirement | Priority |
|---|---|---|
| RF-1 | Generate a Rofi theme (`.rasi`) from the theme's colors, radius, border width, opacity and font. | P0 (M4) |
| RF-2 | The user's own `config.rasi` is kept. The app only adds or changes its `@theme` line, after a snapshot. | P0 (M4) |
| RF-3 | The preview shows a Rofi window drawn from the same values. | P1 (M4) |
| RF-4 | Rofi-specific options (window width, number of rows, icon size, layout preset) are per-target overrides. | P1 (M4) |
| RF-5 | The target is disabled with an explanation when Rofi is not installed. | P0 (M4) |

### 7.8 Desktop layout and Plasma's own appearance settings

The goal is one consistent place for everything that affects how the desktop looks, including settings that today live in System Settings or in the panel's edit mode. System Settings modules cannot be embedded in this app (they are C++/QML plugins without Python bindings), so the app has its own controls for these settings, built like the rest of the editor, and changes them through Plasma's documented interfaces (the Plasma shell scripting interface, `plasma-apply-*`, `kwriteconfig6`). Every one of them is previewed, snapshotted and undoable like any other value.

| ID | Requirement | Priority |
|---|---|---|
| DL-1 | Each shape value (corner radius, border width) can be set separately for windows and for the panel; unset values follow the global one. | P0 (M1; applied to windows, the panel and app widgets in 0.1) |
| DL-2 | Panel layout: screen edge, height, length and alignment, floating, visibility mode and opacity, for each panel, changed from the app and shown in the preview. | P0 (M3; up to six panels in 0.1) |
| DL-3 | The Themes tab lists installed color schemes and saved themes with thumbnails and switches between them. | P0 (M1) |
| DL-4 | Switch between installed Global Themes, Plasma styles, window decorations, application styles, icon themes and cursor themes from the Themes tab. Everything a switch changes is covered by the snapshot. | P1 (M4) |
| DL-5 | Fonts, title bar button layout and window border size can be set in the app. | P1 (M4) |
| DL-6 | A setting the app does not cover yet has a link that opens the matching System Settings page. | P2 |
| DL-7 | Settings the app changes outside its own generated files are read from the system when the editor opens, so the app never shows a stale value. | P0 (with DL-2) |

### 7.9 Language support

| ID | Requirement | Priority |
|---|---|---|
| L-1 | All source strings, code, comments, commit messages and documentation are in English. | P0 |
| L-2 | Every user-visible string is translatable (Qt `tr()`), from the first milestone. | P0 |
| L-3 | The UI language follows the system language and falls back to English. | P0 |
| L-4 | Swedish ships as the first translation. | P1 |
| L-5 | Translations can be contributed through a web platform (Hosted Weblate) once the project is public. | P2 |

## 8. Non-functional requirements

| Area | Requirement |
|---|---|
| **Performance** | Starts in under 2 s on a typical desktop. A full apply completes in under 3 s. |
| **Reliability** | A crash during apply must not leave the desktop unusable. Files are written to a temporary location and moved into place. |
| **Compatibility** | Plasma 6.3 or newer, with Plasma 6.6 or newer as the fully tested tier (see section 11). Works on Wayland and X11. Plasma 5 is not supported. |
| **Accessibility** | Full keyboard navigation. All controls have accessible names. |
| **Privacy** | No telemetry. No network access except explicit user actions (KDE Store upload). |
| **Quality** | Each generator has tests that compare its output against known-good reference files. CI runs tests and linting on every pull request. |

## 9. Technical approach

| Decision | Choice | Reason |
|---|---|---|
| UI framework | Qt 6 Widgets | Same toolkit as Plasma, so the preview can load real style plugins. |
| Language | Python 3 with PySide6 | Fast iteration. The generators are mostly templating. |
| Templates | Jinja2 | Text and SVG output from one mechanism. |
| SVG frame editor | QtSvg + QGraphicsView | Native, no extra dependency. |
| SVG draw mode | SVG-Edit (MIT) in QtWebEngine | Mature open-source editor that can be embedded. |
| Reload | KDE command-line tools and D-Bus | Officially supported paths, no private APIs. |
| Translations | Qt Linguist (`.ts` / `.qm`) | Standard for Qt apps, supported by Weblate. |

PySide6 must be the distribution's package, built against the same Qt as Plasma. A pip-installed PySide6 bundles its own Qt and cannot load Kvantum or other system style plugins.

Proposed source layout:

```
plasma-theme-studio/
├── src/plasma_theme_studio/
│   ├── model/         # theme file: schema, load, save, migrate
│   ├── generators/    # one module per target + templates
│   ├── apply/         # write files, snapshots, reload
│   ├── ui/            # main window, inspector, preview, SVG editor
│   └── i18n/          # .ts translation files
├── tests/
├── packaging/arch/    # PKGBUILD
└── docs/
```

### 9.1 KDE conventions adopted from the start

The project starts on GitHub. It does not apply to become a KDE project now, because that adds process without making development easier. It does follow the KDE conventions that are free to adopt early and expensive to retrofit, so a later move stays possible:

| Convention | What it means here |
|---|---|
| Reverse-DNS application ID | Used for the desktop file, icon name, AppStream metadata and D-Bus name. The ID is `io.github.kryckan.PlasmaThemeStudio` until the project has another home. It is defined in one place in the code. |
| REUSE / SPDX | Every file carries a license identifier. Required by KDE and good practice anyway. |
| AppStream metadata and desktop file | Lets software centers and KDE's app listings show the app. |
| KDE Human Interface Guidelines | Layout, wording and standard shortcuts follow the HIG, so the app feels native in Plasma. |
| Breeze-compatible app icon | SVG in `data/icons/`, with a simplified variant for 16 px and 22 px. |
| Translations | Qt `tr()` with `.ts` files. To be verified: that KDE's translation infrastructure accepts Qt-only apps in this form without code changes. |

## 10. Packaging and updates

| Topic | Decision |
|---|---|
| Format | Arch `PKGBUILD`, published on the AUR as `plasma-theme-studio` (releases) and `plasma-theme-studio-git` (latest code). |
| Install location | `/usr/share/plasma-theme-studio/` with a launcher in `/usr/bin/`. Not in Python's `site-packages`, so Python upgrades do not break the app. |
| Required dependencies | `python`, `pyside6`, `python-jinja`, `qt6-svg`, `kvantum` |
| Optional dependencies | `rofi` for the Rofi target, `matugen` or pywal16 (AUR) for wallpaper colors, `klassy` (AUR) for window decorations, `qt6-webengine` for SVG draw mode, `inkscape` for external editing |
| Build dependencies | `qt6-tools` (compiles translations) |
| Updates | Through the system package manager. No built-in updater. |
| Backend changes | At startup the app checks the installed Kvantum and Klassy versions and warns when a version is untested. |
| Run from source | Supported on every distro from milestone 1: clone the repository and run the launcher. Requires the distro's own PySide6 package. |
| Other distros | Packages for Fedora, openSUSE, Debian and Ubuntu are built with the Open Build Service in milestone 4. One service builds for all of them. |

Flatpak and AppImage are excluded because the sandbox and bundled Qt hide the system's style plugins from the preview and complicate writing to the user's config.

## 11. Platform support

Researched 2026-11-14 from Repology and the Klassy project page.

| Distribution | Plasma | PySide6 | Kvantum (Qt 6) | Support tier |
|---|---|---|---|---|
| Arch, CachyOS, EndeavourOS | 6.8 | 6.12 | 1.1.9 | Full (development platform) |
| Fedora 44 | 6.8 | 6.11 | 1.1.6 | Full |
| KDE neon, openSUSE Tumbleweed | 6.8 | 6.12 (Tumbleweed) | 1.1.8 | Full |
| Manjaro stable, Void | 6.7 | 6.11 | 1.1.8–1.1.9 | Full |
| Ubuntu / Kubuntu 26.10 | 6.7 | 6.11 | 1.1.8 | Full |
| Fedora 43 | 6.7 | 6.10 | 1.1.6 | Full |
| Ubuntu / Kubuntu 26.04 LTS | 6.6 | 6.10 | 1.1.5 | Full |
| openSUSE Leap 16.1 | 6.6 | to be verified | to be verified | Full |
| NixOS 26.05 | 6.6 | 6.11 | 1.1.7 | Full, run from source or community package |
| Debian 13 (stable) | 6.3 | 6.8 | 1.1.4 | Core: everything except Klassy |
| openSUSE Leap 16.0 | 6.4 | to be verified | to be verified | Core: everything except Klassy |
| Ubuntu 24.04 LTS, Debian 12, Leap 15.6 | 5.27 | not packaged | Qt 5 only | Not supported |

**Support tiers**

- **Full (Plasma 6.6 or newer).** All targets. Klassy 6.7 requires Plasma 6.6.1 or newer.
- **Core (Plasma 6.3 to 6.5).** Colors, Kvantum, Plasma style, GTK and Breeze decoration settings. The Klassy target is disabled with an explanation. In practice this tier exists for Debian 13.
- **Not supported (Plasma 5).** Plasma 5 uses Qt 5, and those distributions do not package PySide6. Supporting it would mean a second code path for everything.

**Why 6.3 is the floor.** It is the oldest Plasma 6 release in a distribution that is still supported (Debian 13). The formats the app generates (color schemes, Kvantum themes, Plasma style SVGs, GTK CSS) and the `plasma-apply-*` tools are expected to be the same across Plasma 6.x, so the cost of the core tier is mainly testing. This must be confirmed in a Debian 13 virtual machine during milestones 1 and 3. If a target turns out to need version-specific code, that target is dropped from the core tier instead of adding a compatibility layer.

**Klassy availability.** Klassy is not limited to Arch. The project publishes prebuilt packages through the Open Build Service for openSUSE, Debian/Ubuntu, Fedora, Mageia and Arch/Manjaro, a Fedora Copr, and it is in the NixOS and Gentoo GURU repositories.

## 12. Milestones and deliverables

Each milestone ends with a tagged release that is usable on its own.

### Milestone 1 — Theme file, colors, apply (v0.1)

**Delivers**
- Repository: license, English README, contribution guide, CI, tests.
- Theme file format v1 with validation and migration scaffolding.
- Main window with sections, inspector and a simplified preview.
- Color scheme generator and live apply.
- Snapshots and *Undo last apply*.
- Translation infrastructure with Swedish.
- First PKGBUILD (`-git` variant).
- Runs from a source checkout on any distro with PySide6 installed.
- The `restore` recovery command.
- Brought forward from milestones 2 and 3 (see section 15): window frame through Breeze's settings or a generated Aurorae frame, a generated panel background, and the layout of up to six panels.

**Done when**
- A user can create a theme, change colors, apply it, see all Qt/KDE apps recolor without logging out, and undo it.
- The app runs in Swedish on a Swedish system and in English otherwise.
- `makepkg -si` installs a working app on a clean Arch/CachyOS system.

### Milestone 2 — Shapes for apps and windows (v0.2)

**Delivers**
- Kvantum generator (config + SVG from templates): radius, border, shadows, opacity.
- Klassy as an optional window decoration backend: radius, border, shadow, button style.
- Basic backends: Breeze / Darkly / Klassy application style settings. (The Breeze decoration settings and the application style page shipped in 0.1.)
- Preview rendered with the real Kvantum style.
- Light and dark variants. (Shipped in 0.1: *Add a Dark Variant* on the Colors page and `--variant light|dark`.)
- pywal and matugen import with editable color mapping, and generating a palette from a wallpaper. (Import and colors from a picture shipped in 0.1.)

**Done when**
- Changing the corner radius once changes buttons, fields, menus and window corners after one apply.
- The preview matches a real app window side by side.

### Milestone 3 — SVG editor, panel and popups (v0.3)

**Delivers**
- Plasma style generator: dialogs, tooltips, widget backgrounds. (The panel background shipped in 0.1.)
- SVG frame editor with validation.
- SVG draw mode and *Open in Inkscape*. (Open in Inkscape and the frame editor shipped in 0.1; the embedded draw mode did not.)

**Done when**
- A user can restyle the panel and popups (radius, border, opacity, shadow) and move and resize the panel (DL-2) without leaving the app.
- Generated Plasma styles load without warnings in `plasmashell`.

### Milestone 4 — GTK, sharing, 1.0

**Delivers**
- GTK 3 and GTK 4 CSS generator.
- Rofi theme generator.
- Icon and cursor theme selection, and switching of Global Themes, Plasma styles, window decorations and application styles (DL-4).
- Fonts, title bar buttons and window border size (DL-5).
- Theme export and import, and Global Theme export.
- Command-line apply.
- pywal / matugen follow mode.
- Release PKGBUILD on the AUR, user documentation, screenshots.
- Open Build Service packages for Fedora, openSUSE, Debian and Ubuntu.
- Test pass on one distribution per support tier (Arch, Kubuntu 26.04 LTS, Debian 13).

**Done when**
- GTK apps follow the theme's colors and radius.
- A theme exported on one machine imports and applies on another.
- All P0 requirements pass.

## 13. Success criteria for 1.0

- A theme can be created and applied to every target in section 6.3 without opening another settings tool or editing a file by hand.
- Any apply can be reverted from inside the app.
- No user file is lost or overwritten without a snapshot.
- A new user reaches their first successful apply within 5 minutes of installing.

## 14. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Kvantum or Klassy change their config format | A generator produces broken output | Version check at startup, reference-file tests, generators isolated per target |
| Klassy goes unmaintained or lags behind a new Plasma release | Window decoration target breaks | Klassy is optional. The generated Aurorae frame and the Breeze backend need nothing but KWin |
| A generated theme makes the desktop hard to use (unreadable colors, broken panel graphics) | User cannot easily get back | Output validation (AP-10), snapshots (AP-2), and the console `restore` command (AP-9). The app never touches system files (AP-11) |
| Core tier (Plasma 6.3) needs version-specific code | Extra maintenance | Drop the affected target from the core tier instead of adding compatibility code |
| Plasma style SVGs are intricate (many files, required IDs, hint elements) | Milestone 3 slips | Start from Breeze's files as templates. Ship panel and dialog first, the rest incrementally |
| libadwaita ignores most theming | GTK 4 apps only partly match | Scope GTK 4 to colors and document the limitation |
| Live reload behaves differently across Plasma versions | Apply appears to do nothing | Use official `plasma-apply-*` tools. Offer "restart Plasma shell" as a fallback |
| Overwriting a user's existing `gtk.css` or Klassy config | Lost customization | Snapshot before every write (AP-2, AP-4), show the file list first (AP-5) |
| pywal palettes give poor contrast or clashing accents | Unreadable UI after import or in follow mode | Automatic contrast correction (PW-2). Follow mode is off by default |
| Scope growth ("everything") | 1.0 never ships | Milestones are independently releasable. Non-goals are fixed for 1.0 |

## 15. Decisions

| Date | Decision |
|---|---|
| 2026-11-14 | Window decoration: Klassy is the full backend and stays optional. Breeze decoration settings are the basic backend. An Aurorae (SVG) generator is deferred until after 1.0. |
| 2026-11-14 | Application style: Kvantum is the full backend. Breeze, Darkly and Klassy styles get basic support through their existing settings. No style is forked or patched. |
| 2026-11-14 | Compatibility: as broad as possible without large effort or risk to the user's desktop. Minimum Plasma 6.3 (core tier), full support from Plasma 6.6. Plasma 5 is out of scope. |
| 2026-11-14 | Distribution: AUR first, run-from-source everywhere from milestone 1, other distro packages in milestone 4. |

| 2026-11-14 | pywal and matugen are both supported palette sources in 1.0: import in milestone 2, follow mode in milestone 4. |
| 2026-11-14 | Rofi is a target in 1.0 (milestone 4), best effort within what Rofi's theme format supports. |
| 2026-11-14 | Per-app themes (Kvantum app assignments) are deferred until after 1.0. |
| 2026-11-14 | Themes are stored in the default data location, with links in the app to open the folder. |
| 2026-11-14 | Hosting on GitHub. KDE conventions are followed from the start (section 9.1). Applying to KDE is revisited after 1.0. |
| 2026-11-14 | Repository: public, at `github.com/Kryckan/plasma-theme-studio`. Application ID `io.github.kryckan.PlasmaThemeStudio`. |
| 2026-11-14 | App icon: the "corner handle" design on a blue background. |
| 2026-11-14 | Replaces the first decision above. The Aurorae (SVG) generator is brought forward to 0.1 and is the full window decoration backend: it needs no extra package and gives an exact radius, border and shadow. Breeze stays the basic backend. Klassy becomes an optional backend in milestone 2. |
| 2026-11-14 | The panel background of the Plasma style and the layout of the main panel (DL-2) are brought forward to 0.1. Each new target is off until chosen in the theme, so a theme that only sets colors changes nothing else. |
| 2026-11-14 | Shapes of app widgets stay in milestone 2 (Kvantum). Union is looked at again when Plasma ships it. |
| 2026-11-14 | The app covers Plasma's own appearance settings (panel layout, fonts, theme switching) with its own controls, so the user does not need System Settings for anything visual. Every editable value has a visual preview. |

## 16. Open questions

1. **openSUSE Leap.** PySide6 and Kvantum package versions on Leap 16.0 and 16.1 are not confirmed.
2. **KDE translation compatibility.** See section 9.1.
