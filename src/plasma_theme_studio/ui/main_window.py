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

from .. import APP_DIR, APP_NAME, __version__, library, paths
from ..apply import engine
from ..apply import snapshot as snapshots
from ..apply.runner import SystemRunner
from ..generators import ApplyError
from ..generators.colorscheme import current_scheme
from ..model.color import contrast
from ..model.theme import FIELDS, PRESETS, SECTIONS, Field, Theme, ThemeError
from .banner import INFORMATION, POSITIVE, Banner
from .editors import editor_for
from .labels import FIELD_LABELS, PRESET_TITLES, PREVIEW_ONLY_SECTIONS, SECTION_ICONS, SECTION_TITLES
from .library_view import Entry, LibraryView
from .preview import PreviewWidget

translate = QCoreApplication.translate

MIN_TEXT_CONTRAST = 4.5
MERGE_SECONDS = 1.0


def state_titles() -> dict[str, str]:
    return {
        engine.NEW: translate("ui", "will be created"),
        engine.CHANGED: translate("ui", "will be updated"),
        engine.UNCHANGED: translate("ui", "already up to date"),
        engine.FOREIGN: translate("ui", "exists and was not made by this app"),
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
                "settings back to how they were just before that apply.",
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
        self.plan = engine.build_plan(self.theme)
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self.refresh_timer = QTimer(self, singleShot=True, interval=30)
        self.refresh_timer.timeout.connect(self.refresh)

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
        self.apply_button.clicked.connect(self.apply_theme)
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
        if section in PREVIEW_ONLY_SECTIONS:
            note = QLabel(
                translate(
                    "ui",
                    "These values are saved in the theme and shown in the preview. "
                    "This version does not apply them to the desktop yet.",
                )
            )
            note.setWordWrap(True)
            note.setEnabled(False)
            layout.addWidget(note)
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
            action(translate("ui", "&Apply to desktop"), self.apply_theme, "Ctrl+Return", "dialog-ok-apply")
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
        """Tell the optional fields which value they follow while unset."""
        for field in FIELDS:
            if field.inherits:
                self.editors[field.id].set_inherited(self.theme.get(*field.inherits))

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
                item.setData(Qt.ItemDataRole.UserRole, status)
        self.files_list.blockSignals(False)
        self.files_list.setCurrentRow(min(selected, self.files_list.count() - 1))
        self._show_file(self.files_list.currentRow())
        self.files_info.setText(
            translate(
                "ui",
                "Apply writes these files and then runs: {commands}. Nothing else on the system is changed.",
            ).format(commands=", ".join(commands))
            if commands
            else ""
        )

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
        self.apply_button.setEnabled(not self.plan.blocking)
        self.undo_apply_button.setEnabled(snapshots.latest() is not None)
        self._update_title()

    def _show_file(self, row: int) -> None:
        item = self.files_list.item(row)
        self.file_content.setPlainText(item.data(Qt.ItemDataRole.UserRole).file.content if item else "")

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
        self._load_into_window(theme, path)
        QSettings().setValue("last_file", str(path))
        return True

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

    def _open_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_file_folder(self) -> None:
        item = self.files_list.currentItem()
        if item is not None:
            self._open_folder(item.data(Qt.ItemDataRole.UserRole).file.path.parent)

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

    def use_entry(self, entry: Entry) -> None:
        """Switch the desktop to a theme from the Themes tab."""
        if entry.is_saved_theme:
            self._apply(entry.theme)
            return
        if entry.scheme_id == self.library.active:
            self.banner.show_message(
                INFORMATION, translate("ui", "The desktop already uses {name}.").format(name=entry.title)
            )
            return
        nothing_changed = translate("ui", "The desktop could not be switched. Nothing was changed.")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            engine.switch_color_scheme(entry.scheme_id, entry.title, self.runner)
        except engine.ApplyBlocked as error:
            self._show_problems(nothing_changed, error.problems)
            return
        except ApplyError as error:
            self._show_problems(nothing_changed, [error.message])
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.refresh()
            self.reload_library()
        self.banner.show_message(
            POSITIVE,
            translate("ui", "The desktop now uses {name}. Undo last apply takes you back.").format(
                name=entry.title
            ),
            20,
        )

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

    def _apply(self, theme: Theme) -> None:
        nothing_changed = translate("ui", "The theme cannot be applied. Nothing was changed.")
        plan = engine.build_plan(theme, self.runner)
        if plan.blocking:
            self._show_problems(nothing_changed, plan.blocking)
            return
        if engine.is_current(plan, self.runner):
            self.banner.show_message(
                INFORMATION,
                translate(
                    "ui",
                    "The desktop already uses {name} exactly as it is here, so nothing changed. "
                    "Change a color and apply again.",
                ).format(name=theme.name)
                + self._not_applied_note(theme),
            )
            return
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
                return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = engine.apply(theme, self.runner, replace_foreign=True)
        except engine.ApplyBlocked as error:
            self._show_problems(nothing_changed, error.problems)
            return
        except ApplyError as error:
            self._show_problems(
                translate("ui", "The apply failed. Everything was put back as it was."), [error.message]
            )
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.refresh()
            self.reload_library()
        message = translate("ui", "Applied {name} to the desktop. Undo last apply takes you back.").format(
            name=theme.name
        )
        warnings = "".join(f" {warning}" for warning in result.plan.warnings)
        self.banner.show_message(POSITIVE, message + warnings + self._not_applied_note(theme), 20)

    def _not_applied_note(self, theme: Theme) -> str:
        """Said when the theme has values that this version cannot put on the desktop."""
        if all(theme.get(*f.id) == f.default for f in FIELDS if f.section in PREVIEW_ONLY_SECTIONS):
            return ""
        return " " + translate(
            "ui",
            "Only the colors were applied: this version shows shapes, shadows and panel settings "
            "in the preview but cannot put them on the desktop yet.",
        )

    def _restore(self, snapshot, consume: bool) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            failures = engine.restore(snapshot, self.runner, consume=consume)
        except OSError as error:
            failures = [str(error)]
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh()
        self.reload_library()
        if failures:
            self._show_problems(translate("ui", "Some things could not be put back."), failures)
        else:
            self.banner.show_message(
                POSITIVE,
                translate("ui", "The desktop is back to how it was at {time}.").format(
                    time=f"{snapshot.created_at:%H:%M:%S}"
                ),
                20,
            )

    def undo_last_apply(self) -> None:
        latest = snapshots.latest()
        if latest is not None:
            self._restore(latest, consume=True)

    def show_snapshots(self) -> None:
        dialog = SnapshotDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.chosen is not None:
            self._restore(dialog.chosen, consume=False)

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
