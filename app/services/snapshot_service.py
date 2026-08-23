"""System snapshot service — persistence, history queries, retention.

Snapshots feed the dashboard history chart and long-term trends; retention
keeps the local database bounded (default 30 days, configurable).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.domain.interfaces import SystemSnapshotStore
from app.domain.system import LiveMetrics, SystemSnapshotEntity
from app.domain.time_utils import utc_now

logger = logging.getLogger(__name__)


class SnapshotService:
    def __init__(self, store: SystemSnapshotStore) -> None:
        self._store = store

    def record(self, metrics: LiveMetrics) -> SystemSnapshotEntity:
        """Persist one snapshot from live metrics; returns the stored row."""
        snapshot = SystemSnapshotEntity(
            timestamp=metrics.timestamp,
            cpu_percent=metrics.cpu_percent,
            memory_percent=metrics.memory_percent,
            disk_percent=metrics.disk_percent_max,
        )
        stored = self._store.add(snapshot)
        logger.debug("snapshot recorded at %s", stored.timestamp)
        return stored

    def history(self, hours: float = 1.0, limit: int = 5000) -> list[SystemSnapshotEntity]:
        """Snapshots from the last ``hours`` hours, oldest first."""
        if hours <= 0:
            raise ValueError("hours must be positive")
        end = utc_now()
        start = end - timedelta(hours=hours)
        return self._store.query_range(start, end, limit=limit)

    def history_between(
        self, start: datetime, end: datetime, limit: int = 5000
    ) -> list[SystemSnapshotEntity]:
        """Snapshots in an explicit window, oldest first."""
        if start > end:
            raise ValueError("start must not be after end")
        return self._store.query_range(start, end, limit=limit)

    def apply_retention(self, retention_days: int) -> int:
        """Delete snapshots older than ``retention_days`` days; returns count."""
        if retention_days < 1:
            raise ValueError("retention_days must be >= 1")
        cutoff = utc_now() - timedelta(days=retention_days)
        deleted = self._store.prune_older_than(cutoff)
        if deleted:
            logger.info("retention: pruned %d snapshots older than %s", deleted, cutoff)
        return deleted
