"""Time-series chart — PyQtGraph wrapper themed from central tokens.

Encapsulates all pyqtgraph usage behind a small API so views never touch
the plotting library directly, and restyling on theme switch is one call.
Call ``apply_theme()`` before ``add_series()`` so pens resolve token colors.
"""

from __future__ import annotations

import time
from collections import deque

import pyqtgraph as pg

from app.ui.theme.tokens import ThemeTokens


class _ClockAxis(pg.AxisItem):
    """Bottom axis rendering epoch seconds as local HH:MM:SS."""

    def tickStrings(self, values, scale, spacing):
        return [time.strftime("%H:%M:%S", time.localtime(value)) for value in values]


class TimeSeriesChart(pg.PlotWidget):
    """Rolling-window multi-series line chart with legend and y-range."""

    def __init__(self, y_range: tuple[float, float] = (0, 100), parent=None) -> None:
        pg.setConfigOptions(antialias=True)
        super().__init__(parent, axisItems={"bottom": _ClockAxis(orientation="bottom")})
        self._y_range = y_range
        self._window_seconds: float = 600.0
        self._series: dict[str, dict] = {}
        self._token: ThemeTokens | None = None

        self.showGrid(x=False, y=True, alpha=0.15)
        self.addLegend(offset=(8, 8))
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()

    # ------------------------------------------------------------------
    def add_series(self, name: str, color_role: str = "series0") -> None:
        """Register a plot line; ``color_role`` is a token key (series0..5,
        warning, danger, success, primary...)."""
        assert self._token is not None, "apply_theme() must be called first"
        series: dict = {"role": color_role, "x": deque(), "y": deque()}
        series["curve"] = self.plot(pen=self._pen_for_role(color_role), name=name)
        self._series[name] = series

    def set_window(self, seconds: float) -> None:
        """Rolling time window shown on the x-axis."""
        self._window_seconds = max(10.0, seconds)

    def append(self, name: str, x_epoch: float, y: float) -> None:
        """Append one point to a series and refresh the view."""
        series = self._series[name]
        series["x"].append(x_epoch)
        series["y"].append(y)
        cutoff = x_epoch - self._window_seconds
        while series["x"] and series["x"][0] < cutoff:
            series["x"].popleft()
            series["y"].popleft()
        series["curve"].setData(list(series["x"]), list(series["y"]))
        self._update_range(x_epoch)

    def clear_all(self) -> None:
        for series in self._series.values():
            series["x"].clear()
            series["y"].clear()
            series["curve"].setData([], [])

    def series_points(self, name: str) -> tuple[list[float], list[float]]:
        """Stored (x, y) points for a series (used by tests and history)."""
        series = self._series[name]
        return list(series["x"]), list(series["y"])

    # ------------------------------------------------------------------
    def apply_theme(self, tokens: ThemeTokens) -> None:
        """(Re)color background, axes, and series from theme tokens."""
        self._token = tokens
        self.setBackground(tokens.surface_bg)
        for axis_name in ("left", "bottom"):
            axis = self.getAxis(axis_name)
            axis.setPen(pg.mkPen(tokens.border))
            axis.setTextPen(pg.mkPen(tokens.text_muted))
        for series in self._series.values():
            series["curve"].setPen(self._pen_for_role(series["role"]))

    # Internals ----------------------------------------------------------
    def _pen_for_role(self, role: str):
        assert self._token is not None, "apply_theme() must be called first"
        if role.startswith("series") and role[6:].isdigit():
            index = int(role[6:]) % len(self._token.chart_series)
            color = self._token.chart_series[index]
        else:
            color = getattr(self._token, role, self._token.primary)
        return pg.mkPen(color, width=2)

    def _update_range(self, newest_x: float) -> None:
        self.setXRange(newest_x - self._window_seconds, newest_x, padding=0)
        self.setYRange(*self._y_range, padding=0)
