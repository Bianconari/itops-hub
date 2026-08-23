"""Unit tests — log parsers, registry detection, message normalization."""

from __future__ import annotations

from pathlib import Path

from app.domain.loganalysis import (
    GenericLevelParser,
    LogLevel,
    ParserRegistry,
    PythonLoggingParser,
    SyslogParser,
    normalize_message,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class TestPythonLoggingParser:
    def test_standard_line(self):
        entry = PythonLoggingParser().parse_line(
            "2026-08-20 09:00:05,312 WARNING  web.tls Certificate expires in 12 days"
        )
        assert entry is not None
        assert entry.level is LogLevel.WARNING
        assert entry.message == "web.tls Certificate expires in 12 days"
        assert entry.timestamp is not None and entry.timestamp.year == 2026

    def test_aliases(self):
        parser = PythonLoggingParser()
        assert parser.parse_line("2026-08-20 10:00:00,000 WARN m w").level is LogLevel.WARNING
        assert parser.parse_line("2026-08-20 10:00:00,000 FATAL m w").level is LogLevel.CRITICAL

    def test_non_matching(self):
        assert PythonLoggingParser().parse_line("Aug 23 08:00:01 host proc: msg") is None


class TestSyslogParser:
    def test_standard_line(self):
        entry = SyslogParser().parse_line(
            "Aug 23 08:00:09 gw01 sshd[820]: Failed password for invalid user admin"
        )
        assert entry is not None
        assert entry.level is LogLevel.ERROR  # keyword inferred
        assert entry.timestamp is not None

    def test_info_when_no_keyword(self):
        entry = SyslogParser().parse_line("Aug 23 09:00:00 gw01 dhclient[441]: DHCPREQUEST on eth0")
        assert entry is not None and entry.level is LogLevel.INFO


class TestGenericLevelParser:
    def test_finds_token_anywhere(self):
        entry = GenericLevelParser().parse_line("user 42 logged in; INFO cache warm")
        assert entry is not None and entry.level is LogLevel.INFO

    def test_none_without_token(self):
        assert GenericLevelParser().parse_line("nothing here") is None


class TestRegistryDetection:
    def test_detects_python_logging(self):
        lines = (FIXTURES / "sample-python.log").read_text().splitlines()
        parser = ParserRegistry().detect(lines[:20])
        assert parser.name == "python-logging"

    def test_detects_syslog(self):
        lines = (FIXTURES / "sample-syslog.log").read_text().splitlines()
        parser = ParserRegistry().detect(lines)
        assert parser.name == "syslog"

    def test_falls_back_to_generic(self):
        lines = (FIXTURES / "sample-generic.log").read_text().splitlines()
        parser = ParserRegistry().detect(lines)
        assert parser.name == "generic-level"

    def test_garbage_falls_back_to_generic(self):
        parser = ParserRegistry().detect(["+++", "###", "!!!"])
        assert parser.name == "generic-level"


class TestNormalizeMessage:
    def test_numbers_and_hex_grouped(self):
        assert normalize_message("user 42 failed after 3 tries at 0x1A2B") == (
            "user # failed after # tries at 0x#"
        )

    def test_truncates_long_messages(self):
        assert len(normalize_message("x" * 500)) == 300
