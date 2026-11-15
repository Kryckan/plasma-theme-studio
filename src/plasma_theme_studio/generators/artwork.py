# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Own artwork for the frames of the Plasma style: SVG files drawn by hand (in Inkscape, say).

A file is untrusted input. It is read through `safefile` with a size limit, parsed without ever
following a reference to another file or to the network, and refused when it holds scripts, text,
pictures or anything that points outside itself. Nothing here needs Qt: the declared size of the
picture is never used for anything.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .. import safefile
from ..messages import Msg, translate
from ..model.theme import ARTWORK_LIMIT, Theme

MAX_ELEMENTS = 20000
MAX_DEPTH = 64
MAX_DRAWN = 200000  # elements drawn in all, counting every <use> as the copy of what it points at
# What costs far more than one element: every filtered element is a blurred copy of its area, and
# every marker is drawn at every point of its path. Counted with every <use> as one more copy.
MAX_FILTERED = 60
MAX_MARKERS = 10000
# What other elements point at: it may not point at anything itself, or the cost multiplies.
REFERENCED = frozenset("pattern mask marker clippath filter".split())
# Elements that are never accepted: code, text (a font is not Plasma's to know), pictures and
# links to other files, animation, and anything that embeds another document.
FORBIDDEN_TAGS = frozenset(
    "script text tspan tref textpath foreignobject image iframe a animate animatemotion "
    "animatetransform animatecolor set video audio canvas object embed handler listener".split()
)
OWN_MARK = "<!-- Own artwork. -->"
_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>\s*")
_FORBIDDEN_URL = re.compile(r"url\(\s*['\"]?\s*(?!#)", re.IGNORECASE)
_IMPORT = re.compile(r"@import", re.IGNORECASE)


@dataclass
class Artwork:
    """What a frame's own artwork turned out to be. `text` is the SVG when it can be used,
    otherwise `problems` says why not, in plain words. `path` is None when the theme names none."""

    key: str
    path: Path | None = None
    name: str = ""
    text: str | None = None
    problems: list[Msg] = field(default_factory=list)

    @property
    def set(self) -> bool:
        return bool(self.name)

    @property
    def usable(self) -> bool:
        return self.text is not None


def _names(missing: list[str]) -> str:
    shown = ", ".join(missing[:6])
    return shown + (f" (+{len(missing) - 6})" if len(missing) > 6 else "")


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def check(raw: bytes, required: frozenset[str]) -> tuple[str | None, list[Msg]]:
    """The SVG text made from `raw`, ready to be written into a style (without its XML
    declaration), or None and the problems. `required` are the element ids Plasma needs."""
    if len(raw) > ARTWORK_LIMIT:
        return None, [translate("core", "The file is too large to be artwork for a frame.")]
    try:
        text = raw.decode("utf-8").removeprefix("﻿")
    except UnicodeDecodeError:
        return None, [translate("core", "The file is not text in UTF-8, so it is not an SVG picture.")]
    text = _DECLARATION.sub("", text, count=1)
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        return None, [translate("core", "The file has a document type declaration, which is not accepted.")]
    if "<?" in text:
        return None, [translate("core", "The file has processing instructions, which are not accepted.")]
    problems: list[Msg] = []
    ids: set[str] = set()
    count = depth = 0
    root_tag = ""
    root = None
    try:
        for event, element in ET.iterparse(io.StringIO(text), events=("start", "end")):
            if event == "end":
                depth -= 1
                continue
            root = element if root is None else root
            depth += 1
            count += 1
            if count > MAX_ELEMENTS or depth > MAX_DEPTH:
                return None, [translate("core", "The picture is too complicated for a frame.")]
            tag = _local(element.tag).lower()
            root_tag = root_tag or tag
            if tag in FORBIDDEN_TAGS:
                problems.append(
                    translate("core", "The picture contains {name}, which a frame must not have.").format(
                        name=tag
                    )
                )
            for attribute, value in element.attrib.items():
                name = _local(attribute).lower()
                if name == "id":
                    ids.add(value)
                elif name == "href" and not value.startswith("#"):
                    problems.append(translate("core", "The picture points at another file."))
                elif name.startswith("on"):
                    problems.append(translate("core", "The picture contains a script."))
                elif _FORBIDDEN_URL.search(value):
                    problems.append(translate("core", "The picture points at another file."))
            if tag == "style":
                element_text = "".join(element.itertext())
                if _IMPORT.search(element_text) or _FORBIDDEN_URL.search(element_text):
                    problems.append(translate("core", "The picture points at another file."))
    except ET.ParseError as error:
        return None, [translate("core", "The file is not a valid SVG picture: {detail}").format(detail=error)]
    except (RecursionError, ValueError):
        return None, [translate("core", "The file is not a valid SVG picture.")]
    if root_tag != "svg":
        return None, [translate("core", "The file is not an SVG picture.")]
    if root is not None and _too_costly(root):
        return None, [translate("core", "The picture is too complicated for a frame.")]
    missing = sorted(required - ids)
    if missing:
        problems.append(
            translate("core", "The picture lacks parts Plasma needs: {names}.").format(names=_names(missing))
        )
    unique = list(dict.fromkeys(str(problem) for problem in problems))
    if unique:
        return None, unique
    return text, []


