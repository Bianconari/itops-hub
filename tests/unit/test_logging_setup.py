"""Unit tests — logging setup with sanitizing formatter."""

from __future__ import annotations

import logging

from app.domain.sanitization import sanitize_text
from app.infrastructure.logging_setup import SanitizingFormatter, configure_logging


class TestSanitizingFormatter:
    def test_records_are_sanitized(self):
        formatter = SanitizingFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="connected with token=supersecret123",
            args=None,
            exc_info=None,
        )
        rendered = formatter.format(record)
        assert "supersecret123" not in rendered
        assert "token=***" in rendered


class TestConfigureLogging:
    def test_creates_file_and_writes_sanitized(self, tmp_path):
        log_file = configure_logging(tmp_path / "logs", "DEBUG", console=False)
        assert log_file.exists()
        logging.getLogger("itops.test").info("api_key=abc987 visible? token=zzz")
        for handler in logging.getLogger().handlers:
            handler.flush()
        contents = log_file.read_text(encoding="utf-8")
        assert "abc987" not in contents
        assert "zzz" not in contents
        assert "api_key=***" in contents
        assert sanitize_text(contents) == contents

    def test_idempotent_no_duplicate_handlers(self, tmp_path):
        configure_logging(tmp_path / "logs", console=False)
        count_1 = len(logging.getLogger().handlers)
        configure_logging(tmp_path / "logs", console=False)
        count_2 = len(logging.getLogger().handlers)
        assert count_1 == count_2
