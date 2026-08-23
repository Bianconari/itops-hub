"""Application container (manual dependency injection).

Builds and owns the core object graph:
    paths -> engine -> migrations -> session -> repositories -> services

The container is Qt-free so the whole core can boot headless (selftest, and
later the standalone API process). UI and API are attached on top of it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.paths import AppPaths
from app.domain.events import EventBus
from app.infrastructure.db.engine import create_db_engine, create_session_factory
from app.infrastructure.db.migrate import run_migrations
from app.infrastructure.db.repositories import ActivityRepository, SettingRepository
from app.infrastructure.logging_setup import configure_logging
from app.services.activity_service import ActivityLogService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    """Fully wired application core."""

    paths: AppPaths
    bus: EventBus = field(default_factory=EventBus)
    settings_service: SettingsService | None = None
    activity_service: ActivityLogService | None = None
    engine: Engine | None = None
    session_factory: sessionmaker[Session] | None = None

    @classmethod
    def build(cls, paths: AppPaths | None = None, *, console: bool = True) -> AppContainer:
        """Construct the core; applies migrations and configures logging."""
        container = cls(paths=paths or AppPaths.create())
        container.paths.ensure()

        container.engine = create_db_engine(container.paths.db_path)
        run_migrations(f"sqlite:///{container.paths.db_path.as_posix()}")
        container.session_factory = create_session_factory(container.engine)

        session = container.session_factory()
        try:
            activity_repo = ActivityRepository(session)
            settings_repo = SettingRepository(session)
            container.activity_service = ActivityLogService(activity_repo)
            container.settings_service = SettingsService(
                settings_repo, container.bus, container.activity_service
            )
        finally:
            session.close()

        log_level = container.settings_service.get().log_level.value
        configure_logging(container.paths.log_dir, log_level, console=console)
        logger.info("ITOps Hub core initialized (db=%s)", container.paths.db_path)
        return container

    def new_session(self) -> Session:
        """Open a new unit-of-work session (caller owns closing it)."""
        assert self.session_factory is not None, "container not built"
        return self.session_factory()

    def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
