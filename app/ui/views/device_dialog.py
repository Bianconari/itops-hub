"""Add/Edit device dialog (pure form, validation via MonitorService on save)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)


@dataclass(frozen=True)
class DeviceFormResult:
    name: str
    host: str
    interval_seconds: int
    timeout_ms: int
    enabled: bool


class DeviceDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        name: str = "",
        host: str = "",
        interval_seconds: int = 30,
        timeout_ms: int = 1500,
        enabled: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add device" if not name else "Edit device")
        form = QFormLayout(self)

        self.edit_name = QLineEdit(name)
        self.edit_name.setPlaceholderText("Office router")
        form.addRow("Name", self.edit_name)

        self.edit_host = QLineEdit(host)
        self.edit_host.setPlaceholderText("192.168.1.1")
        form.addRow("Host / IP", self.edit_host)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(5, 3600)
        self.spin_interval.setSuffix(" s")
        self.spin_interval.setValue(interval_seconds)
        form.addRow("Check interval", self.spin_interval)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(100, 10000)
        self.spin_timeout.setSuffix(" ms")
        self.spin_timeout.setValue(timeout_ms)
        form.addRow("Ping timeout", self.spin_timeout)

        self.chk_enabled = QCheckBox("Enabled")
        self.chk_enabled.setChecked(enabled)
        form.addRow("", self.chk_enabled)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def result_values(self) -> DeviceFormResult:
        return DeviceFormResult(
            name=self.edit_name.text().strip(),
            host=self.edit_host.text().strip(),
            interval_seconds=self.spin_interval.value(),
            timeout_ms=self.spin_timeout.value(),
            enabled=self.chk_enabled.isChecked(),
        )
