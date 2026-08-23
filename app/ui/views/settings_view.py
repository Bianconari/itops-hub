"""Settings view — fully functional from v0.3.

Reads/writes settings through ``SettingsService`` only (no storage access in
this widget). Validation errors are surfaced as user-readable messages.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.application.container import AppContainer
from app.config.paths import AppPaths
from app.config.settings import AppSettings, Theme


class SettingsView(QWidget):
    def __init__(self, container: AppContainer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._loading = False

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

        heading = QLabel("Settings")
        heading.setProperty("cssClass", "title")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        # --- Appearance ---
        self.combo_theme = QComboBox()
        self.combo_theme.setObjectName("combo_theme")
        self.combo_theme.addItem("Light", Theme.LIGHT.value)
        self.combo_theme.addItem("Dark", Theme.DARK.value)
        self.combo_theme.addItem("Follow system", Theme.SYSTEM.value)
        form.addRow(QLabel("Theme"), self.combo_theme)

        language = QLabel("English  (more languages via the Qt Linguist pipeline — see docs)")
        language.setProperty("cssClass", "muted")
        form.addRow(QLabel("Language"), language)

        # --- Behavior ---
        self.combo_log_level = QComboBox()
        self.combo_log_level.setObjectName("combo_log_level")
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            self.combo_log_level.addItem(level)
        form.addRow(QLabel("Log level"), self.combo_log_level)

        self.spin_interval = QSpinBox()
        self.spin_interval.setObjectName("spin_interval")
        self.spin_interval.setRange(5, 3600)
        self.spin_interval.setSuffix(" s")
        form.addRow(QLabel("Monitor interval (new devices)"), self.spin_interval)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setObjectName("spin_timeout")
        self.spin_timeout.setRange(100, 10000)
        self.spin_timeout.setSuffix(" ms")
        form.addRow(QLabel("Ping timeout (new devices)"), self.spin_timeout)

        self.spin_retention = QSpinBox()
        self.spin_retention.setObjectName("spin_retention")
        self.spin_retention.setRange(1, 3650)
        self.spin_retention.setSuffix(" days")
        form.addRow(QLabel("History retention"), self.spin_retention)

        # --- Disk thresholds ---
        self.spin_disk_warning = QSpinBox()
        self.spin_disk_warning.setObjectName("spin_disk_warning")
        self.spin_disk_warning.setRange(1, 100)
        self.spin_disk_warning.setSuffix(" %")
        form.addRow(QLabel("Disk warning threshold"), self.spin_disk_warning)

        self.spin_disk_critical = QSpinBox()
        self.spin_disk_critical.setObjectName("spin_disk_critical")
        self.spin_disk_critical.setRange(1, 100)
        self.spin_disk_critical.setSuffix(" %")
        form.addRow(QLabel("Disk critical threshold"), self.spin_disk_critical)

        # --- Network scanner ---
        self.spin_workers = QSpinBox()
        self.spin_workers.setObjectName("spin_workers")
        self.spin_workers.setRange(1, 512)
        form.addRow(QLabel("Scan concurrency (workers)"), self.spin_workers)

        self.chk_private_only = QCheckBox("Require private ranges unless explicitly overridden")
        self.chk_private_only.setObjectName("chk_private_only")
        form.addRow(QLabel("Authorized-scan guard"), self.chk_private_only)

        # --- Exports ---
        export_row = QHBoxLayout()
        self.edit_export_dir = QLineEdit()
        self.edit_export_dir.setObjectName("edit_export_dir")
        self.edit_export_dir.setPlaceholderText(f"Default: {AppPaths.create().default_export_dir}")
        export_row.addWidget(self.edit_export_dir)
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.setObjectName("btn_browse")
        self.btn_browse.clicked.connect(self._browse_export_dir)
        export_row.addWidget(self.btn_browse)
        export_wrapper = QWidget()
        export_wrapper.setLayout(export_row)
        form.addRow(QLabel("Default export directory"), export_wrapper)

        # --- Notifications ---
        self.chk_inapp = QCheckBox("In-app notifications")
        self.chk_inapp.setObjectName("chk_inapp")
        form.addRow(QLabel("Notifications"), self.chk_inapp)

        self.chk_desktop = QCheckBox("Desktop (system tray) notifications")
        self.chk_desktop.setObjectName("chk_desktop")
        form.addRow(QLabel(""), self.chk_desktop)

        layout.addLayout(form)

        # --- Save ---
        buttons = QHBoxLayout()
        self.btn_save = QPushButton("Save settings")
        self.btn_save.setObjectName("btn_save")
        self.btn_save.setProperty("cssClass", "primary")
        self.btn_save.clicked.connect(self._on_save)
        buttons.addWidget(self.btn_save)
        buttons.addStretch(1)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("lbl_status")
        buttons.addWidget(self.lbl_status)
        layout.addLayout(buttons)
        layout.addStretch(1)

        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        settings = self._settings()
        self._loading = True
        try:
            index = self.combo_theme.findData(settings.theme.value)
            self.combo_theme.setCurrentIndex(max(index, 0))
            self.combo_log_level.setCurrentText(settings.log_level.value)
            self.spin_interval.setValue(settings.monitoring.interval_seconds)
            self.spin_timeout.setValue(settings.monitoring.timeout_ms)
            self.spin_retention.setValue(settings.retention_days)
            self.spin_disk_warning.setValue(int(settings.disk.warning_percent))
            self.spin_disk_critical.setValue(int(settings.disk.critical_percent))
            self.spin_workers.setValue(settings.scan_max_workers)
            self.chk_private_only.setChecked(settings.scan_private_only)
            self.edit_export_dir.setText(
                str(settings.default_export_dir) if settings.default_export_dir else ""
            )
            self.chk_inapp.setChecked(settings.notifications.in_app)
            self.chk_desktop.setChecked(settings.notifications.desktop)
            self._set_status("", "")
        finally:
            self._loading = False

    def _on_save(self) -> None:
        if self._loading:
            return
        export_text = self.edit_export_dir.text().strip()
        changes = {
            "theme": self.combo_theme.currentData(),
            "log_level": self.combo_log_level.currentText(),
            "monitoring": {
                "interval_seconds": self.spin_interval.value(),
                "timeout_ms": self.spin_timeout.value(),
            },
            "retention_days": self.spin_retention.value(),
            "disk": {
                "warning_percent": float(self.spin_disk_warning.value()),
                "critical_percent": float(self.spin_disk_critical.value()),
            },
            "scan_max_workers": self.spin_workers.value(),
            "scan_private_only": self.chk_private_only.isChecked(),
            "default_export_dir": export_text or None,
            "notifications": {
                "in_app": self.chk_inapp.isChecked(),
                "desktop": self.chk_desktop.isChecked(),
            },
        }
        self.btn_save.setEnabled(False)
        try:
            self._container.settings_service.update(changes)
        except ValueError as exc:  # pydantic ValidationError is a ValueError
            self._set_status(f"Not saved: {exc}", "danger")
        else:
            self._set_status("Saved", "success")
        finally:
            self.btn_save.setEnabled(True)

    def _browse_export_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose default export directory")
        if chosen:
            self.edit_export_dir.setText(chosen)

    def _set_status(self, text: str, css_class: str) -> None:
        self.lbl_status.setText(text)
        self.lbl_status.setProperty("cssClass", css_class)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)

    def _settings(self) -> AppSettings:
        assert self._container.settings_service is not None
        return self._container.settings_service.get()
