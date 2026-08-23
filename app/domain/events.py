"""In-process event bus and domain event types.

The bus is deliberately simple: synchronous publish, thread-safe subscribe.
Publishing happens in worker threads (monitoring, scans); UI subscribers must
bridge to the Qt main thread themselves (queued signals) — the bus stays
Qt-free so it can also serve the local API process.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

Subscriber = Callable[[Any], None]


class Topics:
    """Canonical event topic names."""

    SETTINGS_CHANGED = "settings.changed"
    APP_STARTED = "app.started"
    APP_STOPPED = "app.stopped"
    SCAN_COMPLETED = "scan.completed"
    MONITOR_RESULT = "monitor.result"
    ALERT_RAISED = "alert.raised"
    BACKUP_COMPLETED = "backup.completed"


@dataclass(frozen=True)
class Event:
    """Base domain event."""

    topic: str
    payload: Any = None


@dataclass(frozen=True)
class SettingsChanged:
    """Fields that changed in the settings store (top-level keys)."""

    fields: tuple[str, ...] = field(default_factory=tuple)


class EventBus:
    """Minimal synchronous publish/subscribe bus."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[Subscriber]] = {}

    def subscribe(self, topic: str, callback: Subscriber) -> None:
        with self._lock:
            self._subscribers.setdefault(topic, []).append(callback)

    def unsubscribe(self, topic: str, callback: Subscriber) -> None:
        with self._lock:
            callbacks = self._subscribers.get(topic, [])
            if callback in callbacks:
                callbacks.remove(callback)

    def publish(self, topic: str, payload: Any = None) -> None:
        with self._lock:
            callbacks = list(self._subscribers.get(topic, ()))
        for callback in callbacks:
            try:
                callback(payload)
            except Exception:
                logger.exception("Event bus subscriber failed for topic '%s'", topic)
