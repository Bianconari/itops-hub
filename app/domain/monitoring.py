"""Monitoring domain model: devices, check results, and store Protocols."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class MonitorState(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    WARNING = "warning"  # reachable but slow (latency above threshold)


@dataclass(frozen=True)
class Device:
    """A monitored endpoint (ping monitor)."""

    name: str
    host: str
    enabled: bool = True
    interval_seconds: int = 30
    timeout_ms: int = 1500
    type: str = "ping"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: int | None = None


@dataclass(frozen=True)
class MonitorResult:
    """One connectivity check of one device."""

    device_id: int
    timestamp: datetime
    status: MonitorState
    response_time_ms: float | None = None
    error_message: str | None = None
    id: int | None = None


@dataclass(frozen=True)
class DeviceStatusRow:
    """UI-facing summary: device + latest check + consecutive failures."""

    device: Device
    last_result: MonitorResult | None
    consecutive_failures: int


class DeviceStore(Protocol):
    def list_all(self) -> list[Device]: ...

    def get(self, device_id: int) -> Device | None: ...

    def get_by_name(self, name: str) -> Device | None: ...

    def add(self, device: Device) -> Device: ...

    def update(self, device: Device) -> Device: ...

    def delete(self, device_id: int) -> bool: ...


class MonitorResultStore(Protocol):
    def add(self, result: MonitorResult) -> MonitorResult: ...

    def latest_for_devices(self, device_ids: list[int]) -> dict[int, MonitorResult]: ...

    def history(
        self, device_id: int, start: datetime, end: datetime, limit: int = 5000
    ) -> list[MonitorResult]: ...

    def consecutive_failures(self, device_id: int) -> int: ...

    def prune_older_than(self, cutoff: datetime) -> int: ...
