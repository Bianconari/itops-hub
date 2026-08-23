"""MetricsPoller — periodic live-metrics collection on a QThread.

The UI thread only receives queued signals; psutil work happens here. The
loop is a plain wait-on-event cycle so ``stop()`` is prompt and safe.
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class MetricsPoller(QThread):
    """Repeatedly calls ``collect_fn`` off-thread and emits its results."""

    result_ready = Signal(object)
    poll_failed = Signal(str)

    def __init__(self, collect_fn, interval_ms: int = 2000, parent=None) -> None:
        super().__init__(parent)
        self._collect_fn = collect_fn
        self._interval_ms = max(500, interval_ms)
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                result = self._collect_fn()
            except Exception as exc:
                logger.exception("live metrics collection failed")
                self.poll_failed.emit(f"{exc}")
            else:
                self.result_ready.emit(result)
            self._stop_event.wait(self._interval_ms / 1000.0)

    def stop(self) -> None:
        self._stop_event.set()

    def wait_stopped(self, timeout_ms: int = 5000) -> None:
        self.wait(timeout_ms)
