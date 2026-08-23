"""Unit tests — export service (CSV / JSON / TXT with metadata)."""

from __future__ import annotations

import csv
import json
from datetime import timedelta

import pytest
from app.config.paths import AppPaths
from app.config.settings import AppSettings
from app.domain.network import HostResult, ScanResult
from app.domain.time_utils import utc_now
from app.services.activity_service import ActivityLogService
from app.services.export_service import ExportError, ExportService
from tests.fakes import FakeActivityStore


def make_result() -> ScanResult:
    now = utc_now()
    hosts = (
        HostResult(
            ip="10.0.0.1",
            reachable=True,
            response_time_ms=3.5,
            hostname="router.lan",
            mac="aa:bb:cc:dd:ee:01",
            timestamp=now,
        ),
        HostResult(
            ip="10.0.0.2",
            reachable=False,
            response_time_ms=None,
            hostname=None,
            mac=None,
            timestamp=now + timedelta(seconds=1),
        ),
    )
    return ScanResult(
        network="10.0.0.0/29",
        started_at=now,
        completed_at=now + timedelta(seconds=2),
        duration_seconds=2.0,
        total=6,
        results=hosts,
    )


@pytest.fixture
def export_dir(tmp_path):
    return tmp_path / "exports"


@pytest.fixture
def activity():
    return ActivityLogService(FakeActivityStore())


@pytest.fixture
def service(export_dir, activity) -> ExportService:
    settings = AppSettings(default_export_dir=export_dir)
    paths = AppPaths.create(base=export_dir.parent / "data")
    return ExportService(lambda: settings, paths, activity)


class TestFormats:
    def test_csv_roundtrip(self, service, export_dir):
        path = service.export_scan(make_result(), "csv")
        assert path.exists() and path.name.startswith("network-scan-")
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 2
        assert rows[0]["ip"] == "10.0.0.1"
        assert rows[0]["reachable"] == "yes"
        assert rows[0]["hostname"] == "router.lan"
        assert rows[1]["reachable"] == "no"

    def test_json_contains_metadata(self, service):
        path = service.export_scan(make_result(), "json")
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["meta"]["network"] == "10.0.0.0/29"
        assert document["meta"]["reachable"] == 1
        assert document["meta"]["application"] == "ITOps Hub"
        assert len(document["rows"]) == 2

    def test_txt_is_aligned_table(self, service):
        path = service.export_scan(make_result(), "txt")
        text = path.read_text(encoding="utf-8")
        assert "ITOps Hub report" in text
        assert "10.0.0.0/29" in text
        assert "router.lan" in text


class TestBehavior:
    def test_never_overwrites_existing_files(self, service, export_dir):
        first = service.export_scan(make_result(), "csv")
        second = service.export_scan(make_result(), "csv")
        assert first != second
        assert first.exists() and second.exists()

    def test_activity_recorded(self, service, activity):
        service.export_scan(make_result(), "csv")
        entries = activity.recent(1)
        assert entries[0].action == "report.exported"

    def test_unwritable_directory_raises_export_error(self, tmp_path, activity):
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file")
        settings = AppSettings(default_export_dir=blocker / "exports")
        service = ExportService(lambda: settings, AppPaths.create(base=tmp_path), activity)
        with pytest.raises(ExportError):
            service.export_scan(make_result(), "csv")
