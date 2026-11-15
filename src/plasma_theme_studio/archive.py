# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A theme as one file: export to and import from a ".ptstheme" archive.

The archive is a zip file with `theme.toml` and a flat `assets/` folder that holds the own artwork
of the Plasma style frames (`assets/panel.svg` ...), which the theme file names as `assets/panel.svg`.
On import the artwork is checked and handed to the theme (`Theme.pending_artwork`); it is written
beside the theme file when that is saved. Import never extracts anything by the name found in the
file: it reads the few allowed members into memory and checks them, so no
path inside an archive can reach the disk. Every read is bounded, whatever the
headers claim. A plain theme file (.toml) is read through the same function.
"""

from __future__ import annotations

import io
import re
import stat
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import svgsandbox
from .generators import artwork, plasmastyle
from .messages import Msg, translate
from .model.theme import ARTWORK_KEYS, Theme, ThemeError, write_atomic

EXTENSION = ".ptstheme"
THEME_NAME = "theme.toml"
ASSETS_DIR = "assets/"
MAX_THEME = 64 * 1024
MAX_ASSET = 2 * 1024 * 1024
MAX_ENTRIES = 64
MAX_TOTAL = 16 * 1024 * 1024  # the sum of the sizes the archive claims for its members
ASSET_NAME = re.compile(r"^assets/[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.svg$")
ZIP_MAGIC = b"PK"
# The same time in every archive, so that the same theme always gives the same bytes.
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


class ArchiveError(Exception):
    """A theme file that cannot be imported. `message` says why, in plain words."""

    def __init__(self, message: Msg):
        self.message = message
        super().__init__(str(message))


def _bad(text: str, **args) -> ArchiveError:
    return ArchiveError(translate("core", text).format(**args))


def _member(name: str, data: bytes) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def _own_artwork(theme: Theme) -> dict[str, str]:
    """The artwork of the theme that can be used, by frame: what is read from the files beside it."""
    found = {}
    for frame in ARTWORK_KEYS:
        text = plasmastyle.own_artwork(theme, frame).text
        if text is not None:
            found[frame] = text
    return found


def theme_bytes(theme: Theme) -> bytes:
    """The archive for a theme. Its own artwork goes along as `assets/<frame>.svg`; artwork
    that cannot be used (missing, damaged, not a frame) is left out and the theme does not name it."""
    shipped = _own_artwork(theme)
    packed = theme.copy()
    for frame in ARTWORK_KEYS:
        packed.set("artwork", frame, f"assets/{frame}.svg" if frame in shipped else None)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_member(THEME_NAME, b""), packed.to_toml().encode("utf-8"))
        for frame, text in shipped.items():
            archive.writestr(_member(f"assets/{frame}.svg", b""), text.encode("utf-8"))
    return buffer.getvalue()


def export_theme(theme: Theme, path: Path) -> None:
    """Write the theme as an archive at `path`."""
    write_atomic(path, theme_bytes(theme))


def _theme_from_bytes(raw: bytes, what: str) -> Theme:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _bad("{what} is not UTF-8 text.", what=what) from error
    try:
        return Theme.from_toml(text)
    except ThemeError as error:
        detail = "; ".join(str(problem) for problem in error.problems)
        raise _bad("{what} is not a valid theme: {detail}", what=what, detail=detail) from error


def _read_limited(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as stream:
            return stream.read(limit + 1)
    except OSError as error:
        raise _bad(
            "Could not read {path}: {detail}", path=str(path), detail=error.strerror or str(error)
        ) from error


def import_theme(path: Path) -> Theme:
    """Read a theme from an archive or from a plain theme file."""
    if _read_limited(path, 1).startswith(ZIP_MAGIC):
        return _read_archive(path)
    raw = _read_limited(path, MAX_THEME)
    if len(raw) > MAX_THEME:
        raise _bad("The file is too large to be a theme.")
    theme = _theme_from_bytes(raw, translate("core", "The file"))
    theme.pending_artwork = {}
    theme.base_dir = path.parent  # the artwork it names is found (and copied on Save As) from here
    return theme


def _check_members(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > MAX_ENTRIES:
        raise _bad("The archive holds too many files.")
    seen: set[str] = set()
    total = 0
    for info in infos:
        name = info.filename
        if name in seen:
            raise _bad("The archive lists {name} twice.", name=repr(name))
        seen.add(name)
        if info.is_dir():
            if name != ASSETS_DIR:
                raise _bad("The archive holds an unexpected folder: {name}", name=repr(name))
            continue
        # This also rejects absolute paths, "..", backslashes, drive letters and nested folders.
        if name != THEME_NAME and not ASSET_NAME.fullmatch(name):
            raise _bad("The archive holds an unexpected file: {name}", name=repr(name))
        # A member without type bits is a regular file (Python's writer leaves them out).
        if stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG):
            raise _bad("{name} in the archive is not a regular file.", name=repr(name))
        if info.flag_bits & 0x1:
            raise _bad("The archive is encrypted, which is not supported.")
        if info.file_size > (MAX_THEME if name == THEME_NAME else MAX_ASSET):
            raise _bad("{name} in the archive is too large.", name=repr(name))
        total += info.file_size
    if total > MAX_TOTAL:
        raise _bad("The archive is too large when unpacked.")
    if THEME_NAME not in seen:
        raise _bad("The archive has no theme.toml.")


def _read_member(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    with archive.open(name) as stream:  # the size in the header is not trusted: the read is bounded
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise _bad("{name} in the archive is too large.", name=repr(name))
    return data


def _drawable(text: str) -> bool:
    """Whether the child can draw `text`. A timeout or a child killed from outside may only mean a busy
    machine: asked once more."""
    outcome = svgsandbox.probe(text.encode("utf-8"))
    if outcome.retry:
        outcome = svgsandbox.probe(text.encode("utf-8"), fresh=True)
    return outcome.ok


def _with_artwork(theme: Theme, assets: dict[str, bytes]) -> Theme:
    """`theme` with the artwork that came along: only what passes the check is kept (as
    `Theme.pending_artwork`, written beside the theme file when it is saved); every other
    artwork name is dropped, because no file belongs to it."""
    theme.pending_artwork = {}
    checked: dict[str, str] = {}
    for frame in ARTWORK_KEYS:
        raw = assets.get(f"assets/{frame}.svg")
        if raw is not None and theme.get("artwork", frame) == f"assets/{frame}.svg":
            text, _problems = artwork.check(raw, plasmastyle.required_ids(frame))
            if text is not None:
                checked[frame] = text
    # Qt must be able to draw it, in a child with a memory cap and a timeout: the four run at once
    with ThreadPoolExecutor(max_workers=max(1, len(checked))) as pool:
        drawn = dict(
            zip(
                checked,
                pool.map(_drawable, checked.values()),
                strict=True,
            )
        )
    for frame in ARTWORK_KEYS:
        if drawn.get(frame):
            theme.pending_artwork[frame] = checked[frame].encode("utf-8")
        else:
            theme.set("artwork", frame, None)
    return theme


def _read_archive(path: Path) -> Theme:
    assets: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            _check_members(infos)
            raw = _read_member(archive, THEME_NAME, MAX_THEME)
            for info in infos:  # an asset is checked for size and damage; only artwork is used
                if not info.is_dir() and info.filename != THEME_NAME:
                    data = _read_member(archive, info.filename, MAX_ASSET)
                    if info.filename in {f"assets/{frame}.svg" for frame in ARTWORK_KEYS}:
                        assets[info.filename] = data
    except ArchiveError:
        raise
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError) as error:
        raise _bad("The file is not a usable theme archive: {detail}", detail=str(error)) from error
    except OSError as error:
        raise _bad(
            "Could not read {path}: {detail}", path=str(path), detail=error.strerror or str(error)
        ) from error
    return _with_artwork(_theme_from_bytes(raw, translate("core", "theme.toml")), assets)
