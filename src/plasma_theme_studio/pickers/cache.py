# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Thumbnails kept on disk.

Files live in `$XDG_CACHE_HOME/plasma-theme-studio/thumbs/<kind>/` and are named
`<item>-<variant>.png`. `<item>` is the SHA-1 of the item's path (or its id when
it has no path), the modification time and size of that path, and the newest
modification time among its direct children when it is a folder. `<variant>`
is the SHA-1 of the pixel size, the device pixel ratio and the colors. A change
of the item, the size or the colors therefore gives another file, and `prune`
can tell the files of items that are gone (or changed) by their first part.

`key(item, size, dpr, colors)` -> name without ".png"
`get(kind_key, name, dpr)` -> QImage or None (a corrupt file is deleted and counts as a miss)
`put(kind_key, name, image)` writes through a temporary file and renames it (atomic)
`prune(kind_key, items)` deletes the files that belong to no current item.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage

from .. import APP_DIR, images, paths
from .base import Item


def directory(kind_key: str) -> Path:
    return paths.cache_home() / APP_DIR / "thumbs" / kind_key


def _sha1(*parts: object) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _stamp(path: Path) -> tuple[int, int, int]:
    try:
        info = path.stat()
    except OSError:
        return (0, 0, 0)
    newest = 0
    if path.is_dir():
        with contextlib.suppress(OSError):
            newest = max((child.stat().st_mtime_ns for child in path.iterdir()), default=0)
    return (info.st_mtime_ns, info.st_size, newest)


def item_hash(item: Item) -> str:
    if item.path is None:
        return _sha1("id", item.id)
    return _sha1("path", str(item.path), *_stamp(Path(item.path)))


def pixel_size(size: QSize, dpr: float) -> tuple[int, int]:
    return (max(1, round(size.width() * dpr)), max(1, round(size.height() * dpr)))


def key(item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> str:
    variant = _sha1(pixel_size(size, dpr), round(dpr, 3), sorted(dict(colors or {}).items()))
    return f"{item_hash(item)}-{variant}"


def _file(kind_key: str, name: str) -> Path:
    return directory(kind_key) / f"{name}.png"


def get(kind_key: str, name: str, dpr: float = 1.0) -> QImage | None:
    """The cached picture for a `key`, or None."""
    path = _file(kind_key, name)
    if not path.is_file():
        return None
    image = images.read_image(path)
    if image.isNull():
        with contextlib.suppress(OSError):
            path.unlink()
        return None
    image.setDevicePixelRatio(dpr)
    return image


def put(kind_key: str, name: str, image: QImage) -> bool:
    """Store a picture; False when it is null or cannot be written. Nothing raises."""
    if image.isNull():
        return False
    folder = directory(kind_key)
    temporary = None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".tmp-", suffix=".png", dir=folder)
        os.close(handle)
        if not image.save(temporary, "PNG"):
            raise OSError("cannot write image")
        os.replace(temporary, _file(kind_key, name))
        return True
    except OSError:
        if temporary:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
        return False


def prune(kind_key: str, items: Iterable[Item]) -> int:
    """Delete the files of items that no longer exist or have changed, and
    leftover temporary files. Returns how many files were removed."""
    keep = {item_hash(item) for item in items if item.path is None or Path(item.path).exists()}
    removed = 0
    try:
        files = list(directory(kind_key).iterdir())
    except OSError:
        return 0
    for file in files:
        if file.name.startswith(".tmp-") or file.name.partition("-")[0] not in keep:
            with contextlib.suppress(OSError):
                file.unlink()
                removed += 1
    return removed
