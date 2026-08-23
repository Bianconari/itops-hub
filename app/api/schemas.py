"""API request/response schemas (Pydantic v2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=253)
    interval_seconds: int = Field(default=30, ge=5, le=3600)
    timeout_ms: int = Field(default=1500, ge=100, le=10000)


class ScanRequest(BaseModel):
    cidr: str
    #: Required (true) to scan non-private ranges when the guard is enabled.
    authorized: bool = False


class LogAnalyzeRequest(BaseModel):
    path: str


class BackupRequest(BaseModel):
    source: str
    destination: str
    verify: bool = True  # legacy: True -> "size", False -> "none"
    verify_mode: Literal["none", "size", "sha256"] | None = None  # wins if set


class ReportRequest(BaseModel):
    report_key: str
    format: Literal["csv", "json", "txt"] = "csv"
    hours: float = Field(default=24.0, gt=0, le=24 * 31)
    device_id: int | None = None


class AckRequest(BaseModel):
    confirm: bool = False
