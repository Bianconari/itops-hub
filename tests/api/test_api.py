"""API integration tests — the local FastAPI service (TestClient, real services).

Verifies the security model (token on everything except /api/health), the
shared-service wiring (same container the UI uses), validation errors, and
every documented endpoint group.
"""

from __future__ import annotations

import pytest
from app.api.app_factory import create_app
from app.application.container import AppContainer
from fastapi.testclient import TestClient
from tests.fakes import FakePinger


@pytest.fixture
def client(container: AppContainer) -> TestClient:
    # Deterministic monitoring checks through the shared service layer.
    assert container.monitor_service is not None
    container.monitor_service._pinger = FakePinger(reachable={"127.0.0.1"}, latency=25.0)
    app = create_app(container)
    return TestClient(app)


def auth_headers(container: AppContainer) -> dict[str, str]:
    return {"X-API-Token": container.api_token}


class TestSecurityModel:
    def test_health_open_without_token(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["application"] == "ITOps Hub"

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/system/info"),
            ("GET", "/api/system/metrics"),
            ("GET", "/api/monitoring/devices"),
            ("POST", "/api/monitoring/check"),
            ("GET", "/api/alerts"),
            ("GET", "/api/activity"),
            ("GET", "/api/backups"),
            ("GET", "/api/reports"),
        ],
    )
    def test_endpoints_require_token(self, client, method, path):
        response = client.post(path, json={}) if method == "POST" else client.get(path)
        assert response.status_code == 401

    def test_wrong_token_rejected(self, client):
        assert client.get("/api/system/info", headers={"X-API-Token": "nope"}).status_code == 401

    def test_openapi_requires_no_token_but_is_documentation(self, client):
        assert client.get("/openapi.json").status_code == 200
        document = client.get("/openapi.json").json()
        assert document["info"]["title"] == "ITOps Hub Local API"
        assert "/api/health" in document["paths"]
        assert "/api/network/scan" in document["paths"]


class TestSystemEndpoints:
    def test_system_info(self, client, container):
        response = client.get("/api/system/info", headers=auth_headers(container))
        assert response.status_code == 200
        body = response.json()
        assert body["hostname"]
        assert body["cpu_cores_logical"] >= 1
        assert isinstance(body["adapters"], list)

    def test_system_metrics_with_levels(self, client, container):
        body = client.get("/api/system/metrics", headers=auth_headers(container)).json()
        assert 0 <= body["cpu_percent"] <= 100
        assert body["levels"]["overall"] in ("ok", "warning", "critical")


class TestMonitoringEndpoints:
    def test_device_crud_and_check(self, client, container):
        headers = auth_headers(container)
        created = client.post(
            "/api/monitoring/devices",
            json={"name": "Loop", "host": "127.0.0.1", "interval_seconds": 30, "timeout_ms": 800},
            headers=headers,
        )
        assert created.status_code == 201
        device_id = created.json()["id"]

        listed = client.get("/api/monitoring/devices", headers=headers).json()
        assert any(d["name"] == "Loop" for d in listed)

        checked = client.post("/api/monitoring/check", headers=headers)
        assert checked.status_code == 200
        assert checked.json()["checked"] >= 1

        listed = client.get("/api/monitoring/devices", headers=headers).json()
        loop = next(d for d in listed if d["name"] == "Loop")
        assert loop["status"] == "online"
        assert loop["response_time_ms"] == 25.0

        # delete requires explicit confirm
        assert (
            client.delete(f"/api/monitoring/devices/{device_id}", headers=headers).status_code
            == 400
        )
        assert (
            client.delete(
                f"/api/monitoring/devices/{device_id}", params={"confirm": "true"}, headers=headers
            ).status_code
            == 200
        )

    def test_invalid_device_returns_400(self, client, container):
        response = client.post(
            "/api/monitoring/devices",
            json={"name": "x", "host": "bad host!", "interval_seconds": 30, "timeout_ms": 800},
            headers=auth_headers(container),
        )
        assert response.status_code == 400
        assert "Host" in response.json()["detail"]


