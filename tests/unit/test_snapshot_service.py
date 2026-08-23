"""Unit tests — SnapshotService with an in-memory store."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.domain.time_utils import utc_now
from app.services.snapshot_service import SnapshotService
from tests.fakes import FakeSnapshotStore, make_metrics


@pytest.fixture
def store():
    return FakeSnapshotStore()


class TestRecord:
    def test_record_persists_fields(self, store):
        service = SnapshotService(store)
        metrics = make_metrics(cpu=11.0, memory=22.0, disk=33.0)
        stored = service.record(metrics)
        assert stored.id == 1
        assert stored.cpu_percent == 11.0
        assert stored.memory_percent == 22.0
        assert stored.disk_percent == 33.0
        assert store.rows[0].timestamp == metrics.timestamp


class TestHistory:
    def test_history_returns_window_oldest_first(self, store):
        service = SnapshotService(store)
        base = utc_now()
        for offset in (120, 60, 30):  # deliberately out of order
            metrics = make_metrics(timestamp=base - timedelta(seconds=offset))
            service.record(metrics)
        recent = service.history(hours=1.0)
        assert [row.timestamp for row in recent] == sorted(row.timestamp for row in recent)
        assert len(recent) == 3
        # Explicit 45-second window keeps only the newest (30s-old) snapshot.
        narrow = service.history_between(base - timedelta(seconds=45), base)
        assert narrow == [store.rows[-1]]

    def test_history_rejects_non_positive(self, store):
        with pytest.raises(ValueError):
            SnapshotService(store).history(hours=0)

    def test_history_between_validates_order(self, store):
        service = SnapshotService(store)
        now = utc_now()
        with pytest.raises(ValueError):
            service.history_between(now, now - timedelta(seconds=1))


class TestRetention:
    def test_apply_retention_prunes_old_rows(self, store):
        service = SnapshotService(store)
        now = utc_now()
        service.record(make_metrics(timestamp=now - timedelta(days=45)))
        service.record(make_metrics(timestamp=now - timedelta(days=5)))
        service.record(make_metrics(timestamp=now))

        deleted = service.apply_retention(30)

        assert deleted == 1
        assert len(store.rows) == 2

    def test_apply_retention_rejects_bad_input(self, store):
        with pytest.raises(ValueError):
            SnapshotService(store).apply_retention(0)
