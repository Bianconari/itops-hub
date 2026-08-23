"""Input validation for domain values.

All validators raise ``ValueError`` with a user-presentable message; they are
pure functions with no I/O so they can be used from any layer and tested
trivially.
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path

_HOSTNAME_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def validate_cidr(value: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    """Parse and validate a CIDR network string (host bits allowed, e.g. /24)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Network must be a non-empty CIDR string, e.g. 192.168.1.0/24")
    try:
        return ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise ValueError(f"Invalid network '{value.strip()}': {exc}") from exc


def is_private_network(network: ipaddress.IPv4Network | ipaddress.IPv6Network) -> bool:
    """True for ranges safe to scan by default (RFC1918, loopback, link-local).

    Anything else (public/internet space) requires an explicit, informed
    override in the UI — the user must only scan networks they administer.
    """
    return network.is_private or network.is_loopback or network.is_link_local


def validate_host(value: str) -> str:
    """Validate an IPv4/IPv6 address or DNS hostname; returns trimmed value."""
    if not isinstance(value, str):
        raise ValueError("Host must be a string")
    host = value.strip()
    if not host:
        raise ValueError("Host must not be empty")
    if len(host) > 253:
        raise ValueError("Host must be at most 253 characters")
    if any(ch.isspace() for ch in host):
        raise ValueError("Host must not contain whitespace")
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass  # not an IP; validate as DNS name below
    labels = host.split(".")
    for label in labels:
        if not _HOSTNAME_LABEL.match(label):
            raise ValueError(f"Invalid hostname '{value}': bad label '{label}'")
    return host


def validate_path(value: str | Path, *, must_exist: bool = False) -> Path:
    """Validate and normalize a filesystem path (never touches the network)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("Path must not be empty")
    text = str(value)
    if "\x00" in text:
        raise ValueError("Path must not contain NUL bytes")
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if must_exist and not path.exists():
        raise ValueError(f"Path does not exist: {path}")
    return path


def validate_thresholds(warning_percent: float, critical_percent: float) -> tuple[float, float]:
    """Validate an ordered warning/critical threshold pair (percent values)."""
    for name, value in (("warning", warning_percent), ("critical", critical_percent)):
        if not 0 < value <= 100:
            raise ValueError(f"{name} threshold must be in (0, 100], got {value}")
    if warning_percent > critical_percent:
        raise ValueError("warning threshold must be less than or equal to critical threshold")
    return warning_percent, critical_percent
