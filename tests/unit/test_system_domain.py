"""Unit tests — system domain model and formatters."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.domain.formatters import (
    as_local_string,
    epoch_of,
    format_uptime,
    human_bytes,
)
from app.domain.system import Level, evaluate_usage_level


class TestEvaluateUsageLevel:
    def test_ok_below_warning(self):
        assert evaluate_usage_level(79.9, 80, 90) is Level.OK

    def test_warning_boundary_inclusive(self):
        assert evaluate_usage_level(80, 80, 90) is Level.WARNING

    def test_critical_boundary_inclusive(self):
        assert evaluate_usage_level(90, 80, 90) is Level.CRITICAL

    def test_above_critical(self):
        assert evaluate_usage_level(99.9, 80, 90) is Level.CRITICAL


class TestHumanBytes:
    def test_zero(self):
        assert human_bytes(0) == "0 B"

    def test_kib(self):
        assert human_bytes(1024) == "1.0 KiB"

    def test_gib(self):
        assert human_bytes(16 * 1024**3) == "16.0 GiB"

    def test_tib(self):
        assert human_bytes(2 * 1024**4) == "2.0 TiB"

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            human_bytes(-1)


class TestFormatUptime:
    def test_minutes_only(self):
        assert format_uptime(59 * 60) == "59m"

    def test_hours_and_minutes(self):
        assert format_uptime(3 * 3600 + 5 * 60) == "3h 5m"

    def test_days(self):
        assert format_uptime(2 * 86400 + 4 * 3600 + 2 * 60) == "2d 4h 2m"

    def test_zero(self):
        assert format_uptime(0) == "0m"

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            format_uptime(-5)


class TestTimeConversions:
    def test_epoch_of_roundtrip(self):
        naive = datetime(2026, 8, 23, 12, 0, 0)
        assert epoch_of(naive) == naive.replace(tzinfo=UTC).timestamp()

    def test_as_local_string_uses_local_tz(self):
        naive = datetime(2026, 8, 23, 12, 0, 0)
        local = as_local_string(naive)
        expected = naive.replace(tzinfo=UTC).astimezone().strftime("%Y-%m-%d %H:%M")
        assert local == expected
