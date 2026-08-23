"""Reports view — build and export reports from live data."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.application.container import AppContainer
from app.services.report_service import ReportService
from app.ui.workers.one_shot import OneShotWorker

logger = logging.getLogger(__name__)


class ReportsView(QWidget):
    def __init__(self, container: AppContainer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        assert container.report_service is not None
        assert container.export_service is not None
        self._reports: ReportService = container.report_service
        self._container = container
        self._worker: OneShotWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("card")
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        title = QLabel("Reports")
        title.setProperty("cssClass", "title")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.combo_report = QComboBox()
        self.combo_report.setObjectName("combo_report")
        for definition in self._reports.definitions():
            self.combo_report.addItem(definition.title, definition.key)
        self.combo_report.currentIndexChanged.connect(self._sync_fields)
        row.addWidget(self.combo_report, stretch=2)

        self.combo_device = QComboBox()
        self.combo_device.setObjectName("combo_report_device")
        self._reload_devices()
        row.addWidget(self.combo_device, stretch=1)

        self.combo_range = QComboBox()
        self.combo_range.setObjectName("combo_report_range")
        for label, _hours in self._reports.ranges():
            self.combo_range.addItem(label, _hours)
        row.addWidget(self.combo_range)

        self.combo_format = QComboBox()
        for fmt in ("csv", "json", "txt"):
            self.combo_format.addItem(fmt.upper(), fmt)
        row.addWidget(self.combo_format)

        self.btn_generate = QPushButton("Generate report")
        self.btn_generate.setObjectName("btn_generate")
        self.btn_generate.setProperty("cssClass", "primary")
        self.btn_generate.clicked.connect(self._on_generate)
        row.addWidget(self.btn_generate)
        layout.addLayout(row)

        self.lbl_result = QLabel("Choose a dataset and generate — files land in the export folder.")
        self.lbl_result.setProperty("cssClass", "muted")
        self.lbl_result.setWordWrap(True)
        layout.addWidget(self.lbl_result)

        self.lbl_error = QLabel("")
        self.lbl_error.setProperty("cssClass", "danger")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)

        recent_title = QLabel("Recent exports")
        recent_title.setProperty("cssClass", "subtitle")
        layout.addWidget(recent_title)
        self.list_recent = QListWidget()
        self.list_recent.setObjectName("list_recent_exports")
        layout.addWidget(self.list_recent, stretch=1)

        self._sync_fields()
        self._refresh_recent()

    # ------------------------------------------------------------------
    def _reload_devices(self) -> None:
        self.combo_device.clear()
        for device in self._reports._monitor.list_devices():
            if device.id is not None:
                self.combo_device.addItem(f"{device.name} ({device.host})", device.id)

    def _sync_fields(self) -> None:
        definition = self._reports.definitions()[self.combo_report.currentIndex()]
        self.combo_device.setVisible(definition.needs_device)
        self.combo_range.setVisible(definition.needs_range)

    def _on_generate(self) -> None:
        if self._worker is not None:
            return
        self.lbl_error.setVisible(False)
        self.lbl_result.setText("Generating…")
        self.btn_generate.setEnabled(False)
        report_key = self.combo_report.currentData()
        fmt = self.combo_format.currentData()
        device_id = self.combo_device.currentData() if self.combo_device.isVisible() else None
        hours = self.combo_range.currentData() if self.combo_range.isVisible() else 1.0

        def generate():
            return self._reports.generate(report_key, fmt, device_id=device_id, hours=hours)

        self._worker = OneShotWorker(generate)
        self._worker.succeeded.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(lambda: self._worker_gone(self._worker))
        self._worker.start()

    def _worker_gone(self, worker: OneShotWorker | None) -> None:
        if worker is not None and self._worker is worker:
            self._worker = None
            self.btn_generate.setEnabled(True)
            self._reload_devices()

    def _on_done(self, path: object) -> None:
        self.lbl_result.setText(f"Saved: {path}")
        self._refresh_recent()

    def _on_failed(self, message: str) -> None:
        self.lbl_result.setText("Report failed")
        self.lbl_error.setText(message)
        self.lbl_error.setVisible(True)

    def _refresh_recent(self) -> None:
        from pathlib import Path

        from app.config.settings import AppSettings

        assert self._container.settings_service is not None
        assert self._container.export_service is not None
        settings: AppSettings = self._container.settings_service.get()
        directory = Path(settings.default_export_dir or self._container.paths.default_export_dir)
        self.list_recent.clear()
        if not directory.exists():
            return
        files = sorted(
            (p for p in directory.iterdir() if p.suffix in {".csv", ".json", ".txt"}),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:25]
        for file in files:
            from datetime import datetime

            stamp = datetime.fromtimestamp(file.stat().st_mtime).strftime("%m-%d %H:%M")
            self.list_recent.addItem(f"{stamp}  {file.name}")

    def shutdown(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(10000)
