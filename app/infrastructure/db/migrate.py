"""Programmatic Alembic migration runner.

Called at application start (desktop and selftest) to bring the local SQLite
database to the latest schema. Keeps schema changes reviewable and reversible;
the same versions directory is reused when PostgreSQL is introduced later.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

_SCRIPT_LOCATION = Path(__file__).parent / "alembic"


def run_migrations(db_url: str) -> None:
    """Upgrade the database at ``db_url`` to the latest revision (head)."""
    config = Config()
    config.set_main_option("script_location", str(_SCRIPT_LOCATION))
    config.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(config, "head")
    logger.debug("database migrations applied (%s)", db_url)
