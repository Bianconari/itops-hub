"""Scheduler service — headless interval scheduler for recurring jobs.

Runs in its own daemon thread; every tick (30s) it checks what is due:
  - device monitoring rounds (per-device intervals)
  - system snapshot recording
  - scheduled backup profiles (from settings)
  - retention pruning (once per day)

Jobs never overlap themselves; failures are logged and retried next due
time. The UI subscribes to the same bus events ad-hoc checks produce.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.config.settings import AppSettings
from app.domain.monitoring import Device
from app.domain.time_utils import utc_now
from app.services.backup_service import BackupService
from app.services.monitor_service import MonitorService
from app.services.snapshot_service import SnapshotService

logger = logging.getLogger(__name__)

_TICK_SECONDS = 30.0


class SchedulerService:
    def __init__(
        self,
        settings_getter: Callable[[], AppSettings],
        monitor: MonitorService,
        snapshots: SnapshotService,
        backups: BackupService,
        container_retention: Callable[[int], int],
    ) -> None:
        self._settings_getter = settings_getter
        self._monitor = monitor
        self._snapshots = snapshots
        self._backups = backups
        self._container_retention = container_retention
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="itops-sched")
        self._next_device_check: dict[int, float] = {}
        self._next_snapshot = 0.0
        self._next_retention = 0.0
        self._next_backup: dict[str, float] = {}
        self._last_tick = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------ control
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="itops-scheduler", daemon=True)
        self._thread.start()
        logger.info("scheduler started")

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("scheduler stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------ loop
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception:
                logger.exception("scheduler tick failed")
            self._stop.wait(_TICK_SECONDS)

    def tick_once(self) -> None:
        """One scheduling pass (also the unit-test entry point)."""
        now = time.monotonic()
        settings = self._settings_getter()

        # --- device monitoring
        for device in self._monitor.list_devices():
            if not device.enabled or device.id is None:
                continue
            due = self._next_device_check.get(device.id, 0.0)
            if now >= due:
                self._next_device_check[device.id] = now + device.interval_seconds
                self._pool.submit(self._safe_check, device)

        # --- system snapshots
        if now >= self._next_snapshot:
            self._next_snapshot = now + settings.snapshots.interval_seconds
            self._pool.submit(self._safe_snapshot)

        # --- scheduled backups
        for profile in settings.backup_profiles:
            if not profile.enabled:
                continue
            due = self._next_backup.get(profile.name, 0.0)
            if now >= due:
                self._next_backup[profile.name] = now + profile.interval_hours * 3600
                self._pool.submit(
                    self._safe_backup, profile.source, profile.destination, profile.verify
                )

        # --- retention once a day
        if now >= self._next_retention:
            self._next_retention = now + 24 * 3600
            self._pool.submit(self._safe_retention, settings.retention_days)

        self._last_tick = utc_now().timestamp()

    # ------------------------------------------------------------ jobs
    def _safe_check(self, device: Device) -> None:
        try:
            self._monitor.check_device(device)
        except Exception:
            logger.exception("scheduled check failed for %s", device.name)

    def _safe_snapshot(self) -> None:
        try:
            from app.infrastructure.system.psutil_source import PsutilSystemSource

            metrics = PsutilSystemSource().live_metrics()
            self._snapshots.record(metrics)
        except Exception:
            logger.exception("scheduled snapshot failed")

    def _safe_backup(self, source: str, destination: str, verify: bool) -> None:
        try:
            self._backups.run_backup(source, destination, verify=verify)
        except Exception:
            logger.exception("scheduled backup failed (%s)", source)

    def _safe_retention(self, retention_days: int) -> None:
        try:
            self._container_retention(retention_days)
        except Exception:
            logger.exception("scheduled retention failed")

    # ------------------------------------------------------------ status
    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "running": self.running,
                "devices_tracked": len(self._next_device_check),
                "backup_profiles": len(self._next_backup),
                "last_tick_epoch": self._last_tick,
            }

    def next_due_in(self, device_id: int) -> float:
        return max(0.0, self._next_device_check.get(device_id, 0.0) - time.monotonic())
