"""Shared test fakes implementing domain Protocols."""

from __future__ import annotations

import dataclasses
from datetime import datetime

from app.domain.system import DriveUsage, LiveMetrics, SystemInfo, SystemSnapshotEntity
from app.domain.time_utils import utc_now


def make_metrics(
    cpu: float = 10.0,
    memory: float = 20.0,
    disk: float | None = 30.0,
    timestamp: datetime | None = None,
) -> LiveMetrics:
    return LiveMetrics(
        timestamp=timestamp or utc_now(),
        cpu_percent=cpu,
        memory_percent=memory,
        memory_used_bytes=int(memory * 1024**3 // 100),
        memory_total_bytes=100 * 1024**3,
        disk_percent_max=disk,
    )


def make_drives(percents: list[float]) -> list[DriveUsage]:
    return [
        DriveUsage(
            device=f"dev{i}",
            mountpoint=f"/vol{i}" if i else "/",
            fs_type="ext4",
            total_bytes=100 * 1024**3,
            used_bytes=int(percent * 1024**3 // 100),
            free_bytes=int((100 - percent) * 1024**3 // 100),
            percent=percent,
        )
        for i, percent in enumerate(percents)
    ]


def make_info() -> SystemInfo:
    from app.domain.system import NetworkAdapter

    return SystemInfo(
        hostname="test-host",
        os_name="TestOS",
        os_version="1.0 (build 1)",
        os_architecture="x86_64",
        cpu_model="Test CPU 4.0 GHz",
        cpu_cores_physical=4,
        cpu_cores_logical=8,
        cpu_freq_mhz_current=4000.0,
        cpu_freq_mhz_max=4400.0,
        memory_total_bytes=16 * 1024**3,
        boot_time=utc_now(),
        adapters=(
            NetworkAdapter(name="eth0", is_up=True, speed_mbps=1000, ipv4=("10.0.0.5",), ipv6=()),
            NetworkAdapter(name="lo", is_up=True, speed_mbps=0, ipv4=("127.0.0.1",), ipv6=("::1",)),
        ),
        python_version="3.13.0",
    )


class FakeSystemSource:
    """Configurable SystemMetricsSource double."""

    def __init__(
        self,
        info: SystemInfo | None = None,
        metrics: LiveMetrics | None = None,
        drives: list[DriveUsage] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._info = info or make_info()
        self._metrics = metrics or make_metrics()
        self._drives = drives if drives is not None else make_drives([30.0, 60.0])
        self._error = error

    def static_info(self) -> SystemInfo:
        if self._error:
            raise self._error
        return self._info

    def live_metrics(self) -> LiveMetrics:
        if self._error:
            raise self._error
        return self._metrics

    def drive_usages(self) -> list[DriveUsage]:
        if self._error:
            raise self._error
        return self._drives


class FakeSnapshotStore:
    """In-memory SystemSnapshotStore double."""

    def __init__(self) -> None:
        self.rows: list[SystemSnapshotEntity] = []

    def add(self, snapshot: SystemSnapshotEntity) -> SystemSnapshotEntity:
        stored = SystemSnapshotEntity(
            id=len(self.rows) + 1,
            timestamp=snapshot.timestamp,
            cpu_percent=snapshot.cpu_percent,
            memory_percent=snapshot.memory_percent,
            disk_percent=snapshot.disk_percent,
        )
        self.rows.append(stored)
        return stored

    def query_range(
        self, start: datetime, end: datetime, limit: int = 5000
    ) -> list[SystemSnapshotEntity]:
        selected = [row for row in self.rows if start <= row.timestamp <= end]
        return sorted(selected[:limit], key=lambda row: row.timestamp)

    def prune_older_than(self, cutoff: datetime) -> int:
        kept = [row for row in self.rows if row.timestamp >= cutoff]
        removed = len(self.rows) - len(kept)
        self.rows = kept
        return removed


class FakeActivityStore:
    """In-memory ActivityStore double."""

    def __init__(self) -> None:
        self.entries: list = []

    def append(self, entry):
        stored = dataclasses.replace(entry, id=len(self.entries) + 1)
        self.entries.append(stored)
        return stored

    def recent(self, limit: int = 100):
        return list(reversed(self.entries))[:limit]


class FakePinger:
    """Configurable Pinger double: explicit reachable map + call counting."""

    def __init__(
        self,
        reachable: set[str] | None = None,
        latency: float = 5.0,
        delay: float = 0.0,
        error: str = "no reply",
    ) -> None:
        self._reachable = reachable or set()
        self._latency = latency
        self._delay = delay
        self._error = error
        self.calls: list[str] = []

    def ping(self, host: str, timeout_ms: int):
        import time as _time

        from app.domain.network import PingResult

        self.calls.append(host)
        if self._delay:
            _time.sleep(self._delay)
        if host in self._reachable:
            return PingResult(host=host, reachable=True, response_time_ms=self._latency)
        return PingResult(host=host, reachable=False, error=self._error)


class FakeResolver:
    def __init__(self, names: dict[str, str] | None = None) -> None:
        self._names = names or {}

    def resolve(self, ip: str):
        return self._names.get(ip)


class FakeArp:
    def __init__(self, table: dict[str, str] | None = None) -> None:
        self._table = table or {}

    def mac_map(self) -> dict[str, str]:
        return dict(self._table)
