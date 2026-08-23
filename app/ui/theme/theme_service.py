"""Theme service — applies the current theme to the running application."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.config.settings import Theme
from app.ui.theme.tokens import DARK, LIGHT, ThemeTokens, build_qss


class ThemeService(QObject):
    """Owns the active theme and the application stylesheet."""

    themeChanged = Signal(str)  # applied theme name ("light" | "dark")

    def __init__(self, app: QApplication, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._preference: Theme = Theme.SYSTEM
        self._applied_tokens: ThemeTokens = LIGHT

    @property
    def preference(self) -> Theme:
        """The user preference (may be SYSTEM)."""
        return self._preference

    @property
    def tokens(self) -> ThemeTokens:
        """The currently applied token set."""
        return self._applied_tokens

    def apply(self, preference: Theme) -> None:
        """Resolve a preference (including SYSTEM) and apply the stylesheet."""
        self._preference = preference
        tokens = self._resolve(preference)
        self._applied_tokens = tokens
        self._app.setStyleSheet(build_qss(tokens))
        self.themeChanged.emit(tokens.name)

    def toggle(self) -> None:
        """Switch between light and dark (explicit preference)."""
        target = Theme.LIGHT if self._applied_tokens.name == "dark" else Theme.DARK
        self.apply(target)

    def _resolve(self, preference: Theme) -> ThemeTokens:
        if preference == Theme.LIGHT:
            return LIGHT
        if preference == Theme.DARK:
            return DARK
        # SYSTEM: follow the OS color scheme where Qt exposes it.
        try:
            scheme = self._app.styleHints().colorScheme()
            from PySide6.QtCore import Qt

            return DARK if scheme == Qt.ColorScheme.Dark else LIGHT
        except Exception:  # older Qt/platforms without color scheme support
            return LIGHT
