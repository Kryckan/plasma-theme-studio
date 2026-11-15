# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What every page of the window is built from.

A page is one part of the desktop: a header with the page's name, then the controls. Pages are made
the first time they are shown (`build`) and brought up to date only while they are shown (`refresh`);
a page that is hidden while the theme changes is marked `stale` and refreshes when it is shown again.

The window gives a page:

- `window.theme`, the theme in the editor, and `window.plan`, what an apply would write;
- `window.edit(field, value)` and `window.edit_many(text, {field: value})`, the only ways a page
  changes the theme (one undo step each). A page never navigates and never applies;
- `window.runner`, to read what the desktop uses, and `window.loader`, the shared thumbnail loader;
- `window.editors`, the controls by field id, filled by `Page.editor`.

The page kinds:

- `Page`: the header, a scrolling body (`self.content`, a QVBoxLayout) and an InlineNote for every
  section in `note_sections` (what an apply does with its values).
- `ValuePage`: the controls in a column on the left (`build_controls`), a drawn preview on the right.
- `PickerPage`: a grid of cards of what is installed, the part switch "Leave as it is | Set by this
  theme", and under the grid the values that tune the first card, "This theme".
- `TargetPage`: a part that is only written from the theme (GTK, Rofi): a switch, a sample of
  the values and the note.

- `LinkPage`: a part this app does not edit: why, and a button to its page in System Settings.

Room that a picker or target page gives a subclass, without touching this module (each is filled
in `build`, after `super().build()`):

- the actions of the header: `self.header.add_action(button)`, top right beside the title;
- the top row, between the part switch and the grid: `self.add_top_row(widget)`, for example
  `self.add_top_row(self.mode_switch)`;
- below the grid, after the tuning values: `self.add_below(widget)`, for example
  `self.add_below(self.caption("Sample")); self.add_below(sample)`;
- a side preview, beside the grid of a picker or on the right of a target page:
  `self.set_side_preview(widget)` (about 320 px wide; hidden until something is put there).

The whole page below the header scrolls as one: the grid shows all its cards at full height and
only the cards that are scrolled into view ask for a thumbnail. The search field stays above the
scroll (`CardGrid.bar`), so it is always at hand.

A subclass sets `key` (the registry key) and `parts` (the keys of `apply.status.parts_status`
that the nav dot of the page follows), and overrides `subtitle`, `build` and `refresh`.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSize, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ... import pickers
from ...model.theme import FIELD_BY_ID, Field
from ...palette import ROLES
from .. import this_theme
from ..editors import editor_for
from ..labels import FIELD_LABELS
from ..preview import PreviewWidget
from ..widgets import LARGE_SPACING, SPACING, THUMB_SIZE, CardGrid, InlineNote, PageHeader, Segmented

translate = QCoreApplication.translate

LABEL_WIDTH = 168  # the column of labels of a form
TUNING_WIDTH = 640  # the values under a grid of cards
CONTROLS_WIDTH = 432  # the column of controls of a value page
THIS_THEME = "@this-theme"  # the id of the first card of a picker that can generate its part
BREEZE_ADJUSTED = "@breeze"
SIDE_WIDTH = 320  # the side preview of a picker or target page
THIS_THEME_DELAY = 150  # milliseconds after the last edit before the card "This theme" is drawn again


