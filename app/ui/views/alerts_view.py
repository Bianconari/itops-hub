"""Alerts view — inbox with acknowledge actions and filters."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
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
from app.domain.entities import AlertRecord, Severity
from app.domain.formatters import as_local_string
from app.services.alert_service import AlertService
from app.ui.theme.theme_service import ThemeService

_HEADERS = ["Time", "Severity", "Type", "Source", "Message", "Acknowledged"]
_REFRESH_MS = 10_000

_SEVERITY_COLOR = {
    Severity.INFO: "primary",
    Severity.WARNING: "warning",
    Severity.CRITICAL: "danger",
}


class AlertsView(QWidget):
    def __init__(
        self,
        container: AppContainer,
        theme_service: ThemeService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        assert container.alert_service is not None
        self._alerts: AlertService = container.alert_service
        self._theme = theme_service
        self._records: list[AlertRecord] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("card")
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Alerts")
        title.setProperty("cssClass", "subtitle")
        header.addWidget(title)
        header.addStretch(1)

        self.chk_unack = QCheckBox("Unacknowledged only")
        self.chk_unack.setObjectName("chk_unack")
        self.chk_unack.toggled.connect(self.refresh)
        header.addWidget(self.chk_unack)

        self.btn_ack = QPushButton("Acknowledge selected")
        self.btn_ack.setObjectName("btn_ack")
        self.btn_ack.clicked.connect(self._ack_selected)
        header.addWidget(self.btn_ack)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("btn_alerts_refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setProperty("cssClass", "muted")
        layout.addWidget(self.lbl_summary)

        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setObjectName("table_alerts")
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()
        self._timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def refresh(self) -> None:
        records = (
            self._alerts.unacknowledged(limit=200)
            if self.chk_unack.isChecked()
            else self._alerts.recent(limit=200)
        )
        self._records = records
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                as_local_string(record.created_at, "%m-%d %H:%M:%S"),
                record.severity.value.upper(),
                record.type,
                record.source,
                record.message,
                "Yes" if record.acknowledged else "No",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 1:
                    color = getattr(self._theme.tokens, _SEVERITY_COLOR[record.severity])
                    item.setForeground(QColor(color))
                self.table.setItem(row, column, item)
        unack = len(self._alerts.unacknowledged(limit=1000))
        self.lbl_summary.setText(f"{len(records)} shown · {unack} unacknowledged open")

    def _ack_selected(self) -> None:
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            QMessageBox.information(self, "Acknowledge", "Select an alert first.")
            return
        record = self._records[selection[0].row()]
        if record.id is not None and not self._alerts.acknowledge(record.id):
            QMessageBox.information(self, "Acknowledge", "Alert was already acknowledged.")
        self.refresh()
