# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Colors page: the accent, the installed color schemes, colors from the wallpaper or from another
tool, and the twelve colors of the theme with a check that the text can be read, beside the preview.

Top to bottom: the accent row; a short grid of color schemes with search and filter; the block "Colors
from the wallpaper" (one line until it is opened); then the editors and the contrast line on the left
and the preview on the right. Colors are always set by the theme, so the page has no part switch.
Every action of the person is one undo step: a dot, a card, "Use as light theme", an import, "Fix
contrast". `refresh` never edits.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
)

from ... import edits, library, paths, pickers, safefile
from ... import palette as palettes
from ...model.theme import FIELD_BY_ID, write_atomic
from ..banner import INFORMATION, POSITIVE, WARNING
from ..widgets import SPACING, THUMB_SIZE, CardGrid, ColorDots
from .base import LABEL_WIDTH, THIS_THEME, THIS_THEME_DELAY, ValuePage
from .colors_contrast import ContrastBox
from .colors_wallpaper import WallpaperAnswer, WallpaperBlock, WallpaperColors, WallpaperJob

translate = QCoreApplication.translate

SURFACES = ("window", "view", "button", "header")
TEXTS = ("text", "text_muted", "link", "visited")
ACCENTS = ("accent", "negative", "neutral", "positive")
ROLES = SURFACES + TEXTS + ACCENTS

# The accent colors System Settings offers.
STANDARD_ACCENTS = (
    "#e93a9a",
    "#e93d58",
    "#e9643a",
    "#e8cb2d",
    "#3bb566",
    "#3daee9",
    "#926ee4",
    "#8f8f8f",
)
PREVIEW_HEIGHT = 420
GRID_ROWS = 2  # rows of cards that show without scrolling the grid
PICTURE_FILTER = " (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff *.avif *.jxl)"
KIND_NAMES = {"pywal": "pywal", "matugen": "matugen"}


class _AccentFollows(QCheckBox):
    """The check box of `colors.accent_from_wallpaper`, in the form the window's editors have."""

    def __init__(self, page: ColorsPage):
        super().__init__(translate("ui", "Let the accent follow the wallpaper"))
        self.toggled.connect(
            lambda on: page.window.edit(FIELD_BY_ID[("colors", "accent_from_wallpaper")], on)
        )

    def set_title(self, title: str) -> None:
        self.setAccessibleName(self.text())

    def set_value(self, value) -> None:
        self.blockSignals(True)
        self.setChecked(bool(value))
        self.blockSignals(False)


def is_dark(color: str) -> bool:
    return QColor(color).lightnessF() < 0.5


