"""Log analysis service — streaming, cancellable, format-agnostic.

Reads the file in chunks so multi-hundred-MB logs never blow memory;
progress and cancellation are honored between chunks. Anomalies (v1.3 spec
§1.3-F): error-rate spikes per minute and long timestamp gaps.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from app.domain.cancellation import CancelToken
from app.domain.loganalysis import (
    GenericLevelParser,
    LogLevel,
    LogParser,
    LogSummary,
    ParserRegistry,
    normalize_message,
)
from app.domain.sanitization import sanitize_text
from app.domain.validation import validate_path
from app.services.activity_service import ActivityLogService

logger = logging.getLogger(__name__)

_CHUNK_LINES = 2048
_SAMPLE_LINES = 50


class LogAnalysisService:
    def __init__(
        self,
        registry: ParserRegistry | None = None,
        activity: ActivityLogService | None = None,
    ) -> None:
        self._registry = registry or ParserRegistry()
        self._activity = activity

    def analyze(
        self,
        path: str | Path,
        *,
        token: CancelToken | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> LogSummary:
        """Analyze one log file; returns the summary."""
        file_path = validate_path(path, must_exist=True)
        size = file_path.stat().st_size
        token = token or CancelToken()
        started = time.monotonic()

        parser = self._detect_parser(file_path)
        self._record("log.analyze.started", f"file={file_path.name} parser={parser.name}")

        counts: Counter[str] = Counter()
        top_errors: Counter[str] = Counter()
        total = 0
        parsed = 0
        first_ts: datetime | None = None
        last_ts: datetime | None = None
        error_minutes: Counter[str] = Counter()
        timestamps: list[datetime] = []

        token.raise_if_cancelled()
        with file_path.open("r", encoding="utf-8", errors="replace") as handle:
            buffer: list[str] = []
            bytes_read = 0
            for line in handle:
                total += 1
                bytes_read += len(line.encode("utf-8", errors="replace"))
                buffer.append(line)
                if len(buffer) >= _CHUNK_LINES:
                    token.raise_if_cancelled()
                    self._consume(buffer, parser, counts, top_errors, error_minutes)
                    parsed += len(buffer)
                    buffer.clear()
                    if on_progress is not None:
                        on_progress(bytes_read, size)
            if buffer:
                token.raise_if_cancelled()
                self._consume(buffer, parser, counts, top_errors, error_minutes)
                parsed += len(buffer)
            if on_progress is not None:
                on_progress(size, size)

        # Timestamp stats: re-scan cheaply only when the parser produces them
        first_ts, last_ts, timestamps = self._timestamp_stats(file_path, parser)

        anomalies = self._detect_anomalies(counts, error_minutes, timestamps)
        summary = LogSummary(
            total_lines=total,
            parsed_lines=sum(counts.values()),
            parser_name=parser.name,
            counts=dict(counts),
            top_errors=tuple(
                (count, sanitize_text(message) or message)
                for message, count in top_errors.most_common(10)
            ),
            first_timestamp=first_ts,
            last_timestamp=last_ts,
            anomalies=tuple(anomalies),
            duration_seconds=time.monotonic() - started,
        )
        self._record(
            "log.analyze.completed",
            f"file={file_path.name} lines={total} errors={summary.error_count}",
        )
        return summary

    # ------------------------------------------------------------------
    def _detect_parser(self, path: Path) -> LogParser:
        sample: list[str] = []
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                sample.append(line)
                if len(sample) >= _SAMPLE_LINES:
                    break
        return self._registry.detect(sample)

    def _consume(
        self,
        lines: list[str],
        parser: LogParser,
        counts: Counter[str],
        top_errors: Counter[str],
        error_minutes: Counter[str],
    ) -> None:
        for line in lines:
            entry = parser.parse_line(line)
            if entry is None:
                counts[LogLevel.UNKNOWN.value] += 1
                continue
            counts[entry.level.value] += 1
            if entry.level in (LogLevel.ERROR, LogLevel.CRITICAL):
                top_errors[normalize_message(entry.message)] += 1
                if entry.timestamp is not None:
                    error_minutes[entry.timestamp.strftime("%Y-%m-%d %H:%M")] += 1

    def _timestamp_stats(
        self, path: Path, parser: LogParser
    ) -> tuple[datetime | None, datetime | None, list[datetime]]:
        if isinstance(parser, GenericLevelParser):
            return None, None, []
        timestamps: list[datetime] = []
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                entry = parser.parse_line(line)
                if entry is not None and entry.timestamp is not None:
                    timestamps.append(entry.timestamp)
        if not timestamps:
            return None, None, []
        return min(timestamps), max(timestamps), timestamps

    @staticmethod
    def _detect_anomalies(
        counts: Counter[str], error_minutes: Counter[str], timestamps: list[datetime]
    ) -> list[str]:
        anomalies: list[str] = []
        # 1) error bursts: any minute with >=3x the mean per-minute error rate
        total_errors = counts.get(LogLevel.ERROR.value, 0) + counts.get(LogLevel.CRITICAL.value, 0)
        if error_minutes and total_errors >= 10:
            mean = total_errors / len(error_minutes)
            for minute, count in error_minutes.items():
                if count >= 5 and (count >= 3 * mean or count >= mean + 5):
                    anomalies.append(
                        f"Error burst at {minute}: {count} errors (mean {mean:.1f}/min)"
                    )
        # 2) timestamp gaps > 30 minutes hint at missing/stalled logging
        if len(timestamps) >= 2:
            timestamps = sorted(timestamps)
            previous = timestamps[0]
            for current in timestamps[1:]:
                gap = current - previous
                if gap > timedelta(minutes=30):
                    anomalies.append(f"Logging gap: {gap} between {previous} and {current}")
                previous = current
        return anomalies

    def _record(self, action: str, message: str) -> None:
        if self._activity is not None:
            self._activity.record(action, module="logs", message=message)
