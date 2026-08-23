"""Report service — builds tabular datasets from live data and exports them.

Every report is (metadata, headers, rows); writing is delegated to the
shared ExportService so CSV/JSON/TXT behavior stays identical everywhere.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.formatters import human_bytes
from app.services.activity_service import ActivityLogService
from app.services.alert_service import AlertService
from app.services.disk_service import DiskService
from app.services.export_service import ExportFormat, ExportService
from app.services.monitor_service import MonitorService
from app.services.snapshot_service import SnapshotService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportDefinition:
    key: str
    title: str
    needs_device: bool
    needs_range: bool


_Dataset = tuple[dict[str, Any], Sequence[str], list[dict[str, Any]], str]

REPORTS: tuple[ReportDefinition, ...] = (
    ReportDefinition("monitoring_history", "Monitoring history (all devices)", False, True),
    ReportDefinition("device_latency", "Device latency (single device)", True, True),
    ReportDefinition("alerts", "Alerts log", False, True),
    ReportDefinition("activity", "Activity / audit log", False, True),
    ReportDefinition("disk_usage", "Disk usage snapshot", False, False),
    ReportDefinition("system_snapshots", "System snapshots (CPU/RAM/disk)", False, True),
)

_RANGES: tuple[tuple[str, float], ...] = (
    ("Last hour", 1.0),
    ("Last 24 hours", 24.0),
    ("Last 7 days", 168.0),
)


class ReportService:
    def __init__(
        self,
        exports: ExportService,
        monitor: MonitorService,
        alerts: AlertService,
        activity: ActivityLogService,
        disks: DiskService,
        snapshots: SnapshotService,
    ) -> None:
        self._exports = exports
        self._monitor = monitor
        self._alerts = alerts
        self._activity = activity
        self._disks = disks
        self._snapshots = snapshots

    @staticmethod
    def definitions() -> tuple[ReportDefinition, ...]:
        return REPORTS

    @staticmethod
    def ranges() -> tuple[tuple[str, float], ...]:
        return _RANGES

    def generate(
        self,
        report_key: str,
        fmt: ExportFormat,
        *,
        device_id: int | None = None,
        hours: float = 24.0,
    ) -> Any:
        """Build the named dataset and export it; returns the created Path."""
        metadata, headers, rows, stem = self._build(report_key, device_id, hours)
        return self._exports.export_table(stem, fmt, metadata, headers, rows)

    def _build(
        self, report_key: str, device_id: int | None, hours: float
    ) -> tuple[dict[str, Any], Sequence[str], Sequence[dict[str, Any]], str]:
        if report_key == "monitoring_history":
            return self._monitoring_history(hours, None)
        if report_key == "device_latency":
            if device_id is None:
                raise ValueError("Select a device for the latency report")
            return self._monitoring_history(hours, device_id)
        if report_key == "alerts":
            return self._alerts_log(hours)
        if report_key == "activity":
            return self._activity_log(hours)
        if report_key == "disk_usage":
            return self._disk_usage()
        if report_key == "system_snapshots":
            return self._snapshots_report(hours)
        raise ValueError(f"Unknown report: {report_key}")

    # ------------------------------------------------------------ builders
    def _monitoring_history(self, hours: float, device_id: int | None) -> _Dataset:
        devices = {d.id: d for d in self._monitor.list_devices()}
        rows: list[dict[str, Any]] = []
        if device_id is not None:
            history = self._monitor.history(device_id, hours=hours)
        else:
            history = []
            for target in (i for i in devices if i is not None):
                history.extend(self._monitor.history(target, hours=hours))
            history.sort(key=lambda r: r.timestamp)
        for result in history:
            device = devices.get(result.device_id)
            rows.append(
                {
                    "timestamp": result.timestamp.isoformat(),
                    "device": device.name if device else str(result.device_id),
                    "host": device.host if device else "",
                    "status": result.status.value,
                    "response_time_ms": (
                        f"{result.response_time_ms:.1f}"
                        if result.response_time_ms is not None
                        else ""
                    ),
                    "error": result.error_message or "",
                }
            )
        metadata = {
            "report": "monitoring-history",
            "window_hours": hours,
            "device": (
                None
                if device_id is None
                else (devices[device_id].name if device_id in devices else str(device_id))
            ),
            "checks": len(rows),
        }
        headers: Sequence[str] = (
            tuple(rows[0].keys())
            if rows
            else ("timestamp", "device", "host", "status", "response_time_ms", "error")
        )
        return metadata, headers, rows, "monitoring-history"

    def _alerts_log(self, hours: float) -> _Dataset:
        alerts = self._alerts.recent(limit=5000)
        rows: list[dict[str, Any]] = [
            {
                "created_at": alert.created_at.isoformat(),
                "severity": alert.severity.value,
                "type": alert.type,
                "source": alert.source,
                "message": alert.message,
                "acknowledged": "yes" if alert.acknowledged else "no",
            }
            for alert in alerts
        ]
        metadata = {"report": "alerts", "window_hint_hours": hours, "alerts": len(rows)}
        return (
            metadata,
            ("created_at", "severity", "type", "source", "message", "acknowledged"),
            rows,
            "alerts",
        )

    def _activity_log(self, hours: float) -> _Dataset:
        entries = self._activity.recent(limit=5000)
        rows: list[dict[str, Any]] = [
            {
                "timestamp": entry.timestamp.isoformat(),
                "module": entry.module,
                "action": entry.action,
                "status": entry.status.value,
                "message": entry.message or "",
            }
            for entry in entries
        ]
        metadata = {"report": "activity", "window_hint_hours": hours, "entries": len(rows)}
        return metadata, ("timestamp", "module", "action", "status", "message"), rows, "activity"

    def _disk_usage(self) -> _Dataset:
        status = self._disks.evaluate(raise_alerts=False)
        rows: list[dict[str, Any]] = [
            {
                "volume": drive.mountpoint,
                "filesystem": drive.fs_type,
                "total_bytes": drive.total_bytes,
                "total": human_bytes(drive.total_bytes),
                "used": human_bytes(drive.used_bytes),
                "free": human_bytes(drive.free_bytes),
                "usage_percent": f"{drive.percent:.1f}",
                "level": level.value,
            }
            for drive, level in zip(status.drives, status.levels, strict=True)
        ]
        metadata = {
            "report": "disk-usage",
            "volumes": len(rows),
            "overall_level": status.overall_level.value,
        }
        return (
            metadata,
            ("volume", "filesystem", "total", "used", "free", "usage_percent", "level"),
            rows,
            "disk-usage",
        )

    def _snapshots_report(self, hours: float) -> _Dataset:
        snapshots = self._snapshots.history(hours=hours)
        rows: list[dict[str, Any]] = [
            {
                "timestamp": snapshot.timestamp.isoformat(),
                "cpu_percent": snapshot.cpu_percent if snapshot.cpu_percent is not None else "",
                "memory_percent": snapshot.memory_percent
                if snapshot.memory_percent is not None
                else "",
                "disk_percent": snapshot.disk_percent if snapshot.disk_percent is not None else "",
            }
            for snapshot in snapshots
        ]
        metadata = {"report": "system-snapshots", "window_hours": hours, "snapshots": len(rows)}
        return (
            metadata,
            ("timestamp", "cpu_percent", "memory_percent", "disk_percent"),
            rows,
            "system-snapshots",
        )
