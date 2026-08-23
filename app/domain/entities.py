"""Domain entities (pure data, no ORM)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ActivityStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    INFO = "info"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ActivityEntry:
    """One auditable application action (audit/activity log row)."""

    timestamp: datetime
    action: str
    module: str
    status: ActivityStatus
    message: str | None = None
    id: int | None = None


@dataclass(frozen=True)
class AlertRecord:
    """A raised alert (disk threshold, device offline, log anomaly, ...)."""

    type: str
    severity: Severity
    source: str
    message: str
    created_at: datetime
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    id: int | None = None
