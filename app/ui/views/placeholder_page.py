"""Honest placeholder page for modules that land in later milestones.

The Master Spec (§44) forbids fake functionality: these pages state exactly
what is planned and when it arrives — no mock widgets, no dummy buttons.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPage(QWidget):
    def __init__(
        self,
        title: str,
        planned_version: str,
        description: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        heading = QLabel(title)
        heading.setProperty("cssClass", "title")
        layout.addWidget(heading)

        planned = QLabel(f"Planned for {planned_version}")
        planned.setProperty("cssClass", "warning")
        layout.addWidget(planned)
        self.planned_label = planned

        layout.addSpacing(8)
        body = QLabel(description)
        body.setProperty("cssClass", "muted")
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)
