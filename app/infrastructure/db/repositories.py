"""SQLAlchemy repositories implementing the domain store Protocols.

Only repositories currently consumed by services exist here (no dead code);
more arrive with their milestones (devices/monitoring + alert writes v0.6,
backups v1.2).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.entities import ActivityEntry, ActivityStatus, AlertRecord, Severity
from app.domain.system import SystemSnapshotEntity
from app.domain.time_utils import utc_now
from app.infrastructure.db.models import (
    ActivityLogModel,
    AlertModel,
    SettingModel,
    SystemSnapshotModel,
)

_SETTINGS_KEY = "app.settings"


class SettingRepository:
    """Raw settings document storage (single JSON document)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_raw(self) -> str | None:
        row = self._session.get(SettingModel, _SETTINGS_KEY)
        return row.value if row is not None else None

    def save_raw(self, document: str) -> None:
        row = self._session.get(SettingModel, _SETTINGS_KEY)
        if row is None:
            row = SettingModel(key=_SETTINGS_KEY, value=document)
            self._session.add(row)
        else:
            row.value = document
            row.updated_at = utc_now()
        self._session.commit()


class ActivityRepository:
    """Audit/activity log storage."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, entry: ActivityEntry) -> ActivityEntry:
        row = ActivityLogModel(
            timestamp=entry.timestamp,
            action=entry.action,
            module=entry.module,
            status=entry.status.value,
            message=entry.message,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return _to_activity_entity(row)

    def recent(self, limit: int = 100) -> list[ActivityEntry]:
        rows = (
            self._session.query(ActivityLogModel)
            .order_by(ActivityLogModel.timestamp.desc(), ActivityLogModel.id.desc())
            .limit(limit)
            .all()
        )
        return [_to_activity_entity(row) for row in rows]


def _to_activity_entity(row: ActivityLogModel) -> ActivityEntry:
    return ActivityEntry(
        id=row.id,
        timestamp=row.timestamp,
        action=row.action,
        module=row.module,
        status=ActivityStatus(row.status),
        message=row.message,
    )


class SystemSnapshotRepository:
    """Persistence for periodic system snapshots."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, snapshot: SystemSnapshotEntity) -> SystemSnapshotEntity:
        row = SystemSnapshotModel(
            timestamp=snapshot.timestamp,
            cpu_percent=snapshot.cpu_percent,
            memory_percent=snapshot.memory_percent,
            disk_percent=snapshot.disk_percent,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return _to_snapshot_entity(row)

    def query_range(
        self, start: datetime, end: datetime, limit: int = 5000
    ) -> list[SystemSnapshotEntity]:
        rows = self._session.scalars(
            select(SystemSnapshotModel)
            .where(
                SystemSnapshotModel.timestamp >= start,
                SystemSnapshotModel.timestamp <= end,
            )
            .order_by(SystemSnapshotModel.timestamp.asc())
            .limit(limit)
        ).all()
        return [_to_snapshot_entity(row) for row in rows]

    def prune_older_than(self, cutoff: datetime) -> int:
        result = self._session.execute(
            delete(SystemSnapshotModel).where(SystemSnapshotModel.timestamp < cutoff)
        )
        self._session.commit()
        return int(getattr(result, "rowcount", 0) or 0)


def _to_snapshot_entity(row: SystemSnapshotModel) -> SystemSnapshotEntity:
    return SystemSnapshotEntity(
        id=row.id,
        timestamp=row.timestamp,
        cpu_percent=row.cpu_percent,
        memory_percent=row.memory_percent,
        disk_percent=row.disk_percent,
    )


class AlertRepository:
    """Alert persistence (read path; raise/ack arrive in v0.6)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def recent(self, limit: int = 100) -> list[AlertRecord]:
        rows = (
            self._session.query(AlertModel)
            .order_by(AlertModel.created_at.desc(), AlertModel.id.desc())
            .limit(limit)
            .all()
        )
        return [_to_alert_entity(row) for row in rows]


def _to_alert_entity(row: AlertModel) -> AlertRecord:
    return AlertRecord(
        id=row.id,
        type=row.type,
        severity=Severity(row.severity),
        source=row.source,
        message=row.message,
        created_at=row.created_at,
        acknowledged=row.acknowledged,
        acknowledged_at=row.acknowledged_at,
    )
