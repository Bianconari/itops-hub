"""SQLAlchemy repositories implementing the domain store Protocols.

Every method opens its own short session (unit of work). This is required
for correctness: services run on worker threads (monitor rounds, scans,
backups) and a shared SQLAlchemy session is not thread-safe. SQLite in WAL
mode handles the resulting short concurrent readers/writers well.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.domain.entities import ActivityEntry, ActivityStatus, AlertRecord, Severity
from app.domain.monitoring import Device, MonitorResult, MonitorState
from app.domain.system import SystemSnapshotEntity
from app.domain.time_utils import utc_now
from app.infrastructure.db.models import (
    ActivityLogModel,
    AlertModel,
    DeviceModel,
    MonitoringResultModel,
    SettingModel,
    SystemSnapshotModel,
)

_SETTINGS_KEY = "app.settings"
SessionFactory = Callable[[], Session]


class SettingRepository:
    """Raw settings document storage (single JSON document)."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    def load_raw(self) -> str | None:
        with self._sessions() as session:
            row = session.get(SettingModel, _SETTINGS_KEY)
            return row.value if row is not None else None

    def save_raw(self, document: str) -> None:
        with self._sessions() as session:
            row = session.get(SettingModel, _SETTINGS_KEY)
            if row is None:
                session.add(SettingModel(key=_SETTINGS_KEY, value=document))
            else:
                row.value = document
                row.updated_at = utc_now()
            session.commit()


