"""KPI card — reusable metric tile with threshold-colored accent."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.domain.system import Level


class KpiCard(QFrame):
    """A titled metric tile: big value, subtitle, severity-colored accent.

    The widget contains presentation only; callers pass already-formatted
    strings and a computed ``Level`` (business classification stays outside).
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setMinimumHeight(112)
        self.setFixedWidth(210)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(2)

        self._title = QLabel(title)
        self._title.setProperty("cssClass", "muted")
        layout.addWidget(self._title)

        self._value = QLabel("—")
        self._value.setObjectName("kpiValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(self._value)

        self._subtitle = QLabel("")
        self._subtitle.setProperty("cssClass", "muted")
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)
        layout.addStretch(1)

        self.set_level(Level.OK)

    def set_value(self, value: str, subtitle: str = "", level: Level = Level.OK) -> None:
        """Update the displayed value, subtitle, and severity accent."""
        self._value.setText(value)
        self._subtitle.setText(subtitle)
        self.set_level(level)

    def set_level(self, level: Level) -> None:
        for role in ("ok", "warning", "critical"):
            self.setProperty(f"accent_{role}", role == level.value)
        self._repolish()

    def _repolish(self) -> None:
        for widget in (self, self._value):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
