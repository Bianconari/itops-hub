"""Network domain model: ping results, scan results, and Protocols.

Pure data + interfaces; the infrastructure layer provides the OS-backed
implementations (system ping subprocess, socket resolver, ARP cache).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.domain.time_utils import utc_now


@dataclass(frozen=True)
class PingResult:
    """Outcome of a single reachability probe."""

    host: str
    reachable: bool
    response_time_ms: float | None = None
    error: str | None = None


@dataclass
class HostResult:
    """One scanned address.

    Mutable (not frozen): hostname/MAC are enriched after the ping sweep —
    deliberately simple for v0.5; a future release may freeze this.
    """

    ip: str
    reachable: bool
    response_time_ms: float | None
    hostname: str | None = None
    mac: str | None = None
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ScanResult:
    """Complete outcome of one network scan."""

    network: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    total: int
    results: tuple[HostResult, ...]
    cancelled: bool = False

    @property
    def reachable_count(self) -> int:
        return sum(1 for host in self.results if host.reachable)


class Pinger(Protocol):
    """Reachability prober (system ping subprocess in production)."""

    def ping(self, host: str, timeout_ms: int) -> PingResult: ...


class HostnameResolver(Protocol):
    """Reverse-DNS resolver; returns None when no name is found."""

    def resolve(self, ip: str) -> str | None: ...


class ArpSource(Protocol):
    """ARP cache reader; maps IP -> normalized MAC (aa:bb:cc:dd:ee:ff)."""

    def mac_map(self) -> dict[str, str]: ...


#: Called with (completed, total) as scan checks finish.
ProgressCallback = Callable[[int, int], None]
