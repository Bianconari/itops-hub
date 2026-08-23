"""Interfaces (Protocols) that the infrastructure layer implements.

Services depend on these Protocols only — never on concrete storage — so they
can be unit-tested with in-memory fakes and the storage backend (SQLite now,
PostgreSQL later) can be swapped without touching business logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.entities import ActivityEntry, AlertRecord
from app.domain.system import DriveUsage, LiveMetrics, SystemInfo, SystemSnapshotEntity


class SettingsStore(Protocol):
    """Raw settings document storage (JSON string, single document)."""

    def load_raw(self) -> str | None: ...

    def save_raw(self, document: str) -> None: ...


class ActivityStore(Protocol):
    """Persistence for audit/activity log entries."""

    def append(self, entry: ActivityEntry) -> ActivityEntry: ...

    def recent(self, limit: int = 100) -> list[ActivityEntry]: ...


class AlertStore(Protocol):
    """Persistence for raised alerts (read path; raise/ack land in v0.6)."""

    def recent(self, limit: int = 100) -> list[AlertRecord]: ...


class SystemMetricsSource(Protocol):
    """OS adapter supplying local system facts and live metrics (psutil)."""

    def static_info(self) -> SystemInfo: ...

    def live_metrics(self) -> LiveMetrics: ...

    def drive_usages(self) -> list[DriveUsage]: ...


class SystemSnapshotStore(Protocol):
    """Persistence for periodic system snapshots."""

    def add(self, snapshot: SystemSnapshotEntity) -> SystemSnapshotEntity: ...

    def query_range(
        self, start: datetime, end: datetime, limit: int = 5000
    ) -> list[SystemSnapshotEntity]: ...

    def prune_older_than(self, cutoff: datetime) -> int: ...
