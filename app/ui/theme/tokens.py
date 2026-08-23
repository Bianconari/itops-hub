"""Design tokens and QSS generation for light/dark themes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ThemeTokens:
    """Color palette for one theme. Single source of truth for all styling."""

    name: str
    window_bg: str
    surface_bg: str
    surface_hover: str
    border: str
    text_primary: str
    text_muted: str
    primary: str
    primary_hover: str
    primary_text: str
    success: str
    warning: str
    danger: str
    chart_series: tuple[str, ...] = field(default_factory=tuple)


LIGHT = ThemeTokens(
    name="light",
    window_bg="#f4f6f8",
    surface_bg="#ffffff",
    surface_hover="#e9edf1",
    border="#d4dae0",
    text_primary="#1c2733",
    text_muted="#5c6b7a",
    primary="#2563eb",
    primary_hover="#1d4ed8",
    primary_text="#ffffff",
    success="#16a34a",
    warning="#d97706",
    danger="#dc2626",
    chart_series=("#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#0891b2"),
)

DARK = ThemeTokens(
    name="dark",
    window_bg="#14181d",
    surface_bg="#1d232b",
    surface_hover="#273039",
    border="#333d48",
    text_primary="#e8edf2",
    text_muted="#9aa8b5",
    primary="#3b82f6",
    primary_hover="#60a5fa",
    primary_text="#ffffff",
    success="#22c55e",
    warning="#f59e0b",
    danger="#ef4444",
    chart_series=("#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a78bfa", "#22d3ee"),
)


def build_qss(t: ThemeTokens) -> str:
    """Render the application-wide stylesheet from tokens.

    Centralized on purpose: individual widgets never set ad-hoc colors.
    """
    return f"""
* {{
    font-family: "Segoe UI", "Inter", system-ui, sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {t.window_bg}; }}
QWidget {{ color: {t.text_primary}; }}
QLabel {{ background: transparent; }}
QLabel[cssClass="title"] {{ font-size: 20px; font-weight: 600; }}
QLabel[cssClass="subtitle"] {{ font-size: 15px; font-weight: 600; }}
QLabel[cssClass="muted"] {{ color: {t.text_muted}; }}
QLabel[cssClass="success"] {{ color: {t.success}; font-weight: 600; }}
QLabel[cssClass="warning"] {{ color: {t.warning}; font-weight: 600; }}
QLabel[cssClass="danger"] {{ color: {t.danger}; font-weight: 600; }}

QFrame#sidebar {{ background: {t.surface_bg}; border-right: 1px solid {t.border}; }}
QPushButton#navButton {{
    text-align: left; padding: 9px 14px; border: none; border-radius: 8px;
    color: {t.text_muted}; background: transparent; font-weight: 500;
}}
QPushButton#navButton:hover {{ background: {t.surface_hover}; color: {t.text_primary}; }}
QPushButton#navButton:checked {{ background: {t.primary}; color: {t.primary_text}; }}

QFrame#card, QFrame#page {{
    background: {t.surface_bg}; border: 1px solid {t.border}; border-radius: 10px;
}}

QPushButton {{
    background: {t.surface_bg}; color: {t.text_primary};
    border: 1px solid {t.border}; border-radius: 6px; padding: 6px 14px;
}}
QPushButton:hover {{ background: {t.surface_hover}; }}
QPushButton:disabled {{ color: {t.text_muted}; background: {t.window_bg}; }}
QPushButton[cssClass="primary"] {{
    background: {t.primary}; color: {t.primary_text}; border: none; font-weight: 600;
}}
QPushButton[cssClass="primary"]:hover {{ background: {t.primary_hover}; }}
QPushButton[cssClass="primary"]:disabled {{ background: {t.border}; color: {t.primary_text}; }}

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {t.window_bg}; color: {t.text_primary};
    border: 1px solid {t.border}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {t.primary}; selection-color: {t.primary_text};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {t.primary};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {t.surface_bg}; color: {t.text_primary};
    border: 1px solid {t.border}; selection-background-color: {t.primary_hover};
}}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {t.border}; background: {t.window_bg};
}}
QCheckBox::indicator:checked {{ background: {t.primary}; border-color: {t.primary}; }}

QTableWidget {{
    background: {t.surface_bg}; border: 1px solid {t.border}; border-radius: 6px;
    gridline-color: {t.border}; alternate-background-color: {t.surface_hover};
}}
QTableWidget::item {{ padding: 4px 8px; }}
QTableWidget::item:selected {{ background: {t.primary}; color: {t.primary_text}; }}
QHeaderView::section {{
    background: {t.window_bg}; color: {t.text_muted}; font-weight: 600;
    border: none; border-bottom: 1px solid {t.border}; padding: 6px 8px;
}}

QProgressBar {{
    background: {t.window_bg}; border: 1px solid {t.border};
    border-radius: 6px; text-align: center; color: {t.text_primary}; height: 14px;
}}
QProgressBar::chunk {{ background: {t.primary}; border-radius: 6px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t.text_muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QStatusBar {{ color: {t.text_muted}; border-top: 1px solid {t.border}; }}
QToolTip {{
    background: {t.surface_bg}; color: {t.text_primary};
    border: 1px solid {t.border}; padding: 4px;
}}
QMessageBox {{ background: {t.surface_bg}; }}
"""
