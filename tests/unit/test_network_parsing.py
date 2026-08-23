"""Unit tests — ping output and ARP table parsing (pure functions)."""

from __future__ import annotations

from app.infrastructure.network.arp_table import parse_linux_arp, parse_windows_arp
from app.infrastructure.network.system_pinger import is_reachable, parse_latency_ms


class TestParseLatency:
    def test_windows_english(self):
        assert parse_latency_ms("Reply from 10.0.0.1: bytes=32 time=12ms TTL=64") == 12.0

    def test_windows_below_one_ms(self):
        assert parse_latency_ms("Reply from 10.0.0.1: bytes=32 time<1ms TTL=64") == 1.0

    def test_linux_style(self):
        assert parse_latency_ms("64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=0.045 ms") == 0.045

    def test_localized_output_yields_none(self):
        assert parse_latency_ms("64 بایت از 10.0.0.1: ttl=64 زمان=0.5") is None

    def test_empty(self):
        assert parse_latency_ms("") is None


class TestIsReachable:
    def test_windows_rc0_with_ttl(self):
        assert is_reachable(0, "Reply from 10.0.0.1: bytes=32 time=1ms TTL=127", windows=True)

    def test_windows_rc0_destination_unreachable_is_not_reachable(self):
        assert not is_reachable(
            0, "Reply from 10.0.0.1: Destination host unreachable.", windows=True
        )

    def test_windows_nonzero_rc(self):
        assert not is_reachable(1, "Request timed out.", windows=True)

    def test_posix_rc0_is_reliable(self):
        assert is_reachable(
            0, "64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=0.1 ms", windows=False
        )

    def test_posix_nonzero_rc(self):
        assert not is_reachable(2, "", windows=False)


class TestWindowsArpParsing:
    SAMPLE = (
        "\nInterface: 192.168.1.10 --- 0x4\n"
        "  Internet Address      Physical Address      Type\n"
        "  192.168.1.1           a8-6b-ad-11-22-33     dynamic\n"
        "  192.168.1.50          00-1a-2b-3c-4d-5e     static\n"
        "  224.0.0.22            01-00-5e-00-00-16     static\n"
    )

    def test_parses_unicast_entries_normalized(self):
        table = parse_windows_arp(self.SAMPLE)
        assert table == {
            "192.168.1.1": "a8:6b:ad:11:22:33",
            "192.168.1.50": "00:1a:2b:3c:4d:5e",
            "224.0.0.22": "01:00:5e:00:00:16",
        }

    def test_garbage_yields_empty(self):
        assert parse_windows_arp("no table here") == {}


class TestLinuxArpParsing:
    SAMPLE = (
        "IP address       HW type     Flags       HW address            Mask     Device\n"
        "10.0.0.1         0x1         0x2         aa:bb:cc:dd:ee:ff     *        eth0\n"
        "10.0.0.2         0x1         0x0         00:00:00:00:00:00     *        eth0\n"
    )

    def test_parses_complete_entries_only(self):
        table = parse_linux_arp(self.SAMPLE)
        assert table == {"10.0.0.1": "aa:bb:cc:dd:ee:ff"}

    def test_empty(self):
        assert parse_linux_arp("") == {}
