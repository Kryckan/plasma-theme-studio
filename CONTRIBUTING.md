# Contributing

Bug reports, translations and code are all welcome. Everything in the repository is written in English: code, comments, commit messages, documentation and the source text of the UI.

## Set up

The app itself runs on the system Python with the distribution's PySide6 (see the [README](README.md#try-it)). For the tests and the linter, a virtual environment that can see the system packages is the simplest setup:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install pytest ruff
```

If your system has no PySide6 package, `pip install PySide6` inside the environment is enough for the tests.

## Checks

Run these before opening a pull request. CI runs the same three commands.

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

The tests use a temporary home folder and a stand-in for the KDE tools. They never change your desktop.

## Layout

| Path | Contents |
|---|---|
| `src/plasma_theme_studio/model/` | The theme file: fields, validation, loading, saving, migration |
| `src/plasma_theme_studio/generators/` | One generator per target; each turns a theme into files and knows how to reload them |
| `src/plasma_theme_studio/apply/` | Planning, snapshots, apply and restore |
| `src/plasma_theme_studio/ui/` | The Qt window |
| `src/plasma_theme_studio/i18n/` | Translations (`.ts`) |
| `tests/` | Tests |
| `packaging/` | Distribution packages |

`model`, `generators` and `apply` must not import Qt. The `restore` command has to work on a machine where the desktop does not start.

## Rules for code that touches the desktop

These come from the [PRD](docs/PRD.md) and are not negotiable:

- Write only inside the user's home folder. Never require root.
- Take a snapshot before changing anything, and make every change restorable from it.
- Check generated content before writing it. Write files atomically.
- Reload the desktop only through the tools KDE provides.
- If an apply fails halfway, put everything back.

## Translations

User-visible text is wrapped in `translate("context", "English text")`. Use full sentences and named placeholders such as `{name}`; do not build sentences from pieces.

To update the translation files after changing text:

```sh
scripts/update-translations.sh
```

To start a new language, pass its code and then edit the new file with Qt Linguist or a text editor:

```sh
scripts/update-translations.sh de
```

Where KDE already has a term for something, use KDE's wording for that language.

## Adding a field to the theme file

1. Add it to `FIELDS` in `model/theme.py` and give it a label in `ui/labels.py`.
2. If the change is not backward compatible, raise `SCHEMA_VERSION` and add a function to `MIGRATIONS`.
3. Add a test.

## Commits and licensing

- Write commit messages in the imperative: "Add snapshot pruning".
- Every source file starts with SPDX lines, following [REUSE](https://reuse.software/):

  ```
  SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
  SPDX-License-Identifier: GPL-3.0-or-later
  ```

- By contributing you agree to license your work under GPL-3.0-or-later.
