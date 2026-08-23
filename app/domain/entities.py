"""Domain entities (pure data, no ORM)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ActivityStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    INFO = "info"


@dataclass(frozen=True)
class ActivityEntry:
    """One auditable application action (audit/activity log row)."""

    timestamp: datetime
    action: str
    module: str
    status: ActivityStatus
    message: str | None = None
    id: int | None = None
