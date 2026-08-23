"""Integration tests — report service builds real datasets and exports them."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.application.container import AppContainer
from app.services.report_service import ReportService
from tests.fakes import FakePinger


@pytest.fixture
def prepared(container: AppContainer, tmp_path) -> AppContainer:
    assert container.monitor_service is not None
    assert container.settings_service is not None
    container.settings_service.update({"default_export_dir": str(tmp_path / "exports")})
    container.monitor_service._pinger = FakePinger(reachable={"127.0.0.1"}, latency=33.0)
    device = container.monitor_service.add_device("Loop", "127.0.0.1", 30, 800)
    container.monitor_service.check_device(device)
    assert container.alert_service is not None
    container.alert_service.raise_alert("t.test", "warning", "src", "test alert message")
    return container


def test_definitions_and_ranges_shape(prepared: AppContainer):
    defs = ReportService.definitions()
    assert {d.key for d in defs} >= {
        "monitoring_history",
        "device_latency",
        "alerts",
        "activity",
        "disk_usage",
        "system_snapshots",
    }
    assert [hours for _label, hours in ReportService.ranges()] == [1.0, 24.0, 168.0]


def test_monitoring_history_report_contains_checks(prepared: AppContainer, tmp_path):
    assert prepared.report_service is not None
    path = prepared.report_service.generate("monitoring_history", "csv", hours=1.0)
    assert Path(path).exists()
    text = Path(path).read_text(encoding="utf-8")
    assert "Loop" in text and "online" in text


def test_device_latency_requires_device(prepared: AppContainer):
    assert prepared.report_service is not None
    with pytest.raises(ValueError, match="Select a device"):
        prepared.report_service.generate("device_latency", "csv")


def test_alerts_and_activity_and_disk_reports(prepared: AppContainer):
    assert prepared.report_service is not None
    alerts_path = prepared.report_service.generate("alerts", "json", hours=24.0)
    assert "test alert message" in Path(alerts_path).read_text(encoding="utf-8")
    activity_path = prepared.report_service.generate("activity", "txt", hours=24.0)
    assert "device.added" in Path(activity_path).read_text(encoding="utf-8")
    disk_path = prepared.report_service.generate("disk_usage", "csv")
    assert Path(disk_path).exists()


def test_unknown_report_rejected(prepared: AppContainer):
    assert prepared.report_service is not None
    with pytest.raises(ValueError, match="Unknown report"):
        prepared.report_service.generate("nonexistent", "csv")