class TestNetworkEndpoints:
    def test_scan_with_fake_service(self, client, container):
        container.network_scan_service = _FakeScanService()
        response = client.post(
            "/api/network/scan",
            json={"cidr": "10.0.0.0/29"},
            headers=auth_headers(container),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert body["reachable"] == 2

        results = client.get("/api/network/results", headers=auth_headers(container))
        assert results.status_code == 200
        assert results.json()["network"] == "10.0.0.0/29"

    def test_results_404_before_any_scan(self, client, container):
        response = client.get("/api/network/results", headers=auth_headers(container))
        assert response.status_code == 404

    def test_public_range_guarded(self, client, container):
        container.network_scan_service = _GuardingScanService()
        response = client.post(
            "/api/network/scan",
            json={"cidr": "8.8.8.0/24", "authorized": False},
            headers=auth_headers(container),
        )
        assert response.status_code == 400
        assert "not a private range" in response.json()["detail"]


class TestLogsEndpoints:
    def test_analyze_fixture(self, client, container, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(
            "2026-08-20 09:00:00,100 INFO app started\n"
            "2026-08-20 09:01:00,200 ERROR app boom 1\n"
            "2026-08-20 09:02:00,300 ERROR app boom 2\n"
        )
        body = client.post(
            "/api/logs/analyze", json={"path": str(log)}, headers=auth_headers(container)
        ).json()
        assert body["parser"] == "python-logging"
        assert body["counts"]["ERROR"] == 2

    def test_missing_file_400(self, client, container):
        response = client.post(
            "/api/logs/analyze",
            json={"path": "/nonexistent/x.log"},
            headers=auth_headers(container),
        )
        assert response.status_code == 400


class TestBackupEndpoints:
    def test_backup_run_and_history(self, client, container, tmp_path):
        source = tmp_path / "data"
        source.mkdir()
        (source / "a.txt").write_text("hello")
        body = client.post(
            "/api/backups",
            json={"source": str(source), "destination": str(tmp_path / "backups"), "verify": True},
            headers=auth_headers(container),
        ).json()
        assert body["status"] == "verified"
        assert body["files_copied"] == 1

        history = client.get("/api/backups", headers=auth_headers(container)).json()
        assert len(history) == 1

    def test_backup_bad_layout_400(self, client, container, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        response = client.post(
            "/api/backups",
            json={"source": str(source), "destination": str(source / "nested")},
            headers=auth_headers(container),
        )
        assert response.status_code == 400


class TestAlertsAndReports:
    def test_alerts_flow(self, client, container):
        headers = auth_headers(container)
        assert container.alert_service is not None
        raised = container.alert_service.raise_alert("t.api", "warning", "src", "api test alert")
        assert raised is not None

        body = client.get("/api/alerts", headers=headers).json()
        assert body["unacknowledged"] >= 1
        assert any(a["message"] == "api test alert" for a in body["alerts"])

        no_confirm = client.post(f"/api/alerts/{raised.id}/ack", json={}, headers=headers)
        assert no_confirm.status_code == 400
        confirmed = client.post(
            f"/api/alerts/{raised.id}/ack", json={"confirm": True}, headers=headers
        )
        assert confirmed.status_code == 200

    def test_reports_generate_pdf(self, client, container, tmp_path):
        headers = auth_headers(container)
        container.settings_service.update({"default_export_dir": str(tmp_path / "exports")})
        created = client.post(
            "/api/reports",
            json={"report_key": "activity", "format": "pdf", "hours": 24},
            headers=headers,
        )
        assert created.status_code == 201
        path = created.json()["path"]
        with open(path, "rb") as handle:
            assert handle.read(5) == b"%PDF-"

    def test_reports_generate_and_list(self, client, container, tmp_path):
        headers = auth_headers(container)
        container.settings_service.update({"default_export_dir": str(tmp_path / "exports")})
        created = client.post(
            "/api/reports",
            json={"report_key": "activity", "format": "csv", "hours": 24},
            headers=headers,
        )
        assert created.status_code == 201
        listed = client.get("/api/reports", headers=headers).json()
        assert any(item["name"].startswith("activity-") for item in listed)

    def test_activity_endpoint(self, client, container):
        assert container.activity_service is not None
        container.activity_service.record("api.test", module="tests", message="via api")
        body = client.get("/api/activity", headers=auth_headers(container)).json()
        assert isinstance(body, list) and any(e["action"] == "api.test" for e in body)


class _FakeScanService:
    def scan(self, cidr, *, token=None, authorized_override=False, on_progress=None):
        from app.domain.network import HostResult, ScanResult
        from app.domain.time_utils import utc_now

        now = utc_now()
        return ScanResult(
            network=cidr,
            started_at=now,
            completed_at=now,
            duration_seconds=0.01,
            total=3,
            results=(
                HostResult(ip="10.0.0.1", reachable=True, response_time_ms=1.0),
                HostResult(ip="10.0.0.2", reachable=True, response_time_ms=2.0),
                HostResult(ip="10.0.0.3", reachable=False, response_time_ms=None),
            ),
        )


class _GuardingScanService:
    def scan(self, cidr, *, token=None, authorized_override=False, on_progress=None):
        raise ValueError(f"{cidr} is not a private range. Scanning requires authorization.")
