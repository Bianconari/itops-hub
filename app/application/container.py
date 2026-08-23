"""Application container (manual dependency injection).

Builds and owns the core object graph:
    paths -> engine -> migrations -> session -> repositories -> services

The container is Qt-free so the whole core can boot headless (selftest, and
later the standalone API process). UI and API are attached on top of it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.paths import AppPaths
from app.config.settings import AppSettings
from app.domain.events import EventBus
from app.infrastructure.db.engine import create_db_engine, create_session_factory
from app.infrastructure.db.migrate import run_migrations
from app.infrastructure.db.repositories import (
    ActivityRepository,
    AlertRepository,
    SettingRepository,
    SystemSnapshotRepository,
)
from app.infrastructure.logging_setup import configure_logging
from app.infrastructure.network.arp_table import ArpTable
from app.infrastructure.network.resolver import SocketHostnameResolver
from app.infrastructure.network.system_pinger import SystemPinger
from app.infrastructure.system.psutil_source import PsutilSystemSource
from app.services.activity_service import ActivityLogService
from app.services.alert_service import AlertService
from app.services.export_service import ExportService
from app.services.network_scan_service import NetworkScanService
from app.services.settings_service import SettingsService
from app.services.snapshot_service import SnapshotService
from app.services.system_service import SystemInfoService

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    """Fully wired application core."""

    paths: AppPaths
    bus: EventBus = field(default_factory=EventBus)
    settings_service: SettingsService | None = None
    activity_service: ActivityLogService | None = None
    alert_service: AlertService | None = None
    system_service: SystemInfoService | None = None
    snapshot_service: SnapshotService | None = None
    network_scan_service: NetworkScanService | None = None
    export_service: ExportService | None = None
    engine: Engine | None = None
    session_factory: sessionmaker[Session] | None = None

    @classmethod
    def build(cls, paths: AppPaths | None = None, *, console: bool = True) -> AppContainer:
        """Construct the core; applies migrations, retention, and logging."""
        container = cls(paths=paths or AppPaths.create())
        container.paths.ensure()

        container.engine = create_db_engine(container.paths.db_path)
        run_migrations(f"sqlite:///{container.paths.db_path.as_posix()}")
        container.session_factory = create_session_factory(container.engine)

        session = container.session_factory()
        try:
            activity_repo = ActivityRepository(session)
            settings_repo = SettingRepository(session)
            snapshot_repo = SystemSnapshotRepository(session)
            alert_repo = AlertRepository(session)

            container.activity_service = ActivityLogService(activity_repo)
            container.settings_service = SettingsService(
                settings_repo, container.bus, container.activity_service
            )
            container.snapshot_service = SnapshotService(snapshot_repo)
            container.alert_service = AlertService(alert_repo)
            settings_getter: Callable[[], AppSettings] = container.settings_service.get
            container.system_service = SystemInfoService(PsutilSystemSource(), settings_getter)
            container.network_scan_service = NetworkScanService(
                SystemPinger(),
                SocketHostnameResolver(),
                ArpTable(),
                settings_getter,
                activity=container.activity_service,
                bus=container.bus,
            )
            container.export_service = ExportService(
                settings_getter, container.paths, container.activity_service
            )
        finally:
            session.close()

        log_level = container.settings_service.get().log_level.value
        configure_logging(container.paths.log_dir, log_level, console=console)

        container.apply_retention()
        logger.info("ITOps Hub core initialized (db=%s)", container.paths.db_path)
        return container

    def apply_retention(self) -> int:
        """Prune snapshot history older than the configured retention."""
        assert self.snapshot_service is not None and self.settings_service is not None
        retention_days = self.settings_service.get().retention_days
        return self.snapshot_service.apply_retention(retention_days)

    def new_session(self) -> Session:
        """Open a new unit-of-work session (caller owns closing it)."""
        assert self.session_factory is not None, "container not built"
        return self.session_factory()

    def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
