"""Network view — authorized CIDR scanning with progress, cancel, export.

The scan runs on a ScanWorker QThread (UI never blocks); the authorization
checkbox is required for non-private ranges (guard from AD-002 / Spec §15).
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
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
from app.domain.formatters import as_local_string
from app.domain.network import ScanResult
from app.ui.workers.one_shot import OneShotWorker
from app.ui.workers.scan_worker import ScanWorker

logger = logging.getLogger(__name__)

_HEADERS = ["IP address", "Reachable", "Response", "Hostname", "MAC", "Checked at"]


class NetworkView(QWidget):
    def __init__(self, container: AppContainer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Services are resolved lazily so the container can be re-pointed in
        # tests; production wires them before the view is ever used.
        self._container = container

        self._worker: ScanWorker | None = None
        self._export_worker: OneShotWorker | None = None
        self._last_result: ScanResult | None = None

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

        title = QLabel("Network scanner — scan only networks you administer")
        title.setProperty("cssClass", "subtitle")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.edit_cidr = QLineEdit()
        self.edit_cidr.setObjectName("edit_cidr")
        self.edit_cidr.setPlaceholderText("192.168.1.0/24")
        self.edit_cidr.setFixedWidth(220)
        row.addWidget(self.edit_cidr)

        self.btn_scan = QPushButton("Scan")
        self.btn_scan.setObjectName("btn_scan")
        self.btn_scan.setProperty("cssClass", "primary")
        self.btn_scan.clicked.connect(self._on_scan_clicked)
        row.addWidget(self.btn_scan)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        row.addWidget(self.btn_cancel)
        row.addStretch(1)
        layout.addLayout(row)

        self.chk_authorized = QCheckBox(
            "I am authorized to administer this network (required for public ranges)"
        )
        self.chk_authorized.setObjectName("chk_authorized")
        layout.addWidget(self.chk_authorized)

        self.progress = QProgressBar()
        self.progress.setObjectName("scan_progress")
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setObjectName("lbl_summary")
        self.lbl_summary.setProperty("cssClass", "muted")
        layout.addWidget(self.lbl_summary)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("lbl_error")
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

        self.chk_reachable_only = QCheckBox("Only reachable")
        self.chk_reachable_only.setObjectName("chk_reachable_only")
        self.chk_reachable_only.toggled.connect(self._apply_filter)
        header.addWidget(self.chk_reachable_only)

        for fmt, name in (
            ("csv", "Export CSV"),
            ("json", "Export JSON"),
            ("txt", "Export TXT"),
            ("pdf", "Export PDF"),
        ):
            button = QPushButton(name)
            button.setObjectName(f"btn_export_{fmt}")
            button.setEnabled(False)
            button.clicked.connect(lambda _=False, f=fmt: self._on_export_clicked(f))
            header.addWidget(button)
            setattr(self, f"btn_export_{fmt}", button)
        layout.addLayout(header)

        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setObjectName("table_scan_results")
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        table_header = self.table.horizontalHeader()
        table_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, stretch=1)

        self.lbl_export = QLabel("")
        self.lbl_export.setObjectName("lbl_export")
        self.lbl_export.setProperty("cssClass", "success")
        self.lbl_export.setWordWrap(True)
        layout.addWidget(self.lbl_export)
        return card

    # ------------------------------------------------------------ scanning
    def _on_scan_clicked(self) -> None:
        if self._worker is not None:
            return
        cidr = self.edit_cidr.text().strip()
        if not cidr:
            self._show_error("Enter a network in CIDR notation, e.g. 192.168.1.0/24")
            return
        self.lbl_error.setVisible(False)
        self.lbl_export.setText("")
        self.lbl_summary.setText("Starting…")
        self.btn_scan.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.table.setRowCount(0)

        assert self._container.network_scan_service is not None
        self._worker = ScanWorker(
            self._container.network_scan_service,
            cidr,
            self.chk_authorized.isChecked(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_scan_done)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.cancelled.connect(self._on_scan_cancelled)
        self._worker.finished.connect(lambda: self._worker_done(self._worker))
        self._worker.start()

    def _worker_done(self, worker: ScanWorker | None) -> None:
        if worker is not None and self._worker is worker:
            self._worker = None

    def _on_cancel_clicked(self) -> None:
        if self._worker is not None:
            self._worker.token.cancel()
            self.btn_cancel.setEnabled(False)
            self.lbl_summary.setText("Cancelling…")

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.lbl_summary.setText(f"Checking {done} / {total} addresses…")

    def _on_scan_done(self, result: object) -> None:
        scan_result = result  # type: ignore[assignment]
        self._last_result = scan_result
        self.btn_scan.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(False)
        self._populate(scan_result)
        state = "cancelled" if scan_result.cancelled else "completed"
        self.lbl_summary.setText(
            f"{scan_result.total} addresses · {scan_result.reachable_count} reachable · "
            f"{scan_result.duration_seconds:.1f}s · {state}"
        )
        for fmt in ("csv", "json", "txt", "pdf"):
            getattr(self, f"btn_export_{fmt}").setEnabled(bool(scan_result.results))

    def _on_scan_cancelled(self) -> None:
        # Instant cancel before any results: reset state without touching
        # the previous scan's rows (never show stale data as current).
        self.btn_scan.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(False)
        self.lbl_summary.setText("Scan cancelled before results were collected")

    def _on_scan_failed(self, message: str) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(False)
        self.lbl_summary.setText("Scan failed")
        self._show_error(message)
        logger.warning("scan failed: %s", message)

    def _show_error(self, message: str) -> None:
        self.lbl_error.setText(message)
        self.lbl_error.setVisible(True)

    # ------------------------------------------------------------ results
    def _populate(self, result: ScanResult) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(result.results))
        for row, host in enumerate(result.results):
            values = [
                host.ip,
                "Yes" if host.reachable else "No",
                f"{host.response_time_ms:.1f} ms" if host.response_time_ms is not None else "—",
                host.hostname or "—",
                host.mac or "—",
                as_local_string(host.timestamp, "%H:%M:%S"),
            ]
            for column, text in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(text))
        self.table.setSortingEnabled(True)
        self._apply_filter()

    def _apply_filter(self) -> None:
        reachable_only = self.chk_reachable_only.isChecked()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            hide = reachable_only and item is not None and item.text() == "No"
            self.table.setRowHidden(row, hide)

    # ------------------------------------------------------------ export
    def _on_export_clicked(self, fmt: str) -> None:
        if self._last_result is None or self._export_worker is not None:
            return
        self.lbl_export.setText("")
        for name in ("csv", "json", "txt"):
            getattr(self, f"btn_export_{name}").setEnabled(False)

        assert self._container.export_service is not None

        def export():
            return self._container.export_service.export_scan(self._last_result, fmt)  # type: ignore[arg-type]

        self._export_worker = OneShotWorker(export)
        self._export_worker.succeeded.connect(self._on_export_done)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.finished.connect(lambda: self._export_finished(self._export_worker))
        self._export_worker.start()

    def _export_finished(self, worker: OneShotWorker | None) -> None:
        if worker is not None and self._export_worker is worker:
            self._export_worker = None
        if self._last_result is not None and self._last_result.results:
            for name in ("csv", "json", "txt", "pdf"):
                getattr(self, f"btn_export_{name}").setEnabled(True)

    def _on_export_done(self, path: object) -> None:
        self.lbl_export.setText(f"Saved: {path}")

    def _on_export_failed(self, message: str) -> None:
        self.lbl_export.setProperty("cssClass", "danger")
        self.lbl_export.style().unpolish(self.lbl_export)
        self.lbl_export.style().polish(self.lbl_export)
        self.lbl_export.setText(f"Export failed: {message}")

    # ------------------------------------------------------------ teardown
    def shutdown(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.token.cancel()
            self._worker.wait(15000)
        if self._export_worker is not None and self._export_worker.isRunning():
            self._export_worker.wait(5000)
