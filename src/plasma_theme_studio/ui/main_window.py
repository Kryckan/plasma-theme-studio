# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The editor window: a side bar of pages, the page shown, and the permanent Desktop bar.

The window owns the theme in the editor, the undo stack, the plan and everything that touches the
desktop (apply, switch, undo, snapshots). The pages (`ui/pages`) only show the theme and call
`edit` or `edit_many`; see `ui/pages/base.py` for what a page can rely on.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QEventLoop,
    QObject,
    QRunnable,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
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
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_DIR, APP_NAME, __version__, archive, globaltheme, library, paths
from ..apply import engine
from ..apply import snapshot as snapshots
from ..apply.runner import SystemRunner
from ..apply.status import BLOCKED, CHANGE, LEAVE
from ..generators import ApplyError, artwork, plasmastyle
from ..generators.colorscheme import current_scheme
from ..model.color import contrast
from ..model.theme import ARTWORK_KEYS, FIELD_BY_ID, FIELDS, PRESETS, SECTIONS, Field, Theme, ThemeError
from ..pickers.loader import ThumbnailLoader
from . import pages
from .banner import INFORMATION, POSITIVE, Banner
from .files_dialog import FilesDialog
from .labels import FIELD_LABELS, PRESET_TITLES, SECTION_TITLES
from .library_view import Entry
from .variant_view import VariantSwitch
from .widgets import CHANGED, OFF, DesktopBar, InlineNote, NavList

translate = QCoreApplication.translate

MIN_TEXT_CONTRAST = 4.5
MERGE_SECONDS = 1.0
CONTINUOUS_KINDS = ("color", "int", "float", "str")  # what a person drags or types
STATUS_DELAY = 200  # milliseconds after the last edit before the parts are compared with the desktop
SIDEBAR_WIDTH = 236
NOTICE_LINES = 3  # problems listed in the strip above the page; the tooltip has them all
DEFAULT_PAGE = "overview"


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
    """One edit of one field. Quick successive edits of a continuous control (a slider, a
    spin box, a color being dragged, typing) become one step; a click on a card, a switch
    or a choice is always a step of its own."""

    def __init__(self, window: MainWindow, field: Field, value):
        super().__init__(str(FIELD_LABELS[field.id]))
        self.window, self.field = window, field
        self.old, self.new = window.theme.get(*field.id), value
        self.time = time.monotonic()
        # A color belongs to the variant that was shown when it was edited, whatever is shown on undo.
        self.variant = window.theme.shown_variant if field.section == "colors" else None

    def _in_variant(self) -> None:
        theme = self.window.theme
        if self.variant and theme.has_both and theme.shown_variant != self.variant:
            self.window.show_variant(self.variant)

    def id(self) -> int:
        return FIELDS.index(self.field) + 1

    def mergeWith(self, other) -> bool:
        if (
            other.field is not self.field
            or other.variant != self.variant
            or other.time - self.time > MERGE_SECONDS
        ):
            return False
        if self.field.kind not in CONTINUOUS_KINDS or (self.field.kind == "str" and self.field.form):
            return False
        self.new, self.time = other.new, other.time
        return True

    def redo(self) -> None:
        self._in_variant()
        self.window.store(self.field, self.new)

    def undo(self) -> None:
        self._in_variant()
        self.window.store(self.field, self.old)


class ReplaceThemeCommand(QUndoCommand):
    """The editor takes another theme; undo brings the earlier one back (with its file)."""

    def __init__(self, window: MainWindow, text: str, theme: Theme, path: Path | None):
        super().__init__(text)
        self.window = window
        self.old, self.old_path = window.theme, window.path
        self.new, self.new_path = theme, path

    def redo(self) -> None:
        self.window.show_theme(self.new, self.new_path)

    def undo(self) -> None:
        self.window.show_theme(self.old, self.old_path)


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


class _StatusAnswer(QObject):
    """Carries the answer of a status job from the worker thread to the window (a queued signal)."""

    done = Signal(int, object)


