"""Main application window: sidebar + stacked pages.

The window only routes navigation and wire signals — pages get data from
services via their constructors. Status bar shows version and data location.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from app import __version__
from app.application.container import AppContainer
from app.ui.main_window.sidebar import Sidebar
from app.ui.theme.theme_service import ThemeService
from app.ui.views.dashboard_view import DashboardView
from app.ui.views.placeholder_page import PlaceholderPage
from app.ui.views.settings_view import SettingsView
from app.ui.views.system_view import SystemView

#: (page_id, nav title, planned version or None when implemented)
_PAGES: list[tuple[str, str, str | None]] = [
    ("dashboard", "Dashboard", None),  # implemented (v0.4)
    ("system", "System", None),  # implemented (v0.4)
    ("network", "Network", "v0.5 (M4)"),
    ("monitoring", "Monitoring", "v0.6 (M5)"),
    ("logs", "Logs", "v0.7 (M6)"),
    ("backups", "Backups", "v1.2 (M9)"),
    ("reports", "Reports", "v0.8 (M7)"),
    ("alerts", "Alerts", "v0.6 (M5)"),
    ("settings", "Settings", None),  # implemented
]

_PAGE_DESCRIPTIONS: dict[str, str] = {
    "network": (
        "Authorized-network CIDR scanning with validation, concurrent checks, "
        "progress and cancellation, hostname resolution, best-effort MAC lookup, "
        "and result export. An authorization notice guards every scan."
    ),
    "monitoring": (
        "Add devices (name / host / interval / timeout) and track online, "
        "offline, and warning states with response times, failure counts, "
        "last-seen, and persisted history with time-range charts."
    ),
    "logs": (
        "Load and analyze log files through a pluggable parser registry: level "
        "counts, most repeated errors, timestamp patterns, and basic anomaly "
        "indicators — with no single hardcoded log format."
    ),
    "backups": (
        "Local backups of selected files/folders with timestamped naming, "
        "progress, verification, and explicit confirmation for destructive "
        "operations. Originals are never deleted or overwritten silently."
    ),
    "reports": (
        "Export scans, monitoring history, disk usage, log analyses, alerts, "
        "and activity to CSV, JSON, and TXT with metadata headers."
    ),
    "alerts": (
        "Alert inbox for threshold breaches and device state changes, with "
        "severity levels, acknowledgement, and history."
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
        self.setWindowTitle("ITOps Hub")
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
            else:
                page = SettingsView(container)
            self._pages[page_id] = page
            self.stack.addWidget(page)

        self.sidebar.navigate.connect(self._navigate)
        self.sidebar.toggleTheme.connect(self._theme.toggle)

        self._navigate("dashboard")

        db_note = f"v{__version__}  •  data: {container.paths.base}"
        self.statusBar().showMessage(db_note)
        self.statusBar().setSizeGripEnabled(False)

    def closeEvent(self, event) -> None:
        dashboard = self._pages.get("dashboard")
        if isinstance(dashboard, DashboardView):
            dashboard.shutdown()
        super().closeEvent(event)

    def _navigate(self, page_id: str) -> None:
        widget = self._pages.get(page_id)
        if widget is None:
            return
        self.stack.setCurrentWidget(widget)
        self.sidebar.select(page_id)
