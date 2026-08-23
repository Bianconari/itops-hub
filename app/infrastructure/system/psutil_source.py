"""psutil-backed implementation of ``SystemMetricsSource``.

Notes on honesty and portability:
- ``cpu_percent(interval=None)`` is non-blocking (CPU since the previous call);
  it is primed once at construction so the first reading is meaningful.
- The CPU model string comes from ``PROCESSOR_IDENTIFIER`` on Windows and
  ``/proc/cpuinfo`` on Linux; other platforms fall back to a generic label
  (documented limitation — the target OS is Windows).
- Addresses are read from ``psutil.net_if_addrs``/``net_if_stats``; IPv6
  scope suffixes (``fe80::1%eth0``) are stripped for display cleanliness.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
from datetime import UTC, datetime
from pathlib import Path

import psutil

from app.domain.system import DriveUsage, LiveMetrics, NetworkAdapter, SystemInfo
from app.domain.time_utils import utc_now

logger = logging.getLogger(__name__)


def _cpu_model() -> str:
    if os.name == "nt":
        return os.environ.get("PROCESSOR_IDENTIFIER", "Unknown CPU")
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        try:
            for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    processor = platform.processor()
    return processor if processor else "Unknown CPU"


class PsutilSystemSource:
    """Production system metrics source (no admin rights required)."""

    def __init__(self) -> None:
        psutil.cpu_percent(interval=None)  # prime the non-blocking sampler

    def static_info(self) -> SystemInfo:
        hostname = socket.gethostname()
        freq = None
        try:
            freq = psutil.cpu_freq()
        except (NotImplementedError, OSError):
            freq = None

        adapters = self._adapters()
        return SystemInfo(
            hostname=hostname,
            os_name=platform.system(),
            os_version=f"{platform.release()} (build {platform.version()})",
            os_architecture=platform.machine(),
            cpu_model=_cpu_model(),
            cpu_cores_physical=psutil.cpu_count(logical=False),
            cpu_cores_logical=psutil.cpu_count(logical=True),
            cpu_freq_mhz_current=freq.current if freq else None,
            cpu_freq_mhz_max=freq.max if freq else None,
            memory_total_bytes=psutil.virtual_memory().total,
            boot_time=datetime.fromtimestamp(psutil.boot_time(), tz=UTC).replace(tzinfo=None),
            adapters=tuple(adapters),
            python_version=platform.python_version(),
        )

    def live_metrics(self) -> LiveMetrics:
        cpu = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk_percent = max((drive.percent for drive in self.drive_usages()), default=None)
        return LiveMetrics(
            timestamp=utc_now(),
            cpu_percent=cpu,
            memory_percent=memory.percent,
            memory_used_bytes=memory.used,
            memory_total_bytes=memory.total,
            disk_percent_max=disk_percent,
        )

    def drive_usages(self) -> list[DriveUsage]:
        usages: list[DriveUsage] = []
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (PermissionError, OSError) as exc:
                logger.debug("skipping inaccessible volume %s: %s", partition.mountpoint, exc)
                continue
            usages.append(
                DriveUsage(
                    device=partition.device,
                    mountpoint=partition.mountpoint,
                    fs_type=partition.fstype,
                    total_bytes=usage.total,
                    used_bytes=usage.used,
                    free_bytes=usage.free,
                    percent=usage.percent,
                )
            )
        return usages

    def _adapters(self) -> list[NetworkAdapter]:
        addresses = psutil.net_if_addrs()
        try:
            stats = psutil.net_if_stats()
        except OSError:  # pragma: no cover - platform specific
            stats = {}
        adapters: list[NetworkAdapter] = []
        for name, addr_list in addresses.items():
            ipv4: list[str] = []
            ipv6: list[str] = []
            for addr in addr_list:
                value = addr.address.split("%", 1)[0]
                if addr.family == socket.AF_INET:
                    ipv4.append(value)
                elif addr.family == socket.AF_INET6:
                    ipv6.append(value)
            stat = stats.get(name)
            adapters.append(
                NetworkAdapter(
                    name=name,
                    is_up=bool(stat.isup) if stat else bool(ipv4 or ipv6),
                    speed_mbps=stat.speed if stat else None,
                    ipv4=tuple(ipv4),
                    ipv6=tuple(ipv6),
                )
            )
        return adapters
