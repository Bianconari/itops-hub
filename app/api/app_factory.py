"""FastAPI application factory — the local API (v1.5).

Security model (AD-010):
- Binds loopback only by default; the desktop app starts it opt-in.
- Every /api/* route except /api/health requires the per-session token in
  the ``X-API-Token`` header (auto-generated at app start; also written to
  the user data directory for local scripts).
- Destructive/scan operations carry their own confirmation semantics
  (device delete requires confirm; public-range scans require authorized).

The API composes the exact same services the desktop UI uses — there is no
duplicated business logic by construction.
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.schemas import (
    AckRequest,
    BackupRequest,
    DeviceCreate,
    LogAnalyzeRequest,
    ReportRequest,
    ScanRequest,
)
from app.application.container import AppContainer
from app.domain.time_utils import utc_now

logger = logging.getLogger(__name__)

TOKEN_HEADER = "X-API-Token"


def write_token_file(container: AppContainer) -> None:
    """Persist the per-session API token next to the data directory.

    Called by both entry points (embedded and ``python -m app.api``) so the
    token is always discoverable for local scripting. POSIX permissions are
    tightened where the platform supports it.
    """
    import contextlib
    from pathlib import Path

    token_file = Path(container.paths.base) / "api-token"
    with contextlib.suppress(OSError):
        token_file.write_text(container.api_token, encoding="utf-8")
        token_file.chmod(0o600)  # POSIX only; Windows relies on user-profile ACLs


_EXEMPT_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


def create_app(container: AppContainer) -> FastAPI:
    """Build the FastAPI app bound to an application container."""
    app = FastAPI(
        title="ITOps Hub Local API",
        version=__version__,
        description=(
            "Local-only API for ITOps Hub. Requires the per-session "
            "`X-API-Token` header on every endpoint except /api/health. "
            "The token file lives in the application data directory."
        ),
    )
    app.state.container = container
    app.state.last_scan = None

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if request.url.path.startswith("/api") and request.url.path not in _EXEMPT_PATHS:
            provided = request.headers.get(TOKEN_HEADER, "")
            if not secrets.compare_digest(provided, container.api_token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "missing or invalid X-API-Token header"},
                )
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def validation_error(_request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": f"{exc}"})

    def _services() -> Any:
        return container

    # ---------------------------------------------------------------- health
    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "application": "ITOps Hub",
            "version": __version__,
            "time": utc_now().isoformat(),
        }

    # ---------------------------------------------------------------- system
    @app.get("/api/system/info", tags=["system"])
    def system_info() -> dict[str, Any]:
        services = _services()
        assert services.system_service is not None
        info = services.system_service.get_info()
        return {
            "hostname": info.hostname,
            "os": f"{info.os_name} {info.os_version}",
            "architecture": info.os_architecture,
            "cpu_model": info.cpu_model,
            "cpu_cores_physical": info.cpu_cores_physical,
            "cpu_cores_logical": info.cpu_cores_logical,
            "memory_total_bytes": info.memory_total_bytes,
            "boot_time": info.boot_time.isoformat(),
            "adapters": [
                {
                    "name": adapter.name,
                    "up": adapter.is_up,
                    "speed_mbps": adapter.speed_mbps,
                    "ipv4": list(adapter.ipv4),
                    "ipv6": list(adapter.ipv6),
                }
                for adapter in info.adapters
            ],
        }

    @app.get("/api/system/metrics", tags=["system"])
    def system_metrics() -> dict[str, Any]:
        services = _services()
        assert services.system_service is not None
        status = services.system_service.get_status()
        return {
            "timestamp": status.metrics.timestamp.isoformat(),
            "cpu_percent": status.metrics.cpu_percent,
            "memory_percent": status.metrics.memory_percent,
            "disk_percent_max": status.metrics.disk_percent_max,
            "levels": {
                "cpu": status.cpu_level.value,
                "memory": status.memory_level.value,
                "disk": status.disk_level.value if status.disk_level else None,
                "overall": status.overall_level.value,
            },
        }

    # ---------------------------------------------------------------- network
    @app.post("/api/network/scan", tags=["network"])
    def network_scan(request: ScanRequest) -> dict[str, Any]:
        services = _services()
        assert services.network_scan_service is not None
        result = services.network_scan_service.scan(
            request.cidr, authorized_override=request.authorized
        )
        app.state.last_scan = result
        return _scan_payload(result)

    @app.get("/api/network/results", tags=["network"])
    def network_results() -> dict[str, Any]:
        if app.state.last_scan is None:
            raise HTTPException(status_code=404, detail="no scan has been run in this session")
        return _scan_payload(app.state.last_scan)

    # ---------------------------------------------------------------- monitoring
    @app.get("/api/monitoring/devices", tags=["monitoring"])
    def list_devices() -> list[dict[str, Any]]:
        services = _services()
        assert services.monitor_service is not None
        return [_device_payload(row) for row in services.monitor_service.status_rows()]

    @app.post("/api/monitoring/devices", tags=["monitoring"], status_code=201)
    def create_device(payload: DeviceCreate) -> dict[str, Any]:
        services = _services()
        assert services.monitor_service is not None
        device = services.monitor_service.add_device(
            payload.name, payload.host, payload.interval_seconds, payload.timeout_ms
        )
        return {
            "id": device.id,
            "name": device.name,
            "host": device.host,
            "interval_seconds": device.interval_seconds,
            "timeout_ms": device.timeout_ms,
            "enabled": device.enabled,
        }

    @app.delete("/api/monitoring/devices/{device_id}", tags=["monitoring"])
    def delete_device(device_id: int, confirm: bool = False) -> dict[str, Any]:
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="pass ?confirm=true to delete (removes history too)",
            )
        services = _services()
        assert services.monitor_service is not None
        if not services.monitor_service.delete_device(device_id):
            raise HTTPException(status_code=404, detail="device not found")
        return {"deleted": device_id}

    @app.post("/api/monitoring/check", tags=["monitoring"])
    def monitoring_check() -> dict[str, Any]:
        services = _services()
        assert services.monitor_service is not None
        results = services.monitor_service.run_round()
        return {"checked": len(results), "results": [_result_payload(r) for r in results]}

    # ---------------------------------------------------------------- logs
    @app.post("/api/logs/analyze", tags=["logs"])
    def logs_analyze(request: LogAnalyzeRequest) -> dict[str, Any]:
        services = _services()
        assert services.log_service is not None
        summary = services.log_service.analyze(request.path)
        return {
            "parser": summary.parser_name,
            "total_lines": summary.total_lines,
            "counts": summary.counts,
            "errors": summary.error_count,
            "top_errors": [
                {"count": count, "message": message} for count, message in summary.top_errors
            ],
            "first_timestamp": summary.first_timestamp.isoformat()
            if summary.first_timestamp
            else None,
            "last_timestamp": summary.last_timestamp.isoformat()
            if summary.last_timestamp
            else None,
            "anomalies": list(summary.anomalies),
        }

    # ---------------------------------------------------------------- backups
    @app.post("/api/backups", tags=["backups"])
    def run_backup(request: BackupRequest) -> dict[str, Any]:
        services = _services()
        assert services.backup_service is not None
        mode = request.verify_mode or ("size" if request.verify else "none")
        job = services.backup_service.run_backup(
            request.source, request.destination, verify_mode=mode
        )
        return _backup_payload(job)

    @app.get("/api/backups", tags=["backups"])
    def backup_history() -> list[dict[str, Any]]:
        services = _services()
        assert services.backup_service is not None
        return [_backup_payload(job) for job in services.backup_service.history()]

    # ---------------------------------------------------------------- alerts
    @app.get("/api/alerts", tags=["alerts"])
    def alerts(limit: int = 50) -> dict[str, Any]:
        services = _services()
        assert services.alert_service is not None
        recent = services.alert_service.recent(limit=min(limit, 500))
        return {
            "unacknowledged": len(services.alert_service.unacknowledged(limit=1000)),
            "alerts": [_alert_payload(alert) for alert in recent],
        }

    @app.post("/api/alerts/{alert_id}/ack", tags=["alerts"])
    def acknowledge_alert(alert_id: int, payload: AckRequest) -> dict[str, Any]:
        if not payload.confirm:
            raise HTTPException(status_code=400, detail='{"confirm": true} is required')
        services = _services()
        assert services.alert_service is not None
        if not services.alert_service.acknowledge(alert_id):
            raise HTTPException(status_code=404, detail="alert not found or already acknowledged")
        return {"acknowledged": alert_id}

    # ---------------------------------------------------------------- reports
    @app.get("/api/reports", tags=["reports"])
    def list_reports() -> list[dict[str, Any]]:
        services = _services()
        settings = services.settings_service.get()
        directory = Path(settings.default_export_dir or services.paths.default_export_dir)
        files = []
        if directory.exists():
            for path in sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[
                :50
            ]:
                if path.suffix in {".csv", ".json", ".txt"}:
                    files.append(
                        {"name": path.name, "size_bytes": path.stat().st_size, "path": str(path)}
                    )
        return files

    @app.post("/api/reports", tags=["reports"], status_code=201)
    def generate_report(request: ReportRequest) -> dict[str, Any]:
        services = _services()
        assert services.report_service is not None
        path = services.report_service.generate(
            request.report_key,
            request.format,
            device_id=request.device_id,
            hours=request.hours,
        )
        return {"path": str(path), "name": Path(path).name}

    # ---------------------------------------------------------------- activity
    @app.get("/api/activity", tags=["activity"])
    def activity(limit: int = 50) -> list[dict[str, Any]]:
        services = _services()
        assert services.activity_service is not None
        return [
            {
                "timestamp": entry.timestamp.isoformat(),
                "module": entry.module,
                "action": entry.action,
                "status": entry.status.value,
                "message": entry.message,
            }
            for entry in services.activity_service.recent(limit=min(limit, 500))
        ]

    return app


# -------------------------------------------------------------------- payloads
def _scan_payload(result) -> dict[str, Any]:
    return {
        "network": result.network,
        "total": result.total,
        "checked": len(result.results),
        "reachable": result.reachable_count,
        "cancelled": result.cancelled,
        "duration_seconds": round(result.duration_seconds, 3),
        "results": [
            {
                "ip": host.ip,
                "reachable": host.reachable,
                "response_time_ms": host.response_time_ms,
                "hostname": host.hostname,
                "mac": host.mac,
                "checked_at": host.timestamp.isoformat(),
            }
            for host in result.results
        ],
    }


def _device_payload(row) -> dict[str, Any]:
    return {
        "id": row.device.id,
        "name": row.device.name,
        "host": row.device.host,
        "enabled": row.device.enabled,
        "interval_seconds": row.device.interval_seconds,
        "status": row.last_result.status.value if row.last_result else "unknown",
        "response_time_ms": row.last_result.response_time_ms if row.last_result else None,
        "last_seen": row.last_result.timestamp.isoformat() if row.last_result else None,
        "consecutive_failures": row.consecutive_failures,
    }


def _result_payload(result) -> dict[str, Any]:
    return {
        "device_id": result.device_id,
        "timestamp": result.timestamp.isoformat(),
        "status": result.status.value,
        "response_time_ms": result.response_time_ms,
        "error": result.error_message,
    }


def _backup_payload(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "source": job.source,
        "destination": job.destination,
        "status": job.status.value,
        "started_at": job.started_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "files_copied": job.files_copied,
        "size_bytes": job.size_bytes,
        "verified": job.checksum_verified,
        "error": job.error_message,
    }


def _alert_payload(alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "type": alert.type,
        "severity": alert.severity.value,
        "source": alert.source,
        "message": alert.message,
        "created_at": alert.created_at.isoformat(),
        "acknowledged": alert.acknowledged,
    }