class _StatusJob(QRunnable):
    """`engine.parts_status` on a copy of the theme, off the GUI thread. The runner is used from the
    worker, so it must be safe there: SystemRunner is plain subprocess calls, FakeRunner plain Python."""

    def __init__(self, generation: int, theme: Theme, runner, answer: _StatusAnswer):
        super().__init__()
        self.generation, self.theme, self.runner, self.answer = generation, theme, runner, answer

    def run(self) -> None:
        try:
            result = engine.parts_status(self.theme, self.runner)
        except Exception:  # noqa: BLE001 - reading the desktop must never break the window
            result = []
        try:
            self.answer.done.emit(self.generation, result)
        except RuntimeError:  # the window is gone
            pass


class _WorkAnswer(QObject):
    """Carries the end of a `_Work` (and its progress) from the worker thread to the window."""

    done = Signal(object, object)  # the result, and the exception that ended it instead (or None)
    progress = Signal(int, int)


class _Work(QRunnable):
    """Runs `work(progress)` off the GUI thread. The exception it ends with travels to the caller."""

    def __init__(self, work: Callable, answer: _WorkAnswer):
        super().__init__()
        self.work, self.answer = work, answer

    def run(self) -> None:
        result = error = None
        try:
            result = self.work(self.answer.progress.emit)
        except BaseException as caught:  # noqa: BLE001 - handed on to the caller, who decides
            error = caught
        try:
            self.answer.done.emit(result, error)
        except RuntimeError:  # the window is gone
            pass


