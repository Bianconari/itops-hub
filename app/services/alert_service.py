"""Alert service — read feed for existing alerts.

v0.3/v0.4 only expose the read path used by the dashboard. Raising, deduping,
and acknowledging alerts arrives with the monitoring module in v0.6; the
dashboard panel then fills with real data instead of the honest empty state.
"""

from __future__ import annotations

from app.domain.entities import AlertRecord
from app.domain.interfaces import AlertStore


class AlertService:
    def __init__(self, store: AlertStore) -> None:
        self._store = store

    def recent(self, limit: int = 8) -> list[AlertRecord]:
        """Most recent alerts, newest first."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return self._store.recent(limit=limit)
