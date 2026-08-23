"""UI tests (offscreen) — application shell, navigation, theme, settings view."""

from __future__ import annotations

import pytest
from app.application.container import AppContainer
from app.config.settings import Theme
from app.ui.main_window.main_window import MainWindow
from app.ui.theme.theme_service import ThemeService
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

pytestmark = pytest.mark.ui


@pytest.fixture
def main_window(container: AppContainer, theme_service: ThemeService):
    theme_service.apply(container.settings_service.get().theme)
    window = MainWindow(container, theme_service)
    window.show()
    yield window
    window.close()


class TestMainWindow:
    def test_builds_with_all_nav_pages(self, main_window: MainWindow):
        for page_id in (
            "dashboard",
            "system",
            "network",
            "monitoring",
            "logs",
            "backups",
            "reports",
            "alerts",
            "settings",
        ):
            assert page_id in main_window._pages

    def test_navigation_switches_pages(self, main_window: MainWindow, qtbot):
        button = main_window.sidebar._buttons["settings"]
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert main_window.stack.currentWidget() is main_window._pages["settings"]

        main_window.sidebar.navigate.emit("network")
        assert main_window.stack.currentWidget() is main_window._pages["network"]

    def test_placeholder_pages_are_labeled_honestly(self, main_window: MainWindow):
        planned = main_window._pages["network"].planned_label.text()
        assert "Planned for" in planned

    def test_dashboard_and_system_are_real_views(self, main_window: MainWindow):
        from app.ui.views.dashboard_view import DashboardView
        from app.ui.views.system_view import SystemView

        assert isinstance(main_window._pages["dashboard"], DashboardView)
        assert isinstance(main_window._pages["system"], SystemView)

    def test_theme_toggle_changes_stylesheet(self, main_window: MainWindow, qtbot):
        signal = main_window._theme.themeChanged
        with qtbot.waitSignal(signal):
            main_window._theme.toggle()
        first = main_window._theme.tokens.name
        with qtbot.waitSignal(signal):
            main_window._theme.toggle()
        second = main_window._theme.tokens.name
        assert first != second
        assert QApplication.instance().styleSheet()  # non-empty stylesheet applied app-wide


class TestSettingsView:
    def test_save_persists_theme_change(self, main_window: MainWindow, qtbot):
        view = main_window._pages["settings"]
        view.combo_theme.setCurrentIndex(view.combo_theme.findData(Theme.DARK.value))
        qtbot.mouseClick(view.btn_save, Qt.MouseButton.LeftButton)
        assert main_window._container.settings_service.get().theme is Theme.DARK

        activity = main_window._container.activity_service.recent(1)
        assert activity[0].action == "settings.updated"

    def test_invalid_thresholds_show_error_and_do_not_persist(self, main_window: MainWindow, qtbot):
        view = main_window._pages["settings"]
        view.spin_disk_warning.setValue(95)
        view.spin_disk_critical.setValue(80)
        qtbot.mouseClick(view.btn_save, Qt.MouseButton.LeftButton)
        assert "Not saved" in view.lbl_status.text()
        assert main_window._container.settings_service.get().disk.warning_percent == 80.0
