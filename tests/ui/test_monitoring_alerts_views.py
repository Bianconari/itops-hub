"""UI tests — monitoring and alerts views (offscreen, fake-backed)."""

from __future__ import annotations

import pytest
from app.application.container import AppContainer
from app.ui.theme.theme_service import ThemeService
from app.ui.views.alerts_view import AlertsView
from app.ui.views.monitoring_view import MonitoringView
from tests.fakes import FakePinger

pytestmark = pytest.mark.ui


@pytest.fixture
def monitoring_view(container: AppContainer, theme_service: ThemeService) -> MonitoringView:
    # deterministic checks: inject a fake pinger behind the real services
    assert container.monitor_service is not None
    container.monitor_service._pinger = FakePinger(reachable={"127.0.0.1"}, latency=42.0)
    view = MonitoringView(container, theme_service)
    yield view
    view.shutdown()
    view.deleteLater()


class TestMonitoringView:
    def test_renders_empty_state(self, monitoring_view):
        assert monitoring_view.table.rowCount() == 0
        assert monitoring_view.combo_device.count() == 0

    def test_add_device_populates_table_and_history_combo(self, container, monitoring_view, qtbot):
        assert container.monitor_service is not None
        container.monitor_service.add_device("Loopback", "127.0.0.1", 30, 800)
        monitoring_view.refresh_devices()
        assert monitoring_view.table.rowCount() == 1
        assert monitoring_view.combo_device.count() == 1

    def test_check_now_runs_round_and_updates_status(self, container, monitoring_view, qtbot):
        assert container.monitor_service is not None
        container.monitor_service.add_device("Loopback", "127.0.0.1", 30, 800)
        monitoring_view.refresh_devices()
        monitoring_view._on_check_now()
        qtbot.waitUntil(
            lambda: (
                monitoring_view.table.item(0, 2) is not None
                and monitoring_view.table.item(0, 2).text() == "Online"
            ),
            timeout=10000,
        )
        assert monitoring_view.table.item(0, 3).text() == "42.0 ms"

    def test_history_chart_receives_points(self, container, monitoring_view, qtbot):
        assert container.monitor_service is not None
        device = container.monitor_service.add_device("Loopback", "127.0.0.1", 30, 800)
        container.monitor_service.check_device(device)
        monitoring_view.refresh_devices()
        qtbot.waitUntil(
            lambda: monitoring_view.chart.series_points("Latency (ms)")[0] != [],
            timeout=10000,
        )
        assert "availability" in monitoring_view.lbl_history.text()

    def test_disk_table_populates(self, monitoring_view, qtbot):
        monitoring_view._check_disks()
        qtbot.waitUntil(lambda: monitoring_view.disk_table.rowCount() >= 1, timeout=15000)


class TestAlertsView:
    def test_refresh_shows_raised_alert_and_ack_flow(self, container, theme_service, qtbot):
        assert container.alert_service is not None
        container.alert_service.raise_alert(
            "disk.threshold", "warning", "/data", "usage 85% (warning threshold 80%)"
        )
        view = AlertsView(container, theme_service)
        qtbot.addWidget(view)
        view.refresh()
        assert view.table.rowCount() == 1
        assert "/data" in view.table.item(0, 3).text()

        view.table.selectRow(0)
        view._ack_selected()
        assert view.table.rowCount() == 1  # default filter still shows it...
        assert view.table.item(0, 5).text() == "Yes"  # ...now acknowledged
        view.chk_unack.setChecked(True)
        assert view.table.rowCount() == 0  # unack-only filter hides it

    def test_unacknowledged_only_filter(self, container, theme_service, qtbot):
        assert container.alert_service is not None
        alert = container.alert_service.raise_alert("t.x", "info", "s", "m")
        assert alert is not None
        container.alert_service.acknowledge(alert.id)
        view = AlertsView(container, theme_service)
        qtbot.addWidget(view)
        view.chk_unack.setChecked(True)
        view.refresh()
        assert view.table.rowCount() == 0
        view.chk_unack.setChecked(False)
        view.refresh()
        assert view.table.rowCount() == 1
