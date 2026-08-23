"""Time helpers.

All timestamps in ITOps Hub are stored as naive UTC ``datetime`` objects.
SQLite has no real timezone support, so we normalize on write/read rather
than mixing aware and naive values. Convert to local time only at the UI
edge.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Current UTC time as a naive datetime (see module docstring)."""
    return datetime.now(UTC).replace(tzinfo=None)
