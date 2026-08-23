"""UI tests — system view: load, populate, error path (offscreen)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.application.container import AppContainer
from app.services.system_service import SystemInfoService
from app.ui.theme.theme_service import ThemeService
from app.ui.views.system_view import SystemView
from tests.fakes import FakeSystemSource

pytestmark = pytest.mark.ui


@pytest.fixture
def system_view(container: AppContainer, theme_service: ThemeService) -> SystemView:
    view = SystemView(container, theme_service)
    yield view
    view.shutdown()
    view.deleteLater()


class TestSystemViewLoad:
    def test_populates_from_real_source(self, system_view: SystemView, qtbot):
        qtbot.waitUntil(lambda: system_view.lbl_hostname.text() not in ("", "…"), timeout=15000)
        assert system_view.table_drives.rowCount() >= 1
        assert system_view.table_adapters.rowCount() >= 1
        assert system_view.btn_refresh.isEnabled()
        assert not system_view.progress.isVisibleTo(system_view)

    def test_refresh_recollects(self, system_view: SystemView, qtbot):
        qtbot.waitUntil(lambda: system_view.lbl_hostname.text() not in ("", "…"), timeout=15000)
        system_view.refresh()
        qtbot.waitUntil(lambda: system_view.btn_refresh.isEnabled(), timeout=15000)
        assert system_view.lbl_hostname.text() != "…"


class TestSystemViewError:
    def test_failure_shows_error_and_reenables(self, container: AppContainer, qtbot, theme_service):
        failing = SystemInfoService(
            FakeSystemSource(error=RuntimeError("adapter unavailable")),
            container.settings_service.get,
        )
        stub_container = SimpleNamespace(
            system_service=failing, settings_service=container.settings_service
        )
        view = SystemView(stub_container, theme_service)  # type: ignore[arg-type]
        qtbot.addWidget(view)
        qtbot.waitUntil(lambda: "adapter unavailable" in view.lbl_error.text(), timeout=10000)
        assert view.btn_refresh.isEnabled()
        assert view.lbl_hostname.text() == "…"
