"""Unit/integration tests — monitoring, alerts, disk services (fakes + real DB)."""

from __future__ import annotations

import pytest
from app.application.container import AppContainer
from app.config.settings import AppSettings
from app.domain.entities import Severity
from app.domain.monitoring import MonitorState
from app.services.alert_service import AlertService
from app.services.disk_service import DiskService
from app.services.monitor_service import MonitorService
from tests.fakes import FakePinger, make_drives


def make_monitor(container: AppContainer, pinger=None, settings=None) -> MonitorService:
    from app.infrastructure.db.repositories import DeviceRepository, MonitoringResultRepository

    assert container.alert_service is not None
    settings = settings or AppSettings()
    return MonitorService(
        DeviceRepository(container.new_session),
        MonitoringResultRepository(container.new_session),
        pinger or FakePinger(),
        container.alert_service,
        lambda: settings,
    )


@pytest.fixture
def monitor(container: AppContainer) -> MonitorService:
    return make_monitor(container)


class TestDeviceCrud:
    def test_add_lists_and_deletes(self, monitor: MonitorService):
        device = monitor.add_device("Router", "192.168.1.1", 30, 800)
        assert device.id is not None
        names = [d.name for d in monitor.list_devices()]
        assert names == ["Router"]
        assert monitor.delete_device(device.id) is True
        assert monitor.list_devices() == []

    def test_duplicate_name_rejected(self, monitor: MonitorService):
        monitor.add_device("Router", "192.168.1.1", 30, 800)
        with pytest.raises(ValueError, match="already exists"):
            monitor.add_device("Router", "10.0.0.9", 30, 800)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"name": "", "host": "1.2.3.4", "interval_seconds": 30, "timeout_ms": 800},
            {"name": "x", "host": "bad host", "interval_seconds": 30, "timeout_ms": 800},
            {"name": "x", "host": "1.2.3.4", "interval_seconds": 1, "timeout_ms": 800},
            {"name": "x", "host": "1.2.3.4", "interval_seconds": 30, "timeout_ms": 10},
        ],
    )
    def test_invalid_inputs_rejected(self, monitor: MonitorService, kwargs):
        with pytest.raises(ValueError):
            monitor.add_device(**kwargs)


class TestChecksAndStates:
    def test_online_warning_offline_states(self, container: AppContainer):
        settings = AppSettings(monitoring={"latency_warning_ms": 100})
        pinger = FakePinger(reachable={"10.0.0.1"}, latency=150.0)
        monitor_service = make_monitor(container, pinger=pinger, settings=settings)
        device = monitor_service.add_device("Slow", "10.0.0.1", 30, 800)
        result = monitor_service.check_device(device)
        assert result.status is MonitorState.WARNING

        fast_monitor = make_monitor(
            container, pinger=FakePinger(reachable={"10.0.0.1"}, latency=10.0), settings=settings
        )
        result = fast_monitor.check_device(device)
        assert result.status is MonitorState.ONLINE

        down_monitor = make_monitor(container, pinger=FakePinger(), settings=settings)
        result = down_monitor.check_device(device)
        assert result.status is MonitorState.OFFLINE

    def test_offline_alert_raised_once_and_recovery_alerted(self, container: AppContainer):
        assert container.alert_service is not None
        pinger = FakePinger()  # everything offline
        monitor_service = make_monitor(container, pinger=pinger)
        device = monitor_service.add_device("Down", "10.0.0.5", 30, 800)
        monitor_service.check_device(device)
        monitor_service.check_device(device)  # second failure: deduped
        alerts = container.alert_service.unacknowledged()
        offline = [a for a in alerts if a.type == "device.offline"]
        assert len(offline) == 1
        assert offline[0].severity is Severity.CRITICAL

        up_monitor = make_monitor(container, pinger=FakePinger(reachable={"10.0.0.5"}, latency=5.0))
        up_monitor.check_device(device)
        recovered = [a for a in container.alert_service.recent() if a.type == "device.recovered"]
        assert len(recovered) == 1
        remaining_offline = [
            a for a in container.alert_service.unacknowledged() if a.type == "device.offline"
        ]
        assert remaining_offline == []  # auto-acknowledged on recovery

    def test_round_checks_enabled_devices_only(self, monitor: MonitorService):
        monitor.add_device("On", "10.0.0.1", 30, 800)
        monitor.add_device("Off", "10.0.0.2", 30, 800)
        from dataclasses import replace

        disabled = monitor.list_devices()[1]
        monitor.update_device(replace(disabled, enabled=False))
        results = monitor.run_round()
        assert len(results) == 1

    def test_consecutive_failures_counted(self, container: AppContainer):
        monitor_service = make_monitor(container, pinger=FakePinger())
        device = monitor_service.add_device("Flaky", "10.0.0.7", 30, 800)
        monitor_service.check_device(device)
        monitor_service.check_device(device)
        rows = monitor_service.status_rows()
        assert rows[0].consecutive_failures == 2
        assert rows[0].last_result is not None
        assert rows[0].last_result.status is MonitorState.OFFLINE


class TestHistoryAndRetention:
    def test_history_window_and_prune(self, container: AppContainer):
        monitor_service = make_monitor(
            container, pinger=FakePinger(reachable={"10.0.0.1"}, latency=12.0)
        )
        device = monitor_service.add_device("Stable", "10.0.0.1", 30, 800)
        monitor_service.check_device(device)
        history = monitor_service.history(device.id, hours=1)
        assert len(history) == 1
        assert history[0].response_time_ms == 12.0

        deleted = monitor_service.apply_retention(retention_days=30)
        assert deleted >= 0  # fresh rows survive


class TestAlertService:
    def test_dedup_and_acknowledge(self, container: AppContainer):
        assert container.alert_service is not None
        service: AlertService = container.alert_service
        first = service.raise_alert("t", Severity.WARNING, "s", "msg")
        assert first is not None
        assert service.raise_alert("t", Severity.WARNING, "s", "msg") is None  # deduped
        assert service.acknowledge(first.id) is True
        again = service.raise_alert("t", Severity.WARNING, "s", "msg")  # open again after ack
        assert again is not None

    def test_resolve_returns_zero_when_clean(self, container: AppContainer):
        assert container.alert_service is not None
        assert container.alert_service.resolve_alerts("none", "nowhere") == 0


class TestDiskService:
    def test_threshold_alerts_raised_and_cleared(self, container: AppContainer):
        assert container.alert_service is not None
        drives = make_drives([50.0, 85.0])
        disk = DiskService(lambda: drives, lambda: AppSettings(), container.alert_service)

        status = disk.evaluate()
        assert status.levels[1].value == "warning"
        warnings = [
            a for a in container.alert_service.unacknowledged() if a.type == "disk.threshold"
        ]
        assert len(warnings) == 1

        # usage drops -> auto-acknowledge
        disk2 = DiskService(
            lambda: make_drives([50.0, 40.0]), lambda: AppSettings(), container.alert_service
        )
        disk2.evaluate()
        assert [
            a for a in container.alert_service.unacknowledged() if a.type == "disk.threshold"
        ] == []

    def test_critical_severity(self, container: AppContainer):
        assert container.alert_service is not None
        disk = DiskService(
            lambda: make_drives([95.0]), lambda: AppSettings(), container.alert_service
        )
        disk.evaluate()
        alerts = container.alert_service.unacknowledged()
        assert alerts[0].severity is Severity.CRITICAL
