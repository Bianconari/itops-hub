"""Alert service — raise, deduplicate, acknowledge, list.

Dedup rule: at most one unacknowledged alert per (type, source) pair, so a
flapping condition never floods the inbox. Recovery handling (auto-ack when
a condition clears) is invoked by the raisers (disk/monitor services).
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.domain.entities import AlertRecord, Severity
from app.domain.events import EventBus, Topics
from app.domain.interfaces import AlertStore
from app.domain.time_utils import utc_now

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self, store: AlertStore, bus: EventBus | None = None) -> None:
        self._store = store
        self._bus = bus

    def raise_alert(
        self,
        alert_type: str,
        severity: Severity,
        source: str,
        message: str,
    ) -> AlertRecord | None:
        """Raise an alert unless an unacknowledged one already exists.

        Returns the new alert, or None when deduplicated away.
        """
        if not alert_type or not source or not message:
            raise ValueError("type, source and message are required")
        severity = Severity(severity)  # accept enum value or raw string
        existing = self._store.find_unacknowledged(alert_type, source)
        if existing is not None:
            return None
        alert = AlertRecord(
            type=alert_type,
            severity=severity,
            source=source,
            message=message,
            created_at=utc_now(),
        )
        stored = self._store.add(alert)
        logger.info("alert raised: [%s] %s/%s", severity.value, alert_type, source)
        if self._bus is not None:
            self._bus.publish(Topics.ALERT_RAISED, stored)
        return stored

    def resolve_alerts(self, alert_type: str, source: str) -> int:
        """Auto-acknowledge open alerts of a condition that has cleared."""
        open_alert = self._store.find_unacknowledged(alert_type, source)
        if open_alert is None:
            return 0
        self._store.acknowledge(open_alert.id)  # type: ignore[arg-type]
        return 1

    def acknowledge(self, alert_id: int) -> bool:
        return self._store.acknowledge(alert_id)

    def recent(self, limit: int = 100) -> list[AlertRecord]:
        return self._store.recent(limit=limit)

    def unacknowledged(self, limit: int = 100) -> list[AlertRecord]:
        return self._store.unacknowledged(limit=limit)

    @staticmethod
    def format_timestamp(alert: AlertRecord) -> datetime:
        return alert.created_at
