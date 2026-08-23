"""UI tests — network view with an injected fake scan service (offscreen)."""

from __future__ import annotations

import pytest
from app.application.container import AppContainer
from app.domain.network import HostResult, ScanResult
from app.domain.time_utils import utc_now
from app.ui.views.network_view import NetworkView
from PySide6.QtCore import Qt

pytestmark = pytest.mark.ui


class FakeScanService:
    """Instant scan service double (same interface as NetworkScanService)."""

    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []

    def scan(self, cidr, *, token=None, authorized_override=False, on_progress=None):

        self.calls.append({"cidr": cidr, "authorized": authorized_override})
        if self.error:
            raise ValueError(self.error)
        if token is not None:
            token.raise_if_cancelled()
        now = utc_now()
        result = ScanResult(
            network=cidr,
            started_at=now,
            completed_at=now,
            duration_seconds=0.05,
            total=3,
            results=(
                HostResult(
                    ip="10.0.0.1",
                    reachable=True,
                    response_time_ms=2.0,
                    hostname="a.lan",
                    mac="aa:bb:cc:dd:ee:01",
                ),
                HostResult(ip="10.0.0.2", reachable=False, response_time_ms=None),
                HostResult(ip="10.0.0.3", reachable=True, response_time_ms=7.5),
            ),
        )
        if on_progress is not None:
            on_progress(3, 3)
        return result


@pytest.fixture
def network_view(container: AppContainer, tmp_path) -> NetworkView:
    container.settings_service.update({"default_export_dir": str(tmp_path / "exports")})
    view = NetworkView(container)
    yield view
    view.shutdown()
    view.deleteLater()


def attach_fake(container: AppContainer, fake: FakeScanService) -> None:
    container.network_scan_service = fake  # type: ignore[assignment]


class TestScanFlow:
    def test_scan_populates_results_and_summary(self, container, network_view, qtbot):
        attach_fake(container, FakeScanService())
        network_view.edit_cidr.setText("10.0.0.0/29")
        qtbot.mouseClick(network_view.btn_scan, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: network_view.table.rowCount() == 3, timeout=5000)
        assert "3 addresses" in network_view.lbl_summary.text()
        assert "2 reachable" in network_view.lbl_summary.text()
        assert network_view.btn_scan.isEnabled()
        assert not network_view.btn_cancel.isEnabled()
        assert network_view.btn_export_csv.isEnabled()

    def test_authorization_checkbox_forwarded(self, container, network_view, qtbot):
        fake = FakeScanService()
        attach_fake(container, fake)
        network_view.chk_authorized.setChecked(True)
        network_view.edit_cidr.setText("8.8.8.0/29")
        network_view._on_scan_clicked()
        qtbot.waitUntil(lambda: bool(fake.calls), timeout=5000)
        assert fake.calls[0]["authorized"] is True

    def test_empty_input_shows_error_without_scanning(self, container, network_view, qtbot):
        attach_fake(container, FakeScanService())
        network_view.edit_cidr.setText("   ")
        network_view._on_scan_clicked()
        assert "Enter a network" in network_view.lbl_error.text()
        assert network_view._worker is None

    def test_service_error_surfaces_in_label(self, container, network_view, qtbot):
        attach_fake(
            container,
            FakeScanService(error="8.8.8.0/29 is not a private range. Scanning requires..."),
        )
        network_view.edit_cidr.setText("8.8.8.0/29")
        network_view._on_scan_clicked()
        qtbot.waitUntil(lambda: network_view.lbl_error.text() != "", timeout=5000)
        assert "not a private range" in network_view.lbl_error.text()
        assert network_view.btn_scan.isEnabled()


class TestFilterAndExport:
    def test_reachable_only_hides_offline_rows(self, container, network_view, qtbot):
        attach_fake(container, FakeScanService())
        network_view.edit_cidr.setText("10.0.0.0/29")
        network_view._on_scan_clicked()
        qtbot.waitUntil(lambda: network_view.table.rowCount() == 3, timeout=5000)

        network_view.chk_reachable_only.setChecked(True)
        hidden = [
            network_view.table.isRowHidden(row) for row in range(network_view.table.rowCount())
        ]
        assert hidden.count(True) == 1  # the offline 10.0.0.2 row

    def test_export_csv_writes_real_file(self, container, network_view, qtbot, tmp_path):
        attach_fake(container, FakeScanService())
        network_view.edit_cidr.setText("10.0.0.0/29")
        network_view._on_scan_clicked()
        qtbot.waitUntil(lambda: network_view.table.rowCount() == 3, timeout=5000)

        network_view._on_export_clicked("csv")
        qtbot.waitUntil(lambda: network_view.lbl_export.text().startswith("Saved:"), timeout=5000)
        exported = list((tmp_path / "exports").glob("network-scan-*.csv"))
        assert len(exported) == 1
        assert exported[0].read_text(encoding="utf-8").startswith("ip,reachable")


class TestShutdown:
    def test_shutdown_safe_when_idle(self, network_view):
        network_view.shutdown()  # no workers running; must not raise
