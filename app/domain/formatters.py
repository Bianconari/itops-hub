"""Human-friendly value formatting (pure functions, UI-adjacent but I/O-free)."""

from __future__ import annotations

from datetime import UTC, datetime

_UNITS = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")


def human_bytes(size: float) -> str:
    """Format a byte count as a compact human-readable string (binary units)."""
    if size < 0:
        raise ValueError("size must be non-negative")
    value = float(size)
    for unit in _UNITS:
        if value < 1024 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} {_UNITS[-1]}"


def format_uptime(seconds: float) -> str:
    """Format an uptime duration like ``3d 4h 12m`` (days only when > 0)."""
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    minutes, _seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def as_local_string(naive_utc: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Render a naive-UTC datetime in the local timezone."""
    return naive_utc.replace(tzinfo=UTC).astimezone().strftime(fmt)


def as_local_clock(naive_utc: datetime) -> str:
    """Render a naive-UTC datetime as a local ``HH:MM:SS`` clock string."""
    return as_local_string(naive_utc, "%H:%M:%S")


def epoch_of(naive_utc: datetime) -> float:
    """Epoch seconds of a naive-UTC datetime (chart x-axis values)."""
    return naive_utc.replace(tzinfo=UTC).timestamp()