class ActivityRepository:
    """Audit/activity log storage."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    def append(self, entry: ActivityEntry) -> ActivityEntry:
        with self._sessions() as session:
            row = ActivityLogModel(
                timestamp=entry.timestamp,
                action=entry.action,
                module=entry.module,
                status=entry.status.value,
                message=entry.message,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_activity_entity(row)

    def recent(self, limit: int = 100) -> list[ActivityEntry]:
        with self._sessions() as session:
            rows = (
                session.query(ActivityLogModel)
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

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    def add(self, snapshot: SystemSnapshotEntity) -> SystemSnapshotEntity:
        with self._sessions() as session:
            row = SystemSnapshotModel(
                timestamp=snapshot.timestamp,
                cpu_percent=snapshot.cpu_percent,
                memory_percent=snapshot.memory_percent,
                disk_percent=snapshot.disk_percent,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_snapshot_entity(row)

    def query_range(
        self, start: datetime, end: datetime, limit: int = 5000
    ) -> list[SystemSnapshotEntity]:
        with self._sessions() as session:
            rows = session.scalars(
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
        with self._sessions() as session:
            result = session.execute(
                delete(SystemSnapshotModel).where(SystemSnapshotModel.timestamp < cutoff)
            )
            session.commit()
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
    """Alert persistence: raise (dedup support), list, acknowledge."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    def add(self, alert: AlertRecord) -> AlertRecord:
        with self._sessions() as session:
            row = AlertModel(
                type=alert.type,
                severity=alert.severity.value,
                source=alert.source,
                message=alert.message,
                created_at=alert.created_at,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_alert_entity(row)

    def recent(self, limit: int = 100) -> list[AlertRecord]:
        with self._sessions() as session:
            rows = (
                session.query(AlertModel)
                .order_by(AlertModel.created_at.desc(), AlertModel.id.desc())
                .limit(limit)
                .all()
            )
            return [_to_alert_entity(row) for row in rows]

    def unacknowledged(self, limit: int = 100) -> list[AlertRecord]:
        with self._sessions() as session:
            rows = (
                session.query(AlertModel)
                .where(AlertModel.acknowledged.is_(False))
                .order_by(AlertModel.created_at.desc(), AlertModel.id.desc())
                .limit(limit)
                .all()
            )
            return [_to_alert_entity(row) for row in rows]

    def find_unacknowledged(self, alert_type: str, source: str) -> AlertRecord | None:
        with self._sessions() as session:
            row = (
                session.query(AlertModel)
                .where(
                    AlertModel.type == alert_type,
                    AlertModel.source == source,
                    AlertModel.acknowledged.is_(False),
                )
                .order_by(AlertModel.created_at.desc())
                .first()
            )
            return _to_alert_entity(row) if row is not None else None

    def acknowledge(self, alert_id: int) -> bool:
        with self._sessions() as session:
            result = session.execute(
                update(AlertModel)
                .where(AlertModel.id == alert_id, AlertModel.acknowledged.is_(False))
                .values(acknowledged=True, acknowledged_at=utc_now())
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0) > 0


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


class DeviceRepository:
    """CRUD for monitored devices."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    def list_all(self) -> list[Device]:
        with self._sessions() as session:
            rows = session.query(DeviceModel).order_by(DeviceModel.name.asc()).all()
            return [_to_device_entity(row) for row in rows]

    def get(self, device_id: int) -> Device | None:
        with self._sessions() as session:
            row = session.get(DeviceModel, device_id)
            return _to_device_entity(row) if row is not None else None

    def get_by_name(self, name: str) -> Device | None:
        with self._sessions() as session:
            row = session.query(DeviceModel).where(DeviceModel.name == name).first()
            return _to_device_entity(row) if row is not None else None

    def add(self, device: Device) -> Device:
        with self._sessions() as session:
            row = DeviceModel(
                name=device.name,
                host=device.host,
                type=device.type,
                enabled=device.enabled,
                interval_seconds=device.interval_seconds,
                timeout_ms=device.timeout_ms,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_device_entity(row)

    def update(self, device: Device) -> Device:
        if device.id is None:
            raise ValueError("device id is required to update")
        with self._sessions() as session:
            row = session.get(DeviceModel, device.id)
            if row is None:
                raise ValueError(f"device {device.id} does not exist")
            row.name = device.name
            row.host = device.host
            row.enabled = device.enabled
            row.interval_seconds = device.interval_seconds
            row.timeout_ms = device.timeout_ms
            row.updated_at = utc_now()
            session.commit()
            session.refresh(row)
            return _to_device_entity(row)

    def delete(self, device_id: int) -> bool:
        with self._sessions() as session:
            row = session.get(DeviceModel, device_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True


def _to_device_entity(row: DeviceModel) -> Device:
    return Device(
        id=row.id,
        name=row.name,
        host=row.host,
        type=row.type,
        enabled=row.enabled,
        interval_seconds=row.interval_seconds,
        timeout_ms=row.timeout_ms,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class MonitoringResultRepository:
    """Persistence for device check results."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    def add(self, result: MonitorResult) -> MonitorResult:
        with self._sessions() as session:
            row = MonitoringResultModel(
                device_id=result.device_id,
                timestamp=result.timestamp,
                status=result.status.value,
                response_time_ms=result.response_time_ms,
                error_message=result.error_message,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_monitor_entity(row)

    def latest_for_devices(self, device_ids: list[int]) -> dict[int, MonitorResult]:
        if not device_ids:
            return {}
        with self._sessions() as session:
            latest_ids = (
                select(func.max(MonitoringResultModel.id))
                .where(MonitoringResultModel.device_id.in_(device_ids))
                .group_by(MonitoringResultModel.device_id)
                .scalar_subquery()
            )
            rows = (
                session.query(MonitoringResultModel)
                .filter(MonitoringResultModel.id.in_(latest_ids))
                .all()
            )
            return {row.device_id: _to_monitor_entity(row) for row in rows}

    def history(
        self, device_id: int, start: datetime, end: datetime, limit: int = 5000
    ) -> list[MonitorResult]:
        with self._sessions() as session:
            rows = (
                session.query(MonitoringResultModel)
                .where(
                    MonitoringResultModel.device_id == device_id,
                    MonitoringResultModel.timestamp >= start,
                    MonitoringResultModel.timestamp <= end,
                )
                .order_by(MonitoringResultModel.timestamp.asc())
                .limit(limit)
                .all()
            )
            return [_to_monitor_entity(row) for row in rows]

    def consecutive_failures(self, device_id: int) -> int:
        with self._sessions() as session:
            rows = (
                session.query(MonitoringResultModel.status)
                .where(MonitoringResultModel.device_id == device_id)
                .order_by(MonitoringResultModel.timestamp.desc(), MonitoringResultModel.id.desc())
                .limit(200)
                .all()
            )
            failures = 0
            for (status,) in rows:
                if status == MonitorState.OFFLINE.value:
                    failures += 1
                else:
                    break
            return failures

    def prune_older_than(self, cutoff: datetime) -> int:
        with self._sessions() as session:
            result = session.execute(
                delete(MonitoringResultModel).where(MonitoringResultModel.timestamp < cutoff)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


def _to_monitor_entity(row: MonitoringResultModel) -> MonitorResult:
    return MonitorResult(
        id=row.id,
        device_id=row.device_id,
        timestamp=row.timestamp,
        status=MonitorState(row.status),
        response_time_ms=row.response_time_ms,
        error_message=row.error_message,
    )
