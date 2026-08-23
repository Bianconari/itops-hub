"""Unit tests — network scan service with fakes (no OS, no network)."""

from __future__ import annotations

import pytest
from app.config.settings import AppSettings
from app.domain.cancellation import CancelToken
from app.domain.events import EventBus, Topics
from app.services.activity_service import ActivityLogService
from app.services.network_scan_service import NetworkScanService
from tests.fakes import FakeActivityStore, FakeArp, FakePinger, FakeResolver


def make_service(
    settings: AppSettings | None = None,
    pinger=None,
    resolver=None,
    arp=None,
    with_activity: bool = True,
    bus: EventBus | None = None,
) -> NetworkScanService:
    settings = settings or AppSettings(scan_max_workers=8)
    activity_store = FakeActivityStore()
    activity = ActivityLogService(activity_store) if with_activity else None
    service = NetworkScanService(
        pinger or FakePinger(),
        resolver or FakeResolver(),
        arp or FakeArp(),
        lambda: settings,
        activity=activity,
        bus=bus,
    )
    service._test_activity_store = activity_store  # type: ignore[attr-defined]
    return service


class TestHappyPath:
    def test_scan_collects_sorted_results_with_enrichment(self):
        service = make_service(
            pinger=FakePinger(reachable={"10.0.0.1", "10.0.0.3"}, latency=12.5),
            resolver=FakeResolver({"10.0.0.1": "printer.lan"}),
            arp=FakeArp({"10.0.0.1": "AA:BB:CC:DD:EE:01"}),
        )
        result = service.scan("10.0.0.0/29")  # 6 usable hosts

        assert result.total == 6
        assert len(result.results) == 6
        assert result.reachable_count == 2
        assert [host.ip for host in result.results] == [
            "10.0.0.1",
            "10.0.0.2",
            "10.0.0.3",
            "10.0.0.4",
            "10.0.0.5",
            "10.0.0.6",
        ]
        by_ip = {host.ip: host for host in result.results}
        assert by_ip["10.0.0.1"].reachable is True
        assert by_ip["10.0.0.1"].response_time_ms == 12.5
        assert by_ip["10.0.0.1"].hostname == "printer.lan"
        assert by_ip["10.0.0.1"].mac == "AA:BB:CC:DD:EE:01"  # passthrough normalization
        assert by_ip["10.0.0.2"].reachable is False
        assert by_ip["10.0.0.2"].hostname is None  # offline hosts skip resolution
        assert result.cancelled is False
        assert result.duration_seconds >= 0

    def test_progress_reports_every_completion(self):
        events: list[tuple[int, int]] = []
        service = make_service()
        result = service.scan(
            "10.0.0.0/29", on_progress=lambda done, total: events.append((done, total))
        )
        assert events[0] == (1, 6)
        assert events[-1] == (len(result.results), 6)
        assert len(events) == len(result.results)

    def test_activity_and_bus_recorded(self):
        bus = EventBus()
        published = []
        bus.subscribe(Topics.SCAN_COMPLETED, published.append)
        service = make_service(bus=bus)
        service.scan("10.0.0.0/29")
        assert published and published[0].total == 6
        actions = [entry.action for entry in service._test_activity_store.entries]
        assert "scan.started" in actions and "scan.completed" in actions


class TestAuthorizationGuard:
    def test_public_range_rejected_by_default(self):
        service = make_service()
        with pytest.raises(ValueError, match="not a private range"):
            service.scan("8.8.8.0/24")

    def test_public_range_allowed_with_override(self):
        settings = AppSettings(scan_max_workers=8, scan_max_hosts=64)
        service = make_service(settings=settings)
        result = service.scan("8.8.8.0/28", authorized_override=True)  # 14 hosts
        assert result.total == 14

    def test_guard_disabled_by_setting(self):
        settings = AppSettings(scan_private_only=False)
        service = make_service(settings=settings)
        result = service.scan("8.8.8.0/28")
        assert result.total == 14


class TestInputValidation:
    @pytest.mark.parametrize("bad", ["", "banana", "10.0.0.0/33", "300.1.1.0/24"])
    def test_invalid_cidr_rejected(self, bad):
        with pytest.raises(ValueError):
            make_service().scan(bad)

    def test_host_cap_enforced(self):
        settings = AppSettings(scan_max_hosts=16)
        service = make_service(settings=settings)
        with pytest.raises(ValueError, match="above the scan limit"):
            service.scan("10.0.0.0/24")  # 254 hosts > 16

    def test_tiny_networks_supported(self):
        result = make_service().scan("10.0.0.5/32")
        assert result.total == 1
        assert result.results[0].ip == "10.0.0.5"


class TestCancellation:
    def test_cancel_mid_scan_returns_partial_results(self):
        pinger = FakePinger(reachable={"10.0.0.1"}, delay=0.05)
        service = make_service(settings=AppSettings(scan_max_workers=2), pinger=pinger)
        token = CancelToken()

        def on_progress(done: int, total: int) -> None:
            if done >= 2:
                token.cancel()

        result = service.scan("10.0.0.0/28", token=token, on_progress=on_progress)  # 14 hosts
        assert result.cancelled is True
        assert len(result.results) < 14
        actions = [entry.action for entry in service._test_activity_store.entries]
        assert "scan.cancelled" in actions

    def test_cancelled_token_before_start_raises(self):
        token = CancelToken()
        token.cancel()
        from app.domain.cancellation import OperationCancelled

        with pytest.raises(OperationCancelled):
            make_service().scan("10.0.0.0/29", token=token)
