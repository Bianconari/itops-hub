"""Standalone API entry point: ``python -m app.api [--port N] [--host H]``.

Binds loopback only by default. The token is printed once and written to the
``api-token`` file in the data directory.
"""

from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from app.application.container import AppContainer

logger = logging.getLogger(__name__)


def write_token_file(container: AppContainer) -> None:
    token_file = container.paths.base / "api-token"
    token_file.write_text(container.api_token, encoding="utf-8")
    import contextlib

    with contextlib.suppress(OSError):  # best-effort permissions (POSIX)
        token_file.chmod(0o600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="itops-api")
    parser.add_argument("--host", default=None, help="bind host (default: settings)")
    parser.add_argument("--port", type=int, default=None, help="bind port (default: settings)")
    args = parser.parse_args(argv)

    container = AppContainer.build()
    settings = container.settings_service.get()
    host = args.host or settings.api.host
    port = args.port or settings.api.port
    if host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning("binding to %s — non-loopback exposure is a deliberate user decision", host)
    write_token_file(container)

    from app.api.app_factory import create_app

    print(f"ITOps Hub API v{container_version()} on http://{host}:{port}")
    print(f"Auth token: {container.api_token}")
    print(f"Token file: {container.paths.base / 'api-token'}")
    uvicorn.run(create_app(container), host=host, port=port, log_level="info")
    return 0


def container_version() -> str:
    from app import __version__

    return __version__


if __name__ == "__main__":
    sys.exit(main())
