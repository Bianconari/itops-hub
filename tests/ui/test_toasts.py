"""UI tests — toast notifications and the event-bus bridge (offscreen)."""

from __future__ import annotations

import threading

import pytest
from app.application.container import AppContainer
from app.ui.main_window.main_window import MainWindow
from app.ui.theme.theme_service import ThemeService
from PySide6.QtCore import Qt

pytestmark = pytest.mark.ui


@pytest.fixture
def main_window(container: AppContainer, theme_service: ThemeService) -> MainWindow:
    theme_service.apply(container.settings_service.get().theme)
    window = MainWindow(container, theme_service)
    window.show()
    yield window
    window.close()


def raise_alert(container: AppContainer, message: str = "disk usage 92%") -> None:
    assert container.alert_service is not None
    container.alert_service.raise_alert("disk.threshold", "critical", "C:\\", message)


class TestToasts:
    def test_alert_from_worker_thread_shows_toast(self, container, main_window, qtbot):
        # alerts are raised on worker threads (scheduler/monitor pools)
        thread = threading.Thread(target=raise_alert, args=(container,))
        thread.start()
        thread.join()
        qtbot.waitUntil(lambda: main_window._toasts.active_count == 1, timeout=5000)
        toast = main_window._toasts._toasts[0]
        texts = [
            label.text()
            for label in toast.findChildren(object)
            if hasattr(label, "text") and callable(label.text)
        ]
        assert any("disk usage 92%" in text for text in texts)

    def test_click_navigates_to_alerts(self, container, main_window, qtbot):
        raise_alert(container, "click me")
        qtbot.waitUntil(lambda: main_window._toasts.active_count == 1, timeout=5000)
        toast = main_window._toasts._toasts[0]
        qtbot.mouseClick(toast, Qt.MouseButton.LeftButton)
        assert main_window.stack.currentWidget() is main_window._pages["alerts"]

    def test_in_app_disabled_hides_toasts(self, container, main_window, qtbot):
        container.settings_service.update({"notifications": {"in_app": False, "desktop": False}})
        raise_alert(container, "silent")
        qtbot.wait(400)
        assert main_window._toasts.active_count == 0

    def test_toast_auto_dismisses(self, container, main_window, qtbot):
        main_window._toasts.show_toast("info", "Title", "short-lived", duration_ms=150)
        assert main_window._toasts.active_count == 1
        qtbot.waitUntil(lambda: main_window._toasts.active_count == 0, timeout=5000)

    def test_max_four_visible(self, container, main_window):
        for index in range(6):
            main_window._toasts.show_toast("info", f"T{index}", "m", duration_ms=60_000)
        assert main_window._toasts.active_count == 4

    def test_tray_handled_gracefully(self, main_window):
        # offscreen CI has no system tray — must be None and not crash
        assert main_window._tray is None or main_window._tray.isVisible()
