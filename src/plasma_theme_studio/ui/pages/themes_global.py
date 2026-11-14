# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a Global Theme sets, in words, for the detail strip of the Themes page.

The package is read and each name looked up among what is installed in a worker, so that choosing a
card never waits for the disk.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ... import pickers
from ...apply.status import PARTS as STATUS_PARTS
from ...model.parts import FontSpec
from ...pickers import globalthemes

# What a package gives, the part of the Overview it is called after, and the picker that lists it.
_NAMED = (
    ("color_scheme", "colors", "color_scheme"),
    ("plasma_style", "plasma_style", "plasma_style"),
    ("app_style", "app_style", "app_style"),
    ("decoration", "decoration", "decoration"),
    ("icons", "icons", "icons"),
    ("cursors", "pointers", "cursors"),
    ("splash", "splash", "splash"),
)


def package_summary(item) -> list[tuple[str, str, bool]]:
    """(part, value, installed) for every part the package sets, in the order of the Overview. The value
    is the name of what is installed, or the package's own words when it is not installed."""
    given = globalthemes.defaults(item)
    titles = {key: str(title) for key, title, _ids in STATUS_PARTS}
    rows: list[tuple[str, str, bool]] = []
    for part, page_key, kind_key in _NAMED:
        size = f"{given['cursor_size']} px" if part == "cursors" and "cursor_size" in given else ""
        if part not in given and not size:
            continue
        value, installed = "", True
        if part in given:
            picker = pickers.kind(kind_key)
            found = globalthemes.resolve(given[part], list(picker.items()) if picker else [])
            value, installed = (found.name if found else given[part]), found is not None
        rows.append((titles[page_key], ", ".join(text for text in (value, size) if text), installed))
    if "fonts" in given:
        general = FontSpec.parse(given["fonts"].get("general", ""))
        label = general.label() if general else ", ".join(sorted(given["fonts"].values()))
        rows.append((titles["fonts"], label, True))
    return rows


class _Answer(QObject):
    ready = Signal(int, object)


class _Job(QRunnable):
    def __init__(self, generation: int, item, answer: _Answer):
        super().__init__()
        self.generation, self.item, self.answer = generation, item, answer

    def run(self) -> None:
        try:
            rows = package_summary(self.item)
        except Exception:  # noqa: BLE001 - a package that cannot be read shows as one that sets nothing
            rows = []
        try:
            self.answer.ready.emit(self.generation, rows)
        except RuntimeError:  # the page is gone
            pass


class SummaryLoader(QObject):
    """Reads the summaries one at a time. Only the newest request is answered (`ready`)."""

    ready = Signal(object, object)  # the item, its rows

    def __init__(self, parent=None):
        super().__init__(parent)
        self.generation = 0
        self.item = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._answer = _Answer(self)
        self._answer.ready.connect(self._done)

    def request(self, item) -> None:
        self.generation += 1
        self.item = item
        self.pool.start(_Job(self.generation, item, self._answer))

    def cancel(self) -> None:
        self.generation += 1

    def _done(self, generation: int, rows) -> None:
        if generation == self.generation:
            self.ready.emit(self.item, rows)
