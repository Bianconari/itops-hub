"""UI tests — logs view (offscreen, real service on a fixture file)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.application.container import AppContainer
from app.ui.views.logs_view import LogsView
from PySide6.QtCore import Qt

pytestmark = pytest.mark.ui

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def logs_view(container: AppContainer, tmp_path) -> LogsView:
    container.settings_service.update({"default_export_dir": str(tmp_path / "exports")})
    view = LogsView(container)
    yield view
    view.shutdown()
    view.deleteLater()


class TestLogsView:
    def test_analyze_populates_summary_and_top_errors(self, logs_view: LogsView, qtbot):
        logs_view.edit_path.setText(str(FIXTURES / "sample-python.log"))
        qtbot.mouseClick(logs_view.btn_analyze, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: logs_view.table.rowCount() > 0, timeout=10000)
        assert "python-logging" in logs_view.lbl_parser.text()
        assert "ERROR: 11" in logs_view.lbl_levels.text()
        assert logs_view.btn_log_export_csv.isEnabled()

    def test_missing_file_shows_error(self, logs_view: LogsView, qtbot):
        logs_view.edit_path.setText("/nonexistent/app.log")
        logs_view._on_analyze()
        qtbot.waitUntil(lambda: logs_view.lbl_error.text() != "", timeout=10000)
        assert (
            "not exist" in logs_view.lbl_error.text() or "Could not" in logs_view.lbl_error.text()
        )

    def test_export_writes_file(self, logs_view: LogsView, qtbot, tmp_path):
        logs_view.edit_path.setText(str(FIXTURES / "sample-generic.log"))
        logs_view._on_analyze()
        qtbot.waitUntil(lambda: logs_view._last_summary is not None, timeout=10000)
        logs_view._on_export("json")
        qtbot.waitUntil(lambda: logs_view.lbl_export.text().startswith("Saved:"), timeout=10000)
        assert list((tmp_path / "exports").glob("log-analysis-*.json"))
