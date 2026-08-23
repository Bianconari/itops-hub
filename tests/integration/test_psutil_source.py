"""Integration tests — the production psutil adapter (runs on any OS).

These validate the real adapter's contracts (value ranges, shapes); fake
sources cover business logic in unit tests.
"""

from __future__ import annotations

from app.infrastructure.system.psutil_source import PsutilSystemSource


def test_live_metrics_ranges():
    source = PsutilSystemSource()
    metrics = source.live_metrics()
    assert 0.0 <= metrics.cpu_percent <= 100.0
    assert 0.0 <= metrics.memory_percent <= 100.0
    assert metrics.memory_total_bytes > 0
    assert metrics.memory_used_bytes <= metrics.memory_total_bytes
    if metrics.disk_percent_max is not None:
        assert 0.0 <= metrics.disk_percent_max <= 100.0
    assert metrics.timestamp is not None


def test_drive_usages_valid():
    source = PsutilSystemSource()
    drives = source.drive_usages()
    for drive in drives:
        assert drive.total_bytes >= drive.used_bytes >= 0
        assert drive.free_bytes >= 0
        assert 0.0 <= drive.percent <= 100.0
        assert drive.mountpoint


def test_static_info_shape():
    source = PsutilSystemSource()
    info = source.static_info()
    assert info.hostname
    assert info.os_name
    assert info.os_architecture
    assert info.cpu_model
    assert info.cpu_cores_logical and info.cpu_cores_logical >= 1
    assert info.memory_total_bytes > 0
    assert info.boot_time is not None
    assert len(info.adapters) >= 1
    assert info.python_version


def test_repeated_live_calls_are_consistent():
    source = PsutilSystemSource()
    first = source.live_metrics()
    second = source.live_metrics()
    assert first.memory_total_bytes == second.memory_total_bytes
