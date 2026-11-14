# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The editor window: sections, preview, inspector and the apply bar."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QFontDatabase,
    QIcon,
    QKeySequence,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_DIR, APP_NAME, __version__, archive, globaltheme, library, paths
from ..apply import engine
from ..apply import snapshot as snapshots
from ..apply.runner import SystemRunner
from ..generators import ApplyError
from ..generators.colorscheme import current_scheme
from ..model.color import contrast
from ..model.theme import FIELDS, PRESETS, SECTIONS, Field, Theme, ThemeError
from .banner import INFORMATION, POSITIVE, Banner
from .editors import editor_for
from .labels import FIELD_LABELS, PRESET_TITLES, SECTION_ICONS, SECTION_NOTES, SECTION_TITLES
from .library_view import Entry, LibraryView
from .preview import PreviewWidget
from .style_preview import StylePreview

translate = QCoreApplication.translate

MIN_TEXT_CONTRAST = 4.5
MERGE_SECONDS = 1.0
STYLE_PREVIEW_DELAY = 250  # milliseconds after the last edit before the style is made again
APPLY_NAME_LENGTH = 32  # longer theme names are shortened on the apply button


def state_titles() -> dict[str, str]:
    return {
        engine.NEW: translate("ui", "will be created"),
        engine.CHANGED: translate("ui", "will be updated"),
        engine.UNCHANGED: translate("ui", "already up to date"),
        engine.FOREIGN: translate("ui", "exists and was not made by this app"),
    }


# The sections whose values start from the ones on the Shapes page.
SHAPED_SECTIONS = {"apps", "window", "panel", "popup", "gtk", "rofi"}


def left_out_sections(plan: engine.Plan) -> list[str]:
    """The sections whose values an apply of this plan does not put on the desktop."""
    applied = {section for target in plan.wanted_targets for section in target.generator.sections}
    if applied & SHAPED_SECTIONS:
        applied.add("shape")  # the values of the parts that follow it are put on the desktop
    return [
        section
        for section in SECTIONS
        if section != "meta"
        and section not in applied
        and any(plan.theme.get(*f.id) != f.default for f in FIELDS if f.section == section)
    ]


# The values that only count while a style is on: field -> the field that turns it on. The
# value is used when that field is not "unchanged". One Plasma style holds the panel and
# the popups, so the popup values follow the panel's style.
GATED = {
    **{("apps", key): ("apps", "style") for key in ("radius", "border_width")},
    **{("gtk", key): ("gtk", "style") for key in ("radius", "border_width", "window_radius")},
    **{("rofi", key): ("rofi", "style") for key in ("radius", "border_width", "opacity", "font")},
    **{("panel", key): ("panel", "style") for key in ("radius", "border_width", "opacity")},
    **{("popup", key): ("panel", "style") for key in ("radius", "border_width", "opacity")},
    **{("window", key): ("window", "decoration") for key in ("radius", "border_width")},
}


class SetValueCommand(QUndoCommand):
    """One edit of one field. Quick successive edits of a field become one step."""

    def __init__(self, window: MainWindow, field: Field, value):
        super().__init__(str(FIELD_LABELS[field.id]))
        self.window, self.field = window, field
        self.old, self.new = window.theme.get(*field.id), value
        self.time = time.monotonic()

    def id(self) -> int:
        return FIELDS.index(self.field) + 1

    def mergeWith(self, other) -> bool:
        if other.field is not self.field or other.time - self.time > MERGE_SECONDS:
            return False
        self.new, self.time = other.new, other.time
        return True

    def redo(self) -> None:
        self.window.store(self.field, self.new)

    def undo(self) -> None:
        self.window.store(self.field, self.old)


class SnapshotDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("ui", "Snapshots"))
        self.resize(520, 360)
        self.chosen = None
        info = QLabel(
            translate(
                "ui",
                "A snapshot is taken before every apply. Restoring one puts the files and "
                "settings back to how they were just before that apply. The applies made "
                "after it are undone as well.",
            )
        )
        info.setWordWrap(True)
        self.list = QListWidget()
        for item in snapshots.list_snapshots():
            text = translate("ui", "{time} — before applying {name}").format(
                time=f"{item.created_at:%Y-%m-%d %H:%M:%S}", name=item.theme_name
            )
            entry = QListWidgetItem(text, self.list)
            entry.setData(Qt.ItemDataRole.UserRole, item.id)
        self.list.setCurrentRow(0)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.restore_button = buttons.addButton(
            translate("ui", "Restore"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.restore_button.setEnabled(self.list.count() > 0)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self.list.itemDoubleClicked.connect(lambda _item: self._accept())
        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addWidget(self.list, 1)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        current = self.list.currentItem()
        if current is not None:
            self.chosen = snapshots.get(current.data(Qt.ItemDataRole.UserRole))
            self.accept()


class MainWindow(QMainWindow):
    def __init__(self, runner=None):
        super().__init__()
        self.runner = runner or SystemRunner()
        self.theme = Theme.from_preset("breeze-light")
        self.path: Path | None = None
        self.editors: dict[tuple[str, str], QWidget] = {}
        self.notes: dict[str, QLabel] = {}
        self.note_rows: dict[str, QWidget] = {}
        self.plan = engine.build_plan(self.theme)
        # Switches made on the Themes tab that can still be undone: snapshot id ->
        # (theme and file the editor held before, the file the next start would
        # have opened, theme the editor holds since).
        self.switches: dict[str, tuple[Theme, Path | None, str, Theme]] = {}
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self.refresh_timer = QTimer(self, singleShot=True, interval=30)
        self.refresh_timer.timeout.connect(self.refresh)
        self.style_timer = QTimer(self, singleShot=True, interval=STYLE_PREVIEW_DELAY)
        self.style_timer.timeout.connect(self._update_style_preview)

        self._build_central()
        self._build_actions()
        self.resize(1180, 720)
        self._sync_inherited()
        self.refresh()
        self.reload_library()
        self._update_title()

    # ---- construction ------------------------------------------------

    def _build_central(self) -> None:
        self.sections = QListWidget()
        self.sections.setAccessibleName(translate("ui", "Sections"))
        self.sections.setMaximumWidth(220)
        self.inspector = QStackedWidget()
        for section in SECTIONS:
            item = QListWidgetItem(QIcon.fromTheme(SECTION_ICONS[section]), str(SECTION_TITLES[section]))
            self.sections.addItem(item)
            self.inspector.addWidget(self._build_page(section))
        self.sections.currentRowChanged.connect(self.inspector.setCurrentIndex)

        self.preview = PreviewWidget(self.theme)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.library = LibraryView()
        self.library.use_requested.connect(self.use_entry)
        self.library.edit_requested.connect(self.edit_entry)
        self.tabs.addTab(self.library, translate("ui", "Themes"))
        self.tabs.addTab(self.preview, translate("ui", "Preview"))
        self.style_preview = StylePreview(self.theme)
        self.style_preview_stale = False
        self.tabs.addTab(self.style_preview, translate("ui", "Application style"))
        self.tabs.addTab(self._build_files_tab(), translate("ui", "Files written"))

        splitter = QSplitter()
        splitter.addWidget(self.sections)
        splitter.addWidget(self.tabs)
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([190, 640, 350])
        splitter.setChildrenCollapsible(False)

        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.undo_apply_button = QPushButton(QIcon.fromTheme("edit-undo"), translate("ui", "Undo last apply"))
        self.undo_apply_button.clicked.connect(self.undo_last_apply)
        self.apply_button = QPushButton(
            QIcon.fromTheme("dialog-ok-apply"), translate("ui", "Apply to desktop")
        )
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.apply_shown)
        self.library.selection_changed.connect(self._update_apply_button)
        self.tabs.currentChanged.connect(lambda _index: self._update_apply_button())
        self.tabs.currentChanged.connect(lambda _index: self._update_style_preview())
        footer = QHBoxLayout()
        footer.addWidget(self.notice, 1)
        footer.addWidget(self.undo_apply_button)
        footer.addWidget(self.apply_button)

        self.banner = Banner()
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.banner)
        layout.addWidget(splitter, 1)
        layout.addLayout(footer)
        self.setCentralWidget(central)
        self.sections.setCurrentRow(1)

    def _build_page(self, section: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(str(SECTION_TITLES[section]))
        font = heading.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.2)
        heading.setFont(font)
        layout.addWidget(heading)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for field in FIELDS:
            if field.section != section:
                continue
            title = str(FIELD_LABELS[field.id])
            editor = editor_for(field)
            editor.set_title(title)
            editor.set_value(self.theme.get(*field.id))
            editor.changed.connect(lambda value, field=field: self.edit(field, value))
            self.editors[field.id] = editor
            form.addRow(title + translate("ui", ":"), editor)
        layout.addLayout(form)
        layout.addWidget(self._build_note(section))
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(page)
        scroll.setMinimumWidth(300)
        return scroll

    def _build_files_tab(self) -> QWidget:
        self.files_info = QLabel()
        self.files_info.setWordWrap(True)
        # Commands and paths are shown as they are: "<" must not start a tag.
        self.files_info.setTextFormat(Qt.TextFormat.PlainText)
        self.files_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.files_list = QListWidget()
        self.files_list.setMaximumHeight(90)
        self.files_list.currentRowChanged.connect(self._show_file)
        self.file_content = QPlainTextEdit()
        self.file_content.setReadOnly(True)
        self.file_content.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.file_content.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        open_folder = QPushButton(QIcon.fromTheme("document-open-folder"), translate("ui", "Open folder"))
        open_folder.clicked.connect(self._open_file_folder)
        row = QHBoxLayout()
        row.addWidget(self.files_info, 1)
        row.addWidget(open_folder)
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addLayout(row)
        layout.addWidget(self.files_list)
        layout.addWidget(self.file_content, 1)
        return tab

    def _build_note(self, section: str) -> QWidget:
        """What becomes of this section's values on the desktop. Filled in by refresh()."""
        icon = QLabel()
        icon.setPixmap(QIcon.fromTheme("dialog-information").pixmap(16, 16))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        note = self.notes[section] = QLabel()
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = self.note_rows[section] = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.addWidget(icon)
        layout.addWidget(note, 1)
        return row

    def _build_actions(self) -> None:
        def action(text, slot, shortcut=None, icon=None):
            item = QAction(QIcon.fromTheme(icon) if icon else QIcon(), text, self)
            if shortcut:
                item.setShortcut(shortcut)
            item.triggered.connect(slot)
            return item

        file_menu = self.menuBar().addMenu(translate("ui", "&File"))
        new_menu = file_menu.addMenu(QIcon.fromTheme("document-new"), translate("ui", "&New from preset"))
        for preset in PRESETS:
            new_menu.addAction(
                action(str(PRESET_TITLES[preset]), lambda _checked=False, p=preset: self.new_theme(p))
            )
        file_menu.addAction(
            action(
                translate("ui", "&Open…"), self.open_dialog, QKeySequence.StandardKey.Open, "document-open"
            )
        )
        file_menu.addAction(
            action(translate("ui", "&Save"), self.save, QKeySequence.StandardKey.Save, "document-save")
        )
        file_menu.addAction(
            action(
                translate("ui", "Save &As…"),
                self.save_as,
                QKeySequence.StandardKey.SaveAs,
                "document-save-as",
            )
        )
        file_menu.addSeparator()
        file_menu.addAction(
            action(translate("ui", "&Import Theme…"), self.import_theme, icon="document-import")
        )
        file_menu.addAction(
            action(translate("ui", "&Export Theme…"), self.export_theme, icon="document-export")
        )
        file_menu.addAction(
            action(
                translate("ui", "Export as &Global Theme…"),
                self.export_global_theme,
                icon="preferences-desktop-theme-global",
            )
        )
        file_menu.addSeparator()
        file_menu.addAction(
            action(
                translate("ui", "Show &themes folder"),
                lambda: self._open_folder(paths.themes_dir()),
                icon="document-open-folder",
            )
        )
        file_menu.addAction(
            action(
                translate("ui", "Show &color schemes folder"),
                lambda: self._open_folder(paths.color_schemes_dir()),
                icon="document-open-folder",
            )
        )
        file_menu.addSeparator()
        file_menu.addAction(
            action(translate("ui", "&Quit"), self.close, QKeySequence.StandardKey.Quit, "application-exit")
        )

        edit_menu = self.menuBar().addMenu(translate("ui", "&Edit"))
        undo = self.undo_stack.createUndoAction(self, translate("ui", "&Undo"))
        undo.setShortcut(QKeySequence.StandardKey.Undo)
        undo.setIcon(QIcon.fromTheme("edit-undo"))
        redo = self.undo_stack.createRedoAction(self, translate("ui", "&Redo"))
        redo.setShortcut(QKeySequence.StandardKey.Redo)
        redo.setIcon(QIcon.fromTheme("edit-redo"))
        edit_menu.addActions([undo, redo])

        desktop_menu = self.menuBar().addMenu(translate("ui", "&Desktop"))
        desktop_menu.addAction(
            action(translate("ui", "&Apply to desktop"), self.apply_shown, "Ctrl+Return", "dialog-ok-apply")
        )
        desktop_menu.addAction(action(translate("ui", "&Undo last apply"), self.undo_last_apply))
        desktop_menu.addAction(
            action(translate("ui", "&Snapshots…"), self.show_snapshots, icon="view-history")
        )

        help_menu = self.menuBar().addMenu(translate("ui", "&Help"))
        help_menu.addAction(
            action(translate("ui", "&About {app}").format(app=APP_NAME), self.about, icon="help-about")
        )

    # ---- editing -----------------------------------------------------

    def edit(self, field: Field, value) -> None:
        """Called when the user changes a control."""
        if value == self.theme.get(*field.id):
            return
        try:
            self.theme.copy().set(field.section, field.key, value)
        except ThemeError as error:
            self.editors[field.id].set_value(self.theme.get(*field.id))
            self.statusBar().showMessage(str(error.problems[0]), 6000)
            return
        if self.tabs.currentWidget() is self.library:
            self.tabs.setCurrentWidget(self.preview)  # show what the edit does
        self.undo_stack.push(SetValueCommand(self, field, value))

    def store(self, field: Field, value) -> None:
        self.theme.set(field.section, field.key, value)
        self.editors[field.id].set_value(self.theme.get(*field.id))
        self._sync_inherited()
        self.refresh_timer.start()

    def _sync_inherited(self) -> None:
        """Tell the optional fields which value they follow while unset, and turn off
        the values of a part that is left as it is."""
        for field in FIELDS:
            if field.inherits:
                self.editors[field.id].set_inherited(self.theme.resolved(*field.inherits))
        for field_id, gate in GATED.items():
            editor = self.editors[field_id]
            on = self.theme.get(*gate) != "unchanged"
            editor.setEnabled(on)
            editor.setToolTip(
                ""
                if on
                else translate("ui", "Used when “{setting}” is not “Leave as it is”.").format(
                    setting=str(FIELD_LABELS[gate])
                )
            )

    def _load_into_window(self, theme: Theme, path: Path | None) -> None:
        self.theme, self.path = theme, path
        self.undo_stack.clear()
        self._sync_inherited()
        for field in FIELDS:
            self.editors[field.id].set_value(theme.get(*field.id))
        self.refresh()
        self._update_title()

    def refresh(self) -> None:
        """Bring preview, file list and messages in line with the theme."""
        self.preview.set_theme(self.theme)
        self.style_preview_stale = True
        if self.tabs.currentWidget() is self.style_preview:
            self.style_timer.start()  # making the style takes a moment: wait for the edits to stop
        self.plan = engine.build_plan(self.theme)
        selected = max(self.files_list.currentRow(), 0)
        self.files_list.blockSignals(True)
        self.files_list.clear()
        titles = state_titles()
        commands = []
        for target in self.plan.targets:
            if target.reload_command:
                commands.append(target.reload_command)
            for status in target.files:
                item = QListWidgetItem(f"{status.file.path} — {titles[status.state]}", self.files_list)
                item.setData(Qt.ItemDataRole.UserRole, status.file)
            for path in target.stale:
                if path.is_file():
                    removed = translate("ui", "no longer needed, will be removed")
                    QListWidgetItem(f"{path} — {removed}", self.files_list)
        self.files_list.blockSignals(False)
        self.files_list.setCurrentRow(min(selected, self.files_list.count() - 1))
        self._show_file(self.files_list.currentRow())
        self.files_info.setText(self._apply_summary(commands))

        notices = [str(p) for p in self.plan.blocking]
        if not notices:
            for background in ("window", "view", "button", "header"):
                ratio = contrast(self.theme.color("text"), self.theme.color(background))
                if ratio < MIN_TEXT_CONTRAST:
                    notices.append(
                        translate(
                            "ui", 'Text is hard to read on "{surface}" (contrast {ratio}:1, aim for 4.5:1).'
                        ).format(surface=str(FIELD_LABELS[("colors", background)]), ratio=f"{ratio:.1f}")
                    )
        self.notice.setText("\n".join(notices))
        for section, note in self.notes.items():
            targets = [target for target in self.plan.targets if section in target.generator.sections]
            texts = [
                str(text)
                for target in targets
                for text in target.generator.section_notes(self.plan.theme, section)
            ]
            if section in SECTION_NOTES:
                texts = [str(SECTION_NOTES[section]), *texts]
            note.setText("\n\n".join(texts))
            self.note_rows[section].setVisible(bool(texts))
        self._update_apply_button()
        self.undo_apply_button.setEnabled(snapshots.latest() is not None)
        self._update_title()

    def _update_style_preview(self) -> None:
        """The application style is only made while its tab is shown."""
        if self.style_preview_stale and self.tabs.currentWidget() is self.style_preview:
            self.style_preview_stale = False
            self.style_preview.set_theme(self.theme)

    def _apply_summary(self, commands: list[str]) -> str:
        """Everything an apply does to the system, so that nothing comes as a surprise."""
        if not commands:
            return ""
        settings = [str(text) for target in self.plan.targets for text in target.settings]
        if settings:
            return translate(
                "ui",
                "Apply writes these files and then runs: {commands}. It also changes {settings}. "
                "Nothing else on the system is changed.",
            ).format(commands=", ".join(commands), settings="; ".join(settings))
        return translate(
            "ui",
            "Apply writes these files and then runs: {commands}. Nothing else on the system is changed.",
        ).format(commands=", ".join(commands))

    def _update_apply_button(self) -> None:
        """Make the apply button name the theme it will put on the desktop."""
        if self.tabs.currentWidget() is self.library:
            entry = self.library.current()
            name, enabled = (entry.title if entry else ""), entry is not None
            tip = "" if entry else translate("ui", "Select a theme first.")
        else:
            name, enabled, tip = self.theme.name, not self.plan.blocking, ""
        if len(name) > APPLY_NAME_LENGTH:
            name = name[: APPLY_NAME_LENGTH - 1] + "…"
        self.apply_button.setText(
            translate("ui", "Apply “{name}” to desktop").format(name=name.replace("&", "&&"))
            if name
            else translate("ui", "Apply to desktop")
        )
        self.apply_button.setEnabled(enabled)
        self.apply_button.setToolTip(tip)

    def _show_file(self, row: int) -> None:
        file = self._listed_file(row)
        self.file_content.setPlainText(file.content if file else "")

    def _listed_file(self, row: int):
        """The planned file on a row of the list; None for a file that will be removed."""
        item = self.files_list.item(row)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_title(self) -> None:
        name = self.path.name if self.path else translate("ui", "Unsaved theme")
        self.setWindowTitle(f"{self.theme.name or name} ({name})[*]")
        self.setWindowModified(not self.undo_stack.isClean())

    # ---- files -------------------------------------------------------

    def _discard_ok(self) -> bool:
        if self.undo_stack.isClean():
            return True
        answer = QMessageBox.warning(
            self,
            translate("ui", "Unsaved changes"),
            translate("ui", "The theme has changes that are not saved."),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def new_theme(self, preset: str) -> None:
        if self._discard_ok():
            self._load_into_window(Theme.from_preset(preset), None)

    def open_dialog(self) -> None:
        if not self._discard_ok():
            return
        paths.themes_dir().mkdir(parents=True, exist_ok=True)
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            translate("ui", "Open theme"),
            str(self.path.parent if self.path else paths.themes_dir()),
            translate("ui", "Plasma Theme Studio themes (*.toml)"),
        )
        if chosen:
            self.open_path(Path(chosen))

    def open_path(self, path: Path) -> bool:
        try:
            theme = Theme.load(path)
        except ThemeError as error:
            self._show_problems(
                translate("ui", "{file} could not be opened.").format(file=path.name), error.problems
            )
            return False
        self._take_into_editor(theme, path)
        return True

    def _take_into_editor(self, theme: Theme, path: Path | None) -> None:
        """Make a theme the one the editor works on, and the one the next start opens."""
        self._load_into_window(theme, path)
        if path is not None:
            QSettings().setValue("last_file", str(path))

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        return self._save_to(self.path)

    def save_as(self) -> bool:
        paths.themes_dir().mkdir(parents=True, exist_ok=True)
        folder = self.path.parent if self.path else paths.themes_dir()
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            translate("ui", "Save theme"),
            str(folder / f"{self.theme.slug or 'theme'}.toml"),
            translate("ui", "Plasma Theme Studio themes (*.toml)"),
        )
        if not chosen:
            return False
        path = Path(chosen)
        return self._save_to(path if path.suffix else path.with_suffix(".toml"))

    def _save_to(self, path: Path) -> bool:
        try:
            self.theme.save(path)
        except OSError as error:
            QMessageBox.critical(
                self,
                translate("ui", "Could not save"),
                translate("ui", "{file} could not be saved: {detail}").format(
                    file=str(path), detail=str(error)
                ),
            )
            return False
        self.path = path
        self.undo_stack.setClean()
        self._update_title()
        QSettings().setValue("last_file", str(path))
        self.statusBar().showMessage(translate("ui", "Saved {file}").format(file=str(path)), 5000)
        self.reload_library()
        return True

    def import_theme(self) -> None:
        """Read a theme from a theme file or archive and open it as a new saved theme."""
        if not self._discard_ok():
            return
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            translate("ui", "Import theme"),
            str(Path.home()),
            translate("ui", "Plasma Theme Studio themes (*{ext} *.toml)").format(ext=archive.EXTENSION),
        )
        if chosen:
            self.import_path(Path(chosen))

    def import_path(self, path: Path) -> bool:
        try:
            theme = archive.import_theme(path)
            theme, saved = library.save_imported(theme)
        except archive.ArchiveError as error:
            self._show_problems(
                translate("ui", "{file} could not be imported.").format(file=path.name), [error.message]
            )
            return False
        except OSError as error:
            self._show_problems(
                translate("ui", "{file} could not be imported.").format(file=path.name), [str(error)]
            )
            return False
        self._take_into_editor(theme, saved)
        self.reload_library()
        self.tabs.setCurrentWidget(self.preview)
        self.banner.show_message(
            INFORMATION,
            translate(
                "ui", "Imported {name}. It is saved as {file}; nothing was applied to the desktop."
            ).format(name=theme.name, file=str(saved)),
        )
        return True

    def export_theme(self) -> None:
        """Write the theme in the editor as a single shareable file."""
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            translate("ui", "Export theme"),
            str(Path.home() / f"{self.theme.slug or 'theme'}{archive.EXTENSION}"),
            translate("ui", "Plasma Theme Studio themes (*{ext})").format(ext=archive.EXTENSION),
        )
        if chosen:
            path = Path(chosen)
            self.export_path(
                path if path.suffix == archive.EXTENSION else path.with_name(path.name + archive.EXTENSION)
            )

    def export_path(self, path: Path) -> bool:
        try:
            archive.export_theme(self.theme, path)
        except OSError as error:
            self._show_problems(
                translate("ui", "{file} could not be exported.").format(file=str(path)), [str(error)]
            )
            return False
        self.statusBar().showMessage(translate("ui", "Exported {file}").format(file=str(path)), 5000)
        return True

    def export_global_theme(self) -> None:
        """Write the theme as a Global Theme that can be installed and shared."""
        chosen = QFileDialog.getExistingDirectory(
            self, translate("ui", "Choose an empty folder for the Global Theme"), str(Path.home())
        )
        if chosen:
            self.export_global_path(Path(chosen))

    def export_global_path(self, folder: Path) -> bool:
        heading = translate("ui", "The Global Theme could not be exported.")
        try:
            written = globaltheme.export_global_theme(self.theme, folder)
        except globaltheme.ExportError as error:
            self._show_problems(heading, [error.message])
            return False
        except OSError as error:
            self._show_problems(heading, [str(error)])
            return False
        self.banner.show_message(
            POSITIVE,
            translate(
                "ui",
                "Exported {name} as a Global Theme ({count} files) in {folder}. "
                "Run install.sh there to install it. It holds the color scheme, the window frame "
                "and the Plasma style; the application style, GTK and Rofi are not part of it. "
                "Applying a Global Theme also turns the splash screen off.",
            ).format(name=self.theme.name, count=len(written), folder=str(folder)),
            30,
        )
        return True

    def _open_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_file_folder(self) -> None:
        file = self._listed_file(self.files_list.currentRow())
        if file is not None:
            self._open_folder(file.path.parent)

    def closeEvent(self, event) -> None:
        if self._discard_ok():
            event.accept()
        else:
            event.ignore()

    # ---- desktop -----------------------------------------------------

    def _show_problems(self, title: str, problems) -> None:
        box = QMessageBox(QMessageBox.Icon.Warning, APP_NAME, title, parent=self)
        box.setInformativeText("\n".join(f"• {problem}" for problem in problems))
        box.exec()

    def reload_library(self) -> None:
        active = current_scheme(self.runner) if self.runner.which("kreadconfig6") else ""
        self.library.reload(active)

    def apply_shown(self) -> None:
        """Apply what the user is looking at: the theme selected on the Themes
        tab, or on the other tabs the theme in the editor."""
        if self.tabs.currentWidget() is not self.library:
            self.apply_theme()
            return
        entry = self.library.current()
        if entry is not None:
            self.use_entry(entry)

    def use_entry(self, entry: Entry) -> None:
        """Switch the desktop to a theme from the Themes tab.

        The editor takes the theme over, so that what is changed and applied
        next changes this theme and does not bring back the one before it."""
        if self._in_editor(entry):
            self._apply(self.theme, from_library=True)  # with its unsaved edits
            return
        if not self._discard_ok():
            return
        # Edits that were discarded just now must not come back with an undo of the switch.
        before = None
        if self.undo_stack.isClean():
            before = (self.theme, self.path, QSettings().value("last_file", "") or "")
        if entry.is_saved_theme:
            outcome = self._apply(entry.theme, from_library=True)
        else:
            outcome = self._switch_scheme(entry)
        if outcome is False:
            return
        theme = entry.theme.copy()
        self._take_into_editor(theme, entry.path)
        if before is not None and isinstance(outcome, snapshots.Snapshot):
            self.switches[outcome.id] = (*before, theme)

    def _in_editor(self, entry: Entry) -> bool:
        """Whether an entry of the Themes tab is the theme the editor holds: its
        file, or the color scheme that an apply wrote from it."""
        if entry.is_saved_theme:
            return entry.path == self.path
        return entry.scheme.made_here and entry.scheme_id == self.theme.slug

    def _switch_scheme(self, entry: Entry) -> snapshots.Snapshot | bool:
        """Make an installed color scheme the one in use. Returns the snapshot,
        True when the desktop had the scheme already, False when it failed."""
        active = current_scheme(self.runner) if self.runner.which("kreadconfig6") else self.library.active
        if entry.scheme_id == active:
            self.reload_library()  # the mark may be from before the desktop was changed elsewhere
            self.banner.show_message(
                INFORMATION, translate("ui", "The desktop already uses {name}.").format(name=entry.title)
            )
            return True
        nothing_changed = translate("ui", "The desktop could not be switched. Nothing was changed.")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            snapshot = engine.switch_color_scheme(entry.scheme_id, entry.title, self.runner, entry.theme)
        except engine.ApplyBlocked as error:
            self._show_problems(nothing_changed, error.problems)
            return False
        except ApplyError as error:
            self._show_problems(nothing_changed, [error.message])
            return False
        finally:
            QApplication.restoreOverrideCursor()
            self.refresh()
            self.reload_library()
        self.banner.show_message(
            POSITIVE,
            translate(
                "ui",
                "The desktop now uses {name}. Undo last apply takes you back. "
                "Changes you make in the editor go into {theme}, a new theme that is not saved yet.",
            ).format(name=entry.title, theme=entry.theme.name),
            20,
        )
        return snapshot

    def edit_entry(self, entry: Entry) -> None:
        """Open a theme from the Themes tab in the editor."""
        if not self._discard_ok():
            return
        if entry.is_saved_theme:
            if not self.open_path(entry.path):
                return
            self.banner.hide()
        else:
            self._load_into_window(library.theme_from_scheme(entry.scheme), None)
            self.banner.show_message(
                INFORMATION,
                translate(
                    "ui",
                    "This is a new theme that starts with the colors of {name}. "
                    "Change it on the right, then choose Apply to desktop.",
                ).format(name=entry.title),
            )
        self.tabs.setCurrentWidget(self.preview)

    def apply_theme(self) -> None:
        self._apply(self.theme)

    def _apply(self, theme: Theme, from_library: bool = False) -> snapshots.Snapshot | bool:
        """Put a theme on the desktop. Returns the snapshot of the apply, True when
        the desktop had the theme already, False when the desktop is not on it."""
        nothing_changed = translate("ui", "The theme cannot be applied. Nothing was changed.")
        plan = engine.build_plan(theme, self.runner)
        if plan.blocking:
            self._show_problems(nothing_changed, plan.blocking)
            return False
        if engine.is_current(plan, self.runner):
            if from_library:
                text = translate("ui", "The desktop already uses {name}.")
            else:
                text = translate(
                    "ui",
                    "The desktop already uses {name} exactly as it is here, so nothing changed. "
                    "Change something and apply again.",
                )
            self.banner.show_message(INFORMATION, text.format(name=theme.name) + self._not_applied_note(plan))
            return True
        if plan.foreign_files:
            answer = QMessageBox.question(
                self,
                translate("ui", "Replace existing files?"),
                translate(
                    "ui",
                    "These files already exist and were not made by Plasma Theme Studio:\n\n{files}\n\n"
                    "They are kept in a snapshot, so the apply can be undone. Replace them?",
                ).format(files="\n".join(str(p) for p in plan.foreign_files)),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = engine.apply(theme, self.runner, replace_foreign=True)
        except engine.ApplyBlocked as error:
            self._show_problems(nothing_changed, error.problems)
            return False
        except ApplyError as error:
            if error.restored:
                heading = translate("ui", "The apply failed. Everything was put back as it was.")
            else:
                heading = translate("ui", "The apply failed, and not everything could be put back.")
            self._show_problems(heading, [error.message])
            return False
        finally:
            QApplication.restoreOverrideCursor()
            self.refresh()
            self.reload_library()
        message = translate("ui", "Applied {name} to the desktop. Undo last apply takes you back.").format(
            name=theme.name
        )
        warnings = "".join(f" {warning}" for warning in result.plan.warnings)
        self.banner.show_message(POSITIVE, message + warnings + self._not_applied_note(result.plan), 20)
        return result.snapshot

    def _not_applied_note(self, plan: engine.Plan) -> str:
        """Said when the theme has values that were not put on the desktop."""
        sections = left_out_sections(plan)
        if not sections:
            return ""
        return " " + translate(
            "ui", "Not put on the desktop: {sections}. The pages with those names say why."
        ).format(sections=", ".join(str(SECTION_TITLES[section]) for section in sections))

    def _restore(self, snapshot) -> None:
        """Go back to a snapshot, undoing every apply made since, the newest first."""
        reached = None
        # A snapshot that is gone already was removed as too old, not undone.
        present = {item.id for item in snapshots.list_snapshots()}
        self.switches = {key: value for key, value in self.switches.items() if key in present}
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            reached, failures = engine.restore_to(snapshot, self.runner)
        except OSError as error:
            failures = [str(error)]
        finally:
            QApplication.restoreOverrideCursor()
        editor_went_back = self._undo_switches()
        self.refresh()
        self.reload_library()
        if failures:
            if reached is not None and reached.id != snapshot.id:
                failures = [
                    *failures,
                    translate(
                        "ui",
                        "The undo stopped at the apply of {time}. "
                        "The applies before it were left as they are.",
                    ).format(time=f"{reached.created_at:%H:%M:%S}"),
                ]
            if reached is not None and snapshots.get(reached.id) is not None:
                failures = [
                    *failures,
                    translate("ui", "The snapshot is kept, so Undo last apply can try once more."),
                ]
            self._show_problems(translate("ui", "Some things could not be put back."), failures)
            return
        message = translate("ui", "The desktop is back to how it was at {time}.").format(
            time=f"{snapshot.created_at:%H:%M:%S}"
        )
        if editor_went_back:
            message += " " + translate("ui", "The editor holds {name} again.").format(name=self.theme.name)
        self.banner.show_message(POSITIVE, message, 20)

    def _undo_switches(self) -> bool:
        """After an undo: when a switch made on the Themes tab was undone, the
        editor goes back to the theme it held before the switch. It stays as it
        is when it holds something else by now, or changes that are not saved."""
        present = {item.id for item in snapshots.list_snapshots()}
        went_back = False
        for key in sorted(set(self.switches) - present, reverse=True):
            theme, path, last_file, since = self.switches.pop(key)
            if self.theme is not since or not self.undo_stack.isClean():
                continue
            if path is not None and not path.is_file():
                continue  # the file was removed in the meantime
            self._take_into_editor(theme, path)
            if path is None:
                QSettings().setValue("last_file", last_file)
            went_back = True
        return went_back

    def undo_last_apply(self) -> None:
        latest = snapshots.latest()
        if latest is not None:
            self._restore(latest)

    def show_snapshots(self) -> None:
        dialog = SnapshotDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.chosen is not None:
            self._restore(dialog.chosen)

    def about(self) -> None:
        QMessageBox.about(
            self,
            translate("ui", "About {app}").format(app=APP_NAME),
            translate(
                "ui",
                "<h3>{app} {version}</h3>"
                "<p>Edit every part of a KDE Plasma theme in one place.</p>"
                '<p>Themes are stored in <a href="{themes_url}">{themes}</a>. '
                'Snapshots are stored in <a href="{snapshots_url}">{snapshots}</a>.</p>'
                "<p>Free software under the GNU General Public License, version 3 or later.<br>"
                '<a href="https://github.com/Kryckan/plasma-theme-studio">'
                "github.com/Kryckan/plasma-theme-studio</a></p>",
            ).format(
                app=APP_NAME,
                version=__version__,
                themes=str(paths.themes_dir()),
                themes_url=QUrl.fromLocalFile(str(paths.themes_dir())).toString(),
                snapshots=str(paths.data_home() / APP_DIR / "snapshots"),
                snapshots_url=QUrl.fromLocalFile(str(paths.snapshots_dir())).toString(),
            ),
        )
