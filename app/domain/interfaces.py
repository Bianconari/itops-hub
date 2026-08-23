"""Interfaces (Protocols) that the infrastructure layer implements.

Services depend on these Protocols only — never on concrete storage — so they
can be unit-tested with in-memory fakes and the storage backend (SQLite now,
PostgreSQL later) can be swapped without touching business logic.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.entities import ActivityEntry


class SettingsStore(Protocol):
    """Raw settings document storage (JSON string, single document)."""

    def load_raw(self) -> str | None: ...

    def save_raw(self, document: str) -> None: ...


class ActivityStore(Protocol):
    """Persistence for audit/activity log entries."""

    def append(self, entry: ActivityEntry) -> ActivityEntry: ...

    def recent(self, limit: int = 100) -> list[ActivityEntry]: ...
