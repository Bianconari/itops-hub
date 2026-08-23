"""Reverse-DNS hostname resolver (implements ``HostnameResolver``).

``socket.gethostbyaddr`` has no timeout parameter; callers run it inside
worker threads (the scan service does), so blocking is contained. All
failures map to ``None`` — an unresolved host is normal on most LANs.
"""

from __future__ import annotations

import logging
import socket

from app.domain.validation import validate_host

logger = logging.getLogger(__name__)


class SocketHostnameResolver:
    def resolve(self, ip: str) -> str | None:
        try:
            validate_host(ip)
        except ValueError:
            return None
        try:
            name, _aliases, _addresses = socket.gethostbyaddr(ip)
        except (socket.herror, socket.gaierror, OSError):
            return None
        return name or None
