"""Monitoring view — devices, states, history charts, disk volumes.

All checks run off-thread (MonitorWorker / OneShotWorker); alerts are raised
by the services (deduplicated), and this page only displays data.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.container import AppContainer
from app.domain.formatters import as_local_string, human_bytes
from app.domain.monitoring import DeviceStatusRow, MonitorState
from app.domain.system import Level
from app.services.disk_service import DiskService
from app.services.monitor_service import MonitorService
from app.services.settings_service import SettingsService
from app.ui.theme.theme_service import ThemeService
from app.ui.views.device_dialog import DeviceDialog
from app.ui.widgets.time_series_chart import TimeSeriesChart
from app.ui.workers.one_shot import OneShotWorker

logger = logging.getLogger(__name__)

_DEVICE_HEADERS = ["Name", "Host", "Status", "Response", "Last seen", "Failures", "Interval"]
_DISK_HEADERS = ["Volume", "Total", "Used", "Free", "Usage", "Level"]
_RANGES = [("Last hour", 1.0), ("Last 24 hours", 24.0), ("Last 7 days", 168.0)]
_AUTO_ROUND_MS = 30_000

_STATE_TEXT = {
    MonitorState.ONLINE: "Online",
    MonitorState.OFFLINE: "Offline",
    MonitorState.WARNING: "Warning",
}
_STATE_CSS = {
    MonitorState.ONLINE: "success",
    MonitorState.OFFLINE: "danger",
    MonitorState.WARNING: "warning",
}


class MonitorWorker(QThread):
    """One monitoring round for all enabled devices."""

    round_done = Signal(object)  # list[MonitorResult]
    round_failed = Signal(str)

    def __init__(self, service: MonitorService, parent=None) -> None:
        super().__init__(parent)
        self._service = service

    def run(self) -> None:
        try:
            results = self._service.run_round()
        except Exception as exc:
            self.round_failed.emit(f"{exc}")
        else:
            self.round_done.emit(results)


class MonitoringView(QWidget):
    def __init__(
        self,
        container: AppContainer,
        theme_service: ThemeService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        assert container.monitor_service is not None
        assert container.disk_service is not None
        assert container.settings_service is not None
        self._monitor: MonitorService = container.monitor_service
        self._disks: DiskService = container.disk_service
        self._settings: SettingsService = container.settings_service
        self._theme = theme_service
        self._round_worker: MonitorWorker | None = None
        self._history_worker: OneShotWorker | None = None
        self._disk_worker: OneShotWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        outer.addWidget(self._build_devices_card())
        outer.addWidget(self._build_history_card(), stretch=1)
        outer.addWidget(self._build_disks_card())

        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(_AUTO_ROUND_MS)
        self._auto_timer.timeout.connect(self._run_round_if_idle)

    # ------------------------------------------------------------------ UI
    def _build_devices_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Devices")
        title.setProperty("cssClass", "subtitle")
        header.addWidget(title)
        header.addStretch(1)
        self.chk_auto = QCheckBox("Auto check (30s)")
        self.chk_auto.setObjectName("chk_auto")
        self.chk_auto.setChecked(True)
        header.addWidget(self.chk_auto)
        for label, name, handler in (
            ("Add", "btn_add", self._on_add),
            ("Edit…", "btn_edit", self._on_edit),
            ("Delete", "btn_delete", self._on_delete),
            ("Check all now", "btn_check", self._on_check_now),
        ):
            button = QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(handler)
            header.addWidget(button)
        self.lbl_round = QLabel("")
        self.lbl_round.setProperty("cssClass", "muted")
        header.addWidget(self.lbl_round)
        layout.addLayout(header)

        self.table = QTableWidget(0, len(_DEVICE_HEADERS))
        self.table.setObjectName("table_devices")
        self.table.setHorizontalHeaderLabels(_DEVICE_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda _item: self._on_edit())
        layout.addWidget(self.table)
        return card

    def _build_history_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Latency history")
        title.setProperty("cssClass", "subtitle")
        header.addWidget(title)
        header.addStretch(1)
        self.combo_device = QComboBox()
        self.combo_device.setObjectName("combo_device")
        self.combo_device.setMinimumWidth(160)
        header.addWidget(self.combo_device)
        self.combo_range = QComboBox()
        for label, _hours in _RANGES:
            self.combo_range.addItem(label)
        self.combo_range.currentIndexChanged.connect(self._load_history)
        header.addWidget(self.combo_range)
        layout.addLayout(header)

        self.chart = TimeSeriesChart(y_range=(0, 1000))
        self.chart.apply_theme(self._theme.tokens)
        self.chart.add_series("Latency (ms)", "series2")
        self.chart.set_window(3600)
        layout.addWidget(self.chart, stretch=1)

        self.lbl_history = QLabel("Select a device to view its history.")
        self.lbl_history.setProperty("cssClass", "muted")
        layout.addWidget(self.lbl_history)
        return card

    def _build_disks_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("Disk volumes")
        title.setProperty("cssClass", "subtitle")
        header.addWidget(title)
        header.addStretch(1)
        self.btn_disk_check = QPushButton("Check now")
        self.btn_disk_check.setObjectName("btn_disk_check")
        self.btn_disk_check.clicked.connect(self._check_disks)
        header.addWidget(self.btn_disk_check)
        layout.addLayout(header)

        self.disk_table = QTableWidget(0, len(_DISK_HEADERS))
        self.disk_table.setObjectName("table_disks")
        self.disk_table.setHorizontalHeaderLabels(_DISK_HEADERS)
        self.disk_table.verticalHeader().setVisible(False)
        self.disk_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.disk_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.disk_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.disk_table)
        return card

    # ------------------------------------------------------------ lifecycle
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_devices()
        self._check_disks()
        if self.chk_auto.isChecked():
            self._auto_timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._auto_timer.stop()

    def shutdown(self) -> None:
        self._auto_timer.stop()
        for worker in (self._round_worker, self._history_worker, self._disk_worker):
            if worker is not None and worker.isRunning():
                worker.wait(15000)

    # ------------------------------------------------------------ devices
    def refresh_devices(self) -> None:
        rows = self._monitor.status_rows()
        self.table.setRowCount(len(rows))
        selected_name = self.combo_device.currentText()
        self.combo_device.blockSignals(True)
        self.combo_device.clear()
        for row_index, row in enumerate(rows):
            values = self._row_values(row)
            for column, (text, css) in enumerate(values):
                item = QTableWidgetItem(text)
                if css in ("danger", "warning"):
                    item.setForeground(QColor(getattr(self._theme.tokens, css)))
                self.table.setItem(row_index, column, item)
            if row.device.id is not None:
                self.combo_device.addItem(row.device.name, row.device.id)
        self.combo_device.blockSignals(False)
        if selected_name:
            index = self.combo_device.findText(selected_name)
            if index >= 0:
                self.combo_device.setCurrentIndex(index)
        elif self.combo_device.count():
            self.combo_device.setCurrentIndex(0)
        self._load_history()

    @staticmethod
    def _row_values(row: DeviceStatusRow) -> list[tuple[str, str | None]]:
        last = row.last_result
        status = _STATE_TEXT[last.status] if last else "Unknown"
        css = _STATE_CSS[last.status] if last else "muted"
        response = (
            f"{last.response_time_ms:.1f} ms" if last and last.response_time_ms is not None else "—"
        )
        seen = as_local_string(last.timestamp, "%H:%M:%S") if last else "—"
        return [
            (row.device.name, None),
            (row.device.host, None),
            (status, css),
            (response, None),
            (seen, None),
            (str(row.consecutive_failures) if row.consecutive_failures else "0", None),
            (f"{row.device.interval_seconds}s", None),
        ]

    def _selected_row(self) -> DeviceStatusRow | None:
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            return None
        index = selection[0].row()
        rows = self._monitor.status_rows()
        return rows[index] if 0 <= index < len(rows) else None

    def _on_add(self) -> None:
        settings = self._settings.get()
        dialog = DeviceDialog(
            self,
            interval_seconds=settings.monitoring.interval_seconds,
            timeout_ms=settings.monitoring.timeout_ms,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.result_values()
            try:
                self._monitor.add_device(
                    values.name, values.host, values.interval_seconds, values.timeout_ms
                )
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid device", f"{exc}")
            else:
                self.refresh_devices()

    def _on_edit(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "Edit device", "Select a device first.")
            return
        device = row.device
        dialog = DeviceDialog(
            self,
            name=device.name,
            host=device.host,
            interval_seconds=device.interval_seconds,
            timeout_ms=device.timeout_ms,
            enabled=device.enabled,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.result_values()
            from dataclasses import replace

            try:
                self._monitor.update_device(
                    replace(
                        device,
                        name=values.name,
                        host=values.host,
                        interval_seconds=values.interval_seconds,
                        timeout_ms=values.timeout_ms,
                        enabled=values.enabled,
                    )
                )
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid device", f"{exc}")
            else:
                self.refresh_devices()

    def _on_delete(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "Delete device", "Select a device first.")
            return
        confirm = QMessageBox.question(
            self,
            "Delete device",
            f"Delete '{row.device.name}' and its monitoring history?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes and row.device.id is not None:
            self._monitor.delete_device(row.device.id)
            self.refresh_devices()

    # ------------------------------------------------------------ checks
    def _run_round_if_idle(self) -> None:
        if self.chk_auto.isChecked():
            self._on_check_now()

    def _on_check_now(self) -> None:
        if self._round_worker is not None:
            return
        self.lbl_round.setText("Checking…")
        self._round_worker = MonitorWorker(self._monitor)
        self._round_worker.round_done.connect(self._on_round_done)
        self._round_worker.round_failed.connect(self._on_round_failed)
        self._round_worker.finished.connect(
            lambda: self._clear_worker("_round_worker", self._round_worker)
        )
        self._round_worker.start()

    def _clear_worker(self, attr: str, worker: object) -> None:
        current = getattr(self, attr)
        if current is worker:
            setattr(self, attr, None)

    def _on_round_done(self, results: object) -> None:
        self.lbl_round.setText(f"{len(results)} devices checked")
        self.refresh_devices()

    def _on_round_failed(self, message: str) -> None:
        self.lbl_round.setText("Check failed")
        logger.warning("monitor round failed: %s", message)

    # ------------------------------------------------------------ history
    def _load_history(self) -> None:
        device_id = self.combo_device.currentData()
        if device_id is None or self._history_worker is not None:
            return
        hours = _RANGES[self.combo_range.currentIndex()][1]

        def load():
            return self._monitor.history(device_id, hours=hours)  # type: ignore[arg-type]

        self._history_worker = OneShotWorker(load)
        self._history_worker.succeeded.connect(self._on_history)
        self._history_worker.failed.connect(self._on_history_failed)
        self._history_worker.finished.connect(
            lambda: self._clear_worker("_history_worker", self._history_worker)
        )
        self._history_worker.start()

    def _on_history(self, results: object) -> None:
        history = list(results)  # type: ignore[arg-type]
        self.chart.clear_all()
        if not history:
            self.lbl_history.setText("No history for the selected range yet.")
            return
        from app.domain.formatters import epoch_of

        for result in history:
            if result.response_time_ms is not None:
                self.chart.append(
                    "Latency (ms)", epoch_of(result.timestamp), result.response_time_ms
                )
        total = len(history)
        online = sum(1 for r in history if r.status is not MonitorState.OFFLINE)
        latencies = [r.response_time_ms for r in history if r.response_time_ms is not None]
        availability = 100.0 * online / total
        summary = (
            f"{total} checks · availability {availability:.1f}% · "
            f"avg {sum(latencies) / len(latencies):.1f} ms · max {max(latencies):.1f} ms"
            if latencies
            else f"{total} checks · availability {availability:.1f}%"
        )
        self.lbl_history.setText(summary)

    def _on_history_failed(self, message: str) -> None:
        self.lbl_history.setText(f"History load failed: {message}")

    # ------------------------------------------------------------ disks
    def _check_disks(self) -> None:
        if self._disk_worker is not None:
            return
        self._disk_worker = OneShotWorker(lambda: self._disks.evaluate())

        def on_done(status: object) -> None:
            self._populate_disks(status)

        self._disk_worker.succeeded.connect(on_done)
        self._disk_worker.failed.connect(lambda message: self.btn_disk_check.setEnabled(True))
        self._disk_worker.finished.connect(
            lambda: self._clear_worker("_disk_worker", self._disk_worker)
        )
        self.btn_disk_check.setEnabled(False)
        self._disk_worker.start()

    def _populate_disks(self, status: object) -> None:
        self.btn_disk_check.setEnabled(True)
        disk_status = status
        self.disk_table.setRowCount(len(disk_status.drives))
        for row, (drive, level) in enumerate(
            zip(disk_status.drives, disk_status.levels, strict=True)
        ):
            values = [
                drive.mountpoint,
                human_bytes(drive.total_bytes),
                human_bytes(drive.used_bytes),
                human_bytes(drive.free_bytes),
                f"{drive.percent:.1f} %",
                level.value,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 5 and level is not Level.OK:
                    item.setForeground(
                        QColor(
                            getattr(
                                self._theme.tokens,
                                "warning" if level is Level.WARNING else "danger",
                            )
                        )
                    )
                self.disk_table.setItem(row, column, item)
