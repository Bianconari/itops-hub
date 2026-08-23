"""Integration tests — snapshot/alert repositories and services on SQLite."""

from __future__ import annotations

from datetime import timedelta

from app.application.container import AppContainer
from app.domain.entities import Severity
from app.domain.time_utils import utc_now
from app.infrastructure.db.models import AlertModel
from app.infrastructure.db.repositories import AlertRepository, SystemSnapshotRepository
from tests.fakes import make_metrics


class TestSystemSnapshotRepository:
    def test_add_and_query_range_orders_oldest_first(self, container: AppContainer):
        session = container.new_session()
        try:
            repo = SystemSnapshotRepository(session)
            now = utc_now()
            newer = repo.add(_snap(now, 10, 20, 30))
            older = repo.add(_snap(now - timedelta(seconds=5), 1, 2, 3))
            rows = repo.query_range(now - timedelta(minutes=5), now)
            assert [row.id for row in rows] == [older.id, newer.id]
            assert rows[0].cpu_percent == 1.0
            assert rows[1].disk_percent == 30.0
        finally:
            session.close()

    def test_prune_older_than(self, container: AppContainer):
        session = container.new_session()
        try:
            repo = SystemSnapshotRepository(session)
            now = utc_now()
            repo.add(_snap(now - timedelta(days=40), 1, 1, 1))
            repo.add(_snap(now - timedelta(days=1), 2, 2, 2))
            deleted = repo.prune_older_than(now - timedelta(days=30))
            assert deleted == 1
            remaining = repo.query_range(now - timedelta(days=60), now)
            assert len(remaining) == 1
            assert remaining[0].cpu_percent == 2.0
        finally:
            session.close()


def _snap(timestamp, cpu, memory, disk):
    from app.domain.system import SystemSnapshotEntity

    return SystemSnapshotEntity(
        timestamp=timestamp, cpu_percent=cpu, memory_percent=memory, disk_percent=disk
    )


class TestSnapshotServiceIntegration:
    def test_record_and_history_roundtrip(self, container: AppContainer):
        service = container.snapshot_service
        assert service is not None
        metrics = make_metrics(cpu=42, memory=52, disk=62)
        service.record(metrics)
        history = service.history(hours=1)
        assert len(history) == 1
        assert history[0].cpu_percent == 42.0
        assert history[0].memory_percent == 52.0
        assert history[0].disk_percent == 62.0

    def test_container_applies_retention_on_build(self, tmp_path):
        from app.config.paths import AppPaths

        paths = AppPaths.create(base=tmp_path / "data")
        first = AppContainer.build(paths=paths, console=False)
        try:
            session = first.new_session()
            try:
                repo = SystemSnapshotRepository(session)
                old = utc_now() - timedelta(days=60)
                repo.add(_snap(old, 1, 1, 1))
            finally:
                session.close()
            deleted = first.apply_retention()
            assert deleted == 1
        finally:
            first.close()


class TestAlertRepository:
    def test_recent_orders_newest_first_and_maps_severity(self, container: AppContainer):
        session = container.new_session()
        try:
            now = utc_now()
            session.add_all(
                [
                    AlertModel(
                        type="disk.threshold",
                        severity="critical",
                        source="C:\\",
                        message="disk over 90%",
                        created_at=now - timedelta(minutes=1),
                    ),
                    AlertModel(
                        type="disk.threshold",
                        severity="warning",
                        source="D:\\",
                        message="disk over 80%",
                        created_at=now,
                    ),
                ]
            )
            session.commit()
            alerts = AlertRepository(session).recent(limit=10)
        finally:
            session.close()

        assert len(alerts) == 2
        assert alerts[0].severity is Severity.WARNING  # newest first
        assert alerts[1].severity is Severity.CRITICAL
        assert alerts[0].message == "disk over 80%"

    def test_alert_service_reads_through_repo(self, container: AppContainer):
        assert container.alert_service is not None
        assert container.alert_service.recent(limit=5) == []
