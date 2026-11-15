# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Themes page: saved themes, installed Global Themes and color schemes as cards.

Apply puts the selected card on the desktop; Return and a double click open it in the editor. A Global
Theme is loaded into the editor as one step that can be undone, and applying one applies the editor
theme after that: the package itself is never installed as the desktop's Global Theme.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import desktopparts
from ...edits import theme_edits_from_global_theme
from ...model.theme import FIELD_BY_ID, Theme, ThemeError
from ..banner import INFORMATION, WARNING
from ..library_view import GlobalEntry, LibraryView
from ..widgets import SPACING, FlowLayout, MoreAbout, themed_icon
from .base import Page
from .themes_desktop import theme_edits_from_desktop
from .themes_global import SummaryLoader

translate = QCoreApplication.translate

GLOBAL_THEME_MODULE = "kcm_lookandfeel"


class _NightSwitch(QCheckBox):
    """The check box of `desktop.dark_at_night`, in the form the window's editors have."""

    def __init__(self, page: ThemesPage):
        super().__init__(translate("ui", "Switch to Dark Mode at Night"))
        self.setAccessibleName(self.text())
        self.toggled.connect(lambda on: page.window.edit(FIELD_BY_ID[("desktop", "dark_at_night")], on))

    def set_title(self, title: str) -> None:
        self.setAccessibleName(self.text())

    def set_value(self, value) -> None:
        self.blockSignals(True)
        self.setChecked(bool(value))
        self.blockSignals(False)


