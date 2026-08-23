"""OneShotWorker — runs a callable once on a QThread, emits result or error.

Used for short, possibly-blocking service calls (collecting static system
info, exports, ...) so the UI thread never freezes. The callable itself is a
service method; no logic lives here.

Implementation note: a QThread subclass (object lives in the main thread,
``run()`` executes in the worker thread) avoids the moveToThread/deleteLater
destruction races that can abort the process during teardown.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class OneShotWorker(QThread):
    """Fire-and-forget background call.

    Signals are emitted from the worker thread and delivered queued to main-
    thread receivers. The owner keeps a reference and may call ``wait()``
    before teardown; slots typically clear that reference on completion.
    """

    succeeded = Signal(object)  # callable result
    failed = Signal(str)  # user-presentable error message

    def __init__(self, fn, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:
            logger.exception("OneShotWorker task failed")
            self.failed.emit(f"{exc}")
        else:
            self.succeeded.emit(result)
