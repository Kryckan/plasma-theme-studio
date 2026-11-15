# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Application Style: the widget styles of System Settings' page, drawn by the styles themselves.

The page lists every key of `QStyleFactory.keys()`, except the styles whose
`kstyle/themes/*.themerc` has `Hidden=true` (Union, while it is in development). A
themerc is matched to a key by its `[KDE] WidgetStyle`; its `[Misc] Name` and `Comment`
are the display name and the description, and a key without one ("Fusion",
"kvantum") shows as the key. The id is the key, which is what the page writes to
kdeglobals `[KDE] widgetStyle`.

A thumbnail is a panel of real widgets (tabs, a group with check box and radio buttons,
a combo box, a push button) that the style draws. The widgets get the style and the
palette one by one, so the application's own style, palette and font stay as they are.
The styles that are known to be safe that way are drawn on the GUI thread. Kvantum reads
its theme from the user's configuration and any style this module does not know is
not trusted, so those are drawn by the helper process (`_helper.py`), all in one run.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QPushButton,
    QRadioButton,
    QStyleFactory,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import paths
from ..messages import translate
from . import _colors, _process
from .base import Item, Kind, blank, data_folders, localized, read_ini, unique_sorted

# Styles that draw well on one widget and touch nothing else (tried one by one).
# A failed helper run is tried again after this many seconds.
RETRY = 30
# Union is not among them: without its data folder in XDG_DATA_DIRS a widget that gets the
# Union style crashes the process, which only the helper may risk.
IN_PROCESS = frozenset({"breeze", "oxygen", "fusion", "windows"})
HIDDEN = frozenset({"kvantum-dark"})  # System Settings shows only "kvantum"


def style_keys() -> list[str]:
    """The widget styles Qt can create here."""
    return list(QStyleFactory.keys())


def labels() -> dict[str, str]:
    """The texts of the sample, translated."""
    return {
        "tab1": str(translate("pickers", "Tab 1")),
        "tab2": str(translate("pickers", "Tab 2")),
        "group": str(translate("pickers", "Group")),
        "check": str(translate("pickers", "Check box")),
        "radio1": str(translate("pickers", "Radio button")),
        "radio2": str(translate("pickers", "Radio button")),
        "combo": str(translate("pickers", "Combo box")),
        "button": str(translate("pickers", "Push button")),
    }


# Listing -------------------------------------------------------------------


def _themercs() -> dict[str, tuple[Path, bool]]:
    """The themerc files by file name; the home folder's wins."""
    found: dict[str, tuple[Path, bool]] = {}
    for folder, user in data_folders("kstyle", "themes"):
        try:
            names = sorted(folder.glob("*.themerc"))
        except OSError:
            continue
        for path in names:
            found.setdefault(path.name, (path, user))
    return found


def _kvantum_config() -> Path:
    return paths.config_home() / "Kvantum" / "kvantum.kvconfig"


def list_styles() -> list[Item]:
    keys = {key.casefold(): key for key in style_keys()}
    styles: dict[str, dict] = {key: {"user": False} for key in keys.values() if key.casefold() not in HIDDEN}
    for path, user in _themercs().values():
        sections = read_ini(path)
        wanted = sections.get("KDE", {}).get("WidgetStyle", "")
        key = keys.get(wanted.casefold())
        if key is None or "Misc" not in sections:
            continue
        if sections.get("Desktop Entry", {}).get("Hidden", "").lower() == "true":
            styles.pop(key, None)
            continue
        if key in styles:
            styles[key] = {
                "name": localized(sections["Misc"], "Name"),
                "description": localized(sections["Misc"], "Comment"),
                "path": path,
                "user": user,
            }
    items = []
    for key, data in styles.items():
        path = data.get("path")
        if key.casefold().startswith("kvantum"):
            path = _kvantum_config()  # the style follows the Kvantum theme of the user
        items.append(
            Item(
                key,
                data.get("name") or key,
                data.get("description", ""),
                path,
                data["user"],
                {"in_process": key.casefold() in IN_PROCESS},
            )
        )
    items += _union_styles("union" in keys)
    return unique_sorted(items)


def _union_styles(present: bool) -> list[Item]:
    """ "Breeze (Union)" and its sisters: the id is "union/<style>", what the editor writes as
    widgetStyle Union and unionStyle <style>. A style whose metadata.json says `"hidden": true`
    (Breeze Mobile and Breeze Right-to-Left are) is made for other devices and is not offered.
    Union draws the style set in the configuration, so only the default one has a picture."""
    if not present:
        return []
    items = []
    for folder, user in data_folders("union", "styles"):
        try:
            children = sorted(child for child in folder.iterdir() if child.is_dir())
        except OSError:
            continue
        for child in children:
            meta = _union_metadata(child)
            if meta.get("hidden") is True:
                continue
            name = meta.get("name")
            if not isinstance(name, str) or not name.strip():
                name = f"{child.name.replace('-', ' ').title()} (Union)"
            extra = {"in_process": False, "style": "Union", "drawn": child.name == "breeze"}
            items.append(Item(f"union/{child.name}", name.strip(), "", child, user, extra))
    return items


