"""Activity/audit log service.

Records important application actions (scans, backups, alerts, settings
changes, startup/shutdown) to the activity store. Messages are sanitized
before persistence; the service never logs credentials by construction.
"""

from __future__ import annotations

import logging

from app.domain.entities import ActivityEntry, ActivityStatus
from app.domain.interfaces import ActivityStore
from app.domain.sanitization import sanitize_text

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 2000


class ActivityLogService:
    """High-level API for writing audit entries."""

    def __init__(self, store: ActivityStore) -> None:
        self._store = store

    def record(
        self,
        action: str,
        module: str,
        status: ActivityStatus = ActivityStatus.INFO,
        message: str | None = None,
    ) -> ActivityEntry:
        """Persist one audit entry; returns the stored entry (with id).

        Args:
            action: short machine-friendly action name, e.g. ``settings.updated``.
            module: originating module, e.g. ``settings``.
            status: success / failure / info.
            message: optional human-readable detail (sanitized + truncated).
        """
        if not action or not module:
            raise ValueError("action and module are required")
        status = ActivityStatus(status)  # accept enum value or raw string
        cleaned = sanitize_text(message)
        if cleaned is not None and len(cleaned) > _MAX_MESSAGE_LENGTH:
            cleaned = cleaned[:_MAX_MESSAGE_LENGTH] + "…[truncated]"
        from app.domain.time_utils import utc_now

        entry = ActivityEntry(
            timestamp=utc_now(),
            action=action,
            module=module,
            status=status,
            message=cleaned,
        )
        stored = self._store.append(entry)
        logger.debug("activity: %s/%s %s", module, action, status.value)
        return stored

    def recent(self, limit: int = 100) -> list[ActivityEntry]:
        """Most recent audit entries, newest first."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return self._store.recent(limit=limit)
