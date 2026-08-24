"""Export service — writes result sets to CSV / JSON / TXT with metadata.

Shared by every module that exports (network scanner now; monitoring, disk,
logs, and alerts reports in v0.6-v0.8). Files are timestamped and never
overwrite existing ones (a counter suffix is appended instead).
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from app import __version__
from app.config.paths import AppPaths
from app.config.settings import AppSettings
from app.domain.loganalysis import LogSummary
from app.domain.network import ScanResult
from app.domain.time_utils import utc_now
from app.services.activity_service import ActivityLogService

logger = logging.getLogger(__name__)

ExportFormat = Literal["csv", "json", "txt", "pdf"]

_SCAN_HEADERS = ("ip", "reachable", "response_time_ms", "hostname", "mac", "checked_at")


class ExportError(RuntimeError):
    """Raised when an export cannot be written (bad path, permissions...)."""


class ExportService:
    def __init__(
        self,
        settings_getter: Callable[[], AppSettings],
        paths: AppPaths,
        activity: ActivityLogService | None = None,
    ) -> None:
        self._settings_getter = settings_getter
        self._paths = paths
        self._activity = activity

    # ------------------------------------------------------------ scan
    def export_scan(self, result: ScanResult, fmt: ExportFormat) -> Path:
        """Write one network scan result set; returns the created file path."""
        rows = [
            {
                "ip": host.ip,
                "reachable": "yes" if host.reachable else "no",
                "response_time_ms": (
                    f"{host.response_time_ms:.1f}" if host.response_time_ms is not None else ""
                ),
                "hostname": host.hostname or "",
                "mac": host.mac or "",
                "checked_at": host.timestamp.isoformat(),
            }
            for host in result.results
        ]
        metadata = {
            "report": "network-scan",
            "network": result.network,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat(),
            "duration_seconds": round(result.duration_seconds, 3),
            "addresses_total": result.total,
            "addresses_checked": len(result.results),
            "reachable": result.reachable_count,
            "cancelled": result.cancelled,
        }
        return self._write("network-scan", fmt, metadata, _SCAN_HEADERS, rows)

    # ------------------------------------------------------------ logs
    def export_log_analysis(self, summary: LogSummary, fmt: ExportFormat) -> Path:
        """Write a log-analysis summary report."""
        headers = ("level", "count")
        rows = [{"level": level, "count": count} for level, count in summary.counts.items()]
        metadata = {
            "report": "log-analysis",
            "parser": summary.parser_name,
            "total_lines": summary.total_lines,
            "parsed_lines": summary.parsed_lines,
            "errors": summary.error_count,
            "first_timestamp": summary.first_timestamp.isoformat()
            if summary.first_timestamp
            else None,
            "last_timestamp": summary.last_timestamp.isoformat()
            if summary.last_timestamp
            else None,
            "anomalies": "; ".join(summary.anomalies) or "none",
            "top_errors": [
                {"count": count, "message": message} for count, message in summary.top_errors
            ],
        }
        return self._write("log-analysis", fmt, metadata, headers, rows)

    # ------------------------------------------------------------ generic
    def export_table(
        self,
        stem: str,
        fmt: ExportFormat,
        metadata: dict[str, Any],
        headers: Sequence[str],
        rows: Sequence[dict[str, Any]],
    ) -> Path:
        """Generic report writer shared by all report builders."""
        return self._write(stem, fmt, metadata, headers, rows)

    # ------------------------------------------------------------ core
    def _write(
        self,
        stem: str,
        fmt: ExportFormat,
        metadata: dict[str, Any],
        headers: Sequence[str],
        rows: Sequence[dict[str, Any]],
    ) -> Path:
        settings: AppSettings = self._settings_getter()
        directory = Path(settings.default_export_dir or self._paths.default_export_dir)
        try:
            target = self._target_path(directory, stem, fmt)
            if fmt == "csv":
                self._write_csv(target, headers, rows)
            elif fmt == "json":
                self._write_json(target, metadata, headers, rows)
            elif fmt == "txt":
                self._write_txt(target, metadata, headers, rows)
            else:
                self._write_pdf(target, metadata, headers, rows)
        except OSError as exc:
            raise ExportError(f"Could not write into {directory}: {exc}") from exc
        logger.info("exported %s (%d rows)", target.name, len(rows))
        if self._activity is not None:
            self._activity.record(
                "report.exported",
                module="reports",
                message=f"{target.name} ({fmt}, {len(rows)} rows)",
            )
        return target

    def _target_path(self, directory: Path, stem: str, fmt: ExportFormat) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = directory / f"{stem}-{stamp}.{fmt}"
        counter = 1
        while candidate.exists():  # never overwrite previous reports
            candidate = directory / f"{stem}-{stamp}-{counter}.{fmt}"
            counter += 1
        directory.mkdir(parents=True, exist_ok=True)
        return candidate

    @staticmethod
    def _write_csv(path: Path, headers: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(headers), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _write_json(
        path: Path, metadata: dict[str, Any], headers: Sequence[str], rows: Sequence[dict[str, Any]]
    ) -> None:
        document = {
            "meta": {
                "application": "ITOps Hub",
                "app_version": __version__,
                "generated_at": utc_now().isoformat(),
                **metadata,
            },
            "columns": list(headers),
            "rows": list(rows),
        }
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")

    @staticmethod
    def _write_pdf(
        path: Path, metadata: dict[str, Any], headers: Sequence[str], rows: Sequence[dict[str, Any]]
    ) -> None:
        """Branded PDF report: title, metadata block, paginated table."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        brand = colors.HexColor("#2563eb")
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle", parent=styles["Title"], fontSize=16, textColor=brand, spaceAfter=4
        )
        meta_style = ParagraphStyle(
            "Meta", parent=styles["BodyText"], fontSize=8, textColor=colors.HexColor("#5c6b7a")
        )
        cell_style = ParagraphStyle("Cell", parent=styles["BodyText"], fontSize=8, leading=10)
        head_style = ParagraphStyle(
            "Head", parent=cell_style, textColor=colors.white, fontName="Helvetica-Bold"
        )

        def cell(text: object, style: ParagraphStyle = cell_style) -> Paragraph:
            return Paragraph(str(text).replace("&", "&amp;").replace("<", "&lt;"), style)

        story: list[object] = [
            Paragraph("ITOps Hub Report", title_style),
            Paragraph(
                "generated by ITOps Hub v"
                + __version__
                + " &nbsp;·&nbsp; "
                + " &nbsp;·&nbsp; ".join(f"{key}: {value}" for key, value in metadata.items()),
                meta_style,
            ),
            Spacer(1, 6 * mm),
        ]
        if rows:
            table_data = [[cell(header, head_style) for header in headers]]
            table_data += [[cell(row.get(header, "")) for header in headers] for row in rows]
            available = A4[0] - 24 * mm
            col_width = available / max(len(headers), 1)
            table = Table(
                table_data,
                colWidths=[col_width] * len(headers),
                repeatRows=1,
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), brand),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d4dae0")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f4f6f8")],
                        ),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(table)
        else:
            story.append(Paragraph("No data rows for this report.", meta_style))

        SimpleDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
            title="ITOps Hub Report",
        ).build(story)

    @staticmethod
    def _write_txt(
        path: Path, metadata: dict[str, Any], headers: Sequence[str], rows: Sequence[dict[str, Any]]
    ) -> None:
        widths = {
            header: max(len(header), *(len(str(row.get(header, ""))) for row in rows))
            if rows
            else len(header)
            for header in headers
        }
        lines = ["ITOps Hub report", "=" * 40]
        for key, value in metadata.items():
            lines.append(f"{key:<20} {value}")
        lines += ["", "  ".join(header.ljust(widths[header]) for header in headers)]
        lines.append("  ".join("-" * widths[header] for header in headers))
        for row in rows:
            lines.append(
                "  ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers)
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
