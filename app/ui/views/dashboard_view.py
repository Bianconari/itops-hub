"""Dashboard view — live system health at a glance.

Layout: health summary card, CPU/RAM/Disk KPI cards, a live utilization
chart (CPU/RAM/disk), recent alerts, and recent activity.

All data comes from services; collection runs on a MetricsPoller QThread so
the UI never blocks. Snapshots are persisted at the configured cadence.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.application.container import AppContainer
from app.domain.formatters import (
    as_local_clock,
    as_local_string,
    epoch_of,
    format_uptime,
    human_bytes,
)
from app.domain.system import DriveUsage, Level, SystemInfo, SystemStatus
from app.services.activity_service import ActivityLogService
from app.services.alert_service import AlertService
from app.services.settings_service import SettingsService
from app.services.snapshot_service import SnapshotService
from app.services.system_service import SystemInfoService
from app.ui.theme.theme_service import ThemeService
from app.ui.widgets.kpi_card import KpiCard
from app.ui.widgets.time_series_chart import TimeSeriesChart
from app.ui.workers.metrics_poller import MetricsPoller
from app.ui.workers.one_shot import OneShotWorker

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 2000
PANEL_REFRESH_MS = 30_000
CHART_WINDOW_SECONDS = 600.0

_LEVEL_CSS = {Level.OK: "success", Level.WARNING: "warning", Level.CRITICAL: "danger"}


class DashboardView(QWidget):
    def __init__(
        self,
        container: AppContainer,
        theme_service: ThemeService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        assert container.system_service is not None
        assert container.snapshot_service is not None
        assert container.alert_service is not None
        assert container.activity_service is not None
        assert container.settings_service is not None
        self._system: SystemInfoService = container.system_service
        self._snapshots: SnapshotService = container.snapshot_service
        self._alerts: AlertService = container.alert_service
        self._activity: ActivityLogService = container.activity_service
        self._settings: SettingsService = container.settings_service
        self._theme = theme_service

        self._info: SystemInfo | None = None
        self._paused = False
        self._last_snapshot: float | None = None

        self._build_ui()

        self._poller = MetricsPoller(self._collect, POLL_INTERVAL_MS)
        self._poller.result_ready.connect(self._on_poll_result)
        self._poller.poll_failed.connect(self._on_poll_failed)

        self._panel_timer = QTimer(self)
        self._panel_timer.setInterval(PANEL_REFRESH_MS)
        self._panel_timer.timeout.connect(self._refresh_panels)

        self._static_worker: OneShotWorker | None = None
        self._load_static_info()
        self._refresh_panels()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        # Row 1: health summary + KPI cards
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        row1.addWidget(self._build_health_card(), stretch=1)
        self.kpi_cpu = KpiCard("CPU")
        self.kpi_ram = KpiCard("Memory")
        self.kpi_disk = KpiCard("Disk (highest)")
        row1.addWidget(self.kpi_cpu)
        row1.addWidget(self.kpi_ram)
        row1.addWidget(self.kpi_disk)
        outer.addLayout(row1)

        # Row 2: chart + side panels
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(self._build_chart_card(), stretch=1)
        side = QVBoxLayout()
        side.setSpacing(12)
        side.addWidget(self._build_alerts_card())
        side.addWidget(self._build_activity_card())
        row2.addLayout(side)
        outer.addLayout(row2, stretch=1)

    def _build_health_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        title = QLabel("Overall health")
        title.setProperty("cssClass", "subtitle")
        layout.addWidget(title)

        self.lbl_overall = QLabel("Collecting…")
        self.lbl_overall.setObjectName("healthOverall")
        font = self.lbl_overall.font()
        font.setPointSize(16)
        font.setBold(True)
        self.lbl_overall.setFont(font)
        layout.addWidget(self.lbl_overall)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(4)
        self.lbl_host = self._grid_row(grid, 0, "Hostname", "…")
        self.lbl_os = self._grid_row(grid, 1, "Operating system", "…")
        self.lbl_ip = self._grid_row(grid, 2, "Local IPv4", "…")
        self.lbl_interfaces = self._grid_row(grid, 3, "Interfaces up", "…")
        self.lbl_uptime = self._grid_row(grid, 4, "Uptime", "…")
        self.lbl_boot = self._grid_row(grid, 5, "Since boot", "…")
        layout.addLayout(grid)
        layout.addStretch(1)

        self.lbl_poll_error = QLabel("")
        self.lbl_poll_error.setProperty("cssClass", "danger")
        self.lbl_poll_error.setWordWrap(True)
        layout.addWidget(self.lbl_poll_error)
        return card

    def _build_chart_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Live utilization — last 10 minutes")
        title.setProperty("cssClass", "subtitle")
        header.addWidget(title)
        header.addStretch(1)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setObjectName("btn_pause")
        self.btn_pause.setCheckable(True)
        self.btn_pause.clicked.connect(self._on_pause_toggled)
        header.addWidget(self.btn_pause)
        layout.addLayout(header)

        self.chart = TimeSeriesChart(y_range=(0, 100))
        self.chart.apply_theme(self._theme.tokens)
        self.chart.set_window(CHART_WINDOW_SECONDS)
        self.chart.add_series("CPU %", "series0")
        self.chart.add_series("Memory %", "series1")
        self.chart.add_series("Disk %", "series3")
        layout.addWidget(self.chart, stretch=1)
        return card

    def _build_alerts_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumWidth(280)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        title = QLabel("Recent alerts")
        title.setProperty("cssClass", "subtitle")
        layout.addWidget(title)
        self.list_alerts = QListWidget()
        self.list_alerts.setWordWrap(True)
        layout.addWidget(self.list_alerts, stretch=1)
        return card

    def _build_activity_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumWidth(280)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        title = QLabel("Recent activity")
        title.setProperty("cssClass", "subtitle")
        layout.addWidget(title)
        self.list_activity = QListWidget()
        self.list_activity.setWordWrap(True)
        layout.addWidget(self.list_activity, stretch=1)
        return card

    @staticmethod
    def _grid_row(grid: QGridLayout, row: int, label: str, initial: str) -> QLabel:
        key = QLabel(label)
        key.setProperty("cssClass", "muted")
        grid.addWidget(key, row, 0)
        value = QLabel(initial)
        grid.addWidget(value, row, 1)
        return value

    # ------------------------------------------------------------ lifecycle
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._start_polling()
        self._panel_timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._stop_polling()
        self._panel_timer.stop()

    def shutdown(self) -> None:
        """Stop all background work (called when the window closes)."""
        self._stop_polling()
        self._panel_timer.stop()
        if self._static_worker is not None:
            self._static_worker.wait(2000)

    def _start_polling(self) -> None:
        if self._paused:
            return
        if not self._poller.isRunning():
            self._poller.start()

    def _stop_polling(self) -> None:
        if self._poller.isRunning():
            self._poller.stop()
            self._poller.wait_stopped(5000)

    def _on_pause_toggled(self, checked: bool) -> None:
        self._paused = checked
        self.btn_pause.setText("Resume" if checked else "Pause")
        if checked:
            self._stop_polling()
        else:
            self._start_polling()

    # ------------------------------------------------------------ data flow
    def _collect(self) -> tuple[SystemStatus, list[DriveUsage]]:
        return self._system.get_status(), self._system.get_drives()

    def _load_static_info(self) -> None:
        def fetch() -> SystemInfo:
            return self._system.get_info()

        self._static_worker = OneShotWorker(fetch)
        self._static_worker.succeeded.connect(self._on_static_info)
        self._static_worker.failed.connect(self._on_static_failed)
        self._static_worker.start()

    def _on_static_info(self, info: SystemInfo) -> None:
        self._info = info
        self.lbl_host.setText(info.hostname)
        self.lbl_os.setText(f"{info.os_name} {info.os_version} · {info.os_architecture}")
        self.lbl_ip.setText(SystemInfoService.primary_ipv4(info))
        self.lbl_interfaces.setText(
            f"{SystemInfoService.up_interface_count(info)} of {len(info.adapters)}"
        )
        self.lbl_boot.setText(as_local_string(info.boot_time))

    def _on_static_failed(self, message: str) -> None:
        self.lbl_host.setText("unavailable")
        self.lbl_os.setText("unavailable")
        logger.error("static system info failed: %s", message)

    def _on_poll_result(self, result: object) -> None:
        status, drives = result  # type: ignore[misc] — tuple from _collect()
        self._apply_status(status, drives)
        self._maybe_record_snapshot(status.metrics)

    def _apply_status(self, status: SystemStatus, drives: list[DriveUsage]) -> None:
        metrics = status.metrics
        x = epoch_of(metrics.timestamp)

        self.kpi_cpu.set_value(f"{metrics.cpu_percent:.0f} %", subtitle="", level=status.cpu_level)
        self.kpi_ram.set_value(
            f"{metrics.memory_percent:.0f} %",
            subtitle=f"{human_bytes(metrics.memory_used_bytes)} / "
            f"{human_bytes(metrics.memory_total_bytes)}",
            level=status.memory_level,
        )
        top_drive = self._top_drive(drives)
        self.kpi_disk.set_value(
            f"{metrics.disk_percent_max:.0f} %" if metrics.disk_percent_max is not None else "—",
            subtitle=f"max: {top_drive}" if top_drive else "no volumes",
            level=status.disk_level or Level.OK,
        )
        self.chart.append("CPU %", x, metrics.cpu_percent)
        self.chart.append("Memory %", x, metrics.memory_percent)
        if metrics.disk_percent_max is not None:
            self.chart.append("Disk %", x, metrics.disk_percent_max)

        self._set_overall(status.overall_level)
        if self._info is not None:
            self.lbl_uptime.setText(format_uptime(self._system.uptime_seconds(self._info)))
        self.lbl_poll_error.setText("")

    def _maybe_record_snapshot(self, metrics_timestamp) -> None:
        interval = self._settings.get().snapshots.interval_seconds
        now = time.monotonic()
        if self._last_snapshot is None or (now - self._last_snapshot) >= interval:
            self._snapshots.record(metrics_timestamp)
            self._last_snapshot = now

    def _on_poll_failed(self, message: str) -> None:
        self.lbl_poll_error.setText(f"Live collection error: {message}")

    def _set_overall(self, level: Level) -> None:
        self.lbl_overall.setText(
            {"ok": "Healthy", "warning": "Warning", "critical": "Critical"}[level.value]
        )
        self.lbl_overall.setProperty("cssClass", _LEVEL_CSS[level])
        self.lbl_overall.style().unpolish(self.lbl_overall)
        self.lbl_overall.style().polish(self.lbl_overall)

    @staticmethod
    def _top_drive(drives: list[DriveUsage]) -> str:
        if not drives:
            return ""
        top = max(drives, key=lambda drive: drive.percent)
        return top.mountpoint

    # ------------------------------------------------------------ panels
    def _refresh_panels(self) -> None:
        self.list_alerts.clear()
        alerts = self._alerts.recent(limit=8)
        if not alerts:
            self.list_alerts.addItem(
                QListWidgetItem(
                    "No alerts yet — disk thresholds and monitors raise alerts from v0.6."
                )
            )
        for alert in alerts:
            stamp = as_local_clock(alert.created_at)
            self.list_alerts.addItem(
                QListWidgetItem(f"[{alert.severity.value.upper()}] {stamp}  {alert.message}")
            )

        self.list_activity.clear()
        for entry in self._activity.recent(limit=8):
            stamp = as_local_clock(entry.timestamp)
            self.list_activity.addItem(
                QListWidgetItem(f"{stamp}  {entry.action} ({entry.module}) {entry.status.value}")
            )
