"""Network scan service.

Runs authorized CIDR scans concurrently with cooperative cancellation and
progress reporting. Safety rules (Spec §1.3-C, §15, AD-002/AD-009):

- Input is validated with ``validate_cidr``; private-range guard requires an
  explicit override for public networks.
- Reachability uses the OS ``ping`` binary via the ``Pinger`` Protocol —
  never raw sockets, never admin rights, no Npcap.
- Host counts are capped (``scan_max_hosts``) to keep scans bounded.
- Progress/history/logging flow through injected collaborators, so the
  service is fully unit-testable with fakes.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from app.config.settings import AppSettings
from app.domain.cancellation import CancelToken, OperationCancelled
from app.domain.events import EventBus, Topics
from app.domain.network import (
    ArpSource,
    HostnameResolver,
    HostResult,
    Pinger,
    ProgressCallback,
    ScanResult,
)
from app.domain.time_utils import utc_now
from app.domain.validation import is_private_network, validate_cidr
from app.services.activity_service import ActivityLogService

logger = logging.getLogger(__name__)


class NetworkScanService:
    """Concurrent reachability scan of a CIDR network the user administers."""

    def __init__(
        self,
        pinger: Pinger,
        resolver: HostnameResolver,
        arp: ArpSource,
        settings_getter: Callable[[], AppSettings],
        activity: ActivityLogService | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._pinger = pinger
        self._resolver = resolver
        self._arp = arp
        self._settings_getter = settings_getter
        self._activity = activity
        self._bus = bus

    def scan(
        self,
        cidr: str,
        *,
        token: CancelToken | None = None,
        authorized_override: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> ScanResult:
        """Scan ``cidr`` and return structured results.

        Raises:
            ValueError: invalid CIDR, unauthorized public range, or host
                count above the configured cap.
            OperationCancelled: if the token fires before the scan starts.
        """
        network = validate_cidr(cidr)
        settings = self._settings_getter()
        self._enforce_authorization(network, settings, authorized_override)

        hosts = self._enumerate_hosts(network, settings)

        token = token or CancelToken()
        token.raise_if_cancelled()
        self._record("scan.started", f"network={network} hosts={len(hosts)}")

        started = utc_now()
        started_monotonic = time.monotonic()
        results, cancelled = self._run_checks(hosts, settings, token, on_progress)
        self._enrich(results)

        completed = utc_now()
        results.sort(key=lambda host: ipaddress.ip_address(host.ip))
        scan_result = ScanResult(
            network=str(network),
            started_at=started,
            completed_at=completed,
            duration_seconds=time.monotonic() - started_monotonic,
            total=len(hosts),
            results=tuple(results),
            cancelled=cancelled,
        )
        self._finish_activity(scan_result)
        if self._bus is not None:
            self._bus.publish(Topics.SCAN_COMPLETED, scan_result)
        return scan_result

    # ------------------------------------------------------------------
    def _enforce_authorization(
        self,
        network: ipaddress.IPv4Network | ipaddress.IPv6Network,
        settings: AppSettings,
        authorized_override: bool,
    ) -> None:
        if (
            settings.scan_private_only
            and not is_private_network(network)
            and not authorized_override
        ):
            raise ValueError(
                f"{network} is not a private range. Scanning non-private "
                "networks requires confirming you are authorized to "
                "administer them (enable the authorization checkbox)."
            )

    @staticmethod
    def _enumerate_hosts(
        network: ipaddress.IPv4Network | ipaddress.IPv6Network,
        settings: AppSettings,
    ) -> list[str]:
        hosts = [str(ip) for ip in network.hosts()] or [str(network.network_address)]
        if len(hosts) > settings.scan_max_hosts:
            raise ValueError(
                f"{network} contains {len(hosts)} addresses, above the scan "
                f"limit of {settings.scan_max_hosts} (adjustable in Settings)."
            )
        return hosts

    def _run_checks(
        self,
        hosts: list[str],
        settings: AppSettings,
        token: CancelToken,
        on_progress: ProgressCallback | None,
    ) -> tuple[list[HostResult], bool]:
        results: list[HostResult] = []
        cancelled = False
        pool = ThreadPoolExecutor(max_workers=min(settings.scan_max_workers, len(hosts)))
        try:
            futures: dict[Future[HostResult], str] = {
                pool.submit(self._check_host, ip, settings.monitoring.timeout_ms): ip
                for ip in hosts
            }
            for done, future in enumerate(as_completed(futures), start=1):
                if token.cancelled:
                    cancelled = True
                    break
                results.append(future.result())
                if on_progress is not None:
                    on_progress(done, len(hosts))
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        if token.cancelled and not cancelled:
            cancelled = True
        if cancelled and not token.cancelled:
            raise OperationCancelled("scan cancelled")
        return results, cancelled

    def _check_host(self, ip: str, timeout_ms: int) -> HostResult:
        ping = self._pinger.ping(ip, timeout_ms)
        hostname = self._resolver.resolve(ip) if ping.reachable else None
        return HostResult(
            ip=ip,
            reachable=ping.reachable,
            response_time_ms=ping.response_time_ms,
            hostname=hostname,
            timestamp=utc_now(),
        )

    def _enrich(self, results: list[HostResult]) -> None:
        try:
            macs = self._arp.mac_map()
        except Exception as exc:
            logger.warning("ARP cache unavailable: %s", exc)
            return
        for host in results:
            host.mac = macs.get(host.ip.lower())

    # ------------------------------------------------------------------
    def _record(self, action: str, message: str) -> None:
        if self._activity is not None:
            self._activity.record(action, module="network", message=message)

    def _finish_activity(self, result: ScanResult) -> None:
        summary = (
            f"network={result.network} checked={len(result.results)}/{result.total} "
            f"reachable={result.reachable_count} duration={result.duration_seconds:.1f}s"
        )
        if result.cancelled:
            self._record("scan.cancelled", summary)
        else:
            self._record("scan.completed", summary)
