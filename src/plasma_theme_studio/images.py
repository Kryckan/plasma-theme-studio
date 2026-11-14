# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading a picture of unknown origin without hanging or filling the memory.

A picture a person chose can be a pipe (reading it blocks for ever), a header that claims
100000 x 100000 pixels, or simply huge. Every place that decodes such a file goes through
`open_reader` so the same three limits hold everywhere: a regular file, at most MAX_PIXELS
pixels when the header says, and Qt's decode limit set here instead of left to its default.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QImageReader

from . import safefile

MAX_PIXELS = 40_000_000  # a picture of more pixels is not decoded (160 MB as an image)
ALLOCATION_LIMIT_MB = 256  # the most Qt may allocate for one decoded picture


def open_reader(path: Path | str) -> QImageReader | None:
    """A reader for `path` with the size cap applied; None for a pipe, a device, a missing
    file or a picture with more than MAX_PIXELS pixels."""
    path = Path(path)
    if not safefile.is_regular(path):
        return None
    QImageReader.setAllocationLimit(ALLOCATION_LIMIT_MB)
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() * size.height() > MAX_PIXELS:
        return None
    return reader


def read_image(path: Path | str) -> QImage:
    """The whole picture, or a null image when it cannot or may not be read."""
    reader = open_reader(path)
    return reader.read() if reader is not None else QImage()


def too_large(path: Path | str) -> bool:
    """Whether the header of `path` says it has more than MAX_PIXELS pixels."""
    if not safefile.is_regular(Path(path)):
        return False
    size: QSize = QImageReader(str(path)).size()
    return size.isValid() and size.width() * size.height() > MAX_PIXELS