class ColorsPage(ValuePage):
    key = "colors"
    parts = ("colors",)
    note_sections = ("colors",)
    modes = ("desktop", "window", "menu")

    def subtitle(self) -> str:
        return translate("ui", "The color scheme and the accent color. Every part follows these.")

    # ---- building

    def build(self) -> None:
        self.kind = pickers.kind("color_scheme")
        self.items: dict[str, pickers.Item] = {}
        self.extra_accents: list[str] = []  # accents the theme had that are no dot of ours (newest last)
        self.dot_of: dict[str, str] = {}  # the accent a dot became (made readable) -> the dot
        self.found: WallpaperColors | None = None
        self.picture: Path | None = None  # a picture the person chose instead of the wallpaper
        self.job_number = 0
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.answer = WallpaperAnswer(self)
        self.answer.done.connect(self._found, Qt.ConnectionType.QueuedConnection)
        self.this_timer = QTimer(self, singleShot=True, interval=THIS_THEME_DELAY)
        self.this_timer.timeout.connect(self.update_this_theme_card)
        self.window.loader.ready.connect(self._thumbnail_ready)

        self.install_button = QPushButton(translate("ui", "Install from File…"))
        self.install_button.clicked.connect(lambda: self.install_from_file())
        self.import_button = QPushButton(translate("ui", "Import Colors…"))
        self.import_menu = QMenu(self.import_button)
        self.import_button.setMenu(self.import_menu)
        self.header.add_action(self.import_button)
        self.header.add_action(self.install_button)

        self.content.addLayout(self._accent_row())
        self._build_schemes()
        self.wallpaper = WallpaperBlock()
        self.wallpaper.use_light.connect(lambda: self.use_wallpaper("light"))
        self.wallpaper.use_dark.connect(lambda: self.use_wallpaper("dark"))
        self.wallpaper.choose.connect(self.choose_picture)
        self.content.addWidget(self.wallpaper)
        super().build()
        # the preview keeps a sensible height beside the long column of editors; the hint stays under it
        self.preview.setMinimumHeight(PREVIEW_HEIGHT)
        self.preview.setMaximumHeight(PREVIEW_HEIGHT + 60)
        self.content.itemAt(self.content.count() - 1).layout().itemAt(1).layout().addStretch(1000)
        self._fill_import_menu()
        self.load_items()

    def _accent_row(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACING)
        grid.setVerticalSpacing(SPACING)
        grid.setColumnMinimumWidth(0, LABEL_WIDTH)
        grid.setColumnStretch(2, 1)
        self.accent_dots = ColorDots(STANDARD_ACCENTS)
        self.accent_dots.picked.connect(self.pick_accent)
        self.wallpaper_dots = ColorDots()
        self.wallpaper_dots.custom_button.hide()
        self.wallpaper_dots.setAccessibleName(translate("ui", "Accent colors from the wallpaper"))
        self.wallpaper_dots.picked.connect(self.pick_accent)
        self.wallpaper_label = QLabel(translate("ui", "From the wallpaper:"))
        self.follows = _AccentFollows(self)
        self.window.editors[("colors", "accent_from_wallpaper")] = self.follows
        self.follows.set_value(self.theme.get("colors", "accent_from_wallpaper"))
        self.follows.setAccessibleName(translate("ui", "Let the accent follow the wallpaper"))
        self.follows_note = QLabel(
            translate(
                "ui",
                "Plasma then takes the accent from the wallpaper and follows it when the wallpaper "
                "changes. The dots above are only the accent this theme starts with.",
            )
        )
        self.follows_note.setWordWrap(True)
        self.follows_note.setForegroundRole(self.follows_note.palette().ColorRole.PlaceholderText)
        grid.addWidget(QLabel(translate("ui", "Accent color:")), 0, 0, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.accent_dots, 0, 1, 1, 2)
        grid.addWidget(self.wallpaper_label, 1, 0, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.wallpaper_dots, 1, 1, 1, 2)
        grid.addWidget(self.follows, 2, 1, 1, 2)
        grid.addWidget(self.follows_note, 3, 1, 1, 2)
        self.wallpaper_label.hide()
        self.wallpaper_dots.hide()
        return grid

    def _build_schemes(self) -> None:
        self.grid = CardGrid(THUMB_SIZE, with_search=True, fit=False, name=translate("ui", "Color schemes"))
        self.grid.set_filters([("light", translate("ui", "Light")), ("dark", translate("ui", "Dark"))])
        self.grid.selected.connect(self._picked)
        self.grid.thumbnail_requested.connect(self._request)
        self.grid.setFixedHeight(self._grid_height())
        self.content.addWidget(self.caption(translate("ui", "Color schemes")))
        self.content.addWidget(self.grid)

    def _grid_height(self) -> int:
        """Room for the search bar and GRID_ROWS rows of cards."""
        from ..widgets import Card

        card = Card("probe", "Probe", "Probe", THUMB_SIZE).sizeHint().height()
        return 33 + GRID_ROWS * card + (GRID_ROWS - 1) * 16 + 4

    def build_controls(self) -> None:
        self.contrast = ContrastBox()
        self.contrast.fix_requested.connect(self.fix_contrast)
        self.controls.addWidget(self.caption(translate("ui", "Readability")))
        self.controls.addWidget(self.contrast)
        for title, keys in (
            (translate("ui", "Surfaces"), SURFACES),
            (translate("ui", "Text"), TEXTS),
            (translate("ui", "Accents and states"), ACCENTS),
        ):
            self.controls.addWidget(self.separator())
            self.controls.addWidget(self.caption(title))
            self.controls.addLayout(self.form(*(("colors", key) for key in keys)))

    # ---- showing

    def refresh(self) -> None:
        super().refresh()
        theme = self.theme
        self.grid.set_selected(self.selected_card())
        self.this_timer.start(THIS_THEME_DELAY)
        self._show_accent()
        self.follows.set_value(theme.get("colors", "accent_from_wallpaper"))
        self.contrast.set_colors(self.colors())

    def colors(self) -> dict[str, str]:
        return {role: self.theme.get("colors", role) for role in ROLES}

    def read_desktop(self) -> None:
        self.grid.set_in_use(self._match(self.window.active_scheme()))
        if self.picture is None:
            self.read_wallpaper()

    def leave(self) -> None:
        self.window.loader.cancel("color_scheme")
        self.grid.ask_again_for_thumbnails()

    # ---- the accent

    def _dots(self) -> list[str]:
        return [*self.extra_accents, *STANDARD_ACCENTS]

    def _show_accent(self) -> None:
        accent = str(self.theme.get("colors", "accent")).lower()
        wanted = self.dot_of.get(accent, accent)
        from_wallpaper = [c.lower() for c in (self.found.colors if self.found else [])]
        if (
            wanted not in STANDARD_ACCENTS
            and wanted not in from_wallpaper
            and wanted not in self.extra_accents
        ):
            self.extra_accents = [*self.extra_accents, wanted][-3:]
        if self.accent_dots.colors() != [QColor(c) for c in self._dots()]:
            self.accent_dots.set_colors(self._dots())
        if wanted in from_wallpaper and wanted not in self._dots():
            self.accent_dots.set_current(None)
            self.wallpaper_dots.set_current(wanted)
        else:
            self.accent_dots.set_current(wanted)
            self.wallpaper_dots.set_current(
                wanted if wanted in from_wallpaper and wanted not in STANDARD_ACCENTS else None
            )

    def pick_accent(self, color: QColor) -> None:
        """A dot, or the custom color: the accent, made readable on the window as with_accent does."""
        chosen = color.name().lower()
        fitted = palettes.with_accent(self.colors(), chosen)
        changes = {("colors", role): value for role, value in fitted.items() if role in ROLES}
        self.dot_of[str(fitted.get("accent", chosen)).lower()] = chosen
        self.window.edit_many(translate("ui", "Choose accent color"), changes)
        self.window.refresh()

    # ---- color schemes

    def load_items(self) -> None:
        found = self.kind.items() if self.kind is not None else []
        self.items = {item.id: item for item in found}
        cards = [
            (THIS_THEME, translate("ui", "This theme"), translate("ui", "The colors in the editor now"), "")
        ]
        for item in found:
            window = item.extra.get("colors", {}).get("window", "#ffffff")
            cards.append((item.id, item.name, item.description, "dark" if is_dark(window) else "light"))
        self.grid.set_items(cards)
        self.grid.set_empty_text(translate("ui", "No color schemes are installed."))
        self.this_timer.start(0)
        if self.built and self.stale is False:
            self.grid.set_selected(self.selected_card())

    def _match(self, value):
        if not value:
            return None
        return next((i for i in self.items if i.casefold() == str(value).casefold()), None)

    def selected_card(self) -> str:
        """The installed scheme that has exactly the editor's colors, else "This theme"."""
        theme = self.theme
        for item_id, item in self.items.items():
            colors = item.extra.get("colors", {})
            if colors and all(
                str(theme.get("colors", k)).lower() == str(v).lower() for k, v in colors.items()
            ):
                return item_id
        return THIS_THEME

    def installed(self, item: pickers.Item) -> library.InstalledScheme:
        return library.InstalledScheme(
            item.id,
            item.name,
            Path(item.path),
            item.user,
            bool(item.extra.get("made_here")),
            dict(item.extra["colors"]),
        )

    def _picked(self, item_id) -> None:
        item = self.items.get(item_id)
        if item is not None:
            changes, messages = edits.theme_edits_from_color_scheme(self.installed(item))
            self.window.edit_many(
                translate("ui", "Choose color scheme {name}").format(name=item.name), changes
            )
            if messages:
                self.window.banner.show_message(INFORMATION, " ".join(messages), 8)
        self.window.refresh()
        self.grid.set_selected(self.selected_card())  # a click on "This theme" changes nothing

    def update_this_theme_card(self) -> None:
        from .. import this_theme

        if self.grid.card(THIS_THEME) is not None:
            size, dpr = QSize(THUMB_SIZE), self.devicePixelRatioF()
            self.grid.set_thumbnail(THIS_THEME, this_theme.thumbnail("color_scheme", self.theme, size, dpr))

    def _request(self, item_id) -> None:
        item = self.items.get(item_id)
        if item is None or self.kind is None:
            return
        image = self.window.loader.request(self.kind, item, QSize(THUMB_SIZE), self.devicePixelRatioF(), {})
        if image is not None and not image.isNull():
            self.grid.set_thumbnail(item_id, image)
        elif image is not None:
            self.grid.set_no_preview(item_id)

    def _thumbnail_ready(self, kind_key: str, item_id: str, image) -> None:
        if kind_key != "color_scheme" or self.grid.card(item_id) is None:
            return
        if image.isNull():
            self.grid.set_no_preview(item_id)
        else:
            self.grid.set_thumbnail(item_id, image)

    # ---- installing

    def install_from_file(self, path: str | None = None) -> bool:
        """Copy a .colors file into the folder of color schemes, after checking that it is one."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, translate("ui", "Install Color Scheme"), "", translate("ui", "Color schemes (*.colors)")
            )
            if not path:
                return False
        source = Path(path)
        data = safefile.read_regular(source)
        scheme = library.parse_scheme(data, source, True) if data is not None else None
        if scheme is None or not source.stem.strip(". "):
            self.window.banner.show_message(
                WARNING,
                translate("ui", "{name} is not a color scheme, so it was not installed.").format(
                    name=source.name
                ),
                8,
            )
            return False
        target = paths.color_schemes_dir() / f"{source.stem}.colors"
        in_system = any(
            (folder / "color-schemes" / target.name).exists() for folder in paths.system_data_dirs()
        )
        if target.exists() or target.is_symlink() or in_system:
            if in_system and not (target.exists() or target.is_symlink()):
                question = translate(
                    "ui",
                    "A color scheme named {name} came with the system. Yours would hide it. "
                    "Install it anyway?",
                )
            else:
                question = translate("ui", "A color scheme named {name} is already installed. Replace it?")
            answer = QMessageBox.question(
                self, translate("ui", "Install Color Scheme"), question.format(name=source.stem)
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        try:
            write_atomic(target, data)
        except OSError as error:
            self.window.banner.show_message(
                WARNING,
                translate("ui", "{name} could not be installed: {problem}").format(
                    name=source.name, problem=error.strerror or error
                ),
                8,
            )
            return False
        self.load_items()
        self.window.banner.show_message(
            POSITIVE, translate("ui", "{name} is installed.").format(name=scheme.name), 6
        )
        return True

    # ---- colors from other places

    def _fill_import_menu(self) -> None:
        self.import_menu.clear()
        for source in palettes.available_sources():
            title = translate("ui", "From {tool}").format(tool=KIND_NAMES.get(source.kind, source.kind))
            action = self.import_menu.addAction(title)
            action.triggered.connect(lambda _=False, p=source.path: self.import_colors(str(p)))
        if not self.import_menu.isEmpty():
            self.import_menu.addSeparator()
        self.import_menu.addAction(translate("ui", "From a file…")).triggered.connect(
            lambda _=False: self.import_colors()
        )

    def import_colors(self, path: str | None = None) -> bool:
        """Load the colors of a pywal, matugen or .colors file into the editor (one undo step)."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                translate("ui", "Import Colors"),
                "",
                translate("ui", "Color files (*.json *.colors);;All files (*)"),
            )
            if not path:
                return False
        if path.endswith(".colors"):
            result = palettes.from_colors_file(path)
            name = translate("ui", "a color scheme")
        else:
            result = palettes.from_pywal(path)
            name = "pywal"
            if not result.ok:
                other = palettes.from_matugen(path)
                if other.ok:
                    result, name = other, "matugen"
        if not result.ok:
            self.window.banner.show_message(WARNING, str(result.error), 8)
            return False
        dark = result.given == "dark" or (
            result.given not in ("light", "dark") and is_dark(self.colors()["window"])
        )
        self.load_palette(
            result.dark if dark else result.light,
            translate("ui", "Import colors from {name}").format(name=name),
        )
        return True

    def load_palette(self, colors: dict[str, str], text: str) -> None:
        self.window.edit_many(
            text, {("colors", role): value for role, value in colors.items() if role in ROLES}
        )
        self.window.refresh()

    # ---- the wallpaper

    def read_wallpaper(self) -> None:
        """Start the worker that finds the wallpaper (or `self.picture`) and takes its colors."""
        self.job_number += 1
        self.wallpaper.set_busy()
        self.pool.start(WallpaperJob(self.job_number, self.picture, self.devicePixelRatioF(), self.answer))

    def _found(self, number: int, found: WallpaperColors) -> None:
        if number != self.job_number:
            return  # an answer for a picture that was replaced
        self.found = found
        self.wallpaper.show_found(found)
        colors = found.colors
        self.wallpaper_dots.set_colors(colors)
        self.wallpaper_label.setVisible(bool(colors))
        self.wallpaper_dots.setVisible(bool(colors))
        self._show_accent()

    def choose_picture(self, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                translate("ui", "Choose a Picture"),
                "",
                translate("ui", "Pictures") + PICTURE_FILTER,
            )
            if not path:
                return
        self.picture = Path(path)
        self.read_wallpaper()

    def use_wallpaper(self, variant: str) -> None:
        if self.found is None or self.found.result is None or not self.found.result.ok:
            return
        colors = self.found.result.light if variant == "light" else self.found.result.dark
        text = (
            translate("ui", "Use wallpaper colors as light theme")
            if variant == "light"
            else translate("ui", "Use wallpaper colors as dark theme")
        )
        self.load_palette(colors, text)

    # ---- contrast

    def fix_contrast(self) -> None:
        fixed = palettes.ensure_contrast(self.colors())
        changes = {
            ("colors", role): value for role, value in fixed.items() if value != self.colors().get(role)
        }
        if changes:
            self.window.edit_many(translate("ui", "Fix contrast"), changes)
            self.window.refresh()
