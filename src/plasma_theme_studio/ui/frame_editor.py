# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The "Frames" block of the Plasma Style page: the four frames the generated style draws (panel,
popups, tooltips, widget backgrounds), each shown as it is drawn, with its values, and a way to draw
one by hand in Inkscape.

A frame is generated from the theme's values until its file is saved from Inkscape; from then on the
theme names that file (`[artwork]`) and the frame is "Own artwork". The file belongs to the theme: it
lives in a folder next to the theme file. "Back to the generated frame" only forgets the name.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QFileSystemWatcher, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..generators import artwork as artwork_module
from ..generators import plasmastyle
from ..model.theme import ARTWORK_KEYS, FIELD_BY_ID, Theme, artwork_folder, write_atomic
from . import frame_render
from .widgets import SPACING, CardGrid, InlineNote

translate = QCoreApplication.translate

INKSCAPE = "inkscape"
THUMB = QSize(176, 110)
WATCH_DELAY = 500  # milliseconds after the last change of a watched file before it is read


def frame_titles() -> dict[str, str]:
    return {
        "panel": translate("ui", "Panel"),
        "popups": translate("ui", "Popups"),
        "tooltips": translate("ui", "Tooltips"),
        "widgets": translate("ui", "Widget backgrounds"),
    }


def paint_scene(painter: QPainter, rect: QRectF) -> None:
    """A stand-in for the desktop behind a frame: a calm blue-gray, so that light and dark frames and
    their shadows can all be seen."""
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0, QColor("#7f9ab5"))
    gradient.setColorAt(1, QColor("#4d6580"))
    painter.fillRect(rect, gradient)


