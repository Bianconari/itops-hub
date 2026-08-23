"""Log analysis domain: levels, entries, parsers, and summary.

Parsers are pure (line in → entry out) and pluggable per Spec §1.3-F: no
single format is hardcoded into the service; new parsers register in the
registry and auto-detection scores them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LogEntry:
    level: LogLevel
    message: str
    raw: str
    timestamp: datetime | None = None


@dataclass(frozen=True)
class LogSummary:
    total_lines: int
    parsed_lines: int
    parser_name: str
    counts: dict[str, int] = field(default_factory=dict)
    top_errors: tuple[tuple[int, str], ...] = ()
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    anomalies: tuple[str, ...] = ()
    duration_seconds: float = 0.0

    @property
    def error_count(self) -> int:
        return self.counts.get(LogLevel.ERROR.value, 0) + self.counts.get(
            LogLevel.CRITICAL.value, 0
        )


class LogParser(Protocol):
    """One line-in → entry-out parser with a name and a confidence probe."""

    name: str

    def parse_line(self, line: str) -> LogEntry | None: ...


_PYTHON_LOGGING = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[,.]?\d+)\s+"
    r"(?P<level>DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\s+(?P<msg>.*)$"
)
_SYSLOG = re.compile(
    r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+"
    r"(?P<proc>[^\s:]+)(?:\[(?P<pid>\d+)\])?:\s*(?P<msg>.*)$"
)
_GENERIC_LEVEL = re.compile(r"\b(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\b")
_ISO_TS = "%Y-%m-%d %H:%M:%S,%f"
_ISO_TS_DOT = "%Y-%m-%d %H:%M:%S.%f"
_ISO_TS_PLAIN = "%Y-%m-%d %H:%M:%S"
_SYSLOG_TS = "%b %d %H:%M:%S"

_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}


def normalize_level(token: str) -> LogLevel:
    value = _LEVEL_ALIASES.get(token.upper(), token.upper())
    try:
        return LogLevel(value)
    except ValueError:
        return LogLevel.UNKNOWN


class PythonLoggingParser:
    """Python ``logging`` default format: ``2026-08-23 12:00:01,123 WARNING mod msg``."""

    name = "python-logging"

    def parse_line(self, line: str) -> LogEntry | None:
        match = _PYTHON_LOGGING.match(line.strip())
        if match is None:
            return None
        raw_ts = match.group("ts").replace("T", " ")
        ts = None
        for fmt in (_ISO_TS, _ISO_TS_DOT, _ISO_TS_PLAIN):
            try:
                ts = datetime.strptime(raw_ts, fmt)
                break
            except ValueError:
                continue
        return LogEntry(
            level=normalize_level(match.group("level")),
            message=match.group("msg").strip(),
            raw=line,
            timestamp=ts,
        )


class SyslogParser:
    """Classic syslog: ``Aug 23 12:00:01 host proc[pid]: message``.

    Syslog lines carry no explicit level; severity is inferred from message
    keywords, and no year — the current year is assumed when parsing
    (standard syslog behavior; lines written in December read in January
    will show the wrong year — an inherent format limitation, documented
    here rather than papered over with an ambiguous default).
    """

    name = "syslog"
    _KEYWORDS = (
        ("critical", LogLevel.CRITICAL),
        ("emerg", LogLevel.CRITICAL),
        ("alert", LogLevel.CRITICAL),
        ("error", LogLevel.ERROR),
        ("fail", LogLevel.ERROR),
        ("warn", LogLevel.WARNING),
    )

    def parse_line(self, line: str) -> LogEntry | None:
        match = _SYSLOG.match(line.strip())
        if match is None:
            return None
        try:
            stamped = f"{datetime.now().year} {match.group('ts').replace('  ', ' ')}"
            ts = datetime.strptime(stamped, "%Y %b %d %H:%M:%S")
        except ValueError:
            ts = None
        message = match.group("msg").strip()
        lowered = message.lower()
        level = LogLevel.INFO
        for keyword, mapped in self._KEYWORDS:
            if keyword in lowered:
                level = mapped
                break
        return LogEntry(level=level, message=message, raw=line, timestamp=ts)


class GenericLevelParser:
    """Fallback: any line containing an explicit level token (no timestamp needed)."""

    name = "generic-level"

    def parse_line(self, line: str) -> LogEntry | None:
        match = _GENERIC_LEVEL.search(line)
        if match is None:
            return None
        token = match.group(1)
        message = line.strip()
        return LogEntry(level=normalize_level(token), message=message, raw=line, timestamp=None)


class ParserRegistry:
    """Ordered parser set with confidence-based auto-detection."""

    def __init__(self, parsers: list[LogParser] | None = None) -> None:
        self._parsers = parsers or [
            PythonLoggingParser(),
            SyslogParser(),
            GenericLevelParser(),
        ]

    @property
    def parsers(self) -> list[LogParser]:
        return list(self._parsers)

    def detect(self, sample_lines: list[str], *, min_confidence: float = 0.3) -> LogParser:
        """Return the parser that parses the largest fraction of the sample."""
        best: LogParser | None = None
        best_ratio = 0.0
        for parser in self._parsers:
            hits = sum(1 for line in sample_lines if line.strip() and parser.parse_line(line))
            ratio = hits / max(1, len([line for line in sample_lines if line.strip()]))
            if ratio > best_ratio:
                best, best_ratio = parser, ratio
        if best is None or best_ratio < min_confidence:
            return GenericLevelParser()
        return best


_NUM_NORMALIZE = re.compile(r"\d+")
_HEX_NORMALIZE = re.compile(r"0x[0-9a-fA-F]+")


def normalize_message(message: str) -> str:
    """Group similar messages by replacing numbers/hex with placeholders."""
    normalized = _HEX_NORMALIZE.sub("<hex>", message)
    normalized = _NUM_NORMALIZE.sub("#", normalized)
    return normalized.replace("<hex>", "0x#")[:300]
