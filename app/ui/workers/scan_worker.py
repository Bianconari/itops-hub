"""ScanWorker — runs a network scan on a QThread with progress + cancel."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.domain.cancellation import CancelToken, OperationCancelled
from app.services.network_scan_service import NetworkScanService


class ScanWorker(QThread):
    progress = Signal(int, int)  # completed, total
    succeeded = Signal(object)  # ScanResult
    failed = Signal(str)  # user-presentable error
    cancelled = Signal()

    def __init__(
        self,
        service: NetworkScanService,
        cidr: str,
        authorized_override: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._cidr = cidr
        self._authorized = authorized_override
        self.token = CancelToken()

    def run(self) -> None:
        try:
            result = self._service.scan(
                self._cidr,
                token=self.token,
                authorized_override=self._authorized,
                on_progress=lambda done, total: self.progress.emit(done, total),
            )
        except OperationCancelled:
            self.cancelled.emit()
        except ValueError as exc:  # validation / authorization / cap errors
            self.failed.emit(f"{exc}")
        except Exception as exc:
            self.failed.emit(f"Scan failed: {exc}")
        else:
            self.succeeded.emit(result)
