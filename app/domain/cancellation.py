"""Cooperative cancellation primitive shared by all long-running services.

Services check the token inside their work loops (cooperative cancellation);
UI workers and API endpoints create and cancel tokens. This keeps services
Qt-free and unit-testable while still being cancellable.
"""

from __future__ import annotations

import threading


class OperationCancelled(RuntimeError):
    """Raised inside a service when its CancelToken has been cancelled."""


class CancelToken:
    """Thread-safe, one-way cancellation flag."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until cancelled; returns True if cancelled within timeout."""
        return self._event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise OperationCancelled("Operation was cancelled")
