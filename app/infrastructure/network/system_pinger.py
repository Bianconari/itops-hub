"""System-ping reachability prober (implements ``Pinger``).

Design (AD-009):
- Uses the OS ``ping`` binary through ``subprocess.run`` with an argument
  LIST (never ``shell=True``), a validated host, and a bounded timeout.
- Works without administrator rights and without Npcap.
- Reachability uses the locale-independent exit code plus a TTL check on
  Windows (where ``ping`` can exit 0 for "destination unreachable" replies).
- Response time is parsed best-effort; localized outputs yield None.
"""

from __future__ import annotations

import math
import re
import subprocess

from app.domain.network import PingResult
from app.domain.validation import validate_host

_LATENCY = re.compile(r"time[=<]([0-9]+(?:\.[0-9]+)?)\s*ms", re.IGNORECASE)
_MIN_TIMEOUT_MS = 100
_MAX_TIMEOUT_MS = 10_000


def parse_latency_ms(output: str) -> float | None:
    """Best-effort latency extraction from ping output (None if localized)."""
    match = _LATENCY.search(output)
    return float(match.group(1)) if match else None


def is_reachable(returncode: int, output: str, *, windows: bool) -> bool:
    """Decide reachability from exit code and output.

    Windows: exit code 0 can also mean an ICMP error reply was received, so
    require the locale-independent ``ttl=`` marker in the output.
    POSIX: exit code 0 reliably means an echo reply arrived.
    """
    lowered = output.lower()
    if windows:
        return returncode == 0 and "ttl=" in lowered
    return returncode == 0


class SystemPinger:
    """Production ``Pinger`` using the operating system's ping binary."""

    def __init__(self) -> None:
        import os

        self._windows = os.name == "nt"

    def ping(self, host: str, timeout_ms: int) -> PingResult:
        # A prober never raises: invalid input becomes an unreachable result.
        # (List-args already make injection impossible; validation is belt & braces.)
        try:
            host = validate_host(host)
        except ValueError as exc:
            return PingResult(host=str(host)[:100], reachable=False, error=f"invalid host: {exc}")
        timeout_ms = min(max(timeout_ms, _MIN_TIMEOUT_MS), _MAX_TIMEOUT_MS)

        if self._windows:
            args = ["ping", "-n", "1", "-w", str(timeout_ms), host]
            deadline_s = timeout_ms / 1000 + 1.5
        else:
            wait_s = max(1, math.ceil(timeout_ms / 1000))
            args = ["ping", "-c", "1", "-W", str(wait_s), host]
            deadline_s = wait_s + 1.5

        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=deadline_s,
            )
        except subprocess.TimeoutExpired:
            return PingResult(host=host, reachable=False, error="timeout")
        except OSError as exc:
            return PingResult(host=host, reachable=False, error=f"ping failed: {exc}")

        output = completed.stdout or ""
        reachable = is_reachable(completed.returncode, output, windows=self._windows)
        if not reachable:
            return PingResult(host=host, reachable=False, error="no reply")
        return PingResult(
            host=host,
            reachable=True,
            response_time_ms=parse_latency_ms(output),
        )
