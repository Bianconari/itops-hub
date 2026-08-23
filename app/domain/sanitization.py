"""Sanitization of potentially sensitive text before it is logged.

The application never handles passwords or API keys by design; this module is
defense-in-depth so that if sensitive material ever reaches a log call, it is
redacted before being written to disk or the database.
"""

from __future__ import annotations

import re

_KEY_VALUE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|authorization)\b"
    r"(\s*[=:]\s*)([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]+")
_REDACTED = "***"


def sanitize_text(text: str | None) -> str | None:
    """Redact common credential patterns from text; returns the cleaned text."""
    if text is None:
        return None
    # Bearer tokens first: otherwise the key=value rule would eat the word
    # "Bearer" and leave the actual token exposed.
    cleaned = _BEARER.sub(lambda m: f"{m.group(1)}{_REDACTED}", text)
    cleaned = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}", cleaned)
    return cleaned
