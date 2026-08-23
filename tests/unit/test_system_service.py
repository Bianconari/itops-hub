"""Unit tests — SystemInfoService with a fake source (no psutil needed)."""

from __future__ import annotations

from app.config.settings import AppSettings
from app.domain.system import Level
from app.services.system_service import SystemInfoService
from tests.fakes import FakeSystemSource, make_drives, make_info, make_metrics


def make_service(metrics=None, drives=None, info=None, settings=None):
    source = FakeSystemSource(info=info, metrics=metrics, drives=drives)
    return SystemInfoService(source, lambda: settings or AppSettings())


class TestGetStatus:
    def test_all_healthy(self):
        service = make_service(metrics=make_metrics(cpu=10, memory=20, disk=30))
        status = service.get_status()
        assert status.cpu_level is Level.OK
        assert status.memory_level is Level.OK
        assert status.disk_level is Level.OK
        assert status.overall_level is Level.OK

    def test_disk_critical_dominates_overall(self):
        service = make_service(metrics=make_metrics(cpu=10, memory=20, disk=95))
        status = service.get_status()
        assert status.disk_level is Level.CRITICAL
        assert status.overall_level is Level.CRITICAL

    def test_custom_thresholds_from_settings(self):
        settings = AppSettings(disk={"warning_percent": 50, "critical_percent": 70})
        service = make_service(metrics=make_metrics(disk=55), settings=settings)
        assert service.get_status().disk_level is Level.WARNING

    def test_no_drives_yields_none_disk_level(self):
        service = make_service(metrics=make_metrics(disk=None))
        status = service.get_status()
        assert status.disk_level is None
        assert status.overall_level is Level.OK  # cpu/mem fine

    def test_cpu_warning_at_80(self):
        service = make_service(metrics=make_metrics(cpu=85, memory=20, disk=30))
        status = service.get_status()
        assert status.cpu_level is Level.WARNING
        assert status.overall_level is Level.WARNING


class TestStaticHelpers:
    def test_primary_ipv4_skips_loopback(self):
        assert SystemInfoService.primary_ipv4(make_info()) == "10.0.0.5"

    def test_primary_ipv4_fallback(self):
        info = make_info()
        loopback_only = type(info)(**{**info.__dict__, "adapters": info.adapters[1:]})
        assert SystemInfoService.primary_ipv4(loopback_only) == "No IPv4 address"

    def test_up_interface_count(self):
        assert SystemInfoService.up_interface_count(make_info()) == 2

    def test_uptime_non_negative(self):
        service = make_service()
        assert service.uptime_seconds(make_info()) >= 0.0

    def test_get_drives_passthrough(self):
        drives = make_drives([10, 20])
        service = make_service(drives=drives)
        assert service.get_drives() == drives
