"""System information service.

Wraps the ``SystemMetricsSource`` Protocol (psutil in production, fakes in
tests) and classifies live metrics against thresholds. CPU/RAM thresholds are
presentational constants for now; disk thresholds come from settings.
Persisted alerts for all three land with the alerts module in v0.6.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.config.settings import AppSettings
from app.domain.interfaces import SystemMetricsSource
from app.domain.system import (
    DriveUsage,
    Level,
    LiveMetrics,
    SystemInfo,
    SystemStatus,
    evaluate_usage_level,
)
from app.domain.time_utils import utc_now

logger = logging.getLogger(__name__)

#: Presentational thresholds for CPU/RAM on the dashboard (v0.6 makes these
#: configurable alongside disk thresholds when alerting is introduced).
CPU_WARNING_PERCENT = 80.0
CPU_CRITICAL_PERCENT = 90.0
MEMORY_WARNING_PERCENT = 80.0
MEMORY_CRITICAL_PERCENT = 90.0


class SystemInfoService:
    """Reads system facts and live load, classified against thresholds."""

    def __init__(
        self, source: SystemMetricsSource, settings_getter: Callable[[], AppSettings]
    ) -> None:
        self._source = source
        self._settings_getter = settings_getter

    def get_info(self) -> SystemInfo:
        """Collect static system information (may take a moment on slow disks)."""
        return self._source.static_info()

    def get_drives(self) -> list[DriveUsage]:
        """Current capacity facts for all accessible volumes."""
        return self._source.drive_usages()

    def get_live(self) -> LiveMetrics:
        """One point-in-time load measurement (non-blocking with psutil)."""
        return self._source.live_metrics()

    def get_status(self) -> SystemStatus:
        """Live metrics + threshold classification + overall level."""
        metrics = self.get_live()
        settings: AppSettings = self._settings_getter()
        disk_level = (
            evaluate_usage_level(
                metrics.disk_percent_max,
                settings.disk.warning_percent,
                settings.disk.critical_percent,
            )
            if metrics.disk_percent_max is not None
            else None
        )
        cpu_level = evaluate_usage_level(
            metrics.cpu_percent, CPU_WARNING_PERCENT, CPU_CRITICAL_PERCENT
        )
        memory_level = evaluate_usage_level(
            metrics.memory_percent, MEMORY_WARNING_PERCENT, MEMORY_CRITICAL_PERCENT
        )
        levels = [cpu_level, memory_level] + ([disk_level] if disk_level else [])
        overall = max(levels, key=lambda level: list(Level).index(level))
        return SystemStatus(
            metrics=metrics,
            cpu_level=cpu_level,
            memory_level=memory_level,
            disk_level=disk_level,
            overall_level=overall,
        )

    def uptime_seconds(self, info: SystemInfo) -> float:
        """Seconds since boot, computed from static info."""
        return max(0.0, (utc_now() - info.boot_time).total_seconds())

    @staticmethod
    def primary_ipv4(info: SystemInfo) -> str:
        """Best-effort primary IPv4 of an up, non-loopback interface."""
        for adapter in info.adapters:
            if not adapter.is_up:
                continue
            for address in adapter.ipv4:
                if not address.startswith("127."):
                    return address
        return "No IPv4 address"

    @staticmethod
    def up_interface_count(info: SystemInfo) -> int:
        return sum(1 for adapter in info.adapters if adapter.is_up)