class ThemesPage(Page):
    key = "themes"
    scrolling = False
    acts_on_selection = True
    parts = ("night_mode",)
    night_now = False  # what the desktop has, for while the theme leaves the switch alone

    def subtitle(self) -> str:
        return translate(
            "ui",
            "Pick a theme, then choose Apply to Desktop.",
        )

    def build(self) -> None:
        self.library = LibraryView(self.window.loader)
        self.summary = SummaryLoader(self)
        self.summary.ready.connect(self._summary_ready)
        self.shown_package = ""  # the package the strip describes
        self.library.selection_changed.connect(self._selection_changed)
        self.library.edit_requested.connect(self.open_entry)
        self.library.new_requested.connect(self.new_from_desktop)
        self.library.save_requested.connect(lambda: self.window.save_as())
        self.new_button = QPushButton(
            themed_icon("document-new"), translate("ui", "New Theme from the Desktop")
        )
        self.new_button.setToolTip(
            translate("ui", "Start a new theme from the colors and parts the desktop uses now.")
        )
        self.new_button.clicked.connect(self.new_from_desktop)
        self.save_button = QPushButton(themed_icon("document-save"), translate("ui", "Save Current Theme…"))
        self.save_button.setToolTip(
            translate("ui", "Save the theme in the editor as a file of your own. Nothing is applied.")
        )
        self.save_button.clicked.connect(lambda _=False: self.window.save_as())
        menu = QMenu(self)
        self.install_action = menu.addAction(
            themed_icon("document-import"), translate("ui", "Install from File…")
        )
        self.install_action.triggered.connect(lambda _=False: self.window.import_theme())
        self.settings_action = menu.addAction(
            themed_icon("preferences-system"), translate("ui", "Find More in System Settings…")
        )
        self.settings_action.triggered.connect(lambda _=False: self.open_system_settings())
        self.more_button = QPushButton(translate("ui", "Get New…"))
        self.more_button.setMenu(menu)
        self.more_button.setAccessibleName(translate("ui", "Get more themes"))
        for button in (self.library.edit_button, self.new_button, self.save_button, self.more_button):
            self.header.add_action(button)
        self._build_strip()
        self._build_night()
        self.content.addWidget(self.library, 1)
        self.content.addWidget(self.strip)
        self.content.addWidget(self.night_box)
        self.window.entry_handlers[GlobalEntry] = self.use_global
        self.reload()

    # ---- dark mode at night

    def _build_night(self) -> None:
        self.night_box = QFrame()
        box = QVBoxLayout(self.night_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)
        self.night = _NightSwitch(self)
        self.window.editors[("desktop", "dark_at_night")] = self.night
        self.night_more = MoreAbout(
            translate(
                "ui",
                "Plasma changes between its light and its dark Global Theme with the time of day. "
                "Which two it uses is chosen in System Settings. It is set when you choose Apply to Desktop.",
            ),
            lead=translate("ui", "Plasma changes between a light and a dark theme by itself."),
            head=self.night,
        )
        box.addWidget(self.night_more)
        # What a theme with a light and a dark variant adds: which parts follow Plasma's switch.
        self.night_variants = QLabel()
        self.night_variants.setWordWrap(True)
        self.night_variants.setTextFormat(Qt.TextFormat.PlainText)
        self.night_variants.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.night_variants.hide()
        box.addWidget(self.night_variants)

    def refresh(self) -> None:
        super().refresh()
        self._show_night()

    def _show_night(self) -> None:
        """The switch shows what the theme says, or, while the theme leaves it, what the desktop has."""
        value = self.window.theme.get("desktop", "dark_at_night")
        self.night.set_value(self.night_now if value is None else value)
        self._show_night_variants()

    def _show_night_variants(self) -> None:
        from ...generators.variants import NightVariantsTarget

        theme = self.window.theme
        if not theme.has_both:
            self.night_variants.hide()
            return
        target = NightVariantsTarget()
        if target.wanted(theme):
            text = "\n".join(str(note) for note in target.notes(theme))
        else:
            text = translate(
                "ui",
                "This theme has a light and a dark variant. Turn the switch on and Plasma changes "
                "between them by itself; until then Apply puts the variant you see on the desktop.",
            )
        self.night_variants.setText(text)
        self.night_variants.show()

    def read_desktop_state(self):
        """In a worker: whether the desktop changes between light and dark by itself."""
        runner = self.window.runner
        return bool(runner.which("kreadconfig6") and desktopparts.PARTS["night_mode"].current(runner))

    def show_desktop_state(self, state) -> None:
        self.night_now = bool(state)  # the switch only shows it
        self._show_night()

    # ---- the strip under the cards

    def _build_strip(self) -> None:
        self.strip = QFrame()
        self.strip.hide()
        box = QVBoxLayout(self.strip)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(SPACING)
        self.strip_title = self.caption("")
        self.strip_about = QLabel()
        self.strip_about.setWordWrap(True)
        self.strip_about.setTextFormat(Qt.TextFormat.PlainText)
        self.strip_about.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.strip_sets = QWidget()
        self.strip_sets_layout = FlowLayout(self.strip_sets, h=24, v=4)
        self.strip_sets_layout.setContentsMargins(0, 0, 0, 0)
        self.strip_empty = QLabel()
        self.strip_empty.setWordWrap(True)
        self.strip_empty.setTextFormat(Qt.TextFormat.PlainText)
        self.strip_note = QLabel(
            translate(
                "ui",
                "Apply to Desktop first copies these settings into the editor and then applies them. "
                "The theme's own panel layout and widgets are left as they are.",
            )
        )
        self.strip_note.setWordWrap(True)
        self.strip_note.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        for widget in (
            self.separator(),
            self.strip_title,
            self.strip_about,
            self.strip_sets,
            self.strip_empty,
            self.strip_note,
        ):
            box.addWidget(widget)

    def _selection_changed(self) -> None:
        self.window.update_apply_button()
        entry = self.library.current()
        if not isinstance(entry, GlobalEntry):
            self.shown_package = ""
            self.summary.cancel()
            self.strip.hide()
            return
        if entry.item.id == self.shown_package:
            return
        self.shown_package = entry.item.id
        author = str(entry.item.extra.get("author", "")).strip()
        self.strip_title.setText(
            translate("ui", "{name} by {author}").format(name=entry.title, author=author)
            if author
            else entry.title
        )
        self.strip_about.setText(entry.item.description)
        self.strip_about.setVisible(bool(entry.item.description))
        self._fill_strip([])
        self.strip_empty.setText(translate("ui", "Looking at what this theme changes…"))
        self.strip.show()
        self.summary.request(entry.item)

    def _summary_ready(self, item, rows) -> None:
        if item.id == self.shown_package:
            self._fill_strip(rows)
            self.strip_empty.setText(
                "" if rows else translate("ui", "This theme changes nothing that this app can edit.")
            )
            self.strip_empty.setVisible(not rows)

    def _fill_strip(self, rows) -> None:
        layout = self.strip_sets_layout
        while layout.count():
            item = layout.takeAt(0)
            item.widget().deleteLater()
        for part, value, installed in rows:
            if installed:
                text = translate("ui", "{part}: {value}").format(part=part, value=value)
            else:
                text = translate("ui", "{part}: {value} (not installed)").format(part=part, value=value)
            label = QLabel(text)
            label.setTextFormat(Qt.TextFormat.PlainText)
            if not installed:
                label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
            layout.addWidget(label)
        self.strip_sets.setVisible(bool(rows))
        self.strip_empty.setVisible(not rows)
        layout.invalidate()

    # ---- reading the desktop

    def global_theme(self) -> str:
        """The Global Theme the desktop records, or an empty text (a read: for a worker)."""
        runner = self.window.runner
        if not runner.which("kreadconfig6"):
            return ""
        try:
            return desktopparts.PARTS["global_theme"].current(runner) or ""
        except Exception:  # noqa: BLE001 - the mark is only a convenience
            return ""

    def reload(self) -> None:
        """Read the themes and what the desktop uses again; the desktop is asked in a worker."""
        self.read_in_background(
            lambda: (self.window.read_scheme(), self.global_theme()), self._reload_with, name="library"
        )

    def _reload_with(self, state) -> None:
        active, global_theme = state or ("", "")
        self.window._active = active
        self.library.reload(active, global_theme)

    def leave(self) -> None:
        self.library.leave()
        self.summary.cancel()
        self.shown_package = ""  # the strip asks again when the page is shown

    # ---- actions

    def open_entry(self, entry) -> None:
        """Return, a double click or the header button: open the theme in the editor."""
        if isinstance(entry, GlobalEntry):
            self.load_global(entry)
        else:
            self.window.edit_entry(entry)

    def load_global(self, entry: GlobalEntry) -> bool:
        """Fill the editor from a Global Theme as one undo step, and say what could not be matched.
        False when the editor could not take the values."""
        banner, name = self.window.banner, entry.title
        found, messages = theme_edits_from_global_theme(entry.item)
        trial = self.window.theme.copy()
        try:
            for (section, key), value in found.items():
                trial.set(section, key, value)
        except ThemeError as error:
            banner.show_message(
                WARNING,
                translate("ui", "{name} could not be loaded into the editor: {problem}").format(
                    name=name, problem=str(error.problems[0])
                ),
            )
            return False
        steps = self.window.undo_stack.count()
        self.window.edit_many(translate("ui", "Load {name}").format(name=name), found)
        if self.window.undo_stack.count() > steps:
            text = translate("ui", "Loaded {name} into the editor. Undo takes you back.").format(name=name)
        elif found:
            text = translate("ui", "The editor has everything {name} sets already.").format(name=name)
        else:
            text = translate("ui", "{name} sets none of the parts this app can change.").format(name=name)
        text += "".join(f" {message}" for message in messages)
        banner.show_message(WARNING if messages else INFORMATION, text)
        return True

    def use_global(self, entry: GlobalEntry) -> None:
        """Apply to Desktop on a Global Theme card: say what it does, load it, apply the editor theme."""
        answer = QMessageBox.question(
            self.window,
            translate("ui", "Apply to Desktop"),
            translate(
                "ui",
                "Apply “{name}”? Its settings are copied into the editor first, and then applied to the "
                "desktop. Its panel layout and widgets stay as they are. Undo last apply takes you back.",
            ).format(name=entry.title),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes and self.load_global(entry):
            self.window.apply_theme()

    def new_from_desktop(self) -> None:
        """A new theme in the editor from what the desktop uses now, as one undo step."""
        window = self.window
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            found, messages = theme_edits_from_desktop(window.runner)
        finally:
            QApplication.restoreOverrideCursor()
        theme = Theme.from_preset("breeze-light")
        found[("meta", "name")] = translate("ui", "My desktop")
        for (section, key), value in found.items():
            try:
                theme.set(section, key, value)
            except ThemeError:
                continue  # a value this app cannot hold is left as the preset has it
        window.replace_theme(translate("ui", "New theme from the desktop"), theme)
        text = translate(
            "ui",
            "This is a new theme made from what the desktop uses now. Nothing was applied. "
            "Undo brings the theme you had back. Change it on the pages, then choose Apply to Desktop.",
        )
        text += "".join(f" {message}" for message in messages)
        window.banner.show_message(WARNING if messages else INFORMATION, text)

    def open_system_settings(self) -> None:
        problem = desktopparts.open_system_settings(GLOBAL_THEME_MODULE, self.window.runner)
        if problem is not None:
            self.window.banner.show_message(WARNING, str(problem), 8)
