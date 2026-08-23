"""Logs view — load a log file, analyze it, export the summary."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.container import AppContainer
from app.domain.cancellation import CancelToken, OperationCancelled
from app.domain.loganalysis import LogSummary
from app.services.log_analysis_service import LogAnalysisService
from app.ui.workers.one_shot import OneShotWorker

logger = logging.getLogger(__name__)


class LogWorker(QThread):
    progress = Signal(int, int)  # bytes_read, total_bytes
    succeeded = Signal(object)  # LogSummary
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, service: LogAnalysisService, path: str, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._path = path
        self.token = CancelToken()

    def run(self) -> None:
        try:
            summary = self._service.analyze(
                self._path,
                token=self.token,
                on_progress=lambda done, total: self.progress.emit(done, total),
            )
        except OperationCancelled:
            self.cancelled.emit()
        except ValueError as exc:
            self.failed.emit(f"{exc}")
        except OSError as exc:
            self.failed.emit(f"Could not read file: {exc}")
        else:
            self.succeeded.emit(summary)


class LogsView(QWidget):
    def __init__(self, container: AppContainer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        assert container.log_service is not None
        assert container.export_service is not None
        self._container = container
        self._worker: LogWorker | None = None
        self._export_worker: OneShotWorker | None = None
        self._last_summary: LogSummary | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        outer.addWidget(self._build_controls_card())
        outer.addWidget(self._build_results_card(), stretch=1)

    # ------------------------------------------------------------------ UI
    def _build_controls_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        title = QLabel("Log analyzer")
        title.setProperty("cssClass", "subtitle")
        layout.addWidget(title)

        row = QHBoxLayout()
        self.edit_path = QLineEdit()
        self.edit_path.setObjectName("edit_log_path")
        self.edit_path.setPlaceholderText("Path to a log file…")
        row.addWidget(self.edit_path, stretch=1)
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.setObjectName("btn_log_browse")
        self.btn_browse.clicked.connect(self._browse)
        row.addWidget(self.btn_browse)
        self.btn_analyze = QPushButton("Analyze")
        self.btn_analyze.setObjectName("btn_analyze")
        self.btn_analyze.setProperty("cssClass", "primary")
        self.btn_analyze.clicked.connect(self._on_analyze)
        row.addWidget(self.btn_analyze)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_log_cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel)
        row.addWidget(self.btn_cancel)
        layout.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setObjectName("log_progress")
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.lbl_parser = QLabel("")
        self.lbl_parser.setProperty("cssClass", "muted")
        layout.addWidget(self.lbl_parser)

        self.lbl_error = QLabel("")
        self.lbl_error.setProperty("cssClass", "danger")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)
        return card

    def _build_results_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("Results")
        title.setProperty("cssClass", "subtitle")
        header.addWidget(title)
        header.addStretch(1)
        self.lbl_levels = QLabel("No analysis yet")
        self.lbl_levels.setProperty("cssClass", "muted")
        header.addWidget(self.lbl_levels)
        for fmt, name in (("csv", "CSV"), ("json", "JSON"), ("txt", "TXT")):
            button = QPushButton(f"Export {name}")
            button.setObjectName(f"btn_log_export_{fmt}")
            button.setEnabled(False)
            button.clicked.connect(lambda _=False, f=fmt: self._on_export(f))
            header.addWidget(button)
            setattr(self, f"btn_log_export_{fmt}", button)
        layout.addLayout(header)

        self.table = QTableWidget(0, 2)
        self.table.setObjectName("table_log_errors")
        self.table.setHorizontalHeaderLabels(["Count", "Message (normalized)"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, stretch=1)

        self.lbl_anomalies = QLabel("")
        self.lbl_anomalies.setObjectName("lbl_anomalies")
        self.lbl_anomalies.setWordWrap(True)
        self.lbl_anomalies.setProperty("cssClass", "warning")
        layout.addWidget(self.lbl_anomalies)

        self.lbl_export = QLabel("")
        self.lbl_export.setProperty("cssClass", "success")
        layout.addWidget(self.lbl_export)
        return card

    # ------------------------------------------------------------ analysis
    def _browse(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Choose a log file")
        if chosen:
            self.edit_path.setText(chosen)

    def _on_analyze(self) -> None:
        if self._worker is not None:
            return
        path = self.edit_path.text().strip()
        self.lbl_error.setVisible(False)
        self.lbl_export.setText("")
        self.btn_analyze.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)

        assert self._container.log_service is not None
        self._worker = LogWorker(self._container.log_service, path)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished.connect(lambda: self._worker_gone(self._worker))
        self._worker.start()

    def _worker_gone(self, worker: LogWorker | None) -> None:
        if worker is not None and self._worker is worker:
            self._worker = None

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.token.cancel()
            self.btn_cancel.setEnabled(False)

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)

    def _on_done(self, summary: object) -> None:
        self._last_summary = summary
        self.btn_analyze.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(False)
        self._populate(summary)
        for fmt in ("csv", "json", "txt"):
            getattr(self, f"btn_log_export_{fmt}").setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self.btn_analyze.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(False)
        self.lbl_error.setText(message)
        self.lbl_error.setVisible(True)

    def _on_cancelled(self) -> None:
        self.btn_analyze.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(False)
        self.lbl_parser.setText("Analysis cancelled")

    def _populate(self, summary: object) -> None:
        from app.domain.formatters import as_local_string

        counts = summary.counts  # type: ignore[attr-defined]
        self.lbl_parser.setText(
            f"Parser: {summary.parser_name} · {summary.total_lines} lines · "  # type: ignore[attr-defined]
            f"{summary.duration_seconds:.2f}s"
            + (
                " · "
                + as_local_string(summary.first_timestamp)  # type: ignore[attr-defined]
                + " → "
                + as_local_string(summary.last_timestamp)  # type: ignore[attr-defined]
                if summary.first_timestamp is not None  # type: ignore[attr-defined]
                else ""
            )
        )
        levels = " · ".join(
            f"{level}: {counts.get(level, 0)}"
            for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNKNOWN")
        )
        self.lbl_levels.setText(levels)

        top = list(summary.top_errors)  # type: ignore[attr-defined]
        self.table.setRowCount(len(top))
        for row, (count, message) in enumerate(top):
            self.table.setItem(row, 0, QTableWidgetItem(str(count)))
            self.table.setItem(row, 1, QTableWidgetItem(message))
        anomalies = list(summary.anomalies)  # type: ignore[attr-defined]
        self.lbl_anomalies.setText(
            "Anomalies: " + ("; ".join(anomalies) if anomalies else "none detected")
        )

    # ------------------------------------------------------------ export
    def _on_export(self, fmt: str) -> None:
        if self._worker is not None or self._export_worker is not None:
            return
        assert self._container.export_service is not None
        summary = self._last_summary

        def export():
            return self._container.export_service.export_log_analysis(summary, fmt)  # type: ignore[arg-type]

        self._export_worker = OneShotWorker(export)
        self._export_worker.succeeded.connect(
            lambda path: self.lbl_export.setText(f"Saved: {path}")
        )
        self._export_worker.failed.connect(
            lambda message: self.lbl_error.setText(f"Export failed: {message}")
        )
        self._export_worker.finished.connect(lambda: self._export_finished(self._export_worker))
        self._export_worker.start()

    def _export_finished(self, worker: OneShotWorker | None) -> None:
        if worker is not None and self._export_worker is worker:
            self._export_worker = None

    def shutdown(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.token.cancel()
            self._worker.wait(10000)
        if self._export_worker is not None and self._export_worker.isRunning():
            self._export_worker.wait(5000)