def _union_metadata(folder: Path) -> dict:
    """The metadata.json of a Union style, or an empty dict."""
    import json

    try:
        with (folder / "metadata.json").open(encoding="utf-8") as handle:
            data = json.loads(handle.read(65536))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# Drawing -------------------------------------------------------------------


def _sample(texts: Mapping[str, str]) -> QWidget:
    root = QWidget()
    root.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(0, 0, 0, 0)
    tabs = QTabWidget()
    layout.addWidget(tabs)
    page = QWidget()
    grid = QGridLayout(page)
    grid.setSpacing(5)
    check = QCheckBox(texts["check"])
    check.setChecked(True)
    first = QRadioButton(texts["radio1"])
    first.setChecked(True)
    second = QRadioButton(texts["radio2"])
    combo = QComboBox()
    combo.addItem(texts["combo"])
    button = QPushButton(texts["button"])
    button.setDefault(True)
    grid.addWidget(check, 0, 0)
    grid.addWidget(first, 1, 0)
    grid.addWidget(second, 2, 0)
    grid.addWidget(combo, 0, 1)
    grid.addWidget(button, 1, 1)
    tabs.addTab(page, texts["tab1"])
    tabs.addTab(QWidget(), texts["tab2"])
    return root


def render_panel(
    style_name: str, size: QSize, dpr: float, colors: Mapping[str, str] | None, texts: Mapping[str, str]
) -> QImage:
    """The sample drawn by the style `style_name` on a card of `size`; a null image when the
    style cannot be created or there is no QApplication with widgets. Must run on the GUI thread."""
    import shiboken6

    if not isinstance(QApplication.instance(), QApplication):
        return QImage()
    style = QStyleFactory.create(style_name)
    if style is None:
        return QImage()
    pal = _colors.palette(colors)
    root = _sample(texts)
    try:
        for widget in [root, *root.findChildren(QWidget)]:
            widget.setStyle(style)
            widget.setPalette(pal)
        root.setAutoFillBackground(True)
        root.ensurePolished()
        root.adjustSize()
        natural = root.size()
        card = blank(size, dpr, pal.window().color())
        margin = 8
        scale = min(
            (size.width() - 2 * margin) / max(1, natural.width()),
            (size.height() - 2 * margin) / max(1, natural.height()),
            1.0,
        )
        painter = QPainter(card)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(
            (size.width() - natural.width() * scale) / 2, (size.height() - natural.height() * scale) / 2
        )
        painter.scale(scale, scale)
        root.render(painter, QPoint(0, 0))
        painter.end()
        return card
    finally:
        shiboken6.delete(root)  # before the style it uses goes away


class AppStyles(Kind):
    key = "app_style"
    gui_thread_only = True
    scheme_dependent = True

    def __init__(self):
        self._lock = threading.Lock()
        self._outside: dict[tuple, dict[str, QImage]] = {}
        self._tried = 0.0

    @property
    def title(self) -> str:
        return str(translate("pickers", "Application Style"))

    def on_gui_thread(self, item: Item) -> bool:
        return bool(item.extra.get("in_process"))  # the helper's batch runs on a worker thread

    def items(self) -> list[Item]:
        try:
            return list_styles()
        except Exception:
            return []

    def thumbnail(self, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None) -> QImage:
        try:
            if item.extra.get("drawn") is False:
                return QImage()
            if item.extra.get("in_process"):
                return render_panel(item.id, size, dpr, colors, labels())
            return self._from_helper(item, size, dpr, colors)
        except Exception:
            return QImage()

    def _from_helper(self, item: Item, size: QSize, dpr: float, colors) -> QImage:
        """One helper run draws every style that is not drawn here; the rest are then at hand."""
        batch = (size.width(), size.height(), dpr, tuple(sorted(_colors.complete(colors).items())))
        with self._lock:
            if batch not in self._outside or (
                not self._outside[batch] and time.monotonic() - self._tried > RETRY
            ):
                self._outside = {
                    batch: self._run_helper(size, dpr, colors)
                }  # only the latest batch is of use
                self._tried = time.monotonic()
            return self._outside[batch].get(self._helper_key(item), QImage())

    @staticmethod
    def _helper_key(item: Item) -> str:
        return str(item.extra.get("style", item.id))

    def _outside_ids(self) -> list[str]:
        ids = {self._helper_key(i) for i in self.items() if not i.extra.get("in_process")}
        return sorted(ids)

    def _run_helper(self, size: QSize, dpr: float, colors) -> dict[str, QImage]:
        keys = self._outside_ids()
        spec = {
            "size": [size.width(), size.height()],
            "dpr": dpr,
            "colors": dict(_colors.complete(colors)),
            "labels": labels(),
            "font": QApplication.font().toString(),
            "items": [{"key": str(number), "style": key} for number, key in enumerate(keys)],
        }
        found: dict[str, QImage] = {}
        if not keys:
            return found
        with _process.run("styles", spec) as (out, _code):
            for number, key in enumerate(keys):
                image = QImage(str(out / f"{number}.png")) if out is not None else QImage()
                if not image.isNull():
                    image.setDevicePixelRatio(dpr)
                    found[key] = image
        return found


__all__ = ["AppStyles", "list_styles", "render_panel"]
