"""Unit tests — domain validators."""

from __future__ import annotations

import ipaddress

import pytest
from app.domain.validation import (
    is_private_network,
    validate_cidr,
    validate_host,
    validate_path,
    validate_thresholds,
)


class TestValidateCidr:
    def test_valid_ipv4_with_host_bits(self):
        net = validate_cidr("192.168.1.77/24")
        assert net == ipaddress.ip_network("192.168.1.0/24")

    def test_valid_ipv4_bare_address(self):
        assert validate_cidr("10.0.0.1").prefixlen == 32

    def test_valid_ipv6(self):
        net = validate_cidr("fd00::/8")
        assert net.prefixlen == 8

    @pytest.mark.parametrize(
        "bad", ["", "   ", "not-a-network", "192.168.1.0/33", "999.1.1.0/24", "10.0.0.0/-1"]
    )
    def test_invalid(self, bad):
        with pytest.raises(ValueError):
            validate_cidr(bad)

    def test_non_string_rejected(self):
        with pytest.raises(ValueError):
            validate_cidr(123)  # type: ignore[arg-type]


class TestIsPrivateNetwork:
    @pytest.mark.parametrize(
        "cidr", ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "127.0.0.0/8", "169.254.0.0/16"]
    )
    def test_private_ranges(self, cidr):
        assert is_private_network(ipaddress.ip_network(cidr))

    def test_public_range_is_not_private(self):
        assert not is_private_network(ipaddress.ip_network("8.8.8.0/24"))


class TestValidateHost:
    def test_ipv4(self):
        assert validate_host(" 192.168.1.5 ") == "192.168.1.5"

    def test_ipv6(self):
        assert validate_host("::1") == "::1"

    def test_hostname(self):
        assert validate_host("core-switch.lan.example.com") == "core-switch.lan.example.com"

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "   ",
            "has space.example",
            "-leading-dash.example",
            "trailing-.example",
            "bad!char.example",
            "a" * 254 + ".example",
        ],
    )
    def test_invalid(self, bad):
        with pytest.raises(ValueError):
            validate_host(bad)


class TestValidatePath:
    def test_resolves_relative_to_absolute(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = validate_path("reports/x.csv")
        assert result.is_absolute()

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            validate_path("   ")

    def test_nul_rejected(self):
        with pytest.raises(ValueError):
            validate_path("evil\x00name")

    def test_must_exist(self, tmp_path):
        existing = tmp_path / "real.txt"
        existing.write_text("x")
        assert validate_path(existing, must_exist=True) == existing.resolve()
        with pytest.raises(ValueError):
            validate_path(tmp_path / "missing.txt", must_exist=True)


class TestValidateThresholds:
    def test_valid_pair(self):
        assert validate_thresholds(80.0, 90.0) == (80.0, 90.0)

    @pytest.mark.parametrize("w,c", [(0, 90), (80, 101), (-1, 90), (95, 80)])
    def test_invalid(self, w, c):
        with pytest.raises(ValueError):
            validate_thresholds(w, c)
