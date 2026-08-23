"""Integration tests — log analysis service on fixture files (streaming, cancel)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.domain.cancellation import CancelToken, OperationCancelled
from app.domain.loganalysis import LogLevel
from app.services.log_analysis_service import LogAnalysisService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def service():
    return LogAnalysisService()


class TestAnalyze:
    def test_python_log_summary(self, service: LogAnalysisService):
        summary = service.analyze(FIXTURES / "sample-python.log")
        assert summary.parser_name == "python-logging"
        assert summary.total_lines == 18
        assert summary.counts[LogLevel.INFO.value] == 3
        assert summary.counts[LogLevel.WARNING.value] == 2
        assert summary.counts[LogLevel.ERROR.value] == 11
        assert summary.counts[LogLevel.CRITICAL.value] == 1
        assert summary.counts[LogLevel.UNKNOWN.value] == 1  # "not a log line at all"
        assert summary.first_timestamp is not None
        assert summary.last_timestamp is not None
        top_count, top_message = summary.top_errors[0]
        assert top_count == 11
        assert "Login failed" in top_message
        assert "10.0.0.42" in top_message or "#" in top_message

    def test_syslog_summary(self, service: LogAnalysisService):
        summary = service.analyze(FIXTURES / "sample-syslog.log")
        assert summary.parser_name == "syslog"
        assert summary.counts[LogLevel.ERROR.value] >= 3  # failed passwords + failed service

    def test_generic_summary(self, service: LogAnalysisService):
        summary = service.analyze(FIXTURES / "sample-generic.log")
        assert summary.parser_name == "generic-level"
        assert summary.counts[LogLevel.ERROR.value] == 2
        assert summary.counts[LogLevel.CRITICAL.value] == 1
        assert summary.first_timestamp is None  # no timestamps in generic mode

    def test_missing_file_raises_validation_error(self, service: LogAnalysisService):
        with pytest.raises(ValueError):
            service.analyze("/nonexistent/whatever.log")

    def test_anomaly_burst_detected(self, service: LogAnalysisService):
        summary = service.analyze(FIXTURES / "sample-python.log")
        assert any("Error burst" in anomaly for anomaly in summary.anomalies)


class TestProgressAndCancellation:
    def test_progress_reaches_total(self, service: LogAnalysisService, tmp_path):
        big = tmp_path / "big.log"
        big.write_text(
            "\n".join(
                f"2026-08-20 09:{i // 60:02d}:{i % 60:02d},000 INFO app line {i}"
                for i in range(5000)
            )
        )
        seen = []
        summary = service.analyze(big, on_progress=lambda done, total: seen.append((done, total)))
        assert seen and seen[-1] == (big.stat().st_size, big.stat().st_size)
        assert summary.total_lines == 5000

    def test_cancellation_stops_analysis(self, service: LogAnalysisService, tmp_path):
        big = tmp_path / "big.log"
        big.write_text(
            "\n".join(
                f"2026-08-20 09:00:{i % 60:02d},000 ERROR app failure {i}" for i in range(50_000)
            )
        )
        token = CancelToken()

        def on_progress(done: int, total: int) -> None:
            if done > 0:
                token.cancel()

        with pytest.raises(OperationCancelled):
            service.analyze(big, token=token, on_progress=on_progress)
