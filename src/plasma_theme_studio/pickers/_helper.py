# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The helper process of the pickers. It is started by `_process.run` and never runs on import:

    python -m plasma_theme_studio.pickers._helper MODE SPEC.json OUTDIR

`styles` draws the sample panel with each of the widget styles of SPEC and writes
`<key>.png`. `decorations` draws an active and an inactive window with each of the
decorations of SPEC through the QML types KWin's own settings page uses
(`org.kde.kwin.private.kdecoration`) and writes `<key>-active.png` and
`<key>-inactive.png`, each the frame of the window with the margin of its shadow
around it. A style or a decoration that cannot be drawn leaves its file out.

Whatever the environment says, the helper uses the offscreen platform and the software
Qt Quick backend, and it turns core dumps off before it loads Qt.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DECORATION_MARGIN = 14  # logical pixels of shadow kept around a frame
SLOT_PADDING = 64  # room around a frame in the scene for its shadow
COLUMNS = 3  # decorations per row in the scene
TIMES = (120, 260, 800)  # ms: make the frame wider, set the real size, grab


def _prepare() -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ImportError, ValueError, OSError):
        pass
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ.pop("DISPLAY", None)
    os.environ.pop("WAYLAND_DISPLAY", None)


def draw_styles(spec: dict, out: Path) -> None:
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from .appstyles import render_panel

    app = QApplication(["pts-helper"])
    if spec.get("font"):
        font = app.font()
        font.fromString(spec["font"])  # the host's font, as the host's own thumbnails use it
        app.setFont(font)
    size = QSize(*spec["size"])
    for entry in spec["items"]:
        image = render_panel(entry["style"], size, spec["dpr"], spec["colors"], spec["labels"])
        if not image.isNull():
            image.save(str(out / f"{entry['key']}.png"))
    del app


