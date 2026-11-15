# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The program that draws a picture somebody else made (see `svgsandbox`). Run as
`python -P -m plasma_theme_studio.ui.frame_child MEMORY CPU_SECONDS`: the job (one line of JSON) and the SVG
come on standard input, one PNG goes out on standard output. It limits itself first, before it loads Qt.
Exit code 3 means Qt cannot read the picture; anything else that is not 0 is a crash or a kill."""

from __future__ import annotations

import json
import os
import sys


def _limit(memory: int, seconds: int) -> None:
    import resource

    for which, value in (
        (resource.RLIMIT_AS, memory),
        (resource.RLIMIT_CPU, seconds),
        (resource.RLIMIT_CORE, 0),
    ):
        try:
            resource.setrlimit(which, (value, value))
        except (ValueError, OSError):
            pass


def main(argv: list[str]) -> int:
    _limit(int(argv[1]), int(argv[2]))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    stdin = sys.stdin.buffer
    job = json.loads(stdin.readline())
    svg = stdin.read()
    from .. import svgsandbox

    width, height, places = svgsandbox.layout(job)  # refuses a job that asks for too much
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF
    from PySide6.QtGui import QGuiApplication, QImage, QPainter

    application = QGuiApplication([])  # noqa: F841 - Qt needs it alive
    from . import frame_render

    renderer = frame_render.renderer_for(svg.decode("utf-8"))
    if renderer is None:
        return 3
    ratio = float(job["ratio"])
    sheet = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    sheet.fill(0)
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pad = svgsandbox.PAD
    for (frame_width, frame_height, guides), (x, y, cell_width, cell_height) in zip(
        job["tiles"], places, strict=True
    ):
        painter.save()
        painter.setClipRect(QRectF(x, y, cell_width, cell_height))
        painter.translate(x, y)
        painter.scale(ratio, ratio)
        frame = QRectF(pad, pad, frame_width, frame_height)
        frame_render.draw_frame(renderer, painter, frame, guides=bool(guides))
        painter.restore()
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    sheet.save(buffer, "PNG")
    sys.stdout.buffer.write(bytes(data))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
