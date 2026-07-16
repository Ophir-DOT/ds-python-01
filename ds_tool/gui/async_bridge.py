"""Bridge the asyncio backend to the Qt event loop.

`AsyncTaskWorker` runs a coroutine on its own thread via `asyncio.run` and emits
Qt signals for progress / result / failure. Cross-thread signal delivery uses
queued connections, so slots run safely on the GUI thread.

`run_async` is the convenience entry point used by tabs. In demo mode it runs
the coroutine synchronously on the GUI thread (fast canned work) so scripted
tests and screen recordings are deterministic.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from PySide6.QtCore import QThread, Signal

ProgressCb = Callable[[str], None]
CoroFactory = Callable[[ProgressCb], Awaitable[object]]


class AsyncTaskWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(object)

    def __init__(self, coro_factory: CoroFactory, parent=None) -> None:
        super().__init__(parent)
        self._coro_factory = coro_factory

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            result = asyncio.run(self._coro_factory(self.progress.emit))
        except Exception as exc:  # surfaced to the UI via the `failed` signal
            self.failed.emit(exc)
            return
        self.finished_ok.emit(result)


# Keep references so workers aren't garbage-collected mid-run.
_LIVE_WORKERS: set[AsyncTaskWorker] = set()


def run_async(
    parent,
    coro_factory: CoroFactory,
    *,
    on_progress: ProgressCb | None = None,
    on_done: Callable[[object], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    sync: bool = False,
) -> AsyncTaskWorker | None:
    """Run an async backend coroutine, wiring results back to Qt callbacks."""
    if sync:
        try:
            result = asyncio.run(coro_factory(on_progress or (lambda _m: None)))
        except Exception as exc:
            if on_error:
                on_error(exc)
            return None
        if on_done:
            on_done(result)
        return None

    worker = AsyncTaskWorker(coro_factory, parent)
    if on_progress:
        worker.progress.connect(on_progress)
    if on_done:
        worker.finished_ok.connect(on_done)
    if on_error:
        worker.failed.connect(on_error)

    def _cleanup() -> None:
        _LIVE_WORKERS.discard(worker)

    worker.finished.connect(_cleanup)
    _LIVE_WORKERS.add(worker)
    worker.start()
    return worker
