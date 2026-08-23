"""Monitor service — device CRUD, connectivity checks, history, alerts.

Checks run through the injected ``Pinger`` Protocol (system ping in
production, fakes in tests). States: online / offline / warning (reachable
but slower than ``latency_warning_ms``). Device-offline and recovery alerts
are deduplicated by the AlertService.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from app.config.settings import AppSettings
from app.domain.cancellation import CancelToken
from app.domain.entities import ActivityStatus, Severity
from app.domain.events import EventBus, Topics
from app.domain.monitoring import (
    Device,
    DeviceStatusRow,
    DeviceStore,
    MonitorResult,
    MonitorResultStore,
    MonitorState,
)
from app.domain.network import Pinger
from app.domain.time_utils import utc_now
from app.domain.validation import validate_host
from app.services.activity_service import ActivityLogService
from app.services.alert_service import AlertService

logger = logging.getLogger(__name__)

_ALERT_TYPE = "device.offline"


class MonitorService:
    def __init__(
        self,
        devices: DeviceStore,
        results: MonitorResultStore,
        pinger: Pinger,
        alerts: AlertService,
        settings_getter: Callable[[], AppSettings],
        activity: ActivityLogService | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._devices = devices
        self._results = results
        self._pinger = pinger
        self._alerts = alerts
        self._settings_getter = settings_getter
        self._activity = activity
        self._bus = bus

    # ------------------------------------------------------------ CRUD
    def list_devices(self) -> list[Device]:
        return self._devices.list_all()

    def add_device(self, name: str, host: str, interval_seconds: int, timeout_ms: int) -> Device:
        name = (name or "").strip()
        if not name:
            raise ValueError("Device name is required")
        host = validate_host(host)
        if not 5 <= interval_seconds <= 3600:
            raise ValueError("Interval must be between 5 and 3600 seconds")
        if not 100 <= timeout_ms <= 10000:
            raise ValueError("Timeout must be between 100 and 10000 ms")
        if self._devices.get_by_name(name) is not None:
            raise ValueError(f"A device named '{name}' already exists")
        device = Device(
            name=name,
            host=host,
            interval_seconds=interval_seconds,
            timeout_ms=timeout_ms,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        created = self._devices.add(device)
        self._record_activity("device.added", f"name={name} host={host}")
        return created

    def update_device(self, device: Device) -> Device:
        updated = Device(**{**device.__dict__, "updated_at": utc_now()})
        stored = self._devices.update(updated)
        self._record_activity("device.updated", f"name={stored.name}")
        return stored

    def delete_device(self, device_id: int) -> bool:
        device = self._devices.get(device_id)
        deleted = self._devices.delete(device_id)
        if deleted and device is not None:
            self._record_activity("device.deleted", f"name={device.name}")
        return deleted

    # ------------------------------------------------------------ checks
    def check_device(self, device: Device) -> MonitorResult:
        """Ping one device, persist the result, and maintain alerts."""
        settings = self._settings_getter()
        ping = self._pinger.ping(device.host, device.timeout_ms)
        if not ping.reachable:
            state = MonitorState.OFFLINE
        elif (
            ping.response_time_ms is not None
            and ping.response_time_ms > settings.monitoring.latency_warning_ms
        ):
            state = MonitorState.WARNING
        else:
            state = MonitorState.ONLINE

        result = MonitorResult(
            device_id=device.id,  # type: ignore[arg-type]
            timestamp=utc_now(),
            status=state,
            response_time_ms=ping.response_time_ms,
            error_message=ping.error,
        )
        stored = self._results.add(result)
        self._maintain_alerts(device, stored)
        if self._bus is not None:
            self._bus.publish(Topics.MONITOR_RESULT, stored)
        return stored

    def run_round(
        self,
        token: CancelToken | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[MonitorResult]:
        """Check every enabled device concurrently (one round)."""
        devices = [device for device in self._devices.list_all() if device.enabled]
        if not devices:
            return []
        token = token or CancelToken()
        settings = self._settings_getter()
        results: list[MonitorResult] = []
        pool = ThreadPoolExecutor(max_workers=min(settings.scan_max_workers, len(devices)))
        try:
            futures = {pool.submit(self.check_device, device): device for device in devices}
            for done, future in enumerate(as_completed(futures), start=1):
                if token.cancelled:
                    break
                results.append(future.result())
                if on_progress is not None:
                    on_progress(done, len(devices))
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        self._record_activity(
            "monitor.round",
            f"devices={len(results)}/{len(devices)}",
            ActivityStatus.SUCCESS,
        )
        return results

    def _maintain_alerts(self, device: Device, result: MonitorResult) -> None:
        if result.status is MonitorState.OFFLINE:
            self._alerts.raise_alert(
                _ALERT_TYPE,
                Severity.CRITICAL,
                device.name,
                f"{device.name} ({device.host}) is unreachable",
            )
        else:
            recovered = self._alerts.resolve_alerts(_ALERT_TYPE, device.name)
            if recovered:
                self._alerts.raise_alert(
                    "device.recovered",
                    Severity.INFO,
                    device.name,
                    f"{device.name} ({device.host}) is back online",
                )

    # ------------------------------------------------------------ views
    def status_rows(self) -> list[DeviceStatusRow]:
        """Latest result + consecutive failures per device (one query set)."""
        devices = self._devices.list_all()
        ids = [device.id for device in devices if device.id is not None]
        latest = self._results.latest_for_devices([i for i in ids if i is not None])
        rows = []
        for device in devices:
            last = latest.get(device.id) if device.id is not None else None
            failures = self._results.consecutive_failures(device.id) if device.id is not None else 0
            rows.append(
                DeviceStatusRow(device=device, last_result=last, consecutive_failures=failures)
            )
        return rows

    def history(self, device_id: int, hours: float = 1.0) -> list[MonitorResult]:
        end = utc_now()
        start = end - timedelta(hours=hours)
        return self._results.history(device_id, start, end)

    def apply_retention(self, retention_days: int) -> int:
        cutoff = utc_now() - timedelta(days=retention_days)
        deleted = self._results.prune_older_than(cutoff)
        if deleted:
            logger.info("retention: pruned %d monitoring results", deleted)
        return deleted

    def _record_activity(
        self, action: str, message: str, status: ActivityStatus = ActivityStatus.SUCCESS
    ) -> None:
        if self._activity is not None:
            self._activity.record(action, module="monitoring", status=status, message=message)
