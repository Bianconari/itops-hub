"""Disk monitoring service — threshold evaluation with deduplicated alerts.

Warning/critical thresholds come from settings (80/90 by default). When a
volume crosses a threshold a ``disk.threshold`` alert is raised (deduped);
when usage returns below warning, the open alert is auto-acknowledged.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.config.settings import AppSettings
from app.domain.entities import Severity
from app.domain.system import DriveUsage, Level, evaluate_usage_level
from app.services.alert_service import AlertService

logger = logging.getLogger(__name__)

_ALERT_TYPE = "disk.threshold"


@dataclass(frozen=True)
class DiskStatus:
    """Evaluated state of all volumes plus the overall level."""

    drives: tuple[DriveUsage, ...]
    levels: tuple[Level, ...]
    overall_level: Level


class DiskService:
    def __init__(
        self,
        drives_getter: Callable[[], list[DriveUsage]],
        settings_getter: Callable[[], AppSettings],
        alerts: AlertService,
    ) -> None:
        self._drives_getter = drives_getter
        self._settings_getter = settings_getter
        self._alerts = alerts

    def evaluate(self, *, raise_alerts: bool = True) -> DiskStatus:
        """Read volumes, classify each against thresholds, maintain alerts."""
        drives = tuple(self._drives_getter())
        settings = self._settings_getter()
        levels = tuple(
            evaluate_usage_level(
                drive.percent, settings.disk.warning_percent, settings.disk.critical_percent
            )
            for drive in drives
        )
        if raise_alerts:
            for drive, level in zip(drives, levels, strict=True):
                self._maintain_alert(drive, level, settings)
        overall = max(levels, key=lambda level: list(Level).index(level), default=Level.OK)
        return DiskStatus(drives=drives, levels=levels, overall_level=overall)

    def _maintain_alert(self, drive: DriveUsage, level: Level, settings: AppSettings) -> None:
        source = drive.mountpoint
        if level is Level.CRITICAL:
            self._alerts.raise_alert(
                _ALERT_TYPE,
                Severity.CRITICAL,
                source,
                f"{drive.mountpoint} usage {drive.percent:.1f}% "
                f"(critical threshold {settings.disk.critical_percent:.0f}%)",
            )
        elif level is Level.WARNING:
            self._alerts.raise_alert(
                _ALERT_TYPE,
                Severity.WARNING,
                source,
                f"{drive.mountpoint} usage {drive.percent:.1f}% "
                f"(warning threshold {settings.disk.warning_percent:.0f}%)",
            )
        elif self._alerts.resolve_alerts(_ALERT_TYPE, source):
            logger.info("disk condition cleared for %s", source)
