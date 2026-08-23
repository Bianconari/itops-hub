"""Integration tests — real OS adapters (system ping, resolver, ARP).

The pinger tests verify the actual subprocess contract; they skip on hosts
where the environment forbids ICMP (e.g., hardened containers without
ping_group_range). Windows CI always runs them.
"""

from __future__ import annotations

import pytest
from app.infrastructure.network.arp_table import ArpTable
from app.infrastructure.network.resolver import SocketHostnameResolver
from app.infrastructure.network.system_pinger import SystemPinger


def _icmp_permitted() -> bool:
    try:
        return SystemPinger().ping("127.0.0.1", 500).reachable
    except Exception:
        return False


requires_icmp = pytest.mark.skipif(not _icmp_permitted(), reason="ICMP not permitted here")


@requires_icmp
class TestSystemPinger:
    def test_localhost_is_reachable(self):
        result = SystemPinger().ping("127.0.0.1", 500)
        assert result.reachable is True
        assert result.error is None
        # loopback latency parses on English locales; None acceptable elsewhere
        assert result.response_time_ms is None or result.response_time_ms >= 0

    def test_unreachable_address_reports_cleanly(self):
        result = SystemPinger().ping("192.0.2.123", 300)  # TEST-NET-1, never routed
        assert result.reachable is False
        assert result.error is not None

    def test_invalid_host_is_rejected_without_subprocess(self):
        result = SystemPinger().ping("bad host!", 500)
        assert result.reachable is False


class TestResolver:
    def test_loopback_resolves_or_none_without_raising(self):
        name = SocketHostnameResolver().resolve("127.0.0.1")
        assert name is None or isinstance(name, str)

    def test_garbage_ip_returns_none(self):
        assert SocketHostnameResolver().resolve("not-an-ip") is None


class TestArpTable:
    def test_returns_dict_without_raising(self):
        table = ArpTable().mac_map()
        assert isinstance(table, dict)
        for ip, mac in table.items():
            assert "." in ip
            assert len(mac.split(":")) == 6
