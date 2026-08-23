"""ITOps Hub entry point.

Usage:
    python -m app.main                # launch the desktop application
    python -m app.main --version      # print version
    python -m app.main --selftest     # headless core verification (CI/packaged exe)
"""

from __future__ import annotations

import argparse
import logging
import sys

from app import __version__

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ITOpsHub", description="ITOps Hub desktop platform")
    parser.add_argument("--version", action="version", version=f"ITOps Hub {__version__}")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run headless core verification and exit (used by CI and the packaged exe)",
    )
    return parser


def run_selftest() -> int:
    """Headless verification of the core stack (no Qt)."""
    from app.application.container import AppContainer

    container = AppContainer.build(console=False)

    settings = container.settings_service.get()
    assert settings.schema_version >= 1, "settings model failed to load"

    container.activity_service.record(
        "selftest.run", module="app", status="success", message="headless selftest"
    )
    latest = container.activity_service.recent(limit=1)
    assert latest and latest[0].action == "selftest.run", "activity round-trip failed"

    from app.ui.theme.tokens import DARK, build_qss

    assert "QWidget" in build_qss(DARK), "theme stylesheet generation failed"

    container.close()
    print(f"SELFTEST OK — ITOps Hub v{__version__} (db, settings, activity, theme)")
    return 0


def run_desktop() -> int:
    """Launch the desktop application."""
    from PySide6.QtWidgets import QApplication

    from app.application.container import AppContainer
    from app.domain.entities import ActivityStatus
    from app.domain.events import Topics
    from app.ui.main_window.main_window import MainWindow
    from app.ui.theme.theme_service import ThemeService

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("ITOps Hub")
    qt_app.setOrganizationName("ITOpsHub")

    container = AppContainer.build()
    theme = ThemeService(qt_app)
    theme.apply(container.settings_service.get().theme)

    window = MainWindow(container, theme)
    window.show()

    container.bus.publish(Topics.APP_STARTED, None)
    container.activity_service.record("app.started", module="app", status=ActivityStatus.SUCCESS)

    exit_code = qt_app.exec()

    container.activity_service.record("app.stopped", module="app", status=ActivityStatus.SUCCESS)
    container.bus.publish(Topics.APP_STOPPED, None)
    container.close()
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return run_selftest()
    return run_desktop()


if __name__ == "__main__":
    sys.exit(main())
