"""Application settings model (Pydantic v2).

The model is the single source of truth for user-configurable behavior.
Persistence is a JSON document stored in the local SQLite ``settings`` table
(see ``SettingsService``); the model itself stays free of storage concerns.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Theme(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DiskThresholdSettings(BaseModel):
    """Disk usage alert thresholds, in percent."""

    warning_percent: float = Field(default=80.0, ge=1.0, le=100.0)
    critical_percent: float = Field(default=90.0, ge=1.0, le=100.0)

    @model_validator(mode="after")
    def _warning_not_above_critical(self) -> DiskThresholdSettings:
        if self.warning_percent > self.critical_percent:
            raise ValueError("warning_percent must be less than or equal to critical_percent")
        return self


class MonitoringSettings(BaseModel):
    """Defaults for newly added monitored devices."""

    interval_seconds: int = Field(default=30, ge=5, le=3600)
    timeout_ms: int = Field(default=1500, ge=100, le=10000)


class SnapshotSettings(BaseModel):
    """System snapshot recording cadence (dashboard history + trends)."""

    interval_seconds: int = Field(default=60, ge=5, le=3600)


class NotificationSettings(BaseModel):
    in_app: bool = True
    desktop: bool = True


class ApiSettings(BaseModel):
    """Local FastAPI service settings (API ships in v1.5).

    ``host`` defaults to loopback only; binding to a non-local address is a
    documented security decision and is never done implicitly.
    """

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8756, ge=1024, le=65535)


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1
    theme: Theme = Theme.SYSTEM
    language: str = "en"
    log_level: LogLevel = LogLevel.INFO

    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    snapshots: SnapshotSettings = Field(default_factory=SnapshotSettings)
    disk: DiskThresholdSettings = Field(default_factory=DiskThresholdSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)

    #: None means "use the OS default export directory" (see AppPaths).
    default_export_dir: Path | None = None

    #: History retention (monitoring results / system snapshots), in days.
    retention_days: int = Field(default=30, ge=1, le=3650)

    #: Network scanner behavior.
    scan_max_workers: int = Field(default=64, ge=1, le=512)
    #: When True, scanning public IP ranges requires an explicit override in
    #: the UI (authorization guard; scanning is for networks you administer).
    scan_private_only: bool = True
