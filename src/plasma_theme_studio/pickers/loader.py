# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""`ThumbnailLoader`: thumbnails for a page, without blocking the window.

    loader = ThumbnailLoader(parent)
    loader.ready.connect(on_ready)          # (kind_key, item_id, QImage)
    image = loader.request(kind, item, size, dpr, colors)

`request` returns the QImage at once when it is in memory or on disk, a null
QImage when making it failed less than RETRY seconds ago, and None when it is
being made: `ready` follows later (a null image when making it failed). The
same thumbnail is never made twice at the same time. Kinds that are not
`gui_thread_only` are made on a thread pool (QImage only); the others one per
event-loop turn on the GUI thread (a kind may say so per item, `Kind.on_gui_thread`).
Made pictures are written to the disk cache.

`cancel(kind_key=None)` forgets work that has not started (everything, or one
kind), as a page does when it is left; a render that is already running still
fills the caches but sends no signal. `shutdown()` stops the pool and waits for
it; it kills the helper processes that run, so it does not wait for them, it runs when the
application quits and is safe to call twice. After it,
`request` only answers from memory and disk.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Mapping

from PySide6.QtCore import QCoreApplication, QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from . import _process, cache
from .base import Item, Kind

MEMORY_LIMIT = 512
RETRY = 30  # seconds before a picture that could not be made is tried again


class _Job:
    def __init__(self, kind: Kind, item: Item, size: QSize, dpr: float, colors, name: str):
        self.kind, self.item, self.size, self.dpr, self.colors, self.name = (
            kind,
            item,
            size,
            dpr,
            colors,
            name,
        )
        self.cancelled = False

    def render(self) -> QImage:
        try:
            image = self.kind.thumbnail(self.item, self.size, self.dpr, self.colors)
        except Exception:
            return QImage()
        if image.isNull():
            return QImage()
        image.setDevicePixelRatio(self.dpr)
        cache.put(self.kind.key, self.name, image)
        return image


class _Worker(QRunnable):
    def __init__(self, loader: ThumbnailLoader, job: _Job):
        super().__init__()
        self.setAutoDelete(True)
        self.loader, self.job = loader, job

    def run(self):
        loader = self.loader
        if loader._closed.is_set() or self.job.cancelled:
            return
        image = self.job.render()
        if loader._closed.is_set():
            return
        try:
            loader._finished.emit(self.job, image)
        except RuntimeError:  # the loader is already gone
            pass


class ThumbnailLoader(QObject):
    ready = Signal(str, str, QImage)
    _finished = Signal(object, QImage)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._closed = threading.Event()
        self._memory: OrderedDict[tuple[str, str], QImage] = OrderedDict()
        self._failed: dict[tuple[str, str], float] = {}
        self._pending: dict[tuple[str, str], _Job] = {}
        self._gui_queue: deque[_Job] = deque()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, min(4, QThreadPool.globalInstance().maxThreadCount())))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._render_one)
        self._finished.connect(self._done, Qt.ConnectionType.QueuedConnection)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def request(
        self, kind: Kind, item: Item, size: QSize, dpr: float, colors: Mapping[str, str] | None = None
    ) -> QImage | None:
        colors = dict(colors) if colors and kind.scheme_dependent else None
        name = cache.key(item, size, dpr, colors)
        slot = (kind.key, name)
        if slot in self._memory:
            self._memory.move_to_end(slot)
            return self._memory[slot]
        image = cache.get(kind.key, name, dpr)
        if image is not None:
            self._remember(slot, image)
            return image
        if self._closed.is_set():
            return QImage()
        failed = self._failed.get(slot)
        if failed is not None:
            if time.monotonic() - failed < RETRY:
                return QImage()
            del self._failed[slot]
        if slot in self._pending:
            return None
        job = _Job(kind, item, QSize(size), dpr, colors, name)
        self._pending[slot] = job
        if kind.on_gui_thread(item):
            self._gui_queue.append(job)
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._pool.start(_Worker(self, job))
        return None

    def cancel(self, kind_key: str | None = None) -> None:
        for slot, job in list(self._pending.items()):
            if kind_key is None or slot[0] == kind_key:
                job.cancelled = True
                del self._pending[slot]
        self._gui_queue = deque(job for job in self._gui_queue if not job.cancelled)

    def shutdown(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        self._timer.stop()
        self._gui_queue.clear()
        for job in self._pending.values():
            job.cancelled = True
        self._pending.clear()
        self._pool.clear()
        _process.terminate_all()  # a helper batch must not keep the application open
        self._pool.waitForDone()

    def _remember(self, slot, image: QImage) -> None:
        self._memory[slot] = image
        while len(self._memory) > MEMORY_LIMIT:
            self._memory.popitem(last=False)

    @Slot()
    def _render_one(self) -> None:
        if self._gui_queue and not self._closed.is_set():
            job = self._gui_queue.popleft()
            if not job.cancelled:
                self._done(job, job.render())
        if self._gui_queue and not self._closed.is_set():
            self._timer.start()

    @Slot(object, QImage)
    def _done(self, job: _Job, image: QImage) -> None:
        slot = (job.kind.key, job.name)
        if self._pending.get(slot) is job:
            del self._pending[slot]
        if self._closed.is_set():
            return
        if image.isNull():
            self._failed[slot] = time.monotonic()  # tried again after RETRY, not at every paint
        else:
            self._remember(slot, image)
        if not job.cancelled:
            self.ready.emit(job.kind.key, job.item.id, image)
