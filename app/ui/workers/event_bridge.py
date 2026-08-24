"""EventBus → Qt signal bridge.

Domain events are published from worker threads (scheduler pool, monitor
rounds); Qt widgets may only be touched from the main thread. Emitting a
Qt signal from any thread is safe — delivery to main-thread receivers is
queued automatically. The bridge therefore subscribes to the bus and
re-emits as signals, keeping every view thread-safe.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from app.domain.events import EventBus, Topics

logger = logging.getLogger(__name__)


class EventBusBridge(QObject):
    alert_raised = Signal(object)  # AlertRecord

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = bus
        self._bus.subscribe(Topics.ALERT_RAISED, self._on_alert)

    def _on_alert(self, alert: object) -> None:
        self.alert_raised.emit(alert)

    def detach(self) -> None:
        """Unsubscribe (call on window teardown to avoid dangling links)."""
        self._bus.unsubscribe(Topics.ALERT_RAISED, self._on_alert)
