"""Toast notifications — in-app, stacked bottom-right, severity-colored.

Presentation only: severity mapping, stacking, and auto-dismiss live here;
*when* to notify is decided by MainWindow wiring (settings-gated). Styling
comes from the central theme tokens (QSS property selectors), so toasts
follow light/dark automatically.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.domain.formatters import as_local_string
from app.domain.time_utils import utc_now
from app.ui.theme.theme_service import ThemeService

logger = logging.getLogger(__name__)

_MARGIN = 16
_SPACING = 8
_MAX_VISIBLE = 4


class ToastWidget(QFrame):
    """One toast card; click anywhere to open the Alerts page."""

    clicked = Signal()
    closed = Signal()  # emitted on hide (close() only hides child widgets)

    def __init__(self, severity: str, title: str, message: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._closing_emitted = False
        self.setObjectName("toast")
        self.setProperty("severity", severity)
        self.setFixedWidth(360)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        header = QHBoxLayout()
        self._title = QLabel(title)
        self._title.setObjectName("toastTitle")
        header.addWidget(self._title)
        header.addStretch(1)
        stamp = QLabel(as_local_string(utc_now(), "%H:%M:%S"))
        stamp.setProperty("cssClass", "muted")
        header.addWidget(stamp)
        layout.addLayout(header)

        body = QLabel(message)
        body.setWordWrap(True)
        layout.addWidget(body)
        self.adjustSize()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.clicked.emit()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if not self._closing_emitted:
            self._closing_emitted = True
            self.closed.emit()


class ToastManager(QObject):
    """Owns the visible toasts of one window (main-thread only)."""

    activated = Signal()  # the user clicked a toast -> open Alerts

    def __init__(self, window: QWidget, theme: ThemeService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window = window
        self._theme = theme
        self._toasts: list[ToastWidget] = []

    # ------------------------------------------------------------------
    def show_toast(
        self,
        severity: str,
        title: str,
        message: str,
        *,
        duration_ms: int | None = None,
    ) -> ToastWidget | None:
        """Show one toast; oldest is dropped beyond the visible maximum."""
        while len(self._toasts) >= _MAX_VISIBLE:
            self._toasts[0].close()
        toast = ToastWidget(severity, title, message, self._window)
        toast.clicked.connect(self._on_clicked)
        toast.closed.connect(lambda: self._forget(toast))
        self._toasts.append(toast)
        self._relayout()
        toast.show()
        if duration_ms is None:
            duration_ms = 10_000 if severity == "critical" else 6_000
        QTimer.singleShot(duration_ms, toast.close)
        return toast

    @property
    def active_count(self) -> int:
        return len(self._toasts)

    def _on_clicked(self) -> None:
        self.activated.emit()

    def _forget(self, toast: ToastWidget) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
            toast.deleteLater()
            self._relayout()

    def _relayout(self) -> None:
        """Stack toasts bottom-right of the window, newest at the bottom."""
        y = self._window.height() - _MARGIN
        for toast in reversed(self._toasts):
            y -= toast.height()
            toast.move(self._window.width() - toast.width() - _MARGIN, max(y, _MARGIN))
            toast.raise_()
            y -= _SPACING
