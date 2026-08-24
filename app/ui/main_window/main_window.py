"""Main application window: sidebar + stacked pages.

The window only routes navigation and wire signals — pages get data from
services via their constructors. Status bar shows version and data location.
"""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QSystemTrayIcon,
    QWidget,
)

from app import __version__
from app.application.container import AppContainer
from app.ui.main_window.sidebar import Sidebar
from app.ui.resources import resource_path
from app.ui.theme.theme_service import ThemeService
from app.ui.views.alerts_view import AlertsView
from app.ui.views.backup_view import BackupView
from app.ui.views.dashboard_view import DashboardView
from app.ui.views.logs_view import LogsView
from app.ui.views.monitoring_view import MonitoringView
from app.ui.views.network_view import NetworkView
from app.ui.views.placeholder_page import PlaceholderPage
from app.ui.views.reports_view import ReportsView
from app.ui.views.settings_view import SettingsView
from app.ui.views.system_view import SystemView
from app.ui.widgets.toast import ToastManager
from app.ui.workers.event_bridge import EventBusBridge

#: (page_id, nav title, planned version or None when implemented)
_PAGES: list[tuple[str, str, str | None]] = [
    ("dashboard", "Dashboard", None),  # implemented (v0.4)
    ("system", "System", None),  # implemented (v0.4)
    ("network", "Network", None),  # implemented (v0.5)
    ("monitoring", "Monitoring", None),  # implemented (v0.6)
    ("logs", "Logs", None),  # implemented (v0.7)
    ("backups", "Backups", None),  # implemented (v1.2)
    ("reports", "Reports", None),  # implemented (v0.8)
    ("alerts", "Alerts", None),  # implemented (v0.6)
    ("settings", "Settings", None),  # implemented
]

_PAGE_DESCRIPTIONS: dict[str, str] = {
    "backups": (
        "Local backups of selected files/folders with timestamped naming, "
        "progress, verification, and explicit confirmation for destructive "
        "operations. Originals are never deleted or overwritten silently."
    ),
    "reports": (
        "Export scans, monitoring history, disk usage, log analyses, alerts, "
        "and activity to CSV, JSON, and TXT with metadata headers."
    ),
}


class MainWindow(QMainWindow):
    def __init__(
        self,
        container: AppContainer,
        theme_service: ThemeService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._container = container
        self._theme = theme_service
        self.setWindowTitle(f"ITOps Hub — v{__version__}")
        self.resize(1180, 760)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        self.sidebar = Sidebar([(pid, title) for pid, title, _ in _PAGES])
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)

        self._pages: dict[str, QWidget] = {}
        for page_id, title, planned in _PAGES:
            if planned is not None:
                page: QWidget = PlaceholderPage(title, planned, _PAGE_DESCRIPTIONS[page_id])
            elif page_id == "dashboard":
                page = DashboardView(container, theme_service)
            elif page_id == "system":
                page = SystemView(container, theme_service)
            elif page_id == "network":
                page = NetworkView(container)
            elif page_id == "monitoring":
                page = MonitoringView(container, theme_service)
            elif page_id == "alerts":
                page = AlertsView(container, theme_service)
            elif page_id == "logs":
                page = LogsView(container)
            elif page_id == "reports":
                page = ReportsView(container)
            elif page_id == "backups":
                page = BackupView(container)
            else:
                page = SettingsView(container)
            self._pages[page_id] = page
            self.stack.addWidget(page)

        self.sidebar.navigate.connect(self._navigate)
        self.sidebar.toggleTheme.connect(self._theme.toggle)

        self._navigate("dashboard")

        # Notifications (v1.6): in-app toasts + system-tray messages.
        self._toasts = ToastManager(self, theme_service)
        self._toasts.activated.connect(lambda: self._navigate("alerts"))
        self._event_bridge = EventBusBridge(container.bus)
        self._event_bridge.alert_raised.connect(self._on_alert_raised)
        self._tray = self._build_tray()

        db_note = f"v{__version__}  •  data: {container.paths.base}"
        self.statusBar().showMessage(db_note)
        self.statusBar().setSizeGripEnabled(False)

    def _build_tray(self) -> QSystemTrayIcon | None:
        """System tray icon with desktop notifications (if the OS provides one)."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(QIcon(str(resource_path("icons", "app.ico"))), self)
        tray.setToolTip(f"ITOps Hub v{__version__}")
        tray.activated.connect(
            lambda reason: (
                self.showNormal()
                if reason == QSystemTrayIcon.ActivationReason.DoubleClick
                else None
            )
        )
        tray.messageClicked.connect(lambda: self._navigate("alerts"))
        tray.show()
        return tray

    def _on_alert_raised(self, alert: object) -> None:
        """Show toast + tray message for a raised alert (settings-gated)."""
        settings = self._container.settings_service.get()
        severity = alert.severity.value  # type: ignore[attr-defined]
        title = f"Alert - {alert.type}"  # type: ignore[attr-defined]
        message = alert.message  # type: ignore[attr-defined]
        if settings.notifications.in_app:
            self._toasts.show_toast(severity, title, message)
        if (
            settings.notifications.desktop
            and self._tray is not None
            and severity in ("warning", "critical")
        ):
            icon = {
                "warning": QSystemTrayIcon.MessageIcon.Warning,
                "critical": QSystemTrayIcon.MessageIcon.Critical,
            }[severity]
            self._tray.showMessage(title, message, icon, 8000)

    def closeEvent(self, event) -> None:
        self._event_bridge.detach()
        if self._tray is not None:
            self._tray.hide()
        for page_id, shutdown_owner in (
            ("dashboard", DashboardView),
            ("network", NetworkView),
            ("monitoring", MonitoringView),
            ("logs", LogsView),
            ("reports", ReportsView),
            ("backups", BackupView),
        ):
            page = self._pages.get(page_id)
            if isinstance(page, shutdown_owner):
                page.shutdown()
        super().closeEvent(event)

    def _navigate(self, page_id: str) -> None:
        widget = self._pages.get(page_id)
        if widget is None:
            return
        self.stack.setCurrentWidget(widget)
        self.sidebar.select(page_id)
