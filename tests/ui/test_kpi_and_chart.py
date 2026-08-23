"""UI tests — KPI card and time-series chart widgets (offscreen)."""

from __future__ import annotations

import pytest
from app.domain.system import Level
from app.ui.theme.tokens import DARK, LIGHT
from app.ui.widgets.kpi_card import KpiCard
from app.ui.widgets.time_series_chart import TimeSeriesChart

pytestmark = pytest.mark.ui


class TestKpiCard:
    def test_initial_state(self, qtbot):
        card = KpiCard("CPU")
        qtbot.addWidget(card)
        assert card._title.text() == "CPU"
        assert card._value.text() == "—"
        assert card.property("accent_ok") is True

    def test_set_value_updates_display_and_level(self, qtbot):
        card = KpiCard("Disk")
        qtbot.addWidget(card)
        card.set_value("95 %", subtitle="max: C:\\", level=Level.CRITICAL)
        assert card._value.text() == "95 %"
        assert card._subtitle.text() == "max: C:\\"
        assert card.property("accent_critical") is True
        assert card.property("accent_ok") is False

    def test_level_switch_repolishes(self, qtbot):
        card = KpiCard("Memory")
        qtbot.addWidget(card)
        card.set_level(Level.WARNING)
        assert card.property("accent_warning") is True
        card.set_level(Level.OK)
        assert card.property("accent_warning") is False


class TestTimeSeriesChart:
    def _chart(self, qtbot) -> TimeSeriesChart:
        chart = TimeSeriesChart()
        chart.apply_theme(LIGHT)
        chart.add_series("CPU %", "series0")
        chart.add_series("Memory %", "series1")
        qtbot.addWidget(chart)
        return chart

    def test_append_and_read_points(self, qtbot):
        chart = self._chart(qtbot)
        chart.append("CPU %", 1000.0, 10.0)
        chart.append("CPU %", 1002.0, 20.0)
        xs, ys = chart.series_points("CPU %")
        assert xs == [1000.0, 1002.0]
        assert ys == [10.0, 20.0]
        assert chart.series_points("Memory %") == ([], [])

    def test_window_prunes_old_points(self, qtbot):
        chart = self._chart(qtbot)
        chart.set_window(60)
        chart.append("CPU %", 0.0, 1.0)
        chart.append("CPU %", 59.0, 2.0)
        chart.append("CPU %", 100.0, 3.0)  # drops x < 40
        xs, _ = chart.series_points("CPU %")
        assert xs == [59.0, 100.0]

    def test_clear_all(self, qtbot):
        chart = self._chart(qtbot)
        chart.append("CPU %", 10.0, 1.0)
        chart.clear_all()
        assert chart.series_points("CPU %") == ([], [])

    def test_retheme_keeps_data(self, qtbot):
        chart = self._chart(qtbot)
        chart.append("CPU %", 10.0, 1.0)
        chart.apply_theme(DARK)
        assert chart.series_points("CPU %")[0] == [10.0]
