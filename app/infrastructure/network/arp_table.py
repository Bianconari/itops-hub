"""ARP cache reader (implements ``ArpSource``).

Reads the existing kernel ARP cache — no packets are sent, no Npcap needed
(AD-009). MACs are normalized to lowercase colon notation. On Windows the
cache is filled by the ping sweep itself, so lookups happen after scanning.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_WINDOWS_ARP = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})\s+((?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2})")
_DYNAMIC_HINT = "dynamic"
_STATIC_HINT = "static"


def parse_windows_arp(output: str) -> dict[str, str]:
    """Parse ``arp -a`` output (interface sections + dynamic/static rows)."""
    table: dict[str, str] = {}
    for match in _WINDOWS_ARP.finditer(output):
        ip, mac = match.group(1), match.group(2)
        row = output[match.start() : match.end() + 40].lower()
        if _DYNAMIC_HINT in row or _STATIC_HINT in row:
            table[ip.lower()] = mac.replace("-", ":").lower()
    return table


def parse_linux_arp(contents: str) -> dict[str, str]:
    """Parse ``/proc/net/arp`` contents (header line included)."""
    table: dict[str, str] = {}
    for line in contents.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4:
            ip, flags, mac = fields[0], fields[2], fields[3]
            if mac != "00:00:00:00:00:00" and "0x2" in flags:
                table[ip.lower()] = mac.lower()
    return table


class ArpTable:
    def __init__(self) -> None:
        import os

        self._windows = os.name == "nt"
        self._proc_file = Path("/proc/net/arp")

    def mac_map(self) -> dict[str, str]:
        if self._windows:
            return self._read_windows()
        return self._read_linux()

    def _read_windows(self) -> dict[str, str]:
        try:
            completed = subprocess.run(
                ["arp", "-a"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("arp -a failed: %s", exc)
            return {}
        return parse_windows_arp(completed.stdout or "")

    def _read_linux(self) -> dict[str, str]:
        try:
            contents = self._proc_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            logger.warning("/proc/net/arp unavailable; returning empty ARP table")
            return {}
        return parse_linux_arp(contents)
