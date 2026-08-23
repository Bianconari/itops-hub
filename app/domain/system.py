"""System domain model: metric snapshots, static system facts, status levels.

Pure data + pure functions — no I/O. The infrastructure layer fills these in
via the ``SystemMetricsSource`` Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Level(StrEnum):
    """Usage severity level (presentational; alert persistence lands in v0.6)."""

    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


def evaluate_usage_level(percent: float, warning: float, critical: float) -> Level:
    """Classify a usage percentage against warning/critical thresholds."""
    if percent >= critical:
        return Level.CRITICAL
    if percent >= warning:
        return Level.WARNING
    return Level.OK


@dataclass(frozen=True)
class DriveUsage:
    """Capacity facts for one mounted volume."""

    device: str
    mountpoint: str
    fs_type: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float


@dataclass(frozen=True)
class NetworkAdapter:
    """One local network interface."""

    name: str
    is_up: bool
    speed_mbps: int | None
    ipv4: tuple[str, ...]
    ipv6: tuple[str, ...]


@dataclass(frozen=True)
class SystemInfo:
    """Static (slow-changing) system facts."""

    hostname: str
    os_name: str
    os_version: str
    os_architecture: str
    cpu_model: str
    cpu_cores_physical: int | None
    cpu_cores_logical: int | None
    cpu_freq_mhz_current: float | None
    cpu_freq_mhz_max: float | None
    memory_total_bytes: int
    boot_time: datetime  # naive UTC
    adapters: tuple[NetworkAdapter, ...]
    python_version: str


@dataclass(frozen=True)
class LiveMetrics:
    """One point-in-time measurement of local system load."""

    timestamp: datetime  # naive UTC
    cpu_percent: float
    memory_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    disk_percent_max: float | None  # highest usage across mounted volumes


@dataclass(frozen=True)
class SystemStatus:
    """Live metrics classified against thresholds, plus the overall level."""

    metrics: LiveMetrics
    cpu_level: Level
    memory_level: Level
    disk_level: Level | None
    overall_level: Level


@dataclass(frozen=True)
class SystemSnapshotEntity:
    """A persisted point of the ``system_snapshots`` table."""

    timestamp: datetime
    cpu_percent: float | None
    memory_percent: float | None
    disk_percent: float | None
    id: int | None = None
