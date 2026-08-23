"""System view — full inventory of local hardware, OS, storage, and network.

Static info collection runs on a OneShotWorker (hostname lookups and disk
enumeration can block); the view shows a loading state until data arrives
and an explicit error row with a retry on failure.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.container import AppContainer
from app.domain.formatters import as_local_string, format_uptime, human_bytes
from app.domain.system import DriveUsage, Level, SystemInfo, evaluate_usage_level
from app.services.settings_service import SettingsService
from app.services.system_service import SystemInfoService
from app.ui.theme.theme_service import ThemeService
from app.ui.workers.one_shot import OneShotWorker

logger = logging.getLogger(__name__)


class SystemView(QWidget):
    def __init__(
        self,
        container: AppContainer,
        theme_service: ThemeService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        assert container.system_service is not None
        assert container.settings_service is not None
        self._system: SystemInfoService = container.system_service
        self._settings: SettingsService = container.settings_service
        self._theme = theme_service
        self._worker: OneShotWorker | None = None
        self._last_drives: list[DriveUsage] = []
        self._theme.themeChanged.connect(lambda _name: self._restyle_drives())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        page = QFrame()
        page.setObjectName("page")
        scroll.setWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("System information")
        title.setProperty("cssClass", "title")
        header.addWidget(title)
        header.addStretch(1)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("btn_refresh")
        self.btn_refresh.setProperty("cssClass", "primary")
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        self.progress = QProgressBar()
        self.progress.setObjectName("collect_progress")
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("lbl_error")
        self.lbl_error.setProperty("cssClass", "danger")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)

        layout.addWidget(self._build_info_card())
        layout.addWidget(self._build_drives_card())
        layout.addWidget(self._build_adapters_card())
        layout.addStretch(1)

        self.refresh()

    # ------------------------------------------------------------------ UI
    def _build_info_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(18, 14, 18, 14)
        form.setSpacing(6)
        self.lbl_hostname = self._info_row(form, "Hostname")
        self.lbl_os = self._info_row(form, "Operating system")
        self.lbl_arch = self._info_row(form, "Architecture")
        self.lbl_cpu = self._info_row(form, "CPU")
        self.lbl_cores = self._info_row(form, "Cores")
        self.lbl_freq = self._info_row(form, "CPU frequency")
        self.lbl_ram = self._info_row(form, "Total memory")
        self.lbl_boot = self._info_row(form, "Booted (local time)")
        self.lbl_uptime = self._info_row(form, "Uptime at refresh")
        self.lbl_python = self._info_row(form, "ITOps runtime")
        return card

    @staticmethod
    def _info_row(form: QFormLayout, label: str) -> QLabel:
        key = QLabel(label)
        key.setProperty("cssClass", "muted")
        value = QLabel("…")
        form.addRow(key, value)
        return value

    def _build_drives_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        title = QLabel("Storage volumes")
        title.setProperty("cssClass", "subtitle")
        layout.addWidget(title)
        self.table_drives = QTableWidget(0, 6)
        self.table_drives.setObjectName("table_drives")
        self.table_drives.setHorizontalHeaderLabels(
            ["Volume", "Filesystem", "Total", "Used", "Free", "Usage"]
        )
        self.table_drives.verticalHeader().setVisible(False)
        self.table_drives.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_drives.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self.table_drives.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_drives)
        return card

    def _build_adapters_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        title = QLabel("Network adapters")
        title.setProperty("cssClass", "subtitle")
        layout.addWidget(title)
        self.table_adapters = QTableWidget(0, 5)
        self.table_adapters.setObjectName("table_adapters")
        self.table_adapters.setHorizontalHeaderLabels(
            ["Adapter", "Status", "Speed", "IPv4", "IPv6"]
        )
        self.table_adapters.verticalHeader().setVisible(False)
        self.table_adapters.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_adapters.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self.table_adapters.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_adapters)
        return card

    # ------------------------------------------------------------ data flow
    def refresh(self) -> None:
        """Collect system info + drives off-thread and populate the view."""
        if self._worker is not None:
            return
        self.btn_refresh.setEnabled(False)
        self.progress.setVisible(True)
        self.lbl_error.setVisible(False)

        def fetch() -> tuple[SystemInfo, list[DriveUsage]]:
            return self._system.get_info(), self._system.get_drives()

        worker = OneShotWorker(fetch)
        worker.succeeded.connect(self._on_loaded)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda: self._worker_done(worker))
        self._worker = worker
        worker.start()

    def shutdown(self) -> None:
        """Wait for any in-flight collection (called on teardown/close)."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(10000)

    def _worker_done(self, worker: OneShotWorker) -> None:
        if self._worker is worker:
            self._worker = None

    def _on_loaded(self, result: object) -> None:
        self.btn_refresh.setEnabled(True)
        self.progress.setVisible(False)
        info, drives = result  # type: ignore[misc]
        self._populate_info(info)
        self._populate_drives(drives)
        self._populate_adapters(info)

    def _on_failed(self, message: str) -> None:
        self.btn_refresh.setEnabled(True)
        self.progress.setVisible(False)
        self.lbl_error.setText(f"Could not collect system information: {message}")
        self.lbl_error.setVisible(True)
        logger.error("system info collection failed: %s", message)

    # ------------------------------------------------------------ populate
    def _populate_info(self, info: SystemInfo) -> None:
        self.lbl_hostname.setText(info.hostname)
        self.lbl_os.setText(f"{info.os_name} {info.os_version}")
        self.lbl_arch.setText(info.os_architecture)
        self.lbl_cpu.setText(info.cpu_model)
        physical = info.cpu_cores_physical or "?"
        logical = info.cpu_cores_logical or "?"
        self.lbl_cores.setText(f"{physical} physical / {logical} logical")
        if info.cpu_freq_mhz_current is not None:
            freq = f"{info.cpu_freq_mhz_current:.0f} MHz"
            if info.cpu_freq_mhz_max:
                freq += f" (max {info.cpu_freq_mhz_max:.0f} MHz)"
            self.lbl_freq.setText(freq)
        else:
            self.lbl_freq.setText("not reported")
        self.lbl_ram.setText(human_bytes(info.memory_total_bytes))
        self.lbl_boot.setText(as_local_string(info.boot_time, "%Y-%m-%d %H:%M:%S"))
        self.lbl_uptime.setText(format_uptime(self._system.uptime_seconds(info)))
        self.lbl_python.setText(f"Python {info.python_version}")

    def _populate_drives(self, drives: list[DriveUsage]) -> None:
        self._last_drives = drives
        settings = self._settings.get()
        self.table_drives.setRowCount(len(drives))
        for row, drive in enumerate(drives):
            level = evaluate_usage_level(
                drive.percent, settings.disk.warning_percent, settings.disk.critical_percent
            )
            values = [
                drive.mountpoint,
                drive.fs_type or "—",
                human_bytes(drive.total_bytes),
                human_bytes(drive.used_bytes),
                human_bytes(drive.free_bytes),
                f"{drive.percent:.1f} % ({level.value})",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 5 and level is not Level.OK:
                    role = {"warning": "warning", "critical": "danger"}[level.value]
                    item.setForeground(QColor(getattr(self._theme.tokens, role)))
                self.table_drives.setItem(row, column, item)

    def _restyle_drives(self) -> None:
        """Re-apply theme colors to the usage column after a theme switch."""
        if self._last_drives:
            self._populate_drives(self._last_drives)

    def _populate_adapters(self, info: SystemInfo) -> None:
        self.table_adapters.setRowCount(len(info.adapters))
        for row, adapter in enumerate(info.adapters):
            values = [
                adapter.name,
                "Up" if adapter.is_up else "Down",
                f"{adapter.speed_mbps} Mbps" if adapter.speed_mbps else "—",
                ", ".join(adapter.ipv4) or "—",
                ", ".join(adapter.ipv6) or "—",
            ]
            for column, text in enumerate(values):
                self.table_adapters.setItem(row, column, QTableWidgetItem(text))
