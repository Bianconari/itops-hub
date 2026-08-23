"""Sidebar navigation widget."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import __version__


class Sidebar(QFrame):
    """Left navigation rail with app identity, nav buttons, theme toggle."""

    navigate = Signal(str)  # page id
    toggleTheme = Signal()

    def __init__(self, pages: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(210)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)

        title = QLabel("ITOps Hub")
        title.setProperty("cssClass", "title")
        layout.addWidget(title)

        version = QLabel(f"v{__version__}")
        version.setProperty("cssClass", "muted")
        layout.addWidget(version)
        layout.addSpacing(14)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for page_id, title_text in pages:
            button = QPushButton(title_text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            self._group.addButton(button)
            self._buttons[page_id] = button
            button.clicked.connect(lambda _=False, pid=page_id: self.navigate.emit(pid))
            layout.addWidget(button)

        layout.addStretch(1)

        theme_button = QPushButton("Toggle theme")
        theme_button.setObjectName("themeToggle")
        theme_button.clicked.connect(self.toggleTheme.emit)
        layout.addWidget(theme_button)

    def select(self, page_id: str) -> None:
        """Mark the given page's button as active."""
        button = self._buttons.get(page_id)
        if button is not None:
            button.setChecked(True)
