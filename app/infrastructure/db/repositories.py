"""SQLAlchemy repositories implementing the domain store Protocols.

Only repositories currently consumed by services exist here (no dead code);
more arrive with their milestones (snapshots v0.4, devices/monitoring/alerts
v0.6, backups v1.2).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.entities import ActivityEntry, ActivityStatus
from app.domain.time_utils import utc_now
from app.infrastructure.db.models import ActivityLogModel, SettingModel

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