class FrameView(QWidget):
    """A large, true drawing of one frame at two sizes, with a switch for the lines showing how it is cut."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = None
        self.guides = False
        self.setMinimumSize(300, 250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName(translate("ui", "The frame drawn at two sizes"))

    def sizeHint(self) -> QSize:
        return QSize(420, 300)

    def set_renderer(self, renderer) -> None:
        self.renderer = renderer
        self.update()

    def set_guides(self, shown: bool) -> None:
        self.guides = shown
        self.update()

    def sizes(self) -> list[QRectF]:
        """Where the two frames are drawn: a large one on top and a small one under it."""
        w, h = self.width(), self.height() - 28  # the legend takes the bottom
        reach = 14
        big_w, big_h = min(w - 2 * reach - 16, 320.0), min(h * 0.58 - 2 * reach, 130.0)
        small_w, small_h = min(w * 0.4, 150.0), min(h * 0.25, 44.0)
        big = QRectF((w - big_w) / 2, reach + 6, big_w, big_h)
        small = QRectF((w - small_w) / 2, big.bottom() + 2 * reach + 8, small_w, small_h)
        return [big, small]

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        scene = QRectF(self.rect()).adjusted(0, 0, 0, -28)
        p.setClipRect(scene)
        paint_scene(p, scene)
        if self.renderer is not None:
            for rect in self.sizes():
                if rect.width() > 0 and rect.height() > 0:
                    frame_render.draw_frame(self.renderer, p, rect, guides=self.guides)
        p.setClipping(False)
        if self.guides:
            self._legend(p, QRectF(0, self.height() - 26, self.width(), 24))
        p.end()

    def _legend(self, p: QPainter, area: QRectF) -> None:
        items = (
            (frame_render.GUIDE_SLICE, Qt.PenStyle.SolidLine, translate("ui", "Slices")),
            (frame_render.GUIDE_MARGIN, Qt.PenStyle.DashLine, translate("ui", "Keeps content away")),
            (frame_render.GUIDE_SHADOW, Qt.PenStyle.DotLine, translate("ui", "Shadow reaches")),
        )
        metrics = p.fontMetrics()
        x = area.left() + 4
        for color, style, text in items:
            pen = QPen(color, 2.0, style)
            p.setPen(pen)
            y = area.center().y()
            p.drawLine(int(x), int(y), int(x + 22), int(y))
            p.setPen(self.palette().color(QPalette.ColorRole.WindowText))
            width = metrics.horizontalAdvance(text)
            p.drawText(
                QRectF(x + 28, area.top(), width + 4, area.height()), Qt.AlignmentFlag.AlignVCenter, text
            )
            x += 28 + width + 18


class FrameEditor(QWidget):
    """The cards, the values of the chosen frame, its large drawing and the Inkscape buttons."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.current = ARTWORK_KEYS[0]
        self.sources: dict[str, tuple[str, object, plasmastyle.artwork.Artwork]] = {}
        self.stamps: dict[str, tuple[int, int]] = {}  # file stamp of each watched frame when last read
        self._subtitles: list[str] = []
        self.keep_note_text = ""
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._file_event)
        self.watcher.directoryChanged.connect(self._file_event)
        self.watch_timer = QTimer(self, singleShot=True, interval=WATCH_DELAY)
        self.watch_timer.timeout.connect(self.check_files)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 16, 0)
        outer.setSpacing(12)
        self.heading = QLabel(translate("ui", "Frames"))
        font = self.heading.font()
        font.setBold(True)
        self.heading.setFont(font)
        outer.addWidget(self.heading)
        intro = QLabel(
            translate(
                "ui",
                "Plasma draws the panel, popups, tooltips and widget backgrounds from these pictures. "
                "They are made from the values above until you draw one yourself.",
            )
        )
        intro.setWordWrap(True)
        intro.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        outer.addWidget(intro)
        self.grid = CardGrid(THUMB, with_search=False, fit=True, name=translate("ui", "Frames"), reveal=False)
        self.grid.selected.connect(self.choose)
        outer.addWidget(self.grid)

        row = QHBoxLayout()
        row.setSpacing(24)
        column = QVBoxLayout()
        column.setSpacing(10)
        self.title = QLabel()
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        column.addWidget(self.title)
        self.values = QFormLayout()
        self.values.setVerticalSpacing(SPACING)
        self.values.setHorizontalSpacing(SPACING)
        self.value_labels: dict[str, QLabel] = {}
        for key, text in (
            ("radius", translate("ui", "Corner radius")),
            ("border", translate("ui", "Border")),
            ("fill", translate("ui", "Fill")),
            ("opacity", translate("ui", "Opacity")),
            ("shadow", translate("ui", "Shadow")),
        ):
            label = QLabel()
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            self.value_labels[key] = label
            name = QLabel(text + translate("ui", ":"))
            name.setMinimumWidth(110)
            self.values.addRow(name, label)
        column.addLayout(self.values)
        self.source_note = QLabel()
        self.source_note.setWordWrap(True)
        self.source_note.setTextFormat(Qt.TextFormat.PlainText)
        column.addWidget(self.source_note)
        buttons = QHBoxLayout()
        buttons.setSpacing(SPACING)
        self.open_button = QPushButton(translate("ui", "Open in Inkscape…"))
        self.open_button.clicked.connect(self.open_in_inkscape)
        self.back_button = QPushButton(translate("ui", "Back to the generated frame"))
        self.back_button.clicked.connect(self.back_to_generated)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.back_button)
        buttons.addStretch(1)
        column.addLayout(buttons)
        self.why = QLabel()
        self.why.setWordWrap(True)
        self.why.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        column.addWidget(self.why)
        self.problems = InlineNote("", "warning")
        self.problems.hide()
        column.addWidget(self.problems)
        column.addStretch(1)
        right = QVBoxLayout()
        self.view = FrameView()
        right.addWidget(self.view)
        self.guides = QCheckBox(translate("ui", "Show how the frame is cut into nine parts"))
        self.guides.toggled.connect(self.view.set_guides)
        right.addWidget(self.guides)
        row.addLayout(column, 5)
        row.addLayout(right, 6)
        outer.addLayout(row)

    # ---- the theme

    def set_theme(self, theme: Theme) -> None:
        """Show the frames of `theme`. Called by the page whenever it is refreshed."""
        titles = frame_titles()
        self.sources.clear()
        subtitles = []
        for frame in ARTWORK_KEYS:
            art = plasmastyle.own_artwork(theme, frame)
            text = art.text if art.usable else plasmastyle.frame_svg(theme, frame)
            self.sources[frame] = (text, None, art)
            subtitles.append(self._state_words(art))
        if subtitles != self._subtitles:
            self._subtitles = subtitles
            self.grid.set_items(
                [(frame, titles[frame], subtitles[i]) for i, frame in enumerate(ARTWORK_KEYS)]
            )
        self.grid.set_selected(self.current)
        for frame in ARTWORK_KEYS:
            self.grid.set_thumbnail(frame, self.thumbnail(frame))
        self._watch(theme)
        self._show_current()

    @staticmethod
    def _state_words(art) -> str:
        if art.usable:
            return translate("ui", "Own artwork")
        if art.set:
            return translate("ui", "Own artwork, not usable")
        return translate("ui", "Made from the values")

    def renderer(self, frame: str):
        """The renderer of the SVG shown for `frame`, in the colors of the theme."""
        text = self.sources[frame][0]
        theme = self.window.theme
        return frame_render.renderer_for(
            frame_render.colored(text, theme.get("colors", "window"), theme.get("colors", "text"))
        )

    def thumbnail(self, frame: str) -> QImage:
        ratio = self.devicePixelRatioF() or 1.0
        image = QImage(THUMB * ratio, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        scene = QRectF(0, 0, THUMB.width(), THUMB.height())
        paint_scene(p, scene)
        renderer = self.renderer(frame)
        if renderer is not None:
            frame_render.draw_frame(renderer, p, scene.adjusted(30, 30, -30, -30))
        p.end()
        return image

    def choose(self, frame) -> None:
        if frame in ARTWORK_KEYS:
            self.current = frame
            self._show_current()

    # ---- values of the chosen frame

    def _inherited(self, theme: Theme, section: str, key: str, unit: str = "px") -> str:
        """A value with where it comes from: its own, or the one it follows."""
        value = theme.resolved(section, key)
        shown = f"{round(value * 100)} %" if unit == "%" else f"{value} px"
        owner = (section, key)
        while theme.get(*owner) is None and FIELD_BY_ID[owner].inherits:
            owner = FIELD_BY_ID[owner].inherits
        if owner == (section, key) or theme.get(*owner) is None:
            return shown
        if owner[0] == "shape":
            return translate("ui", "{value}, same as Shapes").format(value=shown)
        return translate("ui", "{value}, same as the panel").format(value=shown)

    def _show_current(self) -> None:
        theme = self.window.theme
        frame = self.current
        text, _unused, art = self.sources.get(frame) or ("", None, artwork_module.Artwork(frame))
        titles = frame_titles()
        self.title.setText(titles[frame])
        section = "panel" if frame == "panel" else "popup"
        own = art.usable
        for label in self.value_labels.values():
            label.setEnabled(not own)
        if own:
            for key in ("radius", "border", "fill", "opacity", "shadow"):
                self.value_labels[key].setText(translate("ui", "From the picture"))
        else:
            self.value_labels["radius"].setText(self._inherited(theme, section, "radius"))
            self.value_labels["border"].setText(self._inherited(theme, section, "border_width"))
            self.value_labels["fill"].setText(translate("ui", "The window color of the color scheme"))
            self.value_labels["opacity"].setText(self._inherited(theme, section, "opacity", "%"))
            self.value_labels["shadow"].setText(
                translate("ui", "Soft, reaching 10 px (the same on every side)")
            )
        installed = shutil_which(self.window.runner, INKSCAPE)
        self.open_button.setEnabled(installed)
        self.why.setVisible(not installed)
        if not installed:
            sentence = translate(
                "ui", "Inkscape is not installed on this computer, so a frame cannot be drawn by hand."
            )
            self.why.setText(sentence)
            self.open_button.setToolTip(sentence)
        else:
            self.open_button.setToolTip(translate("ui", "Opens this frame as a picture in Inkscape."))
        self.back_button.setVisible(art.set)
        self.back_button.setToolTip(
            translate("ui", "The picture stays on your disk. The theme just stops using it.")
        )
        if art.usable:
            self.source_note.setText(translate("ui", "Own artwork: {name}").format(name=art.name))
        elif art.set:
            self.source_note.setText(translate("ui", "The generated frame is used for now."))
        else:
            self.source_note.setText(
                self.keep_note_text or translate("ui", "Change the values above, or open it in Inkscape.")
            )
        self.problems.set_text("\n".join(str(problem) for problem in art.problems))
        self.problems.setVisible(bool(art.problems))
        self.view.set_renderer(self.renderer(frame))

    # ---- Inkscape

    def artwork_path(self, frame: str) -> Path | None:
        """Where the file of `frame` is or would be: next to the saved theme file."""
        if self.window.path is None:
            return None
        return artwork_folder(self.window.path) / f"{frame}.svg"

    def open_in_inkscape(self) -> bool:
        """Write the frame's SVG beside the theme file (unless it has artwork already), open it in
        Inkscape and watch it. Returns whether Inkscape was started."""
        frame = self.current
        if self.window.path is None:
            ask = QMessageBox.question(
                self,
                translate("ui", "Save the theme first"),
                translate(
                    "ui",
                    "The artwork is kept in a folder next to the theme file, so the theme has to be "
                    "saved first. Save it now?",
                ),
            )
            if ask != QMessageBox.StandardButton.Yes or not self.window.save():
                return False
        theme = self.window.theme
        existing = plasmastyle.own_artwork(theme, frame)
        path = existing.path if existing.set and existing.path is not None else self.artwork_path(frame)
        if path is None:
            return False
        if not existing.set and path.is_file():
            # "Back to the generated frame" left the picture on disk: use it, do not draw it over.
            self.window.edit(
                FIELD_BY_ID[("artwork", frame)], f"{artwork_folder(self.window.path).name}/{path.name}"
            )
        elif not path.is_file():
            try:
                write_atomic(path, plasmastyle.frame_svg(theme, frame))
            except OSError as error:
                QMessageBox.warning(
                    self,
                    translate("ui", "Could not write the picture"),
                    translate("ui", "{file} could not be written: {detail}").format(
                        file=str(path), detail=str(error)
                    ),
                )
                return False
        self.stamps[frame] = self._stamp(path)
        self._add_watch(path)
        self.window.runner.launch([INKSCAPE, str(path)])
        self.keep_note_text = translate("ui", "Save the picture in Inkscape and this page picks it up.")
        self._show_current()
        return True

    def back_to_generated(self) -> None:
        theme = self.window.theme
        art = plasmastyle.own_artwork(theme, self.current)
        self.window.edit(FIELD_BY_ID[("artwork", self.current)], None)
        where = str(art.path) if art.path else art.name
        self.keep_note_text = translate("ui", "The picture stays on your disk: {file}").format(file=where)
        self.set_theme(self.window.theme)

    # ---- watching the files

    @staticmethod
    def _stamp(path: Path) -> tuple[int, int]:
        try:
            info = path.stat()
        except OSError:
            return (0, 0)
        return (info.st_mtime_ns, info.st_size)

    def _add_watch(self, path: Path) -> None:
        for item in (str(path), str(path.parent)):
            if item not in self.watcher.files() + self.watcher.directories() and os.path.exists(item):
                self.watcher.addPath(item)

    def _watch(self, theme: Theme) -> None:
        for frame in ARTWORK_KEYS:
            art = plasmastyle.own_artwork(theme, frame)
            if art.set and art.path is not None and art.path.is_file():
                self.stamps.setdefault(frame, self._stamp(art.path))
                self._add_watch(art.path)

    def _file_event(self, *_) -> None:
        self.watch_timer.start()  # Inkscape writes in several steps; read once it has been quiet

    def check_files(self) -> None:
        """Read the watched files that changed since they were last read: the frame becomes Own
        artwork (when the file is the one beside the theme file) and the page and the status are redone."""
        theme = self.window.theme
        changed = False
        for frame, stamp in list(self.stamps.items()):
            path = self.artwork_path(frame)
            art = plasmastyle.own_artwork(theme, frame)
            if art.set and art.path is not None:
                path = art.path
            if path is None or self._stamp(path) == stamp:
                continue
            self.stamps[frame] = self._stamp(path)
            self._add_watch(path)  # an editor that saves by replacing the file leaves the old watch behind
            if not art.set and path.is_file():
                relative = f"{artwork_folder(self.window.path).name}/{path.name}"
                self.window.edit(FIELD_BY_ID[("artwork", frame)], relative)
            changed = True
        if changed:
            self.window.refresh()


def shutil_which(runner, program: str) -> bool:
    try:
        return bool(runner.which(program))
    except OSError:
        return False