def _too_costly(root: ET.Element) -> bool:
    """Whether drawing the picture would take far longer than its size suggests: a few small <use>
    elements that point at groups that point at groups double the work with every level."""
    by_id = {element.get("id"): element for element in root.iter() if element.get("id")}
    size: dict[int, int] = {}

    def subtree(element: ET.Element) -> int:
        if id(element) not in size:
            size[id(element)] = sum(1 for _ in element.iter())
        return size[id(element)]

    def points(element: ET.Element) -> bool:
        for item in element.iter():
            if _local(item.tag).lower() == "use":
                return True
            if any("url(#" in value for value in item.attrib.values()):
                return True
        return False

    drawn = subtree(root)
    uses: dict[str, int] = {}
    for element in root.iter():
        if _local(element.tag).lower() == "use":
            for attribute, value in element.attrib.items():
                if _local(attribute).lower() == "href":
                    uses[value.removeprefix("#")] = uses.get(value.removeprefix("#"), 0) + 1
    if _heavy(root, by_id, uses, subtree):
        return True
    for element in root.iter():
        tag = _local(element.tag).lower()
        if tag in REFERENCED and any(points(child) for child in element):
            return True
        if tag != "use":
            continue
        target = None
        for attribute, value in element.attrib.items():
            if _local(attribute).lower() == "href":
                target = by_id.get(value.removeprefix("#"))
        if target is None:
            continue
        if any(_local(item.tag).lower() == "use" for item in target.iter()):
            return True  # a use that points at another use is where the doubling comes from
        drawn += subtree(target)
        if drawn > MAX_DRAWN:
            return True
    return False


def _heavy(root: ET.Element, by_id: dict, uses: dict[str, int], subtree) -> bool:
    """Whether the filters and markers, with every <use> counted as another copy, cost too much."""
    filtered = markers = 0
    stack = [(root, 1)]
    while stack:
        element, copies = stack.pop()
        copies += uses.get(element.get("id"), 0)
        values = dict(element.attrib)
        for declaration in values.pop("style", "").split(";"):
            name, _, value = declaration.partition(":")
            values[name.strip()] = value
        if "url(#" in values.get("filter", ""):
            filtered += copies
        for name in ("marker", "marker-start", "marker-mid", "marker-end"):
            match = re.search(r"url\(#([^)\s]*)", values.get(name, ""))
            if match and match.group(1) in by_id:
                numbers = len(re.findall(r"-?\d*\.?\d+", values.get("d", values.get("points", ""))))
                markers += copies * subtree(by_id[match.group(1)]) * max(2, numbers // 2)
        if filtered > MAX_FILTERED or markers > MAX_MARKERS:
            return True
        stack += [(child, copies) for child in element]
    return False


_cache: dict[tuple, Artwork] = {}


def resolve(theme: Theme, key: str) -> tuple[str, Path | None]:
    """The name the theme gives to the artwork of frame `key` and where that file is, or
    (name, None) when it cannot be found: the theme has no file yet, or the name leaves the folder."""
    name = theme.get("artwork", key) or ""
    if not name or theme.base_dir is None:
        return name, None
    try:
        base = theme.base_dir.resolve()
        path = (base / name).resolve()
    except (OSError, RuntimeError):
        return name, None
    return (name, path) if path.is_relative_to(base) else (name, None)


def load(theme: Theme, key: str, required: frozenset[str]) -> Artwork:
    """Read and check the own artwork of frame `key`, if the theme names any."""
    name, path = resolve(theme, key)
    art = Artwork(key, path, name)
    if not name:
        return art
    if theme.base_dir is None:
        art.problems = [translate("core", "The theme is not saved yet, so its artwork cannot be found.")]
        return art
    if path is None:
        art.problems = [
            translate("core", "The artwork {name} is outside the folder of the theme.").format(name=name)
        ]
        return art
    try:
        info = path.stat()
        stamp = (str(path), info.st_mtime_ns, info.st_size, tuple(sorted(required)))
    except OSError:
        art.problems = [translate("core", "The artwork file {name} was not found.").format(name=name)]
        return art
    if stamp in _cache:
        return _cache[stamp]
    raw = safefile.read_regular(path, ARTWORK_LIMIT)
    if raw is None:
        art.problems = [
            translate("core", "The artwork file {name} cannot be read or is too large.").format(name=name)
        ]
    else:
        art.text, art.problems = check(raw, required)
    if len(_cache) > 32:
        _cache.clear()
    _cache[stamp] = art
    return art


def style_text(text: str) -> str:
    """`text` as a file of a generated style: it starts with the mark that says it is ours."""
    from .base import XML_MARKER

    return f"{XML_MARKER}\n{OWN_MARK}\n{text}"
