"""SQLAlchemy 2.0 models — the complete v1.5 schema (see docs/data-model.md).

The whole schema is created up-front by the initial Alembic migration so the
database stays stable across milestones; repositories and services adopt
tables incrementally as features land.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.time_utils import utc_now


class Base(DeclarativeBase):
    pass


class DeviceModel(Base):
    """A monitored device (ping monitor)."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False, default="ping")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1500)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (UniqueConstraint("name", name="uq_devices_name"),)


class MonitoringResultModel(Base):
    """One ping/connectivity check result for a device."""

    __tablename__ = "monitoring_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('online', 'offline', 'warning')", name="ck_monitoring_status"),
        Index("ix_monitoring_results_device_time", "device_id", "timestamp"),
    )


class SystemSnapshotModel(Base):
    """Periodic local system metrics snapshot."""

    __tablename__ = "system_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_system_snapshots_timestamp", "timestamp"),)


class BackupJobModel(Base):
    """One backup job execution record."""

    __tablename__ = "backup_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    files_copied: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'verified', 'failed', 'cancelled')",
            name="ck_backup_jobs_status",
        ),
    )


class AlertModel(Base):
    """A raised alert (disk threshold, device offline, log anomaly, ...)."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("severity IN ('info', 'warning', 'critical')", name="ck_alerts_severity"),
        Index("ix_alerts_created_at", "created_at"),
    )


class ActivityLogModel(Base):
    """Audit trail of application actions."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="info")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('success', 'failure', 'info')", name="ck_activity_status"),
        Index("ix_activity_logs_timestamp", "timestamp"),
    )


class SettingModel(Base):
    """Key/value settings documents (JSON values)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
