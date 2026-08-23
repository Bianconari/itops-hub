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
    import traceback

    from app.application.container import AppContainer

    try:
        return _run_selftest(AppContainer.build)
    except Exception:
        # Windowed builds have no stdout: persist the traceback next to the
        # data dir so CI (and users) can see what failed.
        import tempfile

        diagnostic = traceback.format_exc()
        log_path = __import__("pathlib").Path(tempfile.gettempdir()) / "itopshub-selftest.log"
        try:
            log_path.write_text(diagnostic, encoding="utf-8")
        except OSError:
            pass
        print(diagnostic)
        return 1


def _run_selftest(container_factory) -> int:
    container = container_factory(console=False)

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


def start_embedded_api(container):
    """Run the local API on a daemon thread (opt-in via Settings)."""
    import threading

    import uvicorn

    from app.api.app_factory import create_app

    settings = container.settings_service.get()
    config = uvicorn.Config(
        create_app(container),
        host=settings.api.host,
        port=settings.api.port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="itops-api", daemon=True)
    thread.start()
    container.activity_service.record(
        "api.started",
        module="api",
        message=f"http://{settings.api.host}:{settings.api.port}",
    )
    return server


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
