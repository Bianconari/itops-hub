"""Backup domain model: job entities and the store Protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class BackupStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    VERIFIED = "verified"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class BackupJob:
    """One backup execution (persisted in ``backup_jobs``)."""

    source: str
    destination: str
    started_at: datetime
    status: BackupStatus = BackupStatus.RUNNING
    completed_at: datetime | None = None
    size_bytes: int | None = None
    files_copied: int | None = None
    checksum_verified: bool | None = None
    error_message: str | None = None
    id: int | None = None


class BackupStore(Protocol):
    def add(self, job: BackupJob) -> BackupJob: ...

    def update(self, job: BackupJob) -> BackupJob: ...

    def list_recent(self, limit: int = 50) -> list[BackupJob]: ...
