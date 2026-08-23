"""Structured logging setup: rotating file handler + optional console.

All records pass through a sanitizing formatter (see
``app.domain.sanitization``) as defense-in-depth against accidental
credential leakage into logs.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.domain.sanitization import sanitize_text

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


class _ManagedRotatingFileHandler(RotatingFileHandler):
    """Marker subclass so reconfiguration can replace only our handlers."""


class _ManagedStreamHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Marker subclass so reconfiguration can replace only our handlers."""


class SanitizingFormatter(logging.Formatter):
    """Formatter that redacts common credential patterns from messages."""

    def format(self, record: logging.LogRecord) -> str:
        return sanitize_text(super().format(record)) or ""


def configure_logging(
    log_dir: Path,
    level: str = "INFO",
    *,
    console: bool = True,
) -> Path:
    """Configure the root logger; returns the log file path.

    Safe to call repeatedly (idempotent): existing ITOps-managed handlers are
    replaced instead of duplicated.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "itops-hub.log"

    root = logging.getLogger()
    root.setLevel(level.upper())

    formatter = SanitizingFormatter(fmt=_FORMAT, datefmt=_DATE_FORMAT)

    for handler in list(root.handlers):
        if isinstance(handler, (_ManagedRotatingFileHandler, _ManagedStreamHandler)):
            root.removeHandler(handler)
            handler.close()

    file_handler = _ManagedRotatingFileHandler(
        log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if console:
        console_handler = _ManagedStreamHandler()
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    return log_file