class MainWindow(QMainWindow):
    discard_on_close = False  # set only by `close_without_asking`
    _away_running = 0  # how many `_away` jobs are running

    def __init__(self, runner=None):
        super().__init__()
        self.runner = runner or SystemRunner()
        self.theme = Theme.from_preset("breeze-light")
        self.path: Path | None = None
        self.editors: dict[tuple[str, str], QWidget] = {}
        self.notes: dict[str, InlineNote] = {}
        self.pages: dict[str, pages.base.Page] = {}
        self.statuses: list = []
        self._active = ""
        self.plan = engine.build_plan(self.theme)
        # Switches made on the Themes page that can still be undone: snapshot id ->
        # (theme and file the editor held before, the file the next start would
        # have opened, theme the editor holds since).
        self.switches: dict[str, tuple[Theme, Path | None, str, Theme]] = {}
        self.loader = ThumbnailLoader(self)
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self.refresh_timer = QTimer(self, singleShot=True, interval=30)
        self.refresh_timer.timeout.connect(self.refresh)
        self.status_timer = QTimer(self, singleShot=True, interval=STATUS_DELAY)
        self.status_timer.timeout.connect(self.update_status)
        self.status_pool = QThreadPool(self)
        self.status_pool.setMaxThreadCount(1)
        self.status_answer = _StatusAnswer(self)
        self.status_answer.done.connect(self._status_ready, Qt.ConnectionType.QueuedConnection)
        self.status_generation = 0  # the newest job; an older answer is dropped
        self.status_pending = False
        self.entry_handlers: dict[type, Callable] = {}  # a card class -> what applying one does
        self.nothing_to_apply = False  # the last answer said an apply would change nothing
        # What the status said for a theme (by `fingerprint`) since the desktop last changed: an edit that
        # brings the theme back to one we know needs no new answer, so Apply does not flash on.
        self.known_nothing: dict[str, bool] = {}
        self.fingerprint = ""

        self._build_central()
        self._build_actions()
        self.resize(1280, 800)
        settings = QSettings()
        geometry = settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self._update_title()
        start = str(settings.value("window/page", DEFAULT_PAGE) or DEFAULT_PAGE)
        self.show_page(start if start in pages.SPECS else DEFAULT_PAGE)
        self.refresh()
        QTimer.singleShot(0, self.update_status)  # after the first paint

    # ---- construction ------------------------------------------------

    def _build_central(self) -> None:
        self.files_dialog = FilesDialog(self)
        self.nav = NavList()
        self.nav.setAccessibleName(translate("ui", "Pages"))
        for caption, keys in pages.GROUPS:
            if caption:
                self.nav.add_group(str(caption))
            for key in keys:
                spec = pages.SPECS[key]
                self.nav.add_page(key, str(spec.title), spec.icon, "", spec.fallback)
        self.nav.current_changed.connect(self._page_changed)

        self.theme_name = QLabel()
        self.theme_name.setTextFormat(Qt.TextFormat.PlainText)
        font = self.theme_name.font()
        font.setBold(True)
        self.theme_name.setFont(font)
        self.theme_state = QLabel()
        self.theme_state.setTextFormat(Qt.TextFormat.PlainText)
        self.theme_state.setForegroundRole(self.theme_state.palette().ColorRole.PlaceholderText)
        self.theme_menu = QToolButton()
        self.theme_menu.setIcon(QIcon.fromTheme("application-menu"))
        self.theme_menu.setAutoRaise(True)
        self.theme_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.theme_menu.setToolTip(translate("ui", "Theme menu"))
        self.theme_menu.setAccessibleName(translate("ui", "Theme menu"))
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(self.theme_name)
        names.addWidget(self.theme_state)
        # The variant the editor shows; only there while the theme has both.
        self.variant_switch = VariantSwitch()
        self.variant_switch.chosen.connect(self.show_variant)
        self.variant_switch.hide()
        block = QHBoxLayout()
        block.setContentsMargins(12, 8, 4, 4)
        block.addLayout(names, 1)
        block.addWidget(self.theme_menu)
        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 4, 0, 0)
        side.setSpacing(0)
        side.addLayout(block)
        switch_row = QHBoxLayout()
        switch_row.setContentsMargins(12, 0, 8, 6)
        switch_row.addWidget(self.variant_switch)
        switch_row.addStretch(1)
        side.addLayout(switch_row)
        side.addWidget(self.nav, 1)

        self.stack = QStackedWidget()
        self.banner = Banner()
        self.notice = InlineNote("", "warning")
        self.notice.hide()
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.banner)
        right.addWidget(self.notice)
        right.addWidget(self.stack, 1)

        self.desktop_bar = DesktopBar()
        self.apply_button = self.desktop_bar.apply_button
        self.undo_apply_button = self.desktop_bar.undo_button
        self.snapshots_button = self.desktop_bar.snapshots_button
        self.apply_button.clicked.connect(self.apply_shown)
        self.undo_apply_button.clicked.connect(self.undo_last_apply)
        self.snapshots_button.clicked.connect(self.show_snapshots)
        self.desktop_bar.files_button.clicked.connect(self.show_files)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)
        columns.addWidget(sidebar)
        columns.addLayout(right, 1)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(columns, 1)
        layout.addWidget(self.desktop_bar)
        self.setCentralWidget(central)

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
                lambda: self.open_folder(paths.themes_dir()),
                icon="document-open-folder",
            )
        )
        file_menu.addAction(
            action(
                translate("ui", "Show &color schemes folder"),
                lambda: self.open_folder(paths.color_schemes_dir()),
                icon="document-open-folder",
            )
        )
        file_menu.addSeparator()
        file_menu.addAction(
            action(translate("ui", "&Quit"), self.close, QKeySequence.StandardKey.Quit, "application-exit")
        )
        self.theme_menu.setMenu(file_menu)

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
            action(translate("ui", "&Apply to Desktop"), self.apply_shown, "Ctrl+Return", "dialog-ok-apply")
        )
        desktop_menu.addAction(action(translate("ui", "&Undo last apply"), self.undo_last_apply))
        desktop_menu.addAction(
            action(translate("ui", "&Snapshots…"), self.show_snapshots, icon="view-history")
        )
        desktop_menu.addAction(action(translate("ui", "Show &files…"), self.show_files, icon="document-open"))

        help_menu = self.menuBar().addMenu(translate("ui", "&Help"))
        help_menu.addAction(
            action(translate("ui", "&About {app}").format(app=APP_NAME), self.about, icon="help-about")
        )

    # ---- pages -------------------------------------------------------

    def page(self, key: str):
        """The page `key`, made (not built) on the first call."""
        if key not in self.pages:
            page = pages.create(key, self)
            self.pages[key] = page
            self.stack.addWidget(page)
        return self.pages[key]

    @property
    def current_key(self) -> str:
        return self.nav.current_key()

    def show_page(self, key: str) -> None:
        """Go to a page. Nothing is edited by going there."""
        if self.nav.current_key() == key:
            self._page_changed(key)
        else:
            self.nav.set_current(key)

    def _page_changed(self, key: str) -> None:
        if not key:
            return
        for page in self.pages.values():
            if page.isVisibleTo(self.stack) and page is not self.pages.get(key):
                page.leave()
        page = self.page(key)
        self.stack.setCurrentWidget(page)
        page.show_page()
        self.update_apply_button()
        QSettings().setValue("window/page", key)

    # Where the tests and other code look for the pages' main widgets. Each makes the page.
    @property
    def library(self):
        page = self.page("themes")
        page.ensure_built()
        return page.library

    @property
    def preview(self):
        page = self.page("colors")
        page.ensure_built()
        return page.preview

    @property
    def style_preview(self):
        page = self.page("app_style")
        page.ensure_built()
        return page.style_preview

    def build_pages(self) -> None:
        """Make and fill every page now (they are otherwise built when first shown)."""
        for key in pages.SPECS:
            self.page(key).show_page()

    def show_files(self) -> None:
        self.files_dialog.fill(self.plan, self.apply_summary())
        self.files_dialog.show()
        self.files_dialog.raise_()

    # ---- editing -----------------------------------------------------

    def edit(self, field: Field, value) -> None:
        """Called when the user changes a control."""
        if value == self.theme.get(*field.id):
            return
        try:
            self.theme.copy().set(field.section, field.key, value)
        except ThemeError as error:
            self._reject(field, error)
            return
        self.undo_stack.push(SetValueCommand(self, field, value))

    def edit_many(self, text: str, values: dict) -> None:
        """Change several fields as one step of the undo stack. `values` maps a Field, or its
        (section, key), to the new value. Nothing changes when one of the values is not allowed."""
        changes = []
        trial = self.theme.copy()
        for field, value in values.items():
            field = field if isinstance(field, Field) else FIELD_BY_ID[tuple(field)]
            try:
                trial.set(field.section, field.key, value)
            except ThemeError as error:
                self._reject(field, error)
                return
            if value != self.theme.get(*field.id):
                changes.append((field, value))
        if not changes:
            return
        self.undo_stack.beginMacro(text)
        for field, value in changes:
            self.undo_stack.push(SetValueCommand(self, field, value))
        self.undo_stack.endMacro()

    def _reject(self, field: Field, error: ThemeError) -> None:
        control = self.editors.get(field.id)
        if control is not None:
            control.set_value(self.theme.get(*field.id))
        self.statusBar().showMessage(str(error.problems[0]), 6000)

    def store(self, field: Field, value) -> None:
        self.theme.set(field.section, field.key, value)
        control = self.editors.get(field.id)
        if control is not None:
            control.set_value(self.theme.get(*field.id))
        self.sync_editors()
        if self.known_nothing:  # Apply follows the edit at once, not after the refresh below
            self.nothing_to_apply = self.known_nothing.get(self._fingerprint(), False)
            self.update_apply_button()
        self.refresh_timer.start()

    def sync_editors(self) -> None:
        """Tell the optional fields which value they follow while unset, and turn off
        the values of a part that is left as it is."""
        for field in FIELDS:
            if field.inherits and field.id in self.editors:
                self.editors[field.id].set_inherited(self.theme.resolved(*field.inherits))
        for field_id, gate in GATED.items():
            editor = self.editors.get(field_id)
            if editor is None:
                continue
            on = self.theme.get(*gate) not in ("unchanged", "installed")
            editor.setEnabled(on)
            editor.setToolTip(
                ""
                if on
                else translate("ui", "Used when “{setting}” is not “Leave as it is”.").format(
                    setting=str(FIELD_LABELS[gate])
                )
            )

    def show_variant(self, variant: str) -> None:
        """Make the editor show `variant` (a theme with both): the page, the switches and every preview
        follow it. Not a step of the undo stack."""
        if not self.theme.has_both or variant == self.theme.shown_variant:
            self._update_variant_switch()
            return
        self.theme.show(variant)
        for field_id, control in self.editors.items():
            control.set_value(self.theme.get(*field_id))
        self.sync_editors()
        self.refresh()

    def add_variant(self) -> None:
        """Make the missing variant by the automatic conversion and show it, as one undo step."""
        if self.theme.has_both:
            return
        new = self.theme.copy()
        made = new.add_variant()
        new.show(made)
        text = (
            translate("ui", "Add the dark variant")
            if made == "dark"
            else translate("ui", "Add the light variant")
        )
        self.replace_theme(text, new, self.path)

    def remove_variant(self, variant: str | None = None) -> None:
        """Remove `variant` (the one that is shown by default), as one undo step."""
        if not self.theme.has_both:
            return
        variant = variant or self.theme.shown_variant
        new = self.theme.copy()
        new.remove_variant(variant)
        text = (
            translate("ui", "Remove the dark variant")
            if variant == "dark"
            else translate("ui", "Remove the light variant")
        )
        self.replace_theme(text, new, self.path)

    def _update_variant_switch(self) -> None:
        both = self.theme.has_both
        self.variant_switch.setVisible(both)
        if both:
            self.variant_switch.set_variant(self.theme.shown_variant)

    def replace_theme(self, text: str, theme: Theme, path: Path | None = None) -> None:
        """Make `theme` the one the editor holds, as one step of the undo stack: Undo brings the
        theme that was in the editor back."""
        self.undo_stack.push(ReplaceThemeCommand(self, text, theme, path))

    def show_theme(self, theme: Theme, path: Path | None) -> None:
        """Put `theme` into the editor and every control, keeping the undo stack."""
        self.theme, self.path = theme, path
        theme.base_dir = path.parent if path else None
        for field_id, control in self.editors.items():
            control.set_value(theme.get(*field_id))
        self.sync_editors()
        self.refresh()
        self._update_title()

    def _load_into_window(self, theme: Theme, path: Path | None) -> None:
        self.theme, self.path = theme, path
        theme.base_dir = path.parent if path else None
        self.undo_stack.clear()
        for field_id, control in self.editors.items():
            control.set_value(theme.get(*field_id))
        self.sync_editors()
        self.refresh()
        self._update_title()

    def refresh(self) -> None:
        """Bring the page shown, the messages and the files in line with the theme."""
        self.plan = engine.build_plan(self.theme)
        # An edit may change something again, so Apply is on until the status says otherwise: a
        # button that stays off for a moment after a real edit is the worse fault. When this very theme
        # was answered before (an edit taken back, an undo of one), that answer is used at once.
        self.fingerprint = self._fingerprint()
        self.nothing_to_apply = self.known_nothing.get(self.fingerprint, False)
        self.status_generation += 1  # an answer for the theme before this edit is out of date
        for page in self.pages.values():
            page.stale = True
            if page.built:
                page.refresh_notes()  # cheap, and a page that is not shown must not say old things
        key = self.nav.current_key()
        if key:
            self.page(key).show_page()
        if self.files_dialog.isVisible():
            self.files_dialog.fill(self.plan, self.apply_summary())
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
        shown = notices[:NOTICE_LINES]
        if len(notices) > len(shown):
            shown.append(translate("ui", "…and {count} more.").format(count=len(notices) - len(shown)))
        self.notice.set_text("\n".join(shown))
        self.notice.setToolTip("\n".join(notices) if len(notices) > len(shown) else "")
        self.notice.setVisible(bool(notices))
        self.update_apply_button()
        self.undo_apply_button.setEnabled(snapshots.latest() is not None)
        self._update_title()
        self._update_variant_switch()
        self.status_timer.start()

    def _fingerprint(self) -> str:
        """What the comparison with the desktop depends on: the theme and the pictures it uses. Cheap
        enough to take on every edit."""
        digest = hashlib.sha256(self.theme.to_toml().encode())
        for frame, data in sorted(self.theme.pending_artwork.items()):
            digest.update(frame.encode() + b"\0" + data)
        for frame in ARTWORK_KEYS:
            _name, path = artwork.resolve(self.theme, frame)
            try:
                info = path.stat() if path is not None else None
            except OSError:
                info = None
            digest.update(repr((frame, info and (info.st_mtime_ns, info.st_size))).encode())
        return digest.hexdigest()

    def update_status(self) -> None:
        """Start the comparison of every part with the desktop in a worker. Only the newest answer is
        used (`_status_ready`); typing and dragging never wait for it."""
        self.status_timer.stop()
        self.status_generation += 1
        self.status_pending = True
        self.status_pool.start(
            _StatusJob(self.status_generation, self.theme.copy(), self.runner, self.status_answer)
        )

    def settle(self) -> None:
        """Wait until the status of the newest theme is known and shown (for tests, and for a caller that
        needs the answer now)."""
        for page in self.pages.values():
            page.wait_desktop()
        while self.status_timer.isActive() or self.status_pending:
            if self.status_timer.isActive():
                self.update_status()
            self.status_pool.waitForDone()
            QCoreApplication.processEvents()
            QCoreApplication.sendPostedEvents(None, 0)
            if self.status_pending and not self.status_timer.isActive():
                self.update_status()  # the answer was for a theme that has changed since: ask again

    def _status_ready(self, generation: int, statuses) -> None:
        if generation != self.status_generation:
            return
        self.status_pending = False
        self.statuses = statuses
        self._show_status()

    def _show_status(self) -> None:
        """The dots of the side bar, the Overview, the sentence of the Desktop bar and the apply button."""
        by_key = {part.key: part.state for part in self.statuses}
        for spec in pages.PAGES:
            page = self.pages.get(spec.key)
            parts = page.parts if page is not None else pages.parts_of(spec.key)
            states = [by_key[key] for key in parts if key in by_key]
            if CHANGE in states or BLOCKED in states:
                self.nav.set_state(spec.key, CHANGED)
            elif states and all(state == LEAVE for state in states):
                self.nav.set_state(spec.key, OFF)
            else:
                self.nav.set_state(spec.key, "")
        changing = sum(1 for part in self.statuses if part.state == CHANGE)
        blocked = [part for part in self.statuses if part.state == BLOCKED]
        if not self.statuses:
            text = ""
        elif blocked:
            text = translate("ui", "{part} cannot be applied: {problem}").format(
                part=blocked[0].title, problem=blocked[0].theme
            )
        elif changing == 0:
            text = translate("ui", "Nothing will change when you apply.")
        elif changing == 1:
            text = translate("ui", "One part will change when you apply.")
        else:
            text = translate("ui", "{count} parts will change when you apply.").format(count=changing)
        self.desktop_bar.set_status(text, changing > 0 or bool(blocked))
        self.nothing_to_apply = bool(self.statuses) and changing == 0 and not blocked
        if self.statuses:
            if len(self.known_nothing) >= 64:
                self.known_nothing.clear()
            self.known_nothing[self.fingerprint] = self.nothing_to_apply
        self.update_apply_button()
        overview = self.pages.get("overview")
        if overview is not None:
            overview.fill(self.statuses)

    def apply_summary(self) -> str:
        """Everything an apply does to the system, so that nothing comes as a surprise."""
        commands = [target.reload_command for target in self.plan.targets if target.reload_command]
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

    def update_apply_button(self) -> None:
        """Enable the apply button and say in its tooltip which theme it puts on the desktop."""
        page = self.pages.get(self.nav.current_key())
        if page is not None and page.acts_on_selection:
            entry = self.library.current()
            name, enabled = (entry.title if entry else ""), entry is not None
            tip = "" if entry else translate("ui", "Select a theme first.")
        else:
            name, enabled, tip = self.theme.name, not self.plan.blocking, ""
            if enabled and self.nothing_to_apply:
                name, enabled = "", False
                tip = translate(
                    "ui", "Nothing would change: the desktop already has everything this theme sets."
                )
        if name and enabled:
            tip = translate("ui", "Apply “{name}” to the desktop").format(name=name)
        self.apply_button.setEnabled(enabled)
        self.apply_button.setToolTip(tip)

    def _update_title(self) -> None:
        name = self.path.name if self.path else translate("ui", "Unsaved theme")
        self.setWindowTitle(f"{self.theme.name or name} ({name})[*]")
        self.setWindowModified(not self.undo_stack.isClean())
        self.theme_name.setText(self.theme.name or name)
        self.theme_state.setText(
            translate("ui", "Unsaved changes") if not self.undo_stack.isClean() else name
        )

    # ---- files -------------------------------------------------------

    def _discard_ok(self, text: str | None = None) -> bool:
        """True when it is fine to go on: nothing is unsaved, or the person saved or discarded it.
        `text` says what is about to happen to the unsaved changes."""
        if self.undo_stack.isClean():
            return True
        answer = QMessageBox.warning(
            self,
            translate("ui", "Unsaved changes"),
            text or translate("ui", "The theme has changes that are not saved."),
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
            # Reading an archive draws its pictures in a child process: the window does not wait for it
            theme = self._away(
                lambda _progress: archive.import_theme(path), translate("ui", "Reading the theme…")
            )
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
            theme = self.theme
            written = self._away(
                lambda _progress: globaltheme.export_global_theme(theme, folder),
                translate("ui", "Checking the artwork…"),
            )
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

    def open_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def stop_page_workers(self) -> None:
        for page in self.pages.values():
            stop = getattr(page, "stop_workers", None)
            if stop is not None:
                stop()

    def hideEvent(self, event) -> None:
        self.stop_page_workers()
        super().hideEvent(event)

    def close_without_asking(self) -> bool:
        """Close the window and let go of unsaved changes without the "Unsaved changes" question, which
        is modal and so blocks a window nobody can click (the offscreen helpers and the tests). A person
        at the desktop never goes through here: the close button and Quit still ask."""
        self.discard_on_close = True
        try:
            return self.close()
        finally:
            self.discard_on_close = False

    def closeEvent(self, event) -> None:
        if self._away_running:  # a worker is putting files back: the window stays until it is done
            event.ignore()
            return
        if not self.discard_on_close and not self._discard_ok():
            event.ignore()
            return
        QSettings().setValue("window/geometry", self.saveGeometry())
        self.loader.shutdown()
        self.stop_page_workers()
        self.status_generation += 1  # nobody listens to a job that is still running
        self.status_pool.waitForDone(3000)
        event.accept()

    # ---- desktop -----------------------------------------------------

    def _show_problems(self, title: str, problems) -> None:
        box = QMessageBox(QMessageBox.Icon.Warning, APP_NAME, title, parent=self)
        box.setInformativeText("\n".join(f"• {problem}" for problem in problems))
        box.exec()

    def read_scheme(self) -> str:
        """The color scheme the desktop uses now, read without touching the window: for a worker."""
        if self.runner.which("kreadconfig6"):
            return current_scheme(self.runner)
        return self._active

    def active_scheme(self) -> str:
        """The color scheme the desktop uses now (a read on the calling thread: for an action the
        person asked for; the pages read it in a worker with `read_scheme`)."""
        self._active = self.read_scheme()
        return self._active

    def reload_library(self) -> None:
        """The desktop changed (an apply, an undo, a save): read it again where it is shown."""
        self.known_nothing.clear()  # the desktop is not what the answers were about
        self.status_generation += 1  # an answer read before the desktop changed is out of date
        for page in self.pages.values():
            page.desktop_stale = True
        themes = self.pages.get("themes")
        if themes is not None and themes.built:
            themes.reload()
        key = self.nav.current_key()
        if key:
            self.page(key).show_page()
        self.status_timer.start()

    def apply_shown(self) -> None:
        """Apply what the user is looking at: the theme selected on the Themes
        page, or on the other pages the theme in the editor."""
        page = self.pages.get(self.nav.current_key())
        if page is None or not page.acts_on_selection:
            self.apply_theme()
            return
        entry = self.library.current()
        if entry is not None:
            self.use_entry(entry)

    def use_entry(self, entry: Entry) -> None:
        """Switch the desktop to a theme from the Themes page.

        The editor takes the theme over, so that what is changed and applied
        next changes this theme and does not bring back the one before it."""
        handler = self.entry_handlers.get(type(entry))
        if handler is not None:  # a kind of card that a page takes care of itself
            handler(entry)
            return
        if self._in_editor(entry):
            self._apply(self.theme, from_library=True)  # with its unsaved edits
            return
        if not self._discard_ok(
            translate(
                "ui",
                "Applying “{name}” replaces the theme in the editor, and its changes are not saved. "
                "Save them first, or discard them and apply?",
            ).format(name=entry.title)
        ):
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
        """Whether an entry of the Themes page is the theme the editor holds: its
        file, or the color scheme that an apply wrote from it."""
        if entry.is_saved_theme:
            return entry.path == self.path
        from ..generators.variants import of_variant

        own = {of_variant(self.theme, variant).scheme_slug for variant in self.theme.variants}
        return entry.scheme.made_here and entry.scheme_id in own

    def _switch_scheme(self, entry: Entry) -> snapshots.Snapshot | bool:
        """Make an installed color scheme the one in use. Returns the snapshot,
        True when the desktop had the scheme already, False when it failed."""
        active = self.active_scheme()
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
            self.known_nothing.clear()  # the desktop changed: what the status said is out of date
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
        """Open a theme from the Themes page in the editor."""
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
                    "Change it on the pages, then choose Apply to Desktop.",
                ).format(name=entry.title),
            )
        self.show_page("overview")

    def apply_theme(self) -> None:
        self._apply(self.theme)

    def _apply(self, theme: Theme, from_library: bool = False) -> snapshots.Snapshot | bool:
        """Put a theme on the desktop. Returns the snapshot of the apply, True when
        the desktop had the theme already, False when the desktop is not on it."""
        nothing_changed = translate("ui", "The theme cannot be applied. Nothing was changed.")
        if any(plasmastyle.own_artwork(theme, frame).usable for frame in ARTWORK_KEYS):
            # own pictures are drawn once by the draw child first, so that one it cannot draw is left out
            self._away(
                lambda progress: plasmastyle.vet_artwork(theme), translate("ui", "Checking the artwork…")
            )
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
        try:
            # The undo waits for the desktop's daemons: it runs in a worker, the window keeps painting
            reached, failures = self._away(
                lambda progress: engine.restore_to(snapshot, self.runner, progress),
                translate("ui", "Putting the desktop back…"),
                translate("ui", "{done} of {total}"),
            )
        except OSError as error:
            failures = [str(error)]
        editor_went_back = self._undo_switches()
        self.known_nothing.clear()
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

    def _away(self, work: Callable, label: str, steps: str | None = None):
        """Run `work(progress)` in a worker thread and return its result (or raise what it raised), while
        a progress window shows `label`, after a short moment when it is quick. `progress(done, total)`
        may be called by the work; `steps` is its text ("{done} of {total}") shown under the label. The
        window keeps painting but takes no clicks. The caller waits here, so the caller stays simple."""
        answer = _WorkAnswer()
        loop = QEventLoop(self)
        finished: list = []
        dialog = QProgressDialog(label, "", 0, 0, self)
        dialog.setCancelButton(None)
        dialog.setWindowTitle(APP_NAME)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(300)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)  # with a busy range only this arms the timer that shows the window

        def stepped(done: int, total: int) -> None:
            if steps is not None and total > 1:
                dialog.setLabelText(label + "\n" + steps.format(done=done, total=total))

        def ended(result, error) -> None:
            finished.append((result, error))
            loop.quit()

        answer.progress.connect(stepped, Qt.ConnectionType.QueuedConnection)
        answer.done.connect(ended, Qt.ConnectionType.QueuedConnection)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._away_running += 1
        try:
            QThreadPool.globalInstance().start(_Work(work, answer))
            if not finished:
                loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            if not finished:
                # The application was told to quit and ended this loop early: the work is not cut off
                # half way, it is waited for.
                QThreadPool.globalInstance().waitForDone()
                QApplication.processEvents()
        finally:
            self._away_running -= 1
            QApplication.restoreOverrideCursor()
            dialog.reset()
            dialog.deleteLater()
        if not finished:
            raise RuntimeError("the work ended without an answer")
        result, error = finished[0]
        if error is not None:
            raise error
        return result

    def _undo_switches(self) -> bool:
        """After an undo: when a switch made on the Themes page was undone, the
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
