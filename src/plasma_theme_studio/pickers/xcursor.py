# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A reader for Xcursor files (the bitmap cursors of a cursor theme).

The file is little endian: the header (magic "Xcur", header size, version,
number of table entries), a table of contents (type, subtype, position) and
the chunks. An image chunk (type 0xfffd0002) has a 36 byte header (header
size, type, nominal size, version, width, height, hotspot x, hotspot y, delay
in ms) followed by width * height premultiplied ARGB pixels. An animated
cursor has several image chunks for a nominal size, in the order of the frames.

Everything read is bounded, and a file that is truncated, too large or made up
is refused: `nominal_sizes` and `read_image` give an empty result or None,
they do not raise. QImage is the only Qt class used, so this is safe on a
worker thread.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QImage

MAGIC = b"Xcur"
IMAGE_TYPE = 0xFFFD0002
MAX_ENTRIES = 4096  # table entries; real files have a few hundred at most
MAX_SIDE = 1024  # largest width or height of an image (themes go up to about 256)
MAX_NOMINAL = 4096
HEADER = struct.Struct("<4sIII")
ENTRY = struct.Struct("<III")
CHUNK = struct.Struct("<IIIIIIIII")


@dataclass(frozen=True)
class Image:
    """One image of a cursor: `pixels` are premultiplied ARGB32, little endian."""

    nominal: int
    width: int
    height: int
    xhot: int
    yhot: int
    delay: int
    pixels: bytes

    def to_qimage(self) -> QImage:
        image = QImage(
            self.pixels, self.width, self.height, 4 * self.width, QImage.Format.Format_ARGB32_Premultiplied
        )
        return image.copy()  # own the pixels: `pixels` may go away


def _toc(handle) -> list[tuple[int, int, int]]:
    """The (type, subtype, position) of the image chunks, in file order."""
    magic, header_size, _version, count = HEADER.unpack(handle.read(HEADER.size))
    if magic != MAGIC or header_size < HEADER.size or count > MAX_ENTRIES:
        return []
    handle.seek(header_size)
    data = handle.read(ENTRY.size * count)
    if len(data) != ENTRY.size * count:
        return []
    entries = [ENTRY.unpack_from(data, i * ENTRY.size) for i in range(count)]
    return [entry for entry in entries if entry[0] == IMAGE_TYPE]


def nominal_sizes(path: Path) -> list[int]:
    """The nominal sizes a cursor file has, ascending; [] when it cannot be read."""
    try:
        with open(path, "rb") as handle:
            return sorted({sub for _, sub, _ in _toc(handle) if 0 < sub <= MAX_NOMINAL})
    except (OSError, struct.error, ValueError):
        return []


def read_image(path: Path, want: int) -> Image | None:
    """The first image (the first frame of an animation) of the nominal size
    nearest to `want` (the smaller one when two are as near); None when the
    file is no usable Xcursor file."""
    try:
        with open(path, "rb") as handle:
            entries = [e for e in _toc(handle) if 0 < e[1] <= MAX_NOMINAL]
            if not entries:
                return None
            nominal = min({e[1] for e in entries}, key=lambda size: (abs(size - want), size))
            for _type, sub, position in entries:  # file order: the first frame of that size
                if sub == nominal and (image := _chunk(handle, position, nominal)) is not None:
                    return image
    except (OSError, struct.error, ValueError, OverflowError):
        pass
    return None


def _chunk(handle, position: int, nominal: int) -> Image | None:
    handle.seek(position)
    raw = handle.read(CHUNK.size)
    if len(raw) != CHUNK.size:
        return None
    header, kind, sub, _version, width, height, xhot, yhot, delay = CHUNK.unpack(raw)
    if header < CHUNK.size or kind != IMAGE_TYPE or sub != nominal:
        return None
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
        return None
    xhot, yhot = min(xhot, width - 1), min(yhot, height - 1)
    handle.seek(position + header)
    pixels = handle.read(4 * width * height)
    if len(pixels) != 4 * width * height:
        return None
    return Image(nominal, width, height, xhot, yhot, delay, pixels)
