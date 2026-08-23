"""Backups view — run local backups, watch progress, manage schedules."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.container import AppContainer
from app.domain.backup import BackupStatus
from app.domain.cancellation import CancelToken, OperationCancelled
from app.domain.formatters import as_local_string, human_bytes
from app.services.backup_service import BackupService
from app.services.settings_service import SettingsService
from app.ui.workers.one_shot import OneShotWorker

logger = logging.getLogger(__name__)

_HEADERS = ["Started", "Source", "Status", "Files", "Size", "Verified", "Error"]


class BackupWorker(QThread):
    progress = Signal(int, int, int)  # files_done, files_total, bytes_done
    succeeded = Signal(object)  # BackupJob
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, service: BackupService, source: str, dest: str, verify: bool, parent=None):
        super().__init__(parent)
        self._service = service
        self._source = source
        self._dest = dest
        self._verify = verify
        self.token = CancelToken()

    def run(self) -> None:
        try:
            job = self._service.run_backup(
                self._source,
                self._dest,
                verify_mode=self._verify_mode,
                token=self.token,
                on_progress=lambda done, total, bytez: self.progress.emit(done, total, bytez),
            )
        except OperationCancelled:
            self.cancelled.emit()
        except (OSError, ValueError) as exc:
            self.failed.emit(f"{exc}")
        else:
            if job.status is BackupStatus.FAILED:
                self.failed.emit(job.error_message or "backup failed")
            else:
                self.succeeded.emit(job)


class BackupView(QWidget):
    def __init__(self, container: AppContainer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._worker: BackupWorker | None = None
        self._profile_worker: OneShotWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        outer.addWidget(self._build_run_card())
        outer.addWidget(self._build_profiles_card())
        outer.addWidget(self._build_history_card(), stretch=1)

    # ------------------------------------------------------------------ UI
    def _build_run_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        title = QLabel("Backup now — originals are never modified or deleted")
        title.setProperty("cssClass", "subtitle")
        layout.addWidget(title)

        source_row = QHBoxLayout()
        self.edit_source = QLineEdit()
        self.edit_source.setObjectName("edit_backup_source")
        self.edit_source.setPlaceholderText("Source folder or file…")
        source_row.addWidget(self.edit_source, stretch=1)
        btn_source = QPushButton("Browse…")
        btn_source.setObjectName("btn_backup_source")
        btn_source.clicked.connect(lambda: self._pick_dir(self.edit_source, "Choose source folder"))
        source_row.addWidget(btn_source)
        layout.addLayout(source_row)

        dest_row = QHBoxLayout()
        self.edit_dest = QLineEdit()
        self.edit_dest.setObjectName("edit_backup_dest")
        self.edit_dest.setPlaceholderText("Destination folder…")
        dest_row.addWidget(self.edit_dest, stretch=1)
        btn_dest = QPushButton("Browse…")
        btn_dest.setObjectName("btn_backup_dest")
        btn_dest.clicked.connect(
            lambda: self._pick_dir(self.edit_dest, "Choose destination folder")
        )
        dest_row.addWidget(btn_dest)
        layout.addLayout(dest_row)

        actions = QHBoxLayout()
        verify_label = QLabel("Verification:")
        actions.addWidget(verify_label)
        self.combo_verify = QComboBox()
        self.combo_verify.setObjectName("combo_verify")
        self.combo_verify.addItem("Sizes & count (fast)", "size")
        self.combo_verify.addItem("SHA-256 (thorough)", "sha256")
        self.combo_verify.addItem("None", "none")
        actions.addWidget(self.combo_verify)
        actions.addStretch(1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_backup_cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel)
        actions.addWidget(self.btn_cancel)
        self.btn_run = QPushButton("Run backup")
        self.btn_run.setObjectName("btn_backup_run")
        self.btn_run.setProperty("cssClass", "primary")
        self.btn_run.clicked.connect(self._on_run)
        actions.addWidget(self.btn_run)
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setObjectName("backup_progress")
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.lbl_progress = QLabel("")
        self.lbl_progress.setObjectName("lbl_backup_progress")
        self.lbl_progress.setProperty("cssClass", "muted")
        layout.addWidget(self.lbl_progress)
        self.lbl_error = QLabel("")
        self.lbl_error.setProperty("cssClass", "danger")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)
        return card

    def _build_profiles_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("Scheduled backups (run by the background scheduler)")
        title.setProperty("cssClass", "subtitle")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(QLabel("Every"))
        self.spin_hours = QSpinBox()
        self.spin_hours.setObjectName("spin_profile_hours")
        self.spin_hours.setRange(1, 720)
        self.spin_hours.setSuffix(" h")
        self.spin_hours.setValue(24)
        header.addWidget(self.spin_hours)
        self.btn_add_profile = QPushButton("Save profile from above")
        self.btn_add_profile.setObjectName("btn_add_profile")
        self.btn_add_profile.clicked.connect(self._on_add_profile)
        header.addWidget(self.btn_add_profile)
        layout.addLayout(header)

        self.table_profiles = QTableWidget(0, 4)
        self.table_profiles.setObjectName("table_profiles")
        self.table_profiles.setHorizontalHeaderLabels(
            ["Name", "Source → Destination", "Interval", "Enabled"]
        )
        self.table_profiles.verticalHeader().setVisible(False)
        self.table_profiles.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_profiles.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_profiles.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_profiles.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_profiles)

        profile_actions = QHBoxLayout()
        self.btn_toggle_profile = QPushButton("Enable / disable selected")
        self.btn_toggle_profile.setObjectName("btn_toggle_profile")
        self.btn_toggle_profile.clicked.connect(self._on_toggle_profile)
        profile_actions.addWidget(self.btn_toggle_profile)
        self.btn_delete_profile = QPushButton("Delete selected")
        self.btn_delete_profile.setObjectName("btn_delete_profile")
        self.btn_delete_profile.clicked.connect(self._on_delete_profile)
        profile_actions.addWidget(self.btn_delete_profile)
        profile_actions.addStretch(1)
        layout.addLayout(profile_actions)
        return card

    def _build_history_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("History")
        title.setProperty("cssClass", "subtitle")
        header.addWidget(title)
        header.addStretch(1)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("btn_backup_refresh")
        self.btn_refresh.clicked.connect(self.refresh_history)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setObjectName("table_backups")
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        return card

    # ------------------------------------------------------------ run flow
    def _pick_dir(self, edit: QLineEdit, title: str) -> None:
        chosen = QFileDialog.getExistingDirectory(self, title)
        if chosen:
            edit.setText(chosen)

    def _on_run(self) -> None:
        if self._worker is not None:
            return
        source = self.edit_source.text().strip()
        dest = self.edit_dest.text().strip()
        self.lbl_error.setVisible(False)
        if not source or not dest:
            self._show_error("Choose both a source and a destination.")
            return
        assert self._container.backup_service is not None
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.lbl_progress.setText("Preparing…")

        self._worker = BackupWorker(
            self._container.backup_service, source, dest, self.combo_verify.currentData()
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished.connect(lambda: self._worker_gone(self._worker))
        self._worker.start()

    def _worker_gone(self, worker: BackupWorker | None) -> None:
        if worker is not None and self._worker is worker:
            self._worker = None

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.token.cancel()
            self.btn_cancel.setEnabled(False)
            self.lbl_progress.setText("Cancelling…")

    def _on_progress(self, done: int, total: int, bytes_done: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.lbl_progress.setText(f"{done} / {total} files · {human_bytes(bytes_done)} copied")

    def _on_done(self, job: object) -> None:
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(False)
        verb = "verified" if job.status is BackupStatus.VERIFIED else "completed"  # type: ignore[attr-defined]
        self.lbl_progress.setText(
            f"Backup {verb}: {job.files_copied} files, {human_bytes(job.size_bytes or 0)}"  # type: ignore[attr-defined]
        )
        self.refresh_history()

    def _on_failed(self, message: str) -> None:
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(False)
        self.lbl_progress.setText("Backup failed")
        self._show_error(message)

    def _on_cancelled(self) -> None:
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(False)
        self.lbl_progress.setText("Backup cancelled (partial copy removed)")

    def _show_error(self, message: str) -> None:
        self.lbl_error.setText(message)
        self.lbl_error.setVisible(True)

    # ------------------------------------------------------------ history
    def refresh_history(self) -> None:
        assert self._container.backup_service is not None
        jobs = self._container.backup_service.history(limit=50)
        self.table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            values = [
                as_local_string(job.started_at, "%m-%d %H:%M:%S"),
                f"{job.source} → {job.destination}",
                job.status.value,
                str(job.files_copied if job.files_copied is not None else "—"),
                human_bytes(job.size_bytes) if job.size_bytes is not None else "—",
                "Yes" if job.checksum_verified else ("No" if job.completed_at else "—"),
                job.error_message or "",
            ]
            for column, text in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(text))

    # ------------------------------------------------------------ profiles
    def refresh_profiles(self) -> None:
        assert self._container.settings_service is not None
        profiles = self._container.settings_service.get().backup_profiles
        self.table_profiles.setRowCount(len(profiles))
        for row, profile in enumerate(profiles):
            values = [
                profile.name,
                f"{profile.source} → {profile.destination}",
                f"{profile.interval_hours} h",
                "Yes" if profile.enabled else "No",
            ]
            for column, text in enumerate(values):
                self.table_profiles.setItem(row, column, QTableWidgetItem(text))

    def _on_add_profile(self) -> None:
        source = self.edit_source.text().strip()
        dest = self.edit_dest.text().strip()
        if not source or not dest:
            self._show_error("Fill in source and destination first, then save the profile.")
            return
        assert self._container.settings_service is not None
        service: SettingsService = self._container.settings_service
        profiles = list(service.get().backup_profiles)
        name = source.rstrip("/\\").split("/")[-1].split("\\")[-1] or "profile"
        base_name = name
        counter = 2
        while any(p.name == name for p in profiles):
            name = f"{base_name}-{counter}"
            counter += 1
        profiles.append(
            {
                "name": name,
                "source": source,
                "destination": dest,
                "interval_hours": self.spin_hours.value(),
                "enabled": True,
                "verify": self.combo_verify.currentData() != "none",
                "verify_mode": self.combo_verify.currentData(),
            }
        )
        service.update({"backup_profiles": profiles})
        self.refresh_profiles()

    def _selected_profile_index(self) -> int:
        selection = self.table_profiles.selectionModel().selectedRows()
        return selection[0].row() if selection else -1

    def _on_toggle_profile(self) -> None:
        index = self._selected_profile_index()
        if index < 0:
            return
        assert self._container.settings_service is not None
        service = self._container.settings_service
        profiles = [p.model_dump() for p in service.get().backup_profiles]
        profiles[index]["enabled"] = not profiles[index]["enabled"]
        service.update({"backup_profiles": profiles})
        self.refresh_profiles()

    def _on_delete_profile(self) -> None:
        index = self._selected_profile_index()
        if index < 0:
            return
        confirm = QMessageBox.question(
            self,
            "Delete profile",
            "Remove this scheduled backup profile? (Existing backups are kept.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        assert self._container.settings_service is not None
        service = self._container.settings_service
        profiles = [p.model_dump() for p in service.get().backup_profiles]
        profiles.pop(index)
        service.update({"backup_profiles": profiles})
        self.refresh_profiles()

    # ------------------------------------------------------------ lifecycle
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_history()
        self.refresh_profiles()

    def shutdown(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.token.cancel()
            self._worker.wait(15000)
        if self._profile_worker is not None and self._profile_worker.isRunning():
            self._profile_worker.wait(5000)
