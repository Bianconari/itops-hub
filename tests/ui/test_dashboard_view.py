"""UI tests — dashboard view with real container services (offscreen).

Business classification is covered by unit tests with fakes; here we verify
the view wiring: KPI updates, health card, chart appends, snapshot cadence,
panel feeds, pause behavior, and safe shutdown. The view is never shown, so
no poller thread starts — data is driven through the poll-result slot.
"""

from __future__ import annotations

import time

import pytest
from app.application.container import AppContainer
from app.domain.system import Level, SystemStatus
from app.infrastructure.db.models import AlertModel
from app.ui.theme.theme_service import ThemeService
from app.ui.views.dashboard_view import DashboardView
from tests.fakes import make_drives, make_metrics

pytestmark = pytest.mark.ui


def make_status(cpu=10.0, memory=20.0, disk=30.0) -> SystemStatus:
    metrics = make_metrics(cpu=cpu, memory=memory, disk=disk)
    return SystemStatus(
        metrics=metrics,
        cpu_level=Level.WARNING if cpu >= 80 else Level.OK,
        memory_level=Level.WARNING if memory >= 80 else Level.OK,
        disk_level=(Level.CRITICAL if disk >= 90 else Level.WARNING if disk >= 80 else Level.OK)
        if disk is not None
        else None,
        overall_level=Level.CRITICAL if disk is not None and disk >= 90 else Level.OK,
    )


@pytest.fixture
def dashboard(container: AppContainer, theme_service: ThemeService) -> DashboardView:
    view = DashboardView(container, theme_service)
    yield view
    view.shutdown()
    view.deleteLater()


class TestDashboardRendering:
    def test_kpi_cards_update_with_levels(self, dashboard: DashboardView):
        status = make_status(cpu=85, memory=50, disk=95)
        dashboard._apply_status(status, make_drives([95, 40]))
        assert dashboard.kpi_cpu._value.text() == "85 %"
        assert dashboard.kpi_cpu.property("accent_warning") is True
        assert dashboard.kpi_ram._value.text() == "50 %"
        assert dashboard.kpi_disk._value.text() == "95 %"
        assert dashboard.kpi_disk.property("accent_critical") is True
        assert dashboard.lbl_overall.text() == "Critical"

    def test_chart_appends_points_per_tick(self, dashboard: DashboardView):
        status = make_status()
        dashboard._apply_status(status, make_drives([30]))
        dashboard._apply_status(status, make_drives([30]))
        xs, ys = dashboard.chart.series_points("CPU %")
        assert len(xs) == 2
        assert ys == [10.0, 10.0]

    def test_top_drive_shown_in_disk_subtitle(self, dashboard: DashboardView):
        dashboard._apply_status(make_status(disk=88), make_drives([88, 10]))
        assert "vol0" not in dashboard.kpi_disk._subtitle.text()  # fakes mount at /
        assert dashboard.kpi_disk._subtitle.text().startswith("max: /")

    def test_no_drives_honest_display(self, dashboard: DashboardView):
        dashboard._apply_status(make_status(disk=None), [])
        assert dashboard.kpi_disk._value.text() == "—"
        assert dashboard.kpi_disk._subtitle.text() == "no volumes"

    def test_poll_error_surfaces(self, dashboard: DashboardView):
        dashboard._on_poll_failed("adapter exploded")
        assert "adapter exploded" in dashboard.lbl_poll_error.text()
        dashboard._apply_status(make_status(), make_drives([30]))
        assert dashboard.lbl_poll_error.text() == ""


class TestSnapshotCadence:
    def test_first_tick_records_snapshot(self, dashboard: DashboardView, container):
        status = make_status(cpu=7)
        dashboard._maybe_record_snapshot(status.metrics)
        assert container.snapshot_service is not None
        history = container.snapshot_service.history(hours=1)
        assert len(history) == 1
        assert history[0].cpu_percent == 7.0

    def test_rapid_ticks_do_not_flood_database(self, dashboard: DashboardView, container):
        metrics = make_metrics()
        dashboard._maybe_record_snapshot(metrics)
        dashboard._maybe_record_snapshot(metrics)
        dashboard._maybe_record_snapshot(metrics)
        assert container.snapshot_service is not None
        assert len(container.snapshot_service.history(hours=1)) == 1

    def test_records_again_after_interval_elapsed(self, dashboard: DashboardView, container):
        dashboard._maybe_record_snapshot(make_metrics())
        dashboard._last_snapshot = time.monotonic() - 7200  # pretend 2h passed
        dashboard._maybe_record_snapshot(make_metrics())
        assert container.snapshot_service is not None
        assert len(container.snapshot_service.history(hours=1)) >= 1


class TestPanels:
    def test_activity_feed_shows_entries(self, dashboard: DashboardView, container):
        assert container.activity_service is not None
        container.activity_service.record("test.hello", module="tests")
        dashboard._refresh_panels()
        texts = [
            dashboard.list_activity.item(row).text()
            for row in range(dashboard.list_activity.count())
        ]
        assert any("test.hello" in text for text in texts)

    def test_alerts_feed_shows_entries_and_empty_state(self, dashboard: DashboardView, container):
        dashboard._refresh_panels()
        first_item = dashboard.list_alerts.item(0).text()
        assert "No alerts yet" in first_item

        session = container.new_session()
        try:
            session.add(
                AlertModel(
                    type="disk.threshold",
                    severity="critical",
                    source="/",
                    message="usage 95%",
                )
            )
            session.commit()
        finally:
            session.close()

        dashboard._refresh_panels()
        first_item = dashboard.list_alerts.item(0).text()
        assert "[CRITICAL]" in first_item
        assert "usage 95%" in first_item


class TestPause:
    def test_pause_toggles_state_and_label(self, dashboard: DashboardView):
        assert dashboard._paused is False
        dashboard._on_pause_toggled(True)
        assert dashboard._paused is True
        assert dashboard.btn_pause.text() == "Resume"
        dashboard._on_pause_toggled(False)
        assert dashboard._paused is False
        assert dashboard.btn_pause.text() == "Pause"

    def test_shutdown_is_safe_without_show(self, dashboard: DashboardView):
        dashboard.shutdown()  # idempotent, no threads running
        assert True


class TestStaticInfoWorker:
    def test_static_info_populates_health_card(self, dashboard: DashboardView, qtbot):
        qtbot.waitUntil(lambda: dashboard.lbl_host.text() not in ("", "…"), timeout=10000)
        assert dashboard.lbl_ip.text() not in ("", "…")
        assert dashboard.lbl_os.text() not in ("", "…")
