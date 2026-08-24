"""Resource path resolution (dev tree and PyInstaller bundles)."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Absolute path of a file under ``resources/``.

    In frozen builds, PyInstaller unpacks bundled data under ``_MEIPASS``;
    in development, ``resources/`` sits at the repository root.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base.joinpath("resources", *parts)
