"""Integration tests — Alembic migrations produce the full schema."""

from __future__ import annotations

from app.config.paths import AppPaths
from app.infrastructure.db.engine import create_db_engine
from app.infrastructure.db.migrate import run_migrations
from sqlalchemy import inspect

EXPECTED_TABLES = {
    "devices",
    "monitoring_results",
    "system_snapshots",
    "backup_jobs",
    "alerts",
    "activity_logs",
    "settings",
    "alembic_version",
}


def test_migrations_create_all_tables(tmp_path):
    db_path = tmp_path / "itops.db"
    run_migrations(f"sqlite:///{db_path.as_posix()}")

    engine = create_db_engine(db_path)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert tables >= EXPECTED_TABLES


def test_migrations_are_idempotent(tmp_path):
    db_path = tmp_path / "itops.db"
    url = f"sqlite:///{db_path.as_posix()}"
    run_migrations(url)
    run_migrations(url)  # second run must be a no-op, not an error
    assert db_path.exists()


def test_wal_mode_enabled(tmp_path):
    db_path = tmp_path / "itops.db"
    run_migrations(f"sqlite:///{db_path.as_posix()}")
    engine = create_db_engine(db_path)
    try:
        with engine.connect() as connection:
            mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        assert str(mode).lower() == "wal"
    finally:
        engine.dispose()


def test_container_boot_uses_migrations(tmp_paths: AppPaths):
    from app.application.container import AppContainer

    container = AppContainer.build(paths=tmp_paths, console=False)
    try:
        engine = container.engine
        assert engine is not None
        tables = set(inspect(engine).get_table_names())
        assert tables >= EXPECTED_TABLES
    finally:
        container.close()