class Page(QWidget):
    key = ""
    parts: tuple[str, ...] = ()
    note_sections: tuple[str, ...] = ()
    scrolling = True  # False for a page whose grid scrolls by itself
    acts_on_selection = False  # Apply puts the selected card on the desktop (the Themes page)

    def __init__(self, window):
        super().__init__()
        from . import title_of

        self.window = window
        self.stale = True
        self.desktop_stale = True
        self.built = False
        self.setAccessibleName(title_of(self.key))
        self.header = PageHeader(title_of(self.key), self.subtitle())
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 0)
        outer.setSpacing(LARGE_SPACING)
        outer.addWidget(self.header)
        body = QWidget()
        if self.scrolling:
            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.scroll.setWidget(body)
            body.setAutoFillBackground(False)
            self.scroll.viewport().setAutoFillBackground(False)
            outer.addWidget(self.scroll, 1)
        else:
            self.scroll = None
            outer.addWidget(body, 1)
        self.content = QVBoxLayout(body)
        self.content.setContentsMargins(0, 0, 0, 16)
        self.content.setSpacing(LARGE_SPACING)
        self.notes_layout = self.content  # where the notes go; a ValuePage moves it to its column

    # ---- for subclasses

    def subtitle(self) -> str:
        return ""

    def build(self) -> None:
        """Make the controls. Called once, before the first refresh."""

    def refresh(self) -> None:
        """Show the theme in the controls. Called when the page is shown and the theme changed."""
        self.refresh_notes()

    def read_desktop(self) -> None:
        """Read what the desktop uses now (the "In use" marks). Called when the page is first shown
        and after an apply or an undo."""

    def leave(self) -> None:
        """The page is no longer shown."""

    # ---- for the window

    def ensure_built(self) -> None:
        if self.built:
            return
        self.built = True
        self.build()
        for section in self.note_sections:
            note = InlineNote("", "information")
            note.hide()
            self.window.notes[section] = note
            self.notes_layout.addWidget(note)
        if self.scrolling and self.notes_layout is self.content:
            self.content.addStretch(1)
        self.window.sync_editors()

    def show_page(self) -> None:
        """The window shows this page now."""
        self.ensure_built()
        if self.desktop_stale:
            self.desktop_stale = False
            self.read_desktop()
        if self.stale:
            self.stale = False
            self.refresh()

    # ---- room for subclasses

    def set_side_preview(self, widget: QWidget, width: int = SIDE_WIDTH) -> None:
        """Put `widget` in the side column (hidden until this is called). Only pages that make one
        (a picker, a target page) have a `side` column."""
        self.side_box.setFixedWidth(width)
        self.side.addWidget(widget)
        self.side_box.show()

    def _side_column(self) -> None:
        self.side_box = QWidget()
        self.side = QVBoxLayout(self.side_box)
        self.side.setContentsMargins(0, 0, 0, 0)
        self.side.setSpacing(SPACING)
        self.side_box.hide()

    # ---- helpers

    @property
    def theme(self):
        return self.window.theme

    def editor(self, section: str, key: str, label: str | None = None) -> QWidget:
        """The control of one theme field, wired to `window.edit` and kept in `window.editors`."""
        field = FIELD_BY_ID[(section, key)]
        title = label or str(FIELD_LABELS[field.id])
        control = editor_for(field)
        control.set_title(title)
        control.set_value(self.theme.get(*field.id))
        control.changed.connect(lambda value, field=field: self.window.edit(field, value))
        self.window.editors[field.id] = control
        return control

    def form(self, *fields: tuple[str, str], label: dict | None = None) -> QFormLayout:
        """A form of the controls of these (section, key) fields, each labelled as the field is."""
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)  # label above the control when narrow
        form.setVerticalSpacing(SPACING)
        form.setHorizontalSpacing(SPACING)
        for section, key in fields:
            text = (label or {}).get((section, key)) or str(FIELD_LABELS[(section, key)])
            name = QLabel(text + translate("ui", ":"))
            name.setMinimumWidth(LABEL_WIDTH)  # one left edge for the controls of every form of a page
            form.addRow(name, self.editor(section, key, text))
        return form

    def form_widget(self, *fields: tuple[str, str]) -> QWidget:
        """`form` in a widget that is not wider than the values need."""
        box = QWidget()
        box.setMaximumWidth(TUNING_WIDTH)
        box.setLayout(self.form(*fields))
        box.layout().setContentsMargins(0, 0, 0, 0)
        return box

    def caption(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label

    def separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setForegroundRole(line.palette().ColorRole.Mid)
        return line

    def refresh_notes(self) -> None:
        """Say what an apply does with the values of this page's sections."""
        plan = self.window.plan
        for section in self.note_sections:
            note = self.window.notes.get(section)
            if note is None:
                continue
            texts = [
                str(text)
                for target in plan.targets
                if section in target.generator.sections
                for text in target.generator.section_notes(plan.theme, section)
            ]
            from ..labels import SECTION_NOTES

            if section in SECTION_NOTES:
                texts = [str(SECTION_NOTES[section]), *texts]
            note.set_text("\n\n".join(texts))
            note.setVisible(bool(texts))


class ValuePage(Page):
    """Controls on the left, the preview on the right.

    A subclass fills `self.controls` in `build_controls` and says in `modes` which parts the preview
    can zoom in on (the first is shown first).
    """

    modes: tuple[str, ...] = ("desktop", "window", "panel", "menu")
    preview_hint = ""

    def build(self) -> None:
        self.preview = PreviewWidget(self.theme)
        left = QWidget()
        left.setMaximumWidth(CONTROLS_WIDTH)
        left.setMinimumWidth(320)
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.controls = QVBoxLayout(left)
        self.controls.setContentsMargins(0, 0, 0, 0)
        self.controls.setSpacing(LARGE_SPACING)
        self.build_controls()
        self.notes_layout = self.controls
        self.controls.addStretch(1)

        titles = {
            "desktop": translate("ui", "Desktop"),
            "window": translate("ui", "Window"),
            "panel": translate("ui", "Panel"),
            "menu": translate("ui", "Menu"),
        }
        self.mode_switch = Segmented(
            [titles[mode] for mode in self.modes], 0, name=translate("ui", "What the preview shows")
        )
        self.mode_switch.changed.connect(lambda index: self.preview.set_mode(self.modes[index]))
        self.preview.set_mode(self.modes[0])
        bar = QHBoxLayout()
        bar.addWidget(self.caption(translate("ui", "Preview")))
        bar.addStretch(1)
        if len(self.modes) > 1:
            bar.addWidget(self.mode_switch)
        hint = QLabel(
            self.preview_hint or translate("ui", "Nothing reaches the desktop until you choose Apply.")
        )
        hint.setWordWrap(True)
        hint.setForegroundRole(hint.palette().ColorRole.PlaceholderText)
        right = self.preview_column = QVBoxLayout()
        right.setSpacing(SPACING)
        right.addLayout(bar)
        right.addWidget(self.preview, 1)
        right.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(LARGE_SPACING + 8)
        row.addWidget(left, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(right, 1)
        self.content.addLayout(row, 1)

    def build_controls(self) -> None:
        """Add the controls to `self.controls`."""

    def refresh(self) -> None:
        self.preview.set_theme(self.theme)
        super().refresh()


class PickerPage(Page):
    """A grid of what is installed, one card selected, and what tunes the card "This theme".

    A subclass names the picker (`kind_key`), where the choice is stored and what the desktop uses now:

    - `id_field`: the field holding the id of the chosen installed thing;
    - `mode_field`: the choice field ("unchanged", "installed", "generated", "breeze") when the part can
      be made from the theme; without it the part is left as it is while `id_field` has no value;
    - `part_key`: the key in `desktopparts.PARTS` that says what the desktop has (for "In use");
    - `tuning`: the (section, key) fields shown under the grid.
    """

    scrolling = True
    kind_key = ""
    id_field: tuple[str, str] = ("", "")
    mode_field: tuple[str, str] | None = None
    part_key = ""
    tuning: tuple[tuple[str, str], ...] = ()
    thumb_size = THUMB_SIZE
    breeze_card = False  # an extra card "Breeze with your changes" (window decorations)
    set_hint = ""

    def build(self) -> None:
        self.kind = pickers.kind(self.kind_key)
        self.items: dict[str, pickers.Item] = {}
        self.colors_seen = None
        self.remembered: str | None = None  # the card that was chosen before "Leave as it is"
        self.header.add_part_switch()
        self.header.set_hint(self.set_hint)
        self.header.part_mode_changed.connect(self._switched)
        self.grid = CardGrid(self.thumb_size, with_search=True, fit=True, name=self.title_text())
        self.grid.selected.connect(self._picked)
        self.grid.thumbnail_requested.connect(self._request)
        self.window.loader.ready.connect(self._thumbnail_ready)
        # the search field stays above the scroll, so it is at hand however far down the grid is
        self.layout().insertWidget(1, self.grid.bar)
        self.top_row = QWidget()
        self.top_row_layout = QHBoxLayout(self.top_row)
        self.top_row_layout.setContentsMargins(0, 0, 0, 0)
        self.top_row_layout.setSpacing(SPACING)
        self.top_row.hide()
        self.content.addWidget(self.top_row)
        self._side_column()
        row = QHBoxLayout()
        row.setSpacing(LARGE_SPACING)
        row.addWidget(self.grid, 1, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.side_box, 0, Qt.AlignmentFlag.AlignTop)
        self.content.addLayout(row)
        if self.tuning:
            self.tuning_box = QWidget()
            self.tuning_box.setMaximumWidth(TUNING_WIDTH)
            box = QVBoxLayout(self.tuning_box)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(SPACING)
            box.addWidget(self.separator())
            box.addWidget(self.caption(self.tuning_title()))
            box.addLayout(self.form(*self.tuning))
            self.content.addWidget(self.tuning_box)
        self.below = QVBoxLayout()
        self.below.setSpacing(SPACING)
        self.content.addLayout(self.below)
        self.this_timer = QTimer(self, singleShot=True, interval=THIS_THEME_DELAY)
        self.this_timer.timeout.connect(self.update_this_theme_cards)
        self.load_items()

    def add_top_row(self, widget: QWidget, stretch: int = 0) -> None:
        """Put `widget` in the row between the part switch and the grid."""
        self.top_row_layout.addWidget(widget, stretch)
        self.top_row.show()

    def add_below(self, widget: QWidget) -> None:
        """Put `widget` below the grid and its tuning values (above the notes)."""
        self.below.addWidget(widget)

    def title_text(self) -> str:
        from . import title_of

        return title_of(self.key)

    def tuning_title(self) -> str:
        return translate("ui", "This theme’s values")

    # ---- the cards

    def generates(self) -> bool:
        return self.mode_field is not None and "generated" in FIELD_BY_ID[self.mode_field].choices

    def load_items(self) -> None:
        self.show_items(self.kind.items() if self.kind is not None else [])

    def show_items(self, found) -> None:
        """Make the cards of what the picker found (a page that reads the list in a worker calls this
        when the list is there, see `pickers_common.LoadsInBackground`)."""
        self.items = {item.id: item for item in found}
        cards = []
        if self.generates():
            cards.append(
                (THIS_THEME, translate("ui", "This theme"), translate("ui", "Generated from this theme"))
            )
        if self.breeze_card:
            cards.append(
                (
                    BREEZE_ADJUSTED,
                    translate("ui", "Breeze with your changes"),
                    translate("ui", "Set by this theme"),
                )
            )
        cards += [(item.id, item.name, item.description) for item in found]
        self.grid.set_items(cards)
        self.grid.set_empty_text(
            translate("ui", "Nothing matches your search.")
            if cards
            else translate("ui", "Nothing of this kind is installed.")
        )
        self.this_timer.start(0)  # the first picture of the generated cards, after the page is shown

    def selection(self):
        """(is the part set by the theme, id of the card that shows it)."""
        if self.mode_field is not None:
            mode = self.theme.part_state(*self.mode_field)
            if mode == "generated":
                return True, THIS_THEME
            if mode == "breeze":
                return True, BREEZE_ADJUSTED
            if mode == "installed":
                return True, self._match(self.theme.get(*self.id_field))
            return False, self._match(self.theme.get(*self.id_field))
        value = self.theme.get(*self.id_field)
        return value is not None, self._match(value)

    def _match(self, value):
        """The id of the installed card a stored value means (ids are compared without case)."""
        if value is None:
            return None
        return next((i for i in self.items if i.casefold() == str(value).casefold()), None)

    def refresh(self) -> None:
        on, chosen = self.selection()
        self.header.set_part_mode(on)
        self.grid.set_selected(chosen if on else None)
        self.grid.set_dimmed(not on)
        if self.tuning:
            self.tuning_box.setEnabled(on)
        self.this_timer.start(THIS_THEME_DELAY)  # drawn again when the edits have stopped
        colors = self.colors()
        if self.kind is not None and self.kind.scheme_dependent and colors != self.colors_seen:
            self.colors_seen = colors
            for card in self.grid.visible_cards():
                self._request(card.item_id)
        super().refresh()

    def colors(self) -> tuple:
        return tuple((key, self.theme.get("colors", key)) for key in pickers_color_roles())

    # ---- what the desktop has

    def current_id(self):
        """What the desktop uses now, as the id of a card, or None."""
        from ... import desktopparts

        try:
            value = desktopparts.PARTS[self.part_key].current(self.window.runner)
        except Exception:
            return None
        if isinstance(value, dict):
            value = value.get("theme")
        return self._match(value) if value else None

    def read_desktop(self) -> None:
        self.grid.set_in_use(self.current_id())

    # ---- thumbnails

    def update_this_theme_cards(self) -> None:
        """Draw the cards "This theme" and "Breeze with your changes" again from the theme."""
        for card in (THIS_THEME, BREEZE_ADJUSTED):
            if self.grid.card(card) is not None:
                self.grid.set_thumbnail(card, self.generated_thumbnail(card))

    def generated_thumbnail(self, card):
        """The picture of one of the generated cards."""
        size, dpr = QSize(self.thumb_size), self.devicePixelRatioF()
        if card == BREEZE_ADJUSTED:
            return this_theme.breeze_thumbnail(self.theme, size, dpr)
        return self.this_theme_thumbnail(size, dpr)

    def this_theme_thumbnail(self, size: QSize, dpr: float) -> QImage:
        """The picture of "This theme": the PART, drawn from the theme (a frame, a panel, widgets, a color
        card; see `ui/this_theme.py`). A page overrides this for a picture of its own, e.g.
        `return my_drawing(self.theme, size, dpr)`."""
        return this_theme.thumbnail(self.kind_key, self.theme, size, dpr)

    def _request(self, item_id) -> None:
        item = self.items.get(item_id)
        if item is None or self.kind is None:
            return
        colors = {key: value for key, value in self.colors()}
        image = self.window.loader.request(
            self.kind, item, QSize(self.thumb_size), self.devicePixelRatioF(), colors
        )
        if image is not None and not image.isNull():
            self.grid.set_thumbnail(item_id, image)
        elif image is not None:
            self.grid.set_no_preview(item_id)

    def _thumbnail_ready(self, kind_key: str, item_id: str, image: QImage) -> None:
        if kind_key != self.kind_key or self.grid.card(item_id) is None:
            return
        if image.isNull():
            self.grid.set_no_preview(item_id)
        else:
            self.grid.set_thumbnail(item_id, image)

    def leave(self) -> None:
        if self.kind is not None:
            self.window.loader.cancel(self.kind_key)
            self.grid.ask_again_for_thumbnails()

    # ---- choosing

    def _picked(self, item_id) -> None:
        if self.mode_field is not None:
            mode = {THIS_THEME: "generated", BREEZE_ADJUSTED: "breeze"}.get(item_id, "installed")
            values = {self.mode_field: mode}
            if mode == "installed":
                values[self.id_field] = item_id
            self.window.edit_many(self.edit_text(), values)
        else:
            self.window.edit(FIELD_BY_ID[self.id_field], item_id)
        self.refresh()  # the card of a click that changed nothing still turns the part on

    def _switched(self, on: bool) -> None:
        if on:
            on_now, chosen = self.selection()
            if self.remembered is not None and self.grid.card(self.remembered) is not None:
                chosen = self.remembered  # what was chosen before "Leave as it is"
            chosen = chosen or self.current_id()
            if chosen is None and self.generates():
                chosen = THIS_THEME
            if chosen is None and self.items:
                chosen = next(iter(self.items))
            if chosen is not None:
                self._picked(chosen)
        else:
            was_on, chosen = self.selection()
            if was_on and chosen is not None:
                self.remembered = chosen
            if self.mode_field is not None:
                self.window.edit(FIELD_BY_ID[self.mode_field], "unchanged")
            else:
                self.window.edit(FIELD_BY_ID[self.id_field], None)
        self.refresh()

    def edit_text(self) -> str:
        return translate("ui", "Choose {part}").format(part=self.title_text())


def pickers_color_roles() -> tuple[str, ...]:
    """The twelve color roles of a theme, as the pickers name them."""
    return ROLES


class TargetPage(Page):
    """A part that is only written from the theme: a switch "Leave as it is | Set by this theme", the
    values it follows and the note of what an apply does with it."""

    style_field: tuple[str, str] = ("", "")
    set_hint = ""

    def build(self) -> None:
        self.header.add_part_switch()
        self.header.set_hint(self.set_hint)
        self.header.part_mode_changed.connect(self._switched)
        # the values and notes in a column on the left, the side preview (if any) on the right
        self._side_column()
        left = QWidget()
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(LARGE_SPACING)
        row = QHBoxLayout()
        row.setSpacing(LARGE_SPACING + 8)
        row.addWidget(left, 1)
        row.addWidget(self.side_box, 0, Qt.AlignmentFlag.AlignTop)
        self.content.addLayout(row, 1)
        self.content = self.notes_layout = column
        self.build_values()

    def build_values(self) -> None:
        """Add the values of the part to `self.content` (the left column). A preview goes to the right
        with `self.set_side_preview(widget)`, e.g. `self.set_side_preview(self.sample)`."""

    def _switched(self, on: bool) -> None:
        self.window.edit(FIELD_BY_ID[self.style_field], "generated" if on else "unchanged")

    def refresh(self) -> None:
        on = self.theme.get(*self.style_field) == "generated"
        self.header.set_part_mode(on)
        super().refresh()


class LinkPage(Page):
    """A part this app does not edit: a few plain words on why, and a button that opens its page in
    System Settings. A subclass sets `key` (a registry entry of kind "link") and gives `explanation`."""

    def explanation(self) -> str:
        return ""

    def build(self) -> None:
        from . import SPECS

        self.module_id = SPECS[self.key].link
        text = QLabel(self.explanation())
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setMaximumWidth(TUNING_WIDTH)
        self.open_button = QPushButton(
            translate("ui", "Open {page} in System Settings…").format(page=self.title_text())
        )
        self.open_button.clicked.connect(self.open_module)
        self.content.addWidget(text)
        self.content.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignLeft)

    def title_text(self) -> str:
        from . import title_of

        return title_of(self.key)

    def open_module(self) -> None:
        from ... import desktopparts
        from ..banner import WARNING

        problem = desktopparts.open_system_settings(self.module_id, self.window.runner)
        if problem is not None:
            self.window.banner.show_message(WARNING, str(problem), 8)


def field_of(section: str, key: str) -> Field:
    return FIELD_BY_ID[(section, key)]