def _qml(spec: dict, windows: list[dict], width: int, height: int) -> str:
    """The QML scene: for each decoration an active and an inactive window side by side in a
    slot. `width` and `height` are the window's size in the scene's own pixels."""
    slot_w, slot_h = width + 2 * SLOT_PADDING, height + 2 * SLOT_PADDING
    color, caption = spec["window_color"], json.dumps(spec["caption"])
    icon = json.dumps(spec.get("icon", ""))
    parts = ["import QtQuick", "import org.kde.kwin.private.kdecoration", "Item {", "  id: scene"]
    nudge, fit, report = [], [], []
    for number, entry in enumerate(windows):
        # Every id differs from the property names it is used in: a QML id equal to a
        # property name ("settings: settings") crashes the Qt Quick backend.
        x, y = (number % COLUMNS) * 2 * slot_w, (number // COLUMNS) * slot_h
        parts.append(
            f"  Bridge {{ id: br{number}; plugin: {json.dumps(entry['plugin'])}; "
            f"theme: {json.dumps(entry['theme'])} }}"
        )
        parts.append(f"  Settings {{ id: st{number}; bridge: br{number}.bridge }}")
        for tag, active, shift in (("a", "true", 0), ("i", "false", slot_w)):
            name = f"{tag}{number}"
            parts.append(
                f"  Decoration {{ id: {name}; x: {x + shift}; y: {y}; width: {width}; height: {height}; "
                f"bridge: br{number}.bridge; settings: st{number}; windowColor: {json.dumps(color)}\n"
                f"    Component.onCompleted: {{ client.caption = {caption}; client.active = {active}; "
                f"client.iconName = {icon} }} }}"
            )
            nudge.append(f"{name}.width += 1;")
            fit.append(
                f"{{ var s = {name}.shadow; var pw = s ? s.paddingLeft + s.paddingRight : 0; "
                f"var ph = s ? s.paddingTop + s.paddingBottom : 0; {name}.width = {width} + pw; "
                f"{name}.height = {height} + ph; {name}.client.active = {active}; }}"
            )
            report.append(f's = {name}.shadow; r["{name}"] = s ? [s.paddingLeft, s.paddingTop] : [0, 0];')
    # A PreviewItem takes its client size from the item's size when that changes, and it
    # paints the frame inside the item, offset by the padding of the shadow. So it is made
    # first, widened by a pixel, and then set to the frame size plus the padding.
    parts.append(f"  Timer {{ interval: {TIMES[0]}; running: true; onTriggered: {{ {' '.join(nudge)} }} }}")
    parts.append(f"  Timer {{ interval: {TIMES[1]}; running: true; onTriggered: {{ {' '.join(fit)} }} }}")
    parts.append("  property string report: ''")
    parts.append(
        f"  Timer {{ interval: {TIMES[1] + 100}; running: true; onTriggered: {{ var r = {{}}; var s; "
        f"{' '.join(report)} scene.report = JSON.stringify(r) }} }}"
    )
    parts.append("}")
    return "\n".join(parts)


def draw_decorations(spec: dict, out: Path) -> None:
    from PySide6.QtCore import QRect, QTimer, QUrl
    from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, qAlpha
    from PySide6.QtQuick import QQuickView

    windows = spec["items"]
    if not windows:
        return
    dpr, scale = spec["dpr"], spec.get("scale", 1.0)
    # The windows are drawn `scale` times their size in the picture, so that a window of
    # a small picture keeps room for its title between the buttons.
    frame_w, frame_h = spec["frame"]
    width, height = round(frame_w / scale), round(frame_h / scale)
    slot_w, slot_h = width + 2 * SLOT_PADDING, height + 2 * SLOT_PADDING
    os.environ["QT_SCALE_FACTOR"] = str(dpr * scale)  # pixels per pixel of the scene
    scene = out / "scene.qml"
    scene.write_text(_qml(spec, windows, width, height), "utf-8")
    app = QGuiApplication(["pts-helper"])
    if spec.get("icon_theme"):
        QIcon.setThemeName(spec["icon_theme"])
    view = QQuickView()
    view.setColor(QColor(0, 0, 0, 0))
    view.setSource(QUrl.fromLocalFile(str(scene)))
    if view.status() != QQuickView.Status.Ready:
        return
    rows = (len(windows) + COLUMNS - 1) // COLUMNS
    view.resize(min(len(windows), COLUMNS) * 2 * slot_w, rows * slot_h)
    view.show()

    def grab() -> None:
        pads = json.loads(view.rootObject().property("report") or "{}")
        shot = view.grabWindow().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        ratio = shot.width() / view.width()  # device pixels per pixel of the scene
        margin = DECORATION_MARGIN * dpr
        for number, entry in enumerate(windows):
            x0, y0 = (number % COLUMNS) * 2 * slot_w, (number // COLUMNS) * slot_h
            for tag, name, shift in (("a", "active", 0), ("i", "inactive", slot_w)):
                pad_left, pad_top = pads.get(f"{tag}{number}", [0, 0])
                # The frame starts at the padding inside the item; keep a margin of shadow around it.
                piece = shot.copy(
                    QRect(
                        round((x0 + shift + pad_left) * ratio - margin),
                        round((y0 + pad_top) * ratio - margin),
                        round((frame_w + 2 * DECORATION_MARGIN) * dpr),
                        round((frame_h + 2 * DECORATION_MARGIN) * dpr),
                    )
                )
                solid = sum(
                    1
                    for px in range(round(margin), round(margin + frame_w * dpr), 9)
                    for py in range(round(margin), round(margin + frame_h * dpr), 9)
                    if qAlpha(piece.pixel(px, py)) > 200
                )
                if solid:  # an empty frame means the decoration could not be created
                    piece.save(str(out / f"{entry['key']}-{name}.png"))
        app.quit()

    QTimer.singleShot(TIMES[2], grab)
    app.exec()


def main(argv: list[str]) -> int:
    _prepare()
    if len(argv) != 3 or argv[0] not in ("styles", "decorations"):
        return 2
    mode, spec_file, out = argv
    spec = json.loads(Path(spec_file).read_text("utf-8"))
    if mode == "styles":
        draw_styles(spec, Path(out))
    else:
        draw_decorations(spec, Path(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
